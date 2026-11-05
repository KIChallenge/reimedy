# Quelle `reimedy_kb`: reimedy Knowledge-DB (ICD-10-AT, SNOMED-Fachrichtungen, Payer, BASG)

Stand der Sichtung: 2026-11-05. Repo: <https://github.com/ArneNostitz/Reimedy_OnlineKnowledgeDB> (geklont nach `repo/`, nur gelesen).

## Verwendung (hart begrenzt)
Nur **administrativ**: Codes normalisieren, Dokumente strukturieren, Fachrichtung/Zuständigkeit finden, Leistungen *als Kandidaten* triggern. Codes werden **nie** gedeutet, nie für Risiko-/Therapieaussagen genutzt; Labels werden wörtlich angezeigt. `leistung_hints` sind grobe Hinweise auf Kandidaten, **keine Aussage über eine Person** und müssen im Lotsen immer zusammen mit „Hausarzt/1450“ und ohne Diagnosecharakter verwendet werden.

## Woher das Repo seine Daten bezieht
| Daten | Repo-Skript | Rohquelle | Zustand |
|---|---|---|---|
| ICD-10-AT | `scripts/etl-icd10-at.ts` | FHIR-URL `https://termgit.elga.gv.at/CodeSystem/icd-10-bmsgpk` | **URL liefert heute 404** (Server wurde auf TerminoloGit/HTML umgestellt, Versionen jetzt `icd-10-bmasgpk-2026`, `-2027`). Das Repo-Skript ist also kaputt und lädt außerdem in ein altes Vokabular (`ICD10GM`, VALID_START 2024). |
| BASG-Medikamente | `scripts/etl-basg-full.ts` (~18.700 Einträge) und `etl-basg.ts` | `POST medikamente.basg.gv.at/api/api/v1/medication/search` mit Bearer-Token, das aus dem JS-Bundle der Website gelesen wird; Browser-UA und `node:https` zur Umgehung eines WAF-Soft-Blocks | Siehe „BASG“ unten. `etl-basg.ts` ist nur ein kuratiertes Sample mit **Platzhalter-PZNs** (z. B. `1111111`), nicht verwendbar. |
| SNOMED-Fachrichtungen | `scripts/seed-provider-data.ts` (+ `seed-provider-hierarchy.ts`) | handkuratierte Liste im Code (61 Fachgebiete + 18 Anbietertypen, DE-Labels) | nutzbar, siehe Lücken |
| Payer | `scripts/seed-standard-info.ts` | handkuratiert: ÖGK, SVS, BVAEB, KFA + 17 Privatversicherer | nutzbar |
| ATC | `etl-link-atc.ts`, BASG-Feld `atcCode` | BASG | Teil der BASG-Daten |

Es gibt **keine Rohdaten-Dateien im Repo** (Seeds sind im Code, ICD/BASG kommen aus Live-Quellen; die Postgres-Instanz selbst ist nicht im Repo).

## Was `ingest.py` tut
`uv run knowledge/sources/reimedy_kb/ingest.py` (Python ≥ 3.11, nur Stdlib, idempotent):

* **ICD-10-AT**: lädt `https://termgit.elga.gv.at/CodeSystem-icd-10-bmasgpk-2026.html` (Herausgeber BMASGPK; Version `1.1.0+20260603`, Status active), parst die Codetabelle (Code, Display, `parent`) → 14.875 Codes inkl. Gruppen-/Kapitelhierarchie (21 Wurzeln, alle `parent`-Verweise lösen auf). 133 numerische LKF-Zusatzcodes (z. B. `101-199`, `901-999`, Endoprothetik-Revisionsgründe) werden **übersprungen**, da kein ICD. `stand` = Version der Quelle. Terminologieserver-`robots.txt` erlaubt `/CodeSystem-*`; 1 Request/s, UA `SV-Lotse-Hackathon/0.1`.
* **`leistung_hints`** (nur für ICD, bewusst grob): `C00–C97` und `D00–D09` → `["reha_onkologisch"]` (D10–D48 = gutartig/unsicher bewusst ohne Hint; Bereichscodes nur, wenn der ganze Bereich enthalten ist), `F` → `["psychosoziale_angebote"]` (478 Codes). Buchstabenübergreifende Gruppen (z. B. `C00-D48`) bekommen keinen Hint. Alle anderen Codes: `[]`.
  `psychosoziale_angebote` ist eine hier neu eingeführte `leistung_id`; bitte mit dem Leistungsgraphen abgleichen (Koordinator).
