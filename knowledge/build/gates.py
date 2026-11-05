#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["fastembed>=0.4", "sqlite-vec==0.1.9", "numpy"]
# ///
"""Qualitäts-Gates (ARCHITEKTUR §6). Laufen gegen eine fertig gebaute DB (meist lotse.sqlite.new) VOR dem Swap.

    uv run --python 3.12 knowledge/build/gates.py [--db PFAD]
Exit 0 = alle harten Gates grün.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DB_PATH  # noqa: E402
from build_db import HINT_POLICY_ICD, hint_allowed  # noqa: E402
from links import LINK_MAX_AGE_DAYS  # noqa: E402

DEMO_FORMULARE = ["pva_pal080", "oegk_fahrtkosten_wien", "antrag_reha_kur", "antrag_ahv_reha_unfall",
                  "fsw_antrag_foerderung", "fsw_einrichtungswunsch", "fsw_bedarfsmeldung_wg"]

# Suche ist einsprachig Deutsch (ARCHITEKTUR §1/§6): System 1 übersetzt + schreibt in Fachbegriffe um.
# Jeder Fall wird zweimal geprüft: (a) rohe Alltagsfrage, (b) mit den Fachbegriffen der Umschreibung (begriffe=…).
# (Frage, Fachbegriffe der Umschreibung, erwartete Leistungen – eine reicht, Top-N)
GOLDEN = [
    ("Mama packt's nicht mehr allein", ["Pflegegeld", "mobile Pflege"], {"pflegegeld", "mobile_pflege_fsw"}, 5),
    ("Meine Mama packt's nimma allein daham, was kann ich tun?", ["Pflegegeld", "Heimhilfe", "Pflegeberatung"],
     {"pflegegeld", "mobile_pflege_fsw", "heimhilfe_wien", "fsw_pflegeberatung", "pflegeberatung"}, 5),
    ("Meine Mutter braucht jetzt Hilfe, was muss ich machen?", ["Pflegegeld", "Pflegeberatung"],
     {"pflegegeld", "mobile_pflege_fsw", "pflegeberatung", "fsw_pflegeberatung"}, 5),
    ("Taxi zur Bestrahlung", ["Krankentransport", "Fahrtkostenzuschuss"], {"krankentransport", "fahrtkostenzuschuss"}, 5),
    ("Wer zahlt das Taxi zur Bestrahlung?", ["Krankentransport", "Fahrtkosten"], {"fahrtkostenzuschuss", "krankentransport"}, 5),
    ("Zahnspange Kind", ["Kieferorthopädie"], {"zahnspange_kfo"}, 3),
    ("Mein Bub braucht vielleicht eine Zahnspange", ["Kieferorthopädie", "Gratis-Zahnspange"], {"zahnspange_kfo"}, 5),
    ("mehr bewegen", ["Bewegung", "Gesundheitsförderung"], {"bewegt_im_park"}, 5),
    ("Ich will was für meine Gesundheit tun, mich mehr bewegen", ["Gesundheitsförderung", "Bewegung"],
     {"bewegt_im_park", "gesundheitshunderter_svs", "vorsorgeuntersuchung"}, 5),
    ("Pflegegeld beantragen", ["Pflegegeld", "Antrag"], {"pflegegeld"}, 1),
    ("Rezeptgebühr zu teuer, kleine Pension", ["Rezeptgebührenbefreiung"], {"rezeptgebuehrenbefreiung"}, 3),
    ("Die Medikamente sind so teuer, die Mama hat nur eine kleine Pension", ["Rezeptgebührenbefreiung", "Ausgleichszulage"],
     {"rezeptgebuehrenbefreiung"}, 5),
    ("nach dem Spital wieder fit werden, Erholung", ["Rehabilitation", "Kur"], {"reha_onkologisch", "reha_medizinisch", "kur"}, 5),
    ("Ich muss mir frei nehmen um die Mama zu pflegen", ["Pflegekarenz", "Pflegeteilzeit"], {"pflegekarenz", "familienhospizkarenz"}, 5),
]


def run(db: Path = DB_PATH, golden=True) -> list[dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rep = json.loads(con.execute("SELECT value FROM meta WHERE key='report'").fetchone()[0])
    res = []

    def gate(name, ok, detail, hart=True):
        res.append({"gate": name, "ok": bool(ok), "hart": hart, "detail": detail})

    # 1 Schema + Pflichtdateien
    errs = {s: q["errors"] for s, q in rep["quellen"].items() if q["errors"]}
    gate("schema_fehlerfrei", not errs and not rep.get("seed_fehler"), errs or "0 Fehler")
    miss = {s: [k for k in ("source_md", "manifest") if not q.get(k)] for s, q in rep["quellen"].items()
            if q["status"] != "leer" and not (q.get("source_md") and q.get("manifest"))}
    gate("source_md_und_manifest", not miss, miss or "alle vorhanden")
    leer = [s for s, q in rep["quellen"].items() if q["status"] == "leer"]
    gate("keine_leeren_quellen", not leer, leer or "keine", hart=False)

    # 2 Golden Queries (Hybrid, wenn Embeddings da)
    if golden:
        from search import Lotse
        L = Lotse(db, log_misses=False)
        for q, begriffe, exp, n in GOLDEN:
            for variante, bg in (("a roh", None), ("b umgeschrieben", begriffe)):
                got = [x["leistung_id"] for x in L.search(q, limit=n, begriffe=bg)["leistungen"]]
                gate(f"golden ({variante}): {q}", bool(set(got[:n]) & exp),
                     {"erwartet": sorted(exp), "begriffe": bg, f"top{n}": got[:n], "modus": L.mode})

    # 3 Live-Links
    nlinks = con.execute("SELECT count(*) FROM links").fetchone()[0] if con.execute(
        "SELECT name FROM sqlite_master WHERE name='links'").fetchone() else 0
    fresh = f"l.ok AND l.last_ok_at IS NOT NULL AND julianday('now') - julianday(l.last_ok_at) < {LINK_MAX_AGE_DAYS}"
    if not nlinks:
        gate("links_demo_formulare_100", False, "Linkcheck nicht gelaufen (links-Tabelle leer)")
        gate("links_formulare_95", False, "Linkcheck nicht gelaufen")
    else:
        demo = {r["formular_id"]: r["ok"] for r in con.execute(
            f"SELECT f.formular_id, ({fresh}) AS ok FROM formulare f LEFT JOIN links l ON l.url=f.url_pdf OR l.final_url=f.url_pdf "
            f"WHERE f.formular_id IN ({','.join('?' * len(DEMO_FORMULARE))})", DEMO_FORMULARE)}
        ok_demo = [f for f in DEMO_FORMULARE if demo.get(f)]
        # Ausnahme: kein öffentliches PDF beim Träger (kb-links url_status=keine_url) + lokale Kopie + Elternseite live
        fallback = [r[0] for r in con.execute(
            f"SELECT f.formular_id FROM formulare f JOIN links l ON l.url=f.quelle_url AND {fresh} "
            f"WHERE f.url_status IN ('keine_url','ersetzt_b') AND f.local_pdf IS NOT NULL AND f.formular_id IN ({','.join('?' * len(DEMO_FORMULARE))})",
            DEMO_FORMULARE)]
        fehlt = [f for f in DEMO_FORMULARE if f not in ok_demo and f not in fallback]
        gate("links_demo_formulare_100", not fehlt,
             {"live": f"{len(ok_demo)}/{len(DEMO_FORMULARE)}", "fallback_lokal+elternseite": fallback, "fehlt": fehlt})
        tot, ok = con.execute(
            f"SELECT count(DISTINCT f.formular_id), count(DISTINCT CASE WHEN {fresh} THEN f.formular_id END) FROM formulare f "
            "LEFT JOIN links l ON l.url=f.url_pdf OR l.final_url=f.url_pdf "
            "WHERE f.url_pdf IS NOT NULL AND coalesce(f.art,'') NOT IN ('tarif_vertrag','video','info_seite')").fetchone()
        quote = ok / tot if tot else 0
        gate("links_formulare_95", quote >= 0.95, f"{ok}/{tot} = {quote:.0%}")

    # 4 Leistung ohne Quelle, ICD-Hint-Policy
    ohne = [r[0] for r in con.execute("SELECT leistung_id, data_json FROM leistungen")
            if not json.loads(r[1]).get("quellen")]
    gate("leistung_hat_quelle", not ohne, ohne[:20] or "alle mit Quelle")
    bad = []
    for r in con.execute("SELECT code, leistung_hints FROM codes WHERE system='ICD-10-AT' AND leistung_hints!='[]'"):
        for hnt in json.loads(r[1]):
            pol = HINT_POLICY_ICD.get(hnt)
            if pol and not hint_allowed(r[0], pol):
                bad.append(f"{r[0]}→{hnt}")
    gate("icd_hint_policy", not bad, bad[:20] or f"ok (vom Build entfernt: {rep.get('codes', {}).get('hints_durch_policy_entfernt', 0)})")
    con.close()
    return res


def summary(res) -> tuple[bool, str]:
    hard_fail = [r for r in res if r["hart"] and not r["ok"]]
    lines = [f"  {'✓' if r['ok'] else ('✗' if r['hart'] else '!')} {r['gate']}: {r['detail']}" for r in res]
    return not hard_fail, "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DB_PATH)
    a = ap.parse_args()
    r = run(a.db)
    ok, txt = summary(r)
    print(txt)
    sys.exit(0 if ok else 1)
