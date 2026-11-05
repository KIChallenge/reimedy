# Quelle `pva` – Pensionsversicherungsanstalt (www.pv.at)

Stand Crawl: 2026-11-05. Ergebnis: 26 Seiten → 242 Dokument-Abschnitte (≤2.000 Zeichen), 8 Leistungs-Kandidaten, 4 Formulare (Live-PDFs geladen und abgeglichen), 20 Stellen (17 Reha-Zentren + Landesstelle Wien, Hauptstelle, Kundenservice-Hotline).

Aufruf: `uv run --python 3.12 knowledge/sources/pva/ingest.py [--offline] [--force]` (`--offline` baut alles deterministisch aus `raw/`; getestet: zweimal identische Outputs).

## Technik / robots / Lizenz
- Seiten sind serverseitig gerendert (`https://www.pv.at/web/<slug>`), Hauptinhalt in `#esv-content_with_nav`. Kein JS nötig. FAQ-Akkordeons („Häufige Fragen“) sind dynamisch und **nicht** enthalten.
- `robots.txt`: leitet auf eine 404-Seite um, also keine Einschränkung. Trotzdem ≤1 Request/s (1,1 s), UA `SV-Lotse-Hackathon/0.1`, kein Login, nur Themen-Seeds (26 Seiten, keine Link-Verfolgung).
- Lizenz: keine offene Lizenz erkennbar, Inhalte © PVA, Nutzung nur mit Quellenangabe (`license_note` je Dokument).
- **Inkrementell:** der Server sendet für diese Seiten **kein ETag/Last-Modified** (Konditional-Header sind vorbereitet). Änderungserkennung über `sha256` des extrahierten Seitentexts (`manifest.json`: `changed_at`) und `raw_sha256` der PDFs. Ein Lauf lädt alle 31 URLs neu (~40 s).
- `valid_from` = Datum aus „Stand: …“ der Seite, falls vorhanden.

## Pflicht: Formular-Abgleich Live ↔ lokale Kopie (`_Source/Anträge und Formulare/`)
| Formular | Live-URL (final, keine Redirects; versionslos = immer aktuelle Fassung, identische Bytes wie die versionierte Verlinkung auf pv.at) | sha256 | AcroForm-Felder (pypdf) |
|---|---|---|---|
| `pva_pal080` Antrag auf Pflegegeld | `https://www.pv.at/cdscontent/load?contentid=10008.781956` (Dateiname `PAL080_0125_Mpfl_052026.pdf`) | **identisch** mit `PAL080_0125_Mpfl_052026.pdf` | 102 = 102, gleich |
| `pva_antrag_kur_reha` Antrag Rehabilitations-, Kur- bzw. Erholungsaufenthalt | `https://www.pv.at/cdscontent/load?contentid=10008.781981` (live `Reha_Kur_Antrag_052026.pdf`) | **verschieden** (live `10b3c1d3…`, lokal `45c4d2ae…`) | 96 = 96, **Feldnamen gleich**, 2 Seiten (nur Binärunterschied, kein Feldunterschied) |
| `pva_ahv_reha_nach_unfall` Antrag auf Anschlussheilverfahren oder Rehabilitation nach Unfall | `https://www.pv.at/cdscontent/load?contentid=10008.781971` (live `Reha_n_Unfall_052026.pdf`) | **identisch** mit `Reha_n_Unfall_052026.pdf` | 59 = 59, gleich |
| `pva_gvr001_uebergangsgeld` Antrag Übergangsgeld / berufliche Reha (GVR 001, 16 Seiten inkl. Merkblätter) | `https://www.pv.at/cdscontent/load?contentid=10008.781947` | – (keine lokale Kopie) | 352 Felder |

Details je Formular (Status, Bytes, Seiten, Hashes) in `out/formulare.jsonl` → Feld `abgleich`. `local_pdf` zeigt auf die Kopie; die Kopien in `_Source/` sind laut ARCHITEKTUR §3 nur Fallback. `Reha_n_Unfall_052026.pdf` ist auf pv.at in den gecrawlten Seiten **nicht direkt verlinkt** (gefunden über eine Websuche, `gefunden_auf` leer), liegt aber live und ist identisch; Quelle für die Verlinkung: Seite Medizinische Rehabilitation (erwähnt „telefonische Antragstellung durch das Krankenhaus“). Dasselbe Formular liegt auch bei sozialversicherung.at/BVAEB/SVS; Dedupe über sha256 im Build.

Online-Anträge (formgen, Weiterleitung auf `sozialversicherung.gv.at/formulare-prod/formserver_pva/…`, mit 200 geprüft, Session-gebunden – deshalb die formgen-URL als `online_url` gespeichert):
- Pflegegeld: `https://www.sozialversicherung.gv.at/formgen/?contentid=10007.892452&portal=pvportal&LO=1&layout=withNav&svtcode=02` (`Antrag_Pflegegeld_PVAF018`)
- Übergangsgeld: `…contentid=10007.892445…` (`Berufl_Rehab_PVAF025`)
- Für Reha/Kur-Antrag findet sich auf pv.at **kein** Online-Antrag, nur das PDF.

