# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Ingestion der Wiener Einrichtungen (Open Government Data, data.wien.gv.at) nach CONTRACT.md.

Aufruf:  uv run knowledge/sources/wien_ogd/ingest.py [--offline] [--force]
  --offline  nichts laden, nur aus raw/ neu bauen
  --force    Hash-Vergleich ignorieren (raw/ immer überschreiben)

Pro Layer ein WFS-GetFeature (GeoJSON, EPSG:4326). Der Server liefert kein ETag/Last-Modified;
Änderungserkennung über sha256 der Features (ohne `timeStamp`). Outputs werden immer
deterministisch aus raw/ neu gebaut (idempotent).
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent
RAW, OUT = ROOT / "raw", ROOT / "out"
SOURCE_ID = "wien_ogd"
UA = "SV-Lotse-Hackathon/0.1"
WFS = ("https://data.wien.gv.at/daten/geo?service=WFS&request=GetFeature&version=1.1.0"
       "&typeName=ogdwien:{t}&srsName=EPSG:4326&outputFormat=json")
LICENSE = "CC BY 4.0 – Namensnennung: Stadt Wien – data.wien.gv.at"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/deed.de"
DELAY = 1.1
# typ = Schema-C-Typ, kat = feinere Kategorie (Zusatzfeld `kategorie`), datensatz = data.gv.at/Katalog-Seite
LAYERS = {
 "ARZTOGD": dict(typ="arzt", kat="arzt", name="Ärztinnen und Ärzte (Standorte)", cat="https://www.data.gv.at/katalog/dataset/fdcaabe5-0efd-4701-8fd9-49935c0d9cff"),
 "APOTHEKEOGD": dict(typ="apotheke", kat="apotheke", name="Apotheken Wien", cat="https://www.data.gv.at/katalog/dataset/cf00fe06-e4b2-4319-af00-85230e7b2f1b"),
 "PRIMAERVERSORGUNGOGD": dict(typ="pve", kat="primaerversorgung", name="Primärversorgungseinheiten Wien", cat="https://www.data.gv.at/katalog/dataset/32a796c7-ef87-4240-9e5d-5684e23c7fde"),
 "KRANKENHAUSOGD": dict(typ="einrichtung", kat="krankenhaus", name="Krankenanstalten Wien", cat=None),
 "AMBULANZOGD": dict(typ="einrichtung", kat="spitalsambulanz", name="Spitalsambulanzen Wien", cat="https://www.data.gv.at/katalog/dataset/7fcf7f09-12d7-4b06-a183-93c51f940670"),
 "WOHNPFLEGEHAUSOGD": dict(typ="einrichtung", kat="pflegewohnhaus", name="Wohn- und Pflegehäuser Wien", cat="https://www.data.gv.at/katalog/dataset/e7065317-1d57-434a-8428-efa263ecc526"),
 "BERATUNGSZENTROGD": dict(typ="beratung", kat="beratungszentrum_pflege_fsw", name="Beratungszentren Pflege und Betreuung (FSW)", cat="https://www.data.gv.at/katalog/dataset/8f5a2c99-5128-4d4a-bbd4-4943649e3fbe"),
 "IMPFSTELLEOGD": dict(typ="einrichtung", kat="impfstelle", name="Impfstellen Wien", cat="https://www.data.gv.at/katalog/dataset/c294da25-b556-4bd6-9e1a-343b28279a33"),
 "FAMHEBAMMEOGD": dict(typ="beratung", kat="familienhebamme", name="Familienhebammen Wien", cat="https://www.data.gv.at/katalog/dataset/1878dd80-b127-4a72-82e0-e00c2ed6487e"),
 "SOZIALMARKTOGD": dict(typ="einrichtung", kat="sozialmarkt", name="Sozialmärkte Wien", cat=None),
}
ZUST = {"impfstelle": ["impfungen"], "familienhebamme": ["hebammen"]}

sha256 = lambda b: hashlib.sha256(b).hexdigest()
now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
ws = lambda s: (re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " – ", str(s))).strip() or None) if s not in (None, "") else None

