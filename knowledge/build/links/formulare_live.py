#!/usr/bin/env python3
"""Kanonische Formular-Registry (ARCHITEKTUR §3.3/§3.4) aus Quellen + Live-Linkcheck.

    uv run --python 3.12 --with pypdf knowledge/build/links/formulare_live.py

Eingaben:  knowledge/sources/*/out/formulare.jsonl, knowledge/build/seed_formulare.jsonl,
           links/links.jsonl + links/pdf_meta.jsonl (von linkcheck.py), links/seed_kandidaten.json,
           lokale Seed-PDFs unter _Source/ (nur Fallback + Vergleich).
Ausgaben:  links/formulare_live.jsonl      eine Zeile pro kanonischem Formular (dedupliziert)
           links/formular_versionen.jsonl  Versionshistorie je formular_id (sha256, Felder-Hash, gesehen von/bis)
           links/review_queue.jsonl        neue Formularversionen (Feld-Diff), tote Links ohne Ersatz, Seed ohne Live-URL
           links/seed_status.json          Status der Demo-Seed-Formulare (für Gate „Demo-Formulare 100 % live")
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

logging.getLogger("pypdf").setLevel(logging.ERROR)

HERE = Path(__file__).resolve().parent
KNOWLEDGE = HERE.parent.parent
ROOT = KNOWLEDGE.parent
SOURCES = KNOWLEDGE / "sources"
SEED = KNOWLEDGE / "build" / "seed_formulare.jsonl"
LOTSE_ARTEN = {"antrag", "beilage", "merkblatt"}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.open(encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def write_jsonl(p: Path, rows):
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(p)


def norm(s: str | None) -> str:
    s = (s or "").lower().replace("­", "")
    s = s.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def felder_hash(felder: list[dict]) -> str:
    return hashlib.sha256("\n".join(sorted(f["name"] for f in felder)).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- Klassifikation
RE_TARIF = re.compile(r"tarif|gesamtvertrag|zusatzprotokoll|honorar|vertrag|katalog|richtlinie|abrechnung|verordnung|satzung|"
                      r"krankenordnung|anlage [a-z0-9]+ zum|leistungsverzeichnis|vereinbarung|protokoll", re.I)
RE_BEILAGE = re.compile(r"beilage|beiblatt|ergaenzungsblatt|zusatzblatt|anhang zum antrag|nachweis|bestaetigung", re.I)
RE_ANTRAG = re.compile(r"antrag|ansuchen|anmeldung|abmeldung|erklaerung|bedarfsmeldung|meldung|fragebogen|vollmacht|"
                       r"formular|einverstaendnis|zustimmung|einwilligung|verzicht|anzeige|bekanntgabe|aenderung|ersuchen|"
                       r"rueckerstattung|kostenerstattung|bescheinigung|verordnungsschein|befreiung", re.I)
RE_MERKBLATT = re.compile(r"merkblatt|ausfuellhilfe|ausfuellanleitung|hinweise zum|information zum antrag|erlaeuterung", re.I)
RE_BROSCHUERE = re.compile(r"broschuere|folder|ratgeber|leitfaden|ueberblick|flyer|magazin|jahresbericht|"
                           r"information|infoblatt|praesentation|programm|tipps|handbuch|leporello|plakat|english|englisch", re.I)


def klassifiziere(e: dict, link: dict | None, meta: dict | None) -> tuple[str, str]:
    """→ (art, grund)"""
    ctype = (link or {}).get("content_type") or ""
    url = ((link or {}).get("final_url") or e.get("url_pdf") or "").lower()
    path = urlsplit(url).path
    if ctype.startswith("video/") or path.endswith((".mp4", ".mov", ".webm")):
        return "video", f"content_type {ctype or path}"
    name = norm(e.get("name"))
    title = norm((meta or {}).get("title"))
    head = norm((meta or {}).get("text_head"))[:300]
    txt = f"{name} {title}"
    src = e.get("_source")
    if ctype.startswith("text/html"):
        return "info_seite", "HTML-Seite statt Datei"
    if src == "aek_wien" or e.get("wer_fuellt_aus") == "arzt" and RE_TARIF.search(txt):
        if RE_TARIF.search(txt) or src == "aek_wien":
            return "tarif_vertrag", "ÄK-Wien-Vertrags-/Tarifdokument (für Ärzt:innen)"
    if RE_MERKBLATT.search(txt):
        return "merkblatt", "Name: Merkblatt/Ausfüllhilfe"
    if RE_BEILAGE.search(txt) and not re.search(r"^antrag", name):
        return "beilage", "Name: Beilage/Beiblatt/Nachweis"
    if RE_ANTRAG.search(txt):
        return "antrag", "Name: Antrag/Erklärung/Meldung"
    if RE_BROSCHUERE.search(txt):
        return "sonstiges", "Broschüre/Folder/Information (kein Formular)"
    if RE_TARIF.search(txt):
        return "tarif_vertrag", "Name: Tarif/Vertrag"
    if meta and meta.get("acroform") and len(meta.get("felder") or []) >= 3:
        return "antrag", "ausfüllbares PDF (AcroForm)"
    if RE_ANTRAG.search(head):
        return "antrag", "Textanfang: Antrag/Erklärung"
    if ctype and not ctype.startswith("application/pdf") and ctype != "application/octet-stream":
        return "sonstiges", f"content_type {ctype}"
    return "sonstiges", "nicht eindeutig"


RE_GENERIC = re.compile(r"^\s*(pdf|online[- ]?antrag|formular|hier|word|excel|broschuere|broschüre|infoblatt|erklaerung|erklärung|download|link|"
                        r"weitere informationen|mehr|pdf-download)\b|^\s*pdf\s*\(|\(\s*pdf", re.I)
RE_JUNK_TITLE = re.compile(r"^(dokument\d*|untitled|docHdl|ohne titel|microsoft word\s*-?\s*$)|fürs internet|\.dotx?$", re.I)


def clean_title(t: str | None) -> str | None:
    if not t:
        return None
    t = re.sub(r"^microsoft (word|excel) - ", "", t.strip(), flags=re.I)
    t = re.sub(r"\.(dotx?|docx?|xlsx?|pdf)$", "", t, flags=re.I).strip(" _-")
    if len(t) < 6 or RE_JUNK_TITLE.search(t) or re.match(r"^DocHdl", t):
        return None
    return t


def text_title(head: str | None) -> str | None:
    if not head:
        return None
    h = re.sub(r"\s+", " ", head).strip()[:120]
    letters = sum(c.isalpha() or c.isspace() for c in h)
    if len(h) < 10 or letters / len(h) < 0.85:
        return None  # Binärmüll / kaputtes Text-Layer
    return h[:90]


def anzeige_name(name: str | None, meta: dict | None, page_title: str | None) -> tuple[str | None, str]:
    """Generische Linktexte („PDF (0.1MB)“, „Online Antrag“, „hier“) durch PDF-Titel / Textanfang / Seitentitel ersetzen."""
    n = (name or "").strip()
    n_clean = re.sub(r"\s*\(\s*PDF[^)]*\)\s*$", "", n).strip()
    if n_clean and not RE_GENERIC.search(n_clean) and len(n_clean) >= 8:
        return n_clean, "linktext"
    for cand, how in ((clean_title((meta or {}).get("title")), "pdf_titel"), (text_title((meta or {}).get("text_head")), "pdf_text")):
        if cand:
            return cand, how
    if page_title:
        return f"{n_clean or 'Formular'} – {page_title}", "seitentitel"
    return n_clean or name, "linktext"


# --------------------------------------------------------------------------- Lokale Seed-PDFs
def local_pdf_info(rel: str | None) -> dict | None:
    if not rel:
        return None
    p = ROOT / rel
    if not p.exists():
        return None
    b = p.read_bytes()
    try:
        from pypdf import PdfReader
        r = PdfReader(str(p), strict=False)
        fields = r.get_fields() or {}
        felder = [{"name": n, "typ": {"/Tx": "text", "/Btn": "checkbox", "/Ch": "choice", "/Sig": "signature"}.get(str(f.get("/FT")), str(f.get("/FT"))),
                   "label": str(f.get("/TU")) if f.get("/TU") else None}
                  for n, f in fields.items() if not (f.get("/FT") is None and not f.get("/Kids"))]
        title = (r.metadata.title if r.metadata else None)
    except Exception:
        felder, title = [], None
    return {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "felder": felder, "title": title}


def feld_diff(alt: list[dict], neu: list[dict]) -> dict:
    a = {f["name"] for f in alt}
    n = {f["name"] for f in neu}
    return {"entfernt": sorted(a - n), "neu": sorted(n - a), "gleich": len(a & n)}


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


# --------------------------------------------------------------------------- main
def main():
    links = {r["url"]: r for r in load_jsonl(HERE / "links.jsonl")}
    meta = {r["sha256"]: r for r in load_jsonl(HERE / "pdf_meta.jsonl")}
    kand = json.loads((HERE / "seed_kandidaten.json").read_text(encoding="utf-8")) if (HERE / "seed_kandidaten.json").exists() else {}
    stamp = now_iso()
    page_title = {}
    for f in SOURCES.glob("*/out/documents.jsonl"):
        if f.parent.parent.name == "elga":
            continue
        for line in f.open(encoding="utf-8"):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            u = (d.get("url") or "").split("#")[0]
            if u and u not in page_title and d.get("title"):
                page_title[u] = d["title"]

    entries = []
    for f in sorted(SOURCES.glob("*/out/formulare.jsonl")):
        src = f.parent.parent.name
        if src == "elga":
            continue
        for i, d in enumerate(load_jsonl(f), 1):
            d["_source"], d["_line"] = src, i
            entries.append(d)
    seeds = load_jsonl(SEED)
    for i, d in enumerate(seeds, 1):
        d["_source"], d["_line"] = "seed", i

    def link_of(u):
        return links.get((u or "").split("#")[0]) if u else None

    # ---- Gruppierung: sha256 > final_url > url > (ohne URL: eigene Gruppe je Eintrag)
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        lk = link_of(e.get("url_pdf"))
        if lk and lk.get("ok") and lk.get("sha256"):
            key = "sha:" + lk["sha256"]
        elif lk and lk.get("ok") and lk.get("final_url"):
            key = "url:" + lk["final_url"]
        elif e.get("url_pdf"):
            key = "url:" + e["url_pdf"].split("#")[0]
        else:
            key = f"none:{e['_source']}:{e.get('formular_id')}"
        e["_key"], e["_link"] = key, lk
        groups[key].append(e)

    # ---- Seed-Abgleich: lokal sha256 → live sha256; Kandidaten-URL; Feld-/Namensähnlichkeit
    sha_to_key = {k[4:]: k for k in groups if k.startswith("sha:")}
    seed_status = {}
    seed_key = {}
    for s in seeds:
        fid = s["formular_id"]
        loc = local_pdf_info(s.get("local_pdf"))
        st = {"formular_id": fid, "name": s.get("name"), "local_pdf": s.get("local_pdf"),
              "local_sha256": loc and loc["sha256"], "local_n_felder": len(loc["felder"]) if loc else None}
        best = None  # (score, key, how, url)
        if loc and loc["sha256"] in sha_to_key:
            best = (1.0, sha_to_key[loc["sha256"]], "sha256_identisch", None)
        # Kandidaten-URLs (live geprüft)
        for u in kand.get(fid, []):
            lk = links.get(u)
            if not (lk and lk.get("ok") and lk.get("sha256")):
                continue
            m = meta.get(lk["sha256"]) or {}
            if loc and lk["sha256"] == loc["sha256"]:
                sc, how = 1.0, "sha256_identisch"
            else:
                sc = 0.5 + 0.5 * jaccard([x["name"] for x in loc["felder"]] if loc else [], [x["name"] for x in m.get("felder", [])])
                how = "kandidat_recherchiert"
            if not best or sc > best[0]:
                best = (sc, "sha:" + lk["sha256"], how, lk.get("final_url") or u)
        # Feld-Ähnlichkeit gegen alle Live-PDFs (findet neue Versionen unter anderer URL)
        if loc and loc["felder"] and (not best or best[0] < 1.0):
            lnames = [x["name"] for x in loc["felder"]]
            for h, m in meta.items():
                if "sha:" + h not in groups and not any(links.get(u, {}).get("sha256") == h for u in kand.get(fid, [])):
                    continue
                j = jaccard(lnames, [x["name"] for x in m.get("felder", [])])
                if j >= 0.6 and (not best or 0.4 + 0.5 * j > best[0]):
                    best = (0.4 + 0.5 * j, "sha:" + h, f"felder_aehnlich_{j:.2f}", m.get("first_url"))
        if best:
            key = best[1]
            seed_key[fid] = key
            if key not in groups:  # Kandidat nur aus seed_kandidaten.json → eigene Gruppe
                lk = next((links[u] for u in kand.get(fid, []) if links.get(u, {}).get("sha256") == key[4:]), None)
                stub = {"formular_id": fid, "name": s.get("name"), "traeger": s.get("traeger"), "url_pdf": lk and lk["url"],
                        "_source": "seed_kandidat", "_line": 0, "_key": key, "_link": lk}
                groups[key].append(stub)
            st["match"] = best[2]
            st["score"] = round(best[0], 3)
        s["_key"] = seed_key.get(fid, f"none:seed:{fid}")
        s["_link"] = None
        groups[s["_key"]].append(s)
        # Quell-Einträge ohne URL, die dieselbe lokale Kopie meinen (svbox_local, fsw), gehören zum Seed
        for e in entries:
            if s.get("local_pdf") and e.get("local_pdf") == s["local_pdf"] and e["_key"].startswith("none:"):
                groups[e["_key"]].remove(e)
                if not groups[e["_key"]]:
                    del groups[e["_key"]]
                e["_key"] = s["_key"]
                groups[s["_key"]].append(e)
        st["_loc"] = loc
        seed_status[fid] = st

    # ---- Kanonische Einträge
    old_versions = load_jsonl(HERE / "formular_versionen.jsonl")
    vers_by_id = defaultdict(list)
    for v in old_versions:
        vers_by_id[v["formular_id"]].append(v)
    review = []
    out = []
    seen_ids = set()
    for key, members in groups.items():
        seed_m = [m for m in members if m["_source"] == "seed"]
        real = [m for m in members if m["_source"] not in ("seed", "seed_kandidat")]
        lk = next((m["_link"] for m in members if m.get("_link") and m["_link"].get("ok")), None) or \
             next((m["_link"] for m in members if m.get("_link")), None)
        sha = lk.get("sha256") if lk and lk.get("ok") else None
        m_meta = meta.get(sha) if sha else None
        # kanonische ID: Seed-ID, sonst Eintrag der Quelle, deren Host zur URL passt, sonst erster
        host = urlsplit((lk or {}).get("final_url") or "").netloc
        def host_rank(m):
            return 0 if m["_source"].replace("_", "") in host.replace(".", "").replace("-", "") else 1
        primary = seed_m[0] if seed_m else (sorted(real, key=host_rank)[0] if real else members[0])
        fid = primary.get("formular_id") or key
        if fid in seen_ids:
            fid = f"{fid}__{hashlib.sha1(key.encode()).hexdigest()[:6]}"
        seen_ids.add(fid)
        qurl = next((m.get("quelle_url") for m in members if m.get("quelle_url")), None)
        disp, name_how = anzeige_name(primary.get("name"), m_meta, page_title.get((qurl or "").split("#")[0]))
        if seed_m:
            disp, name_how = primary.get("name"), "seed"
        art, grund = klassifiziere(dict(primary, name=disp) if not seed_m else dict(primary, _source="seed"), lk, m_meta)
        if seed_m:
            art, grund = ("beilage" if "beilage" in norm(primary.get("name")) else "antrag"), "Demo-Seed-Formular"
        # URL-Status
        if lk and lk.get("ok"):
            url_status, url_live = "live", lk.get("final_url") or lk["url"]
        elif lk and lk.get("ersetzt_durch"):
            url_status, url_live = "ersetzt_" + (lk.get("ersatz_regel") or "")[:1], lk["ersetzt_durch"]
        elif lk and not lk.get("checked_at"):
            url_status, url_live = "ungeprueft", None
        elif lk:
            url_status, url_live = "tot", None
        else:
            url_status, url_live = "keine_url", None
        # Elternseite (quelle_url), live?
        quelle = next((m.get("quelle_url") for m in real + seed_m if m.get("quelle_url") and m.get("quelle_url") != "https://www.pv.at"), None) \
            or (kand.get("_elternseiten") or {}).get(fid)
        qlk = links.get((quelle or "").split("#")[0]) if quelle else None
        if url_status == "keine_url" and qlk and qlk.get("ok"):
            url_status, url_live = "ersetzt_b", qlk.get("final_url") or quelle
        online = next((m.get("online_url") for m in members if m.get("online_url")), None) \
            or (kand.get("_online_antrag") or {}).get(fid)
        olk = links.get(online) if online else None
        if not lk and url_status in ("keine_url", "ersetzt_b") and online and (olk is None or olk.get("ok")):
            url_status, url_live = "online", online
        felder = (m_meta or {}).get("felder") or []
        rec = {
            "formular_id": fid,
            "name": disp,
            "name_original": primary.get("name"),
            "name_herkunft": name_how,
            "traeger": primary.get("traeger") or next((m.get("traeger") for m in real if m.get("traeger")), None),
            "art": art,
            "art_grund": grund,
            "lotse_zeigen": art in LOTSE_ARTEN and url_status in ("live", "ersetzt_a", "ersetzt_b", "online"),
            "url_status": url_status,  # live | ersetzt_a (gleiche Datei woanders) | ersetzt_b (Elternseite) | tot | keine_url
            "url": url_live,
            "url_original": (lk or {}).get("url") or primary.get("url_pdf"),
            "online_url": online if (olk is None or olk.get("ok")) else None,
            "quelle_url": quelle,
            "quelle_url_ok": (qlk or {}).get("ok"),
            "content_type": (lk or {}).get("content_type"),
            "sha256": sha,
            "bytes": (lk or {}).get("bytes") if sha else None,
            "pages": (m_meta or {}).get("pages"),
            "fillable": bool(felder) if m_meta else None,
            "n_felder": len(felder) if m_meta else None,
            "felder": felder,
            "leistung_ids": sorted({x for m in members for x in (m.get("leistung_ids") or [])}),
            "wer_fuellt_aus": primary.get("wer_fuellt_aus") or next((m.get("wer_fuellt_aus") for m in real if m.get("wer_fuellt_aus")), None),
            "local_pdf": next((m.get("local_pdf") for m in members if m.get("local_pdf")), None),
            "gefunden_auf": sorted({json.dumps({"source": m["_source"], "formular_id": m.get("formular_id"),
                                                 "url": m.get("url_pdf"), "zeile": m["_line"]}, ensure_ascii=False)
                                    for m in members}),
            "geprueft_am": (lk or qlk or {}).get("checked_at"),
            "last_ok_at": (lk or {}).get("last_ok_at") or ((qlk or {}).get("last_ok_at") if url_status == "ersetzt_b" else None),
        }
        det = [json.loads(x) for x in rec["gefunden_auf"]]
        rec["gefunden_auf"] = det  # [{source, formular_id, url, zeile}] – knowledge-db liest formular_id daraus
        rec["gefunden_auf_urls"] = sorted({d["url"] for d in det if d.get("url")})
        rec["alias_ids"] = sorted({d["formular_id"] for d in det if d.get("formular_id") and d["formular_id"] != fid})
        rec["url_pdf"] = url_live if url_status in ("live", "ersetzt_a") and sha else None
        # Seed: lokal vs. live
        if seed_m:
            st = seed_status[seed_m[0]["formular_id"]]
            loc = st.pop("_loc", None)
            if sha and loc:
                if loc["sha256"] == sha:
                    vgl = "identisch"
                else:
                    d = feld_diff(loc["felder"], felder)
                    vgl = "neuere_version_felder_gleich" if not d["entfernt"] and not d["neu"] else "andere_version_felder_anders"
                    st["feld_diff_lokal_vs_live"] = d
                    if vgl != "neuere_version_felder_gleich":
                        review.append({"typ": "seed_formular_felder_abweichend", "formular_id": fid, "lokal": rec["local_pdf"],
                                       "live_url": url_live, "diff": d, "b5_mapping_pruefen": True, "created_at": stamp})
            else:
                vgl = "nicht_gefunden"
                review.append({"typ": "seed_formular_ohne_live_pdf", "formular_id": fid, "fallback": rec["local_pdf"],
                               "elternseite": quelle if (qlk or {}).get("ok") else None, "created_at": stamp})
            st.update({"lokal_vs_live": vgl, "url_status": url_status, "url": url_live, "live_sha256": sha,
                       "live_n_felder": rec["n_felder"], "geprueft_am": rec["geprueft_am"]})
            rec["lokal_vs_live"] = vgl
        # Versionshistorie
        if sha:
            hist = vers_by_id[fid]
            cur = next((v for v in hist if v["sha256"] == sha), None)
            if cur:
                cur["last_seen"] = stamp
                cur["url"] = url_live
            else:
                prev = max(hist, key=lambda v: v["last_seen"]) if hist else None
                v = {"formular_id": fid, "version": len(hist) + 1, "sha256": sha, "url": url_live, "n_felder": len(felder),
                     "felder_hash": felder_hash(felder), "felder": [f["name"] for f in felder],
                     "first_seen": stamp, "last_seen": stamp}
                if prev:
                    d = feld_diff([{"name": n} for n in prev.get("felder", [])], felder)
                    v["diff_zur_vorversion"] = d
                    review.append({"typ": "formular_neue_version", "formular_id": fid, "alt_sha256": prev["sha256"],
                                   "neu_sha256": sha, "felder_diff": d, "b5_mapping_pruefen": bool(d["entfernt"] or d["neu"]),
                                   "url": url_live, "created_at": stamp})
                hist.append(v)
            rec["version"] = next(v["version"] for v in hist if v["sha256"] == sha)
        else:
            rec["version"] = None
        if url_status in ("tot",) and art in LOTSE_ARTEN:
            review.append({"typ": "formular_link_tot_ohne_ersatz", "formular_id": fid, "url": rec["url_original"],
                           "fehler": (lk or {}).get("error"), "created_at": stamp})
        out.append(rec)

    out.sort(key=lambda r: (r["art"] not in LOTSE_ARTEN, r["formular_id"]))
    write_jsonl(HERE / "formulare_live.jsonl", out)
    write_jsonl(HERE / "formular_versionen.jsonl", (v for fid in sorted(vers_by_id) for v in vers_by_id[fid]))
    write_jsonl(HERE / "review_queue.jsonl", review)
    for st in seed_status.values():
        st.pop("_loc", None)
    (HERE / "seed_status.json").write_text(json.dumps(seed_status, ensure_ascii=False, indent=2), encoding="utf-8")

    # Kurzstatistik
    from collections import Counter
    print("Formulare kanonisch:", len(out), "aus", len(entries), "Quell-Einträgen", file=sys.stderr)
    print("art:", dict(Counter(r["art"] for r in out)), file=sys.stderr)
    print("url_status:", dict(Counter(r["url_status"] for r in out)), file=sys.stderr)
    print("lotse_zeigen:", sum(r["lotse_zeigen"] for r in out), file=sys.stderr)
    for fid, st in seed_status.items():
        print(f"  seed {fid}: {st.get('url_status')} {st.get('lokal_vs_live')} {st.get('match')} {st.get('url')}", file=sys.stderr)


if __name__ == "__main__":
    main()
