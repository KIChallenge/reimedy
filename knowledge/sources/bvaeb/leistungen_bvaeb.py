from _common import make_leistungen

SPECS = [
 dict(leistung_id="behandlungsbeitrag_bvaeb", name="Behandlungsbeitrag (BVAEB)", kurz="Kostenbeteiligung bei Arztbesuchen/Behandlungen für BVAEB-Versicherte; Nachsicht bei geringem Einkommen möglich.", bereich=["C", "E"],
      title_re=r"Behandlungsbeitrag|Nachsicht", vq=[r"Behandlungsbeitrag", r"Nachsicht|befreit|Befreiung", r"Einkommen|Richtsatz|Ausgleichszulage"], kq=[r"%|Prozent|€|Euro"], zustaendig="BVAEB", trigger=["Behandlungsbeitrag", "Kostenbeteiligung", "Selbstbehalt"],
      unterschied="BVAEB: 'Behandlungsbeitrag' grundsätzlich 20 % (Kinder/Waisenpensionsbezieher ausgenommen; Nachsicht-Richtlinien). SVS: 'Selbstbehalt' 20 % (reduzierbar auf 10 %/5 % via Selbständig Gesund). ÖGK: i. d. R. kein Selbstbehalt bei Vertragsärzt:innen (bitte mit ÖGK-Quelle abgleichen).", conf="mittel"),
 dict(leistung_id="vorsorgeuntersuchung", name="Vorsorgeuntersuchung (BVAEB)", kurz="Kostenlose Vorsorgeuntersuchung bzw. 'Gesundheit und Beruf (GuB)' bei Vertragsärzt:innen.", bereich=["A"], title_re=r"Vorsorgeuntersuchung|Gesundheit und Beruf|FAQ - häufig gestellte Fragen zur Vorsorge", vq=[r"kostenlos|gratis|kostenfrei", r"ab dem|Jahr", r"Anspruch|berechtigt"], kq=[r"kostenlos|gratis|kostenfrei"], fq=[r"jährlich|einmal"], zustaendig="BVAEB", trigger=["Vorsorgeuntersuchung", "Gesundenuntersuchung", "GuB"]),
 dict(leistung_id="pflegegeld", name="Pflegegeld (BVAEB als Entscheidungsträger)", kurz="Pflegegeld für BVAEB-Pensionist:innen/-Versicherte; nach Arbeitsunfall/Berufskrankheit eigene Regeln.", bereich=["D"], title_re=r"Pflegegeld|Pflege zu Hause|Medizinische Hauskrankenpflege", vq=[r"Pflegegeld", r"Pflegebedarf|Stunden", r"Antrag|zuständig"], kq=[r"€|Euro"], zustaendig="BVAEB, wenn sie die Pension/Rente zahlt; sonst PVA/SVS", abh=["rezeptgebuehrenbefreiung"], trigger=["Pflegegeld", "Pflege"]),
 dict(leistung_id="reha_medizinisch", name="Rehabilitation (BVAEB)", kurz="Medizinische, berufliche und soziale Rehabilitation; Antrag für stationäre/ambulante Reha.", bereich=["C"], title_re=r"Rehabilitation|Antrag für eine stationäre", vq=[r"Antrag", r"Voraussetzung|Anspruch|ärztlich", r"Kostenbeitrag|Selbstbehalt|Tag"], kq=[r"Kostenbeitrag|Selbstbehalt|€|Euro|pro Tag"], zustaendig="BVAEB", abh=["reha_onkologisch"], trigger=["Rehabilitation", "Reha"]),
 dict(leistung_id="kur", name="Kur & Gesundheitsvorsorge Aktiv (BVAEB)", kurz="Kur / Gesundheitsvorsorge Aktiv (erweiterte Heilbehandlung); eigene Regeln der BVAEB.", bereich=["C"], title_re=r"Kur & |Kuraufenthalt|Kur und|Genesungsaufenthalte", vq=[r"Antrag", r"Voraussetzung|Anspruch|ärztlich|Dauer", r"Wartefrist|Jahre"], kq=[r"Kostenbeitrag|Selbstbehalt|€|Euro|pro Tag"], zustaendig="BVAEB", trigger=["Kur", "Gesundheitsvorsorge Aktiv"]),
 dict(leistung_id="rezeptgebuehrenbefreiung", name="Rezeptgebühr & Befreiung (BVAEB)", kurz="Rezeptgebühr pro Packung, Obergrenze (Rezeptgebührenkonto) und Befreiung bei hoher finanzieller Belastung.", bereich=["C", "E"], title_re=r"Rezeptgebühr|Befreiung und Nachsicht", vq=[r"Rezeptgebühr", r"befreit|Befreiung", r"Einkommen|Richtsatz|Obergrenze|2 ?%"], kq=[r"Rezeptgebühr.*€|€.*Rezeptgebühr|2 ?%"], zustaendig="BVAEB", trigger=["Rezeptgebühr", "Befreiung"], unterschied="Rezeptgebührenkonto/Obergrenze (2 % des Jahresnettoeinkommens) ist träger-übergreifend; Antragswege je Träger."),
 dict(leistung_id="krankentransport", name="Fahrtkosten, Transportkosten & Flugrettung (BVAEB)", kurz="Kostenübernahme bei medizinisch notwendigen Fahrten/Transporten, meist mit Kostenanteil und Bewilligung.", bereich=["C"], title_re=r"Fahrtkosten|Transportkosten", vq=[r"Transport|Fahrt", r"Bewilligung|ärztlich|Notwendigkeit"], kq=[r"Kostenanteil|Selbstbehalt|€|Euro|Prozent|%"], zustaendig="BVAEB", trigger=["Fahrtkosten", "Transportkosten", "Krankentransport", "Rettung"]),
 dict(leistung_id="heilbehelfe_hilfsmittel", name="Heilbehelfe & Hilfsmittel (BVAEB)", kurz="Brille, Rollstuhl, Hörgerät u. a. auf Verordnung; Kostenanteil und Befreiung vom Kostenanteil.", bereich=["C"], title_re=r"Heilbehelfe|Hilfsmittel|Gebrauchsdauer", vq=[r"Verordnung|ärztlich", r"Bewilligung|Antrag", r"Kostenanteil|Befreiung"], kq=[r"Kostenanteil.*€|€.*Kostenanteil|%|Prozent"], zustaendig="BVAEB", trigger=["Heilbehelf", "Hilfsmittel", "Brille"]),
 dict(leistung_id="wochengeld", name="Wochengeld (BVAEB)", kurz="Wochengeld vor und nach der Geburt; Sonderwochengeld.", bereich=["E"], title_re=r"Wochengeld|Sonderwochengeld|Finanzielles bei der Geburt", vq=[r"Wochengeld", r"Anspruch|Voraussetzung", r"Wochen"], kq=[r"€|Euro|Prozent|%"], fq=[r"Wochen vor|nach der Geburt|Antrag"], zustaendig="BVAEB (für BVAEB-Versicherte)", trigger=["Wochengeld"]),
 dict(leistung_id="krankengeld", name="Krankengeld (BVAEB)", kurz="Krankengeld für Vertragsbedienstete/Angestellte; Rehabilitationsgeld bei vorübergehender Invalidität.", bereich=["E"], title_re=r"Krankengeld|Rehabilitationsgeld|Krankenstand", vq=[r"Krankengeld|Rehabilitationsgeld", r"Anspruch|Voraussetzung|Tag"], kq=[r"€|Euro|Prozent|%"], zustaendig="BVAEB", trigger=["Krankengeld", "Krankenstand"]),
 dict(leistung_id="kostenerstattung_wahlarzt", name="Kostenerstattung (Wahlarzt-Rechnung einreichen) – BVAEB", kurz="Rechnung einreichen und Kostenerstattung für ärztliche Hilfe außerhalb des Kassenvertrags.", bereich=["C", "E"], title_re=r"Kostenerstattung", vq=[r"Kostenerstattung|Rückerstattung|Kostenersatz", r"Rechnung|Beleg", r"Prozent|%|Tarif"], kq=[r"%|Prozent|Tarif"], fq=[r"Frist|Jahre|Monate"], zustaendig="BVAEB", trigger=["Kostenerstattung", "Wahlarzt"]),
 dict(leistung_id="zahnbehandlung_zahnersatz", name="Zahnbehandlung, Zahnspange & Zahnersatz (BVAEB)", kurz="Zahnbehandlung, Zahnspange/Kieferregulierung und Zahnersatz mit Bewilligung/Kostenersatz.", bereich=["C"], title_re=r"Zahn", vq=[r"Bewilligung", r"Kostenersatz|Zuschuss|Kostenanteil", r"Behandlungsbeitrag"], kq=[r"€|Euro|Prozent|%"], zustaendig="BVAEB", trigger=["Zahnersatz", "Zahnspange"]),
 dict(leistung_id="unfall_heilbehandlung", name="Leistungen nach Arbeits-/Dienstunfall & Berufskrankheit (BVAEB)", kurz="Heilbehandlung, Reha, Pflegegeld und Renten nach Dienstunfall/Berufskrankheit.", bereich=["C"], title_re=r"Arbeits- bzw. Dienstunfall|Berufskrankheit|nach Arbeitsunfall|Versehrtenrente", vq=[r"Unfall", r"Anspruch|Voraussetzung|melden"], kq=[r"€|Euro|Prozent|%"], zustaendig="BVAEB (Unfallversicherung für öffentlich Bedienstete, Eisenbahn, Bergbau; sonst AUVA)", trigger=["Dienstunfall", "Berufskrankheit"]),
 dict(leistung_id="unterstuetzungsfonds_bvaeb", name="Unterstützungsfonds (BVAEB)", kurz="Hilfe in finanziellen Notlagen durch den Unterstützungsfonds der BVAEB.", bereich=["E"], title_re=r"Unterstützungsfonds", vq=[r"Notlage|Unterstützung", r"Antrag|Voraussetzung"], kq=[r"€|Euro"], zustaendig="BVAEB", trigger=["Unterstützungsfonds", "Notlage"]),
 dict(leistung_id="auslandsbehandlung_ekvk", name="Auslandsbehandlung: EKVK / Urlaubskrankenschein (BVAEB)", kurz="e-card/EKVK im EU-Ausland; Urlaubskrankenschein für Länder mit Abkommen.", bereich=["C", "F"], title_re=r"EKVK|Urlaub & Ausland|Ausland & Urlaub|Urlaubskrankenschein", vq=[r"EKVK", r"Urlaubskrankenschein", r"Kosten"], kq=[r"Kostenerstattung|Selbstbehalt|€"], zustaendig="BVAEB", trigger=["EKVK", "Ausland"]),
]
def leistungen(docs, pages, cfg):
    import json, pathlib
    forms = [json.loads(l) for l in open(pathlib.Path(__file__).parent / "out/formulare.jsonl")]
    return make_leistungen(SPECS, docs, ["BVAEB"], True, forms)