def canon(content: bytes) -> bytes:
    d = json.loads(content); d.pop("timeStamp", None)
    return json.dumps(d, sort_keys=True, ensure_ascii=False).encode()

def fetch_all(manifest: dict, force: bool):
    RAW.mkdir(exist_ok=True)
    urls = manifest.setdefault("urls", {})
    last = 0.0
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=120) as cl:
        for t in LAYERS:
            u = WFS.format(t=t)
            ent = urls.get(u, {})
            time.sleep(max(0, DELAY - (time.time() - last)))
            try:
                r = cl.get(u); last = time.time()
            except httpx.HTTPError as e:
                print("ERR", t, e, file=sys.stderr); ent["status"] = f"error:{e.__class__.__name__}"; urls[u] = ent; continue
            ent["status"] = r.status_code
            if r.status_code != 200 or b'"FeatureCollection"' not in r.content[:200]:
                print(r.status_code, t, file=sys.stderr); urls[u] = ent; continue
            h = sha256(canon(r.content))
            f = RAW / f"{t}.json"
            if force or ent.get("sha256") != h or not f.exists():
                f.write_bytes(r.content); ent.update(sha256=h, changed_at=now()); print("NEU/GEÄNDERT", t)
            else:
                print("unverändert", t)
            ent.update(fetched_at=now(), etag=r.headers.get("etag"), last_modified=r.headers.get("last-modified"),
                       layer=t, n_features=len(json.loads(r.content)["features"]))
            urls[u] = ent

# ---- Normalisierung --------------------------------------------------------
BEZ_RE = re.compile(r"^\s*(\d{1,2})\.\s*,\s*(.*)$")
def bezirk_of(p: dict):
    b = p.get("BEZIRK")
    if isinstance(b, (int, float)) or (isinstance(b, str) and b.isdigit()): return int(b)
    m = BEZ_RE.match(p.get("ADRESSE") or "")
    return int(m.group(1)) if m else None
def plz_of(p: dict, bez):
    if p.get("PLZ"): return str(int(p["PLZ"]))
    return f"1{bez:02d}0" if bez and 1 <= bez <= 23 else None
def adresse_of(p: dict, bez):
    a = ws(p.get("ADRESSE"))
    if not a: return None
    m = BEZ_RE.match(a)
    street = m.group(2) if m else a
    plz = plz_of(p, bez)
    return f"{street}, {plz} Wien" if plz else f"{street}, Wien"
def tel(v):
    v = ws(v)
    if not v or "(+43" in v: return None  # defekte Sammelnummer im AKH-Ambulanzdatensatz
    return v
def url_ok(u):
    u = ws(u)
    return u if u and re.match(r"https?://", u) else None

def name_of(t, p):
    if t == "AMBULANZOGD":
        return " – ".join(x for x in [ws(p.get("KRANKENHAUS_BEZEICHNUNG")) and ws(p["KRANKENHAUS_BEZEICHNUNG"]), ws(p.get("ABTEILUNG")), ws(p.get("BEZEICHNUNG"))] if x)
    return ws(p.get("NAME") or p.get("BEZEICHNUNG"))

