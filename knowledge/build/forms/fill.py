"""Referenz-Filler: Template + PDF + Werte (Ontologie-Schlüssel → Text) → ausgefülltes PDF.

Gleiche Logik wie Michis generischer Filler (ARCHITEKTUR §8.2), hier für die Prüfschleife:
AcroForm-Felder setzen bzw. bei flachen PDFs per Overlay in die bbox schreiben (Kästchenformat beachten).
Felder mit michi_fuellt=False (Unterschrift, arzt, medizinisch, Behörde, Einkommen) werden nie gefüllt.
"""
from __future__ import annotations

import pymupdf as fitz

BLAU = (0.05, 0.2, 0.75)


def _norm(s) -> str:
    import unicodedata
    s = str(s or "").lower().replace("ß", "ss")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).strip()


def option_fuer(feld: dict, wert: str) -> dict | None:
    w = _norm(wert)
    for o in feld.get("optionen") or []:
        if o.get("wert_semantik") and _norm(o["wert_semantik"]) == w:
            return o
    for o in feld.get("optionen") or []:
        lab = _norm(o.get("label")).rstrip(".")
        if lab and (lab == w or lab.split()[0].rstrip(".") == w or (len(lab) >= 4 and w.startswith(lab))):
            return o
    if len(w) >= 4:  # Auswahl-Listen: "Wien" ∈ "Landesstelle für Wien, NÖ u. Bgld."
        hits = [o for o in feld.get("optionen") or [] if w in _norm(o.get("label") or o.get("wert"))]
        if len(hits) == 1:
            return hits[0]
    return None


def fit_fontsize(text: str, bb, start=10.0, minimum=5.0) -> float | None:
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    fs = min(start, max(minimum, h * 0.75))
    while fs >= minimum:
        if fitz.get_text_length(text, "helv", fs) <= w - 2:
            return fs
        fs -= 0.5
    return None


def fill(template: dict, pdf_bytes: bytes, werte: dict[str, str], markieren: bool = False) -> tuple[bytes, list[dict]]:
    """→ (pdf, protokoll[{feld_id, semantik, wert, status: ok|zu_lang|keine_option|kein_widget}])."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    prot = []
    widgets: dict[tuple[int, str], list] = {}
    pages = [doc[i] for i in range(len(doc))]  # Seiten-Objekte am Leben halten (Widgets sind daran gebunden)
    if template["quelle"] == "acroform":
        for page in pages:
            for w in page.widgets():
                widgets.setdefault((page.number, w.field_name), []).append(w)
    for f in template["felder"]:
        if not f.get("michi_fuellt") or not f.get("semantik"):
            continue
        wert = werte.get(f["semantik"])
        if wert in (None, ""):
            continue
        wert = str(wert)
        page = pages[f["page"]]
        st = "ok"
        if f.get("acro_name"):
            ws = widgets.get((f["page"], f["acro_name"]), [])
            if not ws:
                prot.append({"feld_id": f["feld_id"], "semantik": f["semantik"], "wert": wert, "status": "kein_widget"}); continue
            if f["typ"] in ("checkbox", "radio"):
                o = option_fuer(f, wert)
                if not o:
                    st = "keine_option"
                else:
                    for w in ws:
                        if w.on_state() == o["wert"]:
                            w.field_value = w.on_state(); w.update()
            elif f["typ"] == "auswahl":
                o = option_fuer(f, wert)
                if o:
                    ws[0].field_value = o["wert"]; ws[0].update()
                else:
                    st = "keine_option"
            else:
                mx = f.get("max_zeichen")
                if f.get("format") == "kaestchen_pro_zeichen" or f.get("semantik") in ("bank.iban", "person.svnr"):
                    wert = wert.replace(" ", "")
                if mx and len(wert) > mx:
                    st = "zu_lang"
                elif not fit_fontsize(wert, f["bbox"]) and not f.get("format") == "kaestchen_pro_zeichen":
                    st = "zu_lang"
                for w in ws:
                    w.field_value = wert[:mx] if mx else wert
                    if markieren:
                        w.text_color = BLAU
                    w.update()
        else:
            bb = fitz.Rect(f["bbox"])
            if f["typ"] in ("checkbox", "radio"):
                page.insert_text((bb.x0 + 1, bb.y1 - 1), "X", fontsize=max(6, bb.height * 0.9), color=BLAU)
            elif f.get("format") == "kaestchen_pro_zeichen" and f.get("max_zeichen"):
                n = f["max_zeichen"]
                cw = bb.width / n
                txt = wert.replace(" ", "").replace(".", "")
                if len(txt) > n:
                    st = "zu_lang"
                fs = min(10, bb.height * 0.75)
                for i, ch in enumerate(txt[:n]):
                    x = bb.x0 + i * cw + (cw - fitz.get_text_length(ch, "helv", fs)) / 2
                    page.insert_text((x, bb.y1 - (bb.height - fs) / 2 - 1), ch, fontsize=fs, color=BLAU)
            else:
                fs = fit_fontsize(wert, f["bbox"])
                if fs is None:
                    st = "zu_lang"; fs = 5
                page.insert_text((bb.x0 + 1, bb.y1 - max(1.5, (bb.height - fs) / 2)), wert, fontsize=fs, color=BLAU)
        prot.append({"feld_id": f["feld_id"], "semantik": f["semantik"], "wert": wert, "status": st})
    out = doc.tobytes(garbage=3, deflate=True)
    return out, prot


def acroform_kopie(template: dict, pdf_bytes: bytes) -> bytes:
    """Flaches PDF → AcroForm-angereicherte Kopie (Widgets an den Template-bboxes, Name = feld_id)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for f in template["felder"]:
        if f["typ"] == "unterschrift" or f["wer"] in ("behoerde",):
            continue
        page = doc[f["page"]]
        w = fitz.Widget()
        w.rect = fitz.Rect(f["bbox"])
        w.field_name = f["feld_id"]
        w.field_label = (f.get("label_wörtlich") or "")[:200]
        if f["typ"] in ("checkbox", "radio"):
            w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        else:
            w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            w.text_fontsize = 0
            if f.get("format") == "kaestchen_pro_zeichen" and f.get("max_zeichen"):
                w.text_maxlen = f["max_zeichen"]
                w.field_flags |= 1 << 24  # Comb
        page.add_widget(w)
    return doc.tobytes(garbage=3, deflate=True)
