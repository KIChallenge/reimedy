# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4", "lxml"]
# ///
"""gesundheit_gv ingest: www.gesundheit.gv.at + pflege.gv.at -> out/*.jsonl (Schemas A, B, C).
Aufruf: uv run knowledge/sources/gesundheit_gv/ingest.py [--no-fetch]
Idempotent + inkrementell: Abruf konditional (ETag/Last-Modified), Ausgaben werden immer deterministisch aus raw/ neu gebaut."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch
from build import build_outputs

HERE = fetch.HERE
OUT = HERE / "out"

def main():
    OUT.mkdir(exist_ok=True)
    mf = OUT / "manifest.json"
    old = json.loads(mf.read_text()) if mf.exists() else {}
    if "--no-fetch" in sys.argv:
        urls = old.get("urls", [])
    else:
        print("Wähle URLs …")
        sel = fetch.select_urls()
        print(f"{len(sel)} URLs; rufe ab (≤1 req/s) …")
        urls = fetch.fetch_all(sel, old)
    manifest = {"source_id": "gesundheit_gv", "fetched_at": fetch.now(), "n_docs": 0, "urls": urls}
    n = build_outputs(manifest, OUT)
    manifest["n_docs"] = n
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print("fertig:", n, "Dokument-Abschnitte")

if __name__ == "__main__":
    main()
