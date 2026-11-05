# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf", "certifi"]
# ///
"""FSW (Fonds Soziales Wien) -> Wissens-DB. Idempotent + inkrementell.
Aufruf: uv run knowledge/sources/fsw/ingest.py [--force] [--offline]
 --offline: kein Netz, nur raw/ neu verarbeiten. --force: ETag/Hash ignorieren.
"""
import ssl, certifi, hashlib, html, io, json, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urldefrag, unquote, quote

SSLCTX = ssl.create_default_context(cafile=certifi.where())
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RAW, OUT = HERE / "raw", HERE / "out"
RAW.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
BASE = "https://www.fsw.at"
UA = "SV-Lotse-Hackathon/0.1"
SOURCE = "fsw"
LICENSE = "© Fonds Soziales Wien; öffentliche Webseite, nur als Quelle mit Zitat/Link verwendet (keine Weitergabe als eigene Inhalte)."
OFFLINE = "--offline" in sys.argv
FORCE = "--force" in sys.argv
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

SEEDS = ["/p/pflege-betreuung", "/p/behinderung", "/p/wohnungslosigkeit", "/p/ihr-kostenbeitrag-ab-2025",
         "/p/ihr-kostenbeitrag", "/p/hilfe-kontakt", "/p/kontakt", "/p/pflege-betreuung-fragen-antworten",
         "/p/behinderung-fragen-antworten", "/p/wohnen-obdach-fragen-antworten", "/antrag",
         "/p/antrag-formular-finden", "/standorte", "/p/mitten-in-wien", "/p/alternative-wohnformen",
         "/p/wohnen-und-pflege", "/p/pflege-betreuung-daheim", "/p/kontakt-zu-den-beratungsstellen-leben-mit-behinderung",
         "/p/pflegende-angehoerige", "/p/fragen-antworten"]
# Depth-1-Entdeckung aus diesen Seeds; Muster, die NICHT geholt werden
DISCOVER_FROM = ["/p/pflege-betreuung", "/p/behinderung", "/p/wohnungslosigkeit", "/p/wohnen-und-pflege",
                 "/p/wohnen-mit-behinderung", "/p/pflege-betreuung-daheim", "/p/alternative-wohnformen",
                 "/p/mobilitaet-und-freizeit", "/p/ihr-kostenbeitrag", "/p/hilfe-kontakt"]
EXCLUDE = re.compile(r"pflegetag|presse|tagung|archiv|wiener-tag|expeerience|karriere|nachhaltig|geschaeftsbericht|"
                     r"informationsoffensive|pflege-couch|team-focus|wohnplattform|wpw-|eurocities|datenschutz|impressum|"
                     r"barrierefrei|bosanski|tuerkce|english|befragungen|zahlen-daten|das-unternehmen|ueber-den-fsw|"
                     r"hinweisgeber|informationssicherheit|foerderrichtlinien|foerderansuchen|foerderwesen|"
                     r"informationen-fuer-organisationen|broschueren|ilpn|anmeldung|1450-gesundheit|grundversorgung|"
                     r"studie|ombudsstelle|infothek|adressen-schulen|adressen-ambulatorien|freizeitaktivitaeten|"
                     r"strategie|qualitaetssicherung|projektablauf|wiener-wege", re.I)
MAX_PAGES = 130

def sha1(s): return hashlib.sha1(s.encode()).hexdigest()
def sha256(b): return hashlib.sha256(b).hexdigest()

# ---------- Fetch (höflich, ETag, 1 req/s) ----------
MAN_PATH = OUT / "manifest.json"
old = json.loads(MAN_PATH.read_text()) if MAN_PATH.exists() else {"urls": []}
state = {u["url"]: u for u in old.get("urls", [])}
_last = [0.0]
robots_disallow = ["/cpresources/", "/vendor/", "/.env", "/cache/"]  # robots.txt (geprüft 2026-11-05)

def allowed(url):
    p = url.replace(BASE, "")
    return not any(p.startswith(d) for d in robots_disallow)

