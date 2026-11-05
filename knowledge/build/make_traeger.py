#!/usr/bin/env python3
"""Träger-Register (ARCHITEKTUR §8.1.4) → knowledge/build/traeger.json

Kuratiert = nur Fakten von den offiziellen Kontaktseiten der Träger (Stand + URL je Eintrag). Wo unsere Ingest-Quellen
die Landesstellen bereits liefern (BVAEB, Sozialministeriumservice, FSW), werden sie beim Build aus stellen.jsonl
übernommen (`aus_stellen`) – nichts doppelt pflegen.
Payer-Konzepte des reimedy-Servers werden nur REFERENZIERT (vocabulary_id/concept_code), nicht kopiert.

Zuständigkeit (deterministisch, `aufloesung`):
  landesstelle_nach_bundesland  → Landesstelle des Wohnsitz-Bundeslandes (aus PLZ)
  fix                           → eine Stelle für ganz Österreich
  regional_unbekannt            → mehrere Anstalten, Lotse muss nachfragen (KFA)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "traeger.json"
STAND = "2026-11-05"
OEGK_Q = "https://www.oegk.at/kontakt"
PVA_Q = "https://www.pv.at/kontakt"
SVS_Q = "https://www.svs.at/cdscontent/?contentid=10007.861000&portal=svsportal"
RKB = "Austrian_Payer"  # vocabulary_id am reimedy-Server


def ls(tid, bl, name, adresse, plz, ort, telefon=None, email=None, url=None, quelle=None, hinweis=None):
    return {"id": f"{tid}_{bl.lower()}", "traeger_id": tid, "bundesland": bl, "name": name, "adresse": adresse,
            "plz": plz, "ort": ort, "telefon": telefon, "email": email, "url": url, "quelle_url": quelle, "stand": STAND,
            **({"hinweis": hinweis} if hinweis else {})}


TRAEGER = [
    {"id": "oegk", "name": "Österreichische Gesundheitskasse (ÖGK)", "typ": "sv", "sparten": ["KV"],
     "personenkreis": "Unselbständig Erwerbstätige (ASVG), ASVG-Pensionist:innen, Arbeitslose, Mitversicherte",
     "aufloesung": "landesstelle_nach_bundesland",
     "zentrale": {"adresse": "Wienerbergstraße 15-19", "plz": "1100", "ort": "Wien", "telefon": "+43 5 0766-0",
                  "email": "office@oegk.at", "url": "https://www.oegk.at"},
     "online": {"portal": "https://www.meineoegk.at", "app": "Meine ÖGK"},
     "quelle_url": OEGK_Q, "reimedy": {"vocabulary_id": RKB, "concept_code": "2000000001", "concept_id": 2000000001},
     "landesstellen": [
         ls("oegk", "B", "ÖGK Burgenland", "Siegfried Marcus-Straße 5", "7000", "Eisenstadt", "+43 5 0766-13", quelle=OEGK_Q),
         ls("oegk", "K", "ÖGK Kärnten", "Kempfstraße 8", "9021", "Klagenfurt am Wörthersee", "+43 5 0766-16", quelle=OEGK_Q),
         ls("oegk", "N", "ÖGK Niederösterreich", "Kremser Landstraße 3", "3100", "St. Pölten", "+43 5 0766-12", quelle=OEGK_Q),
         ls("oegk", "O", "ÖGK Oberösterreich", "Gruberstraße 77, Postfach 61", "4021", "Linz", "+43 5 0766-14", quelle=OEGK_Q),
         ls("oegk", "S", "ÖGK Salzburg", "Engelbert-Weiß-Weg 10", "5020", "Salzburg", "+43 5 0766-17", quelle=OEGK_Q),
         ls("oegk", "St", "ÖGK Steiermark", "Josef-Pongratz-Platz 1", "8010", "Graz", "+43 5 0766-15", quelle=OEGK_Q),
         ls("oegk", "T", "ÖGK Tirol", "Klara-Pölt-Weg 2", "6020", "Innsbruck", "+43 5 0766-18", quelle=OEGK_Q),
         ls("oegk", "V", "ÖGK Vorarlberg", "Jahngasse 4", "6850", "Dornbirn", "+43 5 0766-19", quelle=OEGK_Q),
         ls("oegk", "W", "ÖGK Wien", "Wienerbergstraße 15-19", "1100", "Wien", "+43 5 0766-11", quelle=OEGK_Q,
            hinweis="Kundenservicestellen je Bezirk: stellen mit typ=traeger, source oegk"),
     ],
     "aus_stellen": {"source_id": "oegk", "typ": "traeger"},  # Kundenservicestellen (Wien) aus dem oegk-Ingest
     "kontakt_hinweis": "Landesstellen haben keine eigene E-Mail-Adresse; Anfragen über das Online-Formular der jeweiligen Landesstelle."},
    {"id": "pva", "name": "Pensionsversicherungsanstalt (PVA)", "typ": "sv", "sparten": ["PV"],
     "personenkreis": "Pensionsversicherung unselbständig Erwerbstätiger (ASVG); entscheidet über Pflegegeld ihrer Pensionist:innen; Reha",
     "aufloesung": "landesstelle_nach_bundesland",
     "zentrale": {"adresse": "Friedrich-Hillegeist-Straße 1", "plz": "1020", "ort": "Wien", "telefon": "+43 (0)5 03 03",
                  "email": "pva@pv.at", "url": "https://www.pv.at"},
     "quelle_url": PVA_Q, "reimedy": None,
     "landesstellen": [
         ls("pva", "B", "PVA Landesstelle Burgenland", "Ödenburger Straße 8", "7000", "Eisenstadt", "+43 (0)5 03 03", "pva-lsb@pv.at", quelle=PVA_Q),
         ls("pva", "K", "PVA Landesstelle Kärnten", "Südbahngürtel 10", "9020", "Klagenfurt am Wörthersee", "+43 (0)5 03 03", "pva-lsk@pv.at", quelle=PVA_Q),
         ls("pva", "N", "PVA Landesstelle Niederösterreich", "Kremser Landstraße 5", "3100", "St. Pölten", "+43 (0)5 03 03", "pva-lsn@pv.at", quelle=PVA_Q),
         ls("pva", "O", "PVA Landesstelle Oberösterreich", "Terminal Tower, Bahnhofplatz 8", "4020", "Linz", "+43 (0)5 03 03", "pva-lso@pv.at", quelle=PVA_Q),
         ls("pva", "S", "PVA Landesstelle Salzburg", "Schallmooser Hauptstraße 11", "5020", "Salzburg", "+43 (0)5 03 03", "pva-lss@pv.at", quelle=PVA_Q),
         ls("pva", "St", "PVA Landesstelle Steiermark", "Eggenberger Straße 3", "8020", "Graz", "+43 (0)5 03 03", "pva-lsg@pv.at", quelle=PVA_Q),
         ls("pva", "T", "PVA Landesstelle Tirol", "Ing.-Etzel-Straße 13", "6020", "Innsbruck", "+43 (0)5 03 03", "pva-lst@pv.at", quelle=PVA_Q),
         ls("pva", "V", "PVA Landesstelle Vorarlberg", "Zollgasse 6", "6850", "Dornbirn", "+43 (0)5 03 03", "pva-lsv@pv.at", quelle=PVA_Q),
         ls("pva", "W", "PVA Landesstelle Wien", "Friedrich-Hillegeist-Straße 1", "1020", "Wien", "+43 (0)5 03 03", "pva-lsw@pv.at", quelle=PVA_Q,
            hinweis="Während der Generalsanierung: Kund*innenzentrum Ghegastraße 1, 1030 Wien (Beratung und Begutachtung)"),
     ]},
    {"id": "svs", "name": "Sozialversicherungsanstalt der Selbständigen (SVS)", "typ": "sv", "sparten": ["KV", "PV", "UV"],
     "personenkreis": "Gewerbetreibende, Neue Selbständige, Freiberufler:innen, Bäuerinnen und Bauern",
     "aufloesung": "landesstelle_nach_bundesland",
     "zentrale": {"telefon": "050 808 808", "url": "https://www.svs.at"},
     "online": {"portal": "https://www.svs.at", "app": "svsGO"},
     "quelle_url": SVS_Q, "reimedy": {"vocabulary_id": RKB, "concept_code": "2000000002", "concept_id": 2000000002},
     "kontakt_hinweis": "Vorsprache in allen Kundencentern nur mit Terminvereinbarung.",
     "landesstellen": [
         ls("svs", "W", "SVS-Kundencenter Wien", "Wiedner Hauptstraße 84-86", "1051", "Wien", "050 808 808", quelle=SVS_Q),
         ls("svs", "N", "SVS-Kundencenter Niederösterreich", "Neugebäudeplatz 1", "3100", "St. Pölten", "050 808 808", quelle=SVS_Q),
         ls("svs", "B", "SVS-Kundencenter Burgenland", "Siegfried Marcus-Straße 5", "7000", "Eisenstadt", "050 808 808", quelle=SVS_Q),
         ls("svs", "O", "SVS-Kundencenter Oberösterreich", "Hanuschstraße 34", "4020", "Linz", "050 808 808", quelle=SVS_Q),
         ls("svs", "St", "SVS-Kundencenter Steiermark", "Körblergasse 115", "8010", "Graz", "050 808 808", quelle=SVS_Q),
         ls("svs", "K", "SVS-Kundencenter Kärnten", "Feldkirchner Straße 52", "9020", "Klagenfurt am Wörthersee", "050 808 808", quelle=SVS_Q),
         ls("svs", "S", "SVS-Kundencenter Salzburg", "Auerspergstraße 24", "5020", "Salzburg", "050 808 808", quelle=SVS_Q),
         ls("svs", "T", "SVS-Kundencenter Tirol", "Klara-Pölt-Weg 1", "6020", "Innsbruck", "050 808 808", quelle=SVS_Q),
         ls("svs", "V", "SVS-Kundencenter Vorarlberg", "Schloßgraben 14", "6800", "Feldkirch", "050 808 808", quelle=SVS_Q),
     ]},
    {"id": "bvaeb", "name": "Versicherungsanstalt öffentlich Bediensteter, Eisenbahnen und Bergbau (BVAEB)", "typ": "sv",
     "sparten": ["KV", "UV", "PV (Eisenbahn/Bergbau)"],
     "personenkreis": "Beamt:innen und Vertragsbedienstete des Bundes (KV), Eisenbahn- und Bergbaubedienstete",
     "aufloesung": "landesstelle_nach_bundesland",
     "zentrale": {"adresse": "Josefstädter Straße 80", "plz": "1080", "ort": "Wien", "telefon": "050405-23700",
                  "email": "postoffice@bvaeb.at", "url": "https://www.bvaeb.at"},
     "quelle_url": "https://www.bvaeb.at/cdscontent/?contentid=10007.854342&portal=bvaebbportal",
     "reimedy": {"vocabulary_id": RKB, "concept_code": "2000000003", "concept_id": 2000000003},
     "aus_stellen": {"source_id": "bvaeb", "typ": "traeger"},
     "kontakt_hinweis": "Landesstelle Wien ist auch für Niederösterreich und Burgenland zuständig (Außenstellen St. Pölten, Eisenstadt)."},
    {"id": "auva", "name": "Allgemeine Unfallversicherungsanstalt (AUVA)", "typ": "sv", "sparten": ["UV"],
     "personenkreis": "Unfallversicherung unselbständig Erwerbstätiger, Schüler:innen, Studierender",
     "aufloesung": "fix", "zentrale": {"url": "https://www.auva.at"}, "quelle_url": "https://www.auva.at", "reimedy": None,
     "landesstellen": [],
     "kontakt_hinweis": "Adressen nach dem Standortumzug in Wien nicht verlässlich belegt – Kontakt über https://formular.auva.at/allgemeine-anfrage. Im Register bewusst ohne Adresse.",
     "confidence": "niedrig"},
    {"id": "kfa", "name": "Krankenfürsorgeanstalten (KFA)", "typ": "kfa", "sparten": ["KV"],
     "personenkreis": "Bestimmte Landes- und Gemeindebedienstete (statt BVAEB/ÖGK); ca. 15 regionale Anstalten",
     "aufloesung": "regional_unbekannt", "zentrale": None, "quelle_url": "https://rechnungshof.gv.at/rh/home/home/004.746_KFA_Salzburg_Steyr.pdf",
     "reimedy": {"vocabulary_id": RKB, "concept_code": "2000000004", "concept_id": 2000000004}, "landesstellen": [],
     "kontakt_hinweis": "KFAs sind keine SV-Träger und gehören nicht zum Dachverband. Der Lotse fragt nach der konkreten Anstalt (steht auf der e-card bzw. im Dienstvertrag).",
     "confidence": "mittel"},
    {"id": "dachverband", "name": "Dachverband der österreichischen Sozialversicherungsträger", "typ": "sv_dach", "sparten": [],
     "personenkreis": "Keine Leistungen an Versicherte; koordiniert die Träger, betreibt u. a. sozialversicherung.at und MeineSV",
     "aufloesung": "fix", "zentrale": {"adresse": "Kundmanngasse 21", "plz": "1030", "ort": "Wien", "url": "https://www.sozialversicherung.at"},
     "online": {"portal": "https://www.meinesv.at"},
     "quelle_url": "https://www.sozialversicherung.at/cdscontent/?contentid=10007.844507", "reimedy": None, "landesstellen": []},
    {"id": "fsw", "name": "Fonds Soziales Wien (FSW)", "typ": "land", "sparten": ["Pflege und Betreuung", "Behindertenhilfe", "Wohnungslosenhilfe"],
     "personenkreis": "Menschen mit Hauptwohnsitz in Wien", "aufloesung": "fix", "nur_bundesland": "W",
     "zentrale": {"adresse": "Guglgasse 7–9", "plz": "1030", "ort": "Wien", "telefon": "01 24 5 24", "email": "kundinnenservice@fsw.at",
                  "url": "https://www.fsw.at"},
     "quelle_url": "https://www.fsw.at/p/hilfe-kontakt", "reimedy": None, "aus_stellen": {"source_id": "fsw"}, "landesstellen": []},
    {"id": "sozialministeriumservice", "name": "Sozialministeriumservice (SMS)", "typ": "bund",
     "sparten": ["Behindertenpass", "Förderung 24-Stunden-Betreuung", "Pflegekarenzgeld", "Unterstützungsfonds"],
     "personenkreis": "bundesweit; Landesstellen je Bundesland", "aufloesung": "landesstelle_nach_bundesland",
     "zentrale": {"url": "https://www.sozialministeriumservice.gv.at"},
     "quelle_url": "https://www.sozialministeriumservice.gv.at", "reimedy": None,
     "aus_stellen": {"source_id": "sozialministeriumservice", "typ": "traeger"}, "landesstellen": [],
     "kontakt_hinweis": "Im Ingest bisher nur die Landesstelle Wien; andere Bundesländer → zentrale Website."},
]

if __name__ == "__main__":
    OUT.write_text(json.dumps({"_hinweis": __doc__.strip().splitlines()[0], "stand": STAND, "traeger": TRAEGER},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(TRAEGER)} Träger, {sum(len(t.get('landesstellen') or []) for t in TRAEGER)} kuratierte Landesstellen → {OUT.name}")
