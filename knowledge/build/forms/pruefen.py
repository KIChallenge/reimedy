"""Prüfschleife (ARCHITEKTUR §8.1.2): Testperson aus der Ontologie probefüllen, rendern, prüfen.

  uv run --no-project --with pymupdf --with httpx knowledge/build/forms/pruefen.py [--ids a,b|--demo|--alle] [--vision] [--sicht ids]

1. Geometrie: jeder Wert passt in sein Feld (Länge/Schriftgröße/max_zeichen), Optionen treffen, keine zwei
   gefüllten Felder überlappen, Felder liegen auf der Seite, bei generierten Feldern kein gedruckter Text im Feld.
2. Vision: die gerenderten Seiten (gefüllte Werte blau, generierte Felder rot umrandet) prüft ein Vision-LLM
   (`--vision`) oder ein Mensch/Claude per Sichtprüfung (`--sicht id1,id2` trägt das Ergebnis ein).
Nur wenn beides bestanden ist, bekommt das Template `geprueft` – nur das gibt die API aus.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import sys
from pathlib import Path

import pymupdf as fitz

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fill import fill  # noqa: E402

TPL = HERE / "templates"
CACHE = HERE / "cache"
RENDER = CACHE / "pruefung"
ONT = json.loads((HERE / "ontologie.json").read_text())
WERTE = {k: v["beispiel"] for k, v in ONT["schluessel"].items() if v.get("beispiel") is not None}
HEUTE = dt.date.today().isoformat()
DEMO = ["pva_pal080", "antrag_reha_kur", "antrag_ahv_reha_unfall", "oegk_fahrtkosten_wien", "fsw_antrag_foerderung",
        "fsw_einrichtungswunsch", "fsw_bedarfsmeldung_wg", "bvaeb_9096928de6", "svs_8e5303e0b6", "oegk_infoblatt"]


def inter(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def area(r):
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def geometrie(tpl: dict, pdf: bytes) -> tuple[list[str], bytes, list[dict]]:
    befunde = []
    doc = fitz.open(stream=pdf, filetype="pdf")
    for f in tpl["felder"]:
        pg = doc[f["page"]].mediabox  # Widget-Koordinaten sind unrotiert
        m = max(pg.width, pg.height)
        b = f["bbox"]
        if b[0] < -2 or b[1] < -2 or b[2] > m + 2 or b[3] > m + 2:
            befunde.append(f"{f['feld_id']}: bbox außerhalb der Seite")
    filled_pdf, prot = fill(tpl, pdf, WERTE, markieren=True)
    # Felder, in die ein typischer Wert nicht passt (zu schmal, Teilformat, Option fehlt): Michi füllt sie nicht,
    # sondern fragt nach. Das ist eine Korrektur des Templates, kein Fehler der Prüfung.
    by_id = {f["feld_id"]: f for f in tpl["felder"]}
    korr = 0
    for p in prot:
        if p["status"] in ("zu_lang", "keine_option"):
            f = by_id[p["feld_id"]]
            f["michi_fuellt"] = False
            f["pruef_hinweis"] = {"zu_lang": "Feld zu schmal bzw. Teilformat (max. Zeichen) für typische Werte – Michi fragt nach",
                                  "keine_option": "keine passende Auswahl-Option – Michi fragt nach"}[p["status"]]
            korr += 1
        elif p["status"] != "ok":
            befunde.append(f"{p['feld_id']} ({p['semantik']}={p['wert']!r}): {p['status']}")
    if korr:
        filled_pdf, prot = fill(tpl, pdf, WERTE, markieren=True)
    ids = {p["feld_id"] for p in prot}
    fl = [f for f in tpl["felder"] if f["feld_id"] in ids and f["typ"] not in ("checkbox", "radio")]
    for i, a in enumerate(fl):
        for b in fl[i + 1:]:
            if a["page"] == b["page"] and a.get("acro_name") != b.get("acro_name") and \
                    inter(a["bbox"], b["bbox"]) > 0.2 * min(area(a["bbox"]), area(b["bbox"])):
                befunde.append(f"Überlappung {a['feld_id']} / {b['feld_id']}")
    if tpl["quelle"] == "generiert":
        for f in tpl["felder"]:
            if f["typ"] in ("checkbox", "radio"):
                continue
            words = [w for w in doc[f["page"]].get_text("words") if not set(w[4]) <= set("_.… ")]
            occ = sum(inter(f["bbox"], w[:4]) for w in words)
            if occ > 0.2 * area(f["bbox"]):
                befunde.append(f"{f['feld_id']}: gedruckter Text im Feld")
    return befunde, filled_pdf, prot


def render(tpl: dict, filled: bytes) -> list[Path]:
    doc = fitz.open(stream=filled, filetype="pdf")
    out_dir = RENDER / tpl["formular_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    seiten = sorted({f["page"] for f in tpl["felder"]}) or [0]
    paths = []
    for n in seiten:
        page = doc[n]
        if tpl["quelle"] == "generiert":
            for f in tpl["felder"]:
                if f["page"] == n:
                    col = (0.85, 0.1, 0.1) if f["michi_fuellt"] else (0.6, 0.6, 0.6)
                    page.draw_rect(fitz.Rect(f["bbox"]), color=col, width=0.6)
        p = out_dir / f"p{n + 1}.png"
        page.get_pixmap(dpi=90).save(p)
        paths.append(p)
    return paths


VISION_PROMPT = """Du prüfst ein automatisch probe-ausgefülltes österreichisches Formular (Testperson Anna Berger, fiktiv).
Blauer Text = von der Software eingefügte Werte. Rote Rahmen = automatisch erkannte Ausfüllfelder, die die Software füllt;
graue Rahmen = erkannte Felder, die sie nicht füllt. Bilder = Seiten {seiten}. Eingefügte Werte auf diesen Seiten (Seite: Feld-Label → Wert):
{werte}
Prüfe NUR das Layout, nicht die Inhalte: (1) Steht jeder blaue Wert im Feld, das zu seinem Label passt (z. B. Vorname im Vorname-Feld)?
(2) Überdeckt blauer Text gedruckten Formulartext oder ragt er aus dem Feld? (3) Liegen rote Rahmen auf freien Ausfüllbereichen
(Linie, Kästchen, leere Zelle) und nicht auf gedrucktem Text? (4) Gehört jedes blau gefüllte Feld wirklich zur antragstellenden
Person (Anna Berger) bzw. ihrer Vertreterin Sandra Berger – und NICHT zu einer Tabelle für weitere Angehörige, Einkommen, Ärzt:innen,
Einrichtungen oder zum Amtsvermerk? Ein Wert in so einer Tabelle ist ein Problem.
Antworte als JSON: {{"ok": true|false, "probleme": [{{"feld": "Label oder Wert", "problem": "kurz", "schwer": true|false}}]}}.
schwer=true NUR bei echten Fehlern: Wert im falschen Feld oder bei der falschen Person/Tabelle, Wert überdeckt gedruckten Text
so dass er unleserlich wird, roter Rahmen liegt auf gedrucktem Text. KEIN Problem (nicht melden): knappe Ränder, Wert nahe
an Linien, leere Felder, Felder die auf diesen Seiten nicht vorkommen, gleiche Werte in Kopfzeilen mehrerer Seiten."""


def vision(tpl: dict, prot: list[dict], bilder: list[Path]) -> dict:
    import time
    import llm
    lab = {f["feld_id"]: f.get("label_wörtlich") for f in tpl["felder"]}
    seite = {f["feld_id"]: f["page"] for f in tpl["felder"]}
    res = {"ok": True, "probleme": []}
    for i in range(0, len(bilder), 3):
        chunk = bilder[i:i + 3]
        nums = {int(b.stem[1:]) - 1 for b in chunk}
        werte = "\n".join(f"- S. {seite[p['feld_id']] + 1}: {str(lab.get(p['feld_id']) or p['semantik'])[:60]} → {p['wert']}"
                          for p in prot if p["status"] == "ok" and seite[p["feld_id"]] in nums) or "(auf diesen Seiten keine Werte)"
        for versuch in range(4):
            try:
                r = llm.chat_json(VISION_PROMPT.format(werte=werte, seiten=", ".join(str(n + 1) for n in sorted(nums))),
                                  images=[b.read_bytes() for b in chunk])
                break
            except Exception as e:  # noqa
                if "429" in repr(e) and versuch < 3:
                    time.sleep(10 * (versuch + 1)); continue
                raise
        probs = r.get("probleme") or []
        schwer = [x for x in probs if x.get("schwer", True)]
        res["ok"] = res["ok"] and not schwer
        res["probleme"] += probs
    return res


def fingerabdruck(tpl: dict) -> str:
    import hashlib
    x = [(f["feld_id"], f["bbox"], f.get("semantik"), f.get("michi_fuellt")) for f in tpl["felder"]]
    return hashlib.sha256(json.dumps([tpl["sha256"], x]).encode()).hexdigest()[:16]


def pruefe(path: Path, mit_vision: bool) -> dict:
    tpl = json.loads(path.read_text())
    erg = {"formular_id": tpl["formular_id"], "datei": path.name}
    if tpl.get("nicht_moeglich"):
        tpl["geprueft"] = None
        tpl["pruefung"] = {"am": HEUTE, "ok": False, "befunde": [tpl["nicht_moeglich"]]}
        path.write_text(json.dumps(tpl, ensure_ascii=False, indent=1) + "\n")
        return {**erg, "status": "nicht_moeglich", "grund": tpl["nicht_moeglich"]}
    pdf = (CACHE / f"{tpl['sha256']}.pdf").read_bytes()
    befunde, filled, prot = geometrie(tpl, pdf)
    bilder = render(tpl, filled)
    pr = {"am": HEUTE, "geometrie_ok": not befunde, "befunde": befunde, "n_gefuellt": sum(p["status"] == "ok" for p in prot),
          "bilder": [str(b.relative_to(HERE)) for b in bilder]}
    vok = None
    if mit_vision and not befunde:
        try:
            v = vision(tpl, prot, bilder)
            pr["vision"] = v
            vok = v["ok"]
        except Exception as e:  # noqa
            pr["vision_fehler"] = repr(e)[:200]
    fp = fingerabdruck(tpl)
    pr["fp"] = fp
    alt = tpl.get("pruefung") or {}
    if alt.get("sicht") and alt.get("sicht_fp") == fp:
        pr["sicht"], pr["sicht_fp"] = alt["sicht"], fp
        vok = alt["sicht"]["ok"] if vok is None else (vok or alt["sicht"]["ok"])
    if alt.get("vision") and alt.get("fp") == fp and "vision" not in pr:
        pr["vision"] = alt["vision"]
        vok = alt["vision"]["ok"] if vok is None else vok
    ok = (not befunde) and bool(vok)
    pr["ok"] = ok
    methode = "+".join(x for x in ["geometrie", "vision_llm" if pr.get("vision") else None, "sichtpruefung" if pr.get("sicht") else None] if x)
    tpl["pruefung"] = pr
    tpl["geprueft"] = {"methode": methode, "am": HEUTE, "testperson": "ontologie.beispiel (Anna Berger, fiktiv)"} if ok else None
    path.write_text(json.dumps(tpl, ensure_ascii=False, indent=1) + "\n")
    return {**erg, "status": "geprueft" if ok else ("geometrie_fehler" if befunde else "ungeprueft"), "befunde": befunde[:5],
            "vision": pr.get("vision", {}).get("probleme") if pr.get("vision") else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids"); ap.add_argument("--demo", action="store_true"); ap.add_argument("--alle", action="store_true")
    ap.add_argument("--vision", action="store_true")
    ap.add_argument("--nur-ungeprueft", action="store_true")
    ap.add_argument("--sicht", help="id1,id2: Sichtprüfung bestanden eintragen (nach Ansicht der Render-Bilder)")
    ap.add_argument("--sicht-notiz", default="Render-Bilder angesehen: Werte in den passenden Feldern, keine Überlappung")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    paths = sorted(TPL.glob("*.json"))
    if a.sicht:
        for fid in a.sicht.split(","):
            for p in TPL.glob(f"{fid}@*.json"):
                t = json.loads(p.read_text())
                pr = t.setdefault("pruefung", {})
                pr["sicht"] = {"ok": True, "am": HEUTE, "notiz": a.sicht_notiz}
                pr["sicht_fp"] = pr.get("fp")
                p.write_text(json.dumps(t, ensure_ascii=False, indent=1) + "\n")
        a.ids = a.sicht
    if a.ids:
        want = set(a.ids.split(","))
        paths = [p for p in paths if p.name.split("@")[0] in want]
    elif a.demo:
        paths = [p for p in paths if p.name.split("@")[0] in DEMO]
    if a.nur_ungeprueft:
        paths = [p for p in paths if not json.loads(p.read_text()).get("geprueft")]
    with cf.ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(pruefe, paths, [a.vision] * len(paths)))
    for r in res:
        print(json.dumps(r, ensure_ascii=False)[:400])
    from collections import Counter
    print(Counter(r["status"] for r in res), file=sys.stderr)


if __name__ == "__main__":
    main()
