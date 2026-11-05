"""Leistungs-Kandidaten (Schema B) und Stellen (Schema C). Zitate sind wörtliche Teilstrings der Quelltexte."""
import re
from fetch import GV, PF

def g(p): return GV + p
def pf(p): return PF + p

# id, name, bereich, traeger, innerhalb_sv, zielgruppe-Hinweis, Seiten (erste = Hauptquelle), Trigger
DEFS = [
 ("vorsorgeuntersuchung", "Vorsorgeuntersuchung (Gesundheits-Check)", ["A"], ["ÖGK", "SVS", "BVAEB"], True,
  [g("/leben/gesundheitsvorsorge/vorsorgeuntersuchung.html"), g("/leben/gesundheitsvorsorge/vorsorgeuntersuchung/was-wird-gemacht.html"), g("/leben/gesundheitsvorsorge/vorsorgeuntersuchung/ablauf.html"), g("/leben/gesundheitsvorsorge/vorsorgeuntersuchung/jugendlichenuntersuchung.html")],
  ["Vorsorgeuntersuchung", "Gesundheits-Check", "Vorsorge"]),
 ("brustkrebs_frueherkennung", "Brustkrebs-Früherkennung (Mammographie-Screening)", ["A"], ["ÖGK", "SVS", "BVAEB"], True,
  [g("/krankheiten/krebs/brustkrebs/frueherkennung.html"), g("/news/aktuelles/aktuell-2025/brustkrebsmonat-2025.html")],
  ["Brustkrebs", "Mammographie", "Früh-Erkennung Brustkrebs"]),
 ("darmkrebs_vorsorge", "Darmkrebs-Vorsorge (Früherkennung)", ["A"], ["ÖGK", "SVS", "BVAEB"], True,
  [g("/krankheiten/krebs/darmkrebs/frueherkennung-diagnose.html")], ["Darmkrebs", "Darmspiegelung", "Koloskopie", "Stuhltest", "familiäre Belastung"]),
 ("gebaermutterhalskrebs_frueherkennung", "Gebärmutterhalskrebs-Früherkennung", ["A"], ["ÖGK", "SVS", "BVAEB"], True,
  [g("/krankheiten/krebs/eierstock-gebaermutterhalskrebs/gebaermutterhalskrebs.html")], ["Gebärmutterhalskrebs", "PAP-Abstrich", "HPV"]),
 ("hautkrebs_frueherkennung", "Hautkrebs-Früherkennung", ["A"], [], True, [g("/krankheiten/krebs/hautkrebs/frueherkennung.html")], ["Hautkrebs", "Hautscreening"]),
 ("prostata_frueherkennung", "Prostatakrebs-Früherkennung", ["A"], [], True, [g("/krankheiten/krebs/hoden-prostatakrebs/prostata-frueherkennung.html")], ["Prostata", "PSA"]),
 ("impfungen_erwachsene", "Impfungen für Erwachsene (Impfplan Österreich)", ["A"], [], False,
  [g("/leben/gesundheitsvorsorge/impfungen/impfungen-erwachsene.html"), g("/leben/gesundheitsvorsorge/impfungen/impfungen-zielgruppen.html"), g("/leben/gesundheitsvorsorge/impfungen/impfschutz.html")],
  ["Impfung", "Impfplan", "Auffrischung"]),
 ("kinderimpfprogramm", "Kinderimpfprogramm (kostenloses Impfprogramm)", ["A"], [], False,
  [g("/service/leichter-lesen/impfungen.html"), g("/leben/gesundheitsvorsorge/impfungen/kinderimpfungen.html"), g("/leben/gesundheitsvorsorge/impfungen/impfung-schule.html")], ["Kinderimpfung", "Impfprogramm", "Schulimpfung"]),
 ("elektronischer_impfpass", "Elektronischer Impfpass (e-Impfpass)", ["A", "F"], [], False,
  [g("/gesundheitsleistungen/elga/elektronischer-impfpass.html"), g("/leben/gesundheitsvorsorge/impfungen/Impfdokumentation.html")], ["Impfpass", "e-Impfpass"]),
 ("eltern_kind_pass", "Eltern-Kind-Pass", ["A"], ["ÖGK", "SVS", "BVAEB"], True,
  [g("/leben/eltern/eltern-kind-pass.html"), g("/leben/eltern/eltern-kind-pass/untersuchungen-schwangerschaft.html"), g("/leben/eltern/eltern-kind-pass/kindesuntersuchungen.html"), g("/leben/eltern/eltern-kind-pass/eltern-kind-pass-untersuchungen.html"), g("/service/elektronischer-eltern-kind-pass.html"), g("/news/aktuelles/aktuell-2026/eltern-kind-pass-neue-untersuchungen.html")],
  ["Eltern-Kind-Pass", "Mutter-Kind-Pass", "Schwangerschaft", "Kinderuntersuchung"]),
 ("bewegt_im_park", "Bewegt im Park", ["B"], [], False,
  [g("/news/aktuelles/aktuell-2026/bewegt-im-park.html"), g("/news/aktuelles/aktuell-2025/bewegt-im-park-2025.html")], ["Bewegt im Park", "Bewegung im Park"]),
 ("bewegungsempfehlungen", "Nationale Bewegungsempfehlungen", ["B"], [], False,
  [g("/leben/bewegung/gesund-durch-sport/bewegungsempfehlungen-erwachsene.html"), g("/leben/bewegung/gesund-durch-sport/bewegungsempfehlungen-senioren.html"), g("/leben/bewegung/gesund-durch-sport/bewegungsempfehlungen-kinder.html")], ["Bewegungsempfehlung", "Bewegung"]),
 ("ernaehrungspyramide", "Österreichische Ernährungspyramide", ["B"], [], False,
  [g("/leben/ernaehrung/info/oesterreichische-ernaehrungspyramide.html")], ["Ernährungspyramide", "Ernährung"]),
 ("rauchfrei_telefon", "Rauchfrei Telefon", ["B"], [], False,
  [g("/news/aktuelles/aktuell-2026/rauchfrei-telefon-20.html"), g("/service/beratungsstellen/krankheiten/abhaengigkeit-sucht/nikotinsucht-beratung.html"), g("/leben/gesundheitsvorsorge/nichtrauchen.html")], ["Rauchfrei", "Nikotin", "Rauchstopp", "Nichtrauchen"]),
 ("psychosoziale_angebote", "Psychosoziale Beratung und Dienste", ["B", "C"], [], False,
  [g("/service/beratungsstellen/krankheiten/psyche/psychosozialer-dienst.html"), g("/service/beratungsstellen/gesund-leben/psyche-seele/hilfe-psyche.html"), g("/leben/psyche-seele/krisenintervention.html"), g("/service/beratungsstellen/gesund-leben/psyche-seele/psychotherapie.html")],
  ["psychosozial", "Psychotherapie", "Krisenintervention"]),
 ("gesundheitsberatung_1450", "Gesundheitsberatung 1450", ["F"], [], False,
  [g("/service/beratungsstellen/gesundheitssystem/gesundheitsleistungen/gesundheitsberatung.html"), g("/service/notruf/hotline.html"), g("/service/notruf/aerztenotdienst.html")], ["1450", "Gesundheitsberatung", "Ärztenotdienst"]),
 ("hausarzt_primaerversorgung", "Hausärzt:in und Primärversorgung", ["F"], ["ÖGK", "SVS", "BVAEB"], True,
  [g("/gesundheitsleistungen/primaerversorgung.html"), g("/gesundheitsleistungen/primaerversorgung/primaerversorgungseinheiten.html"), g("/gesundheitsleistungen/primaerversorgung/faq.html"), g("/gesundheitsleistungen/arztbesuch/ordinationsformen.html")], ["Primärversorgung", "Hausarzt", "PVE"]),
 ("e_card", "e-card", ["F"], ["ÖGK", "SVS", "BVAEB"], True, [g("/gesundheitsleistungen/arztbesuch/e-card.html")], ["e-card", "Krankenversicherungskarte"]),
 ("wahlarzt_kostenerstattung", "Wahlärzt:in und Kostenerstattung", ["E", "F"], ["ÖGK", "SVS", "BVAEB"], True,
  [g("/gesundheitsleistungen/arztbesuch/wahlarzt-kosten.html"), g("/gesundheitsleistungen/arztbesuch/was-zahlt-sozialversicherung.html")], ["Wahlarzt", "Kostenerstattung"]),
 ("elga", "ELGA – Elektronische Gesundheitsakte", ["F"], [], False,
  [g("/gesundheitsleistungen/elga.html"), g("/gesundheitsleistungen/elga/elga-was-ist-das.html"), g("/gesundheitsleistungen/elga/elga-login-teilnahme.html"), g("/gesundheitsleistungen/elga/e-befund.html"), g("/gesundheitsleistungen/elga/e-medikation.html"), g("/gesundheitsleistungen/elga/elga-ombudsstelle.html")], ["ELGA", "e-Befund", "e-Medikation", "Widerspruch"]),
 ("patientenrechte", "Patientenrechte", ["F"], [], False,
  [g("/gesundheitsleistungen/patientenrechte.html"), g("/gesundheitsleistungen/patientenrechte/patientencharta.html"), g("/gesundheitsleistungen/patientenrechte/recht-auf-behandlung.html"), g("/gesundheitsleistungen/patientenrechte/behandlungsfehler.html"), g("/gesundheitsleistungen/patientenrechte/patienteninformation.html")], ["Patientenrechte", "Patientencharta", "Behandlungsfehler"]),
 ("patientenanwaltschaft", "Patientenanwaltschaft", ["F"], [], False,
  [g("/service/beratungsstellen/gesundheitssystem/patientenrechte/patientenanwaltschaft.html")], ["Patientenanwaltschaft", "Patientenanwalt", "Patientenvertretung"]),
 ("patientenverfuegung", "Patientenverfügung", ["F"], [], False,
  [g("/gesundheitsleistungen/patientenrechte/patientenverfuegung.html"), pf("/de/patientenverfuegung")], ["Patientenverfügung"]),
 ("vorsorgevollmacht", "Vorsorgevollmacht und Erwachsenenvertretung", ["F"], [], False,
  [g("/gesundheitsleistungen/patientenrechte/vorsorgevollmacht.html"), pf("/de/vorsorgevollmacht"), pf("/de/erwachsenenvertretung")], ["Vorsorgevollmacht", "Erwachsenenvertretung", "Sachwalterschaft"]),
 ("reha_medizinisch", "Medizinische Rehabilitation", ["C"], ["PVA", "ÖGK", "SVS", "BVAEB"], True,
  [g("/gesundheitsleistungen/kur-reha/medizinische-rehabilitation.html"), g("/gesundheitsleistungen/kur-reha.html")], ["Rehabilitation", "Reha"]),
 ("kur_aufenthalt", "Kur (Kuraufenthalt)", ["C"], ["PVA", "ÖGK", "SVS", "BVAEB"], True,
  [g("/gesundheitsleistungen/kur-reha/kur-aufenthalt.html"), g("/gesundheitsleistungen/krankenhausaufenthalt/kuraufenthalt.html")], ["Kur", "Kuraufenthalt"]),
 ("reha_kinder", "Rehabilitation für Kinder und Jugendliche", ["C"], ["PVA", "ÖGK"], True,
  [g("/gesundheitsleistungen/kur-reha/kinder-reha.html"), pf("/de/reha-f%C3%BCr-kinder-und-jugendliche")], ["Kinder-Reha", "Rehabilitation Kinder"]),
 ("reha_beruflich", "Berufliche Rehabilitation", ["C", "E"], ["PVA", "AMS"], True, [g("/gesundheitsleistungen/kur-reha/berufliche-rehabilitation.html")], ["berufliche Rehabilitation", "Umschulung"]),
 ("reha_sozial", "Soziale Rehabilitation", ["C", "E"], [], False, [g("/gesundheitsleistungen/kur-reha/soziale-rehabilitation.html")], ["soziale Rehabilitation"]),
 ("heilbehelfe_hilfsmittel", "Heilbehelfe und Hilfsmittel", ["C", "E"], ["ÖGK", "SVS", "BVAEB"], True, [g("/gesundheitsleistungen/heilbehelfe-hilfsmittel.html")], ["Heilbehelf", "Hilfsmittel"]),
 ("palliativ_hospiz", "Palliativ- und Hospizversorgung", ["C", "D"], [], False, [g("/gesundheitsleistungen/palliativ-hospizversorgung.html"), g("/gesundheitsleistungen/palliativ-hospizversorgung/hospiz-palliativ-einrichtungen.html")], ["Hospiz", "Palliativ"]),
 ("selbsthilfe", "Selbsthilfegruppen", ["B", "C"], [], False, [g("/gesundheitsleistungen/institutionen/arge-selbsthilfe.html"), pf("/de/selbsthilfegruppen"), g("/service/beratungsstellen/krankheiten/gehirn-nerven/dachverband-selbsthilfegruppen.html")], ["Selbsthilfe", "Selbsthilfegruppe"]),
 ("pflegegeld", "Pflegegeld", ["D", "E"], ["PVA", "ÖGK", "SVS", "BVAEB"], True,
  [pf("/de/pflegegeld"), pf("/de/pflegegeldstufen"), pf("/de/antrag-auf-pflegegeld-stellen"), pf("/de/anleitung-der-weg-zum-pflegegeld"), pf("/de/pflegegeld-allgemein"), pf("/de/pflegegeldklage")], ["Pflegegeld", "Pflegebedarf", "Pflegestufe"]),
 ("pflegekarenz", "Pflegekarenz, Pflegeteilzeit, Pflegefreistellung und Pflegekarenzgeld", ["D", "E"], ["Sozialministeriumservice"], False,
  [pf("/de/pflegefreistellung-pflegeteilzeit-und-pflegekarenz"), pf("/de/pflegekarenzgeld")], ["Pflegekarenz", "Pflegeteilzeit", "Pflegefreistellung", "Pflegekarenzgeld"]),
 ("pflegende_angehoerige_unterstuetzung", "Unterstützung für pflegende Angehörige (Überblick)", ["D", "E"], [], False,
  [pf("/de/so-finden-pflegende-angehoerige-rat-und-hilfe"), pf("/de/finanzielle-unterstuetzung-und-versicherungsschutz-fuer-pflegende-angehoerige"), pf("/de/versicherungsschutz-f%C3%BCr-pflegende-angeh%C3%B6rige"), g("/leben/altern/wohnen-im-alter/pflegende-angehoerige-entlastungen-unterstuetzungen.html")], ["pflegende Angehörige", "Angehörige", "Versicherungsschutz"]),
 ("angehoerigenbonus", "Angehörigenbonus", ["D", "E"], [], False, [pf("/de/angehoerigenbonus")], ["Angehörigenbonus"]),
 ("angehoerigengespraech", "Angehörigengespräch", ["D"], [], False, [pf("/de/das-angehoerigengespraech")], ["Angehörigengespräch"]),
 ("reha_pflegende_angehoerige", "Rehabilitation für pflegende Angehörige", ["C", "D"], ["PVA"], True, [pf("/de/rehabilitation-fuer-pflegende-und-betreuende-angehoerige")], ["Rehabilitation pflegende Angehörige"]),
 ("kurzzeitpflege", "Kurzzeit-, Ersatz- und Urlaubspflege", ["D"], [], False, [pf("/de/kurzzeitpflege-ersatzpflege-und-urlaubspflege"), pf("/de/entlastungs-und-erholungsmoeglichkeiten")], ["Kurzzeitpflege", "Ersatzpflege", "Verhinderungspflege"]),
 ("betreuung_24_stunden", "24-Stunden-Betreuung (inkl. Förderung)", ["D", "E"], ["Sozialministeriumservice"], False, [pf("/de/24-stunden-betreuung"), pf("/de/foerderung-fuer-24-stunden-betreuung")], ["24-Stunden-Betreuung", "Betreuungskraft"]),
 ("hauskrankenpflege", "Mobile Dienste und Hauskrankenpflege", ["D"], ["ÖGK"], True, [pf("/de/hauskrankenpflege"), pf("/de/heimhilfe-haushaltshilfe"), pf("/de/unterstuetzungsmoeglichkeiten-fuer-zu-hause"), pf("/de/pflege-und-betreuung-zu-hause")], ["Hauskrankenpflege", "Heimhilfe", "mobile Pflege"]),
 ("pflegeheim_tageszentrum", "Pflegeheime und Tageszentren", ["D"], [], False, [pf("/de/altenheime-pflegeheime"), pf("/de/tageszentrum"), pf("/de/pflege-und-betreuungseinrichtungen")], ["Pflegeheim", "Tageszentrum"]),
 ("rezeptgebuehrenbefreiung", "Rezeptgebührenbefreiung", ["E", "F"], ["ÖGK", "SVS", "BVAEB"], True, [pf("/de/rezeptgebuehren"), pf("/de/gebuehrenbefreiung")], ["Rezeptgebühr", "Rezeptgebührenbefreiung"]),
 ("behindertenpass", "Behindertenpass", ["E", "F"], ["Sozialministeriumservice"], False, [pf("/de/behindertenpass")], ["Behindertenpass"]),
 ("pflegeberatung", "Pflegeberatung und Beratungsstellen", ["D", "F"], [], False, [pf("/de/beratungsangebote"), pf("/de/beratungsstellen-oesterreichweit"), pf("/de/beratungsstellen-im-bundesland"), pf("/de/community-nursing")], ["Pflegeberatung", "Beratungsstelle", "Community Nursing"]),
]

