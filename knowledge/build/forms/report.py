"""Erzeugt forms/REPORT.md und forms/index.json (Abdeckung: geprüft, ungeprüft, nicht möglich – mit Grund).

  python3 knowledge/build/forms/report.py
"""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE = HERE.parent / "links" / "formulare_live.jsonl"
DEMO = ["pva_pal080", "antrag_reha_kur", "antrag_ahv_reha_unfall", "oegk_fahrtkosten_wien", "fsw_antrag_foerderung",
        "fsw_einrichtungswunsch", "fsw_bedarfsmeldung_wg", "bvaeb_9096928de6", "svs_8e5303e0b6", "oegk_rezeptgebuehrenbefreiung"]

GRUND_TEXT = {
    "online": "Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt",
    "word": "Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar",
    "html": "Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b)",
    "infoblatt_ohne_ausfuellfelder": "Infoblatt/Merkblatt ohne Ausfüllfelder",
    "bild_pdf_ohne_text": "Bild-PDF ohne Textebene – OCR (Vision) ausstehend",
    "kein_pdf": "kein PDF im Cache (Download fehlgeschlagen)",
    "keine_felder": "keine Ausfüllbereiche erkannt",
}


def main():
    idx = json.loads((HERE / "cache" / "fetch_index.json").read_text()) if (HERE / "cache" / "fetch_index.json").exists() else {}
    tpls = {}
    for p in (HERE / "templates").glob("*.json"):
        t = json.loads(p.read_text())
        tpls[t["formular_id"]] = (p.name, t)
    pdfs = {p.name.split("@")[0] for p in (HERE / "pdf").glob("*.pdf")} if (HERE / "pdf").exists() else set()
    rows = []
    for line in LIVE.open(encoding="utf-8"):
        r = json.loads(line)
        if not r.get("lotse_zeigen"):
            continue
        fid = r["formular_id"]
        row = {"formular_id": fid, "name": r.get("name"), "traeger": r.get("traeger"), "art": r.get("art")}
        if fid in tpls:
            name, t = tpls[fid]
            f = t["felder"]
            pr = t.get("pruefung") or {}
            row.update({"template": f"templates/{name}", "quelle": t["quelle"], "n_felder": len(f),
                        "n_semantik": sum(1 for x in f if x.get("semantik")), "n_michi": sum(1 for x in f if x.get("michi_fuellt")),
                        "n_arzt": sum(1 for x in f if x.get("wer") == "arzt"), "pdf_angereichert": fid in pdfs})
            if t.get("nicht_moeglich"):
                row["status"], row["grund"] = "nicht_moeglich", t["nicht_moeglich"]
            elif not f:
                row["status"], row["grund"] = "nicht_moeglich", "keine_felder"
            elif t.get("geprueft"):
                row["status"], row["methode"] = "geprueft", t["geprueft"]["methode"]
            else:
                row["status"] = "ungeprueft"
                g = pr.get("befunde") or [x.get("problem") for x in ((pr.get("vision") or {}).get("probleme") or [])][:3]
                row["grund"] = "; ".join(str(x) for x in g)[:300] or ("Vision-Prüfung fehlgeschlagen" if pr.get("vision_fehler") else "noch nicht visuell geprüft")
        else:
            fe = (idx.get(fid) or {}).get("fehler", "")
            if r.get("url_status") == "online":
                g = "online"
            elif "word" in fe or "msword" in fe or "openxml" in fe:
                g = "word"
            elif "html" in fe:
                g = "html"
            else:
                g = "kein_pdf"
            row["status"], row["grund"] = "nicht_moeglich", g
        rows.append(row)
    (HERE / "index.json").write_text(json.dumps({"stand": dt.date.today().isoformat(), "formulare": rows}, ensure_ascii=False, indent=1) + "\n")

    st = Counter(r["status"] for r in rows)
    q = Counter((r.get("quelle"), r["status"]) for r in rows if r.get("quelle"))
    gr = Counter(r["grund"] for r in rows if r["status"] == "nicht_moeglich")
    tot = Counter()
    for r in rows:
        for k in ("n_felder", "n_semantik", "n_michi", "n_arzt"):
            tot[k] += r.get(k) or 0
    emp = [json.loads(l) for l in (HERE / "empfaenger.jsonl").open()] if (HERE / "empfaenger.jsonl").exists() else []
    L = []
    L.append(f"# Formulare: Templates, Prüfung, Empfänger (ARCHITEKTUR §8.1)\n\nStand: {dt.date.today().isoformat()} · erzeugt von `report.py`\n")
    L.append("Vorgabe Arne: *„Alle Formulare müssen von Michi ausfüllbar sein, als PDF speicherbar und an die korrekte Stelle versendbar.“*\n")
    L.append("## Abdeckung\n")
    L.append(f"| | Anzahl |\n|---|---|\n| Formulare im Lotsen (`lotse_zeigen`) | {len(rows)} |\n"
             f"| **geprüft** (Template wird ausgeliefert) | **{st['geprueft']}** |\n| ungeprüft (Template vorhanden, Prüfung offen/negativ) | {st['ungeprueft']} |\n"
             f"| nicht möglich | {st['nicht_moeglich']} |\n| Empfänger bestimmt (`empfaenger.jsonl`) | {len(emp)} |\n")
    L.append("\nNach Quelle: " + ", ".join(f"{a}/{b}: {n}" for (a, b), n in sorted(q.items())) + "\n")
    L.append(f"\nFelder gesamt {tot['n_felder']}, davon mit Ontologie-Schlüssel {tot['n_semantik']}, von Michi füllbar {tot['n_michi']}, "
             f"ärztlich (gesperrt) {tot['n_arzt']}. Angereicherte AcroForm-Kopien: {sum(1 for r in rows if r.get('pdf_angereichert'))}.\n")
    L.append("\n### Nicht möglich – Gründe\n\n| Grund | Anzahl |\n|---|---|\n" + "".join(f"| {GRUND_TEXT.get(g, g)} | {n} |\n" for g, n in gr.most_common()))
    L.append("\n## Demo-Formulare\n\n| Formular | Status | Methode | Felder | Michi füllt |\n|---|---|---|---|---|\n")
    for r in rows:
        if r["formular_id"] in DEMO:
            L.append(f"| `{r['formular_id']}` {r['name'][:50]} | {r['status']} | {r.get('methode', r.get('grund', ''))} | {r.get('n_felder', '')} | {r.get('n_michi', '')} |\n")
    L.append("\nRezeptgebührenbefreiung **ÖGK**: `oegk_rezeptgebuehrenbefreiung` (von der Links-Session nachgezogen, AcroForm, geprüft). "
             "`oegk_infoblatt` ist ein Merkblatt ohne Ausfüllfelder.\n")
    L.append("""
## Wie es funktioniert

1. `fetch_pdfs.py` lädt die Live-PDFs (≤1 Req/s/Host) in `cache/<sha256>.pdf` (gitignored).
2. `build_templates.py`: AcroForm → Widgets, bbox, Tooltip-/Nachbar-Label; flach → Ausfüllbereiche geometrisch (Unterstrich-/Punktlinien,
   Linien, leere Kästen, Kästchenreihen = Zeichen-Kästchen, Ankreuzkästchen, Tabellenzellen mit Label). `semantik` per Regeln
   (`semantik.py`), Abschnitts-Sperren (ärztlicher Teil, Amtsvermerk), dann eingefrorene Zuordnungen (`semantik_frozen.json`;
   Demo-Formulare = Goldstandard aus Michi `b5-comms/server/forms/mappings.py`).
3. `pruefen.py`: Testperson (`ontologie.json` → `beispiel`, fiktiv) probefüllen (`fill.py`, derselbe Ablauf wie Michis Filler),
   Geometrie prüfen (Wert passt, keine Überlappung, kein Drucktext im Feld), Seiten rendern, **Vision-LLM** bzw. **Sichtprüfung**.
   Felder, in die ein typischer Wert nicht passt, werden auf `michi_fuellt=false` gesetzt (Michi fragt nach). Nur bei bestandener
   Prüfung setzt es `geprueft`. Der Fingerabdruck (bbox + semantik) bindet die Sichtprüfung an genau diese Template-Version.
4. `make_pdfs.py`: AcroForm-angereicherte Kopien flacher PDFs, nur amtliche Werke (SV-Träger, Bund), siehe `pdf/LIZENZ.md`.
5. `build_empfaenger.py`: `empfaenger.jsonl` + `empfaenger_stellen.json` (Snapshot aus `traeger.json`). Regel:
   fix · landesstelle_nach_plz · auszahlende_stelle (Pflegegeld, § 22 BPGG) · nach_versicherung · unbekannt.
6. `forms_api.py`: `ontologie()`, `template(id)`, `pdf(id)`, `empfaenger(id, plz, traeger)` – verdrahtet in `search.py` (knowledge-db).

**Harte Grenzen:** `wer=arzt`, `unterschrift.*`, `medizinisch.*`, `behoerde.*`, `einkommen.*` und `bank.*` haben `michi_fuellt=false`.
Keine Diagnose, keine Befunddeutung. Die Ontologie wird nur additiv geändert.

**Neu bauen:** `fetch_pdfs.py` → `build_templates.py` → `pruefen.py --alle --vision` → `make_pdfs.py` → `build_empfaenger.py` → `report.py`.
Ändert sich ein sha256 (neue Formularversion), entsteht ein neues Template `<id>@<sha12>.json`, das erst nach erneuter Prüfung ausgeliefert wird.
""")
    L.append("\n## Alle Formulare\n\n| Formular | Träger | Status | Quelle | Felder/Michi | Grund bzw. Methode |\n|---|---|---|---|---|---|\n")
    for r in sorted(rows, key=lambda r: (r["status"], r["formular_id"])):
        L.append(f"| `{r['formular_id']}` | {r.get('traeger') or ''} | {r['status']} | {r.get('quelle') or ''} | "
                 f"{r.get('n_felder', '')}/{r.get('n_michi', '')} | {(r.get('methode') or GRUND_TEXT.get(r.get('grund'), r.get('grund')) or '').replace('|', '/')[:160]} |\n")
    (HERE / "REPORT.md").write_text("".join(L))
    print(dict(st))


if __name__ == "__main__":
    main()
