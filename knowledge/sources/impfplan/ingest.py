# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=4.3"]
# ///
"""Österreichischer Impfplan (BMASGPK) → impfplan_intervalle.jsonl + documents.jsonl (Seiten der genutzten Kapitel).

    uv run knowledge/sources/impfplan/ingest.py [--offline]

- Lädt das aktuelle PDF (bedingter GET über ETag/Last-Modified, sha256 im Manifest).
- Die Intervall-Zeilen sind kuratiert (KURATIERT unten), aber JEDES Zitat wird beim Lauf wörtlich gegen den
  PDF-Text der angegebenen Seite geprüft (Whitespace normalisiert). Fehlt ein Zitat (neue Version, geänderter
  Wortlaut), bricht der Lauf ab → Mensch prüft, statt falsche Intervalle auszuliefern.
- Neue Impfplan-Version: VERSION/GUELTIG_AB/URL anpassen, Lauf zeigt, welche Zitate nicht mehr passen.
Nur administrativ: Der Lotse gibt die Empfehlung DES IMPFPLANS mit Version weiter; ob eine Impfung im Einzelfall
passt, klärt die Ärztin (loesungen/05 §6.4).
"""
import argparse
import hashlib
import io
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW, OUT = HERE / "raw", HERE / "out"
SOURCE_ID = "impfplan"
URL = "https://broschuerenservice.sozialministerium.gv.at/Home/Download?publicationId=420&attachmentName=Impfplan_Oesterreich_2026_2027.pdf"
SEITE_URL = "https://www.sozialministerium.gv.at/Themen/Gesundheit/Impfen/impfplan.html"
VERSION = "Impfplan Österreich 2026/2027, Version 1.1 vom 14.10.2026"
GUELTIG_AB = "2026-10-14"
UA = "SV-Lotse-Hackathon/0.1"
LICENSE = "© BMASGPK, Impfplan Österreich – öffentliches Dokument; Zitate wörtlich mit Quelle und Version"

