"""Stufe 2: raw/*.html -> documents.jsonl (A), leistungen.jsonl (B), stellen.jsonl (C)."""
import json, re, copy
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString
import fetch
from fetch import GV, PF, RAW, sha1

SRC = "gesundheit_gv"
LIC_GV = ("© BMASGPK / Gesundheit Österreich GmbH, gesundheit.gv.at – alle Rechte vorbehalten (Impressum „Geistiges Eigentum“): "
          "Entnahme/Wiedergabe von Inhalten bedarf der Genehmigung des BMASGPK, ausgenommen Bezug über Content-Syndizierung. "
          "Nur mit Quellenangabe zitieren; vor produktiver Nutzung Genehmigung einholen.")
LIC_PF = ("© Gesundheit Österreich GmbH, pflege.gv.at – alle Rechte vorbehalten (Impressum): teilweise oder vollständige Verwendung von Inhalten bedarf der vorhergehenden Genehmigung der GÖG. "
          "Nur mit Quellenangabe zitieren; vor produktiver Nutzung Genehmigung einholen.")
MONTHS = {m: i + 1 for i, m in enumerate("Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split())}
MAXLEN = 1900

# ---------------------------------------------------------------- Parsing
BLOCK = {"p", "li", "dd", "dt", "caption", "blockquote"}
SKIP_CLS = re.compile(r"\b(toc|acceptance|figure|breadcrumb|sidebar|sidebar-first|share|visually-hidden|sr-only|modal|topic-links|tag-link|skip|d-none d-xl-block mt-5)\b")


def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True).replace("\xa0", " ")).strip().replace(" ,", ",").replace(" .", ".").replace(" ;", ";").replace(" :", ":").replace("( ", "(").replace(" )", ")")


def walk(el, out, st):
    for ch in el.children:
        if isinstance(ch, NavigableString): continue
        n = ch.name
        if n in ("script", "style", "svg", "nav", "button", "figure", "form", "noscript", "iframe", "footer", "header", "aside"): continue
        cls = " ".join(ch.get("class", []))
        if cls and re.search(r"(^|\s)(toc|acceptance|breadcrumb|sidebar|sidebar-first|modal|visually-hidden|topic-links|tag-link)(\s|$)", cls): continue
        if n == "h1": continue
        if n in ("h2", "h3", "h4", "h5"):
            t = txt(ch)
            # Accordion-Überschriften enthalten Button + Span doppelt
            span = ch.find("span", class_=re.compile("d-xl-block"))
            if span: t = txt(span)
            if not t or t.lower() in ("inhaltsverzeichnis", "top inhalte"): continue
            out.append(("h" + n[1], t)); continue
        if n == "tr":
            cells = [txt(c) for c in ch.find_all(["th", "td"])]
            if any(cells): out.append(("p", " | ".join(c for c in cells if c)))
            continue
        if n in BLOCK:
            c = copy.copy(ch)
            nested = c.find_all(["ul", "ol"])
            for x in nested: x.extract()
            t = txt(c)
            if t: out.append(("li" if n == "li" else "p", t))
            for x in ch.find_all(["ul", "ol"], recursive=False): walk(x, out, st)
            for x in ch.find_all(["ul", "ol"]) if False else []: pass
            continue
        walk(ch, out, st)


