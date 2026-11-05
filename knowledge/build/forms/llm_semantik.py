"""LLM-Kontrolle der Regel-Zuordnung (ARCHITEKTUR §8.1.2: „semantik per Regeln, sonst per LLM, Ergebnis eingefroren“).

  uv run --no-project --with pymupdf --with httpx knowledge/build/forms/llm_semantik.py [--ids …] [--nur-ungeprueft] [--workers 4]

Für jedes Template bekommt das LLM die Felder mit Seite, wörtlichem Label, Abschnittskontext (Text darüber) und der
Regel-Zuordnung, dazu die erlaubten Ontologie-Schlüssel. Es korrigiert nur:
  - Felder, die zu einer ANDEREN Person/Sache gehören (Ehepartner, Kind, Verstorbene, Angehörige, Arbeitgeber, Arzt,
    Einrichtung, Tabelle) → anderer Schlüssel oder null,
  - eindeutige Personen-/Adress-/Kontaktfelder ohne Zuordnung → Schlüssel.
Medizinische, ärztliche, Unterschrifts-, Einkommens- und Bankfelder werden nie freigegeben (die Sperren gelten weiter).
Ergebnis: semantik_frozen.json[<formular_id>@<sha12>] mit herkunft="llm". Goldstandard/Review-Einträge bleiben vorrangig.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

import pymupdf as fitz

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import llm  # noqa: E402

FROZEN = HERE / "semantik_frozen.json"
ONT = json.loads((HERE / "ontologie.json").read_text())
ERLAUBT = [k for k, v in ONT["schluessel"].items() if v["michi_fuellt"]]
GESPERRT_PREFIX = ("arzt.", "medizinisch.", "unterschrift.", "einkommen.", "bank.", "behoerde.")

PROMPT = """Du prüfst die automatische Zuordnung von Formularfeldern eines österreichischen Sozialversicherungs-Formulars
zu kanonischen Schlüsseln. Formular: "{name}" (Träger: {traeger}).
Die Software füllt später NUR Felder über die antragstellende Person (person.*, adresse.*, kontakt.*), deren
Vertreter:in bzw. ausfüllende Angehörige (vertreter.*), die Versicherte, von der eine Mitversicherung abgeleitet ist
(versicherte_person.*), Ehe-/Lebenspartner:in (partner.*), Kind (kind.*), Arbeitgeber, Pension/Pflegegeld, Datum/Ort.
Erlaubte Schlüssel: {keys}

Felder (id | Seite | Label | Text darüber/links | aktuelle Zuordnung):
{felder}

Aufgabe: Gib NUR die Felder zurück, deren Zuordnung FALSCH ist oder fehlt, mit dem richtigen Schlüssel oder null.
- null, wenn das Feld zu einer Person/Sache gehört, für die es keinen passenden Schlüssel gibt (z. B. Verstorbene, weitere
  Angehörige in einer Tabelle, Einrichtung, Behandler, Bank, Beträge, Zeitraum, Nummern außer Versicherungsnummer) oder wenn
  es medizinische/ärztliche Angaben, Einkommen oder Unterschrift betrifft.
- Ein Feld in einer Tabelle für mehrere Personen (Angehörige, Kinder, Mitbewohner) bekommt null, außer es ist eindeutig die
  Zeile der antragstellenden Person.
