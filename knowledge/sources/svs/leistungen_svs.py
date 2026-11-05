from _common import make_leistungen

SPECS = [
 dict(leistung_id="gesundheitshunderter_svs", name="Gesundheitshunderter (SVS)", kurz="Die SVS zahlt einmal pro Jahr bis zu 100 € für gesundheitsfördernde Aktivitäten dazu – freiwillig, ohne Rechtsanspruch.",
      bereich=["B"], title_re=r"^Gesundheitshunderter$|Gesundheitshunderter Junior|Themen und Programme", vq=[r"Gesundheitshunderter", r"Voraussetzung", r"Vorsorgeuntersuchung|Gesundheits-Check"],
      kq=[r"€|Euro"], fq=[r"pro Kalenderjahr|Frist|innerhalb"], zustaendig="SVS (Gewerbetreibende, Bauern, Neue Selbständige)", trigger=["Gesundheitshunderter", "Bewegung", "Ernährung"],
      unterschied="Nur SVS. Bei BVAEB gibt es keinen Gesundheitshunderter (dort: Gesundheitsförderung/Jackpot.fit).", conf="hoch"),
 dict(leistung_id="selbstaendig_gesund_selbstbehalt", name="Selbständig Gesund – halber Selbstbehalt (SVS)", kurz="Wer mit Hausarzt Gesundheitsziele vereinbart und erreicht, zahlt statt 20 % nur 10 % Selbstbehalt (bis 5 %).",
      bereich=["A", "B"], title_re=r"Selbständig Gesund|Nachhaltig Gesund|Ihr Weg zum halben|Fünf Gesundheitsziele", vq=[r"Selbstbehalt", r"Gesundheitsziel", r"Vorsorgeuntersuchung", r"Evaluierung"],
      kq=[r"Selbstbehalt.*(10|5) ?%|(10|5) ?%.*Selbstbehalt|20 ?%"], fq=[r"sechs Monate|zwei bis drei Jahre"], zustaendig="SVS (GSVG-Versicherte: Gewerbetreibende, Neue Selbständige; Bauern analog nach SVS-Regeln – siehe Quelle)",
      abh=["vorsorgeuntersuchung"], trigger=["Selbstbehalt", "Selbständig Gesund", "Gesundheitsziele"],
      unterschied="Selbstbehalt 20 % bei SVS (Reduktion auf 10 %/5 % möglich) vs. BVAEB: Behandlungsbeitrag ebenfalls grundsätzlich 20 %, aber OHNE Reduktionsprogramm – siehe behandlungsbeitrag_bvaeb. ÖGK: i. d. R. kein Selbstbehalt bei Vertragsärzt:innen.", conf="hoch"),
 dict(leistung_id="vorsorgeuntersuchung", name="Vorsorgeuntersuchung (SVS-Gesundheitscheck)", kurz="Kostenloser Gesundheitscheck bei Vertragsärzt:innen bzw. Wahlärzt:innen mit VU-Vertrag.",
      bereich=["A"], title_re=r"^Vorsorgeuntersuchung$|Vorsorgeangebote|Brustkrebsfrüherkennung|Darmkrebs|Gesundheits-Check Junior|Vorsorgepass|SVS-Vorsorgetag", vq=[r"kostenlos|gratis|kostenfrei", r"ab dem|Jahr", r"Vorsorgeuntersuchung"],
      kq=[r"kostenlos|gratis|kostenfrei"], fq=[r"einmal (pro|im) Jahr|jährlich"], zustaendig="Krankenversicherungsträger (SVS) – Durchführung bei Vertragsärzt:innen", trigger=["Vorsorgeuntersuchung", "Gesundenuntersuchung", "Vorsorgepass"],
      unterschied="Gleiches Grundprinzip bei ÖGK/BVAEB (BVAEB: 'Vorsorgeuntersuchung' und 'Gesundheit und Beruf (GuB)'); Zusatzanreize nur SVS (Selbständig Gesund)."),
 dict(leistung_id="pflegegeld", name="Pflegegeld (SVS als Entscheidungsträger)", kurz="Pflegegeld bei dauerndem Pflegebedarf; für SVS-Pensions-/Rentenbeziehende entscheidet die SVS, sonst PVA/ÖGK/BVAEB.",
      bereich=["D"], title_re=r"^Pflegegeld$|Pflegestufen|^Antrag$|Pflege$", vq=[r"Pflegebedarf", r"Stunden|Std", r"zuständig|Entscheidungsträger|Antrag"], kq=[r"€|Euro"], fq=[r"Antrag|Monat"],
      zustaendig="Der Entscheidungsträger richtet sich nach der Pension/Rente (z. B. SVS, PVA, BVAEB).", abh=["rezeptgebuehrenbefreiung"], trigger=["Pflegegeld", "Pflegebedarf", "Pflegestufe"],
      unterschied="Zuständigkeit: je nach Pensionsversicherungsträger (SVS/BVAEB/PVA); Antragsformular je Träger.", conf="mittel"),
 dict(leistung_id="reha_medizinisch", name="Rehabilitation (medizinisch) – SVS", kurz="Medizinische Rehabilitation nach Krankheit/Unfall, Antrag meist über den Arzt/die Ärztin.",
      bereich=["C"], title_re=r"^Rehabilitation|Rehabilitationsberatung|Betriebshilfe bei medizinischer|Unfallheilbehandlung", vq=[r"Antrag", r"Voraussetzung|Anspruch", r"Selbstbehalt|Kostenbeitrag|Tag"], kq=[r"Kostenbeitrag|Selbstbehalt|€|Euro|pro Tag"], zustaendig="SVS (Kranken-/Pensions-/Unfallversicherung je nach Anlass)", abh=["reha_onkologisch"], trigger=["Rehabilitation", "Reha"]),
 dict(leistung_id="kur", name="Heilverfahren (Kur) – SVS", kurz="Kuraufenthalt (Heilverfahren) mit Kostenzuschuss der SVS.", bereich=["C"], title_re=r"Heilverfahren|Kur\b", vq=[r"Antrag", r"Voraussetzung|Anspruch|ärztlich", r"Wartezeit|Jahre"], kq=[r"Kostenbeitrag|Selbstbehalt|€|Euro|pro Tag"], zustaendig="SVS", trigger=["Kur", "Heilverfahren"]),
 dict(leistung_id="rezeptgebuehrenbefreiung", name="Rezeptgebühr / Befreiung (SVS)", kurz="Rezeptgebühr pro Medikament; bei geringem Einkommen oder hoher Belastung Befreiung möglich.", bereich=["C", "E"], title_re=r"Medikamente$|Selbstbehalt & Vergütung|Befreiungen & Ausnahmen|Medikamente & medizinische", vq=[r"Rezeptgebühr", r"befreit|Befreiung", r"Einkommen|Ausgleichszulage|Richtsatz"], kq=[r"Rezeptgebühr.*€|€.*Rezeptgebühr"], zustaendig="Krankenversicherungsträger (SVS)", trigger=["Rezeptgebühr", "Befreiung"],
      unterschied="Ähnlich bei ÖGK/BVAEB (Obergrenze/Rezeptgebührenkonto); Details je Träger."),
 dict(leistung_id="krankentransport", name="Krankentransport / Rettungstransport (SVS)", kurz="Kostenübernahme für Rettungs- und Krankentransporte bei medizinischer Notwendigkeit, i. d. R. mit Selbstbehalt.", bereich=["C"], title_re=r"Rettungs- und Krankentransport", vq=[r"Transport", r"Bewilligung|ärztlich|Notwendigkeit"], kq=[r"Selbstbehalt|Kostenanteil|€|Euro"], zustaendig="SVS", trigger=["Krankentransport", "Rettung"],
      unterschied="BVAEB: Fahrtkosten/Transportkosten/Flugrettung – eigene Regeln (siehe BVAEB)."),
 dict(leistung_id="heilbehelfe_hilfsmittel", name="Heilbehelfe & Hilfsmittel (SVS)", kurz="Zuschuss zu Brillen, Rollstuhl, Hörgerät u. ä. auf ärztliche Verordnung.", bereich=["C"], title_re=r"Heilbehelf|Hilfsmittel|Körperersatzstücke", vq=[r"Verordnung|ärztlich", r"Bewilligung|Antrag", r"Selbstbehalt|Kostenanteil"], kq=[r"Selbstbehalt|Kostenanteil|€|Euro|Prozent|%"], zustaendig="SVS", trigger=["Heilbehelf", "Hilfsmittel", "Brille"]),
 dict(leistung_id="wochengeld", name="Wochengeld & Mutterschaftsbetriebshilfe (SVS)", kurz="Wochengeld für Selbständige rund um die Geburt bzw. Betriebshilfe; Voraussetzungen und Höhe je Versichertengruppe.", bereich=["E"], title_re=r"Wochengeld|Schwangerschaft & Geburt|Unterbrechung der Selbständigkeit bei Mutterschutz", vq=[r"Wochengeld", r"Anspruch|Voraussetzung", r"Wochen"], kq=[r"€|Euro|Prozent|%"], fq=[r"Wochen vor|nach der Geburt|Antrag"], zustaendig="SVS", trigger=["Wochengeld", "Mutterschutz"]),
 dict(leistung_id="krankengeld", name="Krankengeld (SVS)", kurz="Krankengeld bei Arbeitsunfähigkeit (für Selbständige: besondere Voraussetzungen).", bereich=["E"], title_re=r"Krankengeld", vq=[r"Krankengeld", r"Anspruch|Voraussetzung|Tag"], kq=[r"€|Euro|Prozent|%"], zustaendig="SVS", trigger=["Krankengeld"]),
 dict(leistung_id="unfall_heilbehandlung", name="Unfallheilbehandlung & Rehabilitation (SVS)", kurz="Leistungen der SVS-Unfallversicherung nach Arbeitsunfall/Berufskrankheit.", bereich=["C"], title_re=r"Arbeitsunfall|Berufskrankheit|Leistungen der Unfallversicherung|Unfallheilbehandlung", vq=[r"Arbeitsunfall", r"Anspruch|Voraussetzung|melden"], kq=[r"€|Euro|Prozent|%"], zustaendig="SVS (AUVA ist für diese Gruppen nicht zuständig)", trigger=["Arbeitsunfall", "Berufskrankheit"]),
 dict(leistung_id="gesundheitsangebote_svs", name="SVS-Gesundheitsangebote (Gesundheitswochen, Pflegeauszeit, Camps)", kurz="Geförderte Gesundheitswochen, Pflegeauszeit für pflegende Angehörige und weitere Angebote der SVS.", bereich=["B", "D"], title_re=r"Gesundheitsangebote|Gesundheitswoche|Pflegeauszeit|SVS-Camps|SVS-Beratungstage|Jackpot", vq=[r"Selbstbehalt|Eigenanteil|Kosten", r"Anspruch|Voraussetzung|Teilnahme"], kq=[r"€|Euro|Eigenanteil"], zustaendig="SVS", trigger=["Gesundheitswoche", "Pflegeauszeit"]),
]
def leistungen(docs, pages, cfg):
    import json, pathlib
    forms = [json.loads(l) for l in open(pathlib.Path(__file__).parent / "out/formulare.jsonl")]
    return make_leistungen(SPECS, docs, ["SVS"], True, forms)


