"""Gemeinsamer Helper für svs / bvaeb / aek_wien (CONTRACT.md). Python >=3.11, deps: requests, beautifulsoup4, lxml."""
import hashlib, json, re, time, datetime as dt
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urldefrag
import requests
from bs4 import BeautifulSoup, Comment

UA = "SV-Lotse-Hackathon/0.1"
DELAY = 1.1
NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
import os
OFFLINE = bool(os.environ.get('SV_OFFLINE'))  # nur raw/-Cache verwenden (schneller Neuaufbau der Ableitungen)
MAXCH = 1900
NOISE = {'center','text','textbox','tile','Mehr Informationen','Inhalte relevant für:','download_info','svscontent','Content Start','Content Ende'}

def sha1(s): return hashlib.sha1(s.encode()).hexdigest()
def sha256(b): return hashlib.sha256(b).hexdigest()

class Fetcher:
    def __init__(self, base: Path, source_id, hash_fn=None):
        self.base, self.sid, self.hash_fn = base, source_id, hash_fn
        (base / "raw").mkdir(parents=True, exist_ok=True)
        (base / "out").mkdir(parents=True, exist_ok=True)
        self.mf_path = base / "out" / "manifest.json"
        self.old = {}
        if self.mf_path.exists():
            for u in json.loads(self.mf_path.read_text()).get("urls", []): self.old[u["url"]] = u
        self.new = {}; self.last = 0; self.s = requests.Session(); self.s.headers["User-Agent"] = UA
        self.changed = 0

    def get(self, url):
        """liefert (html_text|None, status). Bedingtes GET; bei 304 wird raw/ wiederverwendet."""
        raw = self.base / "raw" / (sha1(url) + ".html")
        o = self.old.get(url, {}); h = {}
        if raw.exists():
            if o.get("etag"): h["If-None-Match"] = o["etag"]
            if o.get("last_modified"): h["If-Modified-Since"] = o["last_modified"]
        if OFFLINE and raw.exists():
            self.new[url] = {**o, "status": "offline-cache"}; return raw.read_text(encoding="utf8"), 0
        wait = DELAY - (time.time() - self.last)
        if wait > 0: time.sleep(wait)
        try: r = self.s.get(url, headers=h, timeout=30)
        except Exception as e:
            if raw.exists() and o:  # Netzwerkfehler: letzten bekannten Stand weiterverwenden (Manifest unverändert)
                self.new[url] = {**o, "status": "stale-cache"}; return raw.read_text(encoding="utf8"), 0
            self.new[url] = {"url": url, "status": f"error:{type(e).__name__}", "sha256": o.get("sha256"), "etag": None, "last_modified": None}
            return None, 0
        self.last = time.time()
        if r.status_code == 304 and raw.exists():
            self.new[url] = {**o, "status": 304}; return raw.read_text(encoding="utf8"), 304
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            self.new[url] = {"url": url, "status": r.status_code, "sha256": None, "etag": None, "last_modified": None}
            return None, r.status_code
        r.encoding = r.encoding or "utf-8"
        txt = r.content.decode("utf-8", "replace")
        # Hash über den extrahierten Inhalt (rohes HTML enthält volatile Tokens/Zeitstempel)
        sh = sha256((self.hash_fn(txt) if self.hash_fn else txt).encode())
        if o.get("sha256") != sh: self.changed += 1
        raw.write_text(txt, encoding="utf8")
        self.new[url] = {"url": url, "status": 200, "sha256": sh, "etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified")}
        return txt, 200

    def write_manifest(self, n_docs):
        # URLs, die diesmal nicht besucht wurden, bleiben im Manifest erhalten
        urls = {**self.old, **self.new}
        self.mf_path.write_text(json.dumps({"source_id": self.sid, "fetched_at": NOW, "n_docs": n_docs, "urls": list(urls.values())}, ensure_ascii=False, indent=1))

