#!/usr/bin/env python3
"""Live-Link-Check (ARCHITEKTUR §3): prüft JEDE URL, die die Lotse-API ausliefern kann.

    uv run --python 3.12 --with httpx,pypdf knowledge/build/links/linkcheck.py [--max-age-h 20] [--budget-min 50]
        [--kinds formular_pdf,online_antrag,stelle,quelle,seite] [--force] [--no-seed-manifest]

Quellen der URLs (alle `knowledge/sources/*/out/*.jsonl` außer elga):
  formular_pdf   ← formulare.url_pdf
  online_antrag  ← leistungen.antrag.online_url, formulare.online_url
  stelle         ← stellen.url
  quelle         ← leistungen.quellen[].url, voraussetzungen[].quelle_url, formulare/stellen/codes.quelle_url
  seite          ← documents.url (ohne #Fragment, dedupliziert)

Prüfung: HEAD; bei 403/405/501 (oder HEAD-Fehler) GET mit `Range: bytes=0-1023`. Redirects werden aufgelöst
(`final_url`). PDFs (kind formular_pdf oder .pdf/application/pdf) werden voll geladen → sha256, Seitenzahl,
AcroForm-Felder, Titel, Textanfang → `pdf_meta.jsonl` (Schlüssel sha256). ≤1 Request/s pro Host, Retry mit
Backoff (Timeout, 5xx, 429/Retry-After). Inkrementell: URLs mit `checked_at` jünger als --max-age-h werden
übersprungen; PDFs mit gespeichertem ETag/Last-Modified werden konditional geladen (304 = unverändert).
Zwischenstände werden alle 100 Ergebnisse atomar geschrieben, d. h. ein abgebrochener Lauf ist nutzbar.

Ausgabe: `links.jsonl` (eine Zeile pro URL), `pdf_meta.jsonl`, danach Ersatzregeln (§3.2) → Felder
`ersetzt_durch`, `ersatz_regel` in links.jsonl.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

HERE = Path(__file__).resolve().parent
KNOWLEDGE = HERE.parent.parent
SOURCES = KNOWLEDGE / "sources"
LINKS = HERE / "links.jsonl"
PDF_META = HERE / "pdf_meta.jsonl"
UA = "SV-Lotse-Hackathon/0.1 (Linkcheck)"
KIND_PRIO = {"formular_pdf": 0, "online_antrag": 1, "stelle": 2, "quelle": 3, "seite": 4}
SKIP_SOURCES = {"elga"}
MAX_PDF = 40 * 1024 * 1024
HOST_INTERVAL = 1.05  # s, ≤1 Request/s pro Host


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_web(u: str) -> bool:
    return u.startswith("http://") or u.startswith("https://")


def clean_url(u: str) -> str:
    return u.strip().split("#")[0]


# --------------------------------------------------------------------------- URL-Sammlung
def collect() -> dict[str, dict]:
    """url → {kinds:set, refs:[{source, file, line, feld, id}]}"""
    out: dict[str, dict] = {}

    def add(u, kind, src, fname, lineno, feld, rid):
        if not u or not isinstance(u, str):
            return
        u = clean_url(u)
        e = out.setdefault(u, {"kinds": set(), "refs": []})
        e["kinds"].add(kind)
        if len(e["refs"]) < 25:
            e["refs"].append({"source": src, "file": fname, "line": lineno, "feld": feld, "id": rid})

    for f in sorted(SOURCES.glob("*/out/*.jsonl")):
        src = f.parent.parent.name
        if src in SKIP_SOURCES:
            continue
        name = f.name
        with f.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if name == "formulare.jsonl":
                    rid = d.get("formular_id")
                    add(d.get("url_pdf"), "formular_pdf", src, name, i, "url_pdf", rid)
                    add(d.get("online_url"), "online_antrag", src, name, i, "online_url", rid)
                    add(d.get("quelle_url"), "quelle", src, name, i, "quelle_url", rid)
                elif name == "leistungen.jsonl":
                    rid = d.get("leistung_id")
                    a = d.get("antrag") or {}
                    if isinstance(a, dict):
                        add(a.get("online_url"), "online_antrag", src, name, i, "antrag.online_url", rid)
                    for q in d.get("quellen") or []:
                        if isinstance(q, dict):
                            add(q.get("url"), "quelle", src, name, i, "quellen[].url", rid)
                    for v in d.get("voraussetzungen") or []:
                        if isinstance(v, dict):
                            add(v.get("quelle_url"), "quelle", src, name, i, "voraussetzungen[].quelle_url", rid)
                elif name == "stellen.jsonl":
                    rid = d.get("stelle_id")
                    add(d.get("url"), "stelle", src, name, i, "url", rid)
                    add(d.get("quelle_url"), "quelle", src, name, i, "quelle_url", rid)
                elif name == "documents.jsonl":
                    add(d.get("url"), "seite", src, name, i, "url", d.get("id"))
                elif name == "codes.jsonl":
                    add(d.get("quelle_url"), "quelle", src, name, i, "quelle_url", d.get("code"))
    # Seed-Formulare (knowledge/build/seed_formulare.jsonl)
    seed = KNOWLEDGE / "build" / "seed_formulare.jsonl"
    if seed.exists():
        for i, line in enumerate(seed.open(encoding="utf-8"), 1):
            d = json.loads(line)
            add(d.get("url_pdf"), "formular_pdf", "seed", seed.name, i, "url_pdf", d.get("formular_id"))
            add(d.get("quelle_url"), "quelle", "seed", seed.name, i, "quelle_url", d.get("formular_id"))
    # Recherchierte Kandidaten für die Demo-Seed-Formulare (links/seed_kandidaten.json)
    kand = HERE / "seed_kandidaten.json"
    if kand.exists():
        kd = json.loads(kand.read_text(encoding="utf-8"))
        for fid, us in kd.items():
            if fid.startswith("_"):
                continue
            for u in us:
                add(u, "formular_pdf", "seed_kandidat", kand.name, 0, "kandidat", fid)
        for fid, u in (kd.get("_online_antrag") or {}).items():
            add(u, "online_antrag", "seed_kandidat", kand.name, 0, "online_antrag", fid)
        for fid, u in (kd.get("_elternseiten") or {}).items():
            add(u, "quelle", "seed_kandidat", kand.name, 0, "elternseite", fid)
        for i, z in enumerate(kd.get("_zusatz_formulare") or [], 1):
            add(z.get("url_pdf"), "formular_pdf", "zusatz", kand.name, i, "url_pdf", z.get("formular_id"))
            add(z.get("quelle_url"), "quelle", "zusatz", kand.name, i, "quelle_url", z.get("formular_id"))
    return out


def primary_kind(kinds) -> str:
    return min(kinds, key=lambda k: KIND_PRIO.get(k, 9))


def manifest_index() -> dict[str, dict]:
    """url → {status, fetched_at, sha256} aus allen manifest.json (für Seed ohne Request)."""
    idx = {}
    for m in SOURCES.glob("*/out/manifest.json"):
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except Exception:
            continue
        urls = data.get("urls")
        if isinstance(urls, dict):
            urls = [dict(v, url=k) if isinstance(v, dict) else {"url": k} for k, v in urls.items()]
        for e in urls or []:
            if not isinstance(e, dict) or not e.get("url"):
                continue
            idx[clean_url(e["url"])] = {"status": e.get("status"), "fetched_at": e.get("fetched_at") or data.get("fetched_at"),
                                         "sha256": e.get("sha256"), "content_type": e.get("content_type")}
    return idx


# --------------------------------------------------------------------------- PDF-Analyse
def pdf_info(data: bytes) -> dict:
    info = {"pages": None, "acroform": False, "felder": [], "title": None, "text_head": "", "parse_error": None}
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data), strict=False)
        info["pages"] = len(r.pages)
        try:
            md = r.metadata
            info["title"] = (md.title if md else None) or None
        except Exception:
            pass
        try:
            fields = r.get_fields() or {}
        except Exception:
            fields = {}
        felder = []
        for name, f in fields.items():
            ft = f.get("/FT")
            if ft is None and not f.get("/Kids"):
                continue
            typ = {"/Tx": "text", "/Btn": "checkbox", "/Ch": "choice", "/Sig": "signature"}.get(str(ft), str(ft))
            felder.append({"name": name, "typ": typ, "label": str(f.get("/TU")) if f.get("/TU") else None})
        info["felder"] = felder
        info["acroform"] = bool(felder)
        try:
            t = (r.pages[0].extract_text() or "") if r.pages else ""
            info["text_head"] = re.sub(r"\s+", " ", t)[:600]
        except Exception:
            pass
    except Exception as e:  # kaputtes PDF
        info["parse_error"] = f"{type(e).__name__}: {e}"[:200]
    return info


# --------------------------------------------------------------------------- Prüfen
class HostGate:
    def __init__(self):
        self.last: dict[str, float] = defaultdict(float)
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def wait(self, host: str):
        async with self.locks[host]:
            d = self.last[host] + HOST_INTERVAL - time.monotonic()
            if d > 0:
                await asyncio.sleep(d)
            self.last[host] = time.monotonic()


async def request(client, gate, method, url, headers=None, stream_full=False):
    """Ein Request inkl. Redirects (jeder Hop über das Host-Gate), Retry/Backoff. → (resp, body|None, err)"""
    last_err = None
    for attempt in range(3):
        try:
            cur = url
            for _hop in range(8):
                await gate.wait(urlsplit(cur).netloc.lower())
                req = client.build_request(method, cur, headers=headers or {})
                resp = await client.send(req, stream=True, follow_redirects=False)
                if resp.is_redirect and resp.headers.get("location"):
                    await resp.aclose()
                    cur = str(resp.url.join(resp.headers["location"]))
                    continue
                body = None
                try:
                    if method == "GET" and stream_full and resp.status_code in (200, 206):
                        buf = bytearray()
                        async for chunk in resp.aiter_bytes():
                            buf.extend(chunk)
                            if len(buf) > MAX_PDF:
                                break
                        body = bytes(buf)
                    elif method == "GET":
                        buf = bytearray()
                        async for chunk in resp.aiter_bytes():
                            buf.extend(chunk)
                            if len(buf) >= 4096:
                                break
                        body = bytes(buf)
                finally:
                    await resp.aclose()
                if resp.status_code == 429 or resp.status_code >= 500:
                    ra = resp.headers.get("retry-after", "")
                    wait = min(int(ra), 30) if ra.isdigit() else 2 * (3 ** attempt)
                    last_err = f"HTTP {resp.status_code}"
                    if attempt < 2:
                        await asyncio.sleep(wait)
                        break  # retry outer
                return resp, body, cur, None
            else:
                return None, None, cur, "zu viele Redirects"
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_err = f"{type(e).__name__}: {e}"[:200]
            if attempt < 2:
                await asyncio.sleep(2 * (3 ** attempt))
        except httpx.HTTPError as e:
            return None, None, url, f"{type(e).__name__}: {e}"[:200]
    return (resp if 'resp' in locals() else None), None, url, last_err


def looks_pdf(url: str, ctype: str | None) -> bool:
    return (ctype or "").lower().startswith("application/pdf") or urlsplit(url).path.lower().endswith(".pdf")


async def check_one(client, gate, url: str, kind: str, prev: dict | None, pdf_meta: dict) -> dict:
    rec = dict(prev or {})
    rec.update({"url": url, "kind": kind, "checked_at": now_iso()})
    rec.setdefault("first_seen", rec["checked_at"])
    rec.setdefault("fail_count", 0)
    rec.setdefault("last_ok_at", None)
    sp = urlsplit(url)
    if not is_web(url) or not sp.netloc:
        rec.update({"http_status": None, "ok": False, "error": "ungueltige_url (kein Host – relativer Link falsch aufgeloest?)",
                    "final_url": None, "method": None})
        rec["fail_count"] += 1
        return rec
    want_full = kind == "formular_pdf" or sp.path.lower().endswith(".pdf")
    resp = body = None
    final = url
    err = None
    method = None
    if want_full:
        hdr = {}
        if prev and prev.get("sha256") and prev.get("sha256") in pdf_meta:
            if prev.get("etag"):
                hdr["If-None-Match"] = prev["etag"]
            if prev.get("last_modified"):
                hdr["If-Modified-Since"] = prev["last_modified"]
        resp, body, final, err = await request(client, gate, "GET", url, hdr, stream_full=True)
        method = "GET"
    else:
        resp, body, final, err = await request(client, gate, "HEAD", url)
        method = "HEAD"
        if resp is None or resp.status_code in (400, 403, 404, 405, 406, 501) or err:
            r2, b2, f2, e2 = await request(client, gate, "GET", url, {"Range": "bytes=0-1023"})
            if r2 is not None:
                resp, body, final, err, method = r2, b2, f2, e2, "GET-Range"
    if resp is None:
        rec.update({"http_status": None, "ok": False, "error": err or "keine Antwort", "final_url": None, "method": method})
        rec["fail_count"] += 1
        return rec
    st = resp.status_code
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower() or None
    rec.update({"http_status": st, "final_url": final, "method": method, "error": None if st < 400 else f"HTTP {st}"})
    if st == 304 and prev:
        rec["ok"] = True
        rec["unveraendert"] = True
    else:
        rec["ok"] = 200 <= st < 300
        rec["content_type"] = ctype
        cl = resp.headers.get("content-range", "")
        m = re.search(r"/(\d+)$", cl)
        rec["bytes"] = int(m.group(1)) if m else (int(resp.headers["content-length"]) if resp.headers.get("content-length", "").isdigit() else None)
        rec["etag"] = resp.headers.get("etag")
        rec["last_modified"] = resp.headers.get("last-modified")
        rec.pop("unveraendert", None)
        if rec["ok"] and body is not None and want_full and (looks_pdf(final, ctype) or body[:5] == b"%PDF-"):
            if len(body) > MAX_PDF:
                rec["sha256"] = None
                rec["error"] = "PDF > 40 MB, nicht gehasht"
            else:
                rec["bytes"] = len(body)
                h = hashlib.sha256(body).hexdigest()
                rec["sha256"] = h
                if body[:5] != b"%PDF-":
                    rec["error"] = "content-type PDF, aber kein %PDF-Header"
                elif h not in pdf_meta:
                    info = await asyncio.to_thread(pdf_info, body)
                    info.update({"sha256": h, "bytes": len(body), "first_url": final, "parsed_at": now_iso()})
                    pdf_meta[h] = info
        elif rec["ok"] and not want_full:
            rec.pop("sha256", None)
        elif rec["ok"] and want_full:
            rec["sha256"] = None  # kein PDF (HTML/Video/Office)
            if body is not None and ctype and not looks_pdf(final, ctype):
                rec["bytes"] = len(body)
    if rec["ok"]:
        rec["last_ok_at"] = rec["checked_at"]
        rec["fail_count"] = 0
    else:
        rec["fail_count"] = int(rec.get("fail_count") or 0) + 1
    return rec


# --------------------------------------------------------------------------- I/O
def load_jsonl(p: Path, key: str) -> dict:
    out = {}
    if p.exists():
        for line in p.open(encoding="utf-8"):
            try:
                d = json.loads(line)
                out[d[key]] = d
            except Exception:
                continue
    return out


def write_jsonl(p: Path, rows):
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n")
    os.replace(tmp, p)


FIELD_ORDER = ["url", "kind", "kinds", "final_url", "http_status", "ok", "content_type", "bytes", "sha256", "checked_at",
               "last_ok_at", "fail_count", "first_seen", "error", "method", "etag", "last_modified", "unveraendert",
               "check_via", "ersetzt_durch", "ersatz_regel", "eltern_url", "refs"]


def ordered(r: dict) -> dict:
    return {k: r.get(k) for k in FIELD_ORDER if k in r} | {k: v for k, v in r.items() if k not in FIELD_ORDER}


def save(links: dict, pdf_meta: dict):
    write_jsonl(LINKS, (ordered(links[u]) for u in sorted(links)))
    write_jsonl(PDF_META, (pdf_meta[h] for h in sorted(pdf_meta)))


# --------------------------------------------------------------------------- Ersatzregeln §3.2
_LINES: dict = {}


def _line(fpath: Path, n: int) -> str | None:
    if fpath not in _LINES:
        try:
            _LINES[fpath] = fpath.read_text(encoding="utf-8").splitlines()
        except Exception:
            _LINES[fpath] = []
    ls = _LINES[fpath]
    return ls[n - 1] if 0 < n <= len(ls) else None


def eltern_url(rec: dict) -> str | None:
    """Seite, auf der der Link gefunden wurde (quelle_url des Formular-/Stellen-Eintrags), ungeprüft."""
    for ref in rec.get("refs") or []:
        if ref.get("file") in ("formulare.jsonl", "seed_formulare.jsonl", "stellen.jsonl") and ref.get("feld") != "quelle_url":
            src = ref["source"]
            fpath = (KNOWLEDGE / "build" / ref["file"]) if src == "seed" else SOURCES / src / "out" / ref["file"]
            try:
                q = json.loads(_line(fpath, ref["line"]) or "{}").get("quelle_url")
            except Exception:
                q = None
            if q and clean_url(q) != rec["url"]:
                return clean_url(q)
    return None


def parent_page(rec: dict, links: dict) -> str | None:
    """Elternseite: quelle_url des Formulars (aus refs) bzw. die Seite, auf der der Link gefunden wurde."""
    for ref in rec.get("refs") or []:
        if ref.get("file") == "formulare.jsonl" or ref.get("file") == "seed_formulare.jsonl":
            src = ref["source"]
            fpath = (KNOWLEDGE / "build" / ref["file"]) if src == "seed" else SOURCES / src / "out" / ref["file"]
            try:
                q = json.loads(_line(fpath, ref["line"]) or "{}").get("quelle_url")
            except Exception:
                q = None
            if q and q != rec["url"]:
                pr = links.get(clean_url(q))
                if pr and pr.get("ok"):
                    return pr.get("final_url") or q
    return None


def repair_relative(url: str, rec: dict) -> list[str]:
    """http:///cdscontent/… → Kandidaten auf dem Host der Quelle (svs/bvaeb)."""
    sp = urlsplit(url)
    if sp.netloc:
        return []
    hosts = {"svs": ["www.svs.at"], "bvaeb": ["www.bvaeb.at"], "oegk": ["www.oegk.at"]}
    cands = []
    for ref in rec.get("refs") or []:
        for h in hosts.get(ref["source"], []):
            c = urlunsplit(("https", h, sp.path, sp.query, ""))
            if c not in cands:
                cands.append(c)
    return cands


