# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "selectolax", "pypdf"]
# ///
"""Ingestion der PVA-Seiten (www.pv.at) nach knowledge/CONTRACT.md.

Aufruf:  uv run --python 3.12 knowledge/sources/pva/ingest.py [--offline] [--force]
  --offline  nichts laden, alles aus raw/ neu bauen
  --force    ETag/Last-Modified ignorieren

Ablauf: (1) Seiten + Formular-PDFs + Reha-Zentren-JSON bedingt laden (≤1 Request/s),
(2) alle Outputs deterministisch aus raw/ erzeugen, (3) Live-PDFs gegen die lokalen
Kopien in _Source/ abgleichen (sha256, sonst AcroForm-Feldnamen). Idempotent.
Leistungs-Zitate (curated.py-artig in CURATED unten) sind wörtliche Sätze; jeder Satz wird
gegen den Seitentext geprüft und verworfen, wenn er dort nicht (mehr) vorkommt.
"""
from __future__ import annotations
import argparse, base64, hashlib, html as htmllib, io, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from selectolax.lexbor import LexborHTMLParser as P

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
RAW, OUT = ROOT / "raw", ROOT / "out"
SOURCE_ID = "pva"
UA = "SV-Lotse-Hackathon/0.1"
BASE = "https://www.pv.at"
DELAY = 1.1
LICENSE = ("Quelle: Pensionsversicherungsanstalt (www.pv.at), öffentlich zugängliche Seite; Inhalte © PVA. "
           "Nur als Wissensquelle mit Quellenangabe im Hackathon-Prototyp genutzt; keine offene Lizenz erkennbar. "
           "robots.txt: leitet auf eine 404-Seite (keine Einschränkung).")

# slug -> (bereiche, doc_type)
PAGES: dict[str, tuple[list[str], str]] = {
    "pflegegeld": (["D"], "leistungsinfo"),
    "pflegegeld/pflegende-angehoerige": (["D", "E"], "leistungsinfo"),
    "pflegegeld/pflegende-angehoerige/pflegekarenz-und-pflegeteilzeit": (["D", "E"], "leistungsinfo"),
    "pflegegeld/pflegende-angehoerige/angehoerigenbonus": (["D", "E"], "leistungsinfo"),
    "pflegegeld/pflegende-angehoerige/familienhospizkarenz": (["D", "E"], "leistungsinfo"),
    "pflegegeld/pflege-von-angehoerigen-leicht-erklaert": (["D"], "leistungsinfo"),
    "pflege": (["D"], "leistungsinfo"),
    "medizinische-begutachtung": (["D", "C"], "leistungsinfo"),
    "reha-und-gesundheitsvorsorge": (["C"], "leistungsinfo"),
    "reha-und-praevention/vom-antrag-zu-reha-und-kur": (["C"], "leistungsinfo"),
    "reha-und-praevention/medizinische-rehabilitation": (["C"], "leistungsinfo"),
    "reha-und-praevention/gesundheitsvorsorge-kur-gva": (["A", "C"], "leistungsinfo"),
    "reha-und-praevention/berufliche-rehabilitation": (["C", "E"], "leistungsinfo"),
    "reha-und-praevention/soziale-rehabilitation": (["C", "E"], "leistungsinfo"),
    "reha-und-praevention/reha-angebote/teilstationaere-rehabilitation": (["C"], "leistungsinfo"),
    "reha-und-praevention/reha-angebote-und-pilotprojekte": (["C"], "leistungsinfo"),
    "reha-und-praevention/reha-zentren": (["C"], "kontakt"),
    "reha-und-praevention/information-fuer-zuweisende-aerztinnen-und-aerzte": (["C"], "leistungsinfo"),
    "reha-und-praevention/rehabilitation-und-praevention-leicht-erklaert": (["C"], "leistungsinfo"),
    "service-und-kontakt/online-formulare": (["F"], "formular"),
    "service-und-kontakt/kontakt": (["F"], "kontakt"),
    "service-und-kontakt/faq": (["F"], "faq"),
    "service-und-kontakt/regionalsprechtage": (["F"], "kontakt"),
    "service-und-kontakt/ombudsstelle": (["F"], "kontakt"),
    "service-und-kontakt/e-services": (["F"], "leistungsinfo"),
    "pension/in-der-pension/meldepflichten-und-meldefristen": (["F"], "recht"),
}
def page_url(slug): return f"{BASE}/web/{slug}"