- Behalte richtige Zuordnungen bei (nicht auflisten). Im Zweifel null.
Antwort als JSON: {{"korrekturen": [{{"id": "...", "schluessel": "<schlüssel>|null", "grund": "kurz"}}]}}"""


def kontext(doc, f) -> str:
    page = doc[f["page"]]
    x0, y0, x1, y1 = f["bbox"]
    words = page.get_text("words")
    above = [w for w in words if y0 - 70 < w[3] <= y0 + 1 and w[2] > x0 - 120 and w[0] < x1 + 40]
    left = [w for w in words if abs((w[1] + w[3]) / 2 - (y0 + y1) / 2) < 6 and w[2] <= x0 + 2 and x0 - w[2] < 200]
    above.sort(key=lambda w: (round(w[1]), w[0]))
    t = " ".join(w[4] for w in above)[-160:] + " ¦ " + " ".join(w[4] for w in sorted(left, key=lambda w: w[0]))[-80:]
    return t.replace("|", "/").replace("\n", " ")


def task(path: Path) -> tuple[str, dict]:
    t = json.loads(path.read_text())
    if not t["felder"] or t.get("nicht_moeglich"):
        return "", {}
    doc = fitz.open(HERE / "cache" / f"{t['sha256']}.pdf")
    zeilen = []
    for f in t["felder"]:
        if f.get("wer") in ("arzt", "behoerde", "unterschrift") or (f.get("semantik") or "").startswith(GESPERRT_PREFIX):
            continue
        if f["typ"] in ("checkbox", "radio") and not f.get("semantik"):
            continue
        zeilen.append(f"{f['feld_id']} | {f['page'] + 1} | {(f.get('label_wörtlich') or '')[:70]} | {kontext(doc, f)} | {f.get('semantik')}")
    if not zeilen:
        return t["formular_id"] + "@" + t["sha256"][:12], {}
    out = {}
    for i in range(0, len(zeilen), 80):
        prompt = PROMPT.format(name=t.get("name"), traeger=t.get("traeger"), keys=", ".join(ERLAUBT), felder="\n".join(zeilen[i:i + 80]))
        vp = ((t.get("pruefung") or {}).get("vision") or {}).get("probleme") or []
        if vp:
            prompt += "\n\nBefunde einer Sichtprüfung der Probefüllung (Testperson Anna Berger) – korrigiere die betroffenen Felder:\n" + \
                "\n".join(f"- {x.get('feld')}: {x.get('problem')}" for x in vp if x.get("schwer", True))[:3000]
        for versuch in range(4):
            try:
                r = llm.chat_json(prompt)
                break
            except Exception as e:  # noqa
                if "429" in repr(e) and versuch < 3:
                    time.sleep(8 * (versuch + 1)); continue
                print("LLM-Fehler", t["formular_id"], repr(e)[:120], file=sys.stderr)
                r = {}
                break
        ids = {f["feld_id"] for f in t["felder"]}
        for k in r.get("korrekturen") or []:
            fid, key = k.get("id"), k.get("schluessel")
            if fid not in ids:
                continue
            if key in ("null", "", None):
                key = None
            if key is not None and (key not in ERLAUBT or key.startswith(GESPERRT_PREFIX)):
                continue
            out[fid] = {"semantik": key, "herkunft": "llm", "grund": (k.get("grund") or "")[:120]}
            if key is None:
                out[fid]["wer"] = "versicherte"
    return t["formular_id"] + "@" + t["sha256"][:12], out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids"); ap.add_argument("--nur-ungeprueft", action="store_true"); ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    paths = sorted((HERE / "templates").glob("*.json"))
    if a.ids:
        want = set(a.ids.split(","))
        paths = [p for p in paths if p.name.split("@")[0] in want]
    if a.nur_ungeprueft:
        paths = [p for p in paths if not json.loads(p.read_text()).get("geprueft")]
    with cf.ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(task, paths))
    frozen = json.loads(FROZEN.read_text()) if FROZEN.exists() else {}
    n = 0
    for key, corr in res:
        if not key:
            continue
        fid = key.split("@")[0]
        manual = frozen.get(fid, {})
        cur = dict(frozen.get(key) or {})  # frühere LLM-Korrekturen bleiben, neue ergänzen/ersetzen
        for feld, v in corr.items():
            if feld in manual or feld in cur:
                continue  # Goldstandard/Review hat Vorrang
            cur[feld] = v
            n += 1
        frozen[key] = cur
    FROZEN.write_text(json.dumps(frozen, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(n, "LLM-Korrekturen eingefroren", file=sys.stderr)


if __name__ == "__main__":
    main()