HEAD_V = re.compile(r"Anspruch|Wer |Voraussetzung|Zielgruppe|Für wen|Berechtigt|Teilnahme|Wann ", re.I)
HEAD_K = re.compile(r"Kosten|Finanzier|Abdeckung|Höhe|Selbstbehalt|Gebühr|Förder", re.I)
HEAD_W = re.compile(r"Wohin|Anmeld|Antrag stellen|Antrag auf|Wo (kann|erhalte|finde|beantrage)", re.I)
FRIST = re.compile(r"\bFrist\b|innerhalb (von )?\d|spätestens|einmal (?:pro|im|jährlich)|alle (\d+|zwei|drei|fünf) Jahre|\b\d+ (Monate|Wochen|Tage|Jahre)", re.I)


def sents(t):
    t = re.sub(r"^• ", "", t)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if len(s.strip()) > 25]


def build_leistungen(pages, docs):
    by = {}
    for d in docs: by.setdefault(d["url"], []).append(d)
    out = []
    for lid, name, bereich, traeger, insv, urls, trig in DEFS:
        have = [u for u in urls if u in by]
        if not have: continue
        voraus, kosten, wo, fristen, quellen = [], [], [], [], []
        for u in have:
            pg = pages[u]
            quellen.append({"url": u, "stand": pg.get("stand")})
            for d in by[u]:
                head = d["section"]
                if HEAD_V.search(head) and len(voraus) < 6:
                    for s in sents(d["text"])[:3]:
                        if len(voraus) < 6: voraus.append({"text": s, "quelle_url": u, "zitat": s})
                if HEAD_K.search(head) and len(kosten) < 3: kosten += [s for s in sents(d["text"])[:2]]
                if HEAD_W.search(head) and len(wo) < 3: wo += sents(d["text"])[:2]
                for s in sents(d["text"]):
                    if FRIST.search(s) and len(fristen) < 4 and s not in fristen: fristen.append(s)
        main = have[0]
        # leichte Sprache bevorzugen, sonst wörtliche Zusammenfassung (Teaser) der Hauptquelle
        easy = next((u for u in have if "leichter-lesen" in u), None)
        src = easy or main
        cand = [d["text"] for d in by.get(src, []) if len(d["text"]) >= 80]
        first = cand[0] if cand else ""
        kurz = " ".join(sents(first.split("\n")[0])[:2]) or first[:300]
        out.append({
            "leistung_id": lid, "name": name,
            "kurz_einfach": kurz + ("" if easy else "  [Wortlaut Quelle, nicht vereinfacht]"),
            "bereich": bereich, "traeger": traeger, "innerhalb_sv": insv,
            "zielgruppe": voraus[0]["zitat"] if voraus else None,
            "voraussetzungen": voraus, "zustaendig": None,
            "antrag": {"formular_id": None, "wo": " ".join(wo[:3]) or None, "online_url": None},
            "unterlagen": [], "fristen": fristen, "kosten": " ".join(kosten) or None,
            "abhaengigkeiten": [], "trigger_im_dokument": trig, "bundesland": ["AT"],
            "quellen": quellen, "confidence": "mittel" if voraus else "niedrig",
            "hinweis": "Automatisch aus Portaltext extrahiert (wörtliche Zitate), Mensch-Review nötig. Keine medizinische Empfehlung.",
        })
    return out


