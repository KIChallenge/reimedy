# Quelle `sozialministeriumservice` – Sozialministeriumservice (Bereich E, teils D)

Stand Crawl: 2026-11-05. Ergebnis: 15 Seiten → **136 Dokument-Abschnitte**, **7 Leistungs-Kandidaten**, **24 Formulare** (alle live geprüft), **2 Stellen** (Landesstelle Wien, bundesweites Info-Telefon).

## Technik / robots / Lizenz
- Serverseitig gerenderte Seiten, Hauptinhalt in `#maincontent`; keine JS-Pflicht. `robots.txt`: `User-agent: * / Disallow:` (alles erlaubt). ≤1 Request/s, UA `SV-Lotse-Hackathon/0.1`, kein Login.
- Lizenz: keine offene Lizenz erkennbar; © Sozialministeriumservice, nur mit Quellenangabe (`license_note`).
- Seitenliste ist themenbasiert (`PAGES` in `ingest.py`, Tiefe 1, kein Crawl). Abgedeckt: Behindertenpass (+ Zusatzeintragungen, Übersicht), Parkausweis § 29b, 24-Stunden-Betreuung, Pflegekarenz/-teilzeit, Unterstützung für pflegende Angehörige (Ersatzpflege + Pflegekurse), Unterstützungsfonds, Finanzielle Unterstützung (Übersicht, Mobilitätsförderungen), Pflegeunterstützungen (Übersicht), Kontakt, Landesstellen, Landesstelle Wien.

## Leistungs-Kandidaten (`leistung_id`)
`behindertenpass`, `parkausweis_29b`, `foerderung_24h_betreuung`, `unterstuetzungsfonds_behinderung`, `angehoerigen_unterstuetzung_ersatzpflege` (Zuwendung zu den Kosten der Ersatzpflege), `pflegekurse_zuwendung`, `pflegekarenzgeld`.
- `unterstuetzungsfonds_behinderung` ist der **Bundesfonds für Menschen mit Behinderung** und nicht der Unterstützungsfonds der Krankenversicherung (`unterstuetzungsfonds` bei ÖGK, `unterstuetzungsfonds_bvaeb`). Der Graph soll beide über das Taxonomiefeld `nicht_verwechseln_mit` trennen.
- Abhängigkeiten: `behindertenpass` → `parkausweis_29b`, `unterstuetzungsfonds_behinderung`; `pflegegeld` → 24h-Förderung, Ersatzpflege, Pflegekurse, Pflegekarenzgeld (`pflegegeld` selbst kommt aus der PVA-Quelle).
- `voraussetzungen`, `unterlagen`, `fristen`, `kosten` sind **wörtliche Sätze**, per Überschrift/Schlüsselwort ausgewählt. Mensch-Review nötig. Bekannte Schwächen: Die Voraussetzungsliste der Ersatzpflege („pflegt seit mindestens einem Jahr …“) steht in verschachtelten Blöcken, die der Parser überspringt, daher fehlt sie; `pflegekurse_zuwendung` und `angehoerigen_unterstuetzung_ersatzpflege` teilen sich dieselbe Seite und damit teils dieselben Einkommenssätze; `fristen` beim Parkausweis enthält nur eine Überschrift („Online Antragsstellung“). `kurz_einfach` ist handgeschrieben (nahe am Seitentext), nicht lektoriert; `zielgruppe` leer. `confidence` höchstens „mittel“.
- Die Beträge (z. B. Unterstützungsfonds-Einkommensgrenze 2.616,78 €, 24h-Förderung 400/800 €) stammen aus den Seiten mit deren Stand-Angaben („Stand 2026“ bzw. „ab 01.09.2023“); die Seiten haben kein Last-Modified, `valid_from` ist `null`.

## Formulare (`formulare.jsonl`)
- Aufgenommen sind nur Download-Dateien (`.pdf/.doc/.docx/.xls/.xlsx`) auf sozialministeriumservice.gv.at, deren Dateiname/Linktext nach Antrag/Ansuchen/Bestätigung/Kontoüberweisung aussieht. **Jede URL wurde live abgefragt** (GET mit Range, Redirects verfolgt; gespeichert ist `final_url`, `content_type`, `bytes`, `geprueft_am`); HTML-Seiten und Videos werden verworfen. Ausgeschlossen: Infoblätter, Richtlinien, Datenschutz-Beilagen, Broschüren, Checklisten, Organigramm, Projektförderungs- und Rahmenvertragsunterlagen.
- 19 von 24 sind **Word-Dokumente (.doc/.docx)**, nur 5 sind PDFs; `fillable` ist `null`, `felder` leer (nicht geparst). Das Feld `url_pdf` enthält daher meist eine Word-Datei (`format` nennt die Endung). B5 kann sie nicht als AcroForm füllen.
- 24h-Betreuung: Der Antrag existiert zusätzlich in sechs Sprachvarianten (BG, HR, HU, PL, RO, SK); alle sind enthalten. Ohne `leistung_ids` bleiben Individualförderungs- und Mobilitätsformulare (Assistenzhund, KFZ, Mobilitätszuschuss, Förderansuchen allgemein), weil dafür keine Leistung modelliert ist.
- **Online-Anträge** (formularservice.gv.at) sind **keine Formulare**, sondern stehen in `leistungen.antrag.online_url`. Sie leiten auf ein ID-Austria-Login mit Einmal-Token um; deshalb wird die stabile Einstiegs-URL gespeichert (Link-Check: HTTP 200), nicht die Redirect-Ziel-URL. Feld `online_login` nennt „ID Austria / Bürgerkarte“. Der mymailwall-Tracking-Link bei Ersatzpflege wurde auf das Ziel entpackt.

## Stellen
- `sms_landesstelle_wien`: Babenbergerstraße 5, 1010 Wien, Tel 01/588 31, E-Mail, Öffnungs- und Beratungszeiten (wörtlich von der Seite). **Koordinate** per Nominatim (© OpenStreetMap-Mitwirkende, ODbL) einmal geocodiert und im Manifest gecacht (`geocode`). Nur Wien; die 8 anderen Landesstellen wurden nicht aufgenommen (Seiten sind verlinkt, `Landesstellen_des_Sozialministeriumservice.de.html` liegt als Dokument vor).
- `sms_hotline`: Info-Telefon 05 99 88 (Startseite), bundesweit.

## Lücken
- Nicht aufgenommen: erhöhte Familienbeihilfe, steuerliche Absetzmöglichkeiten, Arbeitsmarkt-/NEBA-Angebote, Begünstigte Behinderte, Sozialentschädigung (außerhalb des Auftrags). Nicht geprüft: Inhalte hinter dem Online-Ratgeber behindertenpass.mein-ratgeber.at.
- Pflegekarenzgeld: Antragsformulare vorhanden, aber die Höhe des Pflegekarenzgeldes steht auf diesen Seiten nicht als Satz (kosten leer); sie ist beim Sozialministerium bzw. oesterreich.gv.at nachzutragen.

## Update
`uv run knowledge/sources/sozialministeriumservice/ingest.py [--offline] [--force]`. Der Server sendet kein ETag/Last-Modified; Konditional-Header sind vorbereitet. Die Änderungserkennung läuft über `raw_sha256`/Text-sha256 in `manifest.json`. Links (Formulare, Online-Anträge) werden je Tag einmal neu geprüft (`manifest.links`). `--offline` baut alle Outputs deterministisch aus `raw/` + Manifest neu (getestet: identisch). Ein Lauf braucht ~1 min. `raw/` nicht ins Git.