def fetch(url, ext):
    """Gibt (bytes|None, rec) zurück. Nutzt raw/<sha1(url)>.<ext>, wenn unverändert."""
    f = RAW / f"{sha1(url)}.{ext}"
    rec = state.get(url, {"url": url})
    if OFFLINE or not allowed(url):
        return (f.read_bytes() if f.exists() else None), rec
    hdr = {"User-Agent": UA}
    if f.exists() and not FORCE:
        if rec.get("etag"): hdr["If-None-Match"] = rec["etag"]
        if rec.get("last_modified"): hdr["If-Modified-Since"] = rec["last_modified"]
    wait = 1.05 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    try:
        _last[0] = time.time()
        with urllib.request.urlopen(urllib.request.Request(quote(url, safe=":/?=&%#"), headers=hdr), timeout=40, context=SSLCTX) as r:
            data = r.read()
            new = {"url": url, "sha256": sha256(data), "etag": r.headers.get("ETag"),
                   "last_modified": r.headers.get("Last-Modified"), "status": r.status,
                   "fetched_at": NOW, "content_type": r.headers.get("Content-Type")}
            if rec.get("sha256") == new["sha256"] and f.exists():
                new["fetched_at"] = rec.get("fetched_at", NOW)   # unverändert -> stabiler Output
            else:
                f.write_bytes(data)
            state[url] = new
            return data, new
    except urllib.error.HTTPError as e:
        if e.code == 304 and f.exists():
            return f.read_bytes(), rec
        rec = dict(rec, status=e.code); state[url] = rec
        print("HTTP", e.code, url, file=sys.stderr)
        return (f.read_bytes() if f.exists() and e.code >= 500 else None), rec
    except Exception as e:
        print("ERR", url, e, file=sys.stderr)
        return (f.read_bytes() if f.exists() else None), rec

# ---------- HTML -> Blöcke ----------
BLOCK = {"p", "li", "div", "tr", "section", "br", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "dd", "dt"}
SKIPT = {"script", "style", "noscript", "svg", "form", "select", "button"}
class Ex(HTMLParser):
    def __init__(s):
        super().__init__(convert_charrefs=True)
        s.ctx = {}; s.lastblock = None; s.in_main = False; s.skip = 0; s.cur = []; s.blocks = []; s.links = []; s.h = None; s.a = None; s.title = None; s.in_title = False
    def flush(s, kind="p"):
        t = re.sub(r"\s+", " ", "".join(s.cur)).strip()
        s.cur = []
        if t: s.blocks.append((kind, t)); s.lastblock = t
    def handle_starttag(s, tag, at):
        at = dict(at)
        if tag == "title": s.in_title = True
        if tag == "main": s.in_main = True
        if not s.in_main: return
        if tag in SKIPT: s.skip += 1; return
        if s.skip: return
        if tag in BLOCK or tag in ("a",):
            if tag != "a": s.flush("p")
        if tag in ("h1", "h2", "h3", "h4"): s.h = tag
        if tag == "li": s.cur.append("• ")
        if tag == "a" and at.get("href"): s.a = [at["href"], []]; s.a_prev = s.lastblock
    def handle_endtag(s, tag):
        if tag == "title": s.in_title = False
        if tag == "main": s.flush(); s.in_main = False
        if not s.in_main: return
        if tag in SKIPT: s.skip = max(0, s.skip - 1); return
        if s.skip: return
        if tag == "a" and s.a:
            s.links.append((s.a[0], re.sub(r"\s+", " ", "".join(s.a[1])).strip())); s.ctx.setdefault(s.a[0], (s.links[-1][1], s.a_prev)); s.a = None
        if tag in BLOCK:
            s.flush("h" if (s.h and tag == s.h) else "p")
            if tag == s.h: s.h = None
    def handle_data(s, d):
        if s.in_title: s.title = (s.title or "") + d
        if s.in_main and not s.skip:
            s.cur.append(d)
            if s.a is not None: s.a[1].append(d)

def parse(htmlbytes):
    p = Ex(); p.feed(htmlbytes.decode("utf-8", "replace")); p.flush()
    return p

# Block-Heading-Erkennung: Ex.flush markiert Headings als "h"; Ebene nicht nötig
DROP_SECTIONS = re.compile(r"^(Fördert\. Stärkt\. Wirkt\.|FSW-Kund:innenservice|FSW Beratung und Service-Center|"
                           r"Alle Leistungen aus dem Bereich.*|Zugehörige Seiten|Weitere Informationen)$")
def sections(p, page_title):
    out, cur_t, buf, seen_h = [], page_title, [], False
    for kind, t in p.blocks:
        if not seen_h and kind != "h": continue   # Breadcrumbs vor der ersten Überschrift
        if kind == "h":
            seen_h = True
            if buf: out.append((cur_t, buf))
            cur_t, buf = t, []
        else:
            buf.append(t)
    if buf: out.append((cur_t, buf))
    res = []
    for t, b in out:
        if DROP_SECTIONS.match(t): continue
        b = [x for x in b if not re.match(r"^(Start|Kostenloses Rückrufservice|Standorte anzeigen|Leistungen auswählen)$", x)]
        if b: res.append((t, b))
    return res

