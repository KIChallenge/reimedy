# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Stufe 1 von ingest.py (Import-Modul): URL-Auswahl, höflicher, inkrementeller Abruf nach raw/."""
import hashlib, json, re, time, urllib.request, urllib.error, urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
UA = "SV-Lotse-Hackathon/0.1"
GV = "https://www.gesundheit.gv.at"
PF = "https://pflege.gv.at"
DELAY = 1.1

# ---- URL-Auswahl (Themen-Seeds auf Basis der Sitemaps) -------------------------------------------
GV_INCLUDE = [
    r"^/leben/gesundheitsvorsorge\.html$", r"^/leben/gesundheitsvorsorge/vorsorgeuntersuchung",
    r"^/leben/gesundheitsvorsorge/impfungen\.html$", r"^/leben/gesundheitsvorsorge/impfungen/(impfungen-erwachsene|kinderimpfungen|impfung-schule|impfschutz|impfungen-zielgruppen|impfreaktion|Impfdokumentation|impfstoff-zulassung|impfstoffarten)\.html$",
    r"^/leben/gesundheitsvorsorge/impfungen/ueberblick\.html$",
    r"^/leben/gesundheitsvorsorge/nichtrauchen(\.html|/(nichtraucherschutz|praevention)\.html)$",
    r"^/leben/eltern\.html$", r"^/leben/eltern/eltern-kind-pass", r"^/leben/eltern/schwangerschaft/vorbereitung/vorsorge\.html$",
    r"^/leben/bewegung\.html$", r"^/leben/bewegung/gesund-durch-sport(\.html|/bewegungsempfehlungen-[a-z-]+\.html)$",
    r"^/leben/bewegung/(warum-bewegung|was-ist-bewegung)\.html$",
    r"^/leben/ernaehrung\.html$", r"^/leben/ernaehrung/info/oesterreichische-ernaehrungspyramide\.html$", r"^/leben/ernaehrung/gesunde-ernaehrung\.html$",
    r"^/leben/altern\.html$", r"^/leben/altern/(aelter-werden|bewegung-senioren|wohnen-im-alter)\.html$", r"^/leben/altern/wohnen-im-alter/(pflegende-angehoerige-entlastungen-unterstuetzungen|senoirenheim-pflegeheim)\.html$",
    r"^/leben/psyche-seele(\.html|/(krisenintervention|praevention|psychische-belastungen)\.html)$", r"^/leben/stress\.html$",
    r"^/leben/frauengesundheit(\.html|/erster-frauenarztbesuch\.html)$",
    r"^/krankheiten/krebs/(brustkrebs|darmkrebs|eierstock-gebaermutterhalskrebs)/(frueherkennung[a-z-]*|frueherkennung-diagnose)\.html$",
    r"^/krankheiten/krebs/(hautkrebs|hoden-prostatakrebs)/(frueherkennung|prostata-frueherkennung)\.html$",
    r"^/krankheiten/krebs/eierstock-gebaermutterhalskrebs/gebaermutterhalskrebs\.html$",
    r"^/gesundheitsleistungen\.html$", r"^/gesundheitsleistungen/(arztbesuch|patientenrechte|primaerversorgung|elga|kur-reha|gesundheitswesen|gesundheitsfoerderung|palliativ-hospizversorgung|heilbehelfe-hilfsmittel|krankenhausaufenthalt)(\.html|/)",
    r"^/gesundheitsleistungen/institutionen/arge-selbsthilfe\.html$", r"^/gesundheitsleistungen/gesundheitswesen/[a-z-]+\.html$",
    r"^/service/beratungsstellen", r"^/service/notruf(\.html|/(notrufnummern|hotline|aerztenotdienst)\.html)$",
    r"^/service/elektronischer-eltern-kind-pass\.html$", r"^/service/leichter-lesen(\.html|/(impfungen|frauenarztbesuch|herz-kreislauf-erkrankung-vorbeugung)\.html|/meine-gesundheit-foerdern)",
    r"^/service/gesundheitssuche\.html$", r"^/service/my-health-eu\.html$", r"^/service/kontaktstelle-patientenmobilitaet\.html$",
    r"^/lebenslagen\.html$", r"^/lebenslagen/(aelter-werden|gesund-bleiben|wir-erwarten-ein-kind|teenager)\.html$",
    r"^/news/aktuelles/aktuell-202[56]/(bewegt-im-park[a-z0-9-]*|rauchfrei-telefon-20|eltern-kind-pass-neue-untersuchungen|brustkrebsmonat-2025)\.html$",
    r"^/ueber-uns/impressum\.html$", r"^/ueber-uns/qualitaetskriterien/(datenschutz|nutzungsorientierung|verantwortlichkeit)\.html$",
]
GV_EXCLUDE = [r"/berufe/", r"/lexikon/", r"/labor/", r"/transplantation", r"/narkose", r"/plastische-chirurgie", r"/prothesen", r"/transfusion", r"/stammzell", r"/komplementaer-medizin", r"/videos/", r"/gesundheitsberuferegister", r"/gutachten"]
PF_EXCLUDE = [r"^/en/", r"demenz(?!-selbsthilfegruppen)", r"/node/", r"kinderrechte|un-kinderrechtskonvention|each-charta|bildung|ausbildung|schulfahrt|altersbegriff|altersgrenze|alterslimit|euro-key|youngcarers|spezielle-angebote|mehrsprachige|inhalte-in-gebaerdensprache|sprachauswahl|/de/start$|uebungen-zum-gedaechtnis|seniorentreff|vereinsleben|ehrenamt|orthoptik|logopaedie|ergotherapie|diaetologie|physiotherapie|gehhilfen|ernaehrung$|barrierefreiheitserklaerung|technische-hinweise|datenschutzerklaerung"]
EXTRA = [GV + "/ueber-uns/qualitaetskriterien/datenschutz.html"]


