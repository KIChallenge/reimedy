# Wissens-DB: Zielarchitektur (verbindlich, Stand 05.11.2026 ~21:00)

Diese Datei gehört dem Koordinator. Umsetzung: Session „knowledge-db" (`knowledge/build/`) und die Ingest-Sessions (`knowledge/sources/<id>/`). Grundlagen sind `CONTRACT.md` (Datenformat) und `PLAN.md` (v2, freigegeben): Server B0 bis B9 importiert `knowledge/build/search.py` direkt, und das Deploy (B8) baut `lotse.sqlite` im Docker-Image.

## 1. Technologie-Entscheidung (geprüft)

| Baustein | Wahl | Warum (und warum nicht die Alternative) |
|---|---|---|
| Speicher | **eine SQLite-Datei** (`lotse.sqlite`), zur Laufzeit nur gelesen, beim Update atomar ausgetauscht | Der Server ist ein Python-Prozess (FastAPI), das Deploy ein einzelnes Docker-Image. Wir brauchen keinen DB-Dienst, haben null Betriebsaufwand, die Datei ist reproduzierbar aus `out/*.jsonl` und lokal wie in der Cloud identisch. ~30.000 Abschnitte sind für SQLite klein. *Postgres + pgvector* (wie die reimedy-KB) wäre Overkill und ein weiterer Coolify-Dienst. Für das Produkt kann derselbe Vertrag 1:1 in Postgres geladen werden. |
| Volltext | **FTS5** mit Umlaut- und ß-Normalisierung, Präfix, bm25 | Funktioniert, getestet: Bei „Pflegegeld beantragen", „Taxi zur Bestrahlung" und „Zahnspange Kind" ist der passende Treffer unter den ersten zwei. |
| Semantik | **sqlite-vec** (v0.1.9, mit uv-Python 3.12 geprüft) + **lokales Embedding über fastembed/ONNX**, Hybrid über **RRF** (bm25 + Vektor) | Fremdsprachen sind **kein** Grund: Das LLM übersetzt vorher ins Deutsche. Der Grund ist die **Wortlücke im Deutschen** zwischen Alltagssprache und Amtssprache („Taxi zur Bestrahlung" → Krankentransport, „packt's nimma" → Pflegegeld). Embeddings sind das **Sicherheitsnetz**, wenn die LLM-Umschreibung einen Fachbegriff verfehlt, und sorgen für Recall im RAG-Fallback über ~30.000 Abschnitte, ohne zusätzlichen LLM-Call. Wir haben nur ein Azure-Deployment (`gpt-5-4-mini`) und keinen Embedding-Endpunkt. Das lokale Modell funktioniert offline, kostet nichts und hängt nicht vom Key ab. |
| Embedding-Cache | `knowledge/build/emb_cache/<modell>.npz`, Schlüssel = sha256 des Abschnitts, int8-quantisiert (~12 MB), **im Repo** | Nur neue oder geänderte Abschnitte werden neu eingebettet. Das Docker-Build (B8) muss nicht 30.000 Abschnitte auf der Server-CPU rechnen. |
| Graph | Tabellen `leistungen`, `kanten` (setzt_voraus = harte Voraussetzung nur aus dem kuratierten Seed; verwandt = ungerichtet aus Quellen; alternative_zu, teil_von, nicht_verwechseln_mit), `claims` (jede Aussage + Quelle + Stand) | „Code entscheidet": Reihenfolge und Abhängigkeiten sind deterministisch. Der Graph kommt zuerst, RAG ist der Fallback, Fehlschläge landen in `misses.jsonl` als Kuratierungs-Kandidaten. |
| **Embedding-Modell (entschieden)** | **`minishlab/potion-multilingual-128M`** (statische Embeddings, über fastembed, ohne Transformer-Inferenz, CPU-schnell) | Benchmark am 05.11. mit 144 Leistungen und 7 umgangssprachlichen Fragen, Treffer unter den Top 5: **potion 7/7**, mpnet-base 5/7, MiniLM-L12 4/7. Nur potion findet „Mama packt's nimma allein daham" → pflegegeld und „Medikamente zu teuer" → rezeptgebuehrenbefreiung. Fallback falls nötig: mpnet-base (langsamer). Golden Queries (§6) wiederholen den Test bei jedem Build. |
| Abfrage-Umschreibung | System 1 schreibt die Nutzerfrage **vor** `search()` in 2–3 Fachbegriffe plus Original um und sucht hybrid über beides | billig, transparent, im Log nachvollziehbar |
| Daten-Ownership (Entscheidung Arne, 06.11.) | **SV-Wissensbasis ist Owner** für ICD-10-AT, SV-Träger-Register und Fachrichtungen (SNOMED); reimedy-Server Owner für BASG; Payer-Concept-IDs nur referenziert (`reimedy_ref`). Referenz über `(vocabulary_id, concept_code)`, nie kopieren. Der reimedy-Server wird heute nicht beschrieben. | Details `sources/reimedy_kb/ABGLEICH.md` |

