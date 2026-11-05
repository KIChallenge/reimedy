"""Eingefrorene Zuordnungen für die Demo-Formulare (Goldstandard = Michi b5-comms/server/forms/mappings.py,
ergänzt um Review). Wird in semantik_frozen.json gemerged (LLM-Zuordnungen bleiben erhalten)."""
import json
from pathlib import Path

G = "goldstandard_b5"
R = "review"
def o(sem, h=G, **kw):
    d = {"semantik": sem, "herkunft": h}
    if sem is None:
        d["wer"] = "versicherte"
    d.update(kw)
    return d

DEMO = {
 "pva_pal080": {
  "Antrag Pflg": o(None, pflicht=True), "VSNR_1": o("person.svnr", pflicht=True), "Fam.Name": o("person.familienname", pflicht=True),
  "Vorname": o("person.vorname", pflicht=True), "Geburtsdatum": o("person.geburtsdatum", pflicht=True),
  "Geschlecht": o("person.geschlecht"), "Stabü": o("person.staatsbuergerschaft", optionen_semantik={"01": "Österreich"}),
  "andere Staatsbürgerschaft": o(None, R),
  "Personenstand": o("person.familienstand", optionen_semantik={"01": "ledig", "02": "verheiratet", "03": "verwitwet", "04": "geschieden", "05": "eingetragene Partnerschaft"}),
  "Personenstand seit": o("person.familienstand_seit"), "Adresse Straße": o("adresse.strasse", pflicht=True),
  "Hausnummer, Stiege, Tür": o("adresse.hausnr_stiege_tuer", pflicht=True), "PLZ": o("adresse.plz", pflicht=True),
  "Ort": o("adresse.ort", pflicht=True), "Land": o("adresse.land"), "voruebergehend": o("aufenthalt.temporaer.voll", R),
  "Telefon": o("kontakt.telefon"), "Email": o("kontakt.email", R), "Andere Person": o(None),
  "Familienname andere": o("vertreter.familienname"), "Vorname andere Person": o("vertreter.vorname"),
  "Titel2": o("vertreter.titel", R), "Adresse Straße 1": o("vertreter.adresse.strasse"),
  "Hausnummer, Stiege, Tür2": o("vertreter.adresse.hausnr_stiege_tuer"), "PLZ 1": o("vertreter.adresse.plz"),
  "Ort 1": o("vertreter.adresse.ort"), "Land2": o("vertreter.adresse.land", R), "Telefon 1": o("vertreter.telefon"),
  "Email2": o("vertreter.email", R),
  "Leiden": o("medizinisch.angaben", wer="versicherte"), "Leiden2": o("medizinisch.angaben", wer="versicherte"),
  "Medikamente": o("medizinisch.angaben", wer="versicherte"), "Medikamente2": o("medizinisch.angaben", wer="versicherte"),
  "Datum_1": o("datum.heute"),
 },
 "antrag_reha_kur": {
  "zuständiger SV-träger": o("versicherung.traeger"), "VSNR_1": o("person.svnr", pflicht=True),
  "Patient(in)": o("person.name_voll_umgekehrt", pflicht=True), "Anschrift": o("adresse.voll"),
  "Anschrift Patient(in)": o("adresse.voll"), "Personenstand": o("person.familienstand"), "Telefonnummer": o("kontakt.telefon"),
  "VSNR_2": o("versicherte_person.svnr", R), "Versicherte(r)": o("versicherte_person.name_voll_umgekehrt", R),
  "Versicherte(r) beschäftigt": o("arbeitgeber.name", R), "Pensionsversicherung": o("pension.bezieht", optionen_semantik={"j": "ja", "n": "nein"}),
  "Pensionsversicherungsträger": o("pension.traeger"), "Pflegegeld": o("pflegegeld.bezieht", optionen_semantik={"j": "ja", "n": "nein"}),
  "Von welcher Anstalt": o("pflegegeld.traeger", R), "Stufe1": o("pflegegeld.stufe", R), "Datum": o("datum.heute"),
  "VSNR_1#p1": o("person.svnr"), "Familienname": o("person.familienname"), "Vorname": o("person.vorname"),
  "Geburtsjahr": o("person.geburtsjahr"), "Geschlecht": o("person.geschlecht", optionen_semantik={"w": "weiblich", "m": "männlich"}),
 },
 "oegk_fahrtkosten_wien": {
  "Patient/in": o("person.name_voll_umgekehrt", pflicht=True), "Versicherungsnummer1": o("person.svnr", pflicht=True),
  "Adresse": o("adresse.voll", pflicht=True), "Versicherte/r": o("versicherte_person.name_voll_umgekehrt", R),
  "Versicherungsnummer2": o("versicherte_person.svnr", R), "Behandler/in": o(None), "Art der Behandlung": o("medizinisch.angaben", R, wer="versicherte"),
  "Tatsächliche Kosten": o(None), "IBAN": o("bank.iban"), "Ort/Datum": o("ort_datum.heute"),
 },
 "fsw_antrag_foerderung": {
  "Familienname Titel KundIn": o("person.familienname", pflicht=True), "Vorname KundIn": o("person.vorname", pflicht=True),
  "Geschlecht KundIn": o("person.geschlecht"), "Geburtsdatum KundIn": o("person.geburtsdatum", pflicht=True),
  "Geburtsland KundIn": o("person.geburtsland"), "Familienstand": o("person.familienstand"),
  "Familienstand seit": o("person.familienstand_seit"), "Telefonnummer KundIn": o("kontakt.telefon"),
  "Strassennamen Lebensmittelpunkt": o("adresse.strasse", pflicht=True), "Hausnr Lebensmittelpunkt": o("adresse.hausnr", pflicht=True),
  "Stiege Lebensmittelpunkt": o("adresse.stiege"), "Tuernr Lebensmittelpunkt": o("adresse.tuer"),
  "PLZ Lebensmittelpunkt": o("adresse.plz", pflicht=True), "Ort Lebensmittelpunkt": o("adresse.ort", pflicht=True),
  "Familienname Vertrauensperson": o("vertreter.familienname"), "Vorname Vertrauensperson": o("vertreter.vorname"),
  "Telefonnummer Vertrauensperson": o("vertreter.telefon"), "Einkommen": o("einkommen.angaben"),
  "Datum Unterschrift KundIn 4": o("datum.heute"), "Unterschriftsfeld KundIn": o("unterschrift.person"),
  "IBAN 3": o("bank.iban"), "KontoinhaberIn 3": o("bank.kontoinhaber"), "IBAN 4": o("bank.iban", R), "KontoinhaberIn 4": o("bank.kontoinhaber", R),
  "Keine Unterhaltsverpflichtung Unterhaltsberechtigung PuB": o("einkommen.angaben"), "Vermögen": o("einkommen.angaben"),
  "Stiege ZustellbevollmaechtigteR 2": o("vertreter.adresse.stiege", R), "Tuernr ZustellbevollmaechtigteR 2": o("vertreter.adresse.tuer", R),
  "Schule Adresse": o(None, R), "Datum Unterschrift erste Zeugin / erster Zeuge 3": o(None, R, wer="unterschrift"),
  "Datum Unterschrift zweite ZeugIn 3": o(None, R, wer="unterschrift"),
 },
 "fsw_einrichtungswunsch": {"Name Kontaktaufnahme 3": o("vertreter.name_voll", R)},
 "fsw_bedarfsmeldung_wg": {"Unterschrift der betroffenen Person oder einer für diese zur Vertretung befugten Person 4": o(None, R, wer="unterschrift")},
 "antrag_ahv_reha_unfall": {},
 "svs_8e5303e0b6": {"f01_010": o(None, R), "f01_011": o(None, R), "f01_025": o(None, R), "f01_026": o(None, R), "f01_009": o(None, R)},
 "bvaeb_9096928de6": {
  "adresse": o(None, R), "Name_1": o("person.name_voll_umgekehrt", R, pflicht=True), "Adresse": o("adresse.voll", R, pflicht=True),
  "Festnetz": o("kontakt.telefon", R), "Handy": o(None, R), "Gebdat_2": o(None, R),
  **{f"Namen_{i}": o(None, R) for i in range(2, 10)}, **{f"Famstand_{i}": o(None, R) for i in range(2, 10)},
  "ich_leide": o("medizinisch.angaben", R, wer="versicherte"),
  "Famstand": o("person.familienstand", R), "traeger": o(None, R), "unterorganisation": o("versicherung.landesstelle", R),
 },
}
p = Path(__file__).with_name("semantik_frozen.json")
cur = json.loads(p.read_text()) if p.exists() else {}
for fid, m in DEMO.items():
    cur.setdefault(fid, {}).update(m)
p.write_text(json.dumps(cur, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
print("frozen:", {k: len(v) for k, v in cur.items() if k in DEMO})