def apply_ersatz(links: dict, pdf_meta: dict) -> None:
    by_sha = defaultdict(list)
    for u, r in links.items():
        if r.get("ok") and r.get("sha256"):
            by_sha[r["sha256"]].append(r.get("final_url") or u)
    for u, r in links.items():
        r["eltern_url"] = eltern_url(r)
        r.pop("ersetzt_durch", None)
        r.pop("ersatz_regel", None)
        if r.get("ok"):
            continue
        # (a) gleiche Datei woanders (sha256 der letzten erfolgreichen Version)
        if r.get("sha256") and by_sha.get(r["sha256"]):
            alt = [x for x in by_sha[r["sha256"]] if x != u]
            if alt:
                r["ersetzt_durch"], r["ersatz_regel"] = alt[0], "a_gleicher_sha256"
                continue
        # (a') reparierte relative URL, live geprüft
        for c in repair_relative(u, r):
            cr = links.get(c)
            if cr and cr.get("ok"):
                r["ersetzt_durch"], r["ersatz_regel"] = cr.get("final_url") or c, "a_relative_url_repariert"
                break
        if r.get("ersetzt_durch"):
            continue
        # (b) Elternseite
        pp = parent_page(r, links)
        if pp:
            r["ersetzt_durch"], r["ersatz_regel"] = pp, "b_elternseite"
            continue
        r["ersetzt_durch"], r["ersatz_regel"] = None, "c_ausblenden_review"