## Abdeckung
| Leistung | Qualität | Anmerkung |
|---|---|---|
| `pflegegeld` | hoch | Voraussetzungen (65 h, 6 Monate, Aufenthalt AT), 7 Stufen 2026 mit Beträgen und Stundenwerten strukturiert (`pflegegeldstufen_2026`), Antrag/Erhöhung (gleiches Formular), Antragsberechtigte (Vertretung, Angehörige), Begutachtung/Hausbesuch, Beginn ab Monatserstem, Meldepflicht 4 Wochen, Ruhen bei Spital/Reha/Heim, Zuständigkeit PVA/BVAEB/SVS |
| `rehabilitation` | hoch | Voraussetzungen, Antrag über Ärzt:in, Landesstelle, Termin binnen 6 Wochen bestätigen, Zuzahlung strukturiert (`zuzahlung_staffel_stationaer`, max. 28 Tage/Jahr, ambulant keine) |
| `reha_onkologisch` | mittel | **Keine eigene Seite auf pv.at**: nur „Onkologische Erkrankungen“ als Indikation; Voraussetzungen/Ablauf = medizinische Reha. Zentren mit der Indikation: PV ZAR Graz, PV ZAR Wien, Reha-Zentrum Bad Schallerbach (`indikationen` in `stellen.jsonl`) |
| `anschlussheilverfahren` | mittel | Wenig Text (Spitalsärzt:in, telefonische Antragstellung), Formular live vorhanden |
| `kur` | hoch | Kur/GVA inkl. 22-Tage-Angebot, Kosten, Zuzahlung, Familien-/Taggeld |
| `rehabilitationsgeld` | **niedrig** | Auf pv.at keine eigene Seite, nur Verweise („aus der Krankenversicherung“); Primärquelle ist die ÖGK (Quelle `oegk`) |
| `uebergangsgeld` | mittel | Zusatz (nicht im Auftrag): Voraussetzungen, Antrag/Online-Antrag |
| `pflegekarenzgeld` | mittel | `innerhalb_sv: false`, `traeger: Sozialministeriumservice`; PVA informiert nur, Antrag beim Sozialministeriumservice |

**Zitate:** Voraussetzungen, Unterlagen, Fristen, Kosten und Zuständigkeit stammen aus `curated.py` und sind **wörtliche Sätze von pv.at**. `ingest.py` prüft bei jedem Lauf jedes Zitat gegen den aktuellen Seitentext und verwirft nicht mehr vorkommende (Warnung „ZITAT NICHT GEFUNDEN“). Aktuell 0 verworfen. `kurz_einfach` ist eine eigene knappe Formulierung (kein Zitat); für einfache Sprache später LLM.

## Stellen
- 17 Reha-Zentren aus der JSON-Liste der Seite „Reha-Zentren“ (`contentid=10007.891827`, Felder Base64-kodiert): Name, Bundesland, Indikationen, Website, Seiten-URL. Die Detailseiten (`/web/Listen/Reha-Zentren/…`) sind nur eine App-Hülle (liefern ohne JS keinen Inhalt) und wurden nicht gespeichert. **Adresse/Telefon fehlen** (Ausnahme PV ZAR Wien: Wehlistraße 127, 1020 Wien laut Kontakt-Seite) → Lücke, `geo` überall `null`.
- `pva_landesstelle_wien`: laut Kontakt-Seite finden wegen der Generalsanierung Beratung und Begutachtung derzeit in der **Ghegastraße 1, 1030 Wien** statt (Hauptstelle Friedrich-Hillegeist-Straße 1, 1020). Öffnungszeiten nach Terminvereinbarung. Beleg-Texte werden bei jedem Lauf gegen die Kontakt-Seite geprüft (`BELEG NICHT GEFUNDEN` bei Änderung).
- Andere Landesstellen (Adressen je Bundesland sind in einem Akkordeon/JS) **nicht** enthalten.
- Alle `url`/`website`-Werte wurden am 2026-11-05 mit HEAD/GET geprüft (66 URLs, alle 200; Websites der Zentren leiten per http→https bzw. auf `/web/startseite` um, die URL in der Datei ist die vom Träger angegebene).

## Lücken / Vorsicht
- FAQ-Antworten, Broschüren-PDFs (z. B. „Anspruch auf Pflegegeld in Österreich“ `10008.810769`, MedInfo) sind nur verlinkt, nicht geladen.
- Keine Entscheidungsfrist (z. B. 9 Monate für Pflegegeld-Bescheid) auf den gecrawlten Seiten gefunden → nicht erfunden.
- Pflegegeld-Beträge 2026 sind Stand der Seite (Jahreswerte, ändern sich zum 1.1.); Neuabruf durch Ingest.
- Informationen zu Landesstellen, Regionalsprechtagen (`service-und-kontakt/regionalsprechtage`) stehen nur als Dokument-Abschnitte zur Verfügung.
- Reha-Zuzahlungsstaffel gilt laut Seite für stationäre Aufenthalte; Einkommensgrenzen ändern sich jährlich.

## Harte Grenze
Medizinische Texte (Indikationen, Maßnahmen) sind reine Leistungsinfo mit Quelle; keine Diagnose, Befund- oder Therapieaussage ableiten. Notfall → 144, medizinische Fragen → Hausarzt/1450.
