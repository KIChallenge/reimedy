# Quelle `svs` – Sozialversicherung der Selbständigen (www.svs.at)

**Stand:** 2026-11-05 · **Update:** `uv run knowledge/sources/svs/ingest.py` (idempotent; bedingte GETs mit ETag/Last-Modified, Hash über extrahierten Inhalt, Manifest = Zustand; bei Netzwerkfehler wird der letzte Rohstand aus `raw/` weiterverwendet). Hilfscode: `_common.py` (auch für `bvaeb`, `aek_wien`), `portal_ingest.py`, `leistungen_svs.py` (Leistungs-Specs).

## Wie
- Der SV-Portal-CMS liefert Inhalte als `/cdscontent/?contentid=…&portal=svsportal`. BFS ab Startseite + Kundencenter-Seiten, max. Tiefe 3, **Cap 170 Seiten**, Linktext-Filter (Themen: Gesundheit, Vorsorge, Pflege, Reha, Kur, Rezept, Transport, Heilbehelfe, Wochengeld, Formulare, Kontakt …; ausgeschlossen: Beitrag/Gründung/Karriere/Presse …).
- Pro Seite: Inhalt (`#esv-content_with_nav` ohne Navigation), Zerlegung an Überschriften/Akkordeons in ≤1.900-Zeichen-Chunks → `out/documents.jsonl` (ca. 1.380 Chunks aus 170 Seiten).
- **Leistungs-Kandidaten** (`out/leistungen.jsonl`, 13): `leistung_id`s ÖGK-kompatibel (`pflegegeld`, `rezeptgebuehrenbefreiung`, `kur`, `vorsorgeuntersuchung`, `krankentransport`, `wochengeld` …) + SVS-spezifisch (`gesundheitshunderter_svs`, `selbstaendig_gesund_selbstbehalt`, `gesundheitsangebote_svs`). Voraussetzungen/Kosten sind **wörtliche Sätze** aus den gecrawlten Seiten (per Regex ausgewählt, programmatisch auf Wörtlichkeit geprüft) – das ist eine **Kandidatenliste zum Review, keine kuratierte Auskunft**; `kosten` = erster Treffer, Alternativen in `kosten_belege`.
- Formulare (`out/formulare.jsonl`, ~300): Links auf `/cdscontent/load?…` (PDF), `/formgen/…` (Online-Formular) bzw. Seiten unter „Formulare & Anträge“; PDFs werden **nicht** heruntergeladen/ausgelesen, `felder` leer. `leistung_ids` heuristisch über Linktext.
- Stellen (`out/stellen.jsonl`): SVS-Kundencenter Wien (Wiedner Hauptstraße 84-86, 1051 Wien; Servicenummer 050 808 808), dazu heuristisch aus Kontaktabschnitten gezogene Hotlines/Mails (Qualität gemischt – prüfen).

## Abdeckung (Challenge-Bereiche)
A Vorsorge ✔ (Vorsorgeuntersuchung, Brustkrebs-/Darmkrebs-Früherkennung, Impfungen, Gesundheits-Check Junior) · B Gesundheitsförderung ✔ (Gesundheitshunderter, Selbständig Gesund, Gesundheitswochen, Jackpot.fit, Rauchfrei Telefon) · C Behandlung/Reha ✔ (Reha, Heilverfahren/Kur, Heilbehelfe, Zahn, Krankentransport, Medikamente, Unfallheilbehandlung) · D Pflege ✔ (Pflegegeld inkl. Pflegestufen & Antrag, pflegende Angehörige, Angehörigenbonus) · E Finanzielles ✔ (Wochengeld, Krankengeld, Kinderbetreuungsgeld, Unterstützungsfonds, Befreiungen) · F Administration ◐ (Formulare-Übersicht, Kontakt, svsGO – nur Links).

## Wichtige Fakten für den Lotsen (alle mit Quelle in den Docs)
- **Selbstbehalt SVS (GSVG): 20 %** für ärztliche/zahnärztliche Behandlung; „Selbständig Gesund“: bei erreichten Gesundheitszielen **10 %**, „Nachhaltig Gesund“ bis **5 %** (Antrag, frühestens nach 6 Monaten; gilt für Gewerbetreibende/Neue Selbständige – Bauern: eigene Seite prüfen).
- **Gesundheitshunderter**: einmal pro Kalenderjahr, bis 100 €, freiwillige Leistung **ohne Rechtsanspruch** (§ 99b GSVG / § 96b BSVG); Antrag online (ID Austria) oder per Post.
- **Rezeptgebühr** lt. SVS-Seite „Selbstbehalt & Vergütung“: EUR 7,55 pro Packung (Stand 2026). Privatrezept → 80 % der Kosten abzüglich Rezeptgebühr rückerstattbar.
- Transporte: Direktverrechnung Flugrettung (Dachverband), Taxi-Gesamtvertrag WKO (nicht Wien).

## Lücken / Vorbehalte
- Cap 170 Seiten: Randthemen (Pension, Versicherung/Beitrag) bewusst nicht abgedeckt. Bauern-spezifische Unterschiede nicht systematisch geprüft.
- Keine PDFs ausgelesen (Flyer, Tarife, Formularfelder). Keine Geokoordinaten. Kundencenter außerhalb Wiens und Beratungstage nur, soweit auf den gecrawlten Seiten.
- Leistungs-Kandidaten enthalten automatisch gewählte Zitate: z. B. kann `kosten` auf einen unspezifischen Satz zeigen → vor Produktivnutzung manuell reviewen.
- SVS-Seiten mit `sva-kostenersatz`/`LO=4`-Weiterleitungen (Altportale) wurden teils als Leerseiten („Willkommen am Portal…“) erfasst.

## Lizenz / robots
`https://www.svs.at/robots.txt` → HTTP 404 (keine Vorgaben). Crawl höflich: 1 Request ≥1,1 s, UA `SV-Lotse-Hackathon/0.1`, nur öffentliche Seiten, kein Login. Inhalte © SVS; Verwendung als Kurzzitat mit Quellenangabe (`license_note`). Keine ausdrückliche Open-Content-Lizenz → für Produktivbetrieb Rücksprache mit SVS/Dachverband.