ZENTREN_JSON = f"{BASE}/cdscontent/load?contentid=10007.891827"   # Liste der Reha-Zentren (Base64-Felder)

# Formulare: id -> Daten. Versionslose URL = immer aktuelle Fassung (identische Bytes wie die versionierte).
FORMS = {
    "pva_pal080": dict(
        name="Antrag auf Pflegegeld (auch für Erhöhungsantrag)", url=f"{BASE}/cdscontent/load?contentid=10008.781956",
        local="_Source/Anträge und Formulare/PAL080_0125_Mpfl_052026.pdf", leistung_ids=["pflegegeld"], wer="versicherte",
        gefunden_auf=["pflegegeld"], online_antrag=None),
    "pva_antrag_kur_reha": dict(
        name="Antrag auf Rehabilitations-, Kur- bzw. Erholungsaufenthalt", url=f"{BASE}/cdscontent/load?contentid=10008.781981",
        local="_Source/Anträge und Formulare/Antrag Kur und Reha.pdf", leistung_ids=["rehabilitation", "reha_onkologisch", "kur"],
        wer="versicherte", gefunden_auf=["reha-und-praevention/medizinische-rehabilitation", "reha-und-praevention/vom-antrag-zu-reha-und-kur",
                                         "reha-und-praevention/gesundheitsvorsorge-kur-gva", "service-und-kontakt/online-formulare"]),
    "pva_ahv_reha_nach_unfall": dict(
        name="Antrag auf Anschlussheilverfahren oder Rehabilitation nach Unfall", url=f"{BASE}/cdscontent/load?contentid=10008.781971",
        local="_Source/Anträge und Formulare/Reha_n_Unfall_052026.pdf", leistung_ids=["anschlussheilverfahren", "rehabilitation"],
        wer="krankenhaus", gefunden_auf=[], quelle="reha-und-praevention/medizinische-rehabilitation"),  # Verlinkung wird zur Laufzeit gesucht (siehe find_links)
    "pva_gvr001_uebergangsgeld": dict(
        name="Antrag auf Übergangsgeld / berufliche Maßnahmen der Rehabilitation (GVR 001)", url=f"{BASE}/cdscontent/load?contentid=10008.781947",
        local=None, leistung_ids=["rehabilitation", "uebergangsgeld"], wer="versicherte",
        gefunden_auf=["reha-und-praevention/medizinische-rehabilitation"], quelle="reha-und-praevention/medizinische-rehabilitation"),
}

ws = lambda s: re.sub(r"\s+", " ", s.replace("­", "").replace("\xa0", " ")).strip()
def sha1(s): return hashlib.sha1(s.encode()).hexdigest()
def sha256(b): return hashlib.sha256(b).hexdigest()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def b64(s): return base64.b64decode(s).decode("utf-8") if s else ""

# ---- Laden ------------------------------------------------------------------
def fetch_all(manifest: dict, force: bool):
    RAW.mkdir(exist_ok=True)
    urls = manifest.setdefault("urls", {})
    targets = [(page_url(s), ".html") for s in PAGES] + [(ZENTREN_JSON, ".json")] + [(f["url"], ".pdf") for f in FORMS.values()]
    last = 0.0
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=60) as cl:
        def get(u, ext):
            nonlocal last
            ent = urls.get(u, {}); hdr = {}
            f = RAW / f"{sha1(u)}{ext}"
            if not force and f.exists():
                if ent.get("etag"): hdr["If-None-Match"] = ent["etag"]
                if ent.get("last_modified"): hdr["If-Modified-Since"] = ent["last_modified"]
            wait = DELAY - (time.time() - last)
            if wait > 0: time.sleep(wait)
            try:
                r = cl.get(u, headers=hdr); last = time.time()
            except httpx.HTTPError as e:
                print("ERR", u, e, file=sys.stderr); ent["status"] = f"error:{e.__class__.__name__}"; urls[u] = ent; return None
            ent["status"] = r.status_code; ent["final_url"] = str(r.url)
            if r.status_code == 304: print("304", u); urls[u] = ent; return None
            if r.status_code != 200:
                print(r.status_code, u, file=sys.stderr); urls[u] = ent; return None
            f.write_bytes(r.content)
            ent.update(etag=r.headers.get("etag"), last_modified=r.headers.get("last-modified"), fetched_at=now(),
                       raw_sha256=sha256(r.content), content_type=r.headers.get("content-type"), bytes=len(r.content))
            urls[u] = ent; print("200", u, len(r.content)); return r.content
        for u, ext in targets: get(u, ext)