* **SNOMED-Fachrichtung**: 79 Einträge (Fachgebiete + Anbietertypen) aus `seed-provider-data.ts`, `label_de` = reimedy-Übersetzung, englischer SNOMED-Name steht in `stand`. `parent` ist `null`, weil die Hierarchie im Repo fehlerhaft ist (Top-Level-Codes in `seed-provider-hierarchy.ts` kollidieren mit echten Fachgebiets-Codes, z. B. `394601005` = „Clinical physiology“).
* **Payer** → `out/stellen.jsonl` (Schema C), `typ:"traeger"`: `traeger_oegk`, `traeger_svs`, `traeger_bvaeb`, `traeger_kfa` (nur Name und Haupt-URL; `kfa` ohne URL, da KFAs regional sind). Die 17 privaten Versicherer werden **nicht** übernommen (außerhalb der Sozialversicherung). Hinweis: Das BVAEB-Label stammt hier aus der amtlichen Bezeichnung, im Repo steht „Beamte & Öffentlicher Dienst“. Payer erscheinen nicht in `codes.jsonl`, weil `Payer` kein `system` im Schema E ist.
* **BASG**: siehe unten.
* `out/manifest.json`: `{source_id, fetched_at, n_docs:0, n_codes, n_stellen, stats, urls:[{url, sha256, etag, last_modified, status, version?}]}`. Zwischenspeicher: `raw/<sha1(url)>.html`. Ein Re-Run ohne Änderung erzeugt byte-identische `codes.jsonl`/`stellen.jsonl`; `fetched_at` ändert sich nur bei geändertem Inhalt.

Ergebnis: `out/codes.jsonl` 14.954 Zeilen (ICD-10-AT 14.875 + SNOMED-Fachrichtung 79), `out/stellen.jsonl` 4 Zeilen. Geprüft: keine doppelten (system, code), alle `parent` auflösbar.

## BASG: bewusst NICHT live ingestiert
Die Repo-Methode (Token aus dem Website-Bundle auslesen + WAF-Soft-Block mit Browser-Header umgehen) ist ein Umgehen von Zugriffsschutz. Ich habe sie **nicht** nachgebaut (der Versuch wurde zusätzlich vom Sicherheitsfilter der Umgebung blockiert), und die Website hat keine `robots.txt`, aber auch keine dokumentierte öffentliche API oder Open-Data-Lizenz. Ich habe auch keinen Open-Data-Download des Arzneispezialitätenregisters gefunden.

Stattdessen: `ingest.py --basg-file <export.json|csv>` liest einen Export (Felder `authNumber`/`zulassungsnummer`, `name`, `atcCode`/`atc`, `substances`/`wirkstoff`) und schreibt `system:"BASG"`, `code` = Zulassungsnummer, `label_de` = Name, `parent` = ATC-Code, zusätzlich das Zusatzfeld `wirkstoff` (kein Teil von Schema E; vom Loader ignorierbar). Der Pfad ist mit einer synthetischen Datei getestet, die echte Daten liegen nicht vor.
**Empfohlener Weg:** Arne (Eigentümer der reimedy-DB) exportiert aus seiner Postgres: `SELECT concept_code AS authNumber, concept_name AS name, atc_code AS atcCode, active_ingredient AS wirkstoff FROM concept WHERE vocabulary_id='BASG' AND valid_end_date IS NULL` und legt die Datei ab, danach `ingest.py --basg-file …`. Für den Lotsen reicht BASG nur für Medikamentennamen-Normalisierung (z. B. Scan → Bewilligungspflicht/Erstattung); es ist für die Abgabe nicht kritisch.

