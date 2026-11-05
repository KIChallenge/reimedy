# Quelle `wien_ogd` – Einrichtungen in Wien (Open Government Data der Stadt Wien)

Stand Abruf: 2026-11-05. Ergebnis: **9.140 Stellen mit Koordinaten** (`out/stellen.jsonl`, Schema C) + 10 Datensatz-Beschreibungen (`documents.jsonl`, Quellen- und Lizenznachweis). `leistungen.jsonl` und `formulare.jsonl` sind bewusst leer.

## Quelle und Lizenz
- WFS `https://data.wien.gv.at/daten/geo?service=WFS&request=GetFeature&version=1.1.0&typeName=ogdwien:<LAYER>&srsName=EPSG:4326&outputFormat=json` (GeoJSON, Punkte, WGS84). Die Layer wurden über `GetCapabilities` und die data.gv.at-Such-API gefunden; `katalog_url` verweist auf den jeweiligen data.gv.at-Eintrag (live geprüft für Ärzt:innen und Apotheken, übrige IDs aus der Such-API).
- **Lizenz CC BY 4.0, Namensnennung: „Stadt Wien – data.wien.gv.at“** (steht in jedem Datensatz im Feld `lizenz`). Die UI muss diese Quellenangabe anzeigen.
- robots.txt: `data.wien.gv.at/robots.txt` liefert eine HTML-Seite, also keine Einschränkung. Je Layer 1 Request, ≤1 Request/s, UA `SV-Lotse-Hackathon/0.1`.

## Abdeckung
| Layer | `kategorie` | `typ` | n |
|---|---|---|---|
| ARZTOGD | arzt | arzt | 7.641 |
| AMBULANZOGD | spitalsambulanz | einrichtung | 862 |
| APOTHEKEOGD | apotheke | apotheke | 358 |
| WOHNPFLEGEHAUSOGD | pflegewohnhaus | einrichtung | 134 |
| PRIMAERVERSORGUNGOGD | primaerversorgung | pve | 78 |
| KRANKENHAUSOGD | krankenhaus | einrichtung | 28 |
| SOZIALMARKTOGD | sozialmarkt | einrichtung | 28 |
| BERATUNGSZENTROGD (FSW Pflege & Betreuung) | beratungszentrum_pflege_fsw | beratung | 6 |
| FAMHEBAMMEOGD | familienhebamme | beratung | 4 |
| IMPFSTELLEOGD | impfstelle | einrichtung | 1 |

Zusatzfelder über Schema C hinaus: `kategorie`, `bezirk`, `plz_abgeleitet`, `fachrichtung` (nur Ärzt:innen), `kassenvertrag` (immer `null`), `lizenz`, `katalog_url`, bei FSW `zustaendig_plz`. Die Felder `zustaendig_fuer` sind nur bei Impfstellen (`impfungen`) und Familienhebammen (`hebammen`) gefüllt; die Leistungs-Zuordnung der übrigen Kategorien soll der Graph über `kategorie` machen.

## Ehrliche Befunde und Lücken
- **Kein Kassenvertragsfeld.** Der Ärzt:innen-Datensatz enthält nur `NAME, ADRESSE, FACH, TELEFON, INTERNET`. Es steht **nirgends**, ob eine Ordination Kassen-, Wahl- oder Privatordination ist. Der Lotse darf daraus keine Kassenvertrags-Aussage ableiten. Das Wiener Ärzt:innenverzeichnis (praxisplan.at, über `url` verlinkt) und die ÖGK-Arztsuche sind dafür die Quellen, nicht dieser Datensatz.
- **Fachrichtungsfeld vorhanden:** `FACH` (59 verschiedene Werte, z. B. „Allgemeinmedizin“ 1.538, „Innere Medizin“ 778, „Allgemein- und Familienmedizin“ 476). Die Werte sind Freitext der Ärztekammer-Systematik, nicht die SNOMED-Fachrichtungen aus `reimedy_kb`; ein Mapping steht aus. Zahnärzt:innen sind laut Fachfeld/Name teilweise enthalten, wurden nicht gesondert geprüft.
- **Keine Seniorentreffpunkte/Pensionistenklubs und keine Sozialzentren** als OGD-Layer: weder im WFS-Katalog (377 Layer) noch in der data.gv.at-Suche für Wien (Suchen „Pensionistenklub“, „Seniorentreff“, „Sozialzentrum“ ohne Wien-Treffer). Hinweis: Die „Häuser zum Leben“ (Pensionisten-Wohnhäuser) stecken im Layer Wohn- und Pflegehäuser. Ersatz in der Wissens-DB nur über `fsw`/Beratungszentren.
- `HAUSBETREUUNGOGD` ist leer (0 Features) und wurde nicht aufgenommen. `GEBIETSBETREUUNGOGD` (Wohnen, Stadterneuerung) ist nicht gesundheitsrelevant.
- **PLZ:** Nur der PVE-Layer liefert eine PLZ. Bei allen anderen Layern wird sie aus dem Bezirk abgeleitet (`1000 + 10·Bezirk`, z. B. 5. Bezirk → 1050; `plz_abgeleitet: true`). Das ist für Wien fast immer korrekt, aber eine Annäherung.
- Telefonnummern der AKH-Ambulanzen sind im Quelldatensatz defekt („+43 1 40400-(+43 1) +43 1 40400“) und werden auf `null` gesetzt. Namen der Ambulanzen setzen sich aus Krankenhaus, Abteilung und Ambulanz zusammen; `<br />`-Reste werden bereinigt. Öffnungszeiten gibt es nur bei Impfstelle und FSW-Beratungszentren. Es gibt keine Wartezeiten und keine Barrierefreiheitsangaben.
- Geo-Qualität: alle 9.140 Stellen haben Koordinaten (lat, lon, 6 Nachkommastellen). Ambulanzen eines Spitals teilen sich dieselbe Koordinate. Nur Wien; keine anderen Bundesländer.

## Update
`uv run knowledge/sources/wien_ogd/ingest.py [--offline] [--force]`. Der Server sendet kein ETag/Last-Modified. Die Änderungserkennung läuft über sha256 der Features ohne `timeStamp` (`manifest.json`, `changed_at`). Es werden immer alle Outputs deterministisch aus `raw/*.json` neu gebaut (getestet: identische Outputs bei zwei Läufen). Empfehlung: wöchentlich. `raw/` (3,6 MB) nicht ins Git.