# --------------------------------------------------------------------------- main
async def run(args):
    urls = collect()
    links = load_jsonl(LINKS, "url")
    pdf_meta = load_jsonl(PDF_META, "sha256")
    # Kandidaten für reparierte relative URLs mit aufnehmen (werden live geprüft)
    for u, e in list(urls.items()):
        for c in repair_relative(u, {"refs": e["refs"]}):
            urls.setdefault(c, {"kinds": set(e["kinds"]), "refs": [dict(r, feld=r["feld"] + " (repariert)") for r in e["refs"]]})
    # Verwaiste Einträge entfernen (URL wird nicht mehr ausgeliefert)
    for u in list(links):
        if u not in urls:
            del links[u]
    kinds_filter = set(args.kinds.split(",")) if args.kinds else None
    man = manifest_index() if not args.no_seed_manifest else {}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.max_age_h)
    todo = []
    nonweb = 0
    for u, e in urls.items():
        kind = primary_kind(e["kinds"])
        rec = links.setdefault(u, {"url": u, "first_seen": now_iso(), "fail_count": 0, "last_ok_at": None})
        rec["kind"], rec["kinds"], rec["refs"] = kind, sorted(e["kinds"], key=lambda k: KIND_PRIO[k]), e["refs"]
        if not is_web(u):
            if u.startswith(("http:", "https:")):  # http:///… ⇒ ungültig, aber melden
                pass
            else:
                nonweb += 1
                rec.update({"ok": None, "error": "keine_web_url", "http_status": None, "final_url": None, "checked_at": None})
                continue
        if kinds_filter and kind not in kinds_filter:
            continue
        ca = parse_iso(rec.get("checked_at"))
        if not args.force and ca and ca > cutoff and rec.get("http_status") is not None:
            continue
        # Seiten (nicht PDF) mit frischem Manifest-Eintrag (status 200, < max-age) brauchen keinen Request
        m = man.get(u)
        if (m and kind == "seite" and not args.force and m.get("status") in (200, "ok")
                and (parse_iso(m.get("fetched_at")) or datetime.min.replace(tzinfo=timezone.utc)) > cutoff):
            rec.update({"http_status": 200, "ok": True, "final_url": rec.get("final_url") or u, "checked_at": m["fetched_at"],
                        "last_ok_at": m["fetched_at"], "fail_count": 0, "check_via": "manifest", "error": None,
                        "content_type": rec.get("content_type") or m.get("content_type")})
            continue
        todo.append((KIND_PRIO[kind], u, kind))
    todo.sort()
    print(f"URLs gesamt {len(urls)} (nicht-Web {nonweb}); zu prüfen {len(todo)}", file=sys.stderr)

    by_host = defaultdict(list)
    for _, u, kind in todo:
        by_host[urlsplit(u).netloc.lower()].append((u, kind))
    # Große Hosts (z. B. praxisplan.at mit >7.000 Arzt-Seiten aus wien_ogd): pro Lauf höchstens --host-cap Seiten/Stellen,
    # die am längsten ungeprüften zuerst → rollierende Abdeckung über mehrere Läufe, kein Massen-Crawl einer Domain.
    for h, items in by_host.items():
        prio = [x for x in items if x[1] not in ("seite", "stelle")]
        rest = [x for x in items if x[1] in ("seite", "stelle")]
        if len(rest) > args.host_cap:
            rest.sort(key=lambda x: links.get(x[0], {}).get("checked_at") or "")
            print(f"  Host {h}: {len(rest)} Seiten/Stellen, prüfe in diesem Lauf {args.host_cap} (rollierend)", file=sys.stderr)
            rest = rest[: args.host_cap]
        by_host[h] = prio + rest
    gate = HostGate()
    deadline = time.time() + args.budget_min * 60
    done = 0
    lock = asyncio.Lock()
    limits = httpx.Limits(max_connections=64, max_keepalive_connections=32)
    timeout = httpx.Timeout(25.0, connect=10.0)
    async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept": "*/*"}, timeout=timeout, limits=limits,
                                 http2=False, verify=True) as client:
        sem = asyncio.Semaphore(args.hosts_parallel)

        async def host_worker(host, items):
            nonlocal done
            async with sem:
                for u, kind in items:
                    if time.time() > deadline:
                        return
                    try:
                        rec = await check_one(client, gate, u, kind, links.get(u), pdf_meta)
                    except Exception as e:  # nie den Lauf abbrechen
                        rec = dict(links.get(u) or {}, url=u, kind=kind, checked_at=now_iso(), ok=False,
                                   error=f"intern {type(e).__name__}: {e}"[:200])
                        rec["fail_count"] = int(rec.get("fail_count") or 0) + 1
                    rec.pop("check_via", None)
                    async with lock:
                        links[u] = rec
                        done += 1
                        if done % 100 == 0:
                            save(links, pdf_meta)
                            print(f"  {done}/{len(todo)} geprüft", file=sys.stderr)

        # große Hosts zuerst starten, damit sie das Ende nicht dominieren
        hosts = sorted(by_host.items(), key=lambda kv: (min(KIND_PRIO[k] for _, k in kv[1]), -len(kv[1])))
        await asyncio.gather(*(host_worker(h, it) for h, it in hosts))
    apply_ersatz(links, pdf_meta)
    save(links, pdf_meta)
    web = [r for r in links.values() if r.get("ok") is not None or is_web(r["url"]) or r["url"].startswith("http")]
    ok = sum(1 for r in web if r.get("ok"))
    unchecked = sum(1 for r in web if r.get("checked_at") is None)
    print(f"fertig: {done} geprüft in diesem Lauf; Web-URLs {len(web)}, ok {ok}, ungeprüft {unchecked}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-h", type=float, default=20)
    ap.add_argument("--budget-min", type=float, default=55)
    ap.add_argument("--kinds", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-seed-manifest", action="store_true")
    ap.add_argument("--hosts-parallel", type=int, default=24)
    ap.add_argument("--host-cap", type=int, default=1500, help="max. Seiten/Stellen je Host und Lauf (rollierend)")
    ap.add_argument("--ersatz-only", action="store_true", help="nur Ersatzregeln neu anwenden")
    args = ap.parse_args()
    if args.ersatz_only:
        links = load_jsonl(LINKS, "url")
        pdf_meta = load_jsonl(PDF_META, "sha256")
        apply_ersatz(links, pdf_meta)
        save(links, pdf_meta)
        return
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