def parse(path, url):
    soup = BeautifulSoup(path.read_text(encoding="utf8", errors="replace"), "lxml")
    is_pf = url.startswith(fetch.PF)
    full = soup.get_text(" ")
    title = None; teaser = ""; stand = None; root = None
    if is_pf:
        t = soup.title.get_text() if soup.title else ""
        title = re.sub(r"\s*\|\s*pflege\.gv\.at.*$", "", t).strip()
        nc = soup.select_one(".node-container")
        root = nc or soup.select_one("#main")
        md = soup.find("meta", attrs={"name": "description"})
        teaser = md["content"].strip() if md and md.get("content") else ""
        h1 = soup.select_one(".node-container h1") 
    else:
        root = soup.select_one("main#content") or soup.find("main")
        h1 = root.find("h1") if root else None
        title = txt(h1) if h1 else (soup.title.get_text().split("|")[0].strip() if soup.title else url)
        tz = root.select_one(".teaser-abstract") if root else None
        teaser = txt(tz) if tz else ""
        m = re.search(r"Letzte Aktualisierung:\s*(\d{1,2})\.\s*([A-Za-zäöü]+)\s*(\d{4})", full)
        if m and m.group(2) in MONTHS:
            stand = f"{int(m.group(3)):04d}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    blocks = []
    if root is not None:
        # Quellenverzeichnis-Akkordeon entfernen
        for h in root.find_all(["h2", "h3"]):
            if re.match(r"\s*(Quellenverzeichnis|Quellen)\s*$", txt(h)):
                box = h.find_parent(class_=re.compile("card-collapse")) or h
                box.decompose()
        walk(root, blocks, {})
    links = []
    if root is not None:
        for a in root.find_all("a", href=True):
            t = txt(a)
            if t: links.append((t, a["href"]))
    return {"title": title, "teaser": teaser, "stand": stand, "blocks": blocks, "links": links, "lang": "de"}


def sections(blocks, title):
    """-> [(heading, [paragraph strings])]; h3/h4 werden als eigene Zeile eingerückt."""
    secs = []; cur = ["Einleitung", []]
    for k, t in blocks:
        if k == "h2":
            if cur[1]: secs.append(tuple(cur))
            cur = [t, []]
        elif k in ("h3", "h4", "h5"):
            cur[1].append(t + ":")
        elif k == "li":
            cur[1].append("• " + t)
        else:
            cur[1].append(t)
    if cur[1]: secs.append(tuple(cur))
    return secs


def chunk(paras):
    out = []; buf = ""
    for p in paras:
        parts = [p]
        if len(p) > MAXLEN:
            parts = re.split(r"(?<=[.!?])\s+", p); 
        for x in parts:
            if buf and len(buf) + len(x) + 1 > MAXLEN:
                out.append(buf); buf = ""
            buf = (buf + "\n" + x) if buf else x
    if buf: out.append(buf)
    return out


# ---------------------------------------------------------------- Klassifikation
def classify(url):
    p = url.replace(GV, "").replace(PF, "")
    pf = url.startswith(PF)
    b = []
    if pf:
        b.append("D")
        if re.search(r"pflegegeld|foerder|gebuehr|finanz|behindertenpass|karenz|bonus|versicherung|erhoehte|therapiekosten|kostenersatz|fahrt|rundfunk", p): b.append("E")
        if re.search(r"rehab|aktiv|fit|sturz|schlaf|gesundheit|bewegung|ernaehrung|psychosozial|gesundheitsaktionen", p): b.append("B")
        if re.search(r"vorsorge|patientenverfuegung|erwachsenenvertretung", p): b.append("F")
        if re.search(r"beratung|selbsthilfe|gesetze|antrag|community", p): b.append("F")
        if re.search(r"rehabilitation|reha-", p): b.append("C")
    else:
        if re.search(r"vorsorge|impf|frueherkennung|eltern-kind-pass|schwangerschaft|krebs|frauenarzt|brustkrebs", p): b.append("A")
        if re.search(r"bewegung|ernaehrung|nichtrauch|rauchfrei|psyche|stress|gesundheitsfoerderung|bewegt|altern|lebenswelt|gesund-leben|leichter-lesen/meine", p): b.append("B")
        if re.search(r"kur-reha|krankenhausaufenthalt|palliativ|heilbehelfe", p): b.append("C")
        if re.search(r"pflege|wohnen-im-alter|senoirenheim", p): b.append("D")
        if re.search(r"patientenrechte|arztbesuch|primaerversorgung|elga|e-card|beratungsstellen|notruf|gesundheitswesen|gesundheitssuche|my-health|kontaktstelle|impressum|qualitaets|leichter-lesen\.html", p): b.append("F")
        if re.search(r"patientenrechte|wahlarzt|was-zahlt", p) and "E" not in b: b.append("E")
    return sorted(set(b)) or ["F"]


