# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4", "lxml", "pypdf", "cryptography"]
# ///
"""SVS (www.svs.at). `uv run knowledge/sources/svs/ingest.py`. Inkrementell: bedingte GETs (ETag/Last-Modified), Manifest = Zustand."""
import sys
from pathlib import Path
here = Path(__file__).parent; sys.path.insert(0, str(here))
from portal_ingest import run
from leistungen_svs import leistungen, stellen_override

CFG = dict(source_id="svs", host="www.svs.at", portal="svsportal", traeger=["SVS"], bundesland=["AT"],
    seeds=["https://www.svs.at/", "https://www.svs.at/cdscontent/?contentid=10007.861000&portal=svsportal", "https://www.svs.at/cdscontent/?contentid=10007.846416&portal=svsportal", "https://www.svs.at/cdscontent/?contentid=10007.860990&portal=svsportal"], max_depth=3, max_pages=170,
    license_note="© SVS; öffentliche Webseite www.svs.at, Auszug zu Zitatzwecken mit Quellenangabe; keine robots.txt vorhanden (404)",
    stellen_fn=stellen_override,
    form_hints={"pflegegeld": r"pflege", "wochengeld": r"wochengeld", "kur": r"\bkur|erholung|genesung", "reha_onkologisch": r"reha", "rezeptgebuehrenbefreiung": r"rezeptgebühr|rezeptgebuehr",
                "krankentransport": r"transport", "heilbehelfe": r"heilbehelf|hilfsmittel|brille", "gesundheitshunderter_svs": r"hunderter", "vorsorgeuntersuchung": r"vorsorge"})
if __name__ == "__main__":
    run(CFG, here, leistungen)