## Lizenz und Nutzungsbedingungen (Stand der Prüfung, keine Rechtsberatung)
* **ICD-10 BMASGPK** (Terminologieserver ELGA GmbH / TerminoloGit): öffentlich und kostenfrei abrufbar; Herausgeber BMASGPK, basiert auf ICD-10-GM (BfArM, übersetzte WHO-ICD-10). Auf der Codesystem-Seite steht **kein ausdrücklicher Lizenztext**. Die Daten sind amtliche, öffentlich bereitgestellte Verzeichnisse; **Quelle nennen** („ICD-10 BMASGPK 2026+, BMASGPK, via termgit.elga.gv.at“). Für ein Produktivsystem bitte rückfragen bzw. BfArM-Bedingungen für ICD-10-GM prüfen.
* **ATC (WIdO)** (nur mit `--with-atc`, **standardmäßig AUS**): WIdO erteilt BASG/AGES eine unentgeltliche Nutzungsgenehmigung **zur Unterstützung von ELGA**; auf dem Server steht ausdrücklich: Nutzung für andere Zwecke, insbesondere kommerziell, ist untersagt, ebenso Änderungen. Deshalb nicht in die Standard-Ausgabe aufgenommen. ATC-Codes aus BASG-Exporten sind separat zu bewerten.
* **SNOMED CT**: Österreich ist Mitgliedsland von SNOMED International, die hier verwendeten ~80 Konzept-IDs mit **eigener deutscher Beschriftung durch reimedy** werden ohne SNOMED-Originaltexte weitergegeben (englischer Begriff nur im Feld `stand`). Für Hackathon-Prototyp unkritisch; für Produktivbetrieb Lizenzstatus (nationale Lizenz) prüfen.
* **BASG-Daten**: Arzneimittelregister einer Bundesbehörde; Nutzungsbedingungen nicht eindeutig geklärt, siehe oben. Nur Name, Zulassungsnr., ATC, Wirkstoff (administrativ). Keine Fachinformationen/Beipackzettel.
* **Repo-Code selbst**: im Repo keine LICENSE-Datei; der Code gehört dem User (Arne Nostitz). Wiederverwendung im Lotsen daher unproblematisch.

## Update-Strategie
* Neue ICD-Version: Jahres-/Folgeversionen erscheinen als neues Codesystem `icd-10-bmasgpk-<Jahr>` (2027+ ist bereits veröffentlicht, Version `1.0.0+20261030`, gültig ab 01.01.2027). Nachziehen: `ingest.py --icd-year 2027`. Neue Page-IDs in `ICD_PAGES` ergänzen. Der Terminologieserver ändert auch Unterversionen (z. B. `1.1.0+20260603`); `ingest.py` nutzt ETag/If-Modified-Since und sha256, ein Lauf ohne Änderung bleibt byte-identisch. Wichtig: Es sollte pro `system` nur **eine** Jahresversion in die DB, sonst kollidieren (system, code); ggf. vorher die alte aus der DB löschen. Prüfen, dass `Status` `Active` ist (steht in `manifest.stats`).
* Parser-Bruch: Das Skript bricht laut ab, wenn die Tabelle fehlt („Seitenformat geändert?“). Der Zwischenspeicher `raw/` erlaubt `--offline`.
* BASG: monatliche Aktualisierung der Quelle; neuer Export aus der reimedy-DB → `--basg-file`. Zurückgezogene Präparate fehlen im Export (kein Soft-Delete in der Ausgabe).
* SNOMED/Payer: ändern sich nur mit `repo/` (`git -C repo pull`, dann `ingest.py`).

