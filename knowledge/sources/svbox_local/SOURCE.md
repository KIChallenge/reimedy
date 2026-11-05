# svbox_local – lokale SV-Box-Daten (`_Source/`)

Stand: 05.11.2026. Aufruf: `uv run knowledge/sources/svbox_local/ingest.py [--force]` (idempotent; sha256 je Eingabedatei in `out/manifest.json`, Teilergebnisse in `out/_parts/`). **Update** = neue/geänderte Datei in `_Source/` → nur diese Quelle wird neu verarbeitet, danach werden alle `out/*.jsonl` neu zusammengesetzt. `_Source/` wird nur gelesen. Kein Netzwerk, kein Crawling.

Nicht enthalten (andere Sessions): Rechtstexte (`sozdok_ris`), Befunde (`elga`).

## Ausgabe
| Datei | Inhalt |
|---|---|
| `documents.jsonl` (935) | 130 Broschüren-Abschnitte (`broschuere`, pro PDF-Doppelseite, Seitenzahlen im `section`; plus eigener Abschnitt „Rezeptgebühren-Tabelle 2026“), 66 Zahnärzte-Tarifpositionen + Erläuterungsseiten, 645 Ärzte-Tarifpositionen + Erläuterungen (`tarif`), 38 Formular-Klartexte (`formular`), 5 EKO-Zeichenerklärung (`faq`) |
| `leistungen.jsonl` (39) | Kandidaten, je Broschüren-Kapitel eine; plus `rezeptgebuehrenobergrenze`, `heilmittel_bewilligungspflicht`, `mundhygiene_kinder_jugendliche`, `kieferorthopaedie_gratis_zahnspange`, `hausbesuch_arzt` |
| `formulare.jsonl` (7) | alle 7 AcroForm-PDFs, 416 Felder insgesamt |
| `codes.jsonl` (13.596) | 6.985 `EKO`-Packungen + 6.611 `ATC`-Bezeichnungen (Schema E) |
| `stellen.jsonl` (2) | Hotline 1450, Notruf 144 |

## Quellen und Besonderheiten
- **ÖGK-Broschüre 2026** (Stand 01.01.2026): 59 PDF-Seiten sind Doppelseiten (zwei gedruckte Seiten). Text ist zweispaltig, die Extraktion mischt teils Spalten (z. B. S. 42/43; PDF-Seite 22 wurde umsortiert, damit die Tabelle „Befreiung von der Rezeptgebühr“ zusammenhängt). **Leistungs-Zitate** sind Sätze aus dem Quelltext, per Stichwort gewählt (`voraussetzungen[].zitat`, wörtlich inkl. PDF-Artefakten wie „er st“ oder „Behand - lung“). Mensch-Review nötig, `confidence: mittel/niedrig`; `rezeptgebuehrenbefreiung` ist `hoch`.
  - Rezeptgebührenbefreiung: Grenzbeträge 2026 in `parameter_2026` und im Zitat (1.308,39 € Alleinstehende, 2.064,12 € Paare, +201,88 €/Kind; bei hohen Krankheitsausgaben 1.504,65 € / 2.373,74 €); Rezeptgebühr 7,55 €. Spalten laut Layoutposition: *Ohne Antrag* = links, *Mit Antrag* = rechts.
  - Rezeptgebührenobergrenze: 2 % des Jahresnettoeinkommens (2026), Absenkung auf 1,5 % bis 2030, Mindestgrenze = Ausgleichszulagen-Richtsatz.
  - Krankentransport (Selbstbehalt 7,55 € / 15,10 €, frei bei Chemo-/Strahlen-/Dialysefahrten und Befreiten), Reha/Kur (Zuzahlung 11,06 / 18,96 / 26,87 € je nach Brutto), Heilbehelfe, 1450 vorhanden. Mitversicherung nur als Stichwort-Zitate (langes Kapitel).
  - **Widerspruch**: Broschüre S. 80/81 nennt Gratis-Mundhygiene 10–18 J., 1×/Jahr; Zahnärzte-HO 2026 (BVAEB-Pilot, Erl. Z. 27) nennt 6–18 J., 2×/Jahr. Beides steht als Zitat in `mundhygiene_kinder_jugendliche`; nicht aufgelöst.
