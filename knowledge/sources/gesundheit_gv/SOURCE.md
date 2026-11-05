# Quelle `gesundheit_gv` – gesundheit.gv.at + pflege.gv.at

Stand der Erhebung: 2026-11-05. Aufruf: `uv run knowledge/sources/gesundheit_gv/ingest.py [--no-fetch]`

## Was ist drin
| | Seiten | Abschnitte (Schema A) |
|---|---|---|
| www.gesundheit.gv.at (BMASGPK / GÖG) | 240 abgerufen | 1.822 |
| pflege.gv.at (GÖG) | 130 abgerufen | 454 |
| Gesamt | 370 × HTTP 200 (+3 Fehler) | **2.276** (≤1.900 Zeichen, Wortlaut) |

Ausgaben: `out/documents.jsonl` (A), `out/leistungen.jsonl` (B, 45 Kandidaten), `out/stellen.jsonl` (C, 6 verifizierte Hotlines + ~600 Beratungsstellen-Links), `out/manifest.json`. Keine `formulare.jsonl` (Portale verlinken nur auf Formulare anderer Träger).

Themenfokus (Seeds = Regex-Auswahl aus den Sitemaps, kein Massen-Crawl): Vorsorgeuntersuchung (Ablauf, Anspruch, Kosten), Krebs-**Früherkennung** (Brust, Darm inkl. Altersgrenzen/Intervalle, Gebärmutterhals, Haut, Prostata), Impfungen (Kinderimpfprogramm, Erwachsene, Impfschutz, e-Impfpass), Eltern-Kind-Pass (Untersuchungen, elektronischer EKP), Bewegung/Bewegungsempfehlungen, Ernährungspyramide, Nichtrauchen/Rauchfrei Telefon, psychosoziale Angebote, Patientenrechte/Patientenanwaltschaft/Patientenverfügung/Vorsorgevollmacht, Primärversorgung, Arztbesuch (Wahlarzt, e-card), ELGA, Kur/Reha, Palliativ, Selbsthilfe, Beratungsstellen, Notrufnummern, Leichter-Lesen (`lang:"de-einfach"`, 83 Abschnitte), und von pflege.gv.at: Pflegegeld (Stufen, Antrag, Klage), Pflegekarenz/-teilzeit/-karenzgeld, Angehörigenbonus, Angehörigengespräch, 24-Stunden-Betreuung, mobile Dienste, Heime, Entlastung/Kurzzeitpflege, Reha für pflegende Angehörige, Gebührenbefreiungen, Behindertenpass, Beratungsstellen, Selbsthilfe.
**Bewusst ausgelassen:** Krankheits-/Symptomseiten, Laborwerte, Lexikon, Gesundheitsberufe, Rezepte, Reise-/Indikationsimpfungen je Erreger, Demenz-Klinikseiten auf pflege.gv.at.

## Besonderheiten der Ausgabe
- Zusätzliches Feld `stand` (Datum „Letzte Aktualisierung“ der Seite, sonst `Last-Modified`) in Schema A; `valid_from` bleibt `null`.
- Zusätzliches Feld `tags:["evidenz_nutzen"]` (125 Abschnitte): Abschnitte auf Vorsorge-/Früherkennungs-/Impf-/Bewegungs-Seiten, die Nutzen, Risiken, Empfehlungen, Heilungschancen o. Ä. nennen (Regex-Heuristik, **Wortlaut unverändert**). Konzept-Session 05 kann sie als zitierbare Evidenz-Passagen für Erklärungen ohne eigene Risikobewertung nutzen. Heuristik ist grob → Review.
- `leistungen.jsonl`: `voraussetzungen[].zitat`, `kosten`, `fristen`, `antrag.wo` sind **wörtliche Sätze** aus den Abschnitten mit passenden Überschriften (automatisch geprüft: alle Zitate sind Teilstrings der Quelle). `kurz_einfach` ist der Wortlaut der Quelle (nur bei Kinderimpfungen aus der Leichter-Lesen-Seite) und mit „[Wortlaut Quelle, nicht vereinfacht]“ markiert → vor Anzeige durch LLM/Mensch vereinfachen. `zustaendig`, `formular_id`, `abhaengigkeiten`, `unterlagen` bleiben leer. `confidence` = „niedrig“, wenn keine Voraussetzungen extrahiert wurden (z. B. Brustkrebs/Darmkrebs-Seiten haben keine Anspruchs-Überschrift; Altersgrenzen stehen im Fließtext der Section „Welche Vorsorgeuntersuchungen …“ → über `tags` abrufen). `traeger` ist eine Annahme aus allgemeinem Wissen und nicht aus dem Portal belegt → prüfen.
- `stellen.jsonl`: Hotlines nur aufgenommen, wenn die Nummer im Quelltext steht (1450, 144, 141, 142, Vergiftungsinfo, Rauchfrei Telefon). Die ~600 Beratungsstellen sind externe Links (Name = Linktext, `url` oft `gesundheit.gv.at/linkresolution/…`-Redirect) ohne Adresse/Telefon; Roh-Qualität, Duplikate möglich.
- Alle Texte sind Portalinformation, **keine individuelle Beratung**; Medizinisches nur als Quelle mit Zitat verwenden.

