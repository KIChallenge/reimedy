# Quelle `oegk` – Österreichische Gesundheitskasse (www.oegk.at)

Stand Crawl: 2026-11-05. Ergebnis: 173 Seiten → 1.154 Dokument-Abschnitte (≤2.000 Zeichen), 48 Leistungs-Kandidaten, 115 Formulare/PDF-Verweise, 277 Stellen (26 Wiener Einrichtungen + 251 regionale Themen-Hotlines).

## Wichtige Erkenntnis zu den Seeds
Beide Seeds aus dem Challenge-Dokument sind **Vertragspartner-Seiten** (`portal=oegkvpportal`), nicht Versicherten-Seiten:
- `10007.879096` = „Gesamtverträge" (Ärzte-/Honorarverträge, PDFs) → nur als `recht`-Dokument aufgenommen (6 Abschnitte), keine Formulare.
- `10007.882122` = „Formulare und Drucksorten Wien" (Zuweisung/Verordnung, Fahrtkostenantrag, AU-Meldung, Psychotherapie-Zuschuss …) → Quelle der meisten `formulare.jsonl`-Einträge.

Die eigentlichen Versicherteninhalte liegen unter `portal=oegkportal` (Einstieg `10007.866742`). Deren **Sitemap** (`10007.907279`, 349 Links) wurde als Seitenverzeichnis genutzt; ausgewählt wurde themenbasiert (Liste `PAGES` in `ingest.py`, Tiefe praktisch 1, keine Link-Verfolgung).

## Technik / robots / Lizenz
- Seiten sind **serverseitig gerendert** (`/cdscontent/?contentid=…`), kein JS nötig; Hauptinhalt in `#esv-content_with_nav`. PDFs unter `/cdscontent/load?contentid=10008.…` (nur verlinkt, nicht geladen).
- `robots.txt`: `/robots.txt` liefert **404** (HTML-Fehlerseite) → keine Einschränkung. Trotzdem ≤1 Request/s (1,1 s), UA `SV-Lotse-Hackathon/0.1`, kein Login.
- Lizenz: keine offene Lizenz erkennbar; Inhalte © ÖGK. Nutzung nur mit Quellenangabe im Hackathon-Prototyp (`license_note` in jedem Dokument).
- **Inkrementell:** Der Server sendet für diese dynamischen Seiten **kein ETag/Last-Modified**; die Konditional-Header sind im Code vorbereitet, greifen aber nicht. Änderungserkennung daher über `sha256` des extrahierten Texts (`manifest.json`, `changed_at`). Ein Update lädt alle Seiten neu (~3,5 min). `--offline` baut alles aus `raw/` neu (deterministisch, getestet: identische Outputs).
- Aufruf: `uv run knowledge/sources/oegk/ingest.py [--offline] [--force]`.

## Abdeckung je Bereich (Dokumente)
| Bereich | Abschnitte | Inhalt |
|---|---|---|
| A Vorsorge | 62 | Vorsorgeuntersuchung (Gesundheits-Check), Krebs-Früherkennung (Brust/Darm/Haut/Prostata), Impfungen inkl. Kosten, Jugendlichenuntersuchung, Eltern-Kind-Pass |
| B Gesundheitsförderung | 179 | Bewegt im Park, Kurse/Rücken/Beckenboden, Rauchfrei/Nikotinfrei, Ernährung, easykids, Mentale Gesundheit, Sturzprävention, Selbsthilfe, fit2work |
| C Behandlung/Reha | 366 | Wahlarzt-Erstattung, Krankengeld, Reha-/Wiedereingliederungsgeld, Reha, Kur, Therapien (Physio/Ergo/Logo/Psychotherapie/klin. Psychologie), Heilbehelfe, Zahn/Zahnspange/Zahnersatz, Transportkosten, Gesundheitszentren Wien |
| D Pflege | 35 | Medizinische Hauskrankenpflege, Mit-/Selbstversicherung pflegender Angehöriger |
| E Sozial/Finanziell | 206 | Rezeptgebührenbefreiung, Wochengeld, Kinderbetreuungsgeld, Unterstützungsfonds |
| F Administration | 408 | Mit-/Selbstversicherung, e-card, Ausland, Vollmacht, Rechnung einreichen, Kundenservice, Versichertendaten, Formulare |

## Lücken / Vorsicht
- **Pflegegeld selbst ist nicht ÖGK**, sondern PVA/SVS/BVAEB (kommt hier nur als Bezug in der Versicherung pflegender Angehöriger vor) → muss aus PVA/SVS-Quellen kommen.
- **Rezeptgebührenbefreiung:** Richtsätze stehen im Text; der Antrag ist über Kundenservice/Meine ÖGK, ein eigenes PDF-Formular wurde nicht gefunden (`antrag.formular_id` null).
- **Brustkrebs-Früherkennung:** nur Informationsseiten, Details des Screening-Programms (Einladung, Altersgrenzen) teils unvollständig (`confidence: niedrig` für einige B/A-Kandidaten).
- Kundenservicestellen: nur **Wien** (12) vollständig mit Adresse/Telefon/E-Mail/Öffnungszeiten; andere Bundesländer nur über Hotlines. `geo` überall `null` (kein Geocoding).
- Gesundheitszentren/Physikalische Medizin/Zahngesundheitszentren nur Wien (14 Einrichtungen). Reha-Zentren-Listenseite wurde als Dokument, nicht als Stellen aufgenommen.
- Hotlines (`typ: hotline`) sind je Thema und Bundesland (aus dem Kontakt-Widget der Seite), mit `zustaendig_fuer` aus den Leistungs-Seiten; viele Duplikate je Region, aber unterschiedliche Rufnummern pro Thema.
- Formulare: `felder` leer, `fillable` unbekannt (PDFs nicht geladen); enthält neben Anträgen auch Informationsblätter/Fragebögen und Arzt-Formulare (`wer_fuellt_aus: arzt` per Namensheuristik).
- **Leistungs-Kandidaten sind heuristisch:** `voraussetzungen`/`unterlagen`/`fristen`/`kosten`/`zustaendig` sind **wörtliche Sätze**, die per Schlüsselwort ausgewählt wurden – teils unpassend (z. B. Fristen-Treffer ohne Frist). Mensch-Review nötig. `kurz_einfach` ist der wörtliche Einleitungssatz, noch nicht in einfache Sprache übertragen; `zielgruppe` leer.
- Nicht aufgenommen: Rezepte, Vereinscoaching, BGF/Schule/Betriebe, Presse/Organisation, regionale Listenseiten der Zahngesundheitszentren außerhalb Wiens, Dienstgeber-Portal.
- Seiten enthalten auch tagesaktuelle Hinweise (z. B. Krankengeld-Auszahlung); `valid_from` ist überall `null`.

## Harte Grenze
Medizinische Texte (Früherkennung, Therapien) sind reine Leistungsinfo mit Quelle; nichts davon als Empfehlung oder Interpretation verwenden.