## 2. Was NICHT in die Wissens-DB gehört
- **Personendaten**, also ELGA-Befunde, e-Medikation, Termine und Uploads. Sie gehören in den Vault der Person (`server/elga`, B6; Vault-Modell 07). `knowledge/sources/elga/` bleibt **nur** als Fixture-Ordner für B3 und B6 und ist **keine** Wissensquelle. Der Build überspringt ihn ausdrücklich.
- Rohdaten (`sources/*/raw/`, ~280 MB). Sie gehören **nicht ins Git**. Nur `out/`, `ingest.py`, `SOURCE.md`, `manifest.json` und der Embedding-Cache werden committet.

## 3. Live-Links (Vorgabe des Users: „alle Verlinkungen auf Dateien zum Download, Anträge, Formulare etc. sollten live sein")
Neue Tabelle `links`, gefüllt von `knowledge/build/linkcheck.py`:
```
links(url PK, kind[formular_pdf|online_antrag|seite|stelle|quelle], final_url, http_status, content_type,
      bytes, sha256, checked_at, last_ok_at, fail_count, first_seen, ersetzt_durch)
```
Regeln:
1. **Jede URL**, die die API ausliefert (`formular.url_pdf`, `antrag.online_url`, `stelle.url`, `quelle_url`, `documents.url`), wird geprüft: HEAD, bei 403/405 ein GET mit Range. Redirects werden aufgelöst, **gespeichert wird `final_url`**.
2. Die API liefert **nur Links mit `last_ok_at` < 7 Tage**. Tote Links werden ersetzt: (a) gleiche Datei unter neuer URL über den sha256 bzw. die Elternseite neu crawlen, sonst (b) die **Elternseite** der Quelle mit Hinweis „Formular dort herunterladen", sonst (c) ausgeblendet und in der Review-Queue gemeldet. Jeder Link trägt `geprueft_am`.
3. **Formular-PDFs** werden live geladen, gehasht und auf AcroForm-Felder geparst. Hat sich der sha256 geändert, ist das eine neue Formularversion: Feldliste neu, Diff gegen das Feld-Mapping von B5, Eintrag in der Review-Queue. Die Kopien in `_Source/` sind **nur Fallback**, mit Stand-Hinweis. Kanonisch ist die Live-URL des Trägers.
4. **Dedupe der Formulare** über `final_url` und sha256. Dasselbe PDF, das von aekwien.at und svs.at verlinkt wird, ergibt **ein** Formular mit mehreren `gefunden_auf`. Die kanonische ID ist die Seed-ID, sonst die Träger-ID.
5. Rhythmus: Link-Check **täglich**, Formular-Hash **wöchentlich**, Quellen-Ingest **wöchentlich** (Recht: RIS-Delta täglich).

## 4. Kanonische Leistungen (Taxonomie)
- `aliases.json` wird zu einer **kuratierten Taxonomie** `taxonomie.json` mit `{id, name, typ: sv|land|bund|verein, traeger, eltern, nicht_verwechseln_mit}`.
- Fachliche Trennungen bleiben erhalten. Beispiel: **medizinische Hauskrankenpflege (ÖGK, ärztlich verordnet) ≠ mobile Pflege bzw. Heimhilfe (FSW)**. Der aktuelle Alias `hauskrankenpflege → mobile_pflege_fsw` ist fachlich falsch. Ebenso `rezeptgebuehrenobergrenze` ≠ `rezeptgebuehrenbefreiung` (verwandt, `teil_von`), `rehabilitationsgeld` ≠ `rehabilitation`.
- Träger-Varianten (`unterstuetzungsfonds_bvaeb`) werden **eine Leistung mit Träger-Ausprägungen**, nicht n Leistungen.