# --- Stellen: verifizierte Hotlines (Nummer muss im Quelltext stehen) + Beratungsstellen-Links
HOT = [
 ("gesundheitsberatung_1450", "Gesundheitsberatung 1450", "hotline", "1450", "Rund um die Uhr, telefonische Erstberatung", ["gesundheitsberatung_1450"], g("/service/notruf/hotline.html")),
 ("rettung_144", "Rettung (Notruf)", "hotline", "144", None, [], g("/service/notruf/notrufnummern.html")),
 ("aerztefunkdienst_141", "Ärztenotdienst / Ärztefunkdienst", "hotline", "141", None, ["gesundheitsberatung_1450"], g("/service/notruf/aerztenotdienst.html")),
 ("vergiftungsinformation", "Vergiftungsinformationszentrale", "hotline", "01 406 43 43", None, [], g("/service/notruf/notrufnummern.html")),
 ("rauchfrei_telefon", "Rauchfrei Telefon", "hotline", "0800 810 013", None, ["rauchfrei_telefon"], g("/news/aktuelles/aktuell-2026/rauchfrei-telefon-20.html")),
 ("telefonseelsorge_142", "Telefonseelsorge", "hotline", "142", None, ["psychosoziale_angebote"], g("/service/notruf/notrufnummern.html")),
 ("rat_auf_draht_147", "Rat auf Draht", "hotline", "147", None, ["psychosoziale_angebote"], g("/service/notruf/notrufnummern.html")),
]