def doc_type(url):
    p = url.replace(GV, "").replace(PF, "")
    if re.search(r"impressum|datenschutz|qualitaets", p): return "recht"
    if re.search(r"patientenrechte|gesetze-und-rechte|rechtliche|sachwalter|patientenverfuegung|vorsorgevollmacht|erwachsenenvertretung", p): return "recht"
    if re.search(r"beratungsstellen|notruf|beratungsangebote|selbsthilfe|rat-hilfe", p): return "kontakt"
    if re.search(r"faq", p): return "faq"
    if re.search(r"/news/", p): return "faq" if False else "leistungsinfo"
    return "leistungsinfo"


EVID_URL = re.compile(r"vorsorgeuntersuchung|frueherkennung|impfungen|kinderimpfungen|impfungen-erwachsene|nichtrauchen|eltern-kind-pass|bewegungsempfehlungen|krebs/")
EVID_TXT = re.compile(r"Nutzen|Vorteil|Nachteil|Risiko|Überdiagnos|Evidenz|Studie|Sterblichkeit|Wirksamkeit|Heilungschance|Früherkennung|Empfehlung|Senk|Schutz|Sensitivität|falsch", re.I)


def page_lang(url):
    if "leichter-lesen" in url or url.endswith("/de/leicht-lesen"): return "de-einfach"
    return "de"


# ---------------------------------------------------------------- Build
def build_outputs(manifest, out):
    out = Path(out)
    docs = []; pages = {}
    for e in manifest["urls"]:
        if e.get("status") != 200: continue
        u = e["url"]; f = RAW / e["raw"]
        if not f.exists(): continue
        pg = parse(f, u)
        if not pg["blocks"] and not pg["teaser"]: continue
        if not pg["stand"] and e.get("last_modified"):
            try: pg["stand"] = datetime.strptime(e["last_modified"], "%a, %d %b %Y %H:%M:%S GMT").strftime("%Y-%m-%d")
            except Exception: pass
        pg["entry"] = e; pages[u] = pg
        pf = u.startswith(PF)
        base = dict(source_id=SRC, url=u, title=pg["title"], lang=page_lang(u), traeger=[], bundesland=["AT"],
                    bereich=classify(u), doc_type=doc_type(u), valid_from=None, fetched_at=e.get("fetched_at"), sha256=e["sha256"],
                    license_note=LIC_PF if pf else LIC_GV)
        if pg["stand"]: base["stand"] = pg["stand"]
        secs = sections(pg["blocks"], pg["title"])
        if pg["teaser"]:
            if secs and secs[0][0] == "Einleitung" and secs[0][1] and secs[0][1][0].strip() == pg["teaser"].strip():
                secs[0] = (secs[0][0], secs[0][1][1:])
                secs = [x for x in secs if x[1]]
            secs.insert(0, ("Zusammenfassung", [pg["teaser"]]))
        n = 0
        ev_page = bool(EVID_URL.search(u)) and "A" in base["bereich"] + ["A"] * 0 or bool(EVID_URL.search(u))
        for head, paras in secs:
            for c in chunk(paras):
                d = dict(base); d["id"] = f"{SRC}:{sha1(u)}#{n}"; d["section"] = head; d["text"] = c
                if ev_page and "A" in base["bereich"] and (EVID_TXT.search(head) or EVID_TXT.search(c)) and len(c) > 120:
                    d["tags"] = ["evidenz_nutzen"]
                docs.append(d); n += 1
    docs.sort(key=lambda d: (d["url"], int(d["id"].rsplit("#", 1)[1])))
    wr(out / "documents.jsonl", docs)
    from leistungen import build_leistungen, build_stellen
    L = build_leistungen(pages, docs); wr(out / "leistungen.jsonl", L)
    S = build_stellen(pages, docs); wr(out / "stellen.jsonl", S)
    print(f"documents={len(docs)} leistungen={len(L)} stellen={len(S)}")
    return len(docs)


def wr(path, rows):
    with open(path, "w", encoding="utf8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