def chunk(lines, limit=1800):
    cs, cur = [], ""
    for l in lines:
        while len(l) > limit:
            cut = l.rfind(" ", 0, limit); cut = cut if cut > 0 else limit
            if cur: cs.append(cur); cur = ""
            cs.append(l[:cut]); l = l[cut:].strip()
        if len(cur) + len(l) + 1 > limit and cur: cs.append(cur); cur = ""
        cur = (cur + "\n" + l).strip()
    if cur: cs.append(cur)
    return cs

# ---------- Seiten holen ----------
def norm(u):
    u = urldefrag(urljoin(BASE + "/", u))[0]
    return u.rstrip("/") if u != BASE + "/" else u

def is_page(u):
    if not u.startswith(BASE): return False
    path = u[len(BASE):]
    return (path.startswith("/p/") or path in ("/antrag", "/standorte")) and "?" not in path and not EXCLUDE.search(path)

pages = {}   # url -> (parsed, rec)
queue = [norm(BASE + s) for s in SEEDS]
discovered = set(queue)
def get_page(u):
    data, rec = fetch(u, "html")
    if data is None: return None
    pages[u] = (parse(data), rec); return pages[u]
for u in list(queue): get_page(u)
import importlib.util
spec = importlib.util.spec_from_file_location("leistungen_def", HERE / "leistungen_def.py")
LD = importlib.util.module_from_spec(spec); spec.loader.exec_module(LD)
for L_ in LD.LEISTUNGEN:   # alle in der Leistungsdefinition genannten Seiten sicher holen
    for u_ in L_["urls"]:
        h_ = norm(BASE + u_)
        if h_ not in discovered and u_.startswith("/p/") and len(discovered) < MAX_PAGES + 30:
            discovered.add(h_); get_page(h_)
for s in DISCOVER_FROM:
    u = norm(BASE + s)
    if u not in pages: continue
    for href, _ in pages[u][0].links:
        h = norm(href)
        if is_page(h) and h not in discovered and len(discovered) < MAX_PAGES:
            discovered.add(h); get_page(h)
# Formularfilter-Seiten (GET dropDown1) für Zuordnung Anliegen -> Formular
FILTER_BASE = BASE + "/p/antrag-formular-finden"
filter_map = {}
fp = pages.get(FILTER_BASE)
if fp:
    data, _ = fetch(FILTER_BASE, "html")
    opts = re.findall(r'<option value="(\d+)">([^<]+)</option>', data.decode("utf-8", "replace"))
    for val, label in opts:
        u = f"{FILTER_BASE}?dropDown1={val}"
        d2, _ = fetch(u, "html")
        if d2:
            pp = parse(d2)
            filter_map[html.unescape(label)] = [norm(h) for h, _ in pp.links if ".pdf" in h.lower()]

# ---------- documents.jsonl ----------
def doc_meta(url, title):
    path = url[len(BASE):]
    b, dt = ["D"], "leistungsinfo"
    if re.search(r"behinderung|inklusion|assistenz|fruehfoerderung|gehoerlos|sehbehinder|mobilitaet|fahrtendienst|hilfsmittel|dolmetsch|pflegegeldergaenzung|vollbetreut|teilbetreut|jahreskarte", path): b = ["E"]
    if re.search(r"wohnungslos|obdach|wohnen-mit-betreuung|individuelles-wohnen|organisiertes-wohnen|team-focus", path): b = ["E"]
    if re.search(r"kostenbeitrag", path): b, dt = ["D", "E"], "tarif"
    if re.search(r"fragen-antworten", path): dt = "faq"
    if re.search(r"standorte|kontakt|mitten-in-wien|anbieter|adressen", path): dt = "kontakt"
    if path in ("/antrag",) or "antrag-formular" in path: b, dt = ["F"], "formular"
    return b, dt

docs = []
for u, (p, rec) in pages.items():
    title = (p.title or "").split("|")[0].strip() or u
    h1 = next((t for k, t in p.blocks if k == "h"), title)
    b, dt = doc_meta(u, h1)
    n = 0
    for sec, lines in sections(p, h1):
        for c in chunk(lines):
            docs.append({"id": f"{SOURCE}:{sha1(u)}#{n}", "source_id": SOURCE, "url": u, "title": h1, "section": sec,
                         "text": c, "lang": "de", "traeger": ["FSW"], "bundesland": ["W"], "bereich": b,
                         "doc_type": dt, "valid_from": None, "fetched_at": rec.get("fetched_at", NOW),
                         "sha256": rec.get("sha256"), "license_note": LICENSE})
            n += 1