## 5. Abdeckung: was noch fehlt (nichts vergessen)
| Lücke | Warum kritisch | Neue Quelle |
|---|---|---|
| **PVA** (pv.at) | zuständig für **Pflegegeld** (PAL080) und **Reha** der ASVG-Pensionist:innen, also Annas Hauptpfad | `pva` |
| **Einrichtungen mit Koordinaten in Wien**: Ärzt:innen, Apotheken, PVE, Spitalsambulanzen (data.gv.at OGD, CC BY) | „geeignete Einrichtungen finden / in meiner Region" | `wien_ogd` |
| **Sozialministeriumservice** (Behindertenpass, Förderung 24-h-Betreuung, Unterstützungsfonds) | Bereich E | `sozialministeriumservice` |
| Bewegt im Park, Rauchfrei-Telefon, Gesundheitskurse (Termine/Orte) | Gesundheitsförderung, Szenario D | in `oegk` bzw. `gesundheit_gv` vertiefen |
| Leistungen mit `confidence` niedrig/mittel: Pflegegeld, Pflegekarenz, Sozialhilfe Wien, Gesundheitshunderter, Vollmacht | Kernpfade der Demo | Review mit wörtlichen Zitaten (Review-Queue) |

## 6. Qualitäts-Gates (Build schlägt fehl, wenn …)
- ein Schema-Fehler auftritt oder eine Quelle ohne `SOURCE.md` bzw. `manifest.json` ist (aktuell: aek_wien, bvaeb, fsw, oesterreich_gv);
- die **Golden Queries** nicht treffen: „Mama packt's nicht mehr allein" → pflegegeld/mobile Pflege in den Top 5; „Taxi zur Bestrahlung" → krankentransport/fahrtkostenzuschuss; „Zahnspange Kind" → zahnspange_kfo; „mehr bewegen" → bewegt_im_park. **Nur Deutsch:** Fremdsprachen übersetzt das LLM vor der Suche ins Deutsche, die Suche selbst ist einsprachig;
- die Live-Link-Quote der Formulare, die die Demo nutzt, unter **100 %** liegt (alle anderen ≥ 95 %);
- eine Leistung ohne Quelle oder ein ICD-`leistung_hint` außerhalb der Policy (C00–C97, D00–D09) existiert.

## 7. Update-Lauf (eine Pipeline)
`uv run knowledge/build/update.py [--sources …] [--links-only]`
1. `sources/*/ingest.py --since manifest` (inkrementell) →
2. `build_db.py` (Validierung, Taxonomie-Merge, Embeddings aus dem Cache plus Delta, FTS, Graph) →
3. `linkcheck.py` →
4. Gates →
5. `lotse.sqlite.new` → atomar `mv` →
6. Änderungsbericht `changes/<datum>.md` und Review-Queue.

Scheduling: Coolify Scheduled Task (B8) nachts; lokal per Hand. Demo-Story: „Stand der Daten: heute 04:00, 1.234 Links geprüft, 3 Formulare geändert."

## 8. Formulare: alle ausfüllbar, als PDF speicherbar, an die richtige Stelle versendbar (Vorgabe Arne, 05.11. abends)

Stand der Messung: Der Lotse zeigt 349 Formulare (antrag/beilage/merkblatt). Davon haben **77 AcroForm-Felder** und **272 sind flache Druck-PDFs**. Von den 6.747 AcroForm-Feldern haben nur 2.953 ein Label. In Michi (Branch `b5-comms`) sind erst 4 Formulare von Hand gemappt.

**Prinzip:** Ausfüllen ist **datengetrieben**, nicht pro Formular programmiert. Die Wissensbasis liefert für jedes Formular ein geprüftes **Template**, Michi füllt generisch.

