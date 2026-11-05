"""Tests für knowledge/build/forms (ARCHITEKTUR §8.1).  uv run --no-project --with pytest --with pymupdf pytest knowledge/build/forms

- Ontologie: Vertrag (Pflichtschlüssel aus §8.1.1, Sperren)
- Goldstandard-Regression: Michi b5-comms/server/forms/mappings.py (4 handgemappte Formulare)
- Harte Grenze: arzt/Unterschrift/medizinisch/Bank/Einkommen/Behörde nie michi_fuellt
- Demo-Formulare geprüft, Empfänger deterministisch, forms_api-Schnittstelle wie in search.py erwartet
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# Eigener Modulname, damit sys.modules["forms_api"] frei bleibt (search.py lädt das Modul selbst, test_build.py ersetzt es).
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("forms_api_test", HERE / "forms_api.py")
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

GESPERRT = ("arzt.", "medizinisch.", "unterschrift.", "einkommen.", "bank.", "behoerde.")
DEMO = ["pva_pal080", "antrag_reha_kur", "antrag_ahv_reha_unfall", "oegk_fahrtkosten_wien", "fsw_antrag_foerderung",
        "fsw_einrichtungswunsch", "fsw_bedarfsmeldung_wg", "bvaeb_9096928de6", "svs_8e5303e0b6"]

# Goldstandard: (formular_id, AcroForm-Name) → erwarteter Ontologie-Schlüssel (None = Michi füllt nicht / fragt nach).
# Abgeleitet aus Michi b5-comms mappings.py (plan_pal080, plan_reha_kur, plan_fahrtkosten, plan_fsw).
GOLD = {
    "pva_pal080": {
        "VSNR_1": "person.svnr", "Fam.Name": "person.familienname", "Vorname": "person.vorname",
        "Geburtsdatum": "person.geburtsdatum", "Geschlecht": "person.geschlecht", "Stabü": "person.staatsbuergerschaft",
        "Personenstand": "person.familienstand", "Personenstand seit": "person.familienstand_seit",
        "Adresse Straße": "adresse.strasse", "Hausnummer, Stiege, Tür": "adresse.hausnr_stiege_tuer", "PLZ": "adresse.plz",
        "Ort": "adresse.ort", "Land": "adresse.land", "Telefon": "kontakt.telefon",
        "Familienname andere": "vertreter.familienname", "Vorname andere Person": "vertreter.vorname",
        "Adresse Straße 1": "vertreter.adresse.strasse", "Hausnummer, Stiege, Tür2": "vertreter.adresse.hausnr_stiege_tuer",
        "PLZ 1": "vertreter.adresse.plz", "Ort 1": "vertreter.adresse.ort", "Telefon 1": "vertreter.telefon",
        "Leiden": "GESPERRT", "Medikamente": "GESPERRT", "Medikamente2": "GESPERRT", "Datum_1": "datum.heute",
        "Antrag Pflg": None, "Andere Person": None,
    },
    "antrag_reha_kur": {
        "zuständiger SV-träger": "versicherung.traeger", "VSNR_1": "person.svnr", "Patient(in)": "person.name_voll_umgekehrt",
        "Anschrift": "adresse.voll", "Anschrift Patient(in)": "adresse.voll", "Personenstand": "person.familienstand",
        "Telefonnummer": "kontakt.telefon", "Pensionsversicherung": "pension.bezieht", "Pensionsversicherungsträger": "pension.traeger",
        "Pflegegeld": "pflegegeld.bezieht", "Datum": "datum.heute", "Familienname": "person.familienname",
        "Vorname": "person.vorname", "Geburtsjahr": "person.geburtsjahr", "Geschlecht": "person.geschlecht",
        "Antragsrelevante Diagnose": "GESPERRT", "Befunde": "GESPERRT",
    },
    "oegk_fahrtkosten_wien": {
        "Patient/in": "person.name_voll_umgekehrt", "Versicherungsnummer1": "person.svnr", "Adresse": "adresse.voll",
        "IBAN": "GESPERRT", "Ort/Datum": "ort_datum.heute", "Behandler/in": None, "Tatsächliche Kosten": None,
    },
    "fsw_antrag_foerderung": {
        "Familienname Titel KundIn": "person.familienname", "Vorname KundIn": "person.vorname", "Geschlecht KundIn": "person.geschlecht",
        "Geburtsdatum KundIn": "person.geburtsdatum", "Geburtsland KundIn": "person.geburtsland", "Familienstand ": "person.familienstand",
        "Familienstand seit": "person.familienstand_seit", "Telefonnummer KundIn": "kontakt.telefon",
        "Strassennamen Lebensmittelpunkt": "adresse.strasse", "Hausnr Lebensmittelpunkt": "adresse.hausnr",
        "Stiege Lebensmittelpunkt": "adresse.stiege", "Tuernr Lebensmittelpunkt": "adresse.tuer", "PLZ Lebensmittelpunkt": "adresse.plz",
        "Ort Lebensmittelpunkt": "adresse.ort", "Familienname Vertrauensperson": "vertreter.familienname",
        "Vorname Vertrauensperson": "vertreter.vorname", "Telefonnummer Vertrauensperson": "vertreter.telefon",
        "Einkommen": "GESPERRT", "Datum Unterschrift KundIn 4": "datum.heute", "Unterschriftsfeld KundIn": "GESPERRT",
        "IBAN 3": "GESPERRT", "KontoinhaberIn 3": "GESPERRT", "Vermögen": "GESPERRT",
    },
}


def _tpl(fid):
    t = F.template(fid, nur_geprueft=False)
    assert t, f"kein Template für {fid}"
    return t


def _alle_templates():
    return [json.loads(p.read_text()) for p in sorted((HERE / "templates").glob("*.json"))]


# ------------------------------------------------------------------ Ontologie
def test_ontologie_vertrag():
    o = F.ontologie()["schluessel"]
    pflicht = ["person.vorname", "person.familienname", "person.svnr", "person.geburtsdatum", "person.geschlecht",
               "person.staatsbuergerschaft", "person.familienstand", "adresse.strasse", "adresse.hausnr", "adresse.stiege",
               "adresse.tuer", "adresse.plz", "adresse.ort", "adresse.land", "kontakt.telefon", "kontakt.email",
               "versicherung.traeger", "vertreter.vorname", "vertreter.familienname", "vertreter.rolle", "versicherte_person.svnr",
               "bank.iban", "bank.bic", "bank.kontoinhaber", "pension.bezieht", "pension.traeger", "pflegegeld.bezieht",
               "pflegegeld.stufe", "pflegegeld.traeger", "arbeitgeber.name", "aufenthalt.temporaer.von", "datum.heute", "ort.heute",
               "unterschrift.person", "arzt.angaben"]
    for k in pflicht:
        assert k in o, k
    for k, v in o.items():
        assert {"beschreibung", "typ", "format", "beispiel", "ampel_default", "michi_fuellt"} <= set(v), k
        if k.startswith(GESPERRT):
            assert v["michi_fuellt"] is False, k


# ------------------------------------------------------------------ Goldstandard (Michi b5-comms)
@pytest.mark.parametrize("fid", list(GOLD))
def test_goldstandard_regression(fid):
    t = _tpl(fid)
    by_acro = {}
    for f in t["felder"]:
        by_acro.setdefault(f["acro_name"], f)
    fehler = []
    for acro, erwartet in GOLD[fid].items():
        f = by_acro.get(acro)
        if f is None:
            fehler.append(f"{acro}: Feld fehlt")
            continue
        if erwartet == "GESPERRT":
            if f["michi_fuellt"]:
                fehler.append(f"{acro}: müsste gesperrt sein, ist {f['semantik']}")
        elif erwartet is None:
            if f["michi_fuellt"]:
                fehler.append(f"{acro}: Michi soll nicht füllen, ist {f['semantik']}")
        elif f["semantik"] != erwartet:
            fehler.append(f"{acro}: {f['semantik']} ≠ {erwartet}")
    assert not fehler, fehler


# ------------------------------------------------------------------ Harte Grenze
def test_harte_grenze_nie_arzt_unterschrift_medizin():
    for t in _alle_templates():
        for f in t["felder"]:
            if not f["michi_fuellt"]:
                continue
            assert f["wer"] == "versicherte", (t["formular_id"], f["feld_id"], f["wer"])
            assert f["typ"] != "unterschrift", (t["formular_id"], f["feld_id"])
            assert f["semantik"] and not f["semantik"].startswith(GESPERRT), (t["formular_id"], f["feld_id"], f["semantik"])


def test_template_schema():
    req = {"formular_id", "sha256", "pages", "quelle", "felder", "geprueft"}
    freq = {"feld_id", "acro_name", "page", "bbox", "typ", "label_wörtlich", "semantik", "wer", "pflicht", "max_zeichen", "format"}
    for t in _alle_templates():
        assert req <= set(t), t["formular_id"]
        assert t["quelle"] in ("acroform", "generiert", "keine")
        for f in t["felder"]:
            assert freq <= set(f), (t["formular_id"], f.get("feld_id"))
            assert len(f["bbox"]) == 4 and f["bbox"][0] <= f["bbox"][2] and f["bbox"][1] <= f["bbox"][3]
            assert f["typ"] in ("text", "checkbox", "radio", "datum", "zahl", "unterschrift", "auswahl")
            assert f["wer"] in ("versicherte", "arzt", "behoerde", "unterschrift")


# ------------------------------------------------------------------ Demo + API
@pytest.mark.parametrize("fid", DEMO)
def test_demo_formulare_geprueft(fid):
    t = F.template(fid)
    assert t and t["geprueft"], f"{fid} nicht geprüft"
    assert sum(1 for f in t["felder"] if f["michi_fuellt"]) >= 3
    assert "pruefung" in t and t["pruefung"].get("ok")


def test_ungeprueft_wird_nicht_ausgeliefert():
    for t in _alle_templates():
        if not t.get("geprueft"):
            assert F.template(t["formular_id"]) is None or F.template(t["formular_id"])["sha256"] != t["sha256"]
            assert F.pdf(t["formular_id"]) is None
    assert F.template("gibt_es_nicht") is None and F.template("../etc/passwd") is None


def test_empfaenger_regeln():
    e = F.empfaenger("pva_pal080", plz="1030")
    assert e["traeger_id"] == "pva" and e["zustaendig"]["stelle"]["stelle_id"] == "pva_w"
    assert e["aufloesung"] == "auszahlende_stelle" and e["rueckfragen"]
    assert F.empfaenger("pva_pal080", plz="8010", traeger="SVS")["zustaendig"]["stelle"]["stelle_id"] == "svs_st"
    e = F.empfaenger("oegk_fahrtkosten_wien", plz="1030")
    assert e["zustaendig"]["stelle"]["stelle_id"] == "oegk_w" and "1100 Wien" in e["zustaendig"]["stelle"]["post_adresse"]
    assert F.empfaenger("fsw_antrag_foerderung", plz="1030")["zustaendig"]["status"] == "zentrale"
    assert F.empfaenger("fsw_antrag_foerderung", plz="3100")["zustaendig"]["status"] == "nicht_zustaendig"
    assert F.empfaenger("antrag_reha_kur", plz="1030", traeger="PVA")["zustaendig"]["stelle"]["stelle_id"] == "pva_w"
    assert F.empfaenger("antrag_reha_kur", plz="1030")["rueckfragen"]
    assert F.empfaenger("gibt_es_nicht") is None


def test_empfaenger_fuer_alle_lotse_formulare():
    live = [json.loads(l) for l in (HERE.parent / "links" / "formulare_live.jsonl").open()]
    ids = {r["formular_id"] for r in live if r.get("lotse_zeigen")}
    have = {json.loads(l)["formular_id"] for l in (HERE / "empfaenger.jsonl").open()}
    assert ids <= have, sorted(ids - have)[:10]
    for fid in ids:
        e = F.empfaenger(fid, plz="1030", traeger="ÖGK")
        assert e["aufloesung"] in ("fix", "landesstelle_nach_plz", "auszahlende_stelle", "nach_versicherung", "unbekannt")
        assert e["kanal"]


def test_pdf_kopien():
    pdfs = list((HERE / "pdf").glob("*.pdf"))
    for p in pdfs:
        fid = p.name.split("@")[0]
        r = F.pdf(fid)
        if r is None:  # Kopie einer älteren Version
            continue
        data, ct, name = r
        assert data[:5] == b"%PDF-" and ct == "application/pdf" and name.endswith(".pdf")
    fitz = pytest.importorskip("pymupdf")
    for p in pdfs[:5]:
        assert any(True for pg in fitz.open(p) for _ in pg.widgets())


def test_fill_regression_pal080():
    pytest.importorskip("pymupdf")
    t = _tpl("pva_pal080")
    pdf = HERE / "cache" / f"{t['sha256']}.pdf"
    if not pdf.exists():
        pytest.skip("PDF-Cache fehlt (fetch_pdfs.py)")
    from fill import fill
    werte = {k: v["beispiel"] for k, v in F.ontologie()["schluessel"].items() if v["beispiel"]}
    out, prot = fill(t, pdf.read_bytes(), werte)
    st = {p["feld_id"]: p["status"] for p in prot}
    assert st.get("VSNR_1") == "ok" and st.get("Fam.Name") == "ok" and st.get("Personenstand") == "ok"
    assert "Leiden" not in st and "IBAN" not in st
    import pymupdf
    vals = {w.field_name: w.field_value for pg in pymupdf.open(stream=out, filetype="pdf") for w in pg.widgets()}
    assert vals["Fam.Name"] == "Berger" and vals["Personenstand"] in ("03", "/03")
