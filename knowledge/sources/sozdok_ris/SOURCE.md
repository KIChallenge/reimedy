# Quelle `sozdok_ris` – Rechtsgrundlagen (SozDok-XML, Gegenprüfung RIS OGD)

Stand: 2026-11-05. Reproduzierbar mit `python3 knowledge/sources/sozdok_ris/ingest.py` (nur Standardbibliothek; `uv run` geht ebenso).

## Was
- **Rohdaten:** 14.244 SozDok-XML-Dateien in `_Source/Rechtstexte/` (nur gelesen, nicht kopiert; `raw/` bleibt leer). Je Paragraf/Artikel/Anlage genau eine Fassung (keine Dubletten gefunden), jüngster Stand der Daten: `pubdat` 2026-09-17. Die AVSV-Änderungen von ÖGK/SVS/BVAEB bis März bzw. Mai 2026 sind enthalten.
- **Ergebnis:** `out/documents.jsonl` (19.911 Dokumente, Schema A, max. 1.900 Zeichen, an Absatzgrenzen geteilt, `section` = „Abs. 1–3“), `out/leistung_rechtsgrundlagen.jsonl` (253 Mapping-Zeilen), `out/ris_check.json` (Gegenprüfung), `out/manifest.json`. `leistungen/stellen/formulare.jsonl` sind leer (bewusst: Rechtstext liefert keine Leistungs-Kandidaten, das Mapping steht in `leistung_rechtsgrundlagen.jsonl`).
- **Titel:** „§ 4 BPGG – Anspruchsvoraussetzungen“. **url:** RIS-Link `GeltendeFassung.wxe?...Gesetzesnummer=…&Paragraf=…` für Bundesgesetze mit bekannter Gesetzesnummer (ASVG, GSVG, BSVG, B-KUVG, BPGG, EinstV, KBGG, FLAG), sonst `sozdok:<dokid>` (Satzungen, Krankenordnungen, RRZ, EKO, E-MVB … sind AVSV bzw. nicht im Bundesrecht-Dienst).
- **Zusatzfelder** (über Schema A hinaus, vom Loader ignorierbar): `relevanz` (1–4) und `relevanz_text`, `abkrvo`, `gldart`, `gldnr`, `gesetz`, `aufgehoben`, `dokid`, `pubdat`, **`querverweise`** (aus `rvolink`: `{abkrvo, gldart, gldnr, abs, ziff}`, am ersten Chunk des Paragrafen).

## Relevanz-Stufen (nichts wird verworfen, nur markiert)
| Stufe | Dokumente | Inhalt |
|---|---|---|
| 1 `kern` | 5.238 | ASVG, GSVG, BSVG, B-KUVG, BPGG + EinstV, KBGG, FLAG, RRZ_2008, VO-EKO, Satzung/Krankenordnung ÖGK/SVS/BVAEB, Mutter-Kind-Pass-VO, Heilmittel-Bewilligungs-VO, Richtlinien Zuzahlungs-/Service-Entgelt-Befreiung, Gesundheitsförderung |
| 2 `relevant` | 1.840 | Musterkrankenordnung, E-MVB (Vollzugsempfehlungen), AlVG, EFZG, SVSG, FSVG, KGG, PflegefondsG, APG, AUVA-Satzung 2025, RRK 2021 (Kuren), Veränderliche Werte, Unterstützungsfonds |
| 3 `rand` | 3.143 | alles nicht Klassifizierte, EU-Koordinierung, AMSG, BUAG, BMSVG u. a. |
| 4 `irrelevant` | 9.690 | Dienstordnungen DO.A/B/C, Abkommen über Soziale Sicherheit, Rechnungsvorschriften, Geschäfts-/Prüfungsordnungen, Statistik-Weisungen, Pensionsinstitut Linz u. ä. |

Empfehlung für den Loader/Index: Stufe 1–2 in die Hauptsuche, 3 nachrangig, 4 nur im Archiv. Die Stufen stehen als Tabelle `LAWS` / `IRRELEVANT_PREFIX` in `ingest.py` und sind dort änderbar. Unbekannte Materien landen in Stufe 3.

