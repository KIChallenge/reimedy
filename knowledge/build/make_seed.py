#!/usr/bin/env python3
"""Kuratierter Seed-Leistungsgraph für die 4 Jury-Szenarien → seed_leistungen.jsonl, seed_stellen.jsonl, seed_formulare.jsonl.

Regeln für den Seed (das ist der „geprüfte Cache"):
- Jede Voraussetzung mit Quelle (+ wörtlichem Zitat, wo vorhanden). Beträge NUR aus belegten Quellen (ÖGK-Broschüre 2026).
- confidence: hoch = wörtlich aus Quelle mit Seite · mittel = aus Allgemeinwissen, Quelle verlinkt, aber nicht wörtlich geprüft
  · niedrig = Zuständigkeit/Details unklar → Lotse muss vorsichtig formulieren.
- Keine medizinische Bewertung. Leistungen beschreiben Organisatorisches (wer, was, welcher Antrag).
Menschen editieren DIESE Datei, nicht die JSONL.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
BRO = "_Source/Leistungskataloge/Serviceratgeber-2026_Broschuere_A5_OEAM_99-19_klein_korr.pdf"
ENTL = "_Source/Befunde/Entlassungsbefund.pdf"


def bro(page):
    return {"url": f"{BRO}#page={page}", "stand": "2026-01-01", "titel": "ÖGK – Leistungen und Services 2026 (SV-Box)"}


def web(url, stand="2026-11-05"):
    return {"url": url, "stand": stand}


def V(text, q=None, zitat=None):
    d = {"text": text}
    if q:
        d["quelle_url"] = q["url"]
    if zitat:
        d["zitat"] = zitat
    return d


L = []


def leistung(**kw):
    kw.setdefault("bundesland", ["AT"])
    kw.setdefault("abhaengigkeiten", [])
    kw.setdefault("confidence", "mittel")
    L.append(kw)


# ---------------------------------------------------------------- D Pflege
leistung(leistung_id="pflegegeld", name="Pflegegeld",
         kurz_einfach="Geld als Unterstützung, wenn jemand dauerhaft Hilfe und Pflege braucht. Die Höhe hängt davon ab, wie viele Stunden Pflege pro Monat nötig sind (7 Stufen).",
         bereich=["D", "E"], traeger=["PVA", "SVS", "BVAEB", "AUVA"], innerhalb_sv=True,
         zielgruppe="Menschen mit voraussichtlich mindestens 6 Monate dauerndem Pflegebedarf; Antrag oft durch Angehörige vorbereitet",
         voraussetzungen=[V("Pflegebedarf von mehr als 65 Stunden pro Monat (Stufe 1)", web("https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=10008859")),
                          V("Pflegebedarf voraussichtlich mindestens 6 Monate", web("https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=10008859")),
                          V("Kein automatischer Anspruch durch eine Diagnose", {"url": ENTL + "#page=6"},
                            "Ein Anspruch ist nicht automatisch durch die Krebserkrankung gegeben")],
         zustaendig="Der Träger, der die Pension auszahlt (ASVG-Pension → PVA; SVS-Pension → SVS; Beamte → BVAEB). Ohne Pension: meist PVA. Entscheidung per Bescheid nach Begutachtung.",
         antrag={"formular_id": "pva_pal080", "wo": "Pensionsversicherungsanstalt (Landesstelle) bzw. eigener Pensionsträger; formlos oder Formular PAL080", "online_url": "https://www.pv.at"},
         unterlagen=["ausgefülltes Antragsformular", "aktuelle Befunde/Entlassungsbrief (zur Begutachtung)", "Bankverbindung", "ggf. Vollmacht/Erwachsenenvertretung"],
         fristen=["Pflegegeld gebührt ab dem Monat nach Antragstellung → früh beantragen"],
         kosten="kostenlos", abhaengigkeiten=[],
         trigger_im_dokument=["Pflegegeld", "Pflegebedarf", "Unterstützungsbedarf", "Pflegegeldanspruch prüfen"],
         quellen=[web("https://www.pv.at"), {"url": "_Source/Anträge und Formulare/PAL080_0125_Mpfl_052026.pdf", "stand": "2025-01-01"}, {"url": ENTL + "#page=6", "stand": "2026-10"}],
         confidence="mittel")
leistung(leistung_id="mobile_pflege_fsw", name="Mobile Pflege und Betreuung zu Hause (Wien, FSW)",
         kurz_einfach="Heimhilfe und Hauskrankenpflege kommen nach Hause. In Wien organisiert und fördert das der Fonds Soziales Wien (FSW).",
         bereich=["D"], traeger=["FSW"], innerhalb_sv=False, bundesland=["W"],
         zielgruppe="Menschen in Wien, die zu Hause Unterstützung bei Pflege oder Alltag brauchen",
         voraussetzungen=[V("Hauptwohnsitz in Wien"), V("Pflege-/Betreuungsbedarf; Kostenbeitrag nach Einkommen und Pflegegeld")],
         zustaendig="Fonds Soziales Wien – Beratungszentrum Pflege und Betreuung (Tel. 01 24 5 24)",
         antrag={"formular_id": "fsw_antrag_foerderung", "wo": "FSW Beratungszentrum Pflege und Betreuung", "online_url": "https://www.fsw.at"},
         unterlagen=["Antrag auf Förderung von Leistungen", "Einkommensnachweise", "Pflegegeldbescheid (falls vorhanden)"],
         fristen=[], kosten="Kostenbeitrag abhängig von Einkommen und Pflegegeld",
         abhaengigkeiten=[], trigger_im_dokument=["mobile Hauskrankenpflege", "mobile Pflege", "Heimhilfe", "soziale Dienste", "Alltagshilfen"],
         quellen=[web("https://www.fsw.at"), {"url": "_Source/Anträge und Formulare/fsw-antrag-auf-foerderung-von-leistungen.1779095804.pdf", "stand": "2026-03"}, {"url": ENTL + "#page=6", "stand": "2026-10"}],
         confidence="mittel")
leistung(leistung_id="senior_innen_wg_fsw", name="Senior:innen-Wohngemeinschaft (Wien, FSW)",
         kurz_einfach="Gemeinsam wohnen mit Betreuung, wenn allein wohnen nicht mehr gut geht, ein Pflegeheim aber noch nicht nötig ist.",
         bereich=["D"], traeger=["FSW"], innerhalb_sv=False, bundesland=["W"],
         zustaendig="FSW Beratungszentrum Pflege und Betreuung, Guglgasse 7–9, 1030 Wien",
         antrag={"formular_id": "fsw_bedarfsmeldung_wg", "wo": "FSW Beratungszentrum"},
         trigger_im_dokument=["lebt allein", "Wohngemeinschaft"],
         quellen=[{"url": "_Source/Anträge und Formulare/Bedarfsmeldung-Senior_innen-Wohngemeinschaft_Basispaket.1736522017.pdf", "stand": "2024-12"}],
         confidence="mittel")
leistung(leistung_id="wohn_pflegehaus_fsw", name="Wohn- und Pflegehaus (Wien, FSW)",
         kurz_einfach="Ein Platz in einem Wohn- oder Pflegehaus, gefördert vom FSW. Man kann Wunsch-Einrichtungen angeben.",
         bereich=["D"], traeger=["FSW"], innerhalb_sv=False, bundesland=["W"],
         zustaendig="FSW Beratungszentrum Pflege und Betreuung",
         antrag={"formular_id": "fsw_einrichtungswunsch", "wo": "Beilage zum FSW-Förderantrag"},
         abhaengigkeiten=["mobile_pflege_fsw"], trigger_im_dokument=["Pflegeheim", "stationäre Pflege"],
         quellen=[{"url": "_Source/Anträge und Formulare/FSW-Antrag-Beilage-Einrichtungswunsch.1779345450.pdf", "stand": "2026-05"}],
         confidence="mittel")
leistung(leistung_id="pflegekarenz", name="Pflegekarenz / Pflegeteilzeit und Pflegekarenzgeld",
         kurz_einfach="Angehörige können sich für die Pflege eine Zeit lang von der Arbeit freistellen lassen und bekommen Pflegekarenzgeld.",
         bereich=["D", "E"], traeger=["Sozialministeriumservice"], innerhalb_sv=False,
         zielgruppe="Berufstätige Angehörige einer Person mit Pflegegeld (in der Regel ab Stufe 3)",
         voraussetzungen=[V("Vereinbarung mit dem Arbeitgeber"), V("Pflegebedürftige Person bezieht Pflegegeld (meist ab Stufe 3)")],
         zustaendig="Sozialministeriumservice (Pflegekarenzgeld)", abhaengigkeiten=["pflegegeld"],
         trigger_im_dokument=["Angehörige", "pflegende Angehörige"],
         quellen=[web("https://www.oesterreich.gv.at"), web("https://www.sozialministeriumservice.gv.at")], confidence="niedrig")
leistung(leistung_id="familienhospizkarenz", name="Familienhospizkarenz",
         kurz_einfach="Freistellung von der Arbeit, um schwerst erkrankte nahe Angehörige oder Kinder zu begleiten.",
         bereich=["D", "E"], traeger=["Sozialministeriumservice"], innerhalb_sv=False,
         zustaendig="Arbeitgeber (Meldung) + Sozialministeriumservice (Pflegekarenzgeld)",
         trigger_im_dokument=["palliativ", "Sterbebegleitung"],
         quellen=[web("https://www.oesterreich.gv.at")], confidence="niedrig")

# ---------------------------------------------------------------- E Finanziell
leistung(leistung_id="rezeptgebuehrenbefreiung", name="Befreiung von der Rezeptgebühr",
         kurz_einfach="Bei kleinem Einkommen muss man für Medikamente auf Rezept die Rezeptgebühr (7,55 € pro Packung) nicht zahlen. Für manche Gruppen gilt das automatisch, sonst per Antrag.",
         bereich=["E"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True,
         zielgruppe="Personen mit geringem Einkommen, Ausgleichszulagen-Bezieher:innen, Personen mit hohen krankheitsbedingten Ausgaben",
         voraussetzungen=[V("Ohne Antrag u. a. für Bezieher:innen einer Ausgleichszulage oder Sozialhilfe/Mindestsicherung", bro(22),
                            "Bezieherinnen und Bezieher einer Ausgleichszulage"),
                          V("Mit Antrag: monatliches Nettoeinkommen bis 1.308,39 € (alleinstehend) bzw. 2.064,12 € (Paare)", bro(22),
                            "1.308,39 Euro (für Alleinstehende)"),
                          V("Mit Antrag bei überdurchschnittlichen krankheitsbedingten Ausgaben: bis 1.504,65 € (alleinstehend) bzw. 2.373,74 € (Paare)", bro(22),
                            "1.504,65 Euro (für Alleinstehende)"),
                          V("Automatische Befreiung für den Rest des Jahres, wenn Rezeptgebühren 2 % des Jahresnettoeinkommens erreichen (Obergrenze)", bro(23),
                            "im Kalenderjahr 2026 2 Prozent des Jahresnettoeinkommens erreicht")],
         zustaendig="Die eigene Krankenkasse (für Pensionist:innen in Wien meist ÖGK)",
         antrag={"formular_id": None, "wo": "ÖGK-Kundenservice oder Meine ÖGK"},
         unterlagen=["Einkommensnachweise (Pension, sonstige Einkünfte)", "Nachweis über Einkommen im gemeinsamen Haushalt"],
         fristen=["Obergrenzen-Befreiung endet immer am 31.12."], kosten="Rezeptgebühr 2026: 7,55 € pro Packung",
         abhaengigkeiten=[], trigger_im_dokument=["Rezeptgebührenbefreiung", "Rezeptgebühr", "finanzielle Situation"],
         quellen=[bro(22), bro(23)], confidence="hoch")
leistung(leistung_id="fahrtkostenzuschuss", name="Zuschuss zu Fahrtkosten (ÖGK Wien)",
         kurz_einfach="Wer von der Rezeptgebühr befreit ist, kann für Fahrten zu bestimmten Behandlungen einen Zuschuss bekommen.",
         bereich=["E", "C"], traeger=["ÖGK"], innerhalb_sv=True, bundesland=["W"],
         voraussetzungen=[V("Bestehende Rezeptgebührenbefreiung", {"url": "_Source/Anträge und Formulare/Antrag-auf-Zuschuss-zu-Fahrtkosten_Wien.pdf"},
                            "für Versicherte mit Rezeptgebührenbefreiung")],
         zustaendig="ÖGK", antrag={"formular_id": "oegk_fahrtkosten_wien", "wo": "ÖGK-Kundenservice Wien"},
         unterlagen=["Tabelle der Fahrten (Datum, Behandlungsort)", "Bestätigung der Behandlungen"],
         abhaengigkeiten=["rezeptgebuehrenbefreiung"],
         trigger_im_dokument=["Fahrten zu notwendigen Behandlungsterminen", "Fahrtmöglichkeiten", "Bestrahlung"],
         quellen=[{"url": "_Source/Anträge und Formulare/Antrag-auf-Zuschuss-zu-Fahrtkosten_Wien.pdf", "stand": "2026"}], confidence="hoch")
leistung(leistung_id="krankentransport", name="Krankentransport / Krankenbeförderung",
         kurz_einfach="Wenn jemand wegen der Gesundheit nicht selbst zur Behandlung kommen kann, zahlt die Kasse Transport oder Taxi – mit ärztlicher Transportanweisung.",
         bereich=["C", "E"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True,
         voraussetzungen=[V("Ärztliche Transportanweisung über die Gehunfähigkeit", bro(32), "wenn eine ärztliche Transportanweisung über die Gehunfähigkeit des Versicherten"),
                          V("Fehlendes öffentliches Verkehrsmittel oder Begleitperson allein reicht nicht", bro(32), "begründet keine Kostenübernahme"),
                          V("Kein Selbstbehalt bei Fahrten zu Dialyse-, Chemo-, Strahlen- oder Immuntherapien und bei Rezeptgebührenbefreiung", bro(33),
                            "Fahrten zu Dialyse-, Chemo-, Strahlen- oder Immuntherapien wird kein Kostenanteil eingehoben")],
         zustaendig="Behandelnde Ärztin/Arzt stellt Transportanweisung aus; Kasse zahlt Vertragstarif",
         antrag={"formular_id": None, "wo": "Transportanweisung durch Ärztin/Arzt"},
         kosten="Selbstbehalt 7,55 € pro Fahrtstrecke (Taxi/Fahrtendienst), 15,10 € bei sanitätsdienstlicher Begleitung; Ausnahmen siehe Voraussetzungen",
         abhaengigkeiten=[], trigger_im_dokument=["Transport", "Bestrahlungstermine", "Transportleistung", "eingeschränkte Mobilität"],
         quellen=[bro(32), bro(33)], confidence="hoch")
leistung(leistung_id="sozialhilfe_wien", name="Wiener Mindestsicherung (Sozialhilfe)",
         kurz_einfach="Geld zum Leben für Menschen in Wien, deren Einkommen nicht reicht. Wer sie bekommt, ist auch von der Rezeptgebühr befreit.",
         bereich=["E"], traeger=["Stadt Wien – MA 40"], innerhalb_sv=False, bundesland=["W"],
         zustaendig="Stadt Wien, Magistratsabteilung 40 (Soziales)",
         trigger_im_dokument=["finanzielle Situation", "Einkommen"],
         quellen=[web("https://www.wien.gv.at")], confidence="niedrig")
leistung(leistung_id="ausgleichszulage", name="Ausgleichszulage zur Pension",
         kurz_einfach="Wenn die Pension sehr niedrig ist, wird sie auf einen Mindestbetrag aufgestockt. Dann gilt auch die Rezeptgebührenbefreiung automatisch.",
         bereich=["E"], traeger=["PVA", "SVS", "BVAEB"], innerhalb_sv=True,
         zustaendig="Der Pensionsversicherungsträger, der die Pension auszahlt",
         quellen=[bro(22), web("https://www.pv.at")], confidence="mittel")
leistung(leistung_id="familienbeihilfe", name="Familienbeihilfe",
         kurz_einfach="Monatliches Geld für Eltern mit Kindern. Sie ist auch wichtig für die Mitversicherung älterer Kinder.",
         bereich=["E"], traeger=["Finanzamt"], innerhalb_sv=False,
         zustaendig="Finanzamt Österreich (meist automatisch nach Geburt)",
         trigger_im_dokument=["Kind", "Familienbeihilfe"], quellen=[bro(4), web("https://www.oesterreich.gv.at")], confidence="mittel")
leistung(leistung_id="mitversicherung_angehoerige", name="Mitversicherung von Angehörigen",
         kurz_einfach="Kinder und unter bestimmten Bedingungen Partner:innen sind bei der versicherten Person kostenlos mitversichert.",
         bereich=["F"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True,
         voraussetzungen=[V("Kinder grundsätzlich bis zur Volljährigkeit, länger bei Ausbildung und Familienbeihilfe", bro(4))],
         zustaendig="Krankenkasse der versicherten Person", quellen=[bro(4), bro(5)], confidence="hoch")

# ---------------------------------------------------------------- C Behandlung/Reha
leistung(leistung_id="reha_onkologisch", name="Onkologische Rehabilitation",
         kurz_einfach="Ein Reha-Aufenthalt nach einer Krebsbehandlung, damit man wieder möglichst selbstständig leben kann. Muss vorher beantragt und ärztlich begründet werden.",
         bereich=["C"], traeger=["PVA", "ÖGK"], innerhalb_sv=True,
         voraussetzungen=[V("Antrag im Vorhinein + medizinische Begründung der behandelnden Ärztin", bro(25),
                            "Die angeführten Leistungen müssen Sie im Vorhinein beantragen"),
                          V("Bewilligung und Wahl der Einrichtung durch den Kostenträger", {"url": ENTL + "#page=5"},
                            "Die endgültige Entscheidung über die Bewilligung und die geeignete Einrichtung trifft der zuständige Kostenträger")],
         zustaendig="Je nach Versichertenstatus Pensions- oder Krankenversicherung – im Entlassungsbrief ausdrücklich offen („zuständige Sozialversicherung zu klären“). Gemeinsames Antragsformular.",
         antrag={"formular_id": "antrag_reha_kur", "wo": "über Hausärztin/Facharzt einreichen"},
         unterlagen=["Antrag auf Rehabilitations-, Kur- bzw. Erholungsaufenthalt", "ärztliche Begründung", "relevante Befunde/Entlassungsbrief"],
         fristen=["laut Entlassungsbrief: nach Abschluss der Bestrahlung prüfen"],
         abhaengigkeiten=[], trigger_im_dokument=["onkologische Rehabilitation", "Rehabilitationsantrag", "rehabilitative Maßnahme"],
         quellen=[bro(25), {"url": ENTL + "#page=5", "stand": "2026-10"}], confidence="mittel")
leistung(leistung_id="anschlussheilverfahren", name="Anschlussheilverfahren / Reha nach Unfall",
         kurz_einfach="Reha direkt im Anschluss an den Spitalsaufenthalt. Den Antrag stellt das Krankenhaus.",
         bereich=["C"], traeger=["PVA", "ÖGK", "AUVA"], innerhalb_sv=True,
         zustaendig="Antrag durch das Krankenhaus an den zuständigen Kranken- bzw. Pensionsversicherungsträger",
         antrag={"formular_id": "antrag_ahv_reha_unfall", "wo": "vom Krankenhaus auszufüllen"},
         trigger_im_dokument=["Anschlussheilverfahren", "AHV"],
         quellen=[{"url": "_Source/Anträge und Formulare/Reha_n_Unfall_052026.pdf", "stand": "2026-05"}], confidence="mittel")
leistung(leistung_id="kur", name="Kur- und Erholungsaufenthalt",
         kurz_einfach="Ein Kuraufenthalt zur Festigung der Gesundheit. Freiwillige Leistung der Kasse, muss vorher beantragt und ärztlich begründet werden.",
         bereich=["C", "B"], traeger=["ÖGK", "PVA", "SVS", "BVAEB"], innerhalb_sv=True,
         voraussetzungen=[V("Antrag im Vorhinein, ärztlich begründet", bro(32), "im Vorhinein von der Versicherten bzw. von dem Versicherten zu beantragen"),
                          V("Freiwillige Leistung (kein Rechtsanspruch)", bro(32), "Es handelt sich dabei um freiwillige Leistungen")],
         zustaendig="ÖGK prüft und bewilligt (bei Erwerbstätigen oft PVA)", antrag={"formular_id": "antrag_reha_kur"},
         kosten="Zuzahlung nach Einkommen", quellen=[bro(32)], confidence="hoch")
leistung(leistung_id="heilbehelfe_hilfsmittel", name="Heilbehelfe und Hilfsmittel",
         kurz_einfach="Brillen, Einlagen, Kompressionsstrümpfe, Rollstuhl, Pflegebett: Die Kasse zahlt mit ärztlicher Verordnung bis zu Höchstbeträgen.",
         bereich=["C", "D"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True,
         voraussetzungen=[V("Ärztliche Verordnung", bro(23), "Diese werden über ärztliche Verordnung gewährt")],
         zustaendig="Krankenkasse; manche Hilfsmittel (z. B. Krankenfahrstuhl) leihweise",
         kosten="Kostenübernahme bis 1.848,00 € (Prothesen/Rollstühle 4.620,00 €); Selbstbehalt orthopädische Maßschuhe 77,03 €",
         trigger_im_dokument=["Gehhilfe", "Rollator", "Hilfsmittel", "eingeschränkte Mobilität", "Pflegebett"],
         quellen=[bro(23), bro(24)], confidence="hoch")
leistung(leistung_id="hausarzt_pve", name="Hausärztin / Primärversorgungseinheit (PVE)",
         kurz_einfach="Erste Anlaufstelle für Kontrollen, Überweisungen, Verordnungen und ärztliche Begründungen für Anträge.",
         bereich=["C", "F"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True,
         zustaendig="Vertragsärztin für Allgemeinmedizin oder PVE in der Nähe; Termin selbst vereinbaren",
         trigger_im_dokument=["hausärztliche Kontrolle", "Hausärztin", "Hausarzt", "Medikationsplan abstimmen"],
         quellen=[web("https://www.gesundheit.gv.at")], confidence="mittel")
leistung(leistung_id="gesundheitsberatung_1450", name="Gesundheitsberatung 1450",
         kurz_einfach="Unter 1450 (ohne Vorwahl) beraten diplomierte Pflegekräfte am Telefon und sagen, wohin man mit einem Gesundheitsproblem gehen soll. Bei Lebensgefahr: 144.",
         bereich=["C", "F"], traeger=["Bund", "Länder", "Sozialversicherung"], innerhalb_sv=True,
         voraussetzungen=[V("Rund um die Uhr, 365 Tage, ohne Vorwahl", bro(42), "Rufen Sie die Nummer 1450 ohne Vorwahl")],
         zustaendig="1450 (Gemeinschaftsprojekt Bund, Länder, SV)", kosten="kostenlos",
         trigger_im_dokument=["Beschwerden", "Verschlechterung"], quellen=[bro(42)], confidence="hoch")

# ---------------------------------------------------------------- A Vorsorge / B Gesundheitsförderung
leistung(leistung_id="vorsorgeuntersuchung", name="Vorsorgeuntersuchung (Gesundheits-Check)",
         kurz_einfach="Ein kostenloser Gesundheits-Check für alle ab 18 Jahren, meist bei der Hausärztin.",
         bereich=["A"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True,
         voraussetzungen=[V("Ab 18 Jahren, kostenlos", bro(12), "lädt Personen ab 18 Jahren ein, zur kostenlosen Vorsorgeuntersuchung")],
         zustaendig="Hausärztin, Gesundheitseinrichtungen der SV, Wahlärzt:innen mit VU-Vertrag", kosten="kostenlos",
         fristen=["jährlich möglich"], trigger_im_dokument=["Vorsorge", "Gesundheits-Check"], quellen=[bro(12)], confidence="hoch")
leistung(leistung_id="brustkrebs_frueherkennung", name="Brustkrebs-Früherkennungsprogramm „früh erkennen“",
         kurz_einfach="Mammografie im Rahmen des österreichischen Früherkennungsprogramms an rund 170 Standorten. Ob und wann, bespricht man mit der Ärztin.",
         bereich=["A"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True,
         zustaendig="Programm „früh erkennen“; Radiologie-Standorte im Programm",
         quellen=[bro(13), web("https://www.frueh-erkennen.at")], confidence="mittel")
leistung(leistung_id="impfungen_erwachsene", name="Impfprogramme für Erwachsene",
         kurz_einfach="Manche Impfungen für Erwachsene sind gratis (z. B. Grippe, COVID-19; ab 60 Gürtelrose und Pneumokokken). Andere zahlt man selbst; für FSME gibt es einen Zuschuss. Ob eine Impfung passt, entscheidet die Ärztin.",
         bereich=["A"], traeger=["ÖGK", "Bund", "Länder"], innerhalb_sv=True,
         voraussetzungen=[V("Erwachsenenimpfungen großteils privat; kostenlose Programme u. a. Influenza, COVID-19, ab 60 Gürtelrose und Pneumokokken", bro(17),
                            "Impfungen für Erwachsene sind in Österreich großteils privat zu bezahlen")],
         zustaendig="Ärztin/Arzt; Impfprogramme von Bund/Ländern/SV", trigger_im_dokument=["Impfung", "Impfpass"],
         quellen=[bro(17)], confidence="hoch")
leistung(leistung_id="kinderimpfprogramm", name="Kostenloses Kinderimpfprogramm",
         kurz_einfach="Für Kinder gibt es ein umfangreiches kostenloses Impfangebot. Den Plan bespricht man mit Kinderärztin oder Hausarzt.",
         bereich=["A"], traeger=["Bund", "Länder", "Sozialversicherung"], innerhalb_sv=True,
         quellen=[bro(17), web("https://www.sozialministerium.at")], confidence="mittel")
leistung(leistung_id="eltern_kind_pass", name="Eltern-Kind-Pass-Untersuchungen",
         kurz_einfach="Kostenlose Untersuchungen in Schwangerschaft und für Kinder. Wer die vorgeschriebenen Untersuchungen nicht nachweist, bekommt weniger Kinderbetreuungsgeld.",
         bereich=["A", "E"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True,
         voraussetzungen=[V("Zehn vorgeschriebene Untersuchungen rechtzeitig durchführen und nachweisen", bro(38),
                            "Werden die zehn vorgeschriebenen Eltern-Kind-Pass-Untersuchungen nicht rechtzeitig durchgeführt")],
         kosten="kostenlos; sonst Kürzung Kinderbetreuungsgeld um 1.300,00 € je Elternteil",
         fristen=["Untersuchungen in vorgeschriebenen Zeiträumen"], quellen=[bro(38)], confidence="hoch")
leistung(leistung_id="zahnspange_kfo", name="Zahnspange / Kieferorthopädie für Kinder („Gratis-Zahnspange“)",
         kurz_einfach="Bei medizinischer Notwendigkeit zahlt die ÖGK eine Zahnspange für Kinder und Jugendliche. Ob sie nötig ist, stellt die Kieferorthopädin fest; der Therapievorschlag muss bewilligt werden.",
         bereich=["C"], traeger=["ÖGK"], innerhalb_sv=True,
         voraussetzungen=[V("Therapievorschlag wird eingereicht und vom Zahnmedizinischen Dienst bewilligt", bro(39),
                            "dass der Therapievorschlag eingereicht und vom Zahnmedizinischen Dienst der ÖGK bewilligt wird"),
                          V("„Gratis-Zahnspange“ nur bei medizinischer Notwendigkeit", bro(39), "wird von der ÖGK bei medizinischer Notwendigkeit bezahlt")],
         zustaendig="Vertrags-Kieferorthopädin reicht ein; ÖGK bewilligt", trigger_im_dokument=["Zahnfehlstellung", "Zahnspange"],
         quellen=[bro(39), {"url": "_Source/Leistungskataloge/Zahnärzte Honorarordnung_2026_aktuellste_Version_MAI_070526.pdf", "stand": "2026-05"}],
         confidence="hoch")
leistung(leistung_id="mundhygiene_kinder", name="Gratis-Mundhygiene für Kinder und Jugendliche",
         kurz_einfach="Für 10- bis 18-Jährige zahlt die ÖGK einmal im Jahr die Mundhygiene, mit fester Zahnspange zweimal.",
         bereich=["A", "B"], traeger=["ÖGK"], innerhalb_sv=True,
         voraussetzungen=[V("Vollendetes 10. bis vollendetes 18. Lebensjahr, 1× pro Jahr (mind. 12 Monate Abstand)", bro(41),
                            "zwischen dem vollendeten 10. Lebensjahr und dem vollendeten 18. Lebensjahr"),
                          V("2× pro Jahr bei festsitzender Zahnspange (mind. 6 Monate Abstand)", bro(41))],
         zustaendig="Vertragszahnärzt:innen, Zahngesundheitszentren der ÖGK; Wahlzahnarzt: 80 % Kostenerstattung",
         kosten="kostenlos bei Vertragspartnern", abhaengigkeiten=[], quellen=[bro(41)], confidence="hoch")
leistung(leistung_id="bewegt_im_park", name="Bewegt im Park",
         kurz_einfach="Kostenlose Bewegungskurse im Freien im Sommer, ohne Anmeldung, in ganz Österreich.",
         bereich=["B"], traeger=["Sozialversicherung", "Sportunion/ASKÖ/ASVÖ"], innerhalb_sv=True,
         quellen=[web("https://www.bewegt-im-park.at")], confidence="niedrig")
leistung(leistung_id="gesundheitshunderter_svs", name="Gesundheitshunderter (SVS)",
         kurz_einfach="SVS-Versicherte bekommen einmal im Jahr bis zu 100 € zurück, wenn sie z. B. einen Kurs zu Bewegung oder Ernährung machen.",
         bereich=["B"], traeger=["SVS"], innerhalb_sv=True, zielgruppe="SVS-Versicherte (Selbstständige, Bäuerinnen/Bauern)",
         zustaendig="SVS (Einreichung z. B. über svsGO)", quellen=[web("https://www.svs.at")], confidence="niedrig")
leistung(leistung_id="selbstaendig_gesund_svs", name="Selbständig Gesund (SVS)",
         kurz_einfach="SVS-Versicherte, die Gesundheitsziele mit der Ärztin vereinbaren und erreichen, zahlen weniger Selbstbehalt (10 % statt 20 %).",
         bereich=["B", "E"], traeger=["SVS"], innerhalb_sv=True, abhaengigkeiten=["vorsorgeuntersuchung"],
         zustaendig="SVS", quellen=[web("https://www.svs.at")], confidence="niedrig")

# ---------------------------------------------------------------- F Administration
leistung(leistung_id="erwachsenenvertretung_vollmacht", name="Vorsorgevollmacht / Erwachsenenvertretung",
         kurz_einfach="Damit Angehörige rechtlich für jemanden handeln dürfen, braucht es eine Vollmacht oder eine Erwachsenenvertretung.",
         bereich=["F"], traeger=["Notar/Anwalt/Erwachsenenschutzverein"], innerhalb_sv=False,
         zustaendig="Notariat, Rechtsanwält:in oder Erwachsenenschutzverein; Eintrag im ÖZVV",
         trigger_im_dokument=["Vertrauensperson", "Angehörige", "Unterstützung bei der Antragstellung"],
         quellen=[web("https://www.oesterreich.gv.at")], confidence="niedrig")

# ---------------------------------------------------------------- Stellen
STELLEN = [
    {"stelle_id": "notruf_144", "name": "Rettung (Notruf)", "typ": "hotline", "telefon": "144", "bundesland": "AT",
     "zustaendig_fuer": [], "quelle_url": "https://www.gesundheit.gv.at", "oeffnungszeiten": "24/7"},
    {"stelle_id": "hotline_1450", "name": "Gesundheitsberatung 1450", "typ": "hotline", "telefon": "1450", "bundesland": "AT",
     "oeffnungszeiten": "24/7, 365 Tage", "zustaendig_fuer": ["gesundheitsberatung_1450"], "quelle_url": BRO + "#page=42"},
    {"stelle_id": "fsw_beratungszentrum_pflege", "name": "FSW Beratungszentrum Pflege und Betreuung", "typ": "beratung",
     "adresse": "Guglgasse 7–9, 1030 Wien", "plz": "1030", "bundesland": "W", "telefon": "01 24 5 24", "url": "https://www.fsw.at",
     "zustaendig_fuer": ["mobile_pflege_fsw", "senior_innen_wg_fsw", "wohn_pflegehaus_fsw"],
     "quelle_url": "_Source/Anträge und Formulare/Bedarfsmeldung-Senior_innen-Wohngemeinschaft_Basispaket.1736522017.pdf"},
    {"stelle_id": "pva_hauptstelle", "name": "Pensionsversicherungsanstalt – Hauptstelle", "typ": "traeger",
     "adresse": "Friedrich-Hillegeist-Straße 1, 1020 Wien", "plz": "1020", "bundesland": "W", "url": "https://www.pv.at",
     "zustaendig_fuer": ["pflegegeld", "reha_onkologisch", "ausgleichszulage"],
     "quelle_url": "_Source/Anträge und Formulare/PAL080_0125_Mpfl_052026.pdf"},
    {"stelle_id": "oegk_kundenservice", "name": "ÖGK Kundenservice", "typ": "traeger", "bundesland": "AT", "url": "https://www.oegk.at",
     "zustaendig_fuer": ["rezeptgebuehrenbefreiung", "fahrtkostenzuschuss", "kur", "heilbehelfe_hilfsmittel", "mitversicherung_angehoerige"],
     "quelle_url": "https://www.oegk.at"},
    {"stelle_id": "svs_kundenservice", "name": "SVS Kundenservice / svsGO", "typ": "traeger", "bundesland": "AT", "url": "https://www.svs.at",
     "zustaendig_fuer": ["gesundheitshunderter_svs", "selbstaendig_gesund_svs"], "quelle_url": "https://www.svs.at"},
]

FORMULARE = [
    {"formular_id": "pva_pal080", "name": "Antrag auf Pflegegeld (PAL 080)", "traeger": "PVA",
     "local_pdf": "_Source/Anträge und Formulare/PAL080_0125_Mpfl_052026.pdf", "fillable": True, "leistung_ids": ["pflegegeld"],
     "wer_fuellt_aus": "versicherte", "quelle_url": "https://www.pv.at"},
    {"formular_id": "oegk_fahrtkosten_wien", "name": "Antrag auf Zuschuss zu Fahrtkosten (Wien)", "traeger": "ÖGK",
     "local_pdf": "_Source/Anträge und Formulare/Antrag-auf-Zuschuss-zu-Fahrtkosten_Wien.pdf", "fillable": True,
     "leistung_ids": ["fahrtkostenzuschuss"], "wer_fuellt_aus": "versicherte", "quelle_url": "https://www.oegk.at"},
    {"formular_id": "antrag_reha_kur", "name": "Antrag auf Rehabilitations-, Kur- bzw. Erholungsaufenthalt", "traeger": "SV (Träger im Formular wählen)",
     "local_pdf": "_Source/Anträge und Formulare/Antrag Kur und Reha.pdf", "fillable": True, "leistung_ids": ["reha_onkologisch", "kur"],
     "wer_fuellt_aus": "versicherte+arzt", "quelle_url": None},
    {"formular_id": "antrag_ahv_reha_unfall", "name": "Antrag auf Anschlussheilverfahren oder Rehabilitation nach Unfall", "traeger": "KV/PV",
     "local_pdf": "_Source/Anträge und Formulare/Reha_n_Unfall_052026.pdf", "fillable": True, "leistung_ids": ["anschlussheilverfahren"],
     "wer_fuellt_aus": "krankenhaus", "quelle_url": None},
    {"formular_id": "fsw_antrag_foerderung", "name": "FSW Antrag auf Förderung von Leistungen", "traeger": "FSW",
     "local_pdf": "_Source/Anträge und Formulare/fsw-antrag-auf-foerderung-von-leistungen.1779095804.pdf", "fillable": True,
     "leistung_ids": ["mobile_pflege_fsw", "wohn_pflegehaus_fsw"], "wer_fuellt_aus": "versicherte", "quelle_url": "https://www.fsw.at"},
    {"formular_id": "fsw_einrichtungswunsch", "name": "FSW Beilage Einrichtungswunsch Wohn- und Pflegehäuser", "traeger": "FSW",
     "local_pdf": "_Source/Anträge und Formulare/FSW-Antrag-Beilage-Einrichtungswunsch.1779345450.pdf", "fillable": True,
     "leistung_ids": ["wohn_pflegehaus_fsw"], "wer_fuellt_aus": "versicherte", "quelle_url": "https://www.fsw.at"},
    {"formular_id": "fsw_bedarfsmeldung_wg", "name": "FSW Bedarfsmeldung Senior:innen-WG (Basispaket)", "traeger": "FSW",
     "local_pdf": "_Source/Anträge und Formulare/Bedarfsmeldung-Senior_innen-Wohngemeinschaft_Basispaket.1736522017.pdf", "fillable": True,
     "leistung_ids": ["senior_innen_wg_fsw"], "wer_fuellt_aus": "versicherte", "quelle_url": "https://www.fsw.at"},
]


def dump(name, rows):
    with (OUT / name).open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    for r in L:
        r.setdefault("quellen", [])
    dump("seed_leistungen.jsonl", L)
    dump("seed_stellen.jsonl", STELLEN)
    dump("seed_formulare.jsonl", FORMULARE)
    print(f"Seed: {len(L)} Leistungen, {len(STELLEN)} Stellen, {len(FORMULARE)} Formulare")