def stellen_override(docs):
    import re
    out = []
    for d in docs:
        if d["title"] == "SVS-Kundencenter" and d["section"] == "Kundencenter-Adresse":
            lines = [l.strip() for l in d["text"].split("\n")[1:] if l.strip()]
            m = next((re.match(r"(\d{4}) (.+)", l) for l in lines if re.match(r"\d{4} ", l)), None)
            street = next((l for l in lines if not re.match(r"\d{4} ", l)), None)
            ort = m.group(2) if m else None
            out.append({"stelle_id": f"svs_kundencenter_{(ort or 'x').lower()}_{m.group(1) if m else ''}", "name": f"SVS-Kundencenter {ort}", "typ": "traeger",
                "adresse": f"{street}, {m.group(0)}" if m else street, "plz": m.group(1) if m else None, "bundesland": "W" if ort == "Wien" else None,
                "telefon": "050 808 808", "email": None, "url": d["url"], "oeffnungszeiten": "Beratung nur mit Terminvereinbarung (laut SVS-Kontaktseite)",
                "zustaendig_fuer": ["pflegegeld", "wochengeld", "kur", "reha_medizinisch", "gesundheitshunderter_svs", "selbstaendig_gesund_selbstbehalt"], "geo": None, "quelle_url": d["url"]})
    return out