## Mapping Leistung ↔ Rechtsgrundlage
`out/leistung_rechtsgrundlagen.jsonl`: `{leistung_id, abkrvo, gldnr, abs, zitat, title, url, valid_from}`. `zitat` ist der wörtliche Anfang (≤380 Zeichen) des jeweiligen Abschnitts. `abs` ist ein Absatzbereich wie `1–3`, kein einzelner Absatz. Das Mapping ist **Kandidatenliste, noch nicht juristisch/redaktionell geprüft**. Abgedeckt (Zeilen): pflegegeld (34; BPGG §§ 1–13, 21, 25, 33, EinstV, Kinder-EinstV), pflegekarenz (25; BPGG §§ 21a–21h Pflegekarenzgeld + 3 AVRAG-Verweise), kinderbetreuungsgeld (21), familienbeihilfe (18), rezeptgebuehrenbefreiung (16; RRZ §§ 1–5, ASVG § 136/350, Satzung ÖGK), krankengeld (14), vorsorgeuntersuchung (13; ASVG § 132b/c, GSVG 116/117, B-KUVG), heilmittel_erstattungskodex (13), krankentransport_fahrtkosten (12; ASVG § 135, KrankenO ÖGK, Satzung ÖGK), reha_medizinisch (12; ASVG §§ 154a, 302 ff.), krankenbehandlung (10), heilbehelfe_hilfsmittel (10; §§ 137, 154, 154a, 155), pensionsversicherung_berufsunfaehigkeit, kur_gesundheitsvorsorge, mutterschaftsleistungen_wochengeld, selbst-/mitversicherung, reha_berufliche_pva, zahnbehandlung_zahnersatz, mutter_kind_pass, rezeptgebuehr_obergrenze, pflegegeld_erhoehungsantrag.
Grenzen: Die `leistung_id`s sind Vorschläge und müssen mit denen der anderen Quellen/der Wissens-DB abgeglichen werden. Das ASVG ist bei der Zuordnung der Paragrafen zu Gruppen (GSVG/B-KUVG-Parallelstellen nur teilweise) nicht vollständig. **Pflegekarenz/Pflegeteilzeit** (AVRAG §§ 14a, 14c, 14d) liegen nicht in den lokalen XMLs (Arbeitsrecht, nicht SozDok) → nur RIS-Verweis (`zitat: null`, `lokal: false`). Die Kinder-/Reha-Sondertatbestände (z. B. ASVG § 307d Kur) hängen am Stand der Novelle – bitte vor Nutzung im Ernstfall im RIS gegenlesen.

## Aktualität / Gegenprüfung (RIS OGD API v2.6)
`ingest.py --check-ris` (≈ 3 Min, 1 Request/s, UA `SV-Lotse-Hackathon/0.1`):
1. **Bundesrecht konsolidiert** (`/Bundesrecht?Applikation=BrKons&Titel=…&Abschnitt.Typ=Paragraph&Abschnitt.Von/Bis=<§>&Fassung.FassungVom=<heute>`): je Kern-Paragraf (96 geprüft) wird die heute gültige Fassung (Inkrafttreten ≤ heute, nicht ausgelaufen, jüngste) mit dem lokalen `ikra` verglichen. Der Filter über `Gesetzesnummer` allein funktioniert in der API nicht, daher Titel + Paragrafenbereich und Prüfung auf Gesetzesnummer im Ergebnis.
2. **AVSV** (`/Sonstige?Applikation=Avsv&Suchworte=Krankenordnung|Satzung`): Änderungen von ÖGK, SVS, BVAEB mit Kundmachungsdatum nach dem lokalen `pubdat`-Maximum der jeweiligen Datei werden als `neuer_als_lokal` markiert.

**Ergebnis 2026-11-05:** 86 aktuell, 4 `RIS_NEUER` (ASVG § 141 → RIS ikra 2017-01-01 statt lokal 2005; KBGG § 2 → 2026-07-01; FLAG § 2 und § 3 → 2026-10-17), 3 `abweichend` (ASVG §§ 350/351c, BPGG § 8: lokale SozDok-Fassung gibt ein anderes Inkrafttreten an als RIS, wahrscheinlich mehrere Fassungsstufen; manuell prüfen), 3 `nicht_in_ris_gefunden` (ASVG § 135a aufgehoben; § 164; FLAG § 8a). AVSV: für alle drei Träger ist die jeweils jüngste Änderung bereits im lokalen Stand (ÖGK KrankenO 1. Änd. 27.02.2026, SVS KrankenO 3. Änd. 25.03.2026, BVAEB KrankenO Neufassung 22.12.2025). Details: `out/ris_check.json`.
**Für die Abgabe heißt das:** Die lokalen XMLs sind für ASVG/BPGG/RRZ/Satzungen/KrankenO aktuell. Bei FLAG § 2/3, KBGG § 2 und ASVG § 141 im Zweifel RIS verweisen (Link in `url`). Die Werte (Pflegegeld-Beträge, Grenzen) kommen **nicht** aus diesem Korpus, sondern aus jährlichen Kundmachungen (`veraendW` enthält nur Übersichten).

