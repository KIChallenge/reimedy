#!/usr/bin/env -S uv run --python 3.11
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""reimedy_kb ingestion -> out/codes.jsonl (Schema E) + out/stellen.jsonl (Schema C) + out/manifest.json

Aufruf:
  uv run knowledge/sources/reimedy_kb/ingest.py                 # ICD-10 BMASGPK 2026 + SNOMED + Payer
  uv run knowledge/sources/reimedy_kb/ingest.py --icd-year 2027 # kommende Version (ab 01.01.2027)
  uv run knowledge/sources/reimedy_kb/ingest.py --with-atc      # + ATC (WIdO) -- Lizenz beachten, siehe SOURCE.md
  uv run knowledge/sources/reimedy_kb/ingest.py --basg-file export.json   # BASG aus Export der reimedy-DB
  uv run knowledge/sources/reimedy_kb/ingest.py --offline       # nur raw/-Cache verwenden

Nur Standardbibliothek. Hoeflich: <=1 Request/s, UA ohne E-Mail, robots.txt von
termgit.elga.gv.at erlaubt /CodeSystem-*.  Codes werden NIE gedeutet.
"""
from __future__ import annotations

import argparse, csv, hashlib, html, json, re, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

SRC = "reimedy_kb"
HERE = Path(__file__).resolve().parent
RAW, OUT, REPO = HERE / "raw", HERE / "out", HERE / "repo"
UA = "SV-Lotse-Hackathon/0.1"
TERMGIT = "https://termgit.elga.gv.at/"
REPO_URL = "https://github.com/ArneNostitz/Reimedy_OnlineKnowledgeDB"

# ICD-Version -> Seite auf dem oesterreichischen e-Health-Terminologieserver
ICD_PAGES = {
    "2026": "CodeSystem-icd-10-bmasgpk-2026.html",  # gueltig 2026
    "2027": "CodeSystem-icd-10-bmasgpk-2027.html",  # veroeffentlicht 2026-10-30, gueltig ab 2027
    "2025": "CodeSystem-icd-10-bmsgpk-2025.html",
}
ATC_PAGE = "CodeSystem-atc-deutsch-wido.html"


# ---------------------------------------------------------------- Fetch / Cache
def sha1(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def load_manifest() -> dict:
    p = OUT / "manifest.json"
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return {"source_id": SRC, "urls": []}


def fetch(url: str, prev: dict, offline: bool) -> tuple[bytes, dict]:
    """Konditionaler GET (ETag/Last-Modified). Liefert (bytes, url-eintrag fuer manifest)."""
    cache = RAW / f"{sha1(url)}.html"
    entry = {"url": url, "sha256": None, "etag": None, "last_modified": None, "status": None}
    if offline:
        data = cache.read_bytes()
        entry.update(prev)
        return data, entry
    hdr = {"User-Agent": UA}
    if cache.exists():
        if prev.get("etag"):
            hdr["If-None-Match"] = prev["etag"]
        if prev.get("last_modified"):
            hdr["If-Modified-Since"] = prev["last_modified"]
    time.sleep(1.0)  # <=1 Request/s
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=120) as r:
            data = r.read()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(data)
            entry.update(etag=r.headers.get("ETag"), last_modified=r.headers.get("Last-Modified"), status="ok")
    except urllib.error.HTTPError as e:
        if e.code == 304 and cache.exists():
            data = cache.read_bytes()
            entry.update(prev, status="ok")
        else:
            raise
    entry["sha256"] = hashlib.sha256(data).hexdigest()
    return data, entry


# ---------------------------------------------------------------- FHIR-HTML-Parser
def parse_codesystem_page(raw: bytes) -> tuple[dict, list[dict]]:
    """Terminologieserver-HTML -> (meta, rows). rows = dict header->text."""
    h = raw.decode("utf-8", "replace")
    meta = {}
    for key in ("Version", "Status", "Name", "Title", "Defining URL"):
        m = re.search(rf"<td>{re.escape(key)}:<td>(.*?)<tr>", h, re.S)
        if m:
            meta[key] = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
    i = h.find("<table class=codes")
    if i < 0:
        raise RuntimeError("Codes-Tabelle nicht gefunden (Seitenformat geaendert?)")
    body = h[i : h.find("</table>", i)]
    parts = body.split("<tr>")[1:]

    def cells(r: str) -> list[str]:
        out = []
        for c in r.split("<td")[1:]:
            c = c[c.find(">") + 1 :]  # Attribute abschneiden
            out.append(html.unescape(re.sub(r"<[^>]+>", "", c)).strip())
        return out

    header = cells(parts[0])
    rows = []
    for r in parts[1:]:
        c = cells(r)
        rows.append({header[k]: (c[k] if k < len(c) else "") for k in range(len(header))})
    return meta, rows


# ---------------------------------------------------------------- Hinweise (grob, konservativ)
def _key(code: str) -> tuple[str, int] | None:
    m = re.match(r"^([A-Z])(\d{2})", code)
    return (m.group(1), int(m.group(2))) if m else None


def leistung_hints(code: str) -> list[str]:
    """Nur administrative Kandidaten-Hinweise, KEINE Aussage ueber Person/Krankheit.
    C00-C97, D00-D09 -> reha_onkologisch (D10-D48 bewusst nicht: gutartig/unsicher) ; F00-F99 -> psychosoziale_angebote."""
    rng = code.replace("!", "").split("-")
    ks = [_key(x) for x in rng]
    if any(k is None for k in ks):
        return []
    lo, hi = ks[0], ks[-1]
    if lo[0] != hi[0]:
        return []  # Kapitel-Spannen ueber Buchstaben hinweg: keine Hints
    L = lo[0]
    hints: list[str] = []
    if L == "C" and hi[1] <= 97:
        hints.append("reha_onkologisch")
    elif L == "D" and hi[1] <= 9:
        hints.append("reha_onkologisch")
    elif L == "F":
        hints.append("psychosoziale_angebote")
    return hints


# ---------------------------------------------------------------- Quellen -> Schema E
def icd_codes(rows: list[dict], meta: dict, page_url: str, system: str) -> tuple[list[dict], int]:
    stand = meta.get("Version", "")
    out, skipped = [], 0
    for r in rows:
        code = r["Code"]
        if not re.match(r"^[A-Z]", code):  # numerische LKF-Zusatzcodes (z. B. 101-199) sind kein ICD
            skipped += 1
            continue
        out.append({
            "system": system, "code": code, "label_de": r["Display"], "label_einfach": None,
            "parent": r.get("parent") or None,
            "leistung_hints": leistung_hints(code) if system == "ICD-10-AT" else [],
            "quelle_url": page_url, "stand": stand,
        })
    return out, skipped


def snomed_codes() -> list[dict]:
    """Aus repo/scripts/seed-provider-data.ts (von reimedy kuratierte DE-Labels)."""
    f = REPO / "scripts" / "seed-provider-data.ts"
    txt = f.read_text("utf-8")
    pat = re.compile(r"\{\s*name:\s*'([^']+)',[^}]*?code:\s*'(\d+)',\s*de:\s*'([^']+)',\s*class:\s*'([^']+)'")
    out, seen = [], set()
    for name, code, de, cls in pat.findall(txt):
        if code in seen:
            continue
        seen.add(code)
        out.append({
            "system": "SNOMED-Fachrichtung", "code": code, "label_de": de, "label_einfach": None,
            "parent": None, "leistung_hints": [],
            "quelle_url": f"{REPO_URL}/blob/main/scripts/seed-provider-data.ts",
            "stand": f"reimedy-seed (SNOMED en: {name}; class: {cls})",
        })
    return out


PAYER_SV = [  # aus repo/scripts/seed-standard-info.ts (Eintraege type:'public'); URLs: oeffentliche Traegerseiten
    ("oegk", "ÖGK (Österreichische Gesundheitskasse)", "https://www.gesundheitskasse.at"),
    ("svs", "SVS (Sozialversicherung der Selbständigen)", "https://www.svs.at"),
    ("bvaeb", "BVAEB (Versicherungsanstalt öffentlich Bediensteter, Eisenbahnen und Bergbau)", "https://www.bvaeb.at"),
    ("kfa", "KFA (Krankenfürsorgeanstalt)", None),
]


def payer_stellen() -> list[dict]:
    # Gegencheck gegen Repo-Quelle: Wenn die Public-Payer dort verschwinden, laut warnen.
    src = (REPO / "scripts" / "seed-standard-info.ts").read_text("utf-8")
    for key, *_ in PAYER_SV:
        if {"oegk": "ÖGK"}.get(key, key.upper()) + " (" not in src:
            print(f"WARN: Payer {key} nicht mehr im Repo-Seed gefunden", file=sys.stderr)
    return [{
        "stelle_id": f"traeger_{k}", "name": n, "typ": "traeger", "adresse": None, "plz": None,
        "bundesland": "AT", "telefon": None, "email": None, "url": u, "oeffnungszeiten": None,
        "zustaendig_fuer": [], "geo": None, "quelle_url": f"{REPO_URL}/blob/main/scripts/seed-standard-info.ts",
    } for k, n, u in PAYER_SV]


def basg_codes(path: Path) -> list[dict]:
    """BASG-Export (JSON-Liste oder CSV) mit Feldern authNumber|zulassungsnummer, name, atcCode|atc,
    substances|wirkstoff. Nur administrative Felder."""
    if path.suffix == ".json":
        data = json.loads(path.read_text("utf-8"))
        data = data.get("items", data) if isinstance(data, dict) else data
    else:
        data = list(csv.DictReader(path.open(encoding="utf-8")))
    out = []
    for d in data:
        nr = d.get("authNumber") or d.get("zulassungsnummer") or d.get("concept_code")
        name = d.get("name") or d.get("concept_name")
        if not nr or not name:
            continue
        sub = d.get("substances") or d.get("wirkstoff") or d.get("active_ingredient")
        if isinstance(sub, list):
            sub = ", ".join(sub)
        out.append({
            "system": "BASG", "code": str(nr), "label_de": name, "label_einfach": None,
            "parent": d.get("atcCode") or d.get("atc") or d.get("atc_code") or None,
            "leistung_hints": [], "wirkstoff": sub or None,
            "quelle_url": "https://medikamente.basg.gv.at/", "stand": d.get("stand") or path.name,
        })
    out.sort(key=lambda x: x["code"])
    return out


# ---------------------------------------------------------------- main
def write_jsonl(p: Path, rows: list[dict]) -> None:
    p.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n" for r in rows), "utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--icd-year", default="2026", choices=sorted(ICD_PAGES))
    ap.add_argument("--with-atc", action="store_true")
    ap.add_argument("--basg-file", type=Path)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--since", action="store_true", help="(Vertrag) inkrementell: wird ueber ETag/sha256 ohnehin gemacht")
    a = ap.parse_args()
    RAW.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
    old = load_manifest()
    prev = {u["url"]: u for u in old.get("urls", [])}
    codes, urls, stats = [], [], {}

    def run_cs(page: str, system: str):
        url = TERMGIT + page
        raw, ent = fetch(url, prev.get(url, {}), a.offline)
        meta, rows = parse_codesystem_page(raw)
        c, skipped = icd_codes(rows, meta, url, system)
        stats[system] = {"version": meta.get("Version"), "n": len(c), "skipped_non_icd": skipped, "status": meta.get("Status")}
        ent["version"] = meta.get("Version")
        urls.append(ent)
        return c

    codes += run_cs(ICD_PAGES[a.icd_year], "ICD-10-AT")
    if a.with_atc:
        codes += run_cs(ATC_PAGE, "ATC")
    sn = snomed_codes(); codes += sn; stats["SNOMED-Fachrichtung"] = {"n": len(sn)}
    if a.basg_file:
        b = basg_codes(a.basg_file); codes += b; stats["BASG"] = {"n": len(b), "file": a.basg_file.name}
    else:
        stats["BASG"] = {"n": 0, "note": "kein --basg-file; Live-Abruf bewusst nicht implementiert (siehe SOURCE.md)"}
    stellen = payer_stellen()

    write_jsonl(OUT / "codes.jsonl", codes)
    write_jsonl(OUT / "stellen.jsonl", stellen)
    for f in ("seed-provider-data.ts", "seed-standard-info.ts"):
        p = REPO / "scripts" / f
        urls.append({"url": f"{REPO_URL}/blob/main/scripts/{f}", "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                     "etag": None, "last_modified": None, "status": "local-clone"})
    manifest = {
        "source_id": SRC,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_docs": 0, "n_codes": len(codes), "n_stellen": len(stellen), "stats": stats, "urls": urls,
    }
    # fetched_at nur aendern, wenn sich Inhalte geaendert haben (idempotente Re-Runs)
    if old.get("urls") and [(u["url"], u["sha256"]) for u in old["urls"]] == [(u["url"], u["sha256"]) for u in urls] \
            and old.get("n_codes") == len(codes):
        manifest["fetched_at"] = old["fetched_at"]
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"n_codes": len(codes), "n_stellen": len(stellen), "stats": stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
