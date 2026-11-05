# Abgleich Wissensbasis ↔ reimedy Knowledge-Server

Stand: 05.11.2026, ~23:00. Der Server https://reimedy-server.mynu.me wurde **nur lesend** abgefragt (GET `/api/concepts/search`, GET `/api/concepts/domain/<d>/tree`). Auf den Server wurde **nichts geschrieben**; ob und was dort geändert wird, entscheidet Arne.

## 1. Was der Server hat (OMOP-artiges Concept-Modell)

| Domain | Anzahl | Klassen / Vokabulare | Bemerkung |
|---|---|---|---|
| Payer | 21 | `Austrian_Payer`: ÖGK 2000000001, SVS 2000000002, BVAEB 2000000003, KFA 2000000004 + 17 Privatversicherer (2000100001–017) | nur Namen, keine Landesstellen/Kontakte; **PVA, AUVA, Dachverband fehlen** |
| Provider | 72 im Baum (80 über Suche) | `SNOMED`: 54 Specialty + 18 Provider Type | deckungsgleich mit unserer Kopie (s. u.) |
| Drug | 19.432 | `BASG`: 14.987 Prescription + 4.232 OTC; `RxNorm`: 198 Ingredient + 15 Clinical Drug | `atc_code` in Stichprobe (1.000 BASG-Treffer) **immer leer** |
| Condition | 27 | `SNOMED` | ⚠ `concept_code` = `concept_id` (z. B. Hypertension 320128, eine OMOP-ID), **nicht** der SNOMED-Code → Datenfehler (zu prüfen) |
| Observation / Measurement | 27 / 10 | – | nicht relevant für den Lotsen |
| ICD-10 | **0** | – | ETL kaputt (FHIR-URL 404), siehe `SOURCE.md` |

## 2. Überschneidungen mit der Wissensbasis

| Datenart | Wissensbasis heute | Server | Überschneidung | Vorschlag Owner | Referenz der anderen Seite |
|---|---|---|---|---|---|
| **SNOMED-Fachrichtungen** | `codes` system=`SNOMED-Fachrichtung`, 79 Einträge (Kopie aus dem Repo-Seed) | 80 (Provider) | **79/79 identisch**, Server hat zusätzlich „Surgical specialty“ 394649002 | **reimedy-Server** (pflegt DE-Labels und Hierarchie) | Wissensbasis speichert nur `(vocabulary_id='SNOMED', concept_code)` + Label-Cache mit `stand`; Abgleich im Ingest statt Kopie im Code |
| **Payer / Träger** | **Träger-Register** `traeger` + `traeger_stellen` (`GET /traeger`): 9 Träger, ÖGK/PVA/SVS je 9 Landesstellen mit Adresse/Telefon/E-Mail (offizielle Kontaktseiten), BVAEB/SMS/FSW aus unserem Ingest, Zuständigkeitsregel je Träger | 4 SV-Payer + 17 private, nur Namen | ÖGK, SVS, BVAEB, KFA | **Wissensbasis** für SV-Träger-Struktur, Landesstellen, Kontakte, Zuständigkeit; **Server** für die Concept-ID (Payer-Identität, auch Privatversicherer) | Wissensbasis führt `reimedy_ref = {vocabulary_id:'Austrian_Payer', concept_code}` je Träger (ÖGK/SVS/BVAEB/KFA gesetzt). Server könnte PVA/AUVA/Dachverband als Payer-Konzepte ergänzen und für Adressen auf `GET /traeger/<id>` verweisen. |
| **ATC** | `codes` system=`ATC`, 6.611 (aus dem EKO der SV-Box) | `atc_code` am BASG-Drug, in Stichprobe leer | praktisch keine (Server hat keine ATC-Werte) | **Wissensbasis** (EKO/WIdO, Lizenzhinweis in `SOURCE.md`) | Server verknüpft BASG-Drugs über `(vocabulary_id='ATC', concept_code)`; Wissensbasis liefert die Liste |
| **BASG** | **nichts** (bewusst kein Token-/WAF-Umgehen) | 19.219 BASG-Concepts | – | **reimedy-Server** | Wissensbasis referenziert `(vocabulary_id='BASG', concept_code=Zulassungsnr.)`; Lookup live per `GET /api/concepts/search?domain=Drug` oder Export-Datei → `ingest.py --basg-file` |
| **EKO (Erstattung/Bewilligung)** | `codes` system=`EKO`, 6.985 (Box, Bewilligung, Regeltext wörtlich) | nicht vorhanden | – | **Wissensbasis** (nur administrativ) | Server kann je BASG-Drug auf `(EKO, Pharmanummer)` verweisen |
| **ICD-10-AT** | `codes` system=`ICD-10-AT`, 14.875 (TerminoloGit BMASGPK 2026) | 0 (ETL kaputt) | – | **Wissensbasis** (bis die Server-ETL repariert ist) | Server kann `(ICD-10-AT, code)` aus `GET /code/ICD-10-AT/<code>` beziehen |
| SNOMED-Conditions | – (bewusst keine Diagnosen) | 27 | – | Server | nicht übernehmen (Diagnosecharakter, außerhalb der Produktgrenze) |

## 3. Regel gegen Doppelpflege
1. **Ein Owner je Datenart** (Spalte oben). Die andere Seite speichert nur den natürlichen Schlüssel `(vocabulary_id, concept_code)` plus optional einen Label-Cache mit `stand`.
2. **Kein serieller `concept_id` als Fremdschlüssel** über Systemgrenzen – nur `(vocabulary_id, concept_code)` (wie `POST /resolve` im Server-Code).
3. Abweichungen erkennt der Build (`update.py`) als Review-Eintrag, nicht als stilles Überschreiben.

## 4. Gefundene Datenfehler / offene Punkte am Server (nur gemeldet, nicht geändert)
- **SNOMED-Condition-Codes**: `concept_code` enthält dieselbe Zahl wie `concept_id` (z. B. 320128, eine OMOP-ID) statt des SNOMED-Codes – bitte prüfen.
- **BASG ohne ATC**: Feld `atc_code` leer → ATC-Verknüpfung aus der Wissensbasis (EKO) möglich.
- **ICD**: ETL gegen nicht mehr existente FHIR-URL; die Wissensbasis-Ingest-Logik (`ingest.py`, TerminoloGit-HTML) kann als Vorlage dienen.
- **Payer**: PVA, AUVA, Dachverband fehlen als Konzepte; KFA ist ein Sammelkonzept für ~15 regionale Anstalten.

## 5. Entscheidungen für Arne (Empfehlung)
1. Owner-Aufteilung wie in §2 übernehmen. **Empfehlung: ja.**
2. BASG-Export aus der reimedy-DB als Datei bereitstellen (`ingest.py --basg-file`). **Empfehlung: ja**, statt Live-Kopplung im Hackathon.
3. Server-Korrekturen (§4) erst nach dem Hackathon. **Empfehlung: ja**, nichts unter Zeitdruck in der Produktiv-DB ändern.
