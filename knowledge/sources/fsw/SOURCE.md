# Quelle `fsw` – Fonds Soziales Wien (www.fsw.at)

Stand Abruf: 2026-11-05. **Außerhalb der SV** (Land Wien): alle Leistungen `innerhalb_sv:false`, `bundesland:["W"]`, `traeger:["FSW"]`.

## Was
Öffentliche Seiten zu Pflege und Betreuung (mobile Dienste, Heimhilfe, Hauskrankenpflege, Essen auf Rädern, Besuchsdienst, Tageszentren, Senior:innen-WG, Wohn- und Pflegehäuser, Urlaubs-/Übergangspflege, Palliativ), Kostenbeitrag, Behinderung und Inklusion, Obdach/Wohnungslosigkeit, Standorte und Antragsformulare.
Ablauf der Antragstellung (von `/antrag`): online über MeinFSW (mein.fsw.at), telefonisch/per E-Mail (kundinnenservice@fsw.at) beim Kund:innenservice 01 24 5 24 (täglich 8–20 Uhr), per Post oder persönlich in den Beratungs- und Service-Centern. Elektronische Signatur nur mit Original-PDF (ID Austria/PrimeSign).

## Ergebnis (`out/`)
| Datei | Zeilen | Inhalt |
|---|---|---|
| documents.jsonl | 629 | 90 Seiten, abschnittsweise (≤1.800 Zeichen); FAQ-Antworten aus JSON-LD |
| leistungen.jsonl | 36 | kuratierte Kandidaten (`leistungen_def.py`), Voraussetzungen/Kosten/Ablauf **wörtlich aus Seitenabschnitten** |
| stellen.jsonl | 11 | 4× Beratungszentrum Pflege und Betreuung (Guglgasse 7–9, Rudolf-Köppl-Gasse 2, Graumanngasse 7, Heiligenstädter Str. 31), Behinderung/Inklusion, Obdach (Lederergasse 25), Geflüchtete, Ombudsstelle, Kostenbeitrag, Hotline |
| formulare.jsonl | 26 | alle PDF-Links von `/antrag` + Filterseite + Leistungsseiten (PGE, Frühförderung u. a.), AcroForm-Felder via `pypdf` |
| abgleich_lokale_formulare.json | – | Vergleich lokal vs. online |
| manifest.json | – | URL, sha256, ETag, Last-Modified, Status |

## Abgleich lokaler Formulare (`_Source/Anträge und Formulare/`)
- `fsw-antrag-auf-foerderung-von-leistungen.1779095804.pdf` → **identisch** (sha256, 13 Seiten, 122 Felder) mit Online-Version vom 2026-11-05. Aktuell.
- `FSW-Antrag-Beilage-Einrichtungswunsch.1779345450.pdf` → **identisch** (sha256, 2 Seiten, 13 Felder). Aktuell.
- `Bedarfsmeldung-Senior_innen-Wohngemeinschaft_Basispaket.1736522017.pdf` → **Aktualität nicht prüfbar**: auf keiner geprüften FSW-Seite (auch nicht `/p/seniorinnen-wohngemeinschaften-basispaket`) verlinkt. Zeitstempel im Dateinamen ≈ Jan 2025, also älter als die anderen beiden; Rückfrage beim FSW-Kund:innenservice bzw. Partnerorganisation nötig. Felder (21) trotzdem extrahiert.

## Update-Strategie
`uv run knowledge/sources/fsw/ingest.py` (≤1 Req/s, UA `SV-Lotse-Hackathon/0.1`, robots.txt: nur `/cpresources/`, `/vendor/`, `/.env`, `/cache/` gesperrt – beachtet). Bedingte Requests (ETag/Last-Modified), `raw/<sha1(url)>.html|pdf` als Cache; Outputs werden immer deterministisch aus `raw/` neu gebaut (zweiter Lauf = byte-identisch). `--offline` = nur Neuaufbau, `--force` = alles neu laden. Voller Lauf ≈ 3 min.

## Grenzen / ehrliche Lücken
- `kurz_einfach` ist die **erste Absätze der Seite** (bzw. handgeschriebene Kurzfassung bei fsw_pflegeberatung, mobile_pflege_wien, kostenbeitrag_fsw, 24h-Verweis, Senior:innen-WG) – **keine** echte einfache Sprache; Review/Umformulierung nötig.
- Voraussetzungen sind oft nur „FSW-Kund:innenservice stellt den Bedarf fest“ – die FSW-Seiten nennen keine harten Kriterien (Pflegegeldstufe o. Ä.) für die meisten mobilen Dienste. Keine Ergänzung aus Fremdwissen. Zielgruppe-Felder sind kuratiert (Mensch reviewt).
- `unterlagen`/`fristen` leer (nur im 13-seitigen Antrag selbst; nicht ausgewertet). Kostenbeitrag-Beträge (z. B. 1.060,17 € Selbstbehalt-Grenze, Stand 2026) stehen als Zitat in documents (`ihr-kostenbeitrag-ab-2025`).
- Formularfeld-`label` = PDF-Tooltip (`/TU`), oft leer; `quelle_hint` nur heuristisch (Namens-Regex).
- `leistung_ids` bei Formularen manuell zugeordnet (Mapping in `ingest.py`), Behinderungs-/PGE-Formulare grob.
- Nicht erfasst: Partner-Anbieterlisten als strukturierte Stellen (nur als Dokumenttext), „Mitten in Wien“-Termine, Geo-Koordinaten (`geo:null`), Förderrichtlinien/Organisationsförderung (bewusst ausgeschlossen), Grundversorgung/Flüchtlinge nur Standort.
- 24-h-Betreuung: FSW hat **keine eigene** Seite; nur FAQ-Verweis auf Sozialministeriumservice (`foerderung_24h_betreuung_extern`, confidence niedrig).
- Pflegegeld selbst ist SV-Leistung (PVA/ÖGK/SVS/BVAEB), hier nur als `abhaengigkeiten:["pflegegeld"]` referenziert.
- Notfall: keine medizinischen Inhalte modelliert; Palliativ/Hospiz nur administrativ als Leistungsinfo.
- Lizenz: © FSW; Inhalte nur zitiert und verlinkt. `raw/` (≈46 MB) sollte in .gitignore.
