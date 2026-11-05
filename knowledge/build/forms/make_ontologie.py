"""Erzeugt ontologie.json (ARCHITEKTUR §8.1.1). Vertrag mit Michi: nur additiv ändern.

Jeder Schlüssel: beschreibung, format, typ, beispiel (fiktive Testperson für die Prüfschleife),
ampel_default (gruen = aus Quelle möglich, rot = nur die Person selbst), michi_fuellt (False = nie).
"""
import json
from pathlib import Path

P = "person"
def k(key, beschreibung, beispiel=None, typ="text", format=None, ampel="gruen", michi=True):
    return key, {"beschreibung": beschreibung, "typ": typ, "format": format, "beispiel": beispiel,
                 "ampel_default": ampel, "michi_fuellt": michi}

def personen_block(prefix, wer, bsp):
    return [
        k(f"{prefix}.anrede", f"Anrede {wer}", bsp.get("anrede")),
        k(f"{prefix}.titel", f"Akademischer Titel {wer}", bsp.get("titel")),
        k(f"{prefix}.vorname", f"Vorname {wer}", bsp["vorname"]),
        k(f"{prefix}.familienname", f"Familienname (Nachname) {wer}", bsp["familienname"]),
        k(f"{prefix}.name_voll", f"Vor- und Familienname {wer} in einem Feld", f'{bsp["vorname"]} {bsp["familienname"]}'),
        k(f"{prefix}.name_voll_umgekehrt", f"Familienname, Vorname {wer} in einem Feld", f'{bsp["familienname"]} {bsp["vorname"]}'),
        k(f"{prefix}.svnr", f"Versicherungsnummer {wer} (10 Ziffern, 4+6: laufende Nr. + Geburtsdatum TTMMJJ)", bsp["svnr"], format="NNNNTTMMJJ"),
        k(f"{prefix}.geburtsdatum", f"Geburtsdatum {wer}", bsp["geburtsdatum"], typ="datum", format="TT.MM.JJJJ"),
        k(f"{prefix}.geburtsjahr", f"Geburtsjahr {wer}", bsp["geburtsdatum"][-4:], typ="zahl", format="JJJJ"),
        k(f"{prefix}.geburtsort", f"Geburtsort {wer}", bsp.get("geburtsort")),
        k(f"{prefix}.geburtsland", f"Geburtsland {wer}", bsp.get("geburtsland")),
        k(f"{prefix}.geburtsname", f"Geburtsname / früherer Name {wer}", bsp.get("geburtsname")),
        k(f"{prefix}.geschlecht", f"Geschlecht {wer} (weiblich|männlich|divers|offen|inter|keine Angabe)", bsp.get("geschlecht"), format="enum"),
        k(f"{prefix}.staatsbuergerschaft", f"Staatsbürgerschaft {wer}", bsp.get("staatsbuergerschaft")),
        k(f"{prefix}.familienstand", f"Familienstand {wer} (ledig|verheiratet|verwitwet|geschieden|eingetragene Partnerschaft …)", bsp.get("familienstand"), format="enum"),
        k(f"{prefix}.familienstand_seit", f"Familienstand seit {wer}", bsp.get("familienstand_seit"), typ="datum", format="TT.MM.JJJJ"),
        k(f"{prefix}.beruf", f"Beruf / Tätigkeit {wer}", bsp.get("beruf")),
    ]

def adresse_block(prefix, wer, a):
    return [
        k(f"{prefix}.strasse", f"Straße {wer}", a["strasse"]),
        k(f"{prefix}.hausnr", f"Hausnummer {wer}", a["hausnr"]),
        k(f"{prefix}.stiege", f"Stiege {wer}", a.get("stiege")),
        k(f"{prefix}.tuer", f"Türnummer {wer}", a.get("tuer")),
        k(f"{prefix}.hausnr_stiege_tuer", f"Hausnr./Stiege/Tür {wer} in einem Feld", "/".join(x for x in [a["hausnr"], a.get("stiege"), a.get("tuer")] if x)),
        k(f"{prefix}.strasse_hausnr", f"Straße mit Hausnr./Stiege/Tür {wer} in einem Feld", f'{a["strasse"]} {a["hausnr"]}/{a.get("tuer","")}'.rstrip("/")),
        k(f"{prefix}.plz", f"Postleitzahl {wer}", a["plz"], format="NNNN"),
        k(f"{prefix}.ort", f"Ort {wer}", a["ort"]),
        k(f"{prefix}.plz_ort", f"PLZ und Ort {wer} in einem Feld", f'{a["plz"]} {a["ort"]}'),
        k(f"{prefix}.land", f"Staat {wer}", a.get("land", "Österreich")),
        k(f"{prefix}.voll", f"Komplette Anschrift {wer} in einem Feld", f'{a["strasse"]} {a["hausnr"]}/{a.get("tuer","")}, {a["plz"]} {a["ort"]}'),
    ]

