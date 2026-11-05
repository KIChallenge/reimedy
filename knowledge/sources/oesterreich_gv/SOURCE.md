# oesterreich_gv – www.oesterreich.gv.at (ehem. HELP.gv.at)

Stand: 2026-11-05. Aufruf: `uv run knowledge/sources/oesterreich_gv/ingest.py [--no-fetch] [--refetch] [--max N]`
(`--no-fetch` parst nur `raw/`; ohne Flags: Sitemap holen, Seiten abrufen, neu bauen.)

## Technik / Schnittstellen
- **Keine öffentliche API / kein Open-Data-Dump** für die Inhalte gefunden (robots.txt kennt nur Sitemap; `/api/search` und `/api/request` sind interne Frontend-Endpunkte, nicht dokumentiert, nicht genutzt). Daher: Sitemap (`/sitemap.xml`, ~13.400 URLs) als Discovery + Themen-Präfix-Filter + HTML-Parsing (Next.js, serverseitig gerendert).
- Formular-Seiten (`/de/formsearch/form/N`) sind clientseitig; die PDF-/Online-Links stecken im eingebetteten RSC-Payload und werden daraus extrahiert (inkl. Format-Titel, z. B. „pdf ausfüll- und speicherbar“).
- Crawling: robots.txt geprüft, ≤1 Req/s, UA `SV-Lotse-Hackathon/0.1`, nur öffentliche Seiten. Die Site liefert kein ETag/Last-Modified (`no-store`) → Inkrementalität läuft über sha256 im `manifest.json` (Seiten werden dennoch abgerufen, ~9 Min. Vollrun; unveränderte werden in Output unverändert belassen).

## Abdeckung
- 516 Themenseiten → **2.216 Dokument-Abschnitte** (≤1.900 Zeichen, Abschnitt = h2/h3-Überschrift), `valid_from` = „Stand“-Datum der Seite.
  Präfixe: Pflege (komplett), Menschen mit Behinderungen, Gesundheit, Hilfe & finanzielle Unterstützung (Sozialhilfe, Rezeptgebühr, Senioren-Ermäßigungen, Ombudsstellen …), Erwachsenenvertretung/Vorsorgevollmacht, Pension, Karenz/Mutterschutz, Krankenstand, ältere Arbeitnehmer, Familienbeihilfe, Kinderbetreuungsgeld, Geburt, Lebenslagen „Angehörige/finanzielle Unterstützung/Pension/Kind“.
  Nicht medizinisch relevante Teilbereiche (Sucht-Therapie, Geburtsurkunden etc.) sind mitgecrawlt, aber in `leistungen.jsonl` nicht abgebildet; Doc-Filter ggf. im Loader nach `url` einschränken.
- **22 Leistungs-Kandidaten** (`leistungen.jsonl`): pflegegeld, pflegekarenz, familienhospizkarenz, angehoerigenbonus, pflegende_angehoerige_versicherung, foerderung_24h_betreuung, alten_und_pflegeheim, soziale_dienste, sozialhilfe_wien, rezeptgebuehrenbefreiung, familienbeihilfe, kinderbetreuungsgeld, erwachsenenvertretung, vorsorgevollmacht, patientenverfuegung, behindertenpass, rehabilitation_sv, rehabilitationsgeld, krankenstand_fit2work, medizinische_versorgung_sv, elternkarenz_mutterschutz, pension_allgemein. Zuordnung kuratiert in `leistungen_config.json` (URL-/Titel-Regex); Felder (Voraussetzungen mit wörtlichem Zitat, Fristen, Kosten, Unterlagen, Antrag) werden **heuristisch aus Abschnittsüberschriften** extrahiert → `confidence: mittel`, Review nötig. `traeger`/`zielgruppe`/`kurz_einfach`/`abhaengigkeiten` teils manuell gesetzt.
- **63 Formulare** (`formulare.jsonl`): alle von den Themenseiten verlinkten (`linkresolution/form/N`), mit PDF-/Online-URL (43 PDF, 28 online/HTML), `fillable`, `alle_formate`. `felder` leer (PDFs nicht geladen/analysiert → Aufgabe für Formular-Session). 35 mit `leistung_ids` verknüpft.
- **13 Stellen** (`stellen.jsonl`): Bundesministerien (inkl. BMASGPK) aus `orgsearch/orgtyp/8` plus Pensions-/Unfallversicherungs-Listen von `/de/behoerden/*`.

## Lücken (ehrlich)
- „Zuständige Stelle“ steht auf oesterreich.gv.at meist nur als Rolle („Zuständiger Versicherungsträger“, „Finanzamt Österreich“) mit Link auf Behördenabfrage (`orggroup`, gemeindeabhängig) → **keine** konkreten Adressen/Öffnungszeiten für Sozialzentren, Bezirksgerichte, Sozialministeriumservice-Landesstellen, Erwachsenenschutzvereine. Die 7.337 `orgsearch/org/N`-Seiten wurden bewusst nicht gecrawlt (Massen-Crawl). Konkrete Wiener Stellen → Quellen `fsw`, `svs`, `oegk`.
- Nicht (eigenständig) vorhanden in der Sitemap: Behindertenpass-Detailseite, Patientenverfügung (nur über Patientenrechte), Mutter-Kind-/Eltern-Kind-Pass, Krankengeld/Rehabilitationsgeld als eigene Seiten (nur Kontext in Pension-und-Behinderung / ÖGK-Quelle). `krankenstand_fit2work` und `patientenverfuegung` sind deshalb dünn (`confidence` faktisch niedrig).
- Sozialhilfe: bundesweite Rahmenbeschreibung; **Wien-spezifische** Regeln (Sozialunterstützung/MA 40, Beträge) fehlen → Wien-Quelle nötig. `bundesland` daher `["AT"]`.
- Beträge (Pflegegeld-Stufen, Angehörigenbonus 134,30 €/Monat 2026 u. a.) stehen als Text in den Dokumenten, nicht strukturiert; Stand je Seite in `valid_from`.
- Externe Links (`linkresolution/link/N`, RIS-Rechtsgrundlagen) nicht aufgelöst.
- Es wurden keine PDFs heruntergeladen (`local_pdf: null`).

## Lizenz / Nachnutzung
Inhalte öffentlich zugänglich, Herausgeber Bundeskanzleramt / Digital Austria. Laut Impressum der Site CC BY 4.0 vermutet – **vor Veröffentlichung im Impressum (`/de/ueber-oesterreichgvat/impressum`) verifizieren**; jedenfalls Quelle „oesterreich.gv.at“ + URL + Abrufdatum angeben (steht in `license_note` jedes Dokuments). Für Hackathon-Nutzung unproblematisch. Medizinische/rechtliche Inhalte nur als zitierte Quelle verwenden; keine Beratung.

## Update-Strategie
Wöchentlich `ingest.py` laufen lassen; Änderungen erkennt man an `manifest.json` (`sha256` pro URL, `fetched_at` bleibt bei unverändertem Inhalt stehen). Neue Seiten kommen über die Sitemap automatisch, wenn sie unter `INCLUDE` fallen. Neue Leistungen: Eintrag in `leistungen_config.json`.
