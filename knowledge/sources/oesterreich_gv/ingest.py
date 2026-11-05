# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4", "lxml"]
# ///
"""Ingestion oesterreich.gv.at (HELP.gv.at) -> Schema A/B/C/D + manifest.

Aufruf:  uv run knowledge/sources/oesterreich_gv/ingest.py [--refetch] [--no-fetch] [--max N]
- Discovery ueber sitemap.xml (kein Open-Data-/API-Zugang, siehe SOURCE.md), gefiltert auf Themen-Praefixe.
- Hoeflich: robots.txt, <=1 Request/s, generischer User-Agent, konditionale GETs (ETag/Last-Modified).
- Idempotent/inkrementell: manifest.json ist der Zustand; unveraenderte Seiten (304 / gleicher sha256) werden nicht neu geholt/geparst.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys, time, urllib.request, urllib.error, urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote, unquote

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "out"
BASE = "https://www.oesterreich.gv.at"
UA = "SV-Lotse-Hackathon/0.1"
SOURCE_ID = "oesterreich_gv"
LICENSE = ("oesterreich.gv.at (BKA/Digital Austria): Inhalte oeffentlich; laut Impressum Nachnutzung unter CC BY 4.0 "
           "(bitte im Impressum verifizieren), Quellenangabe 'oesterreich.gv.at' mitfuehren.")

# ---------- Discovery ----------
INCLUDE = [
    r"/de/themen/pflege/", r"/de/themen/pflege$",
    r"/de/themen/menschen_mit_behinderungen/",
    r"/de/themen/gesundheit(/|$)",
    r"/de/themen/hilfe_und_finanzielle_unterstuetzung_erhalten/",
    r"/de/themen/gesetze_und_recht/erwachsenenvertretung_und_vorsorgevollmacht",
    r"/de/themen/arbeit_beruf_und_pension/pension",
    r"/de/themen/arbeit_beruf_und_pension/Karenz-und-Mutterschutz",
    r"/de/themen/arbeit_beruf_und_pension/berufsleben/krankenstand",
    r"/de/themen/arbeit_beruf_und_pension/aeltere_arbeitnehmer",
    r"/de/themen/arbeit_beruf_und_pension/online_services",
    r"/de/themen/familie_und_partnerschaft/familienbeihilfe",
    r"/de/themen/familie_und_partnerschaft/finanzielle-unterstuetzungen",
    r"/de/themen/familie_und_partnerschaft/geburt-eines-kindes",
    r"/de/themen/familie_und_partnerschaft/online_services",
    r"/de/lebenslagen/Ich-k", r"/de/lebenslagen/Ich-ben", r"/de/lebenslagen/Ich-erwarte",
    r"/de/lebenslagen/Ich-bin-f", r"/de/lebenslagen/Ich-gehe", r"/de/lebenslagen/Ich-habe",
    r"/de/behoerden/pensionsversicherungen",
]
EXTRA_URLS = [
    f"{BASE}/de/themen/gesundheit", f"{BASE}/de/themen/arbeit_beruf_und_pension", f"{BASE}/de/themen/pflege",
    f"{BASE}/de/lebenslagen", f"{BASE}/de/themen/menschen_mit_behinderungen",
    f"{BASE}/de/themen/gesundheit/patientenrechte",
    f"{BASE}/de/themen/gesundheit/selbstversicherung_in_der_krankenversicherung",
    f"{BASE}/de/themen/arbeit_beruf_und_pension/berufsleben/krankenstand/Seite.2170007",
]
EXCLUDE = [r"/organtransplantation", r"/rauchverbote", r"/schwangerschaftsabbruch", r"/en/", r"/Gesetzliche-Neuerungen"]
MAX_FORMS = 150
MAX_ORGS = 60

# Bereich-Heuristik (Challenge: A Vorsorge, B Gesundheitsfoerderung, C Behandlung/Reha, D Pflege, E Sozial/Finanziell, F Administration)
def bereich_for(url: str, text: str) -> list[str]:
    u = url.lower(); b = []
    if "/pflege" in u or "pflege" in text[:300].lower(): b.append("D")
    if any(k in u for k in ("hilfe_und_finanzielle", "familie", "finanzielle", "pension", "behinderung", "karenz")): b.append("E")
    if any(k in u for k in ("gesundheit", "rehabilitation", "krankenstand")): b.append("C")
    if any(k in u for k in ("erwachsenenvertretung", "online_services", "lebenslagen", "formsearch", "orgsearch")): b.append("F")
    return sorted(set(b)) or ["F"]


# ---------- HTTP ----------
class Fetcher:
    def __init__(self):
        self.rp = urllib.robotparser.RobotFileParser(BASE + "/robots.txt")
        try:
            req = urllib.request.Request(BASE + "/robots.txt", headers={"User-Agent": UA})
            self.rp.parse(urllib.request.urlopen(req, timeout=30).read().decode().splitlines())
        except Exception as e:  # robots nicht lesbar -> konservativ weitermachen
            print("robots.txt nicht lesbar:", e, file=sys.stderr); self.rp.parse([])
        self.last = 0.0

    def get(self, url, etag=None, lm=None):
        if not self.rp.can_fetch(UA, url):
            return 403, None, {}
        wait = 1.05 - (time.time() - self.last)
        if wait > 0: time.sleep(wait)
        h = {"User-Agent": UA, "Accept-Language": "de"}
        if etag: h["If-None-Match"] = etag
        if lm: h["If-Modified-Since"] = lm
        self.last = time.time()
        try:
            r = urllib.request.urlopen(urllib.request.Request(quote(url, safe=":/?&=%#+@~.,;-_()'"), headers=h), timeout=40)
            return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, None, dict(e.headers or {})
        except Exception as e:
            print("ERR", url, e, file=sys.stderr); return 0, None, {}


def sha1(s): return hashlib.sha1(s.encode()).hexdigest()
def sha256(b): return hashlib.sha256(b).hexdigest()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def discover(f: Fetcher, manifest) -> list[str]:
    st, body, _ = f.get(BASE + "/sitemap.xml")
    urls = []
    if st == 200:
        (RAW / "sitemap.xml").write_bytes(body)
        urls = re.findall(r"<loc>([^<]+)</loc>", body.decode())
    elif (RAW / "sitemap.xml").exists():
        urls = re.findall(r"<loc>([^<]+)</loc>", (RAW / "sitemap.xml").read_text())
    sel = [u for u in urls if any(re.search(p, u) for p in INCLUDE) and not any(re.search(p, u) for p in EXCLUDE)]
    forms = [u for u in urls if "/formsearch/form/" in u]
    return list(dict.fromkeys(EXTRA_URLS + sel)), forms


def fetch_one(f, url, man, refetch=False):
    key = sha1(url)
    ent = man["urls"].get(url, {})
    path = RAW / f"{key}.html"
    if path.exists() and ent and not refetch:
        st, body, hd = f.get(url, ent.get("etag"), ent.get("last_modified"))
        if st == 304:
            ent["checked_at"] = now(); man["urls"][url] = ent; return path.read_bytes(), False
    else:
        st, body, hd = f.get(url)
    if st != 200 or body is None:
        man["urls"][url] = {**ent, "url": url, "status": st, "checked_at": now()}
        return (path.read_bytes() if path.exists() else None), False
    sh = sha256(body)
    changed = sh != ent.get("sha256")
    path.write_bytes(body)
    man["urls"][url] = {"url": url, "sha256": sh, "etag": hd.get("ETag"), "last_modified": hd.get("Last-Modified"),
                        "status": 200, "fetched_at": now() if changed else ent.get("fetched_at", now()), "checked_at": now()}
    return body, changed


# ---------- Parsing ----------
def clean(t): return re.sub(r"\s+", " ", t).strip()

def parse_page(html: bytes, url: str):
    s = BeautifulSoup(html, "lxml")
    main = s.find("main") or s.body
    title = clean(s.title.get_text()) if s.title else ""
    for t in main(["script", "style", "svg", "template", "nav", "noscript", "button", "form"]):
        t.decompose()
    h1 = main.find("h1")
    if h1: title = clean(h1.get_text())
    breadcrumb = []
    links = []
    for a in main.find_all("a", href=True):
        href = urljoin(url, a["href"]); txt = clean(a.get_text())
        links.append((txt, href))
    sections, cur, buf = [], "Einleitung", []
    skip_h = {"Inhalte auf dieser Seite"}
    for e in main.find_all(["h2", "h3", "h4", "p", "li", "tr"]):
        if e.name in ("h2", "h3", "h4"):
            if buf: sections.append((cur, buf))
            cur, buf = clean(e.get_text()), []
            continue
        if e.name == "li" and e.find(["p", "li"]): continue
        if e.name == "p" and e.find_parent("li"): continue
        t = clean(e.get_text(" "))
        t = re.sub(r"\s+([,.;:!?)])", r"\1", t); t = re.sub(r"\(\s+", "(", t)
        if t and cur not in skip_h:
            buf.append(("• " if e.name == "li" else "") + t)
    if buf: sections.append((cur, buf))
    # Stand/Aktualisierung
    txt_all = clean(main.get_text(" "))
    m = re.search(r"(?:Letzte Aktualisierung|Stand|Zuletzt aktualisiert)[: ]+(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", txt_all)
    stand = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None
    return title, sections, links, stand


def chunk(title, section, lines, limit=1900):
    out, cur = [], ""
    for ln in lines:
        while len(ln) > limit:
            cut = ln.rfind(" ", 0, limit); cut = cut if cut > 0 else limit
            if cur: out.append(cur); cur = ""
            out.append(ln[:cut]); ln = ln[cut:].strip()
        if len(cur) + len(ln) + 1 > limit:
            out.append(cur); cur = ln
        else:
            cur = (cur + "\n" + ln).strip()
    if cur: out.append(cur)
    return out


TRAEGER_PAT = [("PVA", r"\bPVA\b|Pensionsversicherungsanstalt"), ("ÖGK", r"ÖGK|Österreichische Gesundheitskasse"),
               ("SVS", r"\bSVS\b|Sozialversicherung der Selbständigen"), ("BVAEB", r"BVAEB"),
               ("SMS", r"Sozialministeriumservice"), ("AUVA", r"AUVA"), ("BMASGPK", r"BMASGPK"), ("AMS", r"\bAMS\b|Arbeitsmarktservice")]

def traeger_for(text):
    return [n for n, p in TRAEGER_PAT if re.search(p, text)]

def doc_type_for(url, title):
    if "/formsearch/" in url: return "formular"
    if "Rechtsgrundlage" in title: return "recht"
    return "leistungsinfo"

def bundesland_for(text):
    return ["AT"]


# ---------- Leistungen (kuratierte Zuordnung -> Felder werden aus den Seiten extrahiert) ----------
# match = Regex auf Seitentitel (h1) ODER URL; erste Treffer pro leistung_id bilden die Quellen
LEISTUNGEN = json.loads((HERE / "leistungen_config.json").read_text()) if (HERE / "leistungen_config.json").exists() else []


def sec_find(secs, pat):
    for name, lines in secs:
        if re.search(pat, name, re.I): return name, lines
    return None, []


def build_leistung(cfg, pages):
    """pages: list of dict(url,title,sections,stand,links) die auf cfg matchen"""
    quellen = [{"url": p["url"], "stand": p["stand"]} for p in pages]
    voraus, fristen, unterlagen, kosten = [], [], [], None
    antrag_wo = None; online = None; formular_ids = []
    for p in sorted(pages, key=lambda x: 0 if re.search(r"Voraussetzung", x["title"]) else 1):
        if re.search(r"Voraussetzung", p["title"]) and not voraus:
            for name, lines in p["sections"]:
                for ln in lines[:10]:
                    voraus.append({"text": ln.lstrip("• ")[:300], "quelle_url": p["url"], "zitat": ln.lstrip("• ")[:400]})
        for name, lines in p["sections"]:
            if re.search(r"Voraussetzung|Anspruch|Wer (hat|bekommt|kann)", name, re.I) and not re.search(r"Klage|Verfahren vor", p["title"]):
                for ln in lines[:12]:
                    voraus.append({"text": ln.lstrip("• ")[:300], "quelle_url": p["url"], "zitat": ln.lstrip("• ")[:400]})
            elif re.search(r"Frist|Zeitpunkt|Wann", name, re.I):
                fristen += [l.lstrip("• ")[:300] for l in lines[:4]]
            elif re.search(r"Unterlagen|Dokumente|Nachweis|Beizulegen|Erforderliche", name, re.I):
                unterlagen += [l.lstrip("• ")[:200] for l in lines[:8]]
            elif re.search(r"Kosten|Gebühr|Höhe|Betrag", name, re.I) and not kosten:
                kosten = " ".join(lines)[:500]
            elif re.search(r"Antrag|Verfahrensablauf|Wo.*beantragen|Zuständige", name, re.I) and not antrag_wo and not re.search(r"Klage|Verfahren vor|Entscheidung|Rechtsgrund", p["title"] + " " + name):
                antrag_wo = " ".join(lines)[:500]
        for txt, href in p["links"]:
            if "secure.oesterreich.gv.at" in href or "/onlineformulare" in href: online = online or href
            m = re.search(r"/(?:formsearch|linkresolution)/form/(\d+)", href)
            if m: formular_ids.append(f"oegv_form_{m.group(1)}")
    intro = ""
    for p in pages:
        for name, lines in p["sections"]:
            if lines: intro = lines[0]; break
        if intro: break
    zust = antrag_wo or "Siehe Quelle (Abschnitt 'Zuständige Stelle' bzw. Verfahrensablauf auf der Seite)."
    alltext = " ".join(" ".join(l) for p in pages for _, l in p["sections"])
    return {
        "leistung_id": cfg["id"], "name": cfg["name"], "kurz_einfach": cfg.get("kurz") or intro[:300],
        "bereich": cfg["bereich"], "traeger": cfg.get("traeger") or traeger_for(alltext),
        "innerhalb_sv": cfg.get("innerhalb_sv", False), "zielgruppe": cfg.get("zielgruppe", ""),
        "voraussetzungen": voraus[:15], "zustaendig": cfg.get("zustaendig") or zust,
        "antrag": {"formular_id": (formular_ids[0] if formular_ids else None), "wo": antrag_wo, "online_url": online},
        "unterlagen": unterlagen[:10], "fristen": fristen[:6], "kosten": kosten,
        "abhaengigkeiten": cfg.get("abhaengigkeiten", []), "trigger_im_dokument": cfg.get("trigger", [cfg["name"]]),
        "bundesland": cfg.get("bundesland", ["AT"]), "quellen": quellen,
        "confidence": "mittel" if pages else "niedrig",
        "hinweis": "Automatisch aus oesterreich.gv.at extrahiert; Mensch-Review noetig (Beträge/Stufen im Original pruefen).",
    }


# ---------- Formulare / Stellen ----------
def _fill(t):
    t = t.lower()
    return "ausfüll" in t and "nicht" not in t


def parse_form(html, url):
    s = BeautifulSoup(html, "lxml"); main = s.find("main") or s.body
    for t in main(["script", "style", "svg", "template"]): t.decompose()
    h1 = main.find("h1"); name = clean(h1.get_text()) if h1 else (clean(s.title.get_text()) if s.title else "")
    pdfs = []
    for a in main.find_all("a", href=True):
        h = urljoin(url, a["href"])
        if re.search(r"\.(pdf|docx?|xlsx?)(\?|$)", h, re.I) or "secure.oesterreich.gv.at" in h or "/formsearch/" in h and h != url:
            pdfs.append((clean(a.get_text()), h))
    txt = clean(main.get_text(" "))
    raw = html.decode("utf-8", "replace").replace('\\"', '"').replace("\\u0026", "&")
    fmts = []
    for m in re.finditer(r'"url":"(https?://[^"]+)","format":\{"title":"([^"]+)","shortkey":"(\w+)"\}', raw):
        fmts.append((m.group(2), m.group(1)))
    return name, pdfs, txt, fmts


LISTS = [
    (BASE + "/de/behoerden/pensionsversicherungen", ["pflegegeld", "rehabilitationsgeld", "invaliditaetspension"]),
    (BASE + "/de/behoerden/unfallversicherungen", ["pflegegeld"]),
    (BASE + "/orgsearch/orgtyp/8", []),
]


def parse_orglist(html, url, zf):
    s = BeautifulSoup(html, "lxml"); main = s.find("main") or s.body
    for t in main(["script", "style", "svg", "template"]): t.decompose()
    out = []
    for h in main.find_all("h2"):
        box = h.find_parent("div")
        for _ in range(4):
            if box.parent and len(box.parent.find_all("h2")) == 1: box = box.parent
        lines = [clean(x) for x in box.get_text("\n").split("\n") if clean(x)]
        name = clean(h.get_text())
        if len(lines) < 2: continue
        def after(label):
            for i, l in enumerate(lines):
                if l.rstrip(":").lower() == label and i + 1 < len(lines): return lines[i + 1]
        tel, mail, web = after("telefon"), after("e-mail"), after("homepage")
        addr = [l for l in lines[1:4] if not l.endswith(":") and "Karte" not in l and "Routen" not in l]
        plz = None
        for l in addr:
            m = re.search(r"\b(\d{4})\b", l)
            if m: plz = m.group(1); break
        if not (tel or mail or web or addr): continue
        sid = "oegv_" + sha1(name + (plz or ""))[:10]
        out.append({"stelle_id": sid, "name": name, "typ": "traeger" if "versicherung" in name.lower() or "kasse" in name.lower() else "einrichtung",
                    "adresse": ", ".join(addr) or None, "plz": plz, "bundesland": None, "telefon": tel, "email": mail, "url": web or url,
                    "oeffnungszeiten": None, "zustaendig_fuer": zf, "geo": None, "quelle_url": url})
    return out


def parse_org(html, url):
    s = BeautifulSoup(html, "lxml"); main = s.find("main") or s.body
    for t in main(["script", "style", "svg", "template"]): t.decompose()
    h1 = main.find("h1"); name = clean(h1.get_text()) if h1 else ""
    txt = main.get_text("\n")
    lines = [clean(l) for l in txt.split("\n") if clean(l)]
    tel = next((m.group(0) for m in (re.search(r"(\+43|0)[\d /\-]{6,}\d", l) for l in lines) if m), None)
    mail = next((m.group(0) for m in (re.search(r"[\w.\-]+@[\w.\-]+\.\w+", l) for l in lines) if m), None)
    plz = next((m.group(1) for m in (re.search(r"\b(\d{4})\s+[A-ZÄÖÜ][\wäöüß\- ]+", l) for l in lines) if m), None)
    web = next((urljoin(url, a["href"]) for a in main.find_all("a", href=True) if a["href"].startswith("http") and "oesterreich.gv.at" not in a["href"]), None)
    return name, tel, mail, plz, web, "\n".join(lines)[:1500]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true"); ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--max", type=int, default=0); ap.add_argument("--since", help="ignoriert; Inkrementalitaet laeuft ueber manifest.json")
    a = ap.parse_args()
    RAW.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
    mp = OUT / "manifest.json"
    man = json.loads(mp.read_text()) if mp.exists() else {"source_id": SOURCE_ID, "urls": {}}
    if isinstance(man.get("urls"), list): man["urls"] = {e["url"]: e for e in man["urls"]}
    f = Fetcher()
    pages_urls, form_sitemap = discover(f, man)
    if a.max: pages_urls = pages_urls[: a.max]
    print(f"{len(pages_urls)} Themenseiten, {len(form_sitemap)} Formulare in Sitemap", file=sys.stderr)

    parsed = {}
    def load(url, refetch=False):
        if a.no_fetch:
            p = RAW / f"{sha1(url)}.html"; return (p.read_bytes() if p.exists() else None)
        body, _ = fetch_one(f, url, man, refetch or a.refetch); return body

    for i, u in enumerate(pages_urls):
        body = load(u)
        if body: parsed[u] = parse_page(body, u)
        if i % 25 == 0:
            print(i, u, file=sys.stderr); mp.write_text(json.dumps({**man, "urls": list(man["urls"].values())}, ensure_ascii=False, indent=1))

    # Formulare: nur die, die von Themenseiten verlinkt sind (+ Stichwort-Treffer ueber Titel nicht moeglich ohne Fetch)
    form_ids = {}
    for u, (_, _, links, _) in parsed.items():
        for txt, h in links:
            m = re.search(r"/(?:formsearch|linkresolution)/form/(\d+)", h)
            if m: form_ids[m.group(1)] = f"{BASE}/de/formsearch/form/{m.group(1)}"
    forms_out = []
    for fid, furl in list(form_ids.items())[:MAX_FORMS]:
        body = load(furl)
        if not body: continue
        name, pdfs, txt, fmts = parse_form(body, furl)
        fmts = list(dict.fromkeys(fmts))
        pdfl = [(t, u) for t, u in fmts if "pdf" in t.lower()]
        pdf = next(((u) for t, u in pdfl if _fill(t)), None) or (pdfl[0][1] if pdfl else None)
        onl = next((u for t, u in fmts if "online" in t.lower() or t.startswith("HTML")), None)
        forms_out.append({"formular_id": f"oegv_form_{fid}", "name": name, "traeger": ", ".join(traeger_for(txt + " " + " ".join(u for _, u in fmts))) or None,
                          "url_pdf": pdf, "online_url": onl, "alle_formate": [{"format": t, "url": u} for t, u in fmts][:8],
                          "local_pdf": None, "fillable": any(_fill(t) for t, _ in pdfl) if pdfl else None, "felder": [],
                          "leistung_ids": [], "wer_fuellt_aus": "versicherte", "quelle_url": furl})

    # Stellen: Behoerden-Listen (Schema C), Ministerien (orgtyp/8), "Zustaendige Stelle"-Abschnitte
    stellen_out = []
    for lu, zf in LISTS:
        body = load(lu)
        if not body: continue
        stellen_out += parse_orglist(body, lu, zf)
    stellen_out = list({x["stelle_id"]: x for x in stellen_out}.values())

    # Dokumente
    fetched_at = now(); docs = []
    for u, (title, secs, links, stand) in parsed.items():
        base = f"{SOURCE_ID}:{sha1(u)}"; n = 0
        allt = " ".join(" ".join(l) for _, l in secs)
        for sname, lines in secs:
            for c in chunk(title, sname, lines):
                n += 1
                docs.append({"id": f"{base}#{n}", "source_id": SOURCE_ID, "url": u, "title": title, "section": sname, "text": c,
                             "lang": "de", "traeger": traeger_for(c) or traeger_for(allt), "bundesland": bundesland_for(c),
                             "bereich": bereich_for(u, allt), "doc_type": doc_type_for(u, sname), "valid_from": stand,
                             "fetched_at": man["urls"].get(u, {}).get("fetched_at", fetched_at),
                             "sha256": man["urls"].get(u, {}).get("sha256"), "license_note": LICENSE})

    # Leistungen
    lei = []
    for cfg in LEISTUNGEN:
        pages = []
        for u, (title, secs, links, stand) in parsed.items():
            hit = any(re.search(p, title, re.I) for p in cfg.get("title_re", [])) or any(re.search(p, u) for p in cfg.get("url_re", []))
            if hit: pages.append({"url": u, "title": title, "sections": secs, "links": links, "stand": stand})
        pages = pages[: cfg.get("max_pages", 6)]
        if not pages: print("keine Seite fuer", cfg["id"], file=sys.stderr); continue
        lei.append(build_leistung(cfg, pages))
        # Formular->Leistung verknuepfen
        fids = {l.get("antrag", {}).get("formular_id") for l in lei[-1:]}
        for p in pages:
            for _, h in p["links"]:
                m = re.search(r"/(?:formsearch|linkresolution)/form/(\d+)", h)
                if m:
                    for fo in forms_out:
                        if fo["formular_id"] == f"oegv_form_{m.group(1)}" and cfg["id"] not in fo["leistung_ids"]:
                            fo["leistung_ids"].append(cfg["id"])

    fo_by = {fo["formular_id"]: fo for fo in forms_out}
    for l in lei:
        fid = l["antrag"].get("formular_id")
        if fid in fo_by:
            l["antrag"]["online_url"] = l["antrag"]["online_url"] or fo_by[fid].get("online_url")
            l["antrag"]["formular_pdf"] = fo_by[fid].get("url_pdf")
        l["formular_ids"] = [fo["formular_id"] for fo in forms_out if l["leistung_id"] in fo["leistung_ids"]]

    def dump(name, rows):
        with open(OUT / name, "w", encoding="utf-8") as fh:
            for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    dump("documents.jsonl", docs); dump("leistungen.jsonl", lei); dump("stellen.jsonl", stellen_out); dump("formulare.jsonl", forms_out)
    man.update({"source_id": SOURCE_ID, "fetched_at": now(), "n_docs": len(docs), "n_pages": len(parsed),
                "n_leistungen": len(lei), "n_stellen": len(stellen_out), "n_formulare": len(forms_out)})
    man["urls"] = {k: v for k, v in man["urls"].items()}
    mp.write_text(json.dumps({**man, "urls": list(man["urls"].values())}, ensure_ascii=False, indent=1))
    print(f"docs={len(docs)} leistungen={len(lei)} stellen={len(stellen_out)} formulare={len(forms_out)}", file=sys.stderr)


def load_fixed_stellen():
    p = HERE / "stellen_fixed.json"
    return json.loads(p.read_text()) if p.exists() else []


if __name__ == "__main__":
    main()