ANNA = dict(vorname="Anna", familienname="Berger", svnr="1234140348", geburtsdatum="14.03.1948", geschlecht="weiblich",
            staatsbuergerschaft="Österreich", familienstand="verwitwet", familienstand_seit="02.05.2019", geburtsort="Wien",
            geburtsland="Österreich", geburtsname="Huber", beruf="Pensionistin", anrede="Frau")
ANNA_ADR = dict(strasse="Musterstraße", hausnr="12", stiege="1", tuer="4", plz="1030", ort="Wien")
SANDRA = dict(vorname="Sandra", familienname="Berger", svnr="5678210875", geburtsdatum="21.08.1975", geschlecht="weiblich",
              staatsbuergerschaft="Österreich", familienstand="verheiratet", anrede="Frau", beruf="Angestellte")
SANDRA_ADR = dict(strasse="Beispielgasse", hausnr="7", tuer="3", plz="1100", ort="Wien")

keys = []
keys += personen_block("person", "der antragstellenden/versicherten Person", ANNA)
keys += adresse_block("adresse", "(Wohnadresse der Person)", ANNA_ADR)
keys += [
    k("kontakt.telefon", "Telefonnummer der Person", "+43 1 2345678", format="E.164 oder national"),
    k("kontakt.email", "E-Mail-Adresse der Person", "anna.berger@example.org"),
    k("versicherung.traeger", "Zuständiger Krankenversicherungsträger (Kurzname, z. B. ÖGK, SVS, BVAEB)", "ÖGK"),
    k("versicherung.landesstelle", "Landesstelle des Versicherungsträgers", "Wien"),
    k("versicherung.art", "Art der Versicherung (Pension, Erwerbstätigkeit, mitversichert …)", "Pensionistin"),
    k("versicherung.mitversichert", "Ist die Person mitversichert? (ja/nein)", "nein", typ="checkbox"),
]
keys += personen_block("versicherte_person", "der Versicherten, von der die Mitversicherung abgeleitet ist", SANDRA)
keys += adresse_block("versicherte_person.adresse", "der versicherten (hauptversicherten) Person", SANDRA_ADR)
keys += personen_block("vertreter", "der vertretenden Person (Vollmacht/Erwachsenenvertretung/ausfüllende Angehörige)", SANDRA)
keys += adresse_block("vertreter.adresse", "der vertretenden Person", SANDRA_ADR)
keys += [
    k("vertreter.rolle", "Rolle der vertretenden Person (Vorsorgevollmacht|gewählte|gesetzliche|gerichtliche Erwachsenenvertretung|Angehörige)", "Vorsorgevollmacht", format="enum"),
    k("vertreter.beziehung", "Verwandtschaftsverhältnis zur Person (z. B. Tochter)", "Tochter"),
    k("vertreter.telefon", "Telefonnummer der vertretenden Person", "+43 660 1234567"),
    k("vertreter.email", "E-Mail der vertretenden Person", "sandra.berger@example.org"),
    k("kind.vorname", "Vorname des Kindes (Familien-/Kinderformulare)", "Lena"),
    k("kind.familienname", "Familienname des Kindes", "Berger"),
    k("kind.geburtsdatum", "Geburtsdatum des Kindes", "03.02.2015", typ="datum", format="TT.MM.JJJJ"),
    k("kind.svnr", "Versicherungsnummer des Kindes", "4321030215", format="NNNNTTMMJJ"),
    k("partner.vorname", "Vorname Ehe-/Lebenspartner:in", "Karl"),
    k("partner.familienname", "Familienname Ehe-/Lebenspartner:in", "Berger"),
    k("partner.svnr", "Versicherungsnummer Ehe-/Lebenspartner:in", "2345050545", format="NNNNTTMMJJ"),
    k("partner.geburtsdatum", "Geburtsdatum Ehe-/Lebenspartner:in", "05.05.1945", typ="datum", format="TT.MM.JJJJ"),
    k("bank.iban", "IBAN (nur die Person selbst)", "AT61 1904 3002 3457 3201", format="IBAN", ampel="rot", michi=False),
    k("bank.bic", "BIC (nur die Person selbst)", "BKAUATWW", ampel="rot", michi=False),
    k("bank.kontoinhaber", "Kontoinhaber:in (nur die Person selbst)", "Anna Berger", ampel="rot", michi=False),
    k("bank.institut", "Name des Kreditinstituts", "Musterbank", ampel="rot", michi=False),
    k("pension.bezieht", "Bezieht eine Pension (ja/nein)", "ja", typ="checkbox"),
    k("pension.traeger", "Pensionsauszahlende Stelle (z. B. PVA)", "PVA"),
    k("pension.art", "Art der Pension (Alters-, Witwen-, Invaliditätspension …)", "Alterspension"),
    k("pflegegeld.bezieht", "Bezieht Pflegegeld (ja/nein)", "nein", typ="checkbox"),
    k("pflegegeld.stufe", "Pflegegeldstufe 1–7", "2", typ="zahl"),
    k("pflegegeld.traeger", "Auszahlende Stelle des Pflegegelds", "PVA"),
    k("arbeitgeber.name", "Name des Dienstgebers", "Muster GmbH"),
    k("arbeitgeber.adresse", "Anschrift des Dienstgebers", "Industriestraße 1, 1220 Wien"),
    k("arbeitgeber.telefon", "Telefon des Dienstgebers", "+43 1 9876543"),
    k("arbeitgeber.beitragskontonummer", "Beitragskontonummer des Dienstgebers", "123456789"),
    k("unternehmen.name", "Firmenwortlaut / Betrieb (Selbständige, SVS)", "Muster e.U."),
    k("unternehmen.gisa", "GISA-Zahl / Gewerbe", "12345678"),
    k("unternehmen.uid", "UID-Nummer", "ATU12345678"),
    k("aufenthalt.temporaer.voll", "Vorübergehende Aufenthaltsadresse (Heim, Krankenhaus, Reha) in einem Feld", "Reha-Zentrum Kurpark, Kurpark 3, 2500 Baden"),
    k("aufenthalt.temporaer.strasse", "Vorübergehende Aufenthaltsadresse: Straße/Nr.", "Kurpark 3"),
    k("aufenthalt.temporaer.plz", "Vorübergehende Aufenthaltsadresse: PLZ", "2500", format="NNNN"),
    k("aufenthalt.temporaer.ort", "Vorübergehende Aufenthaltsadresse: Ort", "Baden"),
    k("aufenthalt.temporaer.von", "Vorübergehender Aufenthalt von", "01.12.2026", typ="datum", format="TT.MM.JJJJ"),
    k("aufenthalt.temporaer.bis", "Vorübergehender Aufenthalt bis", "21.12.2026", typ="datum", format="TT.MM.JJJJ"),
    k("datum.heute", "Datum der Antragstellung (heute; Person prüft am Tag der Unterschrift)", "05.11.2026", typ="datum", format="TT.MM.JJJJ", ampel="gelb"),
    k("ort.heute", "Ort der Antragstellung (meist Wohnort)", "Wien", ampel="gelb"),
    k("ort_datum.heute", "Ort und Datum in einem Feld", "Wien, 05.11.2026", ampel="gelb"),
    k("unterschrift.person", "Unterschrift der Person – füllt Michi NIE", None, typ="unterschrift", ampel="rot", michi=False),
    k("unterschrift.vertreter", "Unterschrift der vertretenden Person – füllt Michi NIE", None, typ="unterschrift", ampel="rot", michi=False),
    k("unterschrift.sonstige", "Andere Unterschrift/Stempel (Dienstgeber, Behörde) – füllt Michi NIE", None, typ="unterschrift", ampel="rot", michi=False),
    k("einkommen.angaben", "Angaben zu Einkommen/Vermögen – nur die Person selbst", None, ampel="rot", michi=False),
    k("arzt.angaben", "Ärztliche Angaben (Diagnose, Befund, Verordnung, Stempel) – füllt Michi NIE", None, ampel="rot", michi=False),
    k("arzt.name", "Name der Ärztin/des Arztes – füllt Michi NIE (wer=arzt)", None, ampel="rot", michi=False),
    k("medizinisch.angaben", "Medizinische Angaben der Person (Leiden, Beschwerden, Medikamente, Einschränkungen) – Michi füllt nie, nur die Person bzw. Ärzt:in", None, ampel="rot", michi=False),
    k("behoerde.vermerk", "Vom Träger/Amt auszufüllen (Eingangsstempel, Aktenzahl) – nie füllen", None, ampel="rot", michi=False),
]
ont = {"version": "1.0", "stand": "2026-11-05",
       "hinweis": "Vertrag mit Michi (ARCHITEKTUR §8.1.1): Schlüssel werden nur additiv geändert. Beispiele sind eine fiktive Testperson (Anna Berger, Tochter Sandra als Vertreterin) für die Prüfschleife.",
       "regeln": {"michi_fuellt_nie": ["unterschrift.*", "arzt.*", "medizinisch.*", "behoerde.*", "einkommen.*"],
                  "nur_person_selbst": ["bank.*", "einkommen.*", "unterschrift.*"]},
       "schluessel": dict(keys)}
assert len(ont["schluessel"]) == len(keys), "doppelter Schlüssel"
Path(__file__).with_name("ontologie.json").write_text(json.dumps(ont, ensure_ascii=False, indent=1) + "\n")
print(len(keys), "Schlüssel")