- **Zahnärzte-HO 2026**: Tarifpositionen automatisch aus dem Tabellentext geparst (`Pos`, Abkürzung, Beträge in der Reihenfolge der Spalten; `traeger`-Geltung steht im `section`). Parser deckt nicht jede Zeile ab (66 Positionen erkannt; mehrzeilige Zellen, KFO-Teilbeträge teils nur als Erläuterungstext). Gratis-Zahnspange: IOTN 4/5 + Behandlungsbeginn vor 18, keine Zuzahlung (Zitate).
- **„ÖGK Honorarordnung Ärzt:innen“** ist laut Titelblatt die **Honorarordnung Steiermark, Stand 01.01.2025** (nicht Wien/2026). `bundesland:["ST"]`, `confidence: niedrig` bei `hausbesuch_arzt`. Positionen: Nummer + Text + Betrag; Zeilen ohne Kontext (z. B. Röntgenformate) sind nur Rohtarif.
- **Erstattungskodex** (Latin-1, Fixed-Width, aus Dateikopf abgeleitet): Spalten `Pharmanummer[0:7]`, laufende Nr.[9:15], Name[18:117], Bereich[118] (G=grün, Y=gelb), Kennzeichen[121:125] (IND, RE1, RE2, F14, Fachgruppe), Packung[125:132], zwei Preisfelder (Rohwerte, Bedeutung nicht belegt → `preis_raw`, nicht interpretieren), Rest `zusatz_raw`. `regeltext` aus `regeltext_v2.txt` (HTML entschärft, `<br>`→Zeilenumbruch), Indikationstext wörtlich aus `indtext_v2.txt`. `bewilligung`: `vorab_erforderlich` (RE1, 856), `nachtraegliche_kontrolle_moeglich` (RE2), `indikationsvermerk` (IND), sonst `nein_laut_kennzeichen`. **Nur administrativ**, keine Therapieaussage; Indikationstexte sind medizinisch und dürfen nur zitiert werden. `atccode.txt` ist nur eine Code-Liste ohne Verknüpfung zu den Packungen (Feld `atc` bei EKO daher leer).
  Das Datum „EKO 1/2024“ gilt nur für die Zeichenerklärung; die Datendateien tragen Sep-2026-Änderungsdatum.
- **Formulare**: Felder aus den AcroForm-Widgets (Name, Typ text/checkbox/radio/choice, Seite). `label` = AcroForm-`/TU` (verlässlich, FSW, ÖGK-Fahrtkosten, PAL080 teils) sonst nächstgelegener Text im Layout (`label_quelle: Layout…`, **unzuverlässig** bei Kur-/Reha-Anträgen); `quelle_hint` heuristisch (vorname, svnr, …). Verknüpfungen: PAL080→`pflegegeld`; Fahrtkosten→`krankentransport` + `rezeptgebuehrenbefreiung`; Kur/Reha→`kur_erholung`, `reha_medizinisch`; Reha-n-Unfall (vom Krankenhaus auszufüllen)→`reha_medizinisch`; FSW-Formulare→`fsw_*` (IDs von der FSW-Quelle noch abzugleichen). Das Bedarfsmeldungsformular für Senior:innen-WGs wird von einer Partnerorganisation ausgefüllt.

## Lücken
Keine Fließtext-Tarife für Kieferorthopädie-Hauptbehandlung in allen Spalten; keine OCR; keine Auswertung von Tabellen mit Bruttoeinkommen als strukturierte Felder (nur Zitat/`parameter_2026`); `antrag.online_url` leer; Lizenz: nur Hackathon-Nutzung der bereitgestellten Dokumente.