def stellen_override(docs):
    """Landesstellen/Außenstellen strukturiert aus 'Kundenservicestellen / Landesstellen' (Zeilenmuster: Name / Straße / PLZ Ort / Tel / Mail)."""
    import re
    out, seen = [], set()
    for d in docs:
        if d["title"] != "Kundenservicestellen / Landesstellen" or d["section"] == d["title"]: continue
        bl = {"Wien": "W", "Niederösterreich": "NÖ", "Burgenland": "B", "Steiermark": "ST", "Oberösterreich": "OÖ", "Salzburg": "S", "Kärnten": "K", "Tirol": "T", "Vorarlberg": "V"}.get(d["section"])
        lines = [l.strip() for l in d["text"].split("\n") if l.strip()][1:]
        i = 0
        while i < len(lines):
            if re.match(r"(Landesstelle|Außenstelle|Kundenservice)", lines[i]):
                name = lines[i]; blk = []; i += 1
                while i < len(lines) and not re.match(r"(Landesstelle|Außenstelle|Kundenservice)", lines[i]): blk.append(lines[i]); i += 1
                m = re.search(r"(\d{4}) ([^\n]+)", " \n".join(blk) if False else "\n".join(l for l in blk if re.match(r"\d{4} ", l)))
                street = next((l for l in blk if re.search(r"\d", l) and not re.match(r"\d{4} |050405|\S+@", l)), None)
                tel = next((l for l in blk if l.startswith("050405")), None); mail = next((l for l in blk if "@" in l), None)
                key = (name, street)
                if key in seen: continue
                seen.add(key)
                plz = m.group(1) if m else None
                out.append({"stelle_id": "bvaeb_" + re.sub(r"\W+", "_", f"{name}_{plz or ''}_{d['section']}".lower()).strip("_"), "name": f"BVAEB {name} ({d['section']})", "typ": "traeger",
                    "adresse": ", ".join(x for x in [street, (m.group(0) if m else None)] if x), "plz": plz, "bundesland": bl, "telefon": tel, "email": mail, "url": d["url"],
                    "oeffnungszeiten": "Mo–Do 8–14 Uhr, Fr 8–13 Uhr (telefonisch Mo–Do 7–16, Fr 7–14)", "zustaendig_fuer": ["pflegegeld", "kur", "reha_medizinisch", "rezeptgebuehrenbefreiung", "kostenerstattung_wahlarzt"], "geo": None, "quelle_url": d["url"]})
            else: i += 1
    return out
