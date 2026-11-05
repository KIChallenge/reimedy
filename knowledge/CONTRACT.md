# Wissens-DB: gemeinsamer Datenvertrag (verbindlich für alle Ingestion-Sessions)

Ziel: Alle Quellen landen in **einem** einheitlichen Format. Daraus baut `knowledge/build/` eine SQLite-DB (FTS5 + optional Embeddings) plus den **Leistungsgraphen**. Jede Quelle muss **wiederholbar aktualisiert** werden können.

## Ordner
```
knowledge/
  CONTRACT.md                ← diese Datei (nur der Koordinator ändert sie)
  sources/<source_id>/       ← EINE Session pro source_id, schreibt NUR hier
    ingest.py                ← idempotent; `uv run knowledge/sources/<id>/ingest.py [--since]`
    SOURCE.md                ← was, wie, Lizenz/robots-Notiz, Abdeckung, Lücken, Update-Strategie
    raw/                     ← Rohdaten (HTML/PDF/XML), Dateiname = sha1(url).ext   (gitignore-fähig)
    out/documents.jsonl      ← normalisierte Dokumente (Schema A)
    out/leistungen.jsonl     ← Leistungs-Kandidaten (Schema B), soweit erkennbar
    out/stellen.jsonl        ← Stellen/Einrichtungen/Kontakte (Schema C), soweit erkennbar
    out/formulare.jsonl      ← Formulare (Schema D), soweit erkennbar
    out/manifest.json        ← {source_id, fetched_at, n_docs, urls:[{url, sha256, etag, last_modified, status}]}
  build/                     ← Koordinations-Session „knowledge-db": Loader, DB, Graph, Update-Runner, Such-API
```
source_ids: `oegk`, `aek_wien`, `fsw`, `svs`, `bvaeb`, `sozdok_ris`, `gesundheit_gv`, `oesterreich_gv`, `svbox_local`, **`reimedy_kb`** (reimedy Knowledge-DB: ICD-10-AT, BASG-Medikamente, SNOMED-Fachrichtungen, Payer-Liste; Entscheidung des Users: wird **auf jeden Fall** eingebunden), **`elga`** (ELGA-Anbindung: Befunde/e-Befund, e-Medikation, e-Impfpass, Termine; Entscheidung des Users: wird **auf jeden Fall** eingebunden).

**Zusatz-Schema E: `codes.jsonl`** (für reimedy_kb)
```json
{"system":"ICD-10-AT|ATC|BASG|SNOMED-Fachrichtung", "code":"C20", "label_de":"Bösartige Neubildung des Rektums",
 "label_einfach":null, "parent":"C15-C26", "leistung_hints":["reha_onkologisch"], "quelle_url":"…", "stand":"…"}
```
Verwendung von ICD/Medikation nur **administrativ**: Codes normalisieren, Dokumente strukturieren, Fachrichtung und Zuständigkeit finden (z. B. C-Kapitel → onkologische Reha bzw. PVA-Rehazentren) und Leistungen *als Kandidaten* triggern. Codes werden **nie** gedeutet und **nie** für eine Risiko- oder Therapieaussage verwendet. Labels werden wörtlich angezeigt.

## Schema A: `documents.jsonl` (eine Zeile = ein zitierbarer Abschnitt, max. ~2.000 Zeichen)
```json
{"id":"oegk:sha1(url)#3", "source_id":"oegk", "url":"https://…", "title":"Pflegegeld",
 "section":"Voraussetzungen", "text":"…Klartext…", "lang":"de",
 "traeger":["ÖGK"], "bundesland":["W"] | ["AT"], "bereich":["D"],
 "doc_type":"leistungsinfo|formular|recht|kontakt|faq|broschuere|tarif",
 "valid_from":"2026-01-01"|null, "fetched_at":"2026-11-05T20:00:00Z", "sha256":"…",
 "license_note":"…"}
```
`bereich` = Challenge-Bereiche A Vorsorge · B Gesundheitsförderung · C Behandlung/Reha/Nachsorge · D Pflege · E Sozial/Finanziell · F Administration.

## Schema B: `leistungen.jsonl` (Kandidaten für den Leistungsgraphen, Mensch reviewt später)
```json
{"leistung_id":"pflegegeld", "name":"Pflegegeld", "kurz_einfach":"1–2 Sätze, einfache Sprache",
 "bereich":["D"], "traeger":["PVA","ÖGK","SVS","BVAEB"], "innerhalb_sv":true,
 "zielgruppe":"…", "voraussetzungen":[{"text":"Pflegebedarf > 65 h/Monat", "quelle_url":"…", "zitat":"wörtlich"}],
 "zustaendig":"…Regel, wer zuständig ist…", "antrag":{"formular_id":"pva_pal080", "wo":"…", "online_url":"…"},
 "unterlagen":["…"], "fristen":["…"], "kosten":"…", "abhaengigkeiten":["rezeptgebuehrenbefreiung"],
 "trigger_im_dokument":["Pflegegeld", "Pflegebedarf"], "bundesland":["AT"],
 "quellen":[{"url":"…","stand":"2026-…"}], "confidence":"hoch|mittel|niedrig"}
```
`leistung_id` in snake_case, deutsch, stabil (z. B. `rezeptgebuehrenbefreiung`, `reha_onkologisch`, `vorsorgeuntersuchung`, `gesundheitshunderter_svs`, `bewegt_im_park`). Lieber einen bestehenden Namen aus dieser Liste wiederverwenden als eine Variante erfinden.

## Schema C: `stellen.jsonl`
```json
{"stelle_id":"fsw_beratungszentrum_pflege", "name":"…", "typ":"traeger|beratung|einrichtung|hotline|arzt|apotheke|pve",
 "adresse":"…", "plz":"1030", "bundesland":"W", "telefon":"…", "email":"…", "url":"…",
 "oeffnungszeiten":"…", "zustaendig_fuer":["pflegegeld"], "geo":[lat,lon]|null, "quelle_url":"…"}
```

## Schema D: `formulare.jsonl`
```json
{"formular_id":"pva_pal080", "name":"Antrag auf Pflegegeld", "traeger":"PVA", "url_pdf":"…",
 "local_pdf":"_Source/…"|null, "fillable":true, "felder":[{"name":"…","label":"…","typ":"text|checkbox","quelle_hint":"vorname"}],
 "leistung_ids":["pflegegeld"], "wer_fuellt_aus":"versicherte|arzt|krankenhaus", "quelle_url":"…"}
```

## Regeln
- **Keine medizinischen Inhalte als Empfehlung modellieren.** Medizinische Texte nur als Quelle mit Zitat. EKO bzw. Medikamente nur administrativ (Erstattung oder Bewilligungspflicht).
- Crawling: robots.txt respektieren, ≤1 Request/s, generischer User-Agent `SV-Lotse-Hackathon/0.1` **ohne E-Mail**, nur öffentliche Seiten, kein Login. Kein Massen-Crawl ganzer Domains: Themen-Seeds und eine Tiefe von max. 2–3 Ebenen.
- Updates: `ingest.py` vergleicht ETag, Last-Modified und sha256 und verarbeitet nur Geänderte neu. `manifest.json` ist der Zustand.
- Python ≥3.11 über `uv run --with <pkgs>` (System-Python ist 3.9). Keine globalen Installs.
- Fertig = `out/*.jsonl` existiert, validiert gegen das Schema, und `SOURCE.md` beschreibt die Abdeckung ehrlich (inklusive dem, was fehlt).