# Kuratierte Intervalle. intervall_monate = Abstand zur nächsten Impfung laut Plan (None = einmalig/keine Auffrischung).
KURATIERT = [
    {"id": "influenza_erwachsene", "krankheit": "Influenza", "impfung": "Influenza (Echte Grippe)",
     "altersgruppe": "Erwachsene", "alter_von": 18, "alter_bis": None, "intervall": "jährlich (Saison)",
     "intervall_monate": 12, "dosen": 1, "zeitpunkt": "Mitte Oktober/November",
     "kostenlos_impfprogramm": True, "leistung_id": "impfungen_erwachsene",
     "zitate": [(52, "Die Influenza-Impfung ist für alle Erwachsenen empfohlen und steht im öffentlichen Impfprogramm gratis zur Verfügung"),
                (56, "Ab dem vollendeten 9. Lebensjahr jährliche Impfung"),
                (55, "Idealerweise wird die Influenza-Impfung Mitte Oktober/im November verabreicht.")]},
    {"id": "influenza_ab_60", "krankheit": "Influenza", "impfung": "Influenza (Echte Grippe)",
     "altersgruppe": "ab 60 Jahren", "alter_von": 60, "alter_bis": None, "intervall": "jährlich (Saison), Impfstoffe speziell für diese Altersgruppe",
     "intervall_monate": 12, "dosen": 1, "zeitpunkt": "Mitte Oktober/November",
     "kostenlos_impfprogramm": True, "leistung_id": "impfungen_erwachsene",
     "zitate": [(56, "Besonders für Menschen ab dem vollendeten 60. Lebensjahr und noch nachdrücklicher ab dem vollendeten 65. Lebensjahr ist die jährliche Influenza-Impfung mit einem der Impfstoffe, die speziell für diese Altersgruppe entwickelt wurden, empfohlen.")]},
    {"id": "tdap_bis_60", "krankheit": "Diphtherie-Tetanus-Pertussis", "impfung": "Tdap-Auffrischung (3-fach)",
     "altersgruppe": "Erwachsene bis 60 Jahre", "alter_von": 18, "alter_bis": 59, "intervall": "alle 10 Jahre",
     "intervall_monate": 120, "dosen": 1, "zeitpunkt": None, "kostenlos_impfprogramm": False, "leistung_id": "impfungen_erwachsene",
     "zitate": [(22, "Danach Auffrischungsimpfungen mit 3-fach-Impfstoffen gegen Diphtherie-Tetanus-Pertussis (z.B. Boostrix) bis zum vollendeten 60. Lebensjahr alle 10 Jahre.")]},
    {"id": "tdap_ab_60", "krankheit": "Diphtherie-Tetanus-Pertussis", "impfung": "Tdap-Auffrischung (3-fach)",
     "altersgruppe": "ab 60 Jahren", "alter_von": 60, "alter_bis": None, "intervall": "alle 5 Jahre",
     "intervall_monate": 60, "dosen": 1, "zeitpunkt": None, "kostenlos_impfprogramm": False, "leistung_id": "impfungen_erwachsene",
     "zitate": [(22, "Ab dem vollendeten 60. Lebensjahr Auffrischungsimpfungen mit 3-fach-Impfstoffen gegen Diphtherie-Tetanus-Pertussis alle 5 Jahre.")]},
    {"id": "zoster_ab_60", "krankheit": "Herpes Zoster", "impfung": "Herpes Zoster (Gürtelrose), Totimpfstoff",
     "altersgruppe": "ab 60 Jahren", "alter_von": 60, "alter_bis": None, "intervall": "2 Dosen im Abstand von mindestens 2 Monaten (2–6 Monate); derzeit keine Auffrischung",
     "intervall_monate": None, "dosen": 2, "zeitpunkt": None, "kostenlos_impfprogramm": True, "leistung_id": "impfungen_erwachsene",
     "zitate": [(123, "Die Impfung gegen Herpes Zoster (HZ) ist für Personen ab dem vollendeten 50. Lebensjahr zugelassen und wird ab dem vollendeten 60. Lebensjahr für alle empfohlen."),
                (123, "Die Impfung steht für Personen ab dem vollendeten 60. Lebensjahr und Personen mit spezieller Indikation ab dem vollendeten 18. Lebensjahr im öffentlichen Impfprogramm gratis zur Verfügung"),
                (126, "Der Totimpfstoff wird 2-malig i.m. in einem Abstand von mindestens 2 Monaten (2–6 Monate möglich) verabreicht."),
                (126, "Derzeit ist keine Auffrischungsimpfung empfohlen.")]},
    {"id": "pneumokokken_ab_60", "krankheit": "Pneumokokken", "impfung": "Pneumokokken PCV21 (Capvaxive)",
     "altersgruppe": "ab 60 Jahren (ohne spezielle Indikation)", "alter_von": 60, "alter_bis": None, "intervall": "einmalig",
     "intervall_monate": None, "dosen": 1, "zeitpunkt": None, "kostenlos_impfprogramm": True, "leistung_id": "impfungen_erwachsene",
     "zitate": [(90, "Lebensjahr wird die kostenlose Impfung mit Capvaxive im öffentlichen Impfprogramm empfohlen."),
                (92, "Einmalige Impfung. Es gibt derzeit noch keine Daten, ob/wann für Personen ab 60 Jahren weitere Pneumokokken-Impfungen notwendig sind."),
                (89, "Für Personen ab dem vollendeten 5. bis zum vollendeten 60. Lebensjahr ohne spezielle Indikation wird keine Pneumokokken-Impfung empfohlen.")]},
]
# Kapitel-Seiten, die als zitierbare Dokumente (RAG) mitgeliefert werden
KAPITEL = {"Diphtherie / Tdap": range(20, 23), "Influenza (Echte Grippe)": range(52, 57),
           "Pertussis": range(82, 85), "Pneumokokken": range(89, 93), "Herpes Zoster": range(123, 127)}


def ws(s: str) -> str:
    s = s.replace("­", "").replace("-\n", "-")
    return re.sub(r"\s+", " ", s).strip()