## Lücken / ehrliche Einschränkungen
* **Keine BASG-Daten** in `out/` (siehe oben). Das Repo-Sample hat Platzhalter-PZNs.
* **SNOMED-Fachrichtungen unvollständig**: Es fehlen u. a. Chirurgie, Psychiatrie, Augenheilkunde, HNO, Urologie, Gynäkologie, Orthopädie, Radiologie. Das Hierarchiefile referenziert sie, aber der Seed enthält sie nicht. Für Fachrichtungs-Zuständigkeit besser Ärztekammer-Fachgebiete (Quelle `aek_wien`) als Hauptliste verwenden. Außerdem einzelne fragwürdige Übersetzungen (z. B. „Respite care“ → „Kurzzeitpflege“). Labels sind von reimedy, nicht amtlich.
* Keine Synonyme, Altersgrenzen, Meldepflicht-Kennzeichen und kein LKF-Mapping aus der ICD-Tabelle übernommen (absichtlich: Diagnosecharakter). Die Quelle enthält sie als Spalten, falls später benötigt.
* `label_einfach` ist überall `null` (keine einfache Sprache vorhanden).
* Payer: nur Name und URL, keine Kontaktdaten. Die Verknüpfung `zustaendig_fuer` ist leer.
* ICD-Hinweise sind absichtlich minimal (nur C00–C97, D00–D09 und F). Ob z. B. „Reha nach Herz-Kreislauf“ als Kandidat getriggert wird, bleibt Aufgabe des Leistungsgraphen mit Quellenzitat.

## Was der Lotse aus dem reimedy-KB-Code direkt wiederverwenden kann
Alles TypeScript (Hono, Drizzle, Postgres); der Lotse ist voraussichtlich Python, deshalb sind das Portierungsvorlagen:
* **`src/routes/scan.ts`: Foto → striktes JSON** (Gemini Vision, Prompt „Return ONLY valid JSON“ mit festem Schlüsselsatz, `null` bei Unsicherheit, tolerantes Extrahieren des JSON-Blocks per Regex). Direkt übertragbar auf **Dokumenten-Scan** (Bescheid, Überweisung, Formular → Felder `traeger`, `datum`, `aktenzeichen`, `leistung`…), dann Abgleich mit der DB. Verbesserungsvorschläge: `responseSchema`/`responseMimeType: application/json` statt Regex, nur nicht-medizinische Felder extrahieren, **keine** Interpretation der Befundinhalte, Modell `gemini-2.0-flash-exp` ist veraltet.
* **`src/lib/fuzzySearch.ts`** (96 Zeilen, rein funktional): tokenisierte, gewichtete Fuzzy-Suche für verrauschte OCR-Zeilen (Wirkstoff/Marke/Stärke). Als Matching-Schicht für Medikamentennamen und, leicht angepasst, für Leistungs-/Stellennamen nutzbar.
* **`src/routes/concept.ts`**: `POST /resolve` (stabiler natürlicher Schlüssel `(vocabulary_id, concept_code)` statt serieller ID, inklusive Rückgabe „fehlt/zurückgezogen“) ist ein gutes Muster für das Wieder-Auflösen gespeicherter Referenzen. `GET /concepts/search` mit Domänenfilter als Vorlage für die Such-API.
* **`src/lib/parseDrugName.ts`** (Stärke/Darreichungsform aus BASG-Namen): nur falls Medikamentenpackungen gescannt werden.
* **Datenmodell** (OMOP-artig: `concept`, `concept_synonym`, `concept_relationship` 'Is a'): zu schwergewichtig; für den Lotsen reicht das flache Schema E in SQLite/FTS5.
* Nicht übernehmen: `etl-basg-full.ts` (Token-/WAF-Umgehung), `etl-icd10-at.ts` (kaputte URL, siehe oben), `etl-interactions.ts`/`etl-rxnorm.ts` (Wechselwirkungen = medizinischer Inhalt, außerhalb der Produktgrenze).