def zentren() -> list[dict]:
    f = RAW / f"{sha1(ZENTREN_JSON)}.json"
    if not f.exists(): return []
    d = json.loads(f.read_text(encoding="utf-8"))
    out = []
    for x in d.get("contextList", []):
        desc = b64(x.get("description", ""))
        web = re.search(r'href="(https?://[^"]+)"', desc)
        out.append(dict(pageurl=x["pageurl"], name=b64(x["pagename"]), bundesland=x.get("federalstate"),
                        indikationen=[c.strip() for c in b64(x.get("category", "")).split(",") if c.strip()],
                        beschreibung=ws(re.sub(r"<[^>]+>", " ", htmllib.unescape(desc))), web=web.group(1) if web else None))
    return out

# ---- Parsen -----------------------------------------------------------------
BLOCK = "h1,h2,h3,h4,h5,h6,p,li,td,th,dt,dd,div,figcaption,summary,blockquote"
BOILER = {"Drucken", "Kontakt", "Inhalt", "Das könnte Sie auch interessieren", "Zum Seiteninhalt springen", "Mehr Infos"}
BOILER_RX = re.compile(r"^(Hinweis: Die auf dieser Website angebotenen Inhalte|Stand: \d)")

def parse_page(html: str):
    t = P(html)
    c = t.css_first("#esv-content_with_nav") or t.css_first("div.content[role=main]")
    if c is None: return None
    for n in c.css("script,style,noscript,form,nav"): n.decompose()
    h1 = c.css_first("h1"); title = ws(h1.text()) if h1 else ""
    if not title:
        tt = t.css_first("title"); title = ws(tt.text().split("|")[0]) if tt else ""
    items = []
    for el in c.css(BLOCK):
        if len(el.css(BLOCK)) > 1: continue
        txt = ws(el.text(separator=" "))
        # Leerzeichen vor Satzzeichen (durch separator=" " entstanden) glätten
        txt = re.sub(r"\s+([.,;:!?)])", r"\1", txt); txt = re.sub(r"\(\s+", "(", txt)
        if not txt or txt in BOILER or BOILER_RX.match(txt): continue
        items.append(("h" if el.tag in ("h1", "h2", "h3", "h4", "h5", "h6") else "p", txt))
    ded = []
    for it in items:
        if not ded or ded[-1] != it: ded.append(it)
    stand = None
    m = re.search(r"Stand:\s*(\d{1,2})\.\s*([A-Za-zäöü]+)\s*(\d{4})", c.text(separator=" "))
    if m: stand = (m.group(1), m.group(2), m.group(3))
    links = []
    for a in c.css("a[href]"):
        h = htmllib.unescape(a.attributes.get("href") or "")
        if "contentid=10008." in h or h.lower().endswith(".pdf"):
            links.append({"href": h if h.startswith("http") else BASE + h, "text": ws(a.text())})
    return {"title": title, "items": ded, "links": links, "stand": stand}

MONTHS = {"Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6, "Juli": 7, "August": 8,
          "September": 9, "Oktober": 10, "November": 11, "Dezember": 12}