def fetch(offline: bool, manifest: dict) -> tuple[bytes, dict]:
    RAW.mkdir(exist_ok=True)
    local = RAW / (hashlib.sha1(URL.encode()).hexdigest() + ".pdf")
    prev = next((u for u in manifest.get("urls", []) if u["url"] == URL), {})
    if offline and local.exists():
        return local.read_bytes(), prev | {"status": "offline"}
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    if local.exists() and prev.get("etag"):
        req.add_header("If-None-Match", prev["etag"])
    if local.exists() and prev.get("last_modified"):
        req.add_header("If-Modified-Since", prev["last_modified"])
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
            meta = {"etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified"), "status": r.status}
    except urllib.error.HTTPError as e:
        if e.code == 304 and local.exists():
            return local.read_bytes(), prev | {"status": 304}
        raise
    local.write_bytes(data)
    return data, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--since", nargs="?", const="manifest")  # Vertrag: inkrementell über manifest (ETag/sha256)
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    mf = OUT / "manifest.json"
    manifest = json.loads(mf.read_text()) if mf.exists() else {}
    data, meta = fetch(a.offline, manifest)
    sha = hashlib.sha256(data).hexdigest()
    import pypdf
    pages = [ws(p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(data)).pages]
    if not any(VERSION.split(",")[1].strip().split(" vom")[0] in p for p in pages[:3]):
        sys.exit(f"Version passt nicht: '{VERSION}' nicht auf den ersten Seiten gefunden – neue Fassung? KURATIERT prüfen.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    fehler, rows = [], []
    for k in KURATIERT:
        zit = []
        for seite, z in k["zitate"]:
            if ws(z) not in pages[seite - 1]:
                fehler.append(f"{k['id']}: Zitat nicht wörtlich auf S. {seite}: {z[:70]}…")
            zit.append({"seite": seite, "zitat": z, "url": f"{URL}#page={seite}"})
        row = {kk: v for kk, v in k.items() if kk != "zitate"}
        rows.append(row | {"zitate": zit, "zitat": zit[0]["zitat"], "seite": zit[0]["seite"], "version": VERSION,
                           "gueltig_ab": GUELTIG_AB, "quelle_url": URL, "quelle_seite": SEITE_URL, "pdf_sha256": sha,
                           "stand": now[:10], "hinweis": "Empfehlung laut Impfplan (mit Version). Ob die Impfung im "
                                                         "Einzelfall passt, klärt die Ärztin beim Termin."})
    if fehler:
        sys.exit("Zitatprüfung fehlgeschlagen:\n  " + "\n  ".join(fehler))

    docs = []
    for titel, rng in KAPITEL.items():
        for s in rng:
            text = pages[s - 1]
            for i in range(0, len(text), 1800):
                docs.append({"id": f"{SOURCE_ID}:{sha[:12]}:S{s}#{i // 1800}", "source_id": SOURCE_ID, "url": f"{URL}#page={s}",
                             "title": f"Impfplan Österreich 2026/2027 – {titel}", "section": f"Seite {s}", "text": text[i:i + 1800],
                             "lang": "de", "traeger": ["BMASGPK"], "bundesland": ["AT"], "bereich": ["A"], "doc_type": "broschuere",
                             "valid_from": GUELTIG_AB, "fetched_at": now, "sha256": hashlib.sha256(text[i:i + 1800].encode()).hexdigest(),
                             "license_note": LICENSE})
    with (OUT / "impfplan_intervalle.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (OUT / "documents.jsonl").open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    mf.write_text(json.dumps({"source_id": SOURCE_ID, "fetched_at": now, "n_docs": len(docs), "n_intervalle": len(rows),
                              "version": VERSION, "gueltig_ab": GUELTIG_AB,
                              "urls": [{"url": URL, "sha256": sha, "etag": meta.get("etag"), "last_modified": meta.get("last_modified"),
                                        "status": meta.get("status")}]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{VERSION}: {len(rows)} Intervalle (alle Zitate wörtlich geprüft), {len(docs)} Abschnitte, sha256 {sha[:12]}")


if __name__ == "__main__":
    main()