def sha1(s): return hashlib.sha1(s.encode()).hexdigest()
def sha256(b): return hashlib.sha256(b).hexdigest()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), b""
    except Exception as e:
        return 0, {}, str(e).encode()


def sitemap_urls(base):
    st, _, body = get(base + "/sitemap.xml")
    time.sleep(DELAY)
    if st != 200: raise SystemExit(f"Sitemap {base} nicht erreichbar: {st}")
    return re.findall(r"<loc>([^<]+)</loc>", body.decode("utf8", "replace"))


def select_urls():
    out = []
    for u in sitemap_urls(GV):
        p = u[len(GV):]
        if any(re.search(x, p) for x in GV_INCLUDE) and not any(re.search(x, p) for x in GV_EXCLUDE):
            out.append(u)
    for u in sitemap_urls(PF):
        p = u[len(PF):]
        if p.startswith("/de") and not any(re.search(x, p) for x in PF_EXCLUDE):
            out.append(u)
    for u in (PF + "/de/impressum", PF + "/de/leicht-lesen"): 
        if u not in out: out.append(u)
    return sorted(set(out + EXTRA))


def robots_ok():
    rp = {}
    for base in (GV, PF):
        r = urllib.robotparser.RobotFileParser()
        st, _, body = get(base + "/robots.txt")
        txt = body.decode("utf8", "replace")
        if st == 200 and "User-agent" in txt: r.parse(txt.splitlines())
        else: r.parse([])  # keine (gültige) robots.txt -> alles erlaubt
        rp[base] = r
        time.sleep(DELAY)
    return lambda u: rp[GV if u.startswith(GV) else PF].can_fetch(UA, u)


def fetch_all(urls, old_manifest, max_age_s=0, log=print):
    """Konditionaler Abruf (ETag / Last-Modified). Gibt neues urls-Manifest zurück."""
    RAW.mkdir(exist_ok=True)
    old = {e["url"]: e for e in old_manifest.get("urls", [])}
    allowed = robots_ok()
    res = []
    for i, u in enumerate(urls, 1):
        prev = old.get(u)
        f = RAW / (sha1(u) + ".html")
        if not allowed(u):
            res.append({"url": u, "status": "robots_disallow"}); continue
        h = {}
        if prev and f.exists() and prev.get("status") == 200:
            if prev.get("etag"): h["If-None-Match"] = prev["etag"]
            if prev.get("last_modified"): h["If-Modified-Since"] = prev["last_modified"]
        st, hd, body = get(u, h)
        time.sleep(DELAY)
        hd = {k.lower(): v for k, v in hd.items()}
        if st == 304 and prev:
            e = dict(prev); e["checked_at"] = now(); res.append(e); continue
        if st == 200:
            f.write_bytes(body)
            e = {"url": u, "status": 200, "sha256": sha256(body), "etag": hd.get("etag"), "last_modified": hd.get("last-modified"), "fetched_at": now(), "raw": f.name}
            if prev and prev.get("sha256") == e["sha256"]: e["fetched_at"] = prev.get("fetched_at", e["fetched_at"])
            res.append(e)
        else:
            log(f"  ! {st} {u}")
            res.append({"url": u, "status": st, "fetched_at": now()})
        if i % 25 == 0: log(f"  fetched {i}/{len(urls)}")
    return res
