# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "selectolax"]
# ///
"""Ingestion der ÖGK-Versicherten-Seiten (www.oegk.at) nach CONTRACT.md.

Aufruf:  uv run knowledge/sources/oegk/ingest.py [--offline] [--force]
  --offline  nichts laden, nur aus raw/ neu bauen
  --force    ETag/Last-Modified ignorieren

Ablauf: (1) Seitenliste (PAGES) bedingt laden (If-None-Match / If-Modified-Since,
Änderungserkennung zusätzlich über sha256 des extrahierten Texts), (2) alle Outputs
deterministisch aus raw/ neu erzeugen. Idempotent.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from selectolax.lexbor import LexborHTMLParser as P

ROOT = Path(__file__).resolve().parent
RAW, OUT = ROOT / "raw", ROOT / "out"
SOURCE_ID = "oegk"
UA = "SV-Lotse-Hackathon/0.1"
BASE = "https://www.oegk.at"
DELAY = 1.1  # <= 1 Request/s
LICENSE = ("Quelle: ÖGK (www.oegk.at), öffentlich zugängliche Seite; Inhalte © Österreichische "
           "Gesundheitskasse. Nur als Wissensquelle mit Quellenangabe im Hackathon-Prototyp genutzt; "
           "keine ausdrückliche offene Lizenz erkennbar. robots.txt: 404 (keine Einschränkung).")

def url_of(cid: str, portal: str = "oegkportal") -> str:
    return f"{BASE}/cdscontent/?contentid=10007.{cid}&portal={portal}"

# ---- Seitenliste: cid -> (portal, bereiche) -------------------------------
def _grp(bereich, ids, portal="oegkportal"):
    return {i: (portal, bereich) for i in ids.split()}
PAGES: dict[str, tuple[str, list[str]]] = {}
for b, ids in [
    (["A"], "878943 896672 888833 896677 896676 896675 896494 890481 890475 890477 890478 890487 908752 893239 870437 895435"),
    (["B"], "892973 895360 888830 894145 888832 901013 893566 895453 885216 901145 904302 895359 897588 904091 904089 904090 896476 "
            "895362 899627 893786 896441 900719 901313 893545 898445 890838 896653 895429 895363 896678 890017 895315"),
    (["C"], "867304 867468 870526 870543 898565 870522 870516 867336 870178 906197 897679 870510 867522 870415 867531 870431 870222 "
            "870456 882758 867388 870418 870472 870457 867901 890465"),
    (["C", "E"], "870423 867322 867467 867490 867465 867448 870714 870460 870471 870721 867384 867386"),
    (["D"], "881073 870679 870511"),
    (["E"], "867302 867461 867463 879630 879754 879676 879755 879642 879742 885205 867346 870708 867477 870473"),
    (["F"], "867306 867480 870413 870671 870707 870439 867481 870459 870462 870421 870436 867497 870659 870660 870661 870662 870663 "
            "870664 896577 867502 870502 870665 870667 870715 867314 867315 868713 870435 869520 867555 870554 870556 870557 870699 "
            "888210 870541 891669 883201 867380 869522 870668 878901 867330"),
]:
    PAGES.update(_grp(b, ids))
# Stellen Wien (Kundenservice, Gesundheitszentren, Physikalische Medizin, Zahngesundheit)
STELLEN_PAGES = {
    "kundenservice": "882916 882910 882918 882913 882920 882921 882914 882911 882922 882917 882919 870674",
    "gesundheitszentrum": "869918 869919 869920 869921",
    "physikalische_medizin": "879828 879829",
    "zahngesundheitszentrum": "880081 880080 880078 880079 880064 880077 880076 880075",
}
STELLEN_TYP = {k: ("einrichtung" if k != "kundenservice" else "traeger") for k in STELLEN_PAGES}
for k, ids in STELLEN_PAGES.items():
    for i in ids.split():
        PAGES[i] = ("oegkportal", ["F"] if k == "kundenservice" else ["C"])
# Seeds aus dem Challenge-Dokument (Vertragspartner-Portal)
SEEDS = {"882122": "formular", "879096": "recht"}
for i in SEEDS:
    PAGES[i] = ("oegkvpportal", ["F"])

# ---- Leistungs-Kandidaten -------------------------------------------------
LEISTUNGEN = [
 # id, name, bereich, seiten, trigger, abhaengigkeiten, formular-regex
 ("vorsorgeuntersuchung","Vorsorgeuntersuchung",["A"],"878943",["Vorsorgeuntersuchung","Gesundenuntersuchung"],[],None),
 ("brustkrebs_frueherkennung","Brustkrebs-Früherkennung (Mammographie-Screening)",["A"],"888833 896672",["Brustkrebs","Mammographie"],[],None),
 ("darmkrebs_frueherkennung","Darmkrebs-Früherkennung",["A"],"896677",["Darmkrebs","Darmspiegelung"],["vorsorgeuntersuchung"],None),
 ("hautkrebs_frueherkennung","Hautkrebs-Früherkennung",["A"],"896676",["Hautkrebs"],["vorsorgeuntersuchung"],None),
 ("prostatakrebs_frueherkennung","Prostatakrebs-Früherkennung",["A"],"896675",["Prostata"],["vorsorgeuntersuchung"],None),
 ("impfungen","Impfungen (Kostenübernahme/Angebote)",["A"],"890481 890475 890477 890478 890487 908752",["Impfung","Impfen","Zecken"],[],None),
 ("jugendlichenuntersuchung","Jugendlichenuntersuchung",["A"],"893239",["Jugendlichenuntersuchung"],[],None),
 ("eltern_kind_pass","Eltern-Kind-Pass",["A","E"],"870437",["Eltern-Kind-Pass","Mutter-Kind-Pass"],["wochengeld"],None),
 ("bewegt_im_park","Bewegt im Park",["B"],"892973",["Bewegt im Park"],[],None),
 ("gesundheitskurse_bewegung","Bewegungs- und Gesundheitskurse (Rücken, Beckenboden, Bewegungsberatung)",["B"],"895360 888830 894145 888832 901013 893566",["Kurse","Bewegung","Rücken","Beckenboden"],[],None),
 ("nikotinfrei_rauchfrei","Rauchfrei-/Nikotinfrei-Angebote (Rauchfrei Telefon)",["B"],"885216 901145",["Rauchfrei","Nikotinfrei","Rauchen"],[],None),
 ("ernaehrungsberatung","Ernährungsberatung und -angebote",["B"],"895359 897588",["Ernährung","Ernährungsberatung"],[],None),
 ("easykids","easykids (Programme für Kinder mit Übergewicht)",["B"],"904091 904089 904090",["easykids"],[],None),
 ("mentale_gesundheit_angebote","Mentale Gesundheit: Angebote und Beratung",["B"],"895362 899627 893786",["Mentale Gesundheit","Erste Hilfe für die Seele"],[],None),
 ("trittsicher_sturzpraevention","Trittsicher & aktiv (Sturzprävention)",["B"],"901313",["Sturz","Trittsicher"],[],None),
 ("selbsthilfegruppen","Selbsthilfegruppen",["B"],"893545",["Selbsthilfe"],[],None),
 ("fit2work","fit2work (Beratung zum Erhalt der Arbeitsfähigkeit)",["B","C"],"890017",["fit2work"],[],None),
 ("rezeptgebuehrenbefreiung","Rezeptgebührenbefreiung und Rezeptgebührenobergrenze",["E","C"],"870471 870721 870460",["Rezeptgebühr","Rezeptgebührenbefreiung"],[],None),
 ("krankentransport_fahrtkosten","Krankentransporte und Fahrtkosten",["C"],"870423",["Krankentransport","Fahrtkosten","Transportkosten"],[],r"Fahrtkosten|Krankentransport"),
 ("reha_medizinisch","Medizinische Rehabilitation",["C"],"867531 867336",["Rehabilitation","Reha"],["krankengeld"],None),
 ("kur","Kuraufenthalt",["C"],"867522",["Kur","Kuraufenthalt"],[],None),
 ("krankengeld","Krankengeld / Krankenstand",["C","E"],"867467 867490 867322 870714",["Krankengeld","Krankenstand"],[],r"^AU"),
 ("rehabilitationsgeld","Rehabilitationsgeld",["C","E"],"867465",["Rehabilitationsgeld"],["krankengeld"],None),
 ("wiedereingliederungsgeld","Wiedereingliederungsgeld",["C","E"],"867448",["Wiedereingliederung"],["krankengeld"],None),
 ("case_management","Case Management",["C"],"890465",["Case Management"],[],None),
 ("heilbehelfe_hilfsmittel","Heilbehelfe und Hilfsmittel",["C"],"870456",["Heilbehelf","Hilfsmittel"],[],r"Heilbehelf|Sehbehelf"),
 ("wahlarzt_kostenerstattung","Wahlarzt: Kostenerstattung (Rückerstattung)",["C","F"],"870516",["Wahlarzt","Wahlärzt","Kostenerstattung"],[],None),
 ("zahnbehandlung","Zahnbehandlung",["C"],"870418 867388 870457",["Zahnbehandlung","Zahnarzt"],[],None),
 ("zahnersatz","Zahnersatz",["C"],"870472",["Zahnersatz"],[],None),
 ("zahnspange","Zahnspange (Kieferorthopädie)",["C"],"882758",["Zahnspange","Kieferorthopädie"],[],None),
 ("psychotherapie","Psychotherapie (Kostenzuschuss/Sachleistung)",["C"],"870222",["Psychotherapie"],[],r"psychotherap"),
 ("klinisch_psychologische_behandlung","Klinisch-psychologische Behandlung und Diagnostik",["C"],"897679 870510",["Klinisch-psychologisch","Psycholog"],[],None),
 ("physiotherapie","Physiotherapie",["C"],"870431",["Physiotherapie"],[],None),
 ("ergotherapie","Ergotherapie",["C"],"870178",["Ergotherapie"],[],None),
 ("logopaedie","Logopädie",["C"],"870415",["Logopädie"],[],None),
 ("heilmassage","Heilmassage",["C"],"906197",["Heilmassage"],[],None),
 ("medizinische_hauskrankenpflege","Medizinische Hauskrankenpflege",["D","C"],"881073",["Hauskrankenpflege"],[],None),
 ("unterstuetzungsfonds","Unterstützungsfonds",["E"],"870473 867477",["Unterstützungsfonds","finanzielle Unterstützung"],[],None),
 ("wochengeld","Wochengeld",["E"],"867346 870708",["Wochengeld","Mutterschutz"],["eltern_kind_pass"],r"Mutterschaft|Entbindung"),
 ("kinderbetreuungsgeld","Kinderbetreuungsgeld",["E"],"867463 879630 879754 879676 879755 879642 879742 885205",["Kinderbetreuungsgeld","Familienzeitbonus"],["wochengeld"],None),
 ("hebammen","Hebammen-Leistungen",["C","A"],"867461",["Hebamme"],[],None),
 ("mitversicherung","Mitversicherung (Angehörige)",["F"],"867502 870502 870665 870667 870715",["Mitversicherung","mitversichert"],[],None),
 ("selbstversicherung","Selbstversicherung in der Krankenversicherung",["F"],"867314 867315 869520 868713 870435",["Selbstversicherung"],[],None),
 ("versicherung_pflegende_angehoerige","Versicherung für pflegende Angehörige",["D","F"],"870679 870511",["pflegende Angehörige","Pflegegeld"],["mitversicherung","selbstversicherung"],None),
 ("e_card","e-card (inkl. e-card mit Foto, Ersatz)",["F"],"870671 870699",["e-card","Ersatzbeleg"],[],r"e-card"),
 ("behandlung_im_ausland","Behandlung im Ausland / Krankenversicherung auf Reisen",["F"],"867497 870663 870660 870661 870662 870664 870659",["Ausland","Urlaub","EKVK"],[],None),
 ("vollmacht","Vollmacht (Vertretung gegenüber der ÖGK)",["F"],"888210",["Vollmacht"],[],None),
 ("rechnung_einreichen","Rechnung einreichen (Kostenerstattung online)",["F"],"867386",["Rechnung einreichen"],["wahlarzt_kostenerstattung"],None),
]

HOT_ZUST = {}
for _l in LEISTUNGEN:
    for _p in _l[3].split(): HOT_ZUST.setdefault(_p, []).append(_l[0])

# ---- Boilerplate ----------------------------------------------------------
BLOCK = "h1,h2,h3,h4,h5,h6,p,li,td,th,dt,dd,div,figcaption,summary,blockquote"
BOILER_EXACT = {
 "Wie wollen Sie das Service nutzen?", "Meine ÖGK-Website (ID Austria erforderlich)", "Meine ÖGK-App (ID-Austria erforderlich)",
 "Meine ÖGK-App (ID Austria erforderlich)", "Meine ÖGK-Website", "Meine ÖGK-App", "E-Mail senden", "Wählen Sie Ihre Region",
 "An wen soll ich mich wenden?", "Karte", "Anfahrt", "Route", "Kontakt", "Weitere Standorte", "Service", "Telefon", "Telefon:",
 "Eingereichte Rechnungen anzeigen", "Rechnung einreichen", "Fertig ausdrucken und per Post schicken", "Zum Seiteninhalt springen",
 "Zur Navigation springen", "Zur Mobilen Navigation springen", "Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich",
 "Salzburg", "Steiermark", "Tirol", "Vorarlberg", "Wien", "Burgen­land", "Nieder­österreich", "Ober­österreich", "Steier­mark",
 "Vorarl­berg", "Österreichische Gesundheitskasse (ÖGK)", "Distanz anzeigen", "Distanzanzeiger", "Termin online vereinbaren",
}
PHONE_RE = re.compile(r"\+43[\d\s\-/()]{6,}")
ws = lambda s: re.sub(r"\s+", " ", s.replace("­", "").replace("\xa0", " ")).strip()

def sha1(s): return hashlib.sha1(s.encode()).hexdigest()
def sha256(b): return hashlib.sha256(b).hexdigest()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---- Laden ----------------------------------------------------------------
def fetch_all(manifest: dict, force: bool):
    RAW.mkdir(exist_ok=True)
    urls = manifest.setdefault("urls", {})
    last = 0.0
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=30) as cl:
        for cid, (portal, _) in PAGES.items():
            u = url_of(cid, portal)
            ent = urls.get(u, {})
            hdr = {}
            if not force and (RAW / f"{sha1(u)}.html").exists():
                if ent.get("etag"): hdr["If-None-Match"] = ent["etag"]
                if ent.get("last_modified"): hdr["If-Modified-Since"] = ent["last_modified"]
            wait = DELAY - (time.time() - last)
            if wait > 0: time.sleep(wait)
            try:
                r = cl.get(u, headers=hdr); last = time.time()
            except httpx.HTTPError as e:
                print("ERR", u, e, file=sys.stderr); ent["status"] = f"error:{e.__class__.__name__}"; urls[u] = ent; continue
            ent["status"] = r.status_code
            if r.status_code == 304:
                print("304", cid); urls[u] = ent; continue
            if r.status_code != 200:
                print(r.status_code, u, file=sys.stderr); urls[u] = ent; continue
            (RAW / f"{sha1(u)}.html").write_bytes(r.content)
            ent.update(etag=r.headers.get("etag"), last_modified=r.headers.get("last-modified"),
                       fetched_at=now(), raw_sha256=sha256(r.content))
            urls[u] = ent
            print("200", cid, len(r.content))

# ---- Parsen ---------------------------------------------------------------
def parse_page(html: str):
    t = P(html)
    c = t.css_first("#esv-content_with_nav") or t.css_first("div.content[role=main]") or t.css_first("#esv-container")
    if c is None: return None
    for n in c.css("script,style,noscript,form,nav"): n.decompose()
    title = ""
    h1 = c.css_first("h1")
    if h1: title = ws(h1.text())
    if not title:
        tt = t.css_first("title"); title = ws(tt.text()) if tt else ""
    items = []  # (kind, text)  kind: h|p
    for el in c.css(BLOCK):
        if len(el.css(BLOCK)) > 1:  # css() schließt das Element selbst ein -> nicht Blatt
            continue
        txt = ws(el.text(separator=" "))
        if not txt: continue
        items.append(("h" if el.tag in ("h1","h2","h3","h4","h5","h6") else "p", txt))
    # Kontakt-Hotlines herausziehen (Widget: "Österreichische Gesundheitskasse (ÖGK)" Region Label Telefon)
    hotlines, clean, i = [], [], 0
    while i < len(items):
        k, tx = items[i]
        m = re.fullmatch(r"Österreichische Gesundheitskasse \(ÖGK\) (Burgenland|Kärnten|Niederösterreich|Oberösterreich|Salzburg|Steiermark|Tirol|Vorarlberg|Wien)", tx)
        if m and i + 1 < len(items):
            lab = items[i+1][1]; j = i + 2
            mm = PHONE_RE.search(lab)
            if mm:  # Label+Telefon in einer Zeile
                hotlines.append({"region": m.group(1), "label": ws(lab[:mm.start()]), "telefon": ws(mm.group(0))}); i += 2; continue
            if j < len(items) and PHONE_RE.match(items[j][1]):
                hotlines.append({"region": m.group(1), "label": lab, "telefon": ws(items[j][1])}); i += 3; continue
        clean.append((k, tx)); i += 1
    clean = [(k, tx) for k, tx in clean if tx not in BOILER_EXACT and not re.fullmatch(r"(Gesundheitsleistungen|Gesund leben|Kundenservice|Über die ÖGK)", tx)]
    # Duplikate in Folge entfernen
    dedup = []
    for it in clean:
        if not dedup or dedup[-1] != it: dedup.append(it)
    pdfs = []
    for a in c.css("a[href]"):
        h = a.attributes.get("href") or ""
        if "cdscontent/load?" in h or h.lower().endswith(".pdf"):
            pdfs.append({"url": h if h.startswith("http") else BASE + h, "text": ws(a.text())})
    return {"title": title, "items": dedup, "hotlines": hotlines, "pdfs": pdfs}

def sections(items, title):
    secs, cur, buf = [], title, []
    def flush():
        nonlocal buf
        if buf: secs.append((cur, buf)); buf = []
    for k, tx in items:
        if k == "h":
            if tx == title and not buf: continue
            flush(); cur = tx
        else: buf.append(tx)
    flush()
    chunks = []
    for name, paras in secs:
        text, acc = [], ""
        for p in paras:
            while len(p) > 1900:  # sehr lange Absätze an Satzgrenze teilen
                cut = p.rfind(". ", 0, 1900); cut = cut + 1 if cut > 400 else 1900
                paras_part, p = p[:cut], p[cut:].strip()
                if len(acc) + len(paras_part) > 1900 and acc: chunks.append((name, acc)); acc = ""
                acc = (acc + "\n" + paras_part).strip()
                chunks.append((name, acc)); acc = ""
            if len(acc) + len(p) + 1 > 1900 and acc: chunks.append((name, acc)); acc = ""
            acc = (acc + "\n" + p).strip()
        if acc: chunks.append((name, acc))
    return [(n, t) for n, t in chunks if len(t) >= 25]

SENT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ•])")
def sentences(paras):
    out = []
    for p in paras:
        out += [s.strip() for s in SENT.split(p) if len(s.strip()) > 25]
    return out
RX = {
 "voraussetzungen": re.compile(r"Voraussetzung|Anspruch|berechtigt|müssen|muss |nur wenn|nur dann|erforderlich|vorausgesetzt|Voraussetzungen|ab dem \d+\.|Alter", re.I),
 "unterlagen": re.compile(r"Unterlage|Nachweis|Bestätigung|mitbring|vorlegen|beizulegen|beilegen|Rechnung|Zahlungsbeleg|Antrag|e-card", re.I),
 "fristen": re.compile(r"Frist|innerhalb|spätestens|Monat|Wochen|Jahre|Tage|binnen|bis zum|verjähr", re.I),
 "zustaendig": re.compile(r"zuständig|wenden Sie sich|Kundenservice|Landesstelle", re.I),
 "kosten": re.compile(r"€|Euro|Prozent|kostenlos|Kostenbeitrag|Selbstbehalt|Rezeptgebühr|Kostenersatz|erstattet|übernimmt", re.I),
}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--offline", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True, parents=True)
    mpath = OUT / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    valid = {url_of(c, p) for c, (p, _) in PAGES.items()}
    manifest["urls"] = {u: e for u, e in manifest.get("urls", {}).items() if u in valid}
    if not a.offline: fetch_all(manifest, a.force)

    docs, pages = [], {}
    fetched = now()
    for cid, (portal, bereich) in PAGES.items():
        u = url_of(cid, portal); f = RAW / f"{sha1(u)}.html"
        if not f.exists(): continue
        pg = parse_page(f.read_text(encoding="utf-8", errors="replace"))
        if not pg or not pg["items"]: continue
        pg.update(cid=cid, url=u, bereich=bereich, portal=portal)
        pages[cid] = pg
        text_hash = sha256("\n".join(t for _, t in pg["items"]).encode())
        ent = manifest["urls"].setdefault(u, {})
        if ent.get("sha256") != text_hash: ent["changed_at"] = ent.get("fetched_at") or fetched
        ent["sha256"] = text_hash; pg["sha256"] = text_hash; pg["fetched_at"] = ent.get("fetched_at", fetched)
        dtype = "recht" if cid == "879096" else "formular" if cid == "882122" else \
                ("kontakt" if cid in sum([v.split() for v in STELLEN_PAGES.values()], []) or cid in ("869522", "878901") else "leistungsinfo")
        trg = ["ÖGK"]; bl = ["W"] if (cid in STELLEN_PAGES["kundenservice"] or cid == "882122") else ["AT"]
        for n, (sec, txt) in enumerate(sections(pg["items"], pg["title"])):
            docs.append({"id": f"{SOURCE_ID}:{sha1(u)}#{n}", "source_id": SOURCE_ID, "url": u, "title": pg["title"], "section": sec,
                         "text": txt, "lang": "de", "traeger": trg, "bundesland": bl, "bereich": bereich, "doc_type": dtype,
                         "valid_from": None, "fetched_at": pg["fetched_at"], "sha256": text_hash, "license_note": LICENSE})

    # Formulare (Seeds + alle PDF-Links in Versicherten-Seiten, ohne Gesamtverträge/Folder)
    forms = {}
    FORM_LEIST = [(r"Fahrt|Reise|Krankentransport", "krankentransport_fahrtkosten"), (r"psychotherap", "psychotherapie"),
                  (r"Mutterschaft|Entbindung", "wochengeld"), (r"^AU|Krankenstand", "krankengeld"), (r"Heilbehelf|Sehbehelf|Hilfsmittel|Augenoptik", "heilbehelfe_hilfsmittel"),
                  (r"e-card", "e_card"), (r"Vorsorge", "vorsorgeuntersuchung"), (r"Zahn|Kiefer", "zahnbehandlung"), (r"Heilnahrung", "heilbehelfe_hilfsmittel"),
                  (r"physikalisch", "physiotherapie"), (r"Zuschuss|Kostenerstattung", "wahlarzt_kostenerstattung")]
    ARZT = re.compile(r"Zuweisung|Überweisung|^VO |Verordnung|Rezeptbestellung|Krankentransportwagen|Genehmigung|ärztlichen Untersuchung|Vertretungsschein|Augenoptik|Heilnahrung", re.I)
    for cid, pg in pages.items():
        if cid == "879096": continue  # Gesamtverträge sind keine Versicherten-Formulare
        for p in pg["pdfs"]:
            name = re.sub(r"\((PDF|DOC|DOCX)[^)]*\)\s*$", "", p["text"]).strip() or p["text"]
            if not name or "Folder" in name or "Plakat" in name or "Broschüre" in name: continue
            fid = "oegk_" + re.sub(r"[^a-z0-9]+", "_", name.lower().replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")).strip("_")[:60]
            if fid in forms:
                forms[fid]["leistung_ids"] = sorted(set(forms[fid]["leistung_ids"]) | set(l for r, l in FORM_LEIST if re.search(r, name, re.I)))
                continue
            forms[fid] = {"formular_id": fid, "name": name, "traeger": "ÖGK", "url_pdf": p["url"], "local_pdf": None, "fillable": None, "felder": [],
                          "leistung_ids": sorted({l for r, l in FORM_LEIST if re.search(r, name, re.I)}),
                          "wer_fuellt_aus": "arzt" if ARZT.search(name) else "versicherte", "quelle_url": pg["url"]}
    (OUT / "formulare.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in forms.values()))

    # Stellen
    stellen = []
    for typ, ids in STELLEN_PAGES.items():
        for cid in ids.split():
            pg = pages.get(cid)
            if not pg: continue
            ls = [t for _, t in pg["items"]]
            name = pg["title"] or ls[0]
            plz = adr = tel = mail = None
            for j, l in enumerate(ls):
                m = re.fullmatch(r"(\d{4}) (.+)", l)
                if m and not plz and j > 0 and re.search(r"\d", ls[j-1]):
                    plz, adr = m.group(1), f"{ls[j-1]}, {l}"
                m = re.fullmatch(r"Telefon:? ?(\+43[\d\s\-/()]+)", l)
                if m and not tel: tel = ws(m.group(1))
                m = re.fullmatch(r"E-Mail:? ?([\w.\-]+@[\w.\-]+)", l)
                if m and not mail: mail = m.group(1)
            oz = [l for l in ls if re.match(r"(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag)\s*[:\-]", l)]
            zust = {"kundenservice": ["krankengeld", "mitversicherung", "rezeptgebuehrenbefreiung", "wahlarzt_kostenerstattung", "e_card"],
                    "zahngesundheitszentrum": ["zahnbehandlung", "zahnersatz", "zahnspange"], "gesundheitszentrum": ["vorsorgeuntersuchung"],
                    "physikalische_medizin": ["physiotherapie"]}.get(typ, [])
            if cid == "882921": zust = ["kinderbetreuungsgeld", "wochengeld"]
            stellen.append({"stelle_id": f"oegk_{typ}_{cid}", "name": name, "typ": STELLEN_TYP[typ], "adresse": adr, "plz": plz, "bundesland": "W",
                            "telefon": tel, "email": mail, "url": pg["url"], "oeffnungszeiten": "; ".join(oz) or None,
                            "zustaendig_fuer": zust, "geo": None, "quelle_url": pg["url"]})
    # Hotlines je Bundesland (aus Kontakt-Widgets): nur eindeutige (region,label,telefon)
    seen = set()
    for cid, pg in pages.items():
        for h in pg["hotlines"]:
            key = (h["region"], h["label"], h["telefon"])
            if key in seen: continue
            seen.add(key)
            bl = {"Burgenland":"B","Kärnten":"K","Niederösterreich":"NÖ","Oberösterreich":"OÖ","Salzburg":"S","Steiermark":"ST","Tirol":"T","Vorarlberg":"V","Wien":"W"}.get(h["region"], h["region"])
            stellen.append({"stelle_id": "oegk_hotline_" + re.sub(r"[^a-z0-9]+", "_", (h["region"] + " " + h["label"]).lower().replace("ä","ae").replace("ö","oe").replace("ü","ue")).strip("_")[:70],
                            "name": f"ÖGK {h['region']}: {h['label']}", "typ": "hotline", "adresse": None, "plz": None, "bundesland": bl,
                            "telefon": h["telefon"], "email": None, "url": pg["url"], "oeffnungszeiten": None,
                            "zustaendig_fuer": HOT_ZUST.get(cid, []), "geo": None, "quelle_url": pg["url"]})
    (OUT / "stellen.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in stellen))

    # Leistungen
    leist = []
    for lid, name, ber, pids, trig, dep, frx in LEISTUNGEN:
        pgs = [pages[p] for p in pids.split() if p in pages]
        if not pgs: continue
        out = {k: [] for k in RX}
        for pg in pgs:
            paras = [t for k, t in pg["items"] if k == "p"]
            for s in sentences(paras):
                for k, rx in RX.items():
                    if not s.endswith('?') and rx.search(s) and not any(s == q["zitat"] for q in out[k]) and len(s) < 600:
                        out[k].append({"text": s, "quelle_url": pg["url"], "zitat": s})
        lead = next((t for k, t in pgs[0]["items"] if k == "p" and len(t) > 60), "")
        fids = [f["formular_id"] for f in forms.values() if lid in f["leistung_ids"]]
        online = "https://meine.oegk.at" if any("Meine ÖGK" in t or "meine.oegk.at" in t for pg in pgs for _, t in pg["items"]) else None
        bl = ["W"] if False else ["AT"]
        leist.append({"leistung_id": lid, "name": name,
                      "kurz_einfach": ws(SENT.split(lead)[0]) if lead else None,  # wörtlicher Einleitungssatz; Vereinfachung später im LLM
                      "bereich": ber, "traeger": ["ÖGK"], "innerhalb_sv": True,
                      "zielgruppe": None,
                      "voraussetzungen": out["voraussetzungen"][:6],
                      "zustaendig": " ".join(q["zitat"] for q in out["zustaendig"][:2]) or None,
                      "antrag": {"formular_id": fids[0] if fids else None, "formular_ids": fids, "wo": next((q["zitat"] for q in out["unterlagen"] if "Antrag" in q["zitat"]), None), "online_url": online},
                      "unterlagen": [q["zitat"] for q in out["unterlagen"][:5]],
                      "fristen": [q["zitat"] for q in out["fristen"][:4]],
                      "kosten": " ".join(q["zitat"] for q in out["kosten"][:3]) or None,
                      "abhaengigkeiten": dep, "trigger_im_dokument": trig, "bundesland": ["AT"],
                      "quellen": [{"url": pg["url"], "stand": pg["fetched_at"][:10]} for pg in pgs],
                      "confidence": "mittel" if len(out["voraussetzungen"]) >= 1 else "niedrig",
                      "hinweis": "Zitate automatisch per Schlüsselwort extrahiert (wörtlich); Review nötig."})
    (OUT / "leistungen.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in leist))
    (OUT / "documents.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs))

    manifest.update(source_id=SOURCE_ID, fetched_at=fetched, n_docs=len(docs), n_pages=len(pages), n_leistungen=len(leist),
                    n_formulare=len(forms), n_stellen=len(stellen))
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"pages={len(pages)} docs={len(docs)} leistungen={len(leist)} formulare={len(forms)} stellen={len(stellen)}")

if __name__ == "__main__":
    main()
