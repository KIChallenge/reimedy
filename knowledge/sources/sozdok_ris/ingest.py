#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""sozdok_ris: SozDok-XML (Rechtstexte) -> Schema A (documents.jsonl) + Mapping Leistung<->Rechtsgrundlage.

Nutzung:
  uv run knowledge/sources/sozdok_ris/ingest.py                # parst alle XMLs (inkrementell via sha256 im Manifest)
  uv run knowledge/sources/sozdok_ris/ingest.py --full         # alles neu
  uv run knowledge/sources/sozdok_ris/ingest.py --check-ris    # zusätzlich: Kern-Paragrafen gegen RIS OGD API v2.6 prüfen
  uv run knowledge/sources/sozdok_ris/ingest.py --src PFAD     # anderer XML-Ordner

Nur Standardbibliothek.
"""
import argparse, hashlib, json, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_SRC = ROOT / "_Source" / "Rechtstexte"
OUT = HERE / "out"
SOURCE_ID = "sozdok_ris"
UA = "SV-Lotse-Hackathon/0.1"
MAXCH = 1900

# ---------------------------------------------------------------- Gesetzes-Tabelle
# abk -> (Kurzname, Träger, Bereiche, RIS-Gesetzesnummer|None, RIS-Titel für Suche, Relevanz-Stufe)
# Stufen: 1 = Kern (Lotse zitiert), 2 = relevant (Kontext/Nachschlagen), 3 = Rand, 4 = irrelevant (Dienstrecht, Abkommen, Interna)
LAWS = {
    "ASVG": ("ASVG", ["ÖGK", "PVA", "AUVA"], ["A", "C", "D", "E", "F"], "10008147", "Allgemeines Sozialversicherungsgesetz", 1),
    "GSVG": ("GSVG", ["SVS"], ["A", "C", "D", "E"], "10008422", "Gewerbliches Sozialversicherungsgesetz", 1),
    "BSVG": ("BSVG", ["SVS"], ["A", "C", "D", "E"], "10008431", "Bauern-Sozialversicherungsgesetz", 1),
    "B-KUVG": ("B-KUVG", ["BVAEB"], ["A", "C", "D", "E"], "10008215", "Beamten-Kranken- und Unfallversicherungsgesetz", 1),
    "BPGG": ("BPGG", ["PVA", "ÖGK", "SVS", "BVAEB"], ["D", "E"], "10008859", "Bundespflegegeldgesetz", 1),
    "BPGGEinstV_1999": ("EinstV zum BPGG", ["PVA", "ÖGK", "SVS", "BVAEB"], ["D"], "10009142", "Einstufungsverordnung zum Bundespflegegeldgesetz", 1),
    "BPGGKinderEinstV": ("Kinder-EinstV zum BPGG", ["PVA", "ÖGK", "SVS", "BVAEB"], ["D"], "20009626", "Kinder-Einstufungsverordnung zum Bundespflegegeldgesetz", 1),
    "RRZ_2008": ("RRZ 2008", ["ÖGK", "SVS", "BVAEB"], ["C", "E"], None, None, 1),
    "KBGG": ("KBGG", ["ÖGK", "Finanzamt"], ["E"], "20001474", "Kinderbetreuungsgeldgesetz", 1),
    "FLAG": ("FLAG 1967", ["Finanzamt"], ["E"], "10008220", "Familienlastenausgleichsgesetz 1967", 1),
    "VO-EKO": ("VO-EKO", ["DVSV"], ["C"], None, None, 1),
    "Satzung_OEGK_2025": ("Satzung ÖGK", ["ÖGK"], ["A", "C", "D", "E", "F"], None, None, 1),
    "KrankenO_OEGK_2025": ("Krankenordnung ÖGK", ["ÖGK"], ["A", "C", "E", "F"], None, None, 1),
    "SVS-Satzung_2024": ("Satzung SVS", ["SVS"], ["A", "C", "D", "E", "F"], None, None, 1),
    "SVS-KrankenO_2024": ("Krankenordnung SVS", ["SVS"], ["A", "C", "E", "F"], None, None, 1),
    "KrankenO_BVAEB_2026": ("Krankenordnung BVAEB", ["BVAEB"], ["A", "C", "E", "F"], None, None, 1),
    "Satzung_BVAEB_2026": ("Satzung BVAEB", ["BVAEB"], ["A", "C", "D", "E", "F"], None, None, 1),
    "MuKiPassV_2002": ("Mutter-Kind-Pass-VO", ["ÖGK"], ["A"], None, None, 1),
    "Heilmittel-Bewilligungs-_und_KontrollV": ("Heilmittel-Bewilligungs- und KontrollV", ["ÖGK"], ["C"], None, None, 1),
    "RBZRehab_2005": ("Richtlinien Befreiung Zuzahlungen Rehab", ["ÖGK", "PVA"], ["C", "E"], None, None, 1),
    "RBS_2005": ("Richtlinien Befreiung Service-Entgelt", ["ÖGK"], ["F", "E"], None, None, 1),
    "RGFP": ("Richtlinien Gesundheitsförderung und Prävention", ["DVSV"], ["A", "B"], None, None, 1),
    "MKO_2016": ("Musterkrankenordnung 2016", ["ÖGK"], ["A", "C", "E", "F"], None, None, 2),
    "E-MVB": ("E-MVB", ["DVSV"], ["F", "E", "C"], None, None, 2),
    "AlVG": ("AlVG", ["AMS"], ["E"], None, None, 2),
    "EFZG": ("EFZG", [], ["E"], None, None, 2),
    "SVSG": ("SVSG", ["SVS"], ["E"], None, None, 2),
    "FSVG": ("FSVG", ["SVS"], ["E"], None, None, 2),
    "KGG": ("KGG", ["ÖGK"], ["E"], None, None, 2),
    "PFG": ("PflegefondsG", [], ["D"], None, None, 2),
    "GSBG_1996": ("GSBG", [], ["E"], None, None, 3),
    "APG": ("APG", ["PVA"], ["E"], None, None, 2),
    "NSchG": ("NSchG", ["PVA"], ["E"], None, None, 3),
    "SchwerarbeitsV": ("SchwerarbeitsV", ["PVA"], ["E"], None, None, 3),
    "ASGG": ("ASGG", [], ["F"], None, None, 3),
    "EG-KoordV_883_2004": ("VO (EG) 883/2004", [], ["F", "C"], None, None, 3),
    "EG-Koord-DurchfV_987_2009": ("VO (EG) 987/2009", [], ["F", "C"], None, None, 3),
    "Satzung_AUVA_2025": ("Satzung AUVA", ["AUVA"], ["C", "E"], None, None, 2),
    "Satzung_DVSV_2020": ("Satzung DVSV", ["DVSV"], ["F"], None, None, 3),
    "veraendW": ("Veränderliche Werte", [], ["E"], None, None, 2),
    "BMSVG": ("BMSVG", [], ["E"], None, None, 3),
    "AGG": ("AGG", [], ["B"], None, None, 3),
    "BUAG": ("BUAG", [], ["E"], None, None, 3),
    "AMSG": ("AMSG", ["AMS"], ["E"], None, None, 3),
    "AMPFG": ("AMPFG", ["AMS"], ["E"], None, None, 3),
    "SV-EG": ("SV-EG", [], ["F"], None, None, 3),
    "SV-DSV_2025": ("SV-Datenschutz-VO", [], ["F"], None, None, 3),
    "Ausnahmen_von_der_Einhebung_des_Behandlungsbeitrages-Ambulanz": ("Ausnahmen Behandlungsbeitrag-Ambulanz", ["ÖGK"], ["C", "E"], None, None, 2),
    "RFG_2020": ("Richtlinien ÖGK Gesundheitsförderung", ["ÖGK"], ["B"], None, None, 3),
    "RUF_2020": ("Richtlinien Unterstützungsfonds", ["ÖGK"], ["E"], None, None, 2),
    "RRK_2021": ("Richtlinien Kuren (RRK)", ["ÖGK"], ["C"], None, None, 2),
    "RRK_2005": ("Richtlinien Kuren (RRK 2005, historisch)", ["ÖGK"], ["C"], None, None, 3),
}
# Präfix-Regeln für irrelevante / Randmaterien (Stufe 4/3)
IRRELEVANT_PREFIX = ("DO.", "AbkSozSi", "RechnVorschr", "GO-", "GO_", "GOKDV", "GOHVSV", "MGO", "PO-", "PO_", "statWeis", "AbrGr_",
                     "Satzung_PI_Linz", "WandArb", "EG-WandArb", "Nov_BGBl", "Lohnstufenschema", "RDPP", "REDV", "RLGA", "RFA", "RGB",
                     "RLV", "RLV_", "RJU", "RVU", "SV-SR", "Beilagen_zum_AVSV", "Erreichbarkeitskundmachung", "Kostenersatz", "Satzung_VANotariat",
                     "NVG", "RMDFUE", "RStrukt", "RZSV", "RZIR", "RZR_", "RRGeb", "RBV", "RBGKV", "RMH_", "RoeV", "RoeK", "TAdK", "EntschGr",
                     "Alterssicherungskommissions", "RechtsberKommV", "SV-Neuerlassungskomm", "SchwerarbeitsKommissionsV", "SchKV", "PDStV",
                     "VK-VO", "AUVA_Anh", "SVGW_Anh", "PVA_Anh", "OESG-VO", "e-card_FotoV", "SV-PStV", "EGVVR", "Einhebungsverordnung",
                     "ARUEG", "SUG", "IESG", "EUB-SVG", "EFZ-DV-VO", "Satzung_AUVA_2020", "KrankenO_GKK", "KrankenO_BVAEB_2020",
                     "AMSprV", "Entschaedigungs-VO", "KK-SFG", "GRFG", "RMH", "RLVPK", "EinbezV", "BEIL", "MS_2020", "RPGG")
RELEVANZ_TXT = {1: "kern", 2: "relevant", 3: "rand", 4: "irrelevant"}


def classify(abk_file):
    if abk_file in LAWS:
        return LAWS[abk_file][5]
    if abk_file.startswith(IRRELEVANT_PREFIX):
        return 4
    return 3


def law_info(abk_file, abkrvo):
    if abk_file in LAWS:
        k, tr, be, gnr, rt, rel = LAWS[abk_file]
        return k, tr, be, gnr, rel
    return (abkrvo or abk_file), [], ["F"], None, classify(abk_file)


# ---------------------------------------------------------------- XML -> Text
BLOCK = {"absatz", "ueberschrift", "listelem", "schluss", "schlussteil", "tr", "unterschrift", "fntext", "inhaltsvz", "abschnitt"}
CHAR = {"nbsp": " ", "tab": " ", "amp": "&", "lt": "<", "gt": ">", "gdash": "–", "bdash": "-", "abstand": " ", "n": ""}
SKIP = {"binary", "src"}


def walk(el, out, links):
    t = el.tag
    if t in SKIP:
        return
    if t in CHAR:
        out.append(CHAR[t])
        if el.tail:
            out.append(el.tail)
        return
    if t == "br":
        out.append(" ")
        if el.tail:
            out.append(el.tail)
        return
    if t == "rvolink":
        a = {k: v for k, v in el.attrib.items() if k in ("abkrvo", "gldart", "gldnr", "abs", "ziff", "verwart", "typ")}
        if a.get("gldnr") and a.get("abkrvo"):
            links.append({k: a[k] for k in ("abkrvo", "gldart", "gldnr", "abs", "ziff") if k in a})
    blk = t in BLOCK
    if blk:
        out.append("\n")
    if t == "td":
        out.append(" ")
    if el.text:
        out.append(el.text)
    for ch in el:
        walk(ch, out, links)
    if t == "td":
        out.append(" | ")
    if blk:
        out.append("\n")
    if el.tail:
        out.append(el.tail)


def clean(s):
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    s = re.sub(r"( \|)+\s*$", "", s, flags=re.M)
    return s.strip()


def blocks_of(nutz):
    """Liefert Liste (typ, text, links). typ in ueberschrift|absatz."""
    res = []
    for ab in nutz.iter():
        pass
    # flache Reihenfolge der Top-Level-Blöcke in jedem abschnitt
    def rec(el):
        for ch in el:
            if ch.tag == "abschnitt":
                rec(ch)
            elif ch.tag == "ueberschrift":
                o, l = [], []
                walk(ch, o, l)
                res.append(("h", clean("".join(o)), l))
            else:
                o, l = [], []
                ch.tail = None if False else ch.tail
                walk(ch, o, l)
                tx = clean("".join(o))
                if tx:
                    res.append(("p", tx, l))
    rec(nutz)
    return res


def chunk(blocks):
    """Packt Absatz-Blöcke zu Chunks <= MAXCH; zu lange Blöcke werden an Satzgrenzen geteilt."""
    parts = []
    for typ, tx, l in blocks:
        if typ == "h":
            continue
        while len(tx) > MAXCH:
            cut = max(tx.rfind(". ", 0, MAXCH), tx.rfind("; ", 0, MAXCH), tx.rfind("\n", 0, MAXCH))
            cut = cut + 1 if cut > MAXCH // 3 else MAXCH
            parts.append((tx[:cut].strip(), l))
            tx, l = tx[cut:].strip(), []
        if tx:
            parts.append((tx, l))
    chunks, cur, curl = [], "", []
    for tx, l in parts:
        if cur and len(cur) + len(tx) + 1 > MAXCH:
            chunks.append((cur, curl))
            cur, curl = "", []
        cur = (cur + "\n" + tx) if cur else tx
        curl = curl + l
    if cur:
        chunks.append((cur, curl))
    return chunks


def abs_range(text):
    nums = re.findall(r"(?:^|\n)\((\d+[a-z]?)\)", text)
    if not nums:
        return None
    return f"Abs. {nums[0]}" if len(nums) == 1 else f"Abs. {nums[0]}–{nums[-1]}"


# ---------------------------------------------------------------- RIS-URLs
def ris_url(abk_file, gldart, gldnr, gnr):
    if gnr and gldart == "PARA":
        return f"https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer={gnr}&Paragraf={urllib.parse.quote(gldnr)}"
    if gnr:
        return f"https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer={gnr}"
    return None


def parse_file(path, src_dir):
    f = path.name[:-4]
    fp = f.split("=")
    abk_file = fp[0]
    root = ET.parse(path).getroot()
    rvo = root.find("rvo")
    md = rvo.find("metadaten") if rvo is not None else None
    a = md.attrib if md is not None else {}
    nutz = root.find(".//nutzdaten")
    if nutz is None:
        return []
    gldart = a.get("gldart") or (fp[1] if len(fp) > 1 else "")
    gldnr = a.get("gldnr") or (fp[2] if len(fp) > 2 else "")
    blocks = blocks_of(nutz)
    heads = [t for k, t, _ in blocks if k == "h"]
    head = next((h for h in reversed(heads) if h and h != "(ohne Titel)" and not h.startswith("Verordnung")), "")
    head = re.sub(r"\s+", " ", head)[:140]
    kurz, traeger, bereich, gnr, rel = law_info(abk_file, a.get("abkrvo"))
    sign = {"PARA": "§", "ART": "Art.", "ANL": "Anlage", "ANH": "Anhang", "ZIFF": "Z", "INH": "Inhalt", "PRAE": "Präambel", "PROM": "Promulgation",
            "EINFB": "Einführungsbestimmung"}.get(gldart, gldart)
    base_title = f"{sign} {gldnr} {kurz}" if gldart in ("PARA", "ART", "ANL", "ANH") else f"{kurz} {sign} {gldnr}".strip()
    title = f"{base_title} – {head}" if head and head.lower() not in ("(ohne titel)",) else base_title
    text_all = "\n".join(t for k, t, _ in blocks if k == "p")
    aufgehoben = len(text_all) < 120 and "ufgehoben" in text_all
    ikra = a.get("ikra") or (fp[-1] if len(fp) >= 6 else None)
    dokid = (root.attrib.get("dokid") or f)
    url = ris_url(abk_file, gldart, gldnr, gnr) or f"sozdok:{dokid}"
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Querverweise (dedupliziert)
    seen, links = set(), []
    for _, _, ls in blocks:
        for l in ls:
            k = json.dumps(l, sort_keys=True)
            if k not in seen:
                seen.add(k)
                links.append(l)
    docs = []
    chunks = chunk(blocks)
    for i, (tx, ls) in enumerate(chunks):
        sec = abs_range(tx)
        docs.append({
            "id": f"{SOURCE_ID}:{dokid}#{i}", "source_id": SOURCE_ID, "url": url, "title": title,
            "section": sec, "text": tx, "lang": "de", "traeger": traeger, "bundesland": ["AT"], "bereich": bereich,
            "doc_type": "recht", "valid_from": ikra, "fetched_at": now, "sha256": sha,
            "license_note": "RIS/SozDok Rechtsvorschriften (Bundesrecht: RIS OGD, CC BY 4.0 Namensnennung Bundeskanzleramt/RIS; Satzungen/Richtlinien: AVSV/DVSV, amtliches Werk § 7 UrhG)",
            "relevanz": rel, "relevanz_text": RELEVANZ_TXT[rel], "abkrvo": a.get("abkrvo") or abk_file, "gldart": gldart, "gldnr": gldnr,
            "gesetz": a.get("titrvo"), "aufgehoben": aufgehoben, "dokid": dokid, "pubdat": a.get("pubdat"),
            "querverweise": links if i == 0 else [],
        })
    return docs


# ---------------------------------------------------------------- Leistungs-Mapping
# (leistung_id, datei-abk, gldnr, zitat-Hinweis)  -> Absätze werden aus dem Text gezogen, wo Absatzmarker vorhanden
MAPPING = {
    "pflegegeld": [("BPGG", "1"), ("BPGG", "3"), ("BPGG", "3a"), ("BPGG", "4"), ("BPGG", "4a"), ("BPGG", "5"), ("BPGG", "6"), ("BPGG", "7"),
                   ("BPGG", "8"), ("BPGG", "9"), ("BPGG", "10"), ("BPGG", "12"), ("BPGG", "13"), ("BPGG", "21"), ("BPGG", "25"), ("BPGG", "33"),
                   ("BPGGEinstV_1999", "1"), ("BPGGKinderEinstV", "1")],
    "pflegegeld_erhoehungsantrag": [("BPGG", "9"), ("BPGG", "4")],
    "pflegekarenz": [("BPGG", "21a"), ("BPGG", "21b"), ("BPGG", "21c"), ("BPGG", "21d"), ("BPGG", "21e"), ("BPGG", "21f"), ("BPGG", "21g"), ("BPGG", "21h")],
    "rezeptgebuehrenbefreiung": [("RRZ_2008", "1"), ("RRZ_2008", "2"), ("RRZ_2008", "3"), ("RRZ_2008", "4"), ("RRZ_2008", "5"), ("ASVG", "136"),
                                 ("ASVG", "350"), ("Satzung_OEGK_2025", "34")],
    "krankentransport_fahrtkosten": [("ASVG", "135"), ("ASVG", "135a"), ("KrankenO_OEGK_2025", "20"), ("Satzung_OEGK_2025", "34"), ("Satzung_OEGK_2025", "35")],
    "krankenbehandlung_aerztliche_hilfe": [("ASVG", "133"), ("ASVG", "135"), ("ASVG", "136"), ("ASVG", "137")],
    "heilbehelfe_hilfsmittel": [("ASVG", "137"), ("ASVG", "154"), ("ASVG", "154a"), ("ASVG", "155")],
    "reha_medizinisch": [("ASVG", "154a"), ("ASVG", "302"), ("ASVG", "303"), ("ASVG", "304"), ("ASVG", "305"), ("ASVG", "307d"), ("ASVG", "307e")],
    "reha_berufliche_pva": [("ASVG", "300"), ("ASVG", "301"), ("ASVG", "302"), ("ASVG", "303")],
    "kur_gesundheitsvorsorge": [("ASVG", "154b"), ("ASVG", "155"), ("ASVG", "307d"), ("ASVG", "307g")],
    "vorsorgeuntersuchung": [("ASVG", "132b"), ("ASVG", "132c"), ("GSVG", "116"), ("GSVG", "117"), ("B-KUVG", "5"), ("B-KUVG", "43")],
    "krankengeld": [("ASVG", "138"), ("ASVG", "139"), ("ASVG", "140"), ("ASVG", "141"), ("ASVG", "142"), ("GSVG", "104"), ("GSVG", "105"),
                    ("B-KUVG", "26"), ("B-KUVG", "27")],
    "kinderbetreuungsgeld": [("KBGG", "1"), ("KBGG", "2"), ("KBGG", "3"), ("KBGG", "5"), ("KBGG", "5a"), ("KBGG", "5b"), ("KBGG", "24"), ("KBGG", "24a"),
                             ("KBGG", "24b"), ("KBGG", "26"), ("KBGG", "26a"), ("KBGG", "5c")],
    "familienbeihilfe": [("FLAG", "2"), ("FLAG", "3"), ("FLAG", "5"), ("FLAG", "6"), ("FLAG", "8"), ("FLAG", "8a"), ("FLAG", "10"), ("FLAG", "10a")],
    "mutter_kind_pass": [("MuKiPassV_2002", "1"), ("ASVG", "132c")],
    "heilmittel_erstattungskodex": [("ASVG", "350"), ("ASVG", "351c"), ("ASVG", "351g"), ("ASVG", "31"), ("VO-EKO", "1")],
    "zahnbehandlung_zahnersatz": [("ASVG", "153"), ("ASVG", "153a")],
    "mutterschaftsleistungen_wochengeld": [("ASVG", "162"), ("ASVG", "163"), ("ASVG", "164")],
    "pensionsversicherung_berufsunfaehigkeit": [("ASVG", "273"), ("ASVG", "254"), ("ASVG", "255"), ("ASVG", "253")],
    "rezeptgebuehr_obergrenze": [("ASVG", "136"), ("RRZ_2008", "1")],
    "krankenversicherung_selbstversicherung": [("ASVG", "16"), ("ASVG", "19a")],
    "mitversicherung_angehoerige": [("ASVG", "123"), ("ASVG", "125")],
}


# Rechtsgrundlagen, die NICHT in den lokalen XMLs liegen (arbeitsrechtlich, nicht SV): nur Verweis, kein Volltext
RIS_ONLY = [
    ("pflegekarenz", "AVRAG", "14c", "10008872", "Pflegekarenz (Vereinbarung mit Arbeitgeber:in) – AVRAG, nicht SozDok"),
    ("pflegekarenz", "AVRAG", "14d", "10008872", "Pflegeteilzeit (Vereinbarung mit Arbeitgeber:in) – AVRAG, nicht SozDok"),
    ("pflegekarenz", "AVRAG", "14a", "10008872", "Sterbebegleitung/Begleitung schwerstkranker Kinder (Familienhospizkarenz) – AVRAG, nicht SozDok"),
]


def build_mapping(docs_by_key):
    rows = []
    for lid, abk, nr, gnr, note in RIS_ONLY:
        rows.append({"leistung_id": lid, "abkrvo": abk, "gldnr": nr, "abs": None, "zitat": None, "title": f"§ {nr} {abk} – {note}",
                     "url": ris_url(abk, "PARA", nr, gnr), "valid_from": None, "lokal": False})
    for lid, items in MAPPING.items():
        for abk, nr in items:
            ds = docs_by_key.get((abk, nr))
            if not ds:
                continue
            ds = sorted(ds, key=lambda d: d["id"])
            for d in ds[:4]:
                z = d["text"].strip().replace("\n", " ")
                z = z[:380] + ("…" if len(z) > 380 else "")
                rows.append({"leistung_id": lid, "abkrvo": abk, "gldnr": nr, "abs": (d["section"] or "").replace("Abs. ", "") or None,
                             "zitat": z, "title": d["title"], "url": d["url"], "valid_from": d["valid_from"]})
    return rows


# ---------------------------------------------------------------- RIS-Check
def ris_get(app, **p):
    p["Applikation"] = app
    ep = "Bundesrecht" if app in ("BrKons", "Begut", "Erv") else "Sonstige"
    u = f"https://data.bka.gv.at/ris/api/v2.6/{ep}?" + urllib.parse.urlencode(p)
    time.sleep(1.05)
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=60))["OgdSearchResult"]


def refs_of(r):
    d = r.get("OgdDocumentResults", {})
    x = d.get("OgdDocumentReference", [])
    return [x] if isinstance(x, dict) else x


def check_ris(docs_by_key, today):
    res = []
    for abk, (kurz, tr, be, gnr, rtitle, rel) in LAWS.items():
        if not gnr:
            continue
        nrs = sorted({nr for items in MAPPING.values() for a, nr in items if a == abk})
        for nr in nrs:
            local = docs_by_key.get((abk, nr))
            lv = local[0]["valid_from"] if local else None
            row = {"abkrvo": abk, "gldnr": nr, "lokal_ikra": lv, "ris_ikra": None, "status": None}
            try:
                r = ris_get("BrKons", Titel=rtitle, **{"Abschnitt.Typ": "Paragraph", "Abschnitt.Von": nr, "Abschnitt.Bis": nr,
                                                       "Fassung.FassungVom": today}, DokumenteProSeite="Ten")
                best = None
                for x in refs_of(r):
                    b = x["Data"]["Metadaten"]["Bundesrecht"]
                    k = b.get("BrKons", {})
                    if k.get("Gesetzesnummer") == gnr and k.get("ArtikelParagraphAnlage") == f"§ {nr}":
                        ik, au = k.get("Inkrafttretensdatum"), k.get("Ausserkrafttretensdatum")
                        if ik and ik <= today and (not au or au >= today) and (best is None or ik > best[0]):
                            best = (ik, k.get("Kundmachungsorgan"), x["Data"]["Metadaten"]["Allgemein"].get("DokumentUrl"))
                if best is None:
                    row["status"] = "nicht_in_ris_gefunden" if local else "weder_lokal_noch_ris"
                else:
                    row["ris_ikra"], row["ris_novelle"], row["ris_url"] = best
                    if not local:
                        row["status"] = "nur_ris"
                    elif lv == best[0]:
                        row["status"] = "aktuell"
                    elif lv and best[0] and best[0] > lv:
                        row["status"] = "RIS_NEUER"
                    else:
                        row["status"] = "abweichend"
            except Exception as e:  # noqa
                row["status"] = f"fehler:{type(e).__name__}"
            res.append(row)
            print(row["abkrvo"], row["gldnr"], row["status"], row["lokal_ikra"], row["ris_ikra"], file=sys.stderr)
    return res


AVSV_TRAEGER = {"Österreichische Gesundheitskasse (ÖGK)": ("ÖGK", ("Satzung_OEGK_2025", "KrankenO_OEGK_2025")),
                "Sozialversicherungsanstalt der Selbständigen (SVS)": ("SVS", ("SVS-Satzung_2024", "SVS-KrankenO_2024")),
                "Versicherungsanstalt öffentlich Bediensteter, Eisenbahnen und Bergbau (BVAEB)": ("BVAEB", ("Satzung_BVAEB_2026", "KrankenO_BVAEB_2026"))}


def check_avsv(docs):
    """AVSV (Amtliche Verlautbarungen der SV): Änderungen von Satzung/Krankenordnung nach dem lokalen Stand finden."""
    local = {}
    for d in docs:
        a = d["dokid"].split("=")[0]
        if d.get("pubdat"):
            local[a] = max(local.get(a, ""), d["pubdat"])
    out = []
    for term, art in (("Krankenordnung", "krankenordnung"), ("Satzung", "satzung")):
        for page in (1, 2):
            try:
                r = ris_get("Avsv", Suchworte=term, DokumenteProSeite="Fifty", Seitennummer=str(page), Sortierung_SortDirection="Descending")
            except Exception as e:  # noqa
                out.append({"fehler": f"{type(e).__name__}"})
                break
            for x in refs_of(r):
                m = x["Data"]["Metadaten"]
                av = m.get("Sonstige", {}).get("Avsv", {})
                urh = av.get("Urheber", "")
                if urh not in AVSV_TRAEGER or art not in av.get("Dokumentart", "").strip().lower():
                    continue
                tr, files = AVSV_TRAEGER[urh]
                lf = files[0] if art == "satzung" else files[1]
                kd = m["Sonstige"].get("Kundmachungsdatum")
                out.append({"traeger": tr, "art": av.get("Dokumentart", "").strip(), "titel": m["Sonstige"].get("Kurztitel"), "kundmachung": kd,
                            "avsv_nr": av.get("Avsvnummer"), "lokale_datei": lf, "lokal_pubdat_max": local.get(lf),
                            "neuer_als_lokal": bool(kd and local.get(lf) and kd > local[lf]),
                            "url": x["Data"]["Metadaten"]["Allgemein"].get("DokumentUrl") if "Allgemein" in m else None})
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--check-ris", action="store_true")
    ap.add_argument("--since", default=None, help="(Kompatibilität) ignoriert; Inkrementalität via sha256")
    args = ap.parse_args()
    src = Path(args.src)
    OUT.mkdir(exist_ok=True)
    man_path = OUT / "manifest.json"
    old = {}
    if man_path.exists() and not args.full:
        try:
            old = {u["url"]: u for u in json.loads(man_path.read_text())["urls"]}
        except Exception:
            old = {}
    cache = OUT / "documents.jsonl"
    cached_docs = {}
    if cache.exists() and old and not args.full:
        for line in cache.open(encoding="utf8"):
            d = json.loads(line)
            cached_docs.setdefault(d["dokid"], []).append(d)
    files = sorted(src.glob("*.xml"))
    docs, urls, n_new, n_skip, errs = [], [], 0, 0, []
    for p in files:
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        key = "file:" + p.name
        prev = old.get(key)
        did = p.name[:-4]
        if prev and prev.get("sha256") == sha and did in cached_docs:
            docs.extend(cached_docs[did])
            n_skip += 1
        else:
            try:
                docs.extend(parse_file(p, src))
                n_new += 1
            except Exception as e:
                errs.append(f"{p.name}: {e}")
        urls.append({"url": key, "sha256": sha, "etag": None, "last_modified": None, "status": "ok"})
    # Dubletten-Schutz: je (abkrvo-datei, gldart, gldnr) nur die Fassung mit jüngstem ikra, die nicht in der Zukunft liegt
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    by = {}
    for d in docs:
        k = (d["dokid"].split("=")[0], d["gldart"], d["gldnr"])
        by.setdefault(k, set()).add((d["valid_from"] or "", d["dokid"]))
    drop = set()
    for k, vs in by.items():
        if len(vs) > 1:
            valid = sorted(v for v in vs if v[0] <= today) or sorted(vs)
            keep = valid[-1][1]
            drop |= {v[1] for v in vs if v[1] != keep}
    docs = [d for d in docs if d["dokid"] not in drop]
    with cache.open("w", encoding="utf8") as fo:
        for d in docs:
            fo.write(json.dumps(d, ensure_ascii=False) + "\n")
    # Mapping
    key = {}
    for d in docs:
        if d["gldart"] == "PARA":
            key.setdefault((d["dokid"].split("=")[0], d["gldnr"]), []).append(d)
    rows = build_mapping(key)
    with (OUT / "leistung_rechtsgrundlagen.jsonl").open("w", encoding="utf8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    # Leere Pflicht-Dateien (Schema B-D) anlegen, damit der Loader nicht stolpert
    for n in ("leistungen.jsonl", "stellen.jsonl", "formulare.jsonl"):
        (OUT / n).touch()
    ris = None
    if args.check_ris:
        ris = check_ris(key, today)
        avsv = check_avsv(docs)
        (OUT / "ris_check.json").write_text(json.dumps({"checked_at": today, "rows": ris, "avsv": avsv}, ensure_ascii=False, indent=1))
    elif (OUT / "ris_check.json").exists():
        ris = json.loads((OUT / "ris_check.json").read_text())["rows"]
    ris_when = json.loads((OUT / "ris_check.json").read_text())["checked_at"] if (OUT / "ris_check.json").exists() else None
    rel = {}
    for d in docs:
        rel[d["relevanz_text"]] = rel.get(d["relevanz_text"], 0) + 1
    manifest = {
        "source_id": SOURCE_ID, "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_files": len(files), "n_docs": len(docs), "n_new_parsed": n_new, "n_unchanged": n_skip, "n_dropped_old_versions": len(drop),
        "n_mapping_rows": len(rows), "docs_by_relevanz": rel, "errors": errs[:50],
        "ris_check": ({"checked_at": ris_when, "summary": {s: sum(1 for r in ris if r["status"] == s) for s in {r["status"] for r in ris}}} if ris else None),
        "urls": urls,
    }
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in manifest.items() if k != "urls"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