def stand_iso(st):
    if not st: return None
    try: return f"{int(st[2]):04d}-{MONTHS[st[1]]:02d}-{int(st[0]):02d}"
    except Exception: return None

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
        acc = ""
        for p in paras:
            while len(p) > 1900:
                cut = p.rfind(". ", 0, 1900); cut = cut + 1 if cut > 400 else 1900
                part, p = p[:cut], p[cut:].strip()
                if len(acc) + len(part) > 1900 and acc: chunks.append((name, acc)); acc = ""
                acc = (acc + "\n" + part).strip(); chunks.append((name, acc)); acc = ""
            if len(acc) + len(p) + 1 > 1900 and acc: chunks.append((name, acc)); acc = ""
            acc = (acc + "\n" + p).strip()
        if acc: chunks.append((name, acc))
    return [(n, t) for n, t in chunks if len(t) >= 25]

# ---- Formular-Abgleich -------------------------------------------------------
def pdf_fields(data: bytes):
    from pypdf import PdfReader
    import logging; logging.disable(logging.CRITICAL)
    r = PdfReader(io.BytesIO(data))
    flds = r.get_fields() or {}
    out = []
    for name, f in flds.items():
        ft = str(f.get("/FT", ""))
        label = f.get("/TU")
        out.append({"name": name, "label": str(label) if label else name,
                    "typ": "checkbox" if ft == "/Btn" else "text", "quelle_hint": None})
    return len(r.pages), out

def build_forms(manifest, pages):
    forms = []
    for fid, F in FORMS.items():
        f = RAW / f"{sha1(F['url'])}.pdf"
        ent = manifest["urls"].get(F["url"], {})
        rec = {"formular_id": fid, "name": F["name"], "traeger": "PVA", "url_pdf": ent.get("final_url") or F["url"],
               "local_pdf": F["local"], "fillable": None, "felder": [], "leistung_ids": F["leistung_ids"],
               "wer_fuellt_aus": F["wer"], "quelle_url": page_url(F.get("quelle", "service-und-kontakt/online-formulare")),
               "gefunden_auf": [page_url(s) for s in F["gefunden_auf"]]}
        if not f.exists():
            rec["abgleich"] = {"status": "nicht_geladen"}; forms.append(rec); continue
        data = f.read_bytes()
        n, flds = pdf_fields(data)
        rec["fillable"] = bool(flds); rec["felder"] = flds
        ab = {"geprueft_am": ent.get("fetched_at"), "http_status": ent.get("status"), "content_type": ent.get("content_type"),
              "bytes": len(data), "seiten": n, "sha256_live": sha256(data), "n_felder_live": len(flds)}
        if F["local"] and (REPO / F["local"]).exists():
            ld = (REPO / F["local"]).read_bytes()
            ln, lflds = pdf_fields(ld)
            fa, fb = {x["name"] for x in flds}, {x["name"] for x in lflds}
            ab.update(sha256_local=sha256(ld), n_felder_local=len(lflds), identisch=sha256(data) == sha256(ld),
                      felder_gleich=fa == fb, felder_nur_live=sorted(fa - fb)[:20], felder_nur_lokal=sorted(fb - fa)[:20])
        elif F["local"]: ab["lokale_kopie_fehlt"] = True
        rec["abgleich"] = ab
        forms.append(rec)
    return forms

def find_links(pages):
    """Auf welchen pv.at-Seiten sind die Formular-PDFs verlinkt (Seiten-Crawl)?"""
    for fid, F in FORMS.items():
        cid = re.search(r"contentid=(10008\.\d+)", F["url"]).group(1)
        F["gefunden_auf"] = sorted({s for s, pg in pages.items() if any(cid in l["href"] for l in pg["links"])})

# ---- Leistungen (kuratierte Zitate, gegen Seitentext geprüft) -----------------
# Jedes Zitat: (kategorie, seiten-slug, wörtlicher Satz/Textstück). Verworfen, wenn nicht im Seitentext.
from curated import LEISTUNGEN, STELLEN_EXTRA, ZENTREN_ADRESSE  # noqa: E402
PGSLUG = "pflegegeld"

