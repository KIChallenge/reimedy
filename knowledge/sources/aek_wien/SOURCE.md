# Quelle `aek_wien` – Ärztekammer für Wien, Kassenseiten (www.aekwien.at)

**Stand:** 2026-11-05 · **Update:** `uv run knowledge/sources/aek_wien/ingest.py` (bedingtes GET + Hash über extrahierten Inhalt; zweiter Lauf ohne Änderungen → `changed=0`).

## Was die Seiten sind (ehrliche Einordnung)
Die Seiten https://www.aekwien.at/oegk und /bvaeb-svs sind **Ärzt:innen-Seiten** (Gesamtverträge, Zusatzprotokolle, Tarifkataloge, Honorar-/Abrechnungs-Formulare, Einspruch gegen Abrechnungen, EKO-Infotool). Es gibt dort **keine Patient:innen-Leistungsinfos** (keine Selbstbehalte, Anspruchsvoraussetzungen o. ä.). Für den Lotsen nützlich sind: Existenz/Aufbau des Kassenvertragssystems (Gesamtvertrag je Träger ÖGK/BVAEB/SVS/KFA Wien), Vorsorgeuntersuchung als Vertragsleistung (VU-Gesamtvertrag, Tarifkatalog, Anamnese-/Befundblätter), e-card-Grundlagen, Primärversorgungseinheiten (PVE Zentrum/Netzwerk), Wahlärzt:innen-Rahmen (Honorarnotenübermittlung an SV-Träger), KFA Wien als **eigenen** Träger für Wiener Gemeindebedienstete.

## Umfang
11 Seiten (beide Seeds + Tiefe 1: kfa-wien, punktewerte-krankenkassen, empfehlungstarife, primaerversorgung, e-card, vorsorgeuntersuchung, wahlarzt, formulare, digitalisierung) → ~95 Chunks; ~280 PDF-Verweise als `formulare.jsonl` (Titel + URL, `wer_fuellt_aus: arzt`, **PDFs nicht geladen**); 1 Stelle (Kammer-Zentrale); 1 schwacher Leistungs-Kandidat (`vorsorgeuntersuchung`, Confidence niedrig, nur als Vertragshinweis).
Ansprechpersonen-Kontaktblöcke (Mitarbeiter-Namen/Mails) wurden bewusst **nicht** übernommen; Navigationsmenüs entfernt.

## Lücken
Keine Tarif-/Honorarwerte (liegen in PDFs), keine Gesamtvertragstexte, keine Wahlarzt-Kostenerstattung für Patient:innen. Für Patient:innen-Fragen zu Selbstbehalten → `svs`, `bvaeb`, `oegk`.

## robots / Lizenz
robots.txt sperrt nur `/web/oak/`, `/c/portal/`; wir nutzen nur öffentliche Inhaltsseiten (≥1,1 s, UA `SV-Lotse-Hackathon/0.1`). Sidenote: © Ärztekammer für Wien, keine explizite Lizenz – für den Hackathon ignoriert.