def build_stellen():
    out, seen = [], set()
    for t, cfg in LAYERS.items():
        f = RAW / f"{t}.json"
        if not f.exists(): continue
        d = json.loads(f.read_bytes())
        for ft in d["features"]:
            p, g = ft["properties"], ft.get("geometry") or {}
            lon, lat = (g.get("coordinates") or [None, None])[:2] if g.get("type") == "Point" else (None, None)
            bez = bezirk_of(p)
            fid = ft["id"].split(".", 1)[1]
            sid = f"wien_ogd_{cfg['kat']}_{re.sub(r'[^A-Za-z0-9]+', '_', str(p.get('OBJECTID') or p.get('SE_SDO_ROWID') or p.get('PVE_ID') or fid))}"
            if sid in seen: sid += "_" + re.sub(r"\W+", "", fid)[-8:]
            seen.add(sid)
            nm = name_of(t, p)
            s = dict(stelle_id=sid, name=nm, typ=cfg["typ"], adresse=adresse_of(p, bez), plz=plz_of(p, bez), bundesland="W",
                     telefon=tel(p.get("TELEFON")), email=ws(p.get("EMAIL")),
                     url=url_ok(p.get("WEBLINK1") or p.get("INTERNET")),
                     oeffnungszeiten=ws(p.get("OEFFNUNGSZEIT") or p.get("IMPFZEITEN")),
                     zustaendig_fuer=ZUST.get(cfg["kat"], []),
                     geo=[round(lat, 6), round(lon, 6)] if lat is not None else None,
                     quelle_url=WFS.format(t=t).replace("&outputFormat=json", "&outputFormat=json"),
                     # Zusatzfelder (über Schema C hinaus)
                     kategorie=cfg["kat"], bezirk=bez, plz_abgeleitet=not bool(p.get("PLZ")),
                     fachrichtung=ws(p.get("FACH")) if t == "ARZTOGD" else None,
                     kassenvertrag=None,  # im OGD-Datensatz NICHT enthalten (siehe SOURCE.md)
                     lizenz=LICENSE, katalog_url=cfg["cat"] or WFS.format(t=t))
            if t == "BERATUNGSZENTROGD":
                s["zustaendig_plz"] = ws(p.get("ZUSTAENDIG_FUER"))
            if s["name"]: out.append(s)
    out.sort(key=lambda s: s["stelle_id"])
    return out

def build_documents(stellen):
    docs, ts = [], now()
    for t, cfg in LAYERS.items():
        n = sum(1 for s in stellen if s["kategorie"] == cfg["kat"])
        txt = (f"Datensatz „{cfg['name']}“ der Stadt Wien (Open Government Data), Layer ogdwien:{t}. {n} Standorte mit Koordinaten in Wien. "
               f"Lizenz: {LICENSE}. Der Datensatz enthält Name, Adresse, Bezirk, teils Telefon, E-Mail und Webseite; "
               "keine Angabe zu Kassenverträgen, Öffnungszeiten (außer Impfstellen/FSW-Beratungszentren) oder Wartezeiten.")
        docs.append(dict(id=f"{SOURCE_ID}:{hashlib.sha1(t.encode()).hexdigest()}#0", source_id=SOURCE_ID, url=cfg["cat"] or WFS.format(t=t),
                         title=cfg["name"], section="Datensatzbeschreibung", text=txt, lang="de", traeger=["Stadt Wien"],
                         bundesland=["W"], bereich=["C"] if cfg["typ"] in ("arzt", "apotheke", "pve") or cfg["kat"] in ("krankenhaus", "spitalsambulanz", "impfstelle") else ["D" if cfg["kat"] in ("pflegewohnhaus", "beratungszentrum_pflege_fsw") else "E"],
                         doc_type="kontakt", valid_from=None, fetched_at=ts, sha256=sha256(txt.encode()), license_note=LICENSE))
    return docs

def write_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--offline", action="store_true"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    mf = OUT / "manifest.json"
    manifest = json.loads(mf.read_text()) if mf.exists() else {}
    manifest["source_id"] = SOURCE_ID
    if isinstance(manifest.get("urls"), list):  # Listenform (Vertrag) -> Dict für den Lauf
        manifest["urls"] = {e["url"]: e for e in manifest["urls"]}
    if not a.offline:
        fetch_all(manifest, a.force); manifest["fetched_at"] = now()
    stellen = build_stellen()
    docs = build_documents(stellen)
    write_jsonl(OUT / "stellen.jsonl", stellen)
    write_jsonl(OUT / "documents.jsonl", docs)
    write_jsonl(OUT / "leistungen.jsonl", [])
    write_jsonl(OUT / "formulare.jsonl", [])
    manifest["n_docs"] = len(docs); manifest["n_stellen"] = len(stellen); manifest["license"] = LICENSE
    manifest["urls"] = [dict({k: v for k, v in e.items() if k != "url"}, url=u) for u, e in sorted((manifest.get("urls") or {}).items())] \
        if isinstance(manifest.get("urls"), dict) else manifest.get("urls", [])
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"stellen={len(stellen)} docs={len(docs)}")

if __name__ == "__main__":
    main()