def parse_stufen(pg):
    if not pg: return []
    its = [t for k, t in pg["items"] if k == "p"]; res = []
    for i in range(len(its) - 2):
        if re.fullmatch(r"[1-7]", its[i]) and its[i+1].startswith("EUR ") and "Stunden" in its[i+2]:
            res.append({"stufe": int(its[i]), "betrag_eur_monat": its[i+1][4:], "pflegebedarf_stunden_monat_mehr_als": re.match(r"(\d+)", its[i+2]).group(1),
                        "anmerkung": its[i+2], "quelle_url": pg["url"]})
    return res

def parse_zuzahlung(pg):
    if not pg: return []
    its = [t for k, t in pg["items"] if k == "p"]; res = []
    for i in range(len(its) - 1):
        if its[i].startswith("mehr als EUR") and re.fullmatch(r"EUR [\d.,]+", its[i+1]):
            res.append({"monatliches_bruttoeinkommen": its[i], "taegliche_zuzahlung": its[i+1], "quelle_url": pg["url"]})
    return res

def norm(s): return ws(re.sub(r"\s+([.,;:!?)])", r"\1", s))

def build_leistungen(pages, forms):
    ftext = {s: norm(" ".join(t for _, t in pg["items"])) for s, pg in pages.items()}
    out, dropped = [], []
    for L in LEISTUNGEN:
        q = {"voraussetzungen": [], "unterlagen": [], "fristen": [], "kosten": [], "zustaendig": []}
        for kat, slug, zitat in L["zitate"]:
            if slug in ftext and norm(zitat) in ftext[slug]:
                q[kat].append({"text": zitat, "quelle_url": page_url(slug), "zitat": zitat})
            else: dropped.append((L["id"], slug, zitat[:60]))
        fids = [f["formular_id"] for f in forms if L["id"] in f["leistung_ids"]]
        quellen = [{"url": page_url(s), "stand": stand_iso(pages[s]["stand"]) or pages[s]["fetched_at"][:10]} for s in L["seiten"] if s in pages]
        if not quellen: continue
        extra = {}
        if L["id"] == "pflegegeld": extra["pflegegeldstufen_2026"] = parse_stufen(pages.get(PGSLUG))
        if L["id"] in ("rehabilitation", "reha_onkologisch", "kur"):
            extra["zuzahlung_staffel_stationaer"] = parse_zuzahlung(pages.get("reha-und-praevention/vom-antrag-zu-reha-und-kur"))
        out.append({**extra,
            "leistung_id": L["id"], "name": L["name"], "kurz_einfach": L["kurz"], "bereich": L["bereich"],
            "traeger": L.get("traeger", ["PVA"]), "innerhalb_sv": L.get("innerhalb_sv", True), "zielgruppe": L["zielgruppe"],
            "voraussetzungen": q["voraussetzungen"],
            "zustaendig": L["zustaendig"] if not q["zustaendig"] else " ".join(x["zitat"] for x in q["zustaendig"]),
            "antrag": {"formular_id": fids[0] if fids else None, "formular_ids": fids, "wo": L.get("wo"), "online_url": L.get("online_url")},
            "unterlagen": [x["zitat"] for x in q["unterlagen"]], "fristen": [x["zitat"] for x in q["fristen"]],
            "kosten": " ".join(x["zitat"] for x in q["kosten"]) or None,
            "abhaengigkeiten": L["dep"], "trigger_im_dokument": L["trigger"], "bundesland": ["AT"], "quellen": quellen,
            "confidence": L["conf"], "hinweis": L.get("hinweis", "Zitate wörtlich von pv.at (Satz-Ebene), kuratiert und gegen den Seitentext geprüft.")})
    return out, dropped