**Update-Pfad:** (a) neue XML-Lieferung nach `_Source/Rechtstexte/` legen (oder `--src`) und `ingest.py` laufen lassen. Sha256 pro Datei im Manifest, unveränderte Dateien kommen aus `out/documents.jsonl`. (b) Zwischenstände holt `--check-ris`; für RIS_NEUER-Paragrafen kann die XML-Fassung über `ris_url` bzw. `ogd.ris.bka.gv.at/Dokumente/Bundesnormen/<NOR-ID>/<NOR-ID>.xml` (aus `DokumentUrl` in der API) nachgeladen werden. Das ist noch nicht automatisiert (Hackathon-Scope). (c) Satzungen/KrankenO: AVSV-Check (siehe oben), bei `neuer_als_lokal=true` neue SozDok-Lieferung abwarten oder AVSV-Dokument ziehen.

## sozdok.at – was ist das, ist es die Quelle der XMLs?
- sozdok.at ist die **„Dokumentation des österreichischen Sozialversicherungsrechts“ des Dachverbands der Sozialversicherungsträger** (JSF-Webanwendung unter `/sozdok/allgemein/startseite.xhtml`). Öffentlich: Schnellsuche („§ 4 ASVG“, Volltext) für Rechtsvorschriften in aktueller Fassung, Übersicht, Expertensuche. Mit (kostenloser) Registrierung zusätzlich u. a. Gesetzesmaterialien, parlamentarische Anfragen, Entscheidungen und Erlässe; „Briefkasten“. Die Seite hat keine Sitemap, keine dokumentierte API und kein robots.txt (liefert nur die 404-Seite). Ich habe sie nicht gecrawlt, nur die Startseite gesichtet.
- Das **XML-Format passt**: `<sozdok dokid="…"><rvo><metadaten … gldart gldnr ikra pubdat>` mit Querverweisen (`rvolink`), `berkz`, Änderungsprotokoll, `layoutdaten` → Inhaltlich/strukturell ist das ein SozDok-Export (Dokument-IDs wie `ASVG=PARA=135=145=2024-10-09=2025-01-01`). Dass die lokal vorliegenden Dateien genau von sozdok.at stammen, kann ich **nicht belegen** (kein Download-Angebot gefunden); sie sind vermutlich ein Datenexport der SozDok. Herkunft/Lizenz der Lieferung bitte beim Datenlieferanten bestätigen.

## Lizenz
- **RIS/Bundesrecht:** Daten des Rechtsinformationssystems des Bundes stehen als Open Government Data unter **CC BY 4.0** (Quellenangabe: „Bundeskanzleramt, Rechtsinformationssystem des Bundes (RIS)“). Texte von Gesetzen/Verordnungen sind zudem amtliche Werke (§ 7 UrhG, nicht urheberrechtlich geschützt).
- **Satzungen, Krankenordnungen, Richtlinien, E-MVB** (AVSV/Dachverband): amtliche Kundmachungen; ebenfalls § 7 UrhG, Nutzungsbedingungen der SozDok bzw. des Dachverbands für die lokale Lieferung nicht geprüft → für den Hackathon unkritisch, für Produktivbetrieb klären.
- `license_note` in jedem Dokument benennt das.
- **robots.txt:** `data.bka.gv.at/robots.txt` sperrt generische Bots (`Disallow: /`) und gibt nur den Justiz-Crawler frei. Die OGD-API ist ausdrücklich für maschinellen Zugriff gedacht; ich habe sie mit ~220 Requests (1 Req/s) für die Gegenprüfung genutzt, keinen Massen-Crawl. Für den Produktivbetrieb sollte der Zugriff mit dem RIS-Team abgestimmt oder auf die OGD-Bulk-Downloads umgestellt werden.

## Bekannte Lücken / Vorsicht
- **Textqualität:** Tabellen werden als `a | b` ausgegeben, Fußnoten inline, Formeln/Binärdaten fehlen. Listen-Marker („1.“, „a)“) bleiben im Text. Absatz-`section` nur dort, wo „(n)“ am Zeilenanfang steht.
- Kein Hinweis auf **Fassungsverläufe**: pro Paragraf nur die aktuelle Fassung; `valid_from` = ikra, kein `valid_to`. Zukunfts-Inkrafttreten (ikra > heute) sind nicht separat markiert.
- Gesetzesnummern/RIS-URLs gibt es nur für die acht Bundesgesetze oben; für alle anderen Materien `sozdok:`-Referenzen.
- Mapping `leistung_id` → Paragraf ist maschinell/fachlich vorgeschlagen, nicht verifiziert. **Keine Interpretation**: der Lotse zitiert nur, er legt nicht aus und entscheidet keinen Einzelfall.
- Die Korpusgröße (≈ 41 MB `documents.jsonl`, davon 9.690 Chunks Stufe 4) kann der Loader per `relevanz` filtern.
