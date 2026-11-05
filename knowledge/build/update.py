#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["fastembed>=0.4", "sqlite-vec==0.1.9", "numpy"]
# ///
"""„Hält die Daten am Stand" – EINE Pipeline (ARCHITEKTUR §7):

    uv run knowledge/build/update.py                    # 1 Ingest → 2 Build (.new) → 3 Linkcheck → 4 Gates → 5 atomarer Swap → Bericht
    uv run knowledge/build/update.py --skip-ingest      # nur 2–5 (z. B. nachdem Sessions neu geliefert haben)
    uv run knowledge/build/update.py --sources oegk,fsw
    uv run knowledge/build/update.py --links-only       # nur Linkcheck + Gates auf aktueller DB (täglicher Lauf)
    --force  tauscht auch bei roten Gates (Gates stehen dann in meta.gates und im Bericht)

1 sources/*/ingest.py parallel (je Quelle ein Host), inkrementell über manifest.json (--since manifest, wenn unterstützt).
  Schlägt eine Quelle fehl, bleibt ihr letzter out/-Stand (degradiert statt leer). sources/elga wird nie geladen.
2 build_db → lotse.sqlite.new (Validierung, Taxonomie-Merge, Embeddings aus Cache + Delta, FTS, Graph)
3 build/linkcheck.py (falls vorhanden) → build/links/*.jsonl → Tabelle links
4 gates.py (§6) – rot ⇒ kein Swap, alte DB bleibt live
5 os.replace(.new → lotse.sqlite) – die laufende API lädt beim nächsten Request neu (mtime)
Danach: changes/<ts>.md + LATEST.md, review_queue.jsonl (neue Kandidaten, Änderungen, Konflikte, neue Formularversionen).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, DB_PATH, ROOT, SOURCES, STATE_DIR, rel  # noqa: E402
import build_db  # noqa: E402
import gates  # noqa: E402
import links as linkmod  # noqa: E402

CHANGES = STATE_DIR / "changes"
LOGS = STATE_DIR / "logs"
QUEUE = STATE_DIR / "review_queue.jsonl"
LINKCHECK_BUDGET_MIN = 15  # linkcheck.py prüft nur Links älter als 20 h; Rest im nächsten Lauf


def run_ingest(src: Path, ts: str, timeout: int, extra: list[str]):
    log = LOGS / ts / f"{src.name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        p = subprocess.run(["uv", "run", "-q", str(src / "ingest.py"), *extra], cwd=ROOT, capture_output=True,
                           text=True, timeout=timeout)
        log.write_text(p.stdout + "\n--- stderr ---\n" + p.stderr, encoding="utf-8")
        status = "ok" if p.returncode == 0 else f"fehler (exit {p.returncode})"
    except subprocess.TimeoutExpired:
        status = f"timeout nach {timeout}s"
    except FileNotFoundError as e:
        status = f"fehler ({e})"
    return src.name, status, round(time.time() - t0, 1), rel(log)


def diff(old: dict, new: dict) -> dict:
    out = {"documents": {}, "leistungen": {"neu": [], "geaendert": [], "entfernt": [], "status": []},
           "stellen": {}, "formulare": {}}
    srcs = set(old.get("documents", {})) | set(new.get("documents", {}))
    for s in sorted(srcs):
        o, n = old.get("documents", {}).get(s, {}), new.get("documents", {}).get(s, {})
        d = {"neu": sorted(set(n) - set(o)), "entfernt": sorted(set(o) - set(n)),
             "geaendert": sorted(k for k in set(o) & set(n) if o[k] != n[k])}
        if any(d.values()):
            out["documents"][s] = {k: len(v) for k, v in d.items()} | {"beispiele": {k: v[:5] for k, v in d.items() if v}}
    ol, nl = old.get("leistungen", {}), new.get("leistungen", {})
    for lid in sorted(set(nl) - set(ol)):
        out["leistungen"]["neu"].append({"leistung_id": lid, **nl[lid]})
    for lid in sorted(set(ol) - set(nl)):
        out["leistungen"]["entfernt"].append({"leistung_id": lid, **ol[lid]})
    for lid in sorted(set(ol) & set(nl)):
        if ol[lid]["hash"] != nl[lid]["hash"]:
            out["leistungen"]["geaendert"].append({"leistung_id": lid, "name": nl[lid].get("name"),
                                                   "quellen_vorher": ol[lid]["sources"], "quellen_jetzt": nl[lid]["sources"]})
        if ol[lid]["status"] != nl[lid]["status"]:
            out["leistungen"]["status"].append({"leistung_id": lid, "von": ol[lid]["status"], "nach": nl[lid]["status"]})
    for k in ("stellen", "formulare"):
        o, n = old.get(k, {}), new.get(k, {})
        out[k] = {"neu": len(set(n) - set(o)), "entfernt": len(set(o) - set(n)),
                  "geaendert": sum(1 for x in set(o) & set(n) if o[x] != n[x])}
        if k == "formulare":
            out["formulare_geaendert"] = sorted(x for x in set(o) & set(n) if o[x] != n[x])
    return out


def update_queue(d: dict, report: dict, ts: str):
    existing = set()
    if QUEUE.exists():
        for ln in QUEUE.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(ln)
                if e.get("status") == "offen":
                    existing.add((e["leistung_id"], e["grund"]))
            except json.JSONDecodeError:
                pass
    items = []
    for x in d["leistungen"]["neu"]:
        if x.get("status") == "kandidat":
            items.append((x["leistung_id"], "neuer Kandidat aus Quelle(n) " + ",".join(x["sources"])))
    for x in d["leistungen"]["geaendert"]:
        items.append((x["leistung_id"], "Inhalt geändert"))
    for lid, c in report["leistungen"]["konflikte"].items():
        items.append((lid, "Konflikt: " + "; ".join(c)))
    for a in report["leistungen"]["alias_vorschlaege"]:
        items.append((a["kandidat"], f"Taxonomie? evtl. Variante/teil_von '{a['seed']}' → taxonomie.json"))
    for fid in d.get("formulare_geaendert", []):
        items.append((fid, "Formular geändert (neue Version?) → Feld-Mapping B5 prüfen"))
    n = 0
    with QUEUE.open("a", encoding="utf-8") as fh:
        for lid, grund in items:
            if (lid, grund) in existing:
                continue
            fh.write(json.dumps({"ts": ts, "leistung_id": lid, "grund": grund, "status": "offen"}, ensure_ascii=False) + "\n")
            n += 1
    return n


def write_md(path: Path, ts, ingest, d, report, n_queue, gate_res=None, swapped=True):
    L = [f"# Änderungsbericht Wissens-DB – {ts}", "",
         f"**Swap:** {'ja – lotse.sqlite ist neu' if swapped else 'NEIN – Gates rot, alte DB bleibt aktiv'}  ",
         f"**Links:** {report.get('links')}  ",
         f"**Embeddings:** {(report.get('embeddings') or {}).get('modell')} "
         f"(neu {(report.get('embeddings') or {}).get('neu_berechnet')}, Cache {(report.get('embeddings') or {}).get('aus_cache')})", ""]
    if gate_res:
        L += ["## Gates", ""] + [f"- {'✓' if g['ok'] else ('✗' if g['hart'] else '!')} **{g['gate']}**: {g['detail']}" for g in gate_res] + [""]
    if ingest:
        L += ["## Ingestion", "| Quelle | Status | Dauer | Log |", "|---|---|---|---|"]
        L += [f"| {s} | {st} | {dur}s | `{log}` |" for s, st, dur, log in ingest] + [""]
    if report.get("uebersprungen"):
        L += [f"Übersprungen: {report['uebersprungen']}", ""]
    L += ["## Quellen im Build", "| Quelle | Status | Dok. | Leist. | Stellen | Form. | Fehler | Warn. |", "|---|---|---|---|---|---|---|---|"]
    for s, q in report["quellen"].items():
        L.append(f"| {s} | {q['status']} | {q['documents']} | {q['leistungen']} | {q['stellen']} | {q['formulare']} | {q['errors']} | {q['warnings']} |")
    L += ["", "## Dokumente (neu / geändert / entfernt)"]
    L += [f"- **{s}**: +{x['neu']} / ~{x['geaendert']} / −{x['entfernt']}" for s, x in d["documents"].items()] or ["- keine Änderungen"]
    ld = d["leistungen"]
    L += ["", "## Leistungsgraph",
          f"- neu: {len(ld['neu'])} " + ", ".join(x["leistung_id"] for x in ld["neu"][:30]),
          f"- geändert: {len(ld['geaendert'])} " + ", ".join(x["leistung_id"] for x in ld["geaendert"][:30]),
          f"- entfernt: {len(ld['entfernt'])} " + ", ".join(x["leistung_id"] for x in ld["entfernt"]),
          f"- Statuswechsel: " + ", ".join(f"{x['leistung_id']} {x['von']}→{x['nach']}" for x in ld["status"]),
          f"- Konflikte: " + "; ".join(f"{k}: {v}" for k, v in report["leistungen"]["konflikte"].items()),
          f"- Stellen: {d['stellen']}  Formulare: {d['formulare']} (geänderte Formulare = neue Version → Feld-Mapping B5 prüfen)",
          "", f"**{n_queue} neue Einträge in `review_queue.jsonl`.**"]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def run_linkcheck(ts: str, timeout: int):
    """kb-links-Reihenfolge (links/REPORT.md §7): linkcheck.py → formulare_live.py → report.py."""
    L = BUILD / "links"
    steps = [(L / "linkcheck.py", ["--with", "httpx,pypdf"], ["--budget-min", str(LINKCHECK_BUDGET_MIN)]),
             (L / "formulare_live.py", ["--with", "pypdf"], []),
             (L / "report.py", [], [])]
    if not steps[0][0].exists():
        return {"status": "übersprungen (links/linkcheck.py fehlt – vorhandene links/*.jsonl werden geladen)"}
    log = LOGS / ts / "linkcheck.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    out = []
    for script, uvargs, args in steps:
        if not script.exists():
            continue
        try:
            p = subprocess.run(["uv", "run", "-q", "--python", "3.12", *uvargs, "python", str(script), *args], cwd=ROOT,
                               capture_output=True, text=True, timeout=timeout)
            out.append(f"## {script.name} exit {p.returncode}\n{p.stdout[-4000:]}\n--- stderr ---\n{p.stderr[-4000:]}")
            if p.returncode != 0:
                log.write_text("\n".join(out), encoding="utf-8")
                return {"status": f"fehler in {script.name} (exit {p.returncode})", "log": rel(log)}
        except subprocess.TimeoutExpired:
            return {"status": f"timeout in {script.name} nach {timeout}s"}
    log.write_text("\n".join(out), encoding="utf-8")
    return {"status": "ok", "log": rel(log)}


def merge_links_queue(ts: str) -> int:
    """links/review_queue.jsonl (neue Formularversionen, tote Links ohne Ersatz …) in die zentrale Queue übernehmen."""
    src = BUILD / "links" / "review_queue.jsonl"
    if not src.exists():
        return 0
    have = set(QUEUE.read_text(encoding="utf-8").splitlines()) if QUEUE.exists() else set()
    keys = {json.loads(x).get("links_key") for x in have if x.strip().startswith("{") and "links_key" in x}
    n = 0
    with QUEUE.open("a", encoding="utf-8") as fh:
        for ln in src.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            e = json.loads(ln)
            key = f"{e.get('typ')}|{e.get('formular_id')}|{e.get('sha256') or e.get('url') or ''}"
            if key in keys:
                continue
            fh.write(json.dumps({"ts": ts, "leistung_id": None, "formular_id": e.get("formular_id"),
                                 "grund": f"links: {e.get('typ')}", "status": "offen", "links_key": key, "detail": e},
                                ensure_ascii=False) + "\n")
            keys.add(key)
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="Ingest → Build → Linkcheck → Gates → atomarer Swap → Bericht")
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--sources", "--only", dest="only", help="Komma-Liste von source_ids für den Ingest")
    ap.add_argument("--links-only", action="store_true", help="nur Linkcheck + Gates auf der aktuellen DB")
    ap.add_argument("--force", action="store_true", help="auch bei roten Gates tauschen (Gates stehen dann in meta/Bericht)")
    ap.add_argument("--no-embeddings", action="store_true")
    ap.add_argument("--no-linkcheck", action="store_true", help="Linkcheck nicht starten, nur vorhandene build/links/*.jsonl laden")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    snap = STATE_DIR / "snapshot.json"
    old = json.loads(snap.read_text(encoding="utf-8")) if snap.exists() else {}
    (STATE_DIR / "snapshots").mkdir(parents=True, exist_ok=True)
    if snap.exists():
        shutil.copy(snap, STATE_DIR / "snapshots" / f"{ts}_vorher.json")

    ingest = []
    if not a.skip_ingest and not a.links_only:
        only = set(a.only.split(",")) if a.only else None
        srcs = [d for d in sorted(SOURCES.iterdir()) if d.is_dir() and d.name not in build_db.SKIP_SOURCES
                and (d / "ingest.py").exists() and (not only or d.name in only)]
        print(f"[1/5] Ingest: {', '.join(s.name for s in srcs)}")

        def one(s):
            extra = ["--since", "manifest"] if "--since" in (s / "ingest.py").read_text(encoding="utf-8", errors="ignore") else []
            return run_ingest(s, ts, a.timeout, extra)
        with ThreadPoolExecutor(max_workers=a.parallel) as ex:
            ingest = list(ex.map(one, srcs))
        for s, st, dur, log in ingest:
            print(f"  {s:22} {st:22} {dur:7}s  {log}")

    if a.links_only:
        new = DB_PATH.with_suffix(".sqlite.new")
        shutil.copy(DB_PATH, new)
        report = json.loads(sqlite3.connect(DB_PATH).execute("SELECT value FROM meta WHERE key='report'").fetchone()[0])
    else:
        print("[2/5] Build → lotse.sqlite.new")
        report = build_db.build(DB_PATH, quiet=True, swap=False, embeddings=False if a.no_embeddings else None)
        new = Path(report["_new_path"])
    print("[3/5] Linkcheck")
    lc = {"status": "übersprungen (--no-linkcheck), vorhandene links.jsonl geladen"} if a.no_linkcheck else run_linkcheck(ts, a.timeout)
    con = sqlite3.connect(new)
    report["links"] = linkmod.load_links(con)
    report["linkcheck"] = lc
    con.execute("INSERT OR REPLACE INTO meta VALUES ('report', ?)", (json.dumps(
        {k: v for k, v in report.items() if not k.startswith("_")}, ensure_ascii=False),))
    con.commit()
    con.close()
    print(f"  {lc['status']}  links={report['links']}")

    print("[4/5] Gates")
    res = gates.run(new)
    ok, txt = gates.summary(res)
    print(txt)
    con = sqlite3.connect(new)
    con.execute("INSERT OR REPLACE INTO meta VALUES ('gates', ?)", (json.dumps(res, ensure_ascii=False),))
    con.commit()
    con.close()
    report["gates"] = res
    if not ok and not a.force:
        print(f"\n✗ Gates rot → KEIN Swap. Kandidat liegt in {rel(new)}; laufende API nutzt weiter die alte DB.")
        swapped = False
    else:
        print("[5/5] Swap lotse.sqlite.new → lotse.sqlite" + (" (FORCE trotz roter Gates)" if not ok else ""))
        snapshot = report.get("_snapshot")
        build_db.finalize(new, DB_PATH, report, quiet=True)
        if not snapshot:  # links-only: Snapshot unverändert
            snapshot = old
        swapped = True
    new_snap = json.loads(snap.read_text(encoding="utf-8")) if swapped else report.get("_snapshot", old)
    d = diff(old, new_snap) if new_snap else diff(old, old)
    n_queue = (update_queue(d, report, ts) + merge_links_queue(ts)) if swapped else 0
    CHANGES.mkdir(exist_ok=True)
    (CHANGES / f"{ts}.json").write_text(json.dumps({"ts": ts, "ingest": ingest, "diff": d, "gates": res, "swap": swapped,
                                                    "links": report.get("links")}, ensure_ascii=False, indent=1, default=str),
                                        encoding="utf-8")
    write_md(CHANGES / f"{ts}.md", ts, ingest, d, report, n_queue, res, swapped)
    shutil.copy(CHANGES / f"{ts}.md", CHANGES / "LATEST.md")
    print(f"\nÄnderungsbericht: {rel(CHANGES / f'{ts}.md')}   Review-Queue +{n_queue}   Swap: {swapped}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