# ---- Stellen -----------------------------------------------------------------
def build_stellen(pages):
    st = []
    for z in zentren():
        slug = re.sub(r"[^a-z0-9]+", "_", z["name"].lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("_")
        onko = any("nkolog" in i for i in z["indikationen"])
        bl = {"Wien": "W", "Steiermark": "ST", "Niederösterreich": "NÖ", "Oberösterreich": "OÖ", "Salzburg": "S", "Burgenland": "B",
              "Kärnten": "K", "Tirol": "T", "Vorarlberg": "V"}.get(z["bundesland"], z["bundesland"])
        adr = ZENTREN_ADRESSE.get(z["name"])
        st.append({"stelle_id": f"pva_reha_{slug}", "name": z["name"], "typ": "einrichtung", "adresse": adr[0] if adr else None, "plz": adr[1] if adr else None, "bundesland": bl,
                   "telefon": None, "email": None, "url": z["pageurl"], "oeffnungszeiten": None,
                   "zustaendig_fuer": ["rehabilitation", "anschlussheilverfahren"] + (["reha_onkologisch"] if onko else []) + ["kur"],
                   "geo": None, "quelle_url": page_url("reha-und-praevention/reha-zentren"),
                   "indikationen": z["indikationen"], "website": z["web"], "beschreibung": z["beschreibung"] or None})
    return st

# ---- Main ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--offline", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True, parents=True)
    mpath = OUT / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    valid = {page_url(s) for s in PAGES} | {ZENTREN_JSON} | {f["url"] for f in FORMS.values()}
    manifest["urls"] = {u: e for u, e in manifest.get("urls", {}).items() if u in valid}
    if not a.offline: fetch_all(manifest, a.force)

    docs, pages = [], {}
    fetched = now()
    for slug, (bereich, dtype) in PAGES.items():
        u = page_url(slug); f = RAW / f"{sha1(u)}.html"
        if not f.exists(): continue
        pg = parse_page(f.read_text(encoding="utf-8", errors="replace"))
        if not pg or not pg["items"]: continue
        ent = manifest["urls"].setdefault(u, {})
        text_hash = sha256("\n".join(t for _, t in pg["items"]).encode())
        if ent.get("sha256") != text_hash: ent["changed_at"] = ent.get("fetched_at") or fetched
        ent["sha256"] = text_hash
        pg.update(url=u, sha256=text_hash, fetched_at=ent.get("fetched_at", fetched), bereich=bereich)
        pages[slug] = pg
        for n, (sec, txt) in enumerate(sections(pg["items"], pg["title"])):
            docs.append({"id": f"{SOURCE_ID}:{sha1(u)}#{n}", "source_id": SOURCE_ID, "url": u, "title": pg["title"], "section": sec,
                         "text": txt, "lang": "de", "traeger": ["PVA"], "bundesland": ["AT"], "bereich": bereich, "doc_type": dtype,
                         "valid_from": stand_iso(pg["stand"]), "fetched_at": pg["fetched_at"], "sha256": text_hash, "license_note": LICENSE})
    find_links(pages)
    forms = build_forms(manifest, pages)
    leist, dropped = build_leistungen(pages, forms)
    stellen = build_stellen(pages)

    # Kontakt-Stelle PVA Landesstelle Wien: aus Kontakt-Seite (siehe CONTACT in curated.py)
    kt = norm(" ".join(t for _, t in pages["service-und-kontakt/kontakt"]["items"])) if "service-und-kontakt/kontakt" in pages else ""
    for s_ in STELLEN_EXTRA:
        s_ = dict(s_)
        miss = [b for b in s_.pop("belege", []) if norm(b) not in kt]
        if miss: print("BELEG NICHT GEFUNDEN:", s_["stelle_id"], miss, file=sys.stderr)
        stellen.append(s_)

    w = lambda name, rows: (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    w("documents.jsonl", docs); w("leistungen.jsonl", leist); w("stellen.jsonl", stellen); w("formulare.jsonl", forms)
    manifest.update(source_id=SOURCE_ID, fetched_at=fetched, n_docs=len(docs), n_pages=len(pages), n_leistungen=len(leist),
                    n_formulare=len(forms), n_stellen=len(stellen))
    manifest["urls_list"] = [{"url": u, "sha256": e.get("raw_sha256") or e.get("sha256"), "etag": e.get("etag"),
                              "last_modified": e.get("last_modified"), "status": e.get("status"), "final_url": e.get("final_url")}
                             for u, e in manifest["urls"].items()]
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    for d in dropped: print("ZITAT NICHT GEFUNDEN:", d, file=sys.stderr)
    print(f"pages={len(pages)} docs={len(docs)} leistungen={len(leist)} formulare={len(forms)} stellen={len(stellen)} dropped_quotes={len(dropped)}")

if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
