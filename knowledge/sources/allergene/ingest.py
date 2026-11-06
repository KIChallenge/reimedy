#!/usr/bin/env -S uv run --python 3.11
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""allergene: kuratierte Liste häufiger Allergene und Unverträglichkeiten -> out/codes.jsonl (Schema E, system "Allergen").

Aufruf:  uv run knowledge/sources/allergene/ingest.py

Wofür: Vorschläge im Profil (Allergien und Unverträglichkeiten). Medikamente kommen NICHT von hier, sondern
als Wirkstoff aus ATC (svbox_local) und als Markenname live aus dem BASG-Register auf dem reimedy-server.
Nur Namen und Synonyme zum Finden – keine Aussage über Häufigkeit, Schwere oder Kreuzreaktionen.
Nur Standardbibliothek, kein Netzwerk.
"""
from __future__ import annotations

import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

SRC = "allergene"
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
STAND = "2026-11-06"
# Kennzeichnungspflichtige Lebensmittelallergene (14), Anhang II der EU-Verordnung 1169/2011 (LMIV)
LMIV = "https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32011R1169"
KURATIERT = "kuratiert (Lotse-Team, 06.11.2026)"

# (code, label_de, kategorie, synonyme, snomed)  – snomed nur, wo am reimedy-server geprüft
ALLERGENE: list[tuple[str, str, str, list[str], str | None]] = [
    # --- Lebensmittel: die 14 kennzeichnungspflichtigen Allergene (LMIV Anhang II) ---
    ("LM-GLUTEN", "Glutenhaltiges Getreide", "Lebensmittel", ["Gluten", "Weizen", "Roggen", "Gerste", "Hafer", "Dinkel", "Kamut", "Getreide"], None),
    ("LM-KREBSTIERE", "Krebstiere", "Lebensmittel", ["Garnelen", "Shrimps", "Krabben", "Hummer", "Krebse", "Scampi", "Meeresfrüchte"], None),
    ("LM-EI", "Eier", "Lebensmittel", ["Ei", "Hühnerei", "Eiweiß", "Eigelb"], None),
    ("LM-FISCH", "Fisch", "Lebensmittel", ["Fische"], None),
    ("LM-ERDNUSS", "Erdnüsse", "Lebensmittel", ["Erdnuss", "Erdnussbutter", "Nuss", "Nüsse"], "91935009"),
    ("LM-SOJA", "Soja", "Lebensmittel", ["Sojabohnen", "Tofu", "Sojamilch"], None),
    ("LM-MILCH", "Milch (Milcheiweiß)", "Lebensmittel", ["Kuhmilch", "Milcheiweiß", "Kasein", "Molke", "Milchprodukte"], None),
    ("LM-SCHALENFRUECHTE", "Nüsse (Schalenfrüchte)", "Lebensmittel",
     ["Nuss", "Nüsse", "Baumnüsse", "Schalenfrüchte", "Haselnuss", "Walnuss", "Mandeln", "Cashew", "Pistazien",
      "Pekannuss", "Paranuss", "Macadamia"], "91934008"),
    ("LM-HASELNUSS", "Haselnuss", "Lebensmittel", ["Haselnüsse", "Nuss", "Nüsse"], None),
    ("LM-WALNUSS", "Walnuss", "Lebensmittel", ["Walnüsse", "Nuss", "Nüsse"], None),
    ("LM-MANDEL", "Mandeln", "Lebensmittel", ["Mandel", "Nuss", "Nüsse"], None),
    ("LM-CASHEW", "Cashewkerne", "Lebensmittel", ["Cashew", "Cashewnuss", "Nuss", "Nüsse"], None),
    ("LM-SELLERIE", "Sellerie", "Lebensmittel", ["Knollensellerie", "Staudensellerie", "Selleriesalz"], None),
    ("LM-SENF", "Senf", "Lebensmittel", ["Senfsaat"], None),
    ("LM-SESAM", "Sesam", "Lebensmittel", ["Sesamsamen", "Tahin", "Sesamöl"], None),
    ("LM-SULFITE", "Schwefeldioxid und Sulfite", "Lebensmittel", ["Sulfite", "Schwefel", "Schwefeldioxid", "E220", "Wein", "Trockenfrüchte"], None),
    ("LM-LUPINE", "Lupinen", "Lebensmittel", ["Lupine", "Lupinenmehl"], None),
    ("LM-WEICHTIERE", "Weichtiere", "Lebensmittel", ["Muscheln", "Schnecken", "Tintenfisch", "Kalmar", "Austern", "Meeresfrüchte"], None),
    # --- weitere häufige Lebensmittel ---
    ("LM-KIWI", "Kiwi", "Lebensmittel", ["Kiwis"], None),
    ("LM-APFEL", "Apfel", "Lebensmittel", ["Äpfel", "Obst"], None),
    ("LM-STEINOBST", "Steinobst", "Lebensmittel", ["Pfirsich", "Kirsche", "Marille", "Aprikose", "Zwetschke", "Pflaume", "Obst"], None),
    ("LM-ERDBEERE", "Erdbeeren", "Lebensmittel", ["Erdbeere", "Obst"], None),
    ("LM-TOMATE", "Tomaten", "Lebensmittel", ["Tomate", "Paradeiser"], None),
    ("LM-KAROTTE", "Karotten", "Lebensmittel", ["Karotte", "Möhre", "Gemüse"], None),
    # --- Unverträglichkeiten (keine Allergie im engeren Sinn) ---
    ("UV-LAKTOSE", "Laktoseintoleranz", "Unverträglichkeit", ["Laktose", "Lactose", "Milchzucker", "Laktoseunverträglichkeit"], None),
    ("UV-FRUKTOSE", "Fruktoseintoleranz", "Unverträglichkeit", ["Fruktose", "Fructose", "Fruchtzucker", "Fruktosemalabsorption"], None),
    ("UV-HISTAMIN", "Histaminintoleranz", "Unverträglichkeit", ["Histamin"], None),
    ("UV-GLUTEN", "Zöliakie (Glutenunverträglichkeit)", "Unverträglichkeit", ["Zöliakie", "Gluten", "Glutenunverträglichkeit", "Sprue"], None),
    ("UV-SORBIT", "Sorbitunverträglichkeit", "Unverträglichkeit", ["Sorbit", "Sorbitol", "Zuckeraustauschstoffe"], None),
    ("UV-GLUTAMAT", "Glutamat-Unverträglichkeit", "Unverträglichkeit", ["Glutamat", "Geschmacksverstärker", "E621"], None),
    # --- Pollen, Staub, Tiere, Schimmel ---
    ("IN-POLLEN", "Pollen (Heuschnupfen)", "Pollen und Umwelt", ["Pollen", "Heuschnupfen", "Pollenallergie", "Blütenstaub"], "300910009"),
    ("IN-BIRKE", "Birkenpollen", "Pollen und Umwelt", ["Birke", "Baumpollen", "Pollen"], None),
    ("IN-ERLE-HASEL", "Erlen- und Haselpollen", "Pollen und Umwelt", ["Erle", "Hasel", "Haselpollen", "Baumpollen", "Pollen"], None),
    ("IN-GRAESER", "Gräserpollen", "Pollen und Umwelt", ["Gräser", "Gras", "Roggenpollen", "Pollen"], None),
    ("IN-AMBROSIA", "Ragweed (Ambrosia)", "Pollen und Umwelt", ["Ambrosia", "Ragweed", "Traubenkraut", "Pollen"], None),
    ("IN-BEIFUSS", "Beifuß", "Pollen und Umwelt", ["Beifuss", "Kräuterpollen", "Pollen"], None),
    ("IN-MILBEN", "Hausstaubmilben", "Pollen und Umwelt", ["Hausstaub", "Milben", "Staub", "Hausstauballergie"], "232350006"),
    ("IN-SCHIMMEL", "Schimmelpilze", "Pollen und Umwelt", ["Schimmel", "Schimmelsporen", "Pilzsporen"], None),
    ("TI-KATZE", "Katzenhaare", "Tiere", ["Katze", "Katzen", "Tierhaare"], None),
    ("TI-HUND", "Hundehaare", "Tiere", ["Hund", "Hunde", "Tierhaare"], None),
    ("TI-PFERD", "Pferdehaare", "Tiere", ["Pferd", "Pferde", "Tierhaare"], None),
    ("TI-NAGER", "Nagetiere (Meerschweinchen, Hamster, Kaninchen)", "Tiere", ["Meerschweinchen", "Hamster", "Kaninchen", "Maus", "Tierhaare"], None),
    ("TI-FEDERN", "Vogelfedern", "Tiere", ["Federn", "Vögel", "Bettfedern", "Daunen"], None),
    # --- Insekten ---
    ("IS-BIENE", "Bienengift", "Insekten", ["Biene", "Bienenstich", "Insektengift", "Insektenstich"], None),
    ("IS-WESPE", "Wespengift", "Insekten", ["Wespe", "Wespenstich", "Insektengift", "Insektenstich"], "91941000"),
    # --- Kontakt ---
    ("KO-LATEX", "Latex", "Kontakt", ["Naturlatex", "Gummi", "Latexhandschuhe", "Kautschuk"], "300916003"),
    ("KO-NICKEL", "Nickel", "Kontakt", ["Modeschmuck", "Metall", "Kontaktallergie"], None),
    ("KO-KOBALT", "Kobalt", "Kontakt", ["Metall", "Kontaktallergie"], None),
    ("KO-CHROM", "Chrom (Chromat)", "Kontakt", ["Chromat", "Leder", "Zement", "Kontaktallergie"], None),
    ("KO-DUFTSTOFFE", "Duftstoffe", "Kontakt", ["Parfum", "Parfüm", "Duftstoffmix", "Kosmetik"], None),
    ("KO-PERUBALSAM", "Perubalsam", "Kontakt", ["Balsam", "Duftstoffe"], None),
    ("KO-KONSERV", "Konservierungsstoffe (z. B. Parabene, Methylisothiazolinon)", "Kontakt",
     ["Konservierungsmittel", "Parabene", "Methylisothiazolinon", "Kosmetik"], None),
    ("KO-PPD", "Haarfarbe (p-Phenylendiamin)", "Kontakt", ["PPD", "Haarfärbemittel", "Henna", "Färbemittel"], None),
    ("KO-PFLASTER", "Pflaster und Klebstoffe", "Kontakt", ["Pflaster", "Kolophonium", "Kleber", "Wundpflaster"], None),
    ("KO-DESINFEKTION", "Desinfektionsmittel (z. B. Chlorhexidin)", "Kontakt", ["Chlorhexidin", "Desinfektion", "Jod", "Povidon-Iod"], None),
    # --- Arzneimittel-Gruppen (einzelne Wirkstoffe kommen aus ATC, Markennamen aus BASG) ---
    ("AM-PENICILLINE", "Penicilline", "Arzneimittel", ["Penicillin", "Amoxicillin", "Antibiotika", "Betalaktam"], None),
    ("AM-CEPHALOSPORINE", "Cephalosporine", "Arzneimittel", ["Cephalosporin", "Cefuroxim", "Antibiotika"], None),
    ("AM-SULFONAMIDE", "Sulfonamide", "Arzneimittel", ["Sulfonamid", "Sulfa", "Cotrimoxazol", "Antibiotika"], None),
    ("AM-NSAR", "Schmerzmittel (NSAR, z. B. Ibuprofen, Diclofenac, Acetylsalicylsäure)", "Arzneimittel",
     ["NSAR", "NSAID", "Schmerzmittel", "Rheumamittel", "Ibuprofen", "Diclofenac", "Acetylsalicylsäure", "ASS"], None),
    ("AM-KONTRASTMITTEL", "Kontrastmittel (jodhaltig)", "Arzneimittel", ["Kontrastmittel", "Jod", "Röntgenkontrastmittel", "CT"], None),
    ("AM-LOKALANAESTHETIKA", "Lokalanästhetika (örtliche Betäubung)", "Arzneimittel", ["Lokalanästhetikum", "Betäubung", "Lidocain", "Zahnarzt"], None),
    ("AM-OPIOIDE", "Opioide", "Arzneimittel", ["Opiate", "Morphin", "Codein", "Tramadol"], None),
    ("AM-METAMIZOL", "Metamizol", "Arzneimittel", ["Novalgin", "Novaminsulfon", "Schmerzmittel"], None),
    ("AM-HEPARIN", "Heparin", "Arzneimittel", ["Heparine", "Thrombosespritze"], None),
]


def records() -> list[dict]:
    out = []
    for code, label, kat, syn, snomed in ALLERGENE:
        lmiv = code.startswith("LM-") and code not in ("LM-HASELNUSS", "LM-WALNUSS", "LM-MANDEL", "LM-CASHEW", "LM-KIWI",
                                                        "LM-APFEL", "LM-STEINOBST", "LM-ERDBEERE", "LM-TOMATE", "LM-KAROTTE")
        out.append({
            "system": "Allergen", "code": code, "label_de": label, "label_einfach": None, "parent": None,
            "leistung_hints": [], "quelle_url": LMIV if lmiv else None, "stand": STAND,
            "kategorie": kat, "synonyme": syn, "snomed": snomed, "herkunft": "LMIV Anhang II" if lmiv else KURATIERT,
            "hinweis": "Nur Name zum Erfassen eigener Angaben. Keine Aussage über Schwere, Häufigkeit oder Kreuzreaktionen.",
        })
    return out


def main():
    OUT.mkdir(exist_ok=True)
    recs = records()
    assert len({r["code"] for r in recs}) == len(recs), "doppelter Code"
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs)
    (OUT / "codes.jsonl").write_text(text, encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({
        "source_id": SRC, "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_codes": len(recs), "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "kategorien": sorted({r["kategorie"] for r in recs}),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(recs)} Allergene -> {OUT / 'codes.jsonl'}")


if __name__ == "__main__":
    main()