## Nachnutzungsbedingungen (Impressum geprüft 2026-11-05)
- **gesundheit.gv.at** (Impressum „Geistiges Eigentum“): Texte, Grafiken, Bilder sind urheberrechtlich geschützt, alle Rechte vorbehalten. Teilweise oder vollständige Verwendung (Entnahme/Wiedergabe) bedarf der **vorherigen Genehmigung des BMASGPK**, *ausgenommen der Bezug im Wege der Content-Syndizierung*. Bildmaterial überwiegend Adobe Stock (nicht übernommen). **Keine offene Lizenz (kein CC/OGD).**
- **pflege.gv.at** (Impressum, Herausgeber GÖG): ebenfalls alle Rechte vorbehalten, Verwendung von Inhalten nur mit vorheriger Genehmigung der GÖG.
- Folge: Für den Hackathon-Prototyp intern als Wissensbasis mit Quellenangabe/Link und kurzen Zitaten vertretbar; **keine Weiterverbreitung/Veröffentlichung der Rohtexte (`raw/`, `documents.jsonl`) und keine Wiedergabe ganzer Seiten.** Für Produktivbetrieb: Genehmigung beim BMASGPK/GÖG einholen oder das Content-Syndication-Angebot des Portals nutzen (Kontakt: Portalredaktion bzw. post@sozialministerium.at laut Impressum). Jedes Dokument trägt `license_note`.
- Haftungsausschluss der Portale: Inhalte ohne Gewähr, keine Rechtsansprüche.

## Crawling / robots
- gesundheit.gv.at: keine `robots.txt` (404, Seite mit `noindex`-Fehlerseite) → nichts untersagt; pflege.gv.at: Drupal-Standard-robots (`/search/`, `/admin/` etc. gesperrt; keine genutzt). UA `SV-Lotse-Hackathon/0.1`, ≥1,1 s Pause, nur URLs aus den öffentlichen `sitemap.xml`.

## Update-Strategie
`ingest.py` liest die Sitemaps neu, ruft jede Seite konditional ab (ETag / If-Modified-Since → 304), vergleicht `sha256`, schreibt Rohdateien nach `raw/<sha1(url)>.html` und baut **alle** `out/*.jsonl` deterministisch aus `raw/` neu (idempotent). `--no-fetch` baut nur neu. Voller Lauf ≈ 8 min (370 Seiten, 1 req/s). Zustand: `out/manifest.json` (`urls[].sha256/etag/last_modified/fetched_at/checked_at/status`).

## Lücken / bekannte Schwächen
- Drei URLs lieferten Fehler/Timeout: `pflege.gv.at/de/psychosoziale-gesundheit`, `gesundheit.gv.at/…/patientenrechte/sachwalterschaft.html`, `gesundheit.gv.at/…/bewegungsempfehlungen-erwachsene-chronische-erkrankungen.html` (Status 0, beim nächsten Lauf erneut versucht).
- Nicht in der Seed-Auswahl: „Impfplan Österreich“ als PDF (nicht Teil der Portal-HTML-Seiten), Brustkrebs-Früh-Erkennungs-Programm-Details (Einladungssystem, Altersgruppen) nur soweit im Portaltext; keine Seite „Bewegt im Park“ als Programm/Terminliste (nur Newsmeldungen 2025/2026); Darmkrebs „familiäre Belastung“ nur soweit im Text der Früherkennungsseite.
- Bundesländer-spezifisches (Wien etc.): Portal ist österreichweit; `bundesland` überall `["AT"]`.
- Tabellen/Akkordeons werden als Fließtext mit „•“-Listen geflattet; Abbildungen/Videos ignoriert; Quellenverzeichnis-Abschnitte werden entfernt.
- Stand-Datum aus Seitentext nur bei gesundheit.gv.at; pflege.gv.at nur `Last-Modified`.