# FAQ-Antworten stecken im JSON-LD (FAQPage), nicht im sichtbaren main
for u, (p, rec) in pages.items():
    raw_ = RAW / f"{sha1(u)}.html"
    if not raw_.exists() or "Question" not in raw_.read_text("utf-8", "replace"): continue
    seen_q = set()
    for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', raw_.read_text("utf-8", "replace"), flags=re.S):
        try: j = json.loads(blk)
        except Exception: continue
        items = []
        def walk(x):
            if isinstance(x, dict):
                if x.get("@type") == "Question": items.append(x)
                for v in x.values(): walk(v)
            elif isinstance(x, list):
                for v in x: walk(v)
        walk(j)
        h1 = next((t for k, t in p.blocks if k == "h"), u)
        b, _ = doc_meta(u, h1)
        n0 = sum(1 for d in docs if d["url"] == u)
        for q in items:
            qn = q.get("name", "")
            if qn in seen_q: continue
            seen_q.add(qn)
            ans = html.unescape(re.sub(r"<[^>]+>", " ", (q.get("acceptedAnswer") or {}).get("text", "")))
            ans = re.sub(r"[ \t]+", " ", ans).strip()
            for c in chunk([ans]):
                docs.append({"id": f"{SOURCE}:{sha1(u)}#{n0}", "source_id": SOURCE, "url": u, "title": h1, "section": qn, "text": c, "lang": "de",
                             "traeger": ["FSW"], "bundesland": ["W"], "bereich": b, "doc_type": "faq", "valid_from": None,
                             "fetched_at": rec.get("fetched_at", NOW), "sha256": rec.get("sha256"), "license_note": LICENSE}); n0 += 1

