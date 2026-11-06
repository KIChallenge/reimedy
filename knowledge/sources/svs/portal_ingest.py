"""Gemeinsamer Ablauf für svs/bvaeb. Konfiguration kommt aus <src>/config.py (CFG)."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

def run(cfg, base: Path, extra=None):
    f = Fetcher(base, cfg["source_id"], hash_fn=portal_hash)
    pages = crawl_portal(f, cfg["host"], cfg["portal"], cfg["seeds"], cfg.get("max_depth", 3), cfg.get("max_pages", 160))
    docs = []
    for url, p in pages.items():
        s, title, c = extract_portal(p["html"])
        h1 = (s.select_one("h1") or s.select_one("h2"))
        t = h1.get_text(" ", strip=True) if h1 else title
        if title and len(title) < 90 and title.lower() not in ("startseite",): t = title if not h1 or len(t) > 90 else t
        secs = sections(c, t)
        if not secs: continue
        sh = f.new[url].get("sha256") or sha256(p["html"].encode())
        bereich = guess_bereich(t + " " + " ".join(x for _, x in secs[:2]))
        dt_ = "formular" if re.search(r"formular|antrag", t, re.I) else "leistungsinfo"
        docs += build_docs(cfg["source_id"], url, t, secs, sh, cfg["traeger"], cfg["bundesland"], bereich, dt_, cfg["license_note"])
    write_jsonl(base / "out/documents.jsonl", docs)
    forms = collect_formulare(pages, cfg["host"], cfg["source_id"], cfg["traeger"][0], cfg["form_hints"])
    forms = enrich_forms(f, forms)
    write_jsonl(base / "out/formulare.jsonl", forms)
    stellen = collect_stellen(docs, cfg["source_id"], cfg["traeger"][0], cfg["host"])
    if cfg.get("stellen_fn"): stellen = cfg["stellen_fn"](docs) + [x for x in stellen if not cfg.get("stellen_replace")]
    stellen = geocode_stellen(f, stellen)
    write_jsonl(base / "out/stellen.jsonl", stellen)
    leist = extra(docs, pages, cfg) if extra else []
    write_jsonl(base / "out/leistungen.jsonl", leist)
    f.write_manifest(len(docs))
    print(f"docs={len(docs)} pages={len(pages)} formulare={len(forms)} stellen={len(stellen)} leistungen={len(leist)} changed={f.changed}")