def has_num(tel, text):
    pat = r"(?<![\d])" + r"[\s\-/]*".join(re.escape(c) for c in tel.replace(" ", "")) + r"(?![\d])"
    return re.search(pat, text) is not None


def build_stellen(pages, docs):
    by = {}
    for d in docs: by.setdefault(d["url"], []).append(d["text"])
    out = []; seen = set()
    for sid, name, typ, tel, oz, zf, src in HOT:
        txt_ = " ".join(by.get(src, []))
        if not txt_ or not has_num(tel, txt_): continue  # nur verifizierte Nummern
        if sid in seen: continue
        seen.add(sid)
        out.append({"stelle_id": sid, "name": name, "typ": typ, "adresse": None, "plz": None, "bundesland": "AT", "telefon": tel, "email": None,
                    "url": src, "oeffnungszeiten": oz, "zustaendig_fuer": zf, "geo": None, "quelle_url": src})
    # Beratungsstellen: externe Links aus den Beratungsstellen-Seiten (Name = Linktext, Beschreibung = Kontext)
    for u, pg in pages.items():
        if "/service/beratungsstellen/" not in u and not re.search(r"pflege\.gv\.at/de/(beratungsstellen|selbsthilfegruppen|beratungsangebote|community)", u): continue
        for t, h in pg["links"]:
            if not re.match(r"https?://", h) or "gesundheit.gv.at" in h and "linkresolution" not in h and "/service/" in h: continue
            if "pflege.gv.at" in h or len(t) < 4 or len(t) > 120 or re.search(r"^(mehr|hier|weiter|zur|zum|lesen|mailto)", t, re.I): continue
            t = re.sub(r"^Website\s+", "", t)
            sid = "ggv_" + re.sub(r"[^a-z0-9]+", "_", t.lower().translate(str.maketrans("äöüß", "aous")))[:60].strip("_")
            if sid in seen: continue
            seen.add(sid)
            out.append({"stelle_id": sid, "name": t, "typ": "beratung", "adresse": None, "plz": None, "bundesland": "AT", "telefon": None, "email": None,
                        "url": h, "oeffnungszeiten": None, "zustaendig_fuer": [], "geo": None, "quelle_url": u})
    return out
