# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4", "lxml"]
# ///
"""Ärztekammer für Wien (www.aekwien.at) – Kassen-Seiten. `uv run knowledge/sources/aek_wien/ingest.py`.
Inkrementell via bedingtem GET + sha256. PDFs werden NICHT geladen (nur Titel/Link als Formular-/Tarif-Verweis)."""
import sys, re
from pathlib import Path
here = Path(__file__).parent; sys.path.insert(0, str(here.parent / "svs"))
from _common import *
from urllib.parse import unquote

SID = "aek_wien"
SEEDS = ["https://www.aekwien.at/oegk", "https://www.aekwien.at/bvaeb-svs"]
DEPTH1 = ["kfa-wien", "punktewerte-krankenkassen", "empfehlungstarife", "primaerversorgung", "e-card", "vorsorgeuntersuchung", "wahlarzt", "formulare", "digitalisierung"]
LIC = "© Ärztekammer für Wien; öffentliche Seite, Auszug zu Zitatzwecken mit Quellenangabe; robots.txt: nur /web/oak/ und /c/portal/ gesperrt (nicht betroffen)"
TRAEGER = {"oegk": ["ÖGK"], "bvaeb-svs": ["BVAEB", "SVS"]}

def content_node(html):
    s = BeautifulSoup(html, "lxml"); m = s.select_one("#main-content") or s.body
    rows = m.select(":scope > div.portlet-layout")
    c = rows[1] if len(rows) > 1 else m
    for n in c.select("script,style,noscript"): n.decompose()
    t = s.title.string.strip() if s.title and s.title.string else ""
    return s, t, c

def main():
    f = Fetcher(here, SID, hash_fn=lambda h: content_node(h)[2].get_text(' ', strip=True))
    robots_disallow = ("/web/oak/", "/c/portal/")
    pages, queue = {}, list(SEEDS) + [f"https://www.aekwien.at/{x}" for x in DEPTH1]
    for url in queue:
        if any(d in url for d in robots_disallow): continue
        html, st = f.get(url)
        if not html: print("skip", st, url); continue
        pages[url] = html; print("ok", url)
    docs, forms = [], []
    for url, html in pages.items():
        s, t, c = content_node(html)
        slug = url.rstrip("/").split("/")[-1]
        h1 = s.select_one("h1")
        title = (h1.get_text(" ", strip=True) if h1 else "") or t or slug
        nm = {'oegk': 'ÖGK', 'kfa-wien': 'KFA Wien'}.get(slug, title)
        title = f"Ärztekammer Wien – {nm}"
        trg = TRAEGER.get(slug, ["ÖGK", "BVAEB", "SVS", "KFA"] if slug in ("formulare", "e-card", "vorsorgeuntersuchung") else ["ÖGK"])
        secs = [x for x in sections(c, title) if not re.match(r'Navigationsmen|Kontakt$', x[0])]  # Navigation + Ansprechpersonen (personenbezogen) weglassen
        # PDF-/Dokument-Links als eigene Liste (Titel + URL) -> auffindbar, aber nicht geladen
        links = []
        for a in c.select("a[href]"):
            h = urljoin(url, a["href"]); txt = a.get_text(" ", strip=True)
            if "/documents/" in h and txt: links.append((txt, h))
        for txt, h in links:
            forms.append({"formular_id": f"{SID}_{sha1(h)[:10]}", "name": txt, "traeger": "/".join(trg), "url_pdf": h, "local_pdf": None, "fillable": False, "felder": [],
                          "leistung_ids": [], "wer_fuellt_aus": "arzt", "quelle_url": url})
        sh = f.new[url]["sha256"]
        bereich = ["F", "C"]
        docs += build_docs(SID, url, title, secs, sh, trg, ["W"], bereich, "tarif" if slug in ("punktewerte-krankenkassen", "empfehlungstarife") else "faq", LIC)
    write_jsonl(here / "out/documents.jsonl", docs)
    uniq = list({x["url_pdf"]: x for x in forms}.values())
    write_jsonl(here / "out/formulare.jsonl", uniq)
    stellen = [{"stelle_id": "aek_wien_zentrale", "name": "Ärztekammer für Wien", "typ": "beratung", "adresse": "Weihburggasse 10-12, 1010 Wien", "plz": "1010", "bundesland": "W",
                "telefon": "+43 1 51501-0", "email": None, "url": "https://www.aekwien.at", "oeffnungszeiten": None, "zustaendig_fuer": [], "geo": None, "quelle_url": "https://www.aekwien.at/oegk"}]
    write_jsonl(here / "out/stellen.jsonl", stellen)
    leist = []  # Ärztekammer ist keine Leistungsträgerin; Kandidaten nur als Hinweis auf Kassenleistungen (siehe SOURCE.md)
    hpv = find_quotes([d for d in docs], [r"HPV", r"Vorsorgeuntersuchung"], maxn=3)
    if hpv:
        leist.append({"leistung_id": "vorsorgeuntersuchung", "name": "Vorsorgeuntersuchung (Hinweis aus Kassenvertrags-Sicht)", "kurz_einfach": "Die Ärztekammer führt Tarifkataloge und Verträge für Vorsorgeuntersuchungen bei Kassenärzt:innen.",
            "bereich": ["A"], "traeger": ["ÖGK", "BVAEB", "SVS"], "innerhalb_sv": True, "zielgruppe": None, "voraussetzungen": [], "zustaendig": "Abrechnung über die Krankenversicherungsträger; Durchführung bei Vertragsärzt:innen",
            "antrag": {"formular_id": None, "wo": None, "online_url": None}, "unterlagen": [], "fristen": [], "kosten": None, "abhaengigkeiten": [], "trigger_im_dokument": ["Vorsorgeuntersuchung", "HPV"],
            "bundesland": ["W"], "quellen": [{"url": h["quelle_url"], "stand": NOW[:10]} for h in hpv[:1]], "confidence": "niedrig", "belege": hpv})
    write_jsonl(here / "out/leistungen.jsonl", leist)
    f.write_manifest(len(docs))
    print(f"docs={len(docs)} pages={len(pages)} formulare={len(uniq)} leistungen={len(leist)} changed={f.changed}")

if __name__ == "__main__": main()