# ---------- Stellen ----------
def stellen_from_standorte():
    u = BASE + "/standorte"
    if u not in pages: return []
    p, rec = pages[u]
    html_ = (RAW / f"{sha1(u)}.html").read_text("utf-8", "replace")
    html_ = html_[html_.find("Liste aller Standorte"):]
    html_ = re.sub(r"<script.*?</script>", "", html_, flags=re.S)
    html_ = re.sub(r"<br\s*/?>", "\n", html_)
    html_ = re.sub(r"</(p|div|h\d|li|a)>", "\n", html_)
    txt = html.unescape(re.sub(r"<[^>]+>", "", html_))
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in txt.split("\n")]
    lines = [l for l in lines if l]
    # Blöcke enden mit "Routenplanung"
    start = next((i for i, l in enumerate(lines) if l == "Kommen Sie vorbei!"), 0) + 2
    blocks, cur = [], []
    for l in lines[start:]:
        if l == "Routenplanung":
            if cur: blocks.append(cur)
            cur = []
        elif not l.startswith(("Cookie", "Die Google-Map", "Zu Standortliste")):
            cur.append(l)
    def slug(x):
        return re.sub(r"[^a-z0-9]+", "_", x.lower().replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")).strip("_")
    res = []
    for bl in blocks:
        if bl and bl[0] == "Beratung und Service-Center" and len(bl) > 1:
            name = "Beratung und Service-Center " + bl[1]; rest = bl[2:]
        else:
            name = bl[0]; rest = bl[1:]
        plz_i = next((i for i, l in enumerate(rest) if re.match(r"^\d{4} Wien$", l)), None)
        adr = plz = None
        if plz_i is not None:
            plz = rest[plz_i][:4]
            street = [l for l in rest[:plz_i] if not l.startswith(("Sprechstunden", "Terminvereinbarung"))]
            adr = ", ".join(street[-2:] if street and street[-1].startswith("(") else street[-1:]) if street else None
        if adr and plz: adr = (adr + f", {plz} Wien").replace(", (", " (")
        txt = "\n".join(rest)
        tel = re.search(r"Tel\.?:? ?(01[\d ]{5,})", txt)
        mail = re.search(r"[\w\.\-]+@[\w\.\-]+", txt) or re.search(r"Mail: ?([\w\.\-]+@[\w\.\-]+)", txt)
        zeiten = " ".join(l for l in rest if re.match(r"^(Mo|Do)", l)) or None
        if zeiten: zeiten = re.sub(r"\s+", " ", zeiten)
        hinw = "; ".join(l for l in rest if l.startswith(("Sprechstunden", "Terminvereinbarung")))[:300] or None
        zust = []
        if "Pflege und Betreuung" in name: zust = ["fsw_pflegeberatung", "mobile_pflege_wien", "pflegeheim_wien", "kostenbeitrag_fsw"]
        elif "Behinderung" in name: zust = ["fsw_behindertenhilfe_beratung"]
        elif "Obdach" in name: zust = ["obdach_wohnungslosenhilfe_wien"]
        elif "Kostenbeitrag" in name: zust = ["kostenbeitrag_fsw"]
        sid = "fsw_" + slug(name) + ("_" + slug(adr.split(",")[0].split(" ")[0]) if adr else "")
        res.append({"stelle_id": sid, "name": name, "typ": "beratung", "adresse": adr, "plz": plz, "bundesland": "W",
                    "telefon": tel.group(1).strip() if tel else None, "email": (mail.group(1) if mail and mail.lastindex else (mail.group(0) if mail else None)),
                    "url": u, "oeffnungszeiten": zeiten, "zustaendig_fuer": zust, "geo": None, "quelle_url": u, "hinweis": hinw})
    return res

stellen = stellen_from_standorte()
stellen.append({"stelle_id": "fsw_kundinnenservice_hotline", "name": "FSW-Kund:innenservice (Hotline, kostenloses Rückrufservice)", "typ": "hotline",
                "adresse": None, "plz": None, "bundesland": "W", "telefon": "01 24 5 24", "email": "kundinnenservice@fsw.at",
                "url": BASE + "/p/hilfe-kontakt", "oeffnungszeiten": "täglich 8:00–20:00 Uhr", "zustaendig_fuer": ["fsw_pflegeberatung", "mobile_pflege_wien", "kostenbeitrag_fsw"],
                "geo": None, "quelle_url": BASE + "/p/seniorinnen-wohngemeinschaften-basispaket"})

# ---------- Formulare ----------
from pypdf import PdfReader
LOCAL_DIR = ROOT / "_Source" / "Anträge und Formulare"
def pdf_info(data):
    try:
        r = PdfReader(io.BytesIO(data))
        fields = r.get_fields() or {}
        felder = []
        for name, f in fields.items():
            ft = str(f.get("/FT", ""))
            typ = "checkbox" if ft == "/Btn" else ("choice" if ft == "/Ch" else "text")
            tu = f.get("/TU")
            felder.append({"name": name, "label": str(tu) if tu else None, "typ": typ, "quelle_hint": None})
        text = ""
        try: text = (r.pages[0].extract_text() or "")[:600]
        except Exception: pass
        return {"pages": len(r.pages), "fillable": bool(fields), "felder": felder, "text0": text,
                "title": (r.metadata.get("/Title") if r.metadata else None), "moddate": (r.metadata.get("/ModDate") if r.metadata else None)}
    except Exception as e:
        return {"pages": None, "fillable": False, "felder": [], "text0": "", "error": str(e)}

HINTS = [(r"vorname", "vorname"), (r"(nach|fam)ilienname|nachname|zuname", "nachname"), (r"geburt", "geburtsdatum"), (r"sozialvers|svnr|versicherungsnummer", "svnr"),
         (r"iban", "iban"), (r"telefon|tel\b", "telefon"), (r"e-?mail", "email"), (r"plz|postleitzahl", "plz"), (r"stra(ß|ss)e|adresse", "adresse"), (r"pflegegeld", "pflegegeldstufe")]
def hint(n, l):
    s = f"{n} {l or ''}".lower()
    for rx, h in HINTS:
        if re.search(rx, s): return h
    return None

# Formular-Katalog: alle PDF-Links der Seite /antrag + Filterseiten
fm = {}   # url -> dict(name, kontext)
ap = pages.get(BASE + "/antrag")
if ap:
    p = ap[0]
    for href, txt in p.links:
        if ".pdf" in href.lower():
            u = norm(href)
            fm.setdefault(u, {"names": set()})
            t, prev_ = p.ctx.get(href, (txt, None))
            cand = t if t and not re.match(r"^\(?\s*PDF", t) else prev_
            if cand and "name" not in fm[u]:
                fm[u]["name"] = re.sub(r"\s*\(?\s*PDF,? ?[\d,\. ]*[KM]?B?\s*\)?\s*$", "", cand).strip()
for label, urls in filter_map.items():
    for u in urls:
        fm.setdefault(u, {"names": set()})
        fm[u]["names"].add(label)
NAME_FIX = {  # sprechende Namen, wo die Seite nur Dateiname liefert
    "Anliegen_FSW_interaktiv.pdf": "Ihr Anliegen an den FSW (Formular)",
    "FSW-Antrag-Beilage-Einrichtungswunsch.pdf": "Einrichtungswunsch für Wohn- und Pflegehäuser (Beilage zum Antrag)",
}
FORM_LEISTUNGEN = {
    "fsw-antrag-auf-foerderung-von-leistungen": ["mobile_pflege_wien", "heimhilfe_wien", "hauskrankenpflege_wien", "essen_auf_raedern_wien", "tageszentren_wien", "pflegeheim_wien", "senioren_wg_wien", "fsw_pflegeberatung", "obdach_wohnungslosenhilfe_wien", "vollbetreutes_wohnen_wien"],
    "FSW-Antrag-Beilage-Angehoerige": ["mobile_pflege_wien", "pflegeheim_wien", "vollbetreutes_wohnen_wien", "pflegegeldergaenzungsleistung_pa_wien"],
    "FSW-Antrag-Beilage-Personengemeinschaft": ["obdach_wohnungslosenhilfe_wien"],
    "FSW-Antrag-Beilage-Freizeitfahrtendienst": ["fahrtendienst_fahrtkostenersatz_wien"],
    "FSW-Befundbericht-Wohnen-und-Pflege": ["pflegeheim_wien", "wohnhaus_wien"],
    "FSW-Befundbericht-Kinder": ["pflege_kinder_stationaer_wien"],
    "FSW-Antrag-Beilage-Einrichtungswunsch": ["pflegeheim_wien", "wohnhaus_wien"],
    "Jahreskarte_der_WL_fuer_gehoerlose_Menschen": ["fahrtkostenersatz_gehoerlose_wien"],
    "antrag-foerderung-klimaticket": ["jahreskarte_sehbehinderte_wien"],
    "Antrag-auf-Aenderung-bzw-Verlaengerung-der-Foerderung": ["mobile_pflege_wien", "pflegeheim_wien", "kostenbeitrag_fsw"],
    "Vollmacht": ["fsw_pflegeberatung"], "FSW-SEPA-Lastschriftmandat": ["kostenbeitrag_fsw"],
    "haftungserklaerung": ["kostenbeitrag_fsw"],
}
EXTRA_MAP = [(r"behindertenhilfe|fruehfoerderung", ["fsw_behindertenhilfe_beratung", "mobile_fruehfoerderung_wien"]),
             (r"pflegegeldergaenzung|pge|verwendungsnachweis|selbsteinschaetzung", ["pflegegeldergaenzungsleistung_pa_wien"]),
             (r"ratenzahlung", ["kostenbeitrag_fsw"]), (r"anliegen", ["fsw_pflegeberatung"]), (r"ausfuellhilfe", ["fsw_pflegeberatung"])]
# Zusätzliche, nicht auf /antrag verlinkte Seitenformulare (aus Leistungsseiten): PDF-Links innerhalb von /p/-Seiten
for u, (p, rec) in pages.items():
    if u.endswith("/antrag") or "antrag-formular-finden" in u: continue
    for href, txt in p.links:
        h = norm(href)
        if h.lower().endswith(".pdf") and re.search(r"antrag|bedarfsmeldung|formular|vollmacht|nachweis|anmeld", h, re.I) and "/downloads/" in h:
            fm.setdefault(h, {"names": set()}).setdefault("name", txt if txt and not txt.startswith("PDF") else None)
            fm[h].setdefault("seen_on", u)

def stem(u): return re.sub(r"\.\d{8,}(?=\.pdf$)", "", unquote(u.rsplit("/", 1)[-1]))[:-4]
local_files = {f.name: f for f in LOCAL_DIR.glob("*.pdf")} if LOCAL_DIR.exists() else {}
def match_local(u):
    s = stem(u).lower()
    for n, f in local_files.items():
        ls = re.sub(r"\.\d{8,}(?=\.pdf$)", "", n)[:-4].lower()
        if ls == s or ls.startswith(s) or s.startswith(ls[:25]):
            return f
    if "bedarfsmeldung" in s: return next((f for n, f in local_files.items() if "bedarfsmeldung" in n.lower()), None)
    return None

formulare, abgleich = [], []
for u, info in sorted(fm.items()):
    data, rec = fetch(u, "pdf")
    if data is None: continue
    inf = pdf_info(data)
    s = stem(u)
    name = NAME_FIX.get(s + ".pdf") or info.get("name") or (sorted(info["names"])[0] if info["names"] else s)
    name = re.sub(r"\s*\(?\s*PDF,? ?[\d,\. ]*[KM]?B?\s*\)?\s*$", "", name).replace('"', "").strip()
    name = re.sub(r"\.pdf$", "", name).replace("_", " ").strip()
    lf = match_local(u)
    local_rel = None
    if lf:
        local_rel = str(lf.relative_to(ROOT))
        ld = lf.read_bytes(); li = pdf_info(ld)
        same = sha256(ld) == sha256(data)
        rf = {x["name"] for x in inf["felder"]}; lfn = {x["name"] for x in li["felder"]}
        abgleich.append({"lokal": local_rel, "remote": u, "sha_gleich": same, "felder_gleich": rf == lfn,
                         "felder_nur_lokal": sorted(lfn - rf)[:10], "felder_nur_remote": sorted(rf - lfn)[:10],
                         "seiten_lokal": li["pages"], "seiten_remote": inf["pages"], "bytes_lokal": len(ld), "bytes_remote": len(data),
                         "moddate_lokal": li.get("moddate"), "moddate_remote": inf.get("moddate"),
                         "text_erste_seite_gleich": li["text0"].strip() == inf["text0"].strip()})
        felder_src = li["felder"] if li["felder"] else inf["felder"]
    else:
        felder_src = inf["felder"]
    for f in felder_src: f["quelle_hint"] = hint(f["name"], f["label"])
    lids = next((v for k, v in FORM_LEISTUNGEN.items() if k.lower() == s.lower()), [])
    fid = re.sub(r"[^a-z0-9]+", "_", s.lower().replace("ä","ae").replace("ö","oe").replace("ü","ue")).strip("_")
    fid = fid if fid.startswith("fsw") else "fsw_" + fid
    if any(x["formular_id"] == fid for x in formulare): continue
    if not lids:
        for rx, ids in EXTRA_MAP:
            if re.search(rx, s, re.I): lids = ids; break
    formulare.append({"formular_id": fid, "name": name, "traeger": "FSW", "url_pdf": u, "local_pdf": local_rel,
                      "fillable": inf["fillable"], "felder": felder_src, "leistung_ids": lids,
                      "wer_fuellt_aus": "arzt" if "befundbericht" in s.lower() else "versicherte", "quelle_url": BASE + "/antrag",
                      "anliegen": sorted(info["names"]) or None, "seiten": inf["pages"], "sha256": sha256(data)})
# Bedarfsmeldung WG: lokal vorhanden, online nicht auf /antrag verlinkt -> separat aus WG-Seite suchen
wg = pages.get(BASE + "/p/seniorinnen-wohngemeinschaften-basispaket")
bm_local = next((f for n, f in local_files.items() if "bedarfsmeldung" in n.lower()), None)
if bm_local and not any(x["local_pdf"] and "Bedarfsmeldung" in x["local_pdf"] for x in formulare):
    ld = bm_local.read_bytes(); li = pdf_info(ld)
    cand = None
    for u, (p, _) in pages.items():
        for h, t in p.links:
            if "bedarfsmeldung" in h.lower(): cand = norm(h)
    remote_state = "online nicht gefunden (kein Link auf FSW-Seiten)"
    if cand:
        d2, _ = fetch(cand, "pdf")
        if d2:
            i2 = pdf_info(d2); remote_state = f"online {cand}: sha gleich={sha256(d2)==sha256(ld)}, felder gleich={ {x['name'] for x in i2['felder']}=={x['name'] for x in li['felder']} }"
    for f in li["felder"]: f["quelle_hint"] = hint(f["name"], f["label"])
    formulare.append({"formular_id": "fsw_bedarfsmeldung_senioren_wg_basispaket", "name": "Bedarfsmeldung Senior:innen-Wohngemeinschaft (Basispaket)",
                      "traeger": "FSW", "url_pdf": cand, "local_pdf": str(bm_local.relative_to(ROOT)), "fillable": li["fillable"],
                      "felder": li["felder"], "leistung_ids": ["senioren_wg_wien"], "wer_fuellt_aus": "versicherte",
                      "quelle_url": BASE + "/p/seniorinnen-wohngemeinschaften-basispaket", "anliegen": None, "seiten": li["pages"], "sha256": sha256(ld)})
    abgleich.append({"lokal": str(bm_local.relative_to(ROOT)), "remote": cand, "status": remote_state})

# ---------- Leistungen ----------
def page_sections(u):
    u = norm(BASE + u)
    if u not in pages: return []
    p = pages[u][0]
    h1 = next((t for k, t in p.blocks if k == "h"), u)
    return [(u, h1, s, "\n".join(l)) for s, l in sections(p, h1)]

def find_sec(urls, rx):
    res = []
    for u in urls:
        for pu, h1, s, txt in page_sections(u):
            if re.search(rx, s, re.I): res.append((pu, s, txt))
    return res

def first_text(u):
    ss = page_sections(u)
    if not ss: return None
    return ss[0][3]

leist = []
for L in LD.LEISTUNGEN:
    urls = L["urls"]
    stand = {u: pages[norm(BASE + u)][1].get("fetched_at", NOW) for u in urls if norm(BASE + u) in pages}
    if not stand: continue
    vor = [{"text": txt.split("\n")[0][:300], "quelle_url": pu, "zitat": txt[:600]} for pu, s, txt in find_sec(urls, r"voraussetzung|wer kann|für wen|zielgruppe")]
    kosten_secs = find_sec(urls, r"kosten|förderung")
    ablauf = find_sec(urls, r"beratung|anmeldung|antrag|ablauf|vermittlung|so (geht|funktioniert)")
    intro = None
    for u in urls:
        ss = page_sections(u)
        if ss:
            intro = ss[0][3]; break
    kurz = L.get("kurz") or (re.split(r"(?<=[.!?])\s", intro.replace("\n", " "))[:2] and " ".join(re.split(r"(?<=[.!?])\s", intro.replace("\n", " "))[:2])[:350])
    if L.get("faq"):
        for d in docs:
            if d["doc_type"] == "faq" and d["section"].startswith(L["faq"]) and d["url"].endswith(L["urls"][-1]):
                ablauf = [(d["url"], d["section"], d["text"])]
                kosten_secs = [(d["url"], "FAQ", d["text"])]
                vor = [{"text": d["section"], "quelle_url": d["url"], "zitat": d["text"][:600]}]
    leist.append({
        "leistung_id": L["id"], "name": L["name"], "kurz_einfach": kurz, "bereich": L["bereich"], "traeger": ["FSW"], "innerhalb_sv": False,
        "zielgruppe": L.get("zielgruppe"), "voraussetzungen": vor,
        "zustaendig": L.get("zustaendig", "Fonds Soziales Wien (FSW), Kund:innenservice; nur für Wohnsitz in Wien"),
        "antrag": {"formular_id": L.get("formular"), "wo": L.get("wo", "FSW-Kund:innenservice (Tel. 01 24 5 24), MeinFSW online, FSW Beratung und Service-Center"),
                   "online_url": None if L.get("wo") else "https://mein.fsw.at", "ablauf_zitat": [{"quelle_url": pu, "abschnitt": s, "zitat": txt[:600]} for pu, s, txt in ablauf][:3]},
        "unterlagen": L.get("unterlagen", []), "fristen": [], 
        "kosten": " | ".join(f"[{s}] {txt[:500]}" for pu, s, txt in kosten_secs)[:1200] or None,
        "kosten_quelle_url": kosten_secs[0][0] if kosten_secs else None,
        "abhaengigkeiten": L.get("abhaengigkeiten", ["pflegegeld"] if "D" in L["bereich"] else []),
        "trigger_im_dokument": L["trigger"], "bundesland": ["W"],
        "quellen": [{"url": norm(BASE + u), "stand": stand[u]} for u in stand],
        "confidence": L.get("confidence", "mittel"),
        "hinweis": "Außerhalb der Sozialversicherung (Land Wien / FSW). Kostenbeitrag individuell; keine Beurteilung des Pflegebedarfs durch den Lotsen.",
    })

# ---------- schreiben ----------
def dump(name, rows):
    with open(OUT / name, "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n")
dump("documents.jsonl", docs); dump("leistungen.jsonl", leist); dump("stellen.jsonl", stellen); dump("formulare.jsonl", formulare)
abgleich = list({(a["lokal"], a.get("remote")): a for a in abgleich}.values())
(OUT / "abgleich_lokale_formulare.json").write_text(json.dumps(abgleich, ensure_ascii=False, indent=1), "utf-8")
man = {"source_id": SOURCE, "fetched_at": max([r.get("fetched_at", "") for r in state.values()] or [NOW]), "n_docs": len(docs),
       "n_leistungen": len(leist), "n_stellen": len(stellen), "n_formulare": len(formulare), "urls": sorted(state.values(), key=lambda r: r["url"])}
MAN_PATH.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
print(f"pages={len(pages)} docs={len(docs)} leistungen={len(leist)} stellen={len(stellen)} formulare={len(formulare)}")
