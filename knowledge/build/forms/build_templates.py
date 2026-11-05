"""Erzeugt Formular-Templates (ARCHITEKTUR §8.1.2) für alle Formulare mit lotse_zeigen=true.

  uv run --no-project --with pymupdf knowledge/build/forms/build_templates.py [--ids a,b] [--demo]

AcroForm  → Widgets + bbox, Label = Tooltip (TU) oder nächstliegender Text.
Flach     → Ausfüllbereiche geometrisch: Unterstrich-/Punktlinien, Linien, leere Kästen, Kästchenreihen,
            Ankreuzkästchen (Vektor oder Glyphe ☐), Tabellenzellen mit Label oben links.
Semantik  → Regeln (semantik.py), danach eingefrorene Overrides/LLM-Zuordnung (semantik_frozen.json).
Ergebnis  → templates/<formular_id>@<sha12>.json und index.json. Prüfung macht pruefen.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf as fitz

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import semantik as S  # noqa: E402

LIVE = HERE.parent / "links" / "formulare_live.jsonl"
CACHE = HERE / "cache"
TPL = HERE / "templates"
FROZEN = HERE / "semantik_frozen.json"
ONT = json.loads((HERE / "ontologie.json").read_text())
S.ONT_KEYS = set(ONT["schluessel"])

DEMO = ["pva_pal080", "antrag_reha_kur", "antrag_ahv_reha_unfall", "oegk_fahrtkosten_wien", "fsw_antrag_foerderung",
        "fsw_einrichtungswunsch", "fsw_bedarfsmeldung_wg", "bvaeb_9096928de6", "svs_8e5303e0b6", "oegk_infoblatt"]


def formulare() -> list[dict]:
    idx = json.loads((CACHE / "fetch_index.json").read_text())
    out = []
    for line in LIVE.open():
        r = json.loads(line)
        if not r.get("lotse_zeigen"):
            continue
        f = idx.get(r["formular_id"], {})
        r["_sha"] = f.get("sha256")
        r["_fetch"] = f
        out.append(r)
    return out


# ------------------------------------------------------------------------------- Hilfen
def words_of(page):
    return [w for w in page.get_text("words") if w[4].strip()]


def inter(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0, x1 - x0) * max(0, y1 - y0)


def area(r):
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


LEADER = re.compile(r"^[_.…‥·]{4,}$|^_{3,}")


def is_leader(t: str) -> bool:
    return bool(LEADER.match(t)) or (len(t) >= 4 and set(t) <= set("_.… "))


def label_near(words, bb, max_left=260, max_up=22, rechts=False):
    """Nächstliegender Text: links auf gleicher Zeile, sonst darüber, sonst (für Checkboxen) rechts."""
    cy = (bb[1] + bb[3]) / 2
    h = bb[3] - bb[1]
    if rechts:
        right = [w for w in words if w[0] >= bb[2] - 1 and w[0] - bb[2] < 260 and abs((w[1] + w[3]) / 2 - cy) < max(5, h * 0.6)
                 and not is_leader(w[4])]
        right.sort(key=lambda w: w[0])
        line, last = [], bb[2]
        for w in right:
            if w[0] - last > 14:
                break
            line.append(w[4]); last = w[2]
        if line:
            return " ".join(line)
    left = [w for w in words if w[2] <= bb[0] + 2 and bb[0] - w[2] < max_left and abs((w[1] + w[3]) / 2 - cy) < max(6, h * 0.55)
            and not is_leader(w[4])]
    left.sort(key=lambda w: -w[2])
    line, last = [], bb[0]
    for w in left:
        if last - w[2] > 40 and line:
            break
        line.insert(0, w[4]); last = w[0]
    if line:
        return " ".join(line)
    up = [w for w in words if w[3] <= bb[1] + 3 and bb[1] - w[3] < max_up and w[2] > bb[0] - 5 and w[0] < bb[2] - 5
          and not is_leader(w[4])]
    if up:
        ymax = max(w[3] for w in up)
        line = sorted([w for w in up if abs(w[3] - ymax) < 3], key=lambda w: w[0])
        return " ".join(w[4] for w in line)
    below = [w for w in words if w[1] >= bb[3] - 2 and w[1] - bb[3] < 12 and w[2] > bb[0] - 5 and w[0] < bb[2] - 5
             and not is_leader(w[4]) and (w[3] - w[1]) < 9]
    if below:  # kleine Beschriftung unter der Linie ("Ort, Datum", "Unterschrift")
        ymin = min(w[1] for w in below)
        line = sorted([w for w in below if abs(w[1] - ymin) < 3], key=lambda w: w[0])
        return " ".join(w[4] for w in line)
    return None


def page_markers(page, words):
    """Abschnittsmarker (arzt|behoerde|person) mit y-Position, zeilenweise."""
    lines = defaultdict(list)
    for w in words:
        lines[(w[5], w[6])].append(w)
    out = []
    for ws in lines.values():
        txt = " ".join(w[4] for w in ws)
        m = S.abschnitt_wer(txt)
        if m:
            out.append((min(w[1] for w in ws), m, txt[:120]))
    return sorted(out)


def wer_at(markers, y):
    """Abschnitt für Position y: 'arzt' gilt bis zum nächsten person-Marker, 'behoerde' nur 60 pt darunter."""
    cur, txt = None, ""
    for my, m, t in markers:
        if my > y + 2:
            break
        if m == "behoerde":
            if y - my < 60:
                cur, txt = m, t
            elif cur == "behoerde":
                cur, txt = None, ""
        else:
            cur, txt = m, t
    if cur == "behoerde" and markers:
        last_b = max(my for my, m, _ in markers if m == "behoerde" and my <= y + 2)
        if y - last_b >= 60:
            cur = None
    return cur, txt


def kontext_at(words, y, x0):
    """Überschrift-ähnlicher Kontext: Zeilen bis 80 pt darüber (für Rollen wie 'vertretende Person')."""
    ws = [w for w in words if y - 26 < w[3] <= y - 2]
    ws.sort(key=lambda w: (w[1], w[0]))
    return " ".join(w[4] for w in ws)[-300:]


# ------------------------------------------------------------------------------- AcroForm
TYPMAP = {fitz.PDF_WIDGET_TYPE_TEXT: "text", fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
          fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio", fitz.PDF_WIDGET_TYPE_COMBOBOX: "auswahl",
          fitz.PDF_WIDGET_TYPE_LISTBOX: "auswahl", fitz.PDF_WIDGET_TYPE_SIGNATURE: "unterschrift",
          fitz.PDF_WIDGET_TYPE_BUTTON: "button"}


def acro_felder(doc) -> list[dict]:
    groups: dict[str, dict] = {}
    order = []
    for page in doc:
        words = words_of(page)
        markers = page_markers(page, words)
        for w in page.widgets():
            typ = TYPMAP.get(w.field_type, "text")
            if typ == "button":
                continue
            name = w.field_name or ""
            bb = [round(v, 1) for v in w.rect]
            key = f"{name}"
            if typ == "text" and key in groups and groups[key]["page"] != page.number:
                key = f"{name}#p{page.number}"  # gleiches Feld auf Folgeseite (z. B. VSNR im Kopf)
            g = groups.get(key)
            if g is None:
                lab_near = label_near(words, bb, rechts=False)
                g = groups[key] = {"acro_name": name, "page": page.number, "bbox": bb, "typ": typ,
                                   "tooltip": w.field_label, "label_text": lab_near, "max_zeichen": w.text_maxlen or None,
                                   "comb": bool(w.field_flags & (1 << 24)) if typ == "text" else False,
                                   "optionen": [], "_markers": markers, "_words": words}
                order.append(key)
            else:
                g["bbox"] = [min(g["bbox"][0], bb[0]), min(g["bbox"][1], bb[1]), max(g["bbox"][2], bb[2]), max(g["bbox"][3], bb[3])]
            if typ in ("checkbox", "radio"):
                on = w.on_state()
                opt_label = label_near(words, bb, rechts=True) or label_near(words, bb)
                g["optionen"].append({"wert": on if on not in (True, None) else "Yes", "label": opt_label, "bbox": bb})
            if typ == "auswahl":
                g["optionen"] = [{"wert": v if isinstance(v, str) else v[0], "label": v if isinstance(v, str) else v[1]}
                                 for v in (w.choice_values or [])]
    felder = []
    for key in order:
        g = groups[key]
        typ = g["typ"]
        if typ == "checkbox" and len(g["optionen"]) > 1:
            typ = "radio"
        label = g["tooltip"] or g["label_text"]
        if typ in ("checkbox",) and g["optionen"] and not g["tooltip"]:
            label = g["optionen"][0]["label"] or label
        felder.append({"feld_id": key, "acro_name": g["acro_name"], "page": g["page"], "bbox": g["bbox"], "typ": typ,
                       "label_wörtlich": label, "_tooltip": g["tooltip"], "max_zeichen": g["max_zeichen"],
                       "format": "kaestchen_pro_zeichen" if g["comb"] else None,
                       "optionen": g["optionen"] or None,
                       "_ctx": (g["_markers"], g["_words"])})
    return felder


# ------------------------------------------------------------------------------- Flach (Geometrie)
def flat_felder(doc) -> tuple[list[dict], str | None]:
    felder: list[dict] = []
    n_text = 0
    for page in doc:
        words = words_of(page)
        n_text += len(words)
        if not words:
            continue
        markers = page_markers(page, words)
        cands: list[tuple[str, list, dict]] = []
        # 1) Unterstrich-/Punkt-Leader im Text
        for w in words:
            if is_leader(w[4]) and (w[2] - w[0]) > 25:
                cands.append(("text", [w[0], w[3] - 13, w[2], w[3] - 1], {"quelle": "leader"}))
        # Glyph-Checkboxen
        for b in page.get_text("rawdict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    for c in s["chars"]:
                        if c["c"] in "☐□❑❒■◻☑☒" or (c["c"] in "qo" and "Wingdings" in s["font"]) or (
                                s["font"].lower().startswith(("zapf", "wingding")) and c["c"] in "nopq¨o"):
                            bb = list(c["bbox"])
                            cands.append(("checkbox", bb, {"quelle": "glyph"}))
        # 2) Vektorgrafik
        hlines, rects = [], []
        for d in page.get_drawings():
            for it in d["items"]:
                if it[0] == "l":
                    p1, p2 = it[1], it[2]
                    if abs(p1.y - p2.y) < 0.8 and abs(p2.x - p1.x) > 30:
                        hlines.append([min(p1.x, p2.x), p1.y, max(p1.x, p2.x)])
                elif it[0] == "re":
                    r = it[1]
                    if r.height < 1.6 and r.width > 30:
                        hlines.append([r.x0, r.y1, r.x1])
                    elif r.width > 4 and r.height > 4:
                        rects.append([r.x0, r.y0, r.x1, r.y1])
                elif it[0] == "qu":
                    q = it[1].rect
                    if q.width > 4 and q.height > 4:
                        rects.append([q.x0, q.y0, q.x1, q.y1])
        # Kästchen: klein & quadratisch → Checkbox oder Kästchenreihe
        small = sorted([r for r in rects if 5 <= r[2] - r[0] <= 18 and 5 <= r[3] - r[1] <= 18
                        and abs((r[2] - r[0]) - (r[3] - r[1])) < 3], key=lambda r: (round(r[1]), r[0]))
        used = set()
        for i, r in enumerate(small):
            if i in used:
                continue
            row = [r]
            for j in range(i + 1, len(small)):
                q = small[j]
                if abs(q[1] - row[-1][1]) < 1.5 and 0 <= q[0] - row[-1][2] < 3:
                    row.append(q); used.add(j)
            used.add(i)
            if len(row) >= 4:
                bb = [row[0][0], row[0][1], row[-1][2], row[-1][3]]
                cands.append(("text", bb, {"quelle": "kaestchenreihe", "n": len(row), "format": "kaestchen_pro_zeichen"}))
            else:
                for q in row:
                    if not any(inter(q, w[:4]) > 0.5 * area(q) for w in words):
                        cands.append(("checkbox", q, {"quelle": "kaestchen"}))
        # Leere Boxen / Tabellenzellen
        for r in rects:
            wdt, hgt = r[2] - r[0], r[3] - r[1]
            if wdt < 40 or hgt < 11 or hgt > 90 or wdt > 560 and hgt > 60:
                continue
            inside = [w for w in words if inter(r, w[:4]) > 0.6 * area(w[:4])]
            if not inside:
                cands.append(("text", [r[0] + 1, r[1] + 1, r[2] - 1, r[3] - 1], {"quelle": "box"}))
            else:
                ytop = max(w[3] for w in inside)
                if all(w[3] < r[1] + 0.55 * hgt for w in inside) and r[3] - ytop > 9:
                    lab = " ".join(w[4] for w in sorted(inside, key=lambda w: (w[1], w[0])))
                    cands.append(("text", [r[0] + 2, ytop + 1, r[2] - 2, r[3] - 1], {"quelle": "zelle", "label": lab}))
        # Linien (Unterstreichung zum Schreiben)
        for x0, y, x1 in hlines:
            bb = [x0, y - 13, x1, y - 0.5]
            cands.append(("text", bb, {"quelle": "linie"}))
        # Kandidaten filtern: kein gedruckter Text im Feld, keine Dubletten
        page_f = []
        for typ, bb, meta in cands:
            if typ == "text":
                occ = sum(inter(bb, w[:4]) for w in words if not is_leader(w[4]))
                if occ > 0.15 * area(bb):
                    if meta["quelle"] in ("linie", "box"):
                        continue
                if bb[3] - bb[1] < 6 or bb[2] - bb[0] < 20:
                    continue
            if any(inter(bb, f["bbox"]) > 0.5 * min(area(bb), area(f["bbox"])) for f in page_f):
                continue
            lab = meta.get("label") or label_near(words, bb, rechts=(typ == "checkbox"))
            page_f.append({"page": page.number, "bbox": [round(v, 1) for v in bb], "typ": typ, "label_wörtlich": lab,
                           "acro_name": None, "max_zeichen": meta.get("n"), "format": meta.get("format"),
                           "optionen": None, "_quelle": meta["quelle"], "_ctx": (markers, words)})
        # Linien, die nur Tabellenraster/Trennlinien sind (kein Label) → verwerfen
        page_f = [f for f in page_f if f["label_wörtlich"] or f["_quelle"] in ("kaestchenreihe", "box")]
        page_f.sort(key=lambda f: (round(f["bbox"][1] / 4), f["bbox"][0]))
        felder.extend(page_f)
    if n_text == 0:
        return [], "bild_pdf_ohne_text"
    for i, f in enumerate(felder):
        f["feld_id"] = f"f{f['page'] + 1:02d}_{i:03d}"
    return felder, None


# ------------------------------------------------------------------------------- Semantik
GENERISCH = re.compile(r"^(text|textfeld|feld|field|kontrollk|check ?box|optionsfeld|undefined|untitled|t\\d|cb\\d|kk\\d)", re.I)
IDENT = {"person.svnr", "person.vorname", "person.familienname", "person.name_voll", "person.name_voll_umgekehrt",
         "person.geburtsdatum", "person.geburtsjahr", "person.geschlecht"}


def anreichern(felder, frozen: dict, form: dict):
    form_arzt = (form.get("wer_fuellt_aus") or "") in ("arzt", "krankenhaus")
    for f in felder:
        markers, words = f.pop("_ctx")
        wer_abschnitt, mtxt = wer_at(markers, f["bbox"][1])
        kontext = kontext_at(words, f["bbox"][1], f["bbox"][0]) if f["acro_name"] is None else ""
        # Rollenkontext aus Abschnitt nur, wenn Marker vom Typ person/vertreter nahe ist
        typ = f["typ"]
        quellen = []
        if f["acro_name"]:
            quellen = [f.get("_tooltip"), f["acro_name"] if not GENERISCH.match(f["acro_name"]) else None, f["label_wörtlich"]]
        else:
            quellen = [f["label_wörtlich"]]
        sem, wer = None, "versicherte"
        abw = wer_abschnitt if wer_abschnitt in ("arzt", "behoerde") else None
        for q in [x for x in quellen if x]:
            s_, w_ = S.classify(q, None, kontext + " " + (mtxt if wer_abschnitt == "person" else ""), typ, None)
            if w_ != "versicherte" or s_:
                sem, wer = s_, w_
                break
        if abw == "arzt" and wer == "versicherte" and sem not in IDENT or abw == "behoerde" and wer == "versicherte" and not sem:
            sem, wer = ("arzt.angaben", "arzt") if abw == "arzt" else ("behoerde.vermerk", "behoerde")
        if form_arzt and wer == "versicherte" and sem not in IDENT:
            wer = "arzt"
            if sem and not sem.startswith(("person.", "versicherung.")):
                sem = "arzt.angaben"
        fz = frozen.get(f["feld_id"]) if frozen else None
        herkunft = "regel" if sem else None
        if fz is not None:
            sem = fz.get("semantik", sem)
            wer = fz.get("wer", wer)
            herkunft = fz.get("herkunft", "override")
            if "pflicht" in fz:
                f["pflicht"] = fz["pflicht"]
            if fz.get("optionen_semantik") and f.get("optionen"):
                for o in f["optionen"]:
                    if o["wert"] in fz["optionen_semantik"]:
                        o["wert_semantik"] = fz["optionen_semantik"][o["wert"]]
        if sem == "unterschrift.person" or typ == "unterschrift":
            wer = "unterschrift"
            typ = "unterschrift" if f["acro_name"] is None or typ == "text" else typ
        if sem and sem.startswith("arzt."):
            wer = "arzt"
        if sem and sem.startswith("behoerde."):
            wer = "behoerde"
        if typ == "text" and sem and ONT["schluessel"].get(sem, {}).get("typ") in ("datum", "zahl"):
            typ = ONT["schluessel"][sem]["typ"]
        f["typ"] = typ
        f["semantik"] = sem
        f["semantik_herkunft"] = herkunft
        f["wer"] = wer
        f["michi_fuellt"] = bool(sem) and wer == "versicherte" and ONT["schluessel"].get(sem, {}).get("michi_fuellt", False)
        f.setdefault("pflicht", False)
        if f["format"] is None and sem:
            f["format"] = ONT["schluessel"].get(sem, {}).get("format")
        f.pop("_quelle", None)
        f.pop("_tooltip", None)
        if typ == "auswahl" and sem and not sem.startswith("versicherung."):
            f["semantik"] = sem = None
            f["michi_fuellt"] = False
        # Optionen von Geschlecht/Familienstand: Wert-Semantik per Label
        if f.get("optionen") and sem in ("person.geschlecht", "person.familienstand", "vertreter.geschlecht"):
            for o in f["optionen"]:
                if "wert_semantik" in o:
                    continue
                lab = S.norm(o.get("label"))
                for v, pre in (("weiblich", "weibl"), ("mannlich", "mannl"), ("divers", "divers"), ("ledig", "ledig"),
                               ("verheiratet", "verh"), ("verwitwet", "verw"), ("geschieden", "gesch")):
                    if lab.startswith(pre) or v in lab.split() or S.norm(o.get("wert")).startswith(pre):
                        o["wert_semantik"] = v.replace("mannlich", "männlich")
                        break
        if f.get("optionen") and sem and f["typ"] in ("checkbox", "radio") and not any(o.get("wert_semantik") for o in f["optionen"]):
            f["semantik"] = sem = None  # Ankreuzfeld ohne zuordenbare Option (z. B. "Familienstand Vater") → nicht raten
            f["michi_fuellt"] = False
    return felder


def build_one(form: dict, frozen_all: dict) -> dict:
    fid, sha = form["formular_id"], form["_sha"]
    p = CACHE / f"{sha}.pdf"
    doc = fitz.open(p)
    has_widgets = any(True for pg in doc for _ in pg.widgets())
    if re.match(r"^\s*(information|merkblatt|infoblatt|info )", form.get("name") or "", re.I) or form.get("art") == "merkblatt":
        felder, grund, quelle = [], "infoblatt_ohne_ausfuellfelder", "keine"
    elif has_widgets:
        felder, grund = acro_felder(doc), None
        quelle = "acroform"
    else:
        felder, grund = flat_felder(doc)
        quelle = "generiert"
    frozen = {**frozen_all.get(f"{fid}@{sha[:12]}", {}), **frozen_all.get(fid, {})}  # Goldstandard/Review vor LLM
    felder = anreichern(felder, frozen, form)
    tpl = {"formular_id": fid, "name": form.get("name"), "traeger": form.get("traeger"), "sha256": sha,
           "version_url": form.get("url_pdf") or form.get("url"), "pages": len(doc),
           "page_sizes": [[round(pg.rect.width, 1), round(pg.rect.height, 1)] for pg in doc],
           "quelle": quelle, "wer_fuellt_aus": form.get("wer_fuellt_aus"),
           "felder": felder, "nicht_moeglich": grund, "geprueft": None}
    return tpl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    TPL.mkdir(exist_ok=True)
    frozen_all = json.loads(FROZEN.read_text()) if FROZEN.exists() else {}
    forms = formulare()
    if a.ids:
        want = set(a.ids.split(","))
        forms = [f for f in forms if f["formular_id"] in want]
    elif a.demo:
        forms = [f for f in forms if f["formular_id"] in DEMO]
    n = 0
    for f in forms:
        if not f["_sha"]:
            continue
        try:
            tpl = build_one(f, frozen_all)
        except Exception as e:  # noqa
            print("FEHLER", f["formular_id"], repr(e)[:200], file=sys.stderr)
            continue
        out = TPL / f"{f['formular_id']}@{f['_sha'][:12]}.json"
        old = json.loads(out.read_text()) if out.exists() else None
        if old and old.get("pruefung"):
            tpl["pruefung"] = old["pruefung"]  # pruefen.py entscheidet per Fingerabdruck, ob Sicht/Vision noch gilt
        out.write_text(json.dumps(tpl, ensure_ascii=False, indent=1) + "\n")
        n += 1
    print(n, "Templates", file=sys.stderr)


if __name__ == "__main__":
    main()
