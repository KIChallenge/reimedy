"""Formular-API für knowledge-db (ARCHITEKTUR §8.1.5). Nur stdlib, lädt Dateien lazy und cached sie.

  ontologie()                          → GET /forms/ontologie
  template(formular_id, nur_geprueft)  → GET /formular/<id>/template   (Standard: nur geprüfte Templates)
  pdf(formular_id)                     → GET /formular/<id>/pdf        ((bytes, content_type, filename) der
                                          AcroForm-angereicherten Kopie, sonst None → Aufrufer leitet auf die Live-URL um)
  empfaenger(formular_id, plz, traeger)→ GET /formular/<id>/empfaenger (deterministische Zuständigkeit, s. build_empfaenger.py)

Templates liegen als templates/<formular_id>@<sha256[:12]>.json. Gibt es mehrere Versionen, gilt die zum aktuellen
sha256 in links/formulare_live.jsonl, sonst die neueste Datei.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
TPL = HERE / "templates"
PDF = HERE / "pdf"
LIVE = HERE.parent / "links" / "formulare_live.jsonl"

BL_NORM = {"NÖ": "N", "OÖ": "O", "ST": "St", "STMK": "St"}
TRAEGER_ALIAS = {"ögk": "oegk", "oegk": "oegk", "österreichische gesundheitskasse": "oegk", "pva": "pva",
                 "pensionsversicherungsanstalt": "pva", "svs": "svs", "bvaeb": "bvaeb", "auva": "auva", "fsw": "fsw",
                 "sms": "sozialministeriumservice", "sozialministeriumservice": "sozialministeriumservice", "kfa": "kfa"}
BL_NAME = {"W": "Wien", "N": "Niederösterreich", "B": "Burgenland", "O": "Oberösterreich", "S": "Salzburg",
           "St": "Steiermark", "K": "Kärnten", "T": "Tirol", "V": "Vorarlberg"}


def plz_bundesland(plz) -> str | None:
    """Gleiche Regel wie knowledge/build/common.py (hier dupliziert, damit forms_api ohne Build-Imports läuft)."""
    p = str(plz or "").strip()
    if not (len(p) == 4 and p.isdigit()):
        return None
    n = int(p)
    if n < 2000:
        return "W"
    if n < 4000:
        return "B" if 2421 <= n <= 2491 else "N"
    if n < 5000:
        return "O"
    if n < 6000:
        return "O" if 5100 <= n <= 5299 or 5310 <= n <= 5360 else "S"
    if n < 7000:
        return "V" if n >= 6700 else "T"
    if n < 8000:
        return "B"
    if n < 9000:
        return "St"
    return "T" if n >= 9900 else "K"


@lru_cache(maxsize=1)
def ontologie() -> dict:
    return json.loads((HERE / "ontologie.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _aktuelle_sha() -> dict[str, str]:
    out = {}
    if LIVE.exists():
        for line in LIVE.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("sha256"):
                out[r["formular_id"]] = r["sha256"]
    return out


@lru_cache(maxsize=1024)
def _template_datei(formular_id: str) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", formular_id or ""):
        return None
    files = sorted(TPL.glob(f"{formular_id}@*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    sha = _aktuelle_sha().get(formular_id)
    if sha:
        for p in files:
            if p.name == f"{formular_id}@{sha[:12]}.json":
                return p
    return files[0]


@lru_cache(maxsize=512)
def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def template(formular_id: str, nur_geprueft: bool = True) -> dict | None:
    p = _template_datei(formular_id)
    if not p:
        return None
    t = _load(p)
    if nur_geprueft and not t.get("geprueft"):
        return None
    out = {k: v for k, v in t.items() if k != "pruefung"}
    pr = t.get("pruefung") or {}
    out["pruefung"] = {k: pr.get(k) for k in ("am", "ok", "n_gefuellt", "befunde") if k in pr}
    sha = _aktuelle_sha().get(formular_id)
    out["version_aktuell"] = (sha == t.get("sha256")) if sha else None
    out["pdf_angereichert"] = bool(_pdf_datei(formular_id, t.get("sha256")))
    return out


def _pdf_datei(formular_id: str, sha: str | None) -> Path | None:
    if not sha:
        return None
    p = PDF / f"{formular_id}@{sha[:12]}.pdf"
    return p if p.exists() else None


def pdf(formular_id: str):
    """(bytes, 'application/pdf', dateiname) der AcroForm-angereicherten Kopie eines flachen PDFs (nur geprüfte
    Templates). Für AcroForm-Originale und alle anderen: None → Live-URL des Trägers (kanonisch, §3)."""
    p = _template_datei(formular_id)
    if not p:
        return None
    t = _load(p)
    if not t.get("geprueft"):
        return None
    f = _pdf_datei(formular_id, t.get("sha256"))
    if not f:
        return None
    return f.read_bytes(), "application/pdf", f"{formular_id}_ausfuellbar.pdf"


@lru_cache(maxsize=1)
def _empfaenger() -> dict[str, dict]:
    p = HERE / "empfaenger.jsonl"
    if not p.exists():
        return {}
    return {r["formular_id"]: r for r in (json.loads(l) for l in p.open(encoding="utf-8"))}


@lru_cache(maxsize=1)
def _stellen() -> dict:
    p = HERE / "empfaenger_stellen.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"traeger": {}}


def _traeger_id(traeger: str | None) -> str | None:
    if not traeger:
        return None
    t = traeger.strip().lower()
    return TRAEGER_ALIAS.get(t) or (t if t in _stellen()["traeger"] else None)


def _stelle_kurz(s: dict | None) -> dict | None:
    if not s:
        return None
    adr = s.get("adresse") or ""
    if s.get("plz") and s["plz"] not in adr:
        adr = f"{adr}, {s['plz']} {s.get('ort') or ''}".strip(", ")
    return {"stelle_id": s.get("id"), "name": s.get("name"), "post_adresse": adr or None, "telefon": s.get("telefon"),
            "email": s.get("email"), "url": s.get("url"), "quelle_url": s.get("quelle_url"), "bundesland": s.get("bundesland")}


def empfaenger(formular_id: str, plz: str | None = None, traeger: str | None = None) -> dict | None:
    """Zuständige Stelle für dieses Formular. plz = Wohnsitz-PLZ der Person, traeger = ihr Versicherungsträger bzw.
    die pensionsauszahlende Stelle (für aufloesung=nach_versicherung|auszahlende_stelle). Deterministisch, kein LLM."""
    e = _empfaenger().get(formular_id)
    if not e:
        return None
    out = dict(e)
    bl = plz_bundesland(plz)
    out["plz"], out["bundesland"] = plz, bl
    tid = e.get("traeger_id")
    rueckfragen = []
    if e["aufloesung"] in ("nach_versicherung", "auszahlende_stelle"):
        wunsch = _traeger_id(traeger)
        if wunsch and (wunsch in e["kandidaten"] or not e["kandidaten"]):
            tid = wunsch
        elif e["aufloesung"] == "auszahlende_stelle":
            tid = "pva"
            rueckfragen.append("Wer zahlt die Pension aus? Ohne Angabe gehen wir von der PVA aus (ASVG-Pension).")
        else:
            rueckfragen.append(f"Bei welchem Träger ist die Person versichert? Möglich: {', '.join(e['kandidaten'])}")
    out["traeger_id"] = tid
    st = _stellen()["traeger"].get(tid) if tid else None
    zust = None
    if st:
        if st.get("nur_bundesland") and bl and st["nur_bundesland"] != bl:
            zust = {"status": "nicht_zustaendig", "grund": f"{st['name']} ist nur für {BL_NAME.get(st['nur_bundesland'])} zuständig."}
        elif e["aufloesung"] == "fix" or not st["landesstellen"]:
            z = st.get("zentrale") or {}
            zust = {"status": "zentrale", "stelle": {"stelle_id": tid, "name": st["name"],
                    "post_adresse": ", ".join(x for x in [z.get("adresse"), " ".join(filter(None, [z.get("plz"), z.get("ort")]))] if x) or None,
                    "telefon": z.get("telefon"), "email": z.get("email"), "url": z.get("url")}}
            if st.get("kontakt_hinweis"):
                zust["hinweis"] = st["kontakt_hinweis"]
        elif bl and bl in st["landesstellen"]:
            zust = {"status": "landesstelle", "stelle": _stelle_kurz(st["landesstellen"][bl])}
        else:
            if not bl:
                rueckfragen.append("Wohnsitz-PLZ fehlt – damit bestimmen wir die zuständige Landesstelle.")
            z = st.get("zentrale") or {}
            zust = {"status": "zentrale", "stelle": {"stelle_id": tid, "name": st["name"], "email": z.get("email"),
                    "post_adresse": ", ".join(x for x in [z.get("adresse"), " ".join(filter(None, [z.get("plz"), z.get("ort")]))] if x) or None,
                    "telefon": z.get("telefon"), "url": z.get("url")}}
        if zust and zust.get("stelle") and not zust["stelle"].get("email") and (st.get("zentrale") or {}).get("email"):
            zust["stelle"]["email_zentrale"] = st["zentrale"]["email"]
    elif e["aufloesung"] == "nach_versicherung":
        zust = {"status": "rueckfrage", "kandidaten": e["kandidaten"],
                "grund": "Zuständig ist der eigene Versicherungsträger der Person – bitte traeger= mitgeben (z. B. PVA für Reha von Pensionist:innen)."}
    elif e["aufloesung"] == "unbekannt":
        zust = {"status": "siehe_formular", "adresse_im_formular": e.get("adresse_im_formular")}
    out["zustaendig"] = zust
    if bl:  # je Kandidat-Träger nur die Stelle im Bundesland der PLZ (Rückfrage „Wer zahlt die Pension?“ reicht dann)
        je = {}
        for k in e.get("kandidaten") or []:
            s = _stellen()["traeger"].get(k, {}).get("landesstellen", {}).get(bl)
            je[k] = s["id"] if s else None
        out["stellen_je_traeger"] = je
        out["stelle_ids"] = [x for x in je.values() if x]
    out["rueckfragen"] = rueckfragen
    out["versand"] = {"mock_endpoint": f"/mock-traeger/{tid}/eingang" if tid else None,
                      "hinweis": "Demo: Versand nur über die Mock-Träger-API bzw. Mailpit, nie an echte Adressen."}
    return out
