# reimedy · SV-Wissensbasis

Die Wissensbasis hinter dem **SV KI-Lotsen** (Team reimedy, SV KI-Challenge 2026, Use Case 1). Sie enthält Leistungen, Voraussetzungen, Zuständigkeiten, Formulare mit geprüften Live-Links, Stellen und Einrichtungen sowie Rechtsgrundlagen. Alles ist mit Quelle und Stand-Datum belegt und wird als HTTP-Service angeboten.

> Die Lotse-Anwendung (App, Gespräch, Vaults, ELGA) liegt in einem separaten Repository und ruft diesen Service per HTTP auf. Personendaten (ELGA, Befunde, Uploads) sind **nicht** Teil der Wissensbasis.

## Inhalt

| Quelle (`knowledge/sources/<id>`) | Was |
|---|---|
| `oegk`, `svs`, `bvaeb`, `pva` | Leistungen, Formulare und Kundenservice der Träger |
| `aek_wien` | Kassen-Seiten der Ärztekammer Wien |
| `fsw` | Fonds Soziales Wien: Pflege, Betreuung, Förderanträge |
| `sozialministeriumservice` | Behindertenpass, 24-h-Betreuung, Unterstützungsfonds |
| `gesundheit_gv` | gesundheit.gv.at und pflege.gv.at: Vorsorge, Impfplan, System-Navigation |
| `oesterreich_gv` | oesterreich.gv.at: Lebenslagen Gesundheit, Soziales, Familie, Pension |
| `sozdok_ris` | 14.244 SozDok-Paragrafen (SV-Box) plus Abgleich mit der RIS OGD API |
| `svbox_local` | SV-Box: ÖGK-Leistungsbroschüre 2026, Honorarordnungen, Erstattungskodex (nur administrativ), Formulare |
| `reimedy_kb` | reimedy Knowledge-DB: ICD-10-AT, SNOMED-Fachrichtungen, Träger (nur administrativ, keine Deutung) |
| `wien_ogd` | Stadt Wien OGD: Ärzt:innen, Apotheken, PVE, Spitäler und Pflegehäuser mit Koordinaten (CC BY 4.0) |

Datenformat: [`knowledge/CONTRACT.md`](knowledge/CONTRACT.md). Architektur und Technologie-Entscheidungen: [`knowledge/ARCHITEKTUR.md`](knowledge/ARCHITEKTUR.md). Die SV-Box-Originale liegen unter `_Source/`.

## Technik

- **SQLite** als eine Datei, im Betrieb nur lesend. Die Suche kombiniert **FTS5** (bm25) und **sqlite-vec** mit dem lokalen Modell `minishlab/potion-multilingual-128M` per RRF zu einer Hybrid-Suche. Gesucht wird auf Deutsch; der Lotse übersetzt andere Sprachen vorher.
- **Leistungsgraph:** Leistungen, Abhängigkeiten (`setzt_voraus` …) und Claims mit Quelle und Stand. Zuerst wird der Graph befragt, die Volltextsuche dient als Fallback.
- **Live-Links:** Jede ausgelieferte URL ist geprüft (`geprueft_am`). Formular-PDFs sind versioniert (sha256, AcroForm-Felder).
- **Updates:** `ingest.py` läuft je Quelle inkrementell (ETag, Last-Modified, sha256). Danach folgen Build, Linkcheck und Qualitäts-Gates, zuletzt wird die DB atomar getauscht.

## Nutzung

```bash
uv sync
uv run python knowledge/build/build_db.py            # DB bauen (~15 s)
uv run pytest -q knowledge/build/test_build.py        # Tests
uv run python knowledge/build/search.py --serve       # HTTP-API auf :8765
uv run python knowledge/build/update.py               # Ingest → Build → Linkcheck → Gates → Swap
```

API: `GET /health` · `GET /search?q=` · `GET /leistung/<id>` · `GET /stellen?plz=&typ=&leistung_id=` · `GET /formular/<id>` · `POST /triggers` · `GET /codes/...` · `POST /codes/hints` · `GET /traeger?plz=&bundesland=` (Träger-Register mit Landesstellen + zuständiger Stelle) · `GET /traeger/<id>` · `GET /impfplan?krankheit=&alter=` (Intervalle laut Österreichischem Impfplan, mit Version + Zitat)

Docker: `docker build -t sv-knowledgebase . && docker run -p 8765:8765 sv-knowledgebase`

**Betrieb im Container (Volume, nächtliches Update ohne Redeploy):**

| Env | Default | Zweck |
|---|---|---|
| `DB_PATH` | `knowledge/build/lotse.sqlite` | Live-DB, im Container auf dem Volume, z. B. `/data/lotse.sqlite` |
| `STATE_DIR` | Ordner von `DB_PATH` | snapshot, build_report, changes/, review_queue, misses, logs (überleben Redeploys) |
| `HOST` / `PORT` | `127.0.0.1` / `8765` | HTTP-Service |

- Beim Start übernimmt `search.py --serve` die im Image gebaute DB ins Volume, wenn das Volume leer oder älter ist (`meta.built_at`). Ein neuerer nächtlicher Stand bleibt erhalten.
- Nachts (Coolify Scheduled Task): `DB_PATH=/data/lotse.sqlite python knowledge/build/update.py`. Der Lauf baut `/data/lotse.sqlite.new`, prüft die Gates und tauscht atomar. Die laufende API lädt beim nächsten Request neu (mtime).
- `/health` gibt keine absoluten lokalen Pfade aus.

## Formulare

Einen Teil der Formulare haben wir aufbereitet: die Demo-Formulare und weitere, insgesamt 138 von 350. Dafür gibt es ein geprüftes Template mit Feldern, Bedeutung und Empfänger (`knowledge/build/forms/`, Details in `REPORT.md`). Für alle anderen Formulare versucht der Lotse das Ausfüllen **live**, sobald eines angefordert wird: Er erkennt die Felder per LLM aus dem Original-PDF, markiert alle Angaben zur Prüfung und kennzeichnet sie klar als „nicht vorab geprüft“.

## Grenzen

Kein Medizinprodukt. Die Wissensbasis enthält keine Diagnose-, Befund-, Risiko- oder Therapieaussagen. ICD-, ATC- und EKO-Daten dienen nur der administrativen Zuordnung. Leistungsangaben sind Kandidaten mit Quelle; über einen Anspruch entscheidet der zuständige Träger.

**Rechte:** Die Texte von gesundheit.gv.at stehen unter „alle Rechte vorbehalten“. Sie werden nur als zitierbare Quelle mit Link genutzt, und nur in diesem privaten Hackathon-Repository. Lizenzhinweise je Quelle stehen in `knowledge/sources/*/SOURCE.md`.
