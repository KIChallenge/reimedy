# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4", "lxml"]
# ///
"""BVAEB (www.bvaeb.at). `uv run knowledge/sources/bvaeb/ingest.py`."""
import sys
from pathlib import Path
here = Path(__file__).parent; sys.path.insert(0, str(here.parent / "svs"))
from portal_ingest import run
from leistungen_bvaeb import leistungen, stellen_override

CFG = dict(source_id="bvaeb", host="www.bvaeb.at", portal="bvaebbportal", traeger=["BVAEB"], bundesland=["AT"],
    seeds=["https://www.bvaeb.at/"], max_depth=3, max_pages=170,
    license_note="© BVAEB; öffentliche Webseite www.bvaeb.at, Auszug zu Zitatzwecken mit Quellenangabe; keine robots.txt vorhanden (404)",
    stellen_fn=stellen_override, stellen_replace=True,
    form_hints={"pflegegeld": r"pflege", "kur": r"\bkur|erholung|genesung", "reha_onkologisch": r"reha", "rezeptgebuehrenbefreiung": r"rezeptgebühr|rezeptgebuehr",
                "krankentransport": r"transport", "heilbehelfe": r"heilbehelf|hilfsmittel|brille", "vorsorgeuntersuchung": r"vorsorge|gesundenuntersuchung"})
if __name__ == "__main__":
    run(CFG, here, leistungen)
