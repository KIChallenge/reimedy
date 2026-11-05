# Quelle `bvaeb` – Versicherungsanstalt öffentlich Bediensteter, Eisenbahnen und Bergbau (www.bvaeb.at)

**Stand:** 2026-11-05 · **Update:** `uv run knowledge/sources/bvaeb/ingest.py` (gleiche Mechanik wie `svs`; nutzt `../svs/_common.py` und `portal_ingest.py`; Leistungs-Specs in `leistungen_bvaeb.py`).

## Wie
- Gleicher SV-Portal-CMS (`portal=bvaebbportal`). BFS ab Startseite, Tiefe 3, **Cap 170 Seiten**, Themenfilter. Ergebnis: ca. 1.350 Dokument-Chunks, 15 Leistungs-Kandidaten (wörtliche Zitate, automatisch gewählt → Review nötig), ~185 Formular-Links (nicht geladen), 9 Stellen (alle Landesstellen/Außenstellen strukturiert: Adresse, Tel. 050405-xxxxx, Mail, Öffnungszeiten).
- `leistung_id`s: ÖGK-kompatibel (`pflegegeld`, `rezeptgebuehrenbefreiung`, `kur`, `reha_medizinisch`, `vorsorgeuntersuchung`, `krankentransport`, `heilbehelfe_hilfsmittel`, `wochengeld`, `krankengeld`) + BVAEB-spezifisch (`behandlungsbeitrag_bvaeb`, `kostenerstattung_wahlarzt`, `zahnbehandlung_zahnersatz`, `unterstuetzungsfonds_bvaeb`, `auslandsbehandlung_ekvk`, `unfall_heilbehandlung`).

## Abdeckung
A ✔ Vorsorgeuntersuchung/GuB, Impfungen, Präventionsberatung · B ✔ Jackpot.fit, Ernährung/Bewegung, Gesundheitsveranstaltungen, Gesundheitsförderung in Dienststellen · C ✔ Reha (med./beruflich/sozial, Kinder), Kur & Gesundheitsvorsorge Aktiv, Heilbehelfe & Kostenanteil, Zahn, Psycho-/Physio-/Ergotherapie, Fahrt-/Transportkosten, Medikamentenbewilligung · D ◐ Pflegegeld/Pflege zu Hause (kurz; Pflegegeld nach Arbeitsunfall) · E ✔ Krankengeld, Rehabilitationsgeld, Wochengeld, Unterstützungsfonds, Nachsicht/Befreiung · F ✔ e-card, EKVK, Landesstellen, Service-Zone (Formulare als Links).
Vertragspartner-Seiten (Abrechnung, ELDA, eKOS) wurden mitgecrawlt, sind für den Lotsen aber irrelevant (doc_type bleibt `leistungsinfo`; ggf. im Build per Titel herausfiltern).

## Träger-Unterschiede (belegt in den Docs)
- **Behandlungsbeitrag BVAEB = grundsätzlich 20 %** (Ordination/Visite, Diagnostik, Labor, Physio-/Psychotherapie, Zahnbehandlung/-ersatz …); Kinder und Waisenpensionsbezieher ausgenommen; Nachsicht nach Richtlinien. Eine Halbierung à la SVS „Selbständig Gesund“ gibt es bei der BVAEB **nicht** (kein entsprechendes Programm gefunden).
- Rezeptgebührenobergrenze: 2 % des Jahresnettoeinkommens (seit 1.1.2008); Transport: Kostenanteil in Höhe der Rezeptgebühr je Fahrt; Heilbehelfe: Kostenanteil 10 % (mind. Betrag lt. Seite); Kurkostenbeitrag-Beispiel EUR 25/Tag für 21 Tage; Kronenzuschuss 80 % max. EUR 200.
- Pflegegeld: Entscheidungsträger ist die BVAEB nur für ihre Pensionist:innen/Versicherten – sonst PVA/SVS.
- Kein Gesundheitshunderter bei der BVAEB (nur SVS).

## Lücken / Vorbehalte
- Cap 170: Portalbereiche (z. B. Pension, Dienstleistungsscheck) nur gestreift; einige Ernährungs-Blogartikel mitgecrawlt (Rauschen).
- PDFs/Formularfelder nicht ausgelesen. Keine Geo-Koordinaten. Zitate sind regex-selektiert (Wörtlichkeit geprüft, Relevanz nicht) → Review.
- Kärnten/Tirol/Vorarlberg-Landesstellen: soweit Seite sie führt (siehe stellen.jsonl).

## Lizenz / robots
`https://www.bvaeb.at/robots.txt` → HTTP 404 (keine Vorgaben). 1 Request/≥1,1 s, UA `SV-Lotse-Hackathon/0.1`, kein Login. © BVAEB; Kurzzitate mit Quellenangabe. Keine Open-Content-Lizenz erkennbar → Rücksprache für Produktivbetrieb.