### 8.1 Wissensbasis (dieses Repo) liefert
1. **Feld-Ontologie** `knowledge/build/forms/ontologie.json`: kanonische Schlüssel, z. B. `person.vorname`, `person.familienname`, `person.svnr`, `person.geburtsdatum`, `person.geschlecht`, `person.staatsbuergerschaft`, `person.familienstand`, `adresse.strasse|hausnr|stiege|tuer|plz|ort|land`, `kontakt.telefon|email`, `versicherung.traeger`, `versicherte_person.*` (bei Mitversicherung), `vertreter.*` + `vertreter.rolle` (Vollmacht/Erwachsenenvertretung), `bank.iban|bic|kontoinhaber`, `pension.bezieht|traeger`, `pflegegeld.bezieht|stufe|traeger`, `arbeitgeber.*`, `aufenthalt.temporaer.*`, `datum.heute`, `ort.heute`, `unterschrift.*`, `arzt.*` (wird nie von Michi gefüllt). Das ist der **Vertrag mit Michi** und wird nur additiv geändert.
2. **Template je Formular und Version** `knowledge/build/forms/templates/<formular_id>@<sha256[:12]>.json`:
   `{formular_id, sha256, pages, quelle: acroform|generiert, felder:[{feld_id, acro_name|null, page, bbox[x0,y0,x1,y1] (PDF-Punkte), typ: text|checkbox|radio|datum|zahl|unterschrift, label_wörtlich, semantik: <ontologie-key>|null, wer: versicherte|arzt|behoerde|unterschrift, pflicht: bool, max_zeichen, format (z. B. TTMMJJJJ, Kästchen pro Zeichen)}], geprueft: {methode, am}}`
   - AcroForm: Widgets plus bbox aus dem PDF, Label aus dem nächstliegenden Text. `semantik` per Regeln, sonst per LLM-Zuordnung (offline, Ergebnis eingefroren).
   - Flache PDFs: Ausfüllbereiche erkennen (Linien, Unterstriche, Kästchen, Tabellenzellen über pymupdf/pdfplumber-Geometrie plus Label-Text). Bei reinen Bild-PDFs zuerst OCR (Vision). Danach erzeugen wir zusätzlich eine **AcroForm-angereicherte Kopie**, damit auch die Nutzer:in ein ausfüllbares PDF bekommt.
   - **Prüfung:** Jedes Template wird mit einer Testperson probegefüllt, gerendert und visuell geprüft (Vision-Check: Text in der richtigen Box, nichts überlappt). Nur geprüfte Templates gibt die API aus (`geprueft`).
   - Ändert sich die Formularversion (sha256 aus §3.3), wird das Template neu erzeugt und kommt in die Review-Queue.
3. **Empfänger je Formular** `knowledge/build/forms/empfaenger.jsonl`: `{formular_id, traeger, abteilung, kanal: [online|email|post|fax|persoenlich], aufloesung: "landesstelle_nach_plz"|"fix"|"auszahlende_stelle", stelle_ids[], online_url, email, post_adresse, hinweis}`. Die Zuständigkeitsregel ist deterministisch, z. B. Pflegegeld → auszahlende Pensionsstelle, ÖGK → Landesstelle nach Wohnort, FSW nur Wien.
4. **Träger-Register** (alle SV-Träger mit Landesstellen, Kontakten und Zuständigkeiten: ÖGK + 9 Landesstellen, SVS, BVAEB, PVA, AUVA, KFAs, Dachverband) als Tabelle `traeger`, Endpunkt `GET /traeger`.
5. API (additiv): `GET /formular/<id>/template`, `GET /formular/<id>/pdf` (Live-PDF bzw. AcroForm-angereicherte Kopie, Cache nach sha256), `GET /formular/<id>/empfaenger?plz=&traeger=`, `GET /forms/ontologie`, `GET /traeger`.

### 8.2 Michi (Repo reimedy-svhack) macht
- **Generischer Filler:** AcroForm-Felder setzen, flache PDFs per Overlay in die bbox schreiben (pymupdf `insert_textbox`, Kästchenformat beachten). Ampel je Feld: grün = aus Quelle (Dokument/Vault), gelb = bitte prüfen, rot = nur die Person selbst (Unterschrift, Einkommen, IBAN). Fehlende Pflichtfelder fragt Michi als gezielte Rückfrage nach, sie werden nicht geraten.
- **Speichern:** Das ausgefüllte PDF kommt in den Vault der Person, dazu Download und Eintrag unter „Kommunikation".
- **Versand:** über eine **Mock-Träger-API** mit demselben Interface wie ein späterer echter Adapter: `POST /mock-traeger/{traeger}/eingang` (PDF + Metadaten + Begleitschreiben + Vertretungsnachweis) → `{aktenzeichen, eingang_am, status}`. Danach Statusereignisse (eingegangen → in Bearbeitung → Rückfrage → Bescheid) entlang der Demo-Zeitachse und eine Kopie an Mailpit. Empfänger kommt aus `/formular/<id>/empfaenger`.
- Die handgemappten 4 Formulare aus `b5-comms` dienen als Regressionstest, nicht als Sonderweg.