def clean(t): return re.sub(r"[ \t ]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()

def sections(node, title):
    """Zerlegt node in (section, text) Blöcke an Überschriften; Blöcke >MAXCH werden an Absätzen geteilt."""
    out, cur, buf = [], title, []
    def flush():
        t = clean("\n".join(buf))
        if t: out.append((cur, t))
    for el in node.descendants:
        if getattr(el, "name", None) in ("h1", "h2", "h3", "h4", "h5", "dt", "summary") or (getattr(el, "name", None) == "a" and "ac_droplink" in " ".join(el.get("class", []) + [el.get("id", "")])):
            h = el.get_text(" ", strip=True)
            if h and h != cur:
                flush(); buf = []; cur = h; continue
        if isinstance(el, str) and not isinstance(el, Comment) and el.parent.name not in ("script", "style"):
            s = el.strip()
            if s and s not in NOISE and not re.match(r"^(Tagtyp|tagtyp|contentline|\.Master|noindex|BREADCRUMB|Ende:|Start:|SIDEBAR|\d\. is)", s): buf.append(s)
    flush()
    res = []
    for sec, t in out:
        # Zeilen -> Absätze
        chunk = ""
        for line in t.split("\n"):
            if len(chunk) + len(line) + 1 > MAXCH and chunk:
                res.append((sec, chunk.strip())); chunk = ""
            while len(line) > MAXCH:
                res.append((sec, line[:MAXCH])); line = line[MAXCH:]
            chunk += line + "\n"
        if chunk.strip(): res.append((sec, chunk.strip()))
    # Überschrift-Duplikat der ersten Zeile entfernen nicht nötig
    return res

def build_docs(sid, url, title, secs, sha, traeger, bundesland, bereich, doc_type, license_note, valid_from=None):
    base = f"{sid}:{sha1(url)}"
    return [{"id": f"{base}#{i}", "source_id": sid, "url": url, "title": title, "section": sec, "text": t, "lang": "de",
             "traeger": traeger, "bundesland": bundesland, "bereich": bereich, "doc_type": doc_type, "valid_from": valid_from,
             "fetched_at": NOW, "sha256": sha, "license_note": license_note} for i, (sec, t) in enumerate(secs)]

BEREICH_RULES = [
    ("A", r"vorsorge|früherkennung|impf|gesundenuntersuchung|screening"),
    ("B", r"gesundheitsförderung|gesundheitshunderter|selbständig gesund|bewegung|ernährung|prävention|gesundheitsziel"),
    ("C", r"reha|kur\b|kuren|behandlung|heilbehelf|hilfsmittel|krankentransport|rezept|selbstbehalt|krankengeld|arzt|spital|therapie|zahn|brille"),
    ("D", r"pflege|betreuung|angehörig"),
    ("E", r"wochengeld|kinderbetreuungsgeld|unterstützung|zuschuss|befreiung|härte|finanz|krankengeld|unfallrente|rente"),
    ("F", r"formular|antrag|kundencenter|kontakt|service|e-card|login|anmeld"),
]
def guess_bereich(text):
    t = text.lower(); r = [b for b, p in BEREICH_RULES if re.search(p, t)]
    return r or ["F"]

PHONE = re.compile(r"(?:Tel(?:efon)?\.?:?\s*)?(\+43[\d\s/\-()]{6,20}\d|0\d{1,4}[\s/\-]\d[\d\s\-]{4,16}\d)")
MAIL = re.compile(r"[\w.\-]+@[\w\-]+\.[\w.\-]+")

SPLIT = re.compile(r'(?<![0-9])(?<!z\.B)(?<!z\.b)(?<!bzw)(?<!d\.h)(?<!ca)(?<!Nr)(?<!u\.a)(?<!inkl)(?<!max)(?<!mind)(?<=[.!?])\s+(?=[A-ZÄÖÜ„"])|\n')

def find_quotes(docs, patterns, maxn=4, maxlen=320):
    """Sucht wörtliche Sätze in den Dokumenten, die eines der Regex-Muster enthalten. -> [{text, quelle_url, zitat}]"""
    res, seen = [], set()
    for d in docs:
        for sent in SPLIT.split(d["text"]):
            s = sent.strip()
            if 25 <= len(s) <= maxlen and s[-1] in ".!?:" and s[0].isupper() and s not in seen and any(re.search(p, s, re.I) for p in patterns):
                seen.add(s); res.append({"text": s, "quelle_url": d["url"], "zitat": s})
                if len(res) >= maxn: return res
    return res

def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

def match_docs(docs, url_or_title_re=None, text_re=None):
    out = []
    for d in docs:
        if url_or_title_re and not (re.search(url_or_title_re, d["title"], re.I) or re.search(url_or_title_re, d["section"], re.I)): continue
        if text_re and not re.search(text_re, d["text"], re.I): continue
        out.append(d)
    return out


# ---------- SV-Portal-CMS (svs.at, bvaeb.at: /cdscontent/?contentid=…&portal=…) ----------
ALLOW = re.compile(r"gesund|vorsorge|pflege|reha|\bkur|rezept|selbstbehalt|transport|heilbehelf|hilfsmittel|wochengeld|formular|antrag|kontakt|kundencenter|"
    r"service|krank|kinder|familie|unfall|behandlung|arzt|ärzt|zahn|brille|mutter|eltern|e-card|befrei|zuzahlung|kostenerstattung|wahlarzt|unterstützung|angehörig|"
    r"hunderter|leistung|impf|früherkennung|psych|sucht|ambulan|einrichtung|beratung|hotline|ausland|mitversicher|erholung|genesung|medikament|therapie|"
    r"pflegegeld|rehabilitation|selbständig gesund|bewegung|ernährung|zusatzleistung|heilmittel|sehhilfe|schwanger|geburt|tod|sterbe|bestattung|"
    r"kontaktstelle|standort|landesstelle|dienststelle|öffnungszeiten|telefon|nachsorge|sozial|härte|zuschuss|ehrenamt|barrierefrei|gebärden|leichte sprache", re.I)
DENY = re.compile(r"karriere|presse|datenschutz|impressum|cookie|newsletter|facebook|youtube|linkedin|login|anmelden|sitemap|beitragsgrundlage|gründung|hofübergabe|gewerbeschein|"
    r"rechtssicherheit|steuer|insolvenz|ausschreibung|vergabe|lieferant|aktuelle werte|beitragsberechnung|hinweisgeber|whistle|jobs?\b|lehrling|stellenangebot", re.I)

def portal_id(url):
    q = parse_qs(urlparse(url).query); return (q.get("contentid") or [None])[0], (q.get("portal") or [None])[0]

def norm_portal_url(base, href):
    u = urldefrag(urljoin(base, href))[0].replace("&amp;", "&")
    p = urlparse(u); cid, portal = portal_id(u)
    if p.path.rstrip("/") == "/cdscontent" and cid and portal:
        return f"{p.scheme}://{p.netloc}/cdscontent/?contentid={cid}&portal={portal}"
    return u

def extract_portal(html):
    s = BeautifulSoup(html, "lxml")
    title = (s.title.string or "").strip() if s.title else ""
    c = s.select_one("#esv-content_with_nav") or s.select_one("#esv-container") or s.body
    for sel in ("#esv-navigation", "script", "style", "noscript", "#navigationov_2436", ".breadcrumb", "nav"):
        for n in c.select(sel): n.decompose()
    return s, title, c

def portal_hash(html):
    return extract_portal(html)[2].get_text(' ', strip=True)

def crawl_portal(f: Fetcher, host, portal, seeds, max_depth=3, max_pages=160, log=print):
    """BFS mit Themenfilter auf Linktext. Liefert pages: {url: dict(title, html, links[(text,url)], depth, status)}"""
    from collections import deque
    pages, q, seen = {}, deque((norm_portal_url(f"https://{host}/", u), 0) for u in seeds), set()
    while q and len(pages) < max_pages:
        url, d = q.popleft()
        if url in seen: continue
        seen.add(url)
        html, st = f.get(url)
        if not html: log(f"  skip {st} {url}"); continue
        s, title, c = extract_portal(html)
        links = []
        for a in BeautifulSoup(html, "lxml").select("a[href]"):
            h = a["href"].strip()
            if h.startswith(("mailto:", "tel:", "javascript:", "#")): continue
            u = norm_portal_url(url, h); links.append((a.get_text(" ", strip=True), u))
        pages[url] = {"title": title, "html": html, "links": links, "depth": d, "status": st}
        log(f"[{len(pages)}] d{d} {title[:50]} {url}")
        if d < max_depth:
            for txt, u in links:
                pu = urlparse(u)
                if pu.netloc.replace("www.", "") != host.replace("www.", ""): continue
                cid, pt = portal_id(u)
                if not cid or pt != portal or "/cdscontent/login" in u or "/cdscontent/load" in u: continue
                if u in seen or not txt or DENY.search(txt) or not ALLOW.search(txt): continue
                q.append((u, d + 1))
    return pages

def collect_formulare(pages, host, sid, traeger, lookup_ids):
    """Formular-Links: /cdscontent/load?contentid=…, formgen, *.pdf"""
    fm = {}
    for url, p in pages.items():
        for txt, u in p["links"]:
            if not re.search(r"/cdscontent/load\?|/formgen/|\.pdf($|\?)|/formulare", u, re.I) or not txt or len(txt) < 4: continue
            if re.search(r"datenschutz|impressum|barrierefrei", txt, re.I): continue
            fid = f"{sid}_{sha1(u)[:10]}"
            e = fm.setdefault(u, {"formular_id": fid, "name": txt.strip(), "traeger": traeger, "url_pdf": u if "/formgen/" not in u else None,
                "local_pdf": None, "fillable": "/formgen/" in u, "felder": [], "leistung_ids": [], "wer_fuellt_aus": "versicherte", "quelle_url": url})
            if len(txt) > len(e["name"]) and len(txt) < 120: e["name"] = txt.strip()
            if "/formgen/" in u: e["online_url"] = u
            for lid, rx in lookup_ids.items():
                if re.search(rx, txt + " " + p["title"], re.I) and lid not in e["leistung_ids"]: e["leistung_ids"].append(lid)
    return list(fm.values())

def collect_stellen(docs, sid, traeger_name, url_default):
    """Heuristik: Telefon/Mail in Kontakt-/Kundencenter-Abschnitten -> Stellen (zur manuellen Prüfung)."""
    out, seen = [], set()
    for d in docs:
        if not re.search(r"kontakt|kundencenter|landesstelle|dienststelle|hotline|servicecenter|beratung", d["title"] + d["section"], re.I): continue
        phones = [re.sub(r"\s+", " ", m.group(1)).strip() for m in PHONE.finditer(d["text"])]
        mails = MAIL.findall(d["text"])
        if not phones and not mails: continue
        key = (d["section"], tuple(phones[:1]), tuple(mails[:1]))
        if key in seen: continue
        seen.add(key)
        out.append({"stelle_id": f"{sid}_{sha1(d['url']+d['section'])[:8]}", "name": f"{traeger_name} – {d['section'] or d['title']}", "typ": "traeger",
            "adresse": None, "plz": None, "bundesland": d["bundesland"][0], "telefon": "; ".join(dict.fromkeys(phones)) or None, "email": "; ".join(dict.fromkeys(mails)) or None,
            "url": d["url"], "oeffnungszeiten": None, "zustaendig_fuer": [], "geo": None, "quelle_url": d["url"]})
    return out


def find_spans(docs, spans):
    """Wörtliche Auszüge: (Regex, Länge) -> Text ab Treffer (bis Satz-/Zeilenende gekürzt). Für Aufzählungen, die der Satzsplitter zerlegt."""
    out = []
    for rx, n in spans:
        for d in docs:
            m = re.search(rx, d["text"])
            if not m: continue
            t = d["text"][m.start(): m.start() + n]
            if len(d["text"]) > m.start() + n:
                cut = max(t.rfind("\n"), t.rfind(". "))
                if cut > 40: t = t[:cut + 1]
            t = t.strip()
            out.append({"text": t, "quelle_url": d["url"], "zitat": t}); break
    return out

def apply_overrides(specs, overrides, new=()):
    by = {}
    for sp in specs: by.setdefault(sp["leistung_id"], sp)
    res = []
    for sp in specs:
        o = overrides.get(sp["leistung_id"]); res.append({**sp, **o} if o else sp)
    return res + list(new)

def make_leistungen(specs, docs, traeger, innerhalb_sv=True, forms=()):
    """specs: Liste von dicts (leistung_id, name, kurz, bereich, title_re, vq (Voraussetzungs-Regexe), kq (Kosten-Regexe), fq (Fristen), zustaendig, trigger, abh, conf).
    Zitate werden wörtlich aus den gecrawlten Dokumenten gezogen; Spezifika ohne Beleg bleiben leer."""
    out = []
    for sp in specs:
        ds = match_docs(docs, sp["title_re"])
        if not ds: continue
        vq = find_spans(ds, sp.get("span", [])) + find_quotes(ds, sp.get("vq", []), 4)
        kq = [q for q in find_quotes(ds, sp.get("kq", []), 6) if re.search(r"\d", q["zitat"])][:2]
        fq = find_quotes(ds, sp.get("fq", []), 2)
        urls = list(dict.fromkeys(d["url"] for d in ds))[:4]
        fid = [x["formular_id"] for x in forms if sp["leistung_id"] in x.get("leistung_ids", [])][:3]
        out.append({"leistung_id": sp["leistung_id"], "name": sp["name"], "kurz_einfach": sp["kurz"], "bereich": sp["bereich"], "traeger": traeger, "innerhalb_sv": innerhalb_sv,
            "zielgruppe": sp.get("zielgruppe"), "voraussetzungen": vq, "zustaendig": sp.get("zustaendig"),
            "antrag": {"formular_id": fid[0] if fid else None, "formular_ids": fid, "wo": sp.get("wo"), "online_url": sp.get("online_url")},
            "unterlagen": [], "fristen": [q["zitat"] for q in fq], "kosten": (kq[0]["zitat"] if kq else None), "kosten_belege": kq,
            "abhaengigkeiten": sp.get("abh", []), "trigger_im_dokument": sp.get("trigger", [sp["name"]]), "bundesland": ["AT"],
            "quellen": [{"url": u, "stand": NOW[:10]} for u in urls], "confidence": sp.get("conf", "mittel"),
            "unterschied_traeger": sp.get("unterschied"), "hinweise": sp.get("hinweise")})
    return out


# ---------- Formulare: PDFs laden, Felder extrahieren ----------
FIELD_VOCAB = [  # (Regex auf Label, quelle_hint, typ)
    (r"titel", "titel", "text"), (r"familienname|nachname|zuname", "nachname", "text"), (r"vorname", "vorname", "text"),
    (r"versicherungsnummer|sv-?nummer|svnr", "svnr", "text"), (r"geburtsdatum|geboren am|geb\.?\s*datum", "geburtsdatum", "text"),
    (r"adresse|anschrift|straße|strasse|wohnsitz", "adresse", "text"), (r"\bplz\b|postleitzahl", "plz", "text"), (r"\bort\b|wohnort", "ort", "text"),
    (r"telefon|tel\.?-?nr|mobil", "telefon", "text"), (r"e-?mail", "email", "text"), (r"\biban\b", "iban", "text"), (r"\bbic\b", "bic", "text"),
    (r"kontoinhaber", "kontoinhaber", "text"), (r"staatsbürgerschaft|staatsangehörigkeit", "staatsbuergerschaft", "text"), (r"familienstand", "familienstand", "text"),
    (r"geschlecht", "geschlecht", "checkbox"), (r"arbeitgeber|dienstgeber", "arbeitgeber", "text"), (r"unterschrift", "unterschrift", "signatur"),
    (r"^datum|datum, unterschrift|ort, datum", "datum", "text"), (r"dienststelle|personalnummer", "dienststelle", "text"), (r"kinder|anzahl der kinder", "kinder", "text"),
    (r"pflegestufe|pflegegeld", "pflegestufe", "text"), (r"\bhausarzt|behandelnde[rn]? arzt", "arzt", "text"), (r"einkommen|nettoeinkommen", "einkommen", "text"),
]

def pdf_fields(path):
    from pypdf import PdfReader
    import io
    try: r = PdfReader(str(path))
    except Exception: return None, [], False, 0
    meta = (r.metadata.title if r.metadata and r.metadata.title else None)
    felder, acro = [], False
    try:
        fl = r.get_fields() or {}
        for k, v in fl.items():
            ft = str(v.get("/FT", ""))
            felder.append({"name": k, "label": str(v.get("/TU") or k), "typ": "checkbox" if ft == "/Btn" else "text", "quelle_hint": hint_for(str(v.get("/TU") or k))})
        acro = bool(fl)
    except Exception: pass
    npages = len(r.pages)
    if not felder:  # flaches PDF: Labels aus dem Text (Vokabular)
        seen = set()
        try:
            txt = "\n".join((p.extract_text() or "") for p in r.pages[:3])
        except Exception: txt = ""
        for line in txt.split("\n"):
            ln = line.strip()
            if not ln or len(ln) > 70: continue
            for rx, h, typ in FIELD_VOCAB:
                if re.match(r"^[\W\d]*(" + rx + r")", ln, re.I) and (h, ln) not in seen:
                    seen.add((h, ln)); felder.append({"name": h, "label": ln, "typ": typ, "quelle_hint": h}); break
    return meta, felder, acro, npages

def hint_for(label):
    for rx, h, _ in FIELD_VOCAB:
        if re.search(rx, label, re.I): return h
    return None

def enrich_forms(f: Fetcher, forms, log=print, limit=None):
    """Lädt PDF-Formulare (nur /cdscontent/load-Links dieser Träger), extrahiert Felder. Idempotent: vorhandene Dateien werden nicht neu geladen (Version steckt in der URL)."""
    pdfdir = f.base / "raw" / "pdf"; pdfdir.mkdir(parents=True, exist_ok=True)
    n = 0
    for x in forms:
        u = x.get("url_pdf")
        if not u or "/cdscontent/load" not in u or "ambulatorien" in u: continue
        path = pdfdir / (sha1(u) + ".pdf"); meta = pdfdir / (sha1(u) + ".meta.json")
        if not path.exists() and OFFLINE: continue
        if not path.exists():
            wait = DELAY - (time.time() - f.last)
            if wait > 0: time.sleep(wait)
            try: r = f.s.get(u, timeout=60); f.last = time.time()
            except Exception: continue
            if r.status_code != 200 or not r.content[:5] == b"%PDF-": continue
            path.write_bytes(r.content)
            fn = None
            m = re.search(r'filename="?([^";]+)', r.headers.get("content-disposition", ""))
            if m: fn = m.group(1)
            meta.write_text(json.dumps({"filename": fn, "etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified"), "sha256": sha256(r.content)}))
            n += 1
            if limit and n >= limit: break
        mj = json.loads(meta.read_text()) if meta.exists() else {}
        try: title, felder, acro, npages = pdf_fields(path)
        except Exception: title, felder, acro, npages = None, [], False, 0
        x["local_pdf"] = str(path.relative_to(f.base.parent.parent))
        x["felder"] = felder; x["fillable"] = acro; x["pdf_seiten"] = npages; x["pdf_sha256"] = mj.get("sha256")
        x["felder_quelle"] = "acroform" if acro else ("text-heuristik" if felder else "keine")
        fn = mj.get("filename")
        if fn:
            nm = re.sub(r"\.pdf$", "", fn, flags=re.I); nm = re.sub(r"^(VS|SVS|BVAEB)?-?\d+[_-]", "", nm).replace("_", " ").strip()
            x["dateiname"] = fn
            if re.match(r"^(PDF|\.\.\.|Download|Mehr)", x["name"]) or len(x["name"]) < 6: x["name"] = (title or nm)
        elif title and re.match(r"^PDF", x["name"]): x["name"] = title
        x["wer_fuellt_aus"] = "arzt" if re.search(r"ärztlich|arzt|befund|gutachten", x["name"], re.I) else x["wer_fuellt_aus"]
        if n and n % 25 == 0: log(f"  pdfs geladen: {n}")
    return forms


def geocode_stellen(f: Fetcher, stellen):
    """Koordinaten für Stellen mit Adresse via Nominatim (OSM), gecacht in raw/geo.json, ≤1 Req/s. Nur öffentliche Dienststellen-Adressen."""
    cp = f.base / "raw" / "geo.json"
    cache = json.loads(cp.read_text()) if cp.exists() else {}
    for s in stellen:
        a = s.get("adresse")
        if not a or s.get("geo"): continue
        if a not in cache:
            wait = 1.2 - (time.time() - f.last)
            if wait > 0: time.sleep(wait)
            try:
                r = f.s.get("https://nominatim.openstreetmap.org/search", params={"q": a + ", Österreich", "format": "json", "limit": 1}, timeout=30); f.last = time.time()
                j = r.json() if r.status_code == 200 else []
                cache[a] = [float(j[0]["lat"]), float(j[0]["lon"])] if j else None
            except Exception: continue
        s["geo"] = cache.get(a)
    cp.write_text(json.dumps(cache, ensure_ascii=False))
    return stellen
