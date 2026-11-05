# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "selectolax"]
# ///
"""Ingestion Sozialministeriumservice (www.sozialministeriumservice.gv.at) nach CONTRACT.md.

Aufruf:  uv run knowledge/sources/sozialministeriumservice/ingest.py [--offline] [--force]
  --offline  nichts laden (auch kein Link-Check/Geocoding), nur aus raw/ + manifest.json neu bauen
  --force    ETag/Last-Modified ignorieren, Links neu prüfen

Ablauf: (1) Seitenliste PAGES bedingt laden (If-None-Match/If-Modified-Since + sha256 des Texts),
(2) Formular-Kandidaten (Download-Links der Seiten) per HEAD/GET live prüfen (final_url, Content-Type),
(3) Outputs deterministisch aus raw/ + manifest.json bauen. Idempotent.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
import httpx
from selectolax.lexbor import LexborHTMLParser as P

ROOT = Path(__file__).resolve().parent
RAW, OUT = ROOT / "raw", ROOT / "out"
SOURCE_ID = "sozialministeriumservice"
UA = "SV-Lotse-Hackathon/0.1"
BASE = "https://www.sozialministeriumservice.gv.at"
DELAY = 1.1
LICENSE = ("Quelle: Sozialministeriumservice (www.sozialministeriumservice.gv.at), öffentlich zugängliche Seite, "
           "© Sozialministeriumservice. Keine ausdrückliche offene Lizenz erkennbar; Nutzung nur als Wissensquelle "
           "mit Quellenangabe im Hackathon-Prototyp. robots.txt: 'User-agent: * / Disallow:' (alles erlaubt).")
M = "/Menschen_mit_Behinderung/"
A = "/Angehoerige/Pflege_und_Betreuung/"
# pfad -> (bereiche, doc_type)
PAGES = {
 M + "Behindertenpass_und_Parkausweis/Behindertenpass_und_Parkausweise.de.html": (["E"], "leistungsinfo"),
 M + "Behindertenpass_und_Parkausweis/Behindertenpass/Behindertenpass.de.html": (["E"], "leistungsinfo"),
 M + "Behindertenpass_und_Parkausweis/Behindertenpass/zusatzeintragungen/zusatzeintragungen.de.html": (["E"], "leistungsinfo"),
 M + "Behindertenpass_und_Parkausweis/Parkausweis/Parkausweis.de.html": (["E"], "leistungsinfo"),
 A + "Pflegeunterstuetzungen.de.html": (["D", "E"], "leistungsinfo"),
 A + "24-Stunden-Betreuung/24-Stunden-Betreuung.de.html": (["D", "E"], "leistungsinfo"),
 A + "Pflegekarenz_und_-teilzeit/Pflegekarenz_und_-teilzeit.de.html": (["D", "E"], "leistungsinfo"),
 A + "Pflegende_Angehoerige/Unterstuetzung_fuer_pflegende_Angehoerige.de.html": (["D", "E"], "leistungsinfo"),
 M + "Finanzielle_Unterstuetzung/Finanzielle_Unterstuetzung.de.html": (["E"], "leistungsinfo"),
 M + "Finanzielle_Unterstuetzung/Sonstige_finanzielle_Vorteile/Sonstige_finanzielle_Vorteile_und_Unterstuetzungen.de.html": (["E"], "leistungsinfo"),
 M + "Finanzielle_Unterstuetzung/Sonstige_finanzielle_Vorteile/Unterstuetzungsfonds/Unterstuetzungsfonds.de.html": (["E"], "leistungsinfo"),
 M + "Finanzielle_Unterstuetzung/Mobilitaetsfoerderungen/Mobilitaetsfoerderungen.de.html": (["E"], "leistungsinfo"),
 "/Ueber_uns/Sozialministeriumservice/Kontakt/Kontakt_zum_Sozialministeriumservice.de.html": (["F"], "kontakt"),
 "/Ueber_uns/Sozialministeriumservice/Landesstellen/Landesstellen_des_Sozialministeriumservice.de.html": (["F"], "kontakt"),
 "/Ueber_uns/Sozialministeriumservice/Landesstellen/Wien/Sozialministeriumservice___Landesstelle_Wien.de.html": (["F"], "kontakt"),
}
WIEN_PAGE = BASE + "/Ueber_uns/Sozialministeriumservice/Landesstellen/Wien/Sozialministeriumservice___Landesstelle_Wien.de.html"
KONTAKT_PAGE = BASE + "/Ueber_uns/Sozialministeriumservice/Kontakt/Kontakt_zum_Sozialministeriumservice.de.html"

# id, name, bereich, seiten(Pfad-Teilstring), trigger, abhaengigkeiten, kurz_einfach, zuständig, online_antrag (Teilstring des Linktexts)
LEISTUNGEN = [
 dict(id="behindertenpass", name="Behindertenpass", bereich=["E"], seiten=["Behindertenpass/Behindertenpass.de", "zusatzeintragungen"],
      trigger=["Behindertenpass", "Grad der Behinderung", "Zusatzeintragung"], abh=[],
      kurz="Der Behindertenpass ist ein Ausweis im Scheckkartenformat, der den Grad der Behinderung nachweist. Antrag und Ausstellung sind gebührenfrei.",
      zust="Sozialministeriumservice, Landesstelle des Bundeslandes (Wien: Landesstelle Wien).",
      online=["Online Antrag auf Ausstellung eines Behindertenpasses"], form_re=r"BEHINDERTENPASS_Antrag|Behindertenpass"),
 dict(id="parkausweis_29b", name="Parkausweis nach § 29b StVO", bereich=["E"], seiten=["Parkausweis.de"],
      trigger=["Parkausweis", "§ 29b", "29b StVO"], abh=["behindertenpass"],
      kurz="Der Parkausweis nach § 29b StVO erlaubt Parken an besonderen Stellen. Voraussetzung ist ein Behindertenpass mit passender Zusatzeintragung. Er ist gebührenfrei.",
      zust="Sozialministeriumservice, Landesstelle des Bundeslandes.", online=["Online Antrag auf Ausstellung eines Ausweises"],
      form_re=r"Parkausweis"),
 dict(id="foerderung_24h_betreuung", name="Förderung der 24-Stunden-Betreuung", bereich=["D", "E"], seiten=["24-Stunden-Betreuung.de"],
      trigger=["24-Stunden-Betreuung", "Betreuungskraft", "Hausbetreuungsgesetz"], abh=["pflegegeld"],
      kurz="Wer zuhause rund um die Uhr betreut wird, kann unabhängig vom Vermögen einen monatlichen Zuschuss zur 24-Stunden-Betreuung bekommen.",
      zust="Sozialministeriumservice, Landesstelle des Bundeslandes.", online=["Ansuchen auf Gewährung eines Zuschusses"], form_re=r"24H|24-Stunden|24h"),
 dict(id="unterstuetzungsfonds_behinderung", name="Unterstützungsfonds für Menschen mit Behinderung", bereich=["E"], seiten=["Unterstuetzungsfonds.de"],
      trigger=["Unterstützungsfonds", "soziale Notlage", "Treppenlift"], abh=["behindertenpass"],
      kurz="Einmaliger Zuschuss für Menschen mit Behinderung in einer sozialen Notlage, z. B. für Umbauten, Treppenlifte oder Assistenzhunde. Antrag vor dem Vorhaben stellen.",
      zust="Sozialministeriumservice, Landesstelle des Bundeslandes.", online=["Online Antrag auf Zuwendung aus dem Unterstützungsfonds"],
      form_re=r"Unterst(ue|ü)tzungsfonds|Zuschus"),
 dict(id="angehoerigen_unterstuetzung_ersatzpflege", name="Zuwendung zu den Kosten der Ersatzpflege (Unterstützung für pflegende Angehörige)", bereich=["D", "E"],
      seiten=["Unterstuetzung_fuer_pflegende_Angehoerige.de"], trigger=["Ersatzpflege", "pflegende Angehörige", "Verhinderung"], abh=["pflegegeld"],
      kurz="Pflegende Angehörige können Geld für eine Ersatzpflege bekommen, wenn sie wegen Krankheit, Urlaub oder anderen wichtigen Gründen verhindert sind.",
      zust="Sozialministeriumservice, Landesstelle des Bundeslandes.", online=["Ansuchen für die Gewährung von Zuwendungen"],
      form_re=r"pflegende_Angehoerige_antrag|Ersatzpflege"),
 dict(id="pflegekurse_zuwendung", name="Zuwendung für Pflegekurse (pflegende Angehörige)", bereich=["D", "E"],
      seiten=["Unterstuetzung_fuer_pflegende_Angehoerige.de"], trigger=["Pflegekurse", "Pflegekurs"], abh=["pflegegeld"],
      kurz="Nahe Angehörige können bei geringem Einkommen bis zu 200 € pro Jahr für Pflegekurse bekommen.",
      zust="Sozialministeriumservice, Landesstelle des Bundeslandes.", online=["Online Antrag: Pflegekurse"], form_re=r"Pflegekurse"),
 dict(id="pflegekarenzgeld", name="Pflegekarenzgeld (Pflegekarenz und Pflegeteilzeit)", bereich=["D", "E"], seiten=["Pflegekarenz_und_-teilzeit.de"],
      trigger=["Pflegekarenz", "Pflegeteilzeit", "Pflegekarenzgeld", "Familienhospizkarenz"], abh=["pflegegeld"],
      kurz="Wer einen nahen Angehörigen pflegt, kann mit dem Arbeitgeber 1 bis 3 Monate Pflegekarenz oder Pflegeteilzeit vereinbaren und dafür Pflegekarenzgeld beantragen.",
      zust="Sozialministeriumservice, Landesstelle des Bundeslandes.", online=["Antrag auf Pflegekarenzgeld"], form_re=r"pflegekarenz|Pflegekarenzgeld"),
]
# Formular-Kandidaten: Dateiendung + Namensfilter (Infoblätter/Richtlinien/Datenschutz/Broschüren sind KEINE Formulare)
FORM_EXT = re.compile(r"\.(pdf|docx?|xlsx?)$", re.I)
FORM_YES = re.compile(r"antrag|ansuchen|ersatzpflegebest|bestaetigung|wechsel_oder|konto-ueberweisung|kontoerklaerung", re.I)
FORM_NO = re.compile(r"informationspflicht|richtlinie|checkliste|infoblatt|broschuere|folder|faltkarte|gegenueberstellung|organigramm|_RL_|projektfoerderung|rahmenvertrag|29bAusweis", re.I)
NOFORM_TYPES = ("text/html", "video/", "audio/")

sha1 = lambda s: hashlib.sha1(s.encode()).hexdigest()
sha256 = lambda b: hashlib.sha256(b).hexdigest()
now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
ws = lambda s: re.sub(r"\s+", " ", s.replace("\xa0", " ").replace("­", "")).strip()
def url_of(p): return BASE + p

# ---- Laden -----------------------------------------------------------------
def get(cl, state, u, hdr=None):
    wait = DELAY - (time.time() - state["last"])
    if wait > 0: time.sleep(wait)
    try:
        r = cl.get(u, headers=hdr or {}); state["last"] = time.time(); return r
    except httpx.HTTPError as e:
        state["last"] = time.time(); print("ERR", u, e, file=sys.stderr); return None

def fetch_pages(manifest, force, cl, st):
    RAW.mkdir(exist_ok=True)
    urls = manifest.setdefault("urls", {})
    for path in PAGES:
        u = url_of(path); ent = urls.get(u, {}); hdr = {}
        f = RAW / f"{sha1(u)}.html"
        if not force and f.exists():
            if ent.get("etag"): hdr["If-None-Match"] = ent["etag"]
            if ent.get("last_modified"): hdr["If-Modified-Since"] = ent["last_modified"]
        r = get(cl, st, u, hdr)
        if r is None: ent["status"] = "error"; urls[u] = ent; continue
        ent["status"] = r.status_code
        if r.status_code == 304: print("304", path[-40:]); urls[u] = ent; continue
        if r.status_code != 200: print(r.status_code, u, file=sys.stderr); urls[u] = ent; continue
        f.write_bytes(r.content)
        ent.update(etag=r.headers.get("etag"), last_modified=r.headers.get("last-modified"), fetched_at=now(),
                   final_url=str(r.url), raw_sha256=sha256(r.content))
        urls[u] = ent; print("200", path[-50:])

def check_link(cl, st, u, cache, force):
    """Live-Check: gibt dict(final_url, status, content_type, bytes, ok) – gecacht je Lauf-Tag."""
    c = cache.get(u)
    if c and not force and c.get("checked_at", "")[:10] == now()[:10]: return c
    res = dict(url=u, checked_at=now(), ok=False, status=None)
    wait = DELAY - (time.time() - st["last"])
    if wait > 0: time.sleep(wait)
    try:
        with cl.stream("GET", u, headers={"Range": "bytes=0-1023"}) as r:
            st["last"] = time.time()
            res.update(status=r.status_code, final_url=str(r.url), content_type=(r.headers.get("content-type") or "").split(";")[0].strip().lower())
            cr = r.headers.get("content-range", "")
            res["bytes"] = int(cr.split("/")[-1]) if "/" in cr and cr.split("/")[-1].isdigit() else (int(r.headers["content-length"]) if r.headers.get("content-length", "").isdigit() else None)
            res["ok"] = r.status_code in (200, 206)
    except httpx.HTTPError as e:
        st["last"] = time.time(); res["error"] = e.__class__.__name__
    cache[u] = res
    return res

# ---- Parsen ----------------------------------------------------------------
HEADS = ("h1", "h2", "h3", "h4", "h5", "h6")
BLOCK = "h1,h2,h3,h4,h5,h6,p,li,td,th,dt,dd,div,figcaption,summary,blockquote"
DROP_LINE = re.compile(r"^(©|Leichter Lesen$|Zum Seiteninhalt|Antrag$)")
def parse_page(html: str):
    t = P(html)
    c = t.css_first("#maincontent") or t.css_first("main")
    if c is None: return None
    for n in c.css("script,style,noscript,nav,form"): n.decompose()
    h1 = c.css_first("h1"); title = ws(h1.text()) if h1 else ""
    if not title:
        tt = t.css_first("title"); title = ws(tt.text()).split("|")[0].strip() if tt else ""
    items = []
    for el in c.css(BLOCK):
        if len(el.css(BLOCK)) > 1: continue
        tx = ws(el.text(separator=" "))
        if not tx or DROP_LINE.match(tx): continue
        items.append(("h" if el.tag in HEADS else "p", tx))
    links = []
    for a in c.css("a[href]"):
        h = a.attributes.get("href") or ""
        if h.startswith(("#", "mailto:", "tel:", "javascript:")): continue
        links.append((ws(a.text(separator=" ")), h.replace("&amp;", "&")))
    lines = [ws(x) for x in c.text(separator="\n").split("\n") if ws(x)]
    return dict(title=title, items=items, links=links, lines=lines)

PSEUDO = re.compile(r"^(Voraussetzung|Wer |Welche |Wo liegt|Antragstellung|Höhe der|Unterlagen|Zielgruppe)")
def sections(items, title):
    secs, cur, head = [], [], title
    for k, tx in items:
        if k != "h" and len(tx) < 100 and not tx.endswith((".", ":")) and PSEUDO.match(tx): k = "h"
        if k == "h":
            if cur: secs.append((head, cur))
            head, cur = tx, []
        else: cur.append(tx)
    if cur: secs.append((head, cur))
    return secs

def chunk(texts, limit=1900):
    out, buf = [], ""
    for t in texts:
        while len(t) > limit:
            cut = t.rfind(" ", 0, limit); out.append((buf + "\n" + t[:cut]).strip() if buf else t[:cut]); buf = ""; t = t[cut:].strip()
        if len(buf) + len(t) + 1 > limit and buf: out.append(buf); buf = t
        else: buf = (buf + "\n" + t) if buf else t
    if buf: out.append(buf)
    return out

def load_pages():
    pages = {}
    for path, (bereich, dt) in PAGES.items():
        u = url_of(path); f = RAW / f"{sha1(u)}.html"
        if not f.exists(): continue
        pp = parse_page(f.read_text(encoding="utf-8", errors="ignore"))
        if pp: pp.update(url=u, path=path, bereich=bereich, doc_type=dt); pages[path] = pp
    return pages

def build_documents(pages, manifest):
    docs = []
    for path, pg in pages.items():
        ent = (manifest.get("urls") or {}).get(pg["url"], {})
        body = "\n".join(t for _, t in pg["items"])
        sh = sha256(body.encode()); fa = ent.get("fetched_at") or now()
        n = 0
        for head, texts in sections(pg["items"], pg["title"]):
            for ch in chunk(texts):
                if len(ch) < 30: continue
                docs.append(dict(id=f"{SOURCE_ID}:{sha1(pg['url'])}#{n}", source_id=SOURCE_ID, url=pg["url"], title=pg["title"],
                                 section=head, text=ch, lang="de", traeger=["Sozialministeriumservice"],
                                 bundesland=["W"] if "Landesstelle_Wien" in path else ["AT"], bereich=pg["bereich"], doc_type=pg["doc_type"],
                                 valid_from=None, fetched_at=fa, sha256=sh, license_note=LICENSE)); n += 1
    return docs

# ---- Formulare / Leistungen / Stellen -------------------------------------
def unwrap(u):
    """mymailwall-Tracking-Link -> Ziel-URL (Parameter u)."""
    if "mymailwall.com" in u:
        from urllib.parse import parse_qs
        t = parse_qs(urlparse(u).query).get("u")
        if t: return t[0].strip()
    return u

def clean_name(txt, href):
    n = re.sub(r"\s*\((?:PDF|DOCX?|XLSX?)[^)]*\)\s*$", "", txt, flags=re.I)
    n = re.sub(r"^Antrag:\s*", "Antrag: ", n).strip()
    if len(n) < 12 or re.search(r"\.(docx?|pdf|xlsx?)$|^\d\d |^[A-Za-z]+[-_][A-Za-z]+-?\d{4}$", n, re.I):
        n = re.sub(r"\s+", " ", re.sub(r"^(ACC - |\d\d[ _])", "", unquote(Path(urlparse(href).path).stem).replace("_", " ").replace("-", " "))).strip()
        n = n[:1].upper() + n[1:]
    return n

def collect_form_candidates(pages):
    cands = {}  # abs-url -> dict
    for path, pg in pages.items():
        for txt, href in pg["links"]:
            absu = urljoin(pg["url"], href)
            if urlparse(absu).netloc.replace("www.", "") != "sozialministeriumservice.gv.at": continue
            if not FORM_EXT.search(urlparse(absu).path): continue
            fn = Path(urlparse(absu).path).name
            if FORM_NO.search(fn) or not (FORM_YES.search(fn) or FORM_YES.search(txt)): continue
            c = cands.setdefault(absu, dict(url=absu, name=clean_name(txt, absu), pages=[]))
            c["pages"].append(pg["url"])
    return cands

def build_formulare(cands, linkcache, leistungen_def):
    forms = {}
    for u, c in sorted(cands.items()):
        lc = linkcache.get(u)
        if not lc or not lc.get("ok"): continue
        ct = lc.get("content_type", "")
        if ct.startswith(NOFORM_TYPES): continue  # HTML-Seite/Video ≠ Formular
        fin = lc["final_url"]
        if fin in forms: forms[fin]["gefunden_auf"] = sorted(set(forms[fin]["gefunden_auf"]) | set(c["pages"])); continue
        fn = Path(urlparse(fin).path).name
        lids = [l["id"] for l in leistungen_def if re.search(l["form_re"], fn + " " + c["name"], re.I) and any(s in p for s in l["seiten"] for p in c["pages"])]
        ext = Path(fn).suffix.lower().lstrip(".")
        forms[fin] = dict(formular_id="sms_" + re.sub(r"[^a-z0-9]+", "_", Path(fn).stem.lower()).strip("_")[:60], name=c["name"], traeger="Sozialministeriumservice",
                          url_pdf=fin, local_pdf=None, fillable=None, felder=[], leistung_ids=lids, wer_fuellt_aus="versicherte",
                          quelle_url=c["pages"][0], gefunden_auf=sorted(set(c["pages"])), format=ext, content_type=ct,
                          bytes=lc.get("bytes"), geprueft_am=lc["checked_at"])
    return sorted(forms.values(), key=lambda f: f["formular_id"])

SENT = re.compile(r"(?<=[a-zäöüß]{3}[.!?])\s*(?=[A-ZÄÖÜ„\"])")
def sentences(texts):
    return [s.strip() for t in texts for s in SENT.split(t) if len(s.strip()) > 20]

def section_texts(pages, seiten, head_re):
    out = []
    for path, pg in pages.items():
        if not any(s in path for s in seiten): continue
        for head, texts in sections(pg["items"], pg["title"]):
            if re.search(head_re, head, re.I): out += [(t, pg["url"]) for t in texts]
    return out

def build_leistungen(pages, formulare, linkcache):
    out = []
    for L in LEISTUNGEN:
        pgs = [pg for p, pg in pages.items() if any(s in p for s in L["seiten"])]
        if not pgs: continue
        quellen = [dict(url=pg["url"], stand=(linkcache.get("_stand") or {}).get(pg["url"])) for pg in pgs]
        def q(head_re, extra=None):
            r = []
            for tx, u in section_texts(pages, L["seiten"], head_re):
                if L["id"] == "pflegekurse_zuwendung" and not re.search(r"Pflegekurs|Kurs", tx + head_re) and "Einkommen" not in tx: pass
                r.append(dict(text=tx, quelle_url=u, zitat=tx))
            return r
        voraus = q(r"Voraussetzung|Wer hat Anspruch|Wer bekommt|Zielgruppe|Wo liegt die Einkommensgrenze")
        if not voraus:  # Fallback: Text direkt unter einer Zeile "Voraussetzung…" (steht teils in verschachtelten Blöcken)
            for pg in pgs:
                ls = pg["lines"]
                for i, ln in enumerate(ls):
                    if ln.startswith("Voraussetzung") and len(ln) < 100 and i + 1 < len(ls):
                        for nx in ls[i + 1:i + 3]:
                            if not nx.startswith(("Antrag", "Online")): voraus.append(dict(text=nx, quelle_url=pg["url"], zitat=nx))
                        break
        unterlagen = [t for t, _ in section_texts(pages, L["seiten"], r"Unterlagen")]
        # Kosten/Höhe/Fristen: wörtliche Sätze mit Schlüsselwörtern
        allsent = [(s, pg["url"]) for pg in pgs for _, tx in pg["items"] for s in sentences([tx])]
        kosten = [s for s, _ in allsent if re.search(r"gebührenfrei|kostenlos|Förderbetrag|maximal.*€|EUR \d|€ ?\d|beträgt", s)][:3]
        fristen = [s for s, _ in allsent if re.search(r"vor Realisierung|VOR Realisierung|Frist|innerhalb von|Antragstellung (?:kann|hat|muss)|Antragsstellung", s)][:3]
        forms = [f for f in formulare if L["id"] in f["leistung_ids"]]
        online = None
        for pg in pgs:
            for txt, href in pg["links"]:
                if any(k in txt for k in L["online"]) and href.startswith("http"):
                    online = unwrap(urljoin(pg["url"], href))
                    break
            if online: break
        olc = linkcache.get(online) if online else None
        if online and not (olc and olc.get("ok")): online = None
        # NICHT final_url: Online-Anträge leiten auf ein ID-Austria-Login mit Einmal-Token um (nicht stabil) -> Einstiegs-URL behalten
        out.append(dict(leistung_id=L["id"], name=L["name"], kurz_einfach=L["kurz"], bereich=L["bereich"], traeger=["Sozialministeriumservice"],
                        innerhalb_sv=False, zielgruppe=None, voraussetzungen=voraus[:8], zustaendig=L["zust"],
                        antrag=dict(formular_id=forms[0]["formular_id"] if forms else None, online_login="ID Austria / Bürgerkarte" if online and "formularservice" in online else None,
                                    wo="Landesstelle des Sozialministeriumservice (Wien: Babenbergerstraße 5, 1010 Wien), per Post, E-Mail oder persönlich" ,
                                    online_url=online),
                        unterlagen=unterlagen[:15], fristen=fristen, kosten=" ".join(kosten) or None, abhaengigkeiten=L["abh"],
                        trigger_im_dokument=L["trigger"], bundesland=["AT"], quellen=quellen,
                        confidence="mittel" if (voraus and forms) else "niedrig"))
    return out

def build_stellen(pages, manifest):
    pg = pages.get(next((p for p in pages if "Landesstelle_Wien" in p), ""))
    if not pg: return []
    txt = "\n".join(t for _, t in pg["items"])
    raw = P(RAW.joinpath(f"{sha1(pg['url'])}.html").read_text(encoding="utf-8", errors="ignore")).css_first("#maincontent").text(separator="\n")
    raw = re.sub(r"[ \t\xa0]+", " ", raw)
    adr = re.search(r"([A-ZÄÖÜ][\w\-ßäöü]+(?:gasse|straße|platz|allee)\s*\d+\w*),\s*(\d{4})\s*Wien", raw)
    tel = re.search(r"Tel:\s*([\d/ +]+)", raw); email = re.search(r"[\w.\-]+@sozialministeriumservice\.gv\.at", raw)
    zeiten = []
    for lab in ("Öffnungszeiten", "Beratungszeiten"):
        m = re.search(lab + r"\s*\n((?:(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|außerhalb)[^\n]*\n?)+)", raw)
        if m: zeiten.append(f"{lab}: " + "; ".join(ws(x) for x in m.group(1).strip().split("\n")))
    geo = (manifest.get("geocode") or {}).get("Babenbergerstraße 5, 1010 Wien")
    stellen = []
    if adr:
        stellen.append(dict(stelle_id="sms_landesstelle_wien", name="Sozialministeriumservice – Landesstelle Wien", typ="traeger",
                            adresse=f"{adr.group(1)}, {adr.group(2)} Wien", plz=adr.group(2), bundesland="W",
                            telefon=ws(tel.group(1)) if tel else None, email=email.group(0) if email else None, url=pg["url"],
                            oeffnungszeiten=" | ".join(zeiten) or None,
                            zustaendig_fuer=[l["id"] for l in LEISTUNGEN], geo=geo, quelle_url=pg["url"]))
    kp = pages.get(next((p for p in pages if "Kontakt_zum" in p), ""))
    if kp:
        stellen.append(dict(stelle_id="sms_hotline", name="Sozialministeriumservice – Bundesweites Info-Telefon", typ="hotline", adresse=None, plz=None,
                            bundesland="AT", telefon="05 99 88", email=None, url=kp["url"], oeffnungszeiten=None,
                            zustaendig_fuer=[l["id"] for l in LEISTUNGEN], geo=None, quelle_url=BASE + "/"))
    return stellen

def geocode(cl, st, manifest):
    g = manifest.setdefault("geocode", {}); q = "Babenbergerstraße 5, 1010 Wien"
    if q in g and g[q]: return
    wait = DELAY - (time.time() - st["last"])
    if wait > 0: time.sleep(wait)
    try:
        r = cl.get("https://nominatim.openstreetmap.org/search", params=dict(q=q, format="json", limit=1, countrycodes="at"))
        st["last"] = time.time()
        j = r.json()
        if j: g[q] = [round(float(j[0]["lat"]), 6), round(float(j[0]["lon"]), 6)]; manifest["geocode_note"] = "Koordinate: © OpenStreetMap-Mitwirkende (ODbL) via Nominatim"
    except Exception as e: print("geocode ERR", e, file=sys.stderr)

def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--offline", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)
    mf = OUT / "manifest.json"
    manifest = json.loads(mf.read_text()) if mf.exists() else {}
    manifest["source_id"] = SOURCE_ID
    if isinstance(manifest.get("urls"), list): manifest["urls"] = {e["url"]: e for e in manifest["urls"]}
    linkcache = manifest.setdefault("links", {})
    if not a.offline:
        st = {"last": 0.0}
        with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=30) as cl:
            fetch_pages(manifest, a.force, cl, st)
            pages = load_pages()
            cands = collect_form_candidates(pages)
            online = {unwrap(urljoin(pg["url"], h).replace("&amp;", "&")) for pg in pages.values() for _, h in pg["links"]
                      if any(k in h for k in ("formularservice.gv.at", "mein-ratgeber.at", "mymailwall"))}
            for u in sorted(set(cands) | online): check_link(cl, st, u, linkcache, a.force)
            geocode(cl, st, manifest)
        manifest["fetched_at"] = now()
    pages = load_pages()
    cands = collect_form_candidates(pages)
    for p in pages.values():  # Stand: Last-Modified, falls vorhanden
        e = manifest["urls"].get(p["url"], {}); linkcache.setdefault("_stand", {})[p["url"]] = (e.get("last_modified") or (e.get("fetched_at") or "")[:10] or None)
    docs = build_documents(pages, manifest)
    formulare = build_formulare(cands, linkcache, LEISTUNGEN)
    leistungen = build_leistungen(pages, formulare, linkcache)
    stellen = build_stellen(pages, manifest)
    write_jsonl(OUT / "documents.jsonl", docs); write_jsonl(OUT / "formulare.jsonl", formulare)
    write_jsonl(OUT / "leistungen.jsonl", leistungen); write_jsonl(OUT / "stellen.jsonl", stellen)
    manifest.update(n_docs=len(docs), n_leistungen=len(leistungen), n_formulare=len(formulare), n_stellen=len(stellen))
    ul = [dict({k: v for k, v in e.items() if k != "url"}, url=u) for u, e in sorted(manifest["urls"].items())]
    manifest["urls"] = ul
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"docs={len(docs)} leistungen={len(leistungen)} formulare={len(formulare)} stellen={len(stellen)}")

if __name__ == "__main__":
    main()
