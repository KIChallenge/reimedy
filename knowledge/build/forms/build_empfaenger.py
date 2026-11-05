"""Empfänger je Formular (ARCHITEKTUR §8.1.3) → forms/empfaenger.jsonl + forms/empfaenger_stellen.json

  uv run --no-project --with pymupdf knowledge/build/forms/build_empfaenger.py

Deterministische Zuständigkeitsregel (kein LLM):
  fix                 → eine Stelle (FSW nur Wien, AUVA, Dachverband)
  landesstelle_nach_plz → Landesstelle des Trägers im Bundesland der Wohnsitz-PLZ (ÖGK, PVA, SVS, BVAEB, SMS)
  auszahlende_stelle  → Pflegegeld: Stelle, die die Pension auszahlt (traeger=…, Standard PVA), dort Landesstelle nach PLZ
  nach_versicherung   → Formular gilt für mehrere Träger: zuständig ist der Träger der Person (traeger=…), dort nach PLZ
Die Stellen-Snapshot-Datei stammt aus knowledge/build/traeger.json (Träger-Register, Session knowledge-db) plus den
Landesstellen aus sources/*/out/stellen.jsonl (BVAEB, Sozialministeriumservice), damit forms_api ohne DB auflösen kann.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent
sys.path.insert(0, str(BUILD))
from common import BL_NORM  # noqa: E402

LIVE = BUILD / "links" / "formulare_live.jsonl"
TRAEGER = BUILD / "traeger.json"
SOURCES = BUILD.parent / "sources"

TRAEGER_MAP = {"SVS": "svs", "BVAEB": "bvaeb", "ÖGK": "oegk", "FSW": "fsw", "PVA": "pva", "AUVA": "auva",
               "Sozialministeriumservice": "sozialministeriumservice", "SMS": "sozialministeriumservice"}
ABTEILUNG = [(r"pflegegeld", "Pflegegeld"), (r"reha|kur|anschlussheil|erholung", "Rehabilitation/Kur"),
             (r"rezeptgeb", "Rezeptgebühren"), (r"fahrtkost|transport", "Fahrtkosten"), (r"pension", "Pensionen"),
             (r"wochengeld|kinderbetreuung|familienzeit", "Familienleistungen"), (r"krankengeld|krankmeldung|arbeitsunf", "Krankengeld"),
             (r"behindertenpass|begünstigt", "Behindertenpass / Begünstigte Behinderte"), (r"24.?h|24-stunden|24hb", "Förderung 24-Stunden-Betreuung"),
             (r"pflegekarenz|hospiz", "Pflegekarenzgeld"), (r"zahn|kiefer", "Zahnleistungen"), (r"beitr|versicherung", "Versicherung und Beiträge"),
             (r"heilbehelf|hilfsmittel", "Heilbehelfe und Hilfsmittel"), (r"kostenerstatt|rückerstatt|wahlarzt", "Kostenerstattung")]
PFLEGEKARENZ_SMS = re.compile(r"pflegekarenz|hospiz|24.?h|24-stunden|24hb|ansuchenform|behindertenpass|begünstigte behinderte")
ADR_RX = re.compile(r"([A-ZÄÖÜ][\wäöüß.\- ]{2,40}(?:straße|strasse|gasse|platz|weg|ring|kai|allee|Straße|Gasse|Platz))\s*([\d][\d\-/a-z]*)\s*[,\n ]\s*(?:A-)?(\d{4})\s+([A-ZÄÖÜ][\wäöüß.\- ]{1,30})")


def stellen_snapshot() -> dict:
    """traeger_id → {zentrale, nur_bundesland, aufloesung, landesstellen: {bl: stelle}}"""
    data = json.loads(TRAEGER.read_text(encoding="utf-8"))
    out = {}
    for t in data["traeger"]:
        ls = {}
        for s in t.get("landesstellen") or []:
            ls.setdefault(s["bundesland"], s)
        a = t.get("aus_stellen")
        if a:
            p = SOURCES / a["source_id"] / "out" / "stellen.jsonl"
            if p.exists():
                for line in p.open(encoding="utf-8"):
                    r = json.loads(line)
                    if a.get("typ") and r.get("typ") != a["typ"]:
                        continue
                    bl = BL_NORM.get(r.get("bundesland"), r.get("bundesland"))
                    if not bl:
                        continue
                    rolle = "landesstelle" if "Landesstelle" in (r.get("name") or "") else "stelle"
                    cur = ls.get(bl)
                    if cur is None or (cur.get("_rolle") != "landesstelle" and rolle == "landesstelle"):
                        ls[bl] = {"id": f"{t['id']}:{r['stelle_id']}", "traeger_id": t["id"], "bundesland": bl, "name": r.get("name"),
                                  "adresse": r.get("adresse"), "plz": r.get("plz"), "telefon": r.get("telefon"), "email": r.get("email"),
                                  "url": r.get("url"), "quelle_url": r.get("quelle_url"), "_rolle": rolle}
        out[t["id"]] = {"name": t["name"], "aufloesung": t.get("aufloesung"), "nur_bundesland": t.get("nur_bundesland"),
                        "zentrale": t.get("zentrale"), "online": t.get("online"), "kontakt_hinweis": t.get("kontakt_hinweis"),
                        "quelle_url": t.get("quelle_url"), "landesstellen": ls}
    return {"stand": data.get("stand"), "quelle": "knowledge/build/traeger.json + sources/*/out/stellen.jsonl", "traeger": out}


def adresse_im_formular(sha: str | None) -> str | None:
    if not sha:
        return None
    p = HERE / "cache" / f"{sha}.pdf"
    if not p.exists():
        return None
    try:
        import pymupdf as fitz
        doc = fitz.open(p)
        page = doc[0]
        txt = page.get_text("text", clip=fitz.Rect(0, 0, page.rect.width, page.rect.height * 0.35))
    except Exception:  # noqa
        return None
    m = ADR_RX.search(txt)
    if not m:
        return None
    return f"{m[1].strip()} {m[2]}, {m[3]} {m[4].strip().splitlines()[0]}"


def regel(r: dict) -> tuple[str, str | None, list[str], str]:
    """→ (aufloesung, traeger_id|None, kandidaten, begruendung)"""
    tr = (r.get("traeger") or "").strip()
    name = (r.get("name") or "").lower()
    lids = r.get("leistung_ids") or []
    if "pflegegeld" in lids or "pflegegeld" in name:
        if tr in ("PVA", "PVA, BVAEB", "") or "pva" in r["formular_id"] or r["formular_id"].startswith("oegv"):
            return ("auszahlende_stelle", None, ["pva", "bvaeb", "svs"],
                    "§ 22 BPGG: Pflegegeld beantragt man bei der Stelle, die die Pension auszahlt (ASVG-Pension → PVA). Ohne Angabe: PVA.")
    if tr in TRAEGER_MAP:
        tid = TRAEGER_MAP[tr]
        if tid == "fsw":
            return ("fix", tid, [tid], "FSW ist nur für Personen mit Hauptwohnsitz in Wien zuständig.")
        return ("landesstelle_nach_plz", tid, [tid], f"Formular des Trägers {tr}; zuständig ist die Landesstelle des Wohnsitz-Bundeslandes.")
    if "," in tr or tr.startswith(("KV/PV", "SV")):
        kand = [TRAEGER_MAP[x.strip()] for x in tr.replace("KV/PV", "").replace("SV (Träger im Formular wählen)", "").split(",") if x.strip() in TRAEGER_MAP]
        return ("nach_versicherung", None, kand or ["oegk", "pva", "svs", "bvaeb"],
                "Formular gilt für mehrere Träger: zuständig ist der eigene Kranken- bzw. Pensionsversicherungsträger der Person.")
    if PFLEGEKARENZ_SMS.search(name) or any(x in lids for x in ("pflegekarenz", "familienhospizkarenz", "foerderung_24h_betreuung")):
        return ("landesstelle_nach_plz", "sozialministeriumservice", ["sozialministeriumservice"],
                "Pflegekarenzgeld, 24-Stunden-Förderung, Behindertenpass: Sozialministeriumservice, Landesstelle nach Wohnsitz.")
    if "schwerarbeit" in name or "pension" in name:
        return ("nach_versicherung", None, ["pva", "svs", "bvaeb"], "Pensionsantrag beim eigenen Pensionsversicherungsträger.")
    return ("unbekannt", None, [], "Zuständige Stelle steht im Formular bzw. auf der Seite der Behörde (keine SV-Zuständigkeit).")


def main():
    snap = stellen_snapshot()
    (HERE / "empfaenger_stellen.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n")
    idx = json.loads((HERE / "cache" / "fetch_index.json").read_text()) if (HERE / "cache" / "fetch_index.json").exists() else {}
    rows = []
    for line in LIVE.open(encoding="utf-8"):
        r = json.loads(line)
        if not r.get("lotse_zeigen"):
            continue
        auf, tid, kand, begr = regel(r)
        name_l = (r.get("name") or "").lower()
        abt = next((a for rx, a in ABTEILUNG if re.search(rx, name_l)), None)
        kanal = []
        if r.get("online_url") or r.get("url_status") == "online":
            kanal.append("online")
        t = snap["traeger"].get(tid) if tid else None
        if t and ((t.get("zentrale") or {}).get("email") or any(s.get("email") for s in t["landesstellen"].values())):
            kanal.append("email")
        if r.get("url_status") != "online":
            kanal.append("post")
        kanal.append("persoenlich")
        sha = (idx.get(r["formular_id"]) or {}).get("sha256") or r.get("sha256")
        rows.append({
            "formular_id": r["formular_id"], "name": r.get("name"), "traeger": r.get("traeger"), "traeger_id": tid,
            "kandidaten": kand, "abteilung": abt, "kanal": kanal, "aufloesung": auf,
            "stelle_ids": sorted(s["id"] for k in kand for s in snap["traeger"].get(k, {}).get("landesstellen", {}).values()),
            "online_url": r.get("online_url") or (r.get("url") if r.get("url_status") == "online" else None),
            "email": (t.get("zentrale") or {}).get("email") if t else None,
            "post_adresse": None if auf != "fix" or not t else ", ".join(x for x in [t["name"], (t.get("zentrale") or {}).get("adresse"),
                                                                                        " ".join(filter(None, [(t.get("zentrale") or {}).get("plz"), (t.get("zentrale") or {}).get("ort")]))] if x),
            "adresse_im_formular": adresse_im_formular(sha),
            "hinweis": begr, "nur_bundesland": (t or {}).get("nur_bundesland"),
        })
    with (HERE / "empfaenger.jsonl").open("w", encoding="utf-8") as fh:
        for x in rows:
            fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    from collections import Counter
    print(len(rows), Counter(x["aufloesung"] for x in rows), file=sys.stderr)


if __name__ == "__main__":
    main()
