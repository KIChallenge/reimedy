#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["fastembed>=0.4", "sqlite-vec==0.1.9", "numpy"]
# ///
"""Baut knowledge/build/lotse.sqlite aus knowledge/sources/*/out/*.jsonl + kuratiertem Seed.

    uv run --python 3.12 knowledge/build/build_db.py [--strict] [--db PFAD] [--sources PFAD]

- validiert jede Quelle gegen CONTRACT.md (Fehler → Zeile verworfen, Warnung → übernommen), Bericht pro Quelle
- documents + FTS5 (Umlaut-Normalisierung ä→ae…, Diakritika weg, Präfix-/Stamm-Suche)
- Leistungsgraph: Seed (kuratiert) + Kandidaten aller Quellen, Merge nach leistung_id über taxonomie.json.
  Jede Einzelaussage bleibt als „claim" mit Quelle + Stand erhalten; Widersprüche (z. B. andere Beträge)
  werden als Konflikt markiert und NICHT still überschrieben.
- stellen, formulare, kanten (setzt_voraus, antrag_formular, zustaendige_stelle)
- snapshot.json (Hash je Datensatz) für den Änderungsbericht in update.py
Nur stdlib (sqlite3 mit FTS5).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BUILD, CONF_RANK, DB_PATH, SOURCES, Problems, code_norm, jdump, norm, numbers, read_jsonl)  # noqa: E402
from taxonomy import Taxonomie  # noqa: E402
import links as linkmod  # noqa: E402
import embed  # noqa: E402

SEED_FILES = {"leistungen": BUILD / "seed_leistungen.jsonl", "stellen": BUILD / "seed_stellen.jsonl",
              "formulare": BUILD / "seed_formulare.jsonl"}
# Nicht als Wissensquelle laden (ARCHITEKTUR §2): ELGA = Personendaten → Vault (server/elga, B6); sources/elga = nur Fixtures.
SKIP_SOURCES = {"elga"}
SOURCE_TRAEGER = {"oegk": "ÖGK", "svs": "SVS", "bvaeb": "BVAEB", "pva": "PVA"}

SCALAR = ["name", "kurz_einfach", "zielgruppe", "zustaendig", "kosten", "innerhalb_sv", "antrag", "confidence"]
LISTS = ["bereich", "traeger", "unterlagen", "fristen", "abhaengigkeiten", "trigger_im_dokument", "bundesland"]
# Felder, in denen abweichende Zahlen ein echter Widerspruch sind (Beträge, Stunden, Grenzen)
HARD_NUM_FIELDS = {"kosten", "zustaendig"}

SCHEMA = """
PRAGMA journal_mode=OFF;
CREATE TABLE quellen(source_id TEXT PRIMARY KEY, status TEXT, fetched_at TEXT, has_source_md INT,
  n_documents INT, n_leistungen INT, n_stellen INT, n_formulare INT, n_errors INT, n_warnings INT,
  errors_json TEXT, manifest_json TEXT);
CREATE TABLE documents(rid INTEGER PRIMARY KEY, id TEXT UNIQUE, source_id TEXT, url TEXT, title TEXT, section TEXT,
  text TEXT, lang TEXT, traeger TEXT, bundesland TEXT, bereich TEXT, doc_type TEXT, valid_from TEXT,
  fetched_at TEXT, sha256 TEXT, license_note TEXT);
CREATE VIRTUAL TABLE documents_fts USING fts5(title, section, body, tokenize="unicode61 remove_diacritics 2");
CREATE TABLE leistung_claims(leistung_id TEXT, raw_leistung_id TEXT, source_id TEXT, origin TEXT, field TEXT,
  value_json TEXT, quelle_url TEXT, stand TEXT, confidence TEXT);
CREATE INDEX lc_id ON leistung_claims(leistung_id);
CREATE TABLE leistungen(leistung_id TEXT PRIMARY KEY, name TEXT, kurz_einfach TEXT, bereich TEXT, traeger TEXT,
  innerhalb_sv INT, bundesland TEXT, data_json TEXT, sources TEXT, n_sources INT, review_status TEXT,
  conflicts_json TEXT, stand TEXT);
CREATE VIRTUAL TABLE leistungen_fts USING fts5(leistung_id UNINDEXED, name, body, tokenize="unicode61 remove_diacritics 2");
CREATE TABLE stellen(stelle_id TEXT PRIMARY KEY, name TEXT, typ TEXT, adresse TEXT, plz TEXT, bundesland TEXT,
  telefon TEXT, email TEXT, url TEXT, oeffnungszeiten TEXT, zustaendig_fuer TEXT, lat REAL, lon REAL,
  quelle_url TEXT, source_id TEXT, stand TEXT, variants_json TEXT);
CREATE TABLE formulare(formular_id TEXT PRIMARY KEY, name TEXT, traeger TEXT, url_pdf TEXT, local_pdf TEXT,
  fillable INT, felder_json TEXT, leistung_ids TEXT, wer_fuellt_aus TEXT, quelle_url TEXT, source_id TEXT,
  stand TEXT, variants_json TEXT, art TEXT, sha256 TEXT, version TEXT, gefunden_auf TEXT, live INT, zeigen INT, url_status TEXT);
CREATE TABLE kanten(von TEXT, nach TEXT, typ TEXT, source_id TEXT, dangling INT);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE codes(system TEXT, code TEXT, label_de TEXT, label_einfach TEXT, parent TEXT, leistung_hints TEXT,
  hints_entfernt TEXT, quelle_url TEXT, stand TEXT, source_id TEXT, data_json TEXT, PRIMARY KEY(system, code));
CREATE INDEX codes_parent ON codes(system, parent);
CREATE VIRTUAL TABLE codes_fts USING fts5(system UNINDEXED, code, label, tokenize="unicode61 remove_diacritics 2");
CREATE TABLE extras(source_id TEXT, file TEXT, leistung_id TEXT, data_json TEXT);
CREATE INDEX ex_lid ON extras(leistung_id);
"""


def h(obj) -> str:
    return hashlib.sha1(jdump(obj).encode()).hexdigest()[:12]


def load_source(src_dir: Path):
    sid = src_dir.name
    p = Problems()
    out = src_dir / "out"
    data = {k: read_jsonl(out / f"{k}.jsonl", k, p, sid) for k in ("documents", "leistungen", "stellen", "formulare", "codes")}
    for k, recs in list(data.items()):
        for r in recs:
            if k == "documents" and r.get("source_id") not in (None, sid):
                p.warn(f"{sid}/documents: source_id '{r.get('source_id')}' ≠ Ordner '{sid}' – Ordner gewinnt")
            r["_source_id"] = sid
    # Nicht im Vertrag, aber nützlich (z. B. sozdok_ris/leistung_rechtsgrundlagen.jsonl, programm_regeln.jsonl):
    # generisch als „extras" laden, an leistung_id hängen, nicht validieren.
    extras = []
    for f in sorted(out.glob("*.jsonl")) if out.exists() else []:
        if f.stem in ("documents", "leistungen", "stellen", "formulare", "codes"):
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                extras.append((sid, f.name, rec.get("leistung_id") if isinstance(rec, dict) else None, jdump(rec)))
            except json.JSONDecodeError:
                p.warn(f"{sid}/{f.name}:{n}: kein gültiges JSON (extra-Datei)")
    if extras:
        p.warn(f"{sid}: {len(extras)} Zeilen aus Nicht-Vertragsdateien als 'extras' geladen")
    data["_extras"] = extras
    manifest = None
    mf = out / "manifest.json"
    if mf.exists():
        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            p.err(f"{sid}/manifest.json: ungültiges JSON ({e.msg})")
    else:
        p.warn(f"{sid}: out/manifest.json fehlt → kein inkrementelles Update möglich")
    if not (src_dir / "SOURCE.md").exists():
        p.warn(f"{sid}: SOURCE.md fehlt")
    if not (src_dir / "ingest.py").exists():
        p.warn(f"{sid}: ingest.py fehlt → nicht automatisch aktualisierbar")
    n = sum(len(v) for k, v in data.items() if not k.startswith("_"))
    status = "leer" if n == 0 else ("fehlerhaft" if p.errors and n == 0 else ("ok" if not p.errors else "teilweise"))
    return sid, data, manifest, p, status


def load_seed():
    p = Problems()
    data = {"documents": []}
    for k, f in SEED_FILES.items():
        data[k] = read_jsonl(f, k, p, "seed")
        for r in data[k]:
            r["_source_id"] = "seed"
    return data, p


def stand_of(rec, sid):
    qs = rec.get("quellen") or []
    stands = [q.get("stand") for q in qs if isinstance(q, dict) and q.get("stand")]
    return max(stands) if stands else rec.get("fetched_at")


# --------------------------------------------------------------------------- Merge Leistungen
def merge_leistungen(cands: list[dict], tax: Taxonomie):
    """cands: Schema-B-Datensätze aus Seed und Quellen. Gibt (merged, claims, alias_vorschlaege) zurück.
    Träger-Ausprägungen (z. B. unterstuetzungsfonds_bvaeb) fließen NICHT in die Basiswerte, sondern nach
    traeger_auspraegungen[TRÄGER] – sonst gäbe es Schein-Konflikte zwischen Trägern."""
    by_id = defaultdict(list)
    claims = []
    for r in cands:
        raw = r["leistung_id"]
        lid, aus = tax.resolve(raw)
        # Träger-Quelle (svs/bvaeb/pva/oegk) zu einer Mehr-Träger-Leistung, Träger ≠ Haupt-Träger laut Taxonomie
        # → Ausprägung dieses Trägers statt Basiswert (sonst Schein-Konflikte zwischen Trägern).
        tr = SOURCE_TRAEGER.get(r["_source_id"])
        e = tax.entries.get(lid)
        if not aus and tr and e and len(e.get("traeger") or []) > 1 and tr in e["traeger"] and tr != e["traeger"][0]:
            aus = tr
        r["_raw_id"] = raw
        r["_auspraegung"] = aus
        by_id[lid].append(r)
    seed_ids = {lid for lid, rs in by_id.items() if any(x["_source_id"] == "seed" for x in rs)} | set(tax.entries)

    merged = {}
    for lid, rs in by_id.items():
        # Priorität: kuratiert (Seed) > Confidence > neuester Stand
        def prio(r):
            return (r["_source_id"] == "seed", CONF_RANK.get(r.get("confidence"), 0), stand_of(r, r["_source_id"]) or "")
        rs.sort(key=prio, reverse=True)
        out = {"leistung_id": lid, **tax.info(lid)}
        conflicts = []
        aus_rs = [r for r in rs if r.get("_auspraegung")]
        all_rs = rs
        rs = [r for r in rs if not r.get("_auspraegung")] or rs
        if aus_rs:
            out["traeger_auspraegungen"] = defaultdict(list)
            for r in aus_rs:
                out["traeger_auspraegungen"][r["_auspraegung"]].append(
                    {k: r.get(k) for k in ("name", "kurz_einfach", "zielgruppe", "voraussetzungen", "zustaendig", "kosten",
                                           "antrag", "unterlagen", "fristen", "quellen", "confidence") if r.get(k)}
                    | {"source_id": r["_source_id"], "raw_id": r["_raw_id"]})
            out["traeger_auspraegungen"] = dict(out["traeger_auspraegungen"])
        for f in SCALAR:
            variants = []
            for r in rs:
                v = r.get(f)
                if v in (None, "", {}, []):
                    continue
                variants.append({"value": v, "source_id": r["_source_id"], "stand": stand_of(r, r["_source_id"]),
                                 "quelle_url": (r.get("quellen") or [{}])[0].get("url") if isinstance((r.get("quellen") or [{}])[0], dict) else None})
            if not variants:
                continue
            out[f] = variants[0]["value"]
            distinct = {jdump(v["value"]) if not isinstance(v["value"], str) else norm(v["value"]) for v in variants}
            if len(distinct) > 1:
                out.setdefault("_varianten", {})[f] = variants
                kind = None
                if f == "innerhalb_sv":
                    kind = "widerspruch"
                elif f == "antrag":
                    fids = {(v["value"] or {}).get("formular_id") for v in variants if isinstance(v["value"], dict)} - {None}
                    if len(fids) > 1:
                        kind = "widerspruch"
                elif f in HARD_NUM_FIELDS:
                    # Konflikt nur, wenn zwei Quellen Zahlen nennen und KEINE gemeinsam haben (z. B. 7,55 vs 7,70).
                    # Ergänzungen (Teilmenge/Überlappung) sind Varianten, kein Widerspruch. Jahreszahlen zählen nicht.
                    nums = [n for n in (numbers(v["value"]) - {y for y in numbers(v["value"]) if re.fullmatch(r"(19|20)\d\d", y)}
                                        for v in variants) if n]
                    if len(nums) > 1 and any(not (a & b) for i, a in enumerate(nums) for b in nums[i + 1:]):
                        kind = "zahlen_abweichend"
                if kind:
                    conflicts.append({"feld": f, "art": kind, "varianten": variants})
        # innerhalb_sv entscheidet die kuratierte Taxonomie (typ sv|land|bund|verein), Quellvarianten bleiben sichtbar
        te = tax.entries.get(lid)
        if te and te.get("typ"):
            out["innerhalb_sv"] = te["typ"] == "sv"
            for c in [c for c in conflicts if c["feld"] == "innerhalb_sv"]:
                conflicts.remove(c)
                out.setdefault("_entschieden", {})["innerhalb_sv"] = {"durch": "taxonomie", "typ": te["typ"], "varianten": c["varianten"]}
        for f in LISTS:
            seen, vals = {}, []
            for r in rs:
                for v in r.get(f) or []:
                    key = norm(v) if isinstance(v, str) else jdump(v)
                    if key not in seen:
                        seen[key] = {"value": v, "sources": [r["_source_id"]]}
                        vals.append(seen[key])
                    elif r["_source_id"] not in seen[key]["sources"]:
                        seen[key]["sources"].append(r["_source_id"])
            if vals:
                out[f] = [x["value"] for x in vals]
                out.setdefault("_herkunft", {})[f] = vals
        # Voraussetzungen: Union, je mit Quelle/Zitat; Zahlenwidersprüche zwischen Quellen sichtbar machen
        vor, seen = [], set()
        for r in rs:
            for v in r.get("voraussetzungen") or []:
                key = norm(v.get("text"))
                if key in seen:
                    continue
                seen.add(key)
                vor.append({**v, "source_id": r["_source_id"], "stand": stand_of(r, r["_source_id"])})
        if vor:
            out["voraussetzungen"] = vor
        q, seenq = [], set()
        for r in rs:
            for x in r.get("quellen") or []:
                x = x if isinstance(x, dict) else {"url": x}
                if x.get("url") in seenq:
                    continue
                seenq.add(x.get("url"))
                q.append({**x, "source_id": r["_source_id"]})
        out["quellen"] = q
        rs = all_rs
        srcs = sorted({r["_source_id"] for r in rs})
        out["_sources"] = srcs
        out["_raw_ids"] = sorted({r["_raw_id"] for r in rs})
        if conflicts:
            status = "konflikt"
        elif "seed" in srcs and len(srcs) > 1:
            status = "kuratiert+quellen"
        elif "seed" in srcs:
            status = "kuratiert"
        else:
            status = "kandidat"  # nur aus Ingestion → Mensch muss reviewen
        out["_review_status"] = status
        out["_conflicts"] = conflicts
        out["_stand"] = max([s for s in (stand_of(r, r["_source_id"]) for r in rs) if s] or [None]) if any(stand_of(r, r["_source_id"]) for r in rs) else None
        merged[lid] = out
        for r in rs:
            for f in SCALAR + LISTS + ["voraussetzungen"]:
                if r.get(f) not in (None, "", [], {}):
                    qurl = None
                    if r.get("quellen") and isinstance(r["quellen"][0], dict):
                        qurl = r["quellen"][0].get("url")
                    claims.append((lid, r["_raw_id"], r["_source_id"], "seed" if r["_source_id"] == "seed" else "ingest",
                                   f, jdump(r[f]), qurl, stand_of(r, r["_source_id"]), r.get("confidence")))

    # Alias-Vorschläge: Kandidat-IDs ohne Seed, deren Name/ID einem Seed-Eintrag ähnelt
    vorschlaege = []
    for lid in merged:
        if lid in seed_ids:
            continue
        tl = set(norm(lid.replace("_", " ")).split()) - {"wien", "oegk", "svs", "bvaeb", "fsw"}
        for sid_ in seed_ids & set(merged):
            ts_ = set(norm(sid_.replace("_", " ")).split()) - {"wien", "oegk", "svs", "bvaeb", "fsw"}
            if (tl and ts_ and (tl <= ts_ or ts_ <= tl)) or norm(merged[lid].get("name", "")) == norm(merged[sid_].get("name", "")):
                vorschlaege.append({"kandidat": lid, "seed": sid_})
    return merged, claims, vorschlaege


def merge_simple(recs, key):
    """Stellen/Formulare: nach ID zusammenführen, Seed/neuester gewinnt, Abweichungen als variants_json."""
    by = defaultdict(list)
    for r in recs:
        by[r[key]].append(r)
    out = {}
    for k, rs in by.items():
        rs.sort(key=lambda r: (r["_source_id"] != "seed", ), reverse=False)
        base = dict(rs[0])
        variants = []
        for r in rs[1:]:
            for f, v in r.items():
                if f.startswith("_"):
                    continue
                if base.get(f) in (None, "", [], {}) and v not in (None, "", [], {}):
                    base[f] = v  # Lücken auffüllen
                elif v not in (None, "", [], {}) and jdump(v) != jdump(base.get(f)):
                    variants.append({"feld": f, "value": v, "source_id": r["_source_id"]})
        base["_variants"] = variants
        base["_sources"] = sorted({r["_source_id"] for r in rs})
        out[k] = base
    return out


# --------------------------------------------------------------------------- Codes
def _icd_key(code):
    m = re.match(r"([A-Z])(\d\d)", code)
    return (m[1], int(m[2])) if m else None


def _in_ranges(code, ranges):
    k = _icd_key(code)
    if not k:
        return False
    for a, b in ranges:
        ka, kb = _icd_key(a), _icd_key(b)
        if ka <= k <= kb:
            return True
    return False


def hint_allowed(code, ranges):
    """Einzelcode muss im erlaubten Bereich liegen; Bereichscode (C00-D48) mit BEIDEN Enden."""
    ends = code.split("-")
    return all(_in_ranges(e, ranges) for e in ends if e)


# Welche ICD-Bereiche einen Leistungs-Hinweis überhaupt tragen dürfen (Hinweis von Session 02:
# D10–D36 gutartig, D37–D48 unsicher → KEIN onkologischer Reha-Kandidat; die Einordnung wäre schon medizinisch).
HINT_POLICY_ICD = {"reha_onkologisch": [("C00", "C97"), ("D00", "D09")]}


def load_codes(con, codes, tax, merged):
    by = {}
    removed, dangling = [], set()
    for r in codes:
        system, code = r["system"], code_norm(r["code"])
        hints, weg = [], []
        for h in r.get("leistung_hints") or []:
            h = tax.canon(h)
            pol = HINT_POLICY_ICD.get(h)
            if system == "ICD-10-AT" and pol and not hint_allowed(code, pol):
                weg.append(h)
                continue
            if h not in merged:
                dangling.add(h)
            hints.append(h)
        if weg:
            removed.append(f"{system}:{code}→{','.join(weg)}")
        key = (system, code)
        if key in by:  # gleicher Code aus zwei Quellen: Hints vereinigen, erster Label gewinnt
            by[key]["hints"] = sorted(set(by[key]["hints"]) | set(hints))
            continue
        extra = {k: v for k, v in r.items() if not k.startswith("_") and k not in
                 ("system", "code", "label_de", "label_einfach", "parent", "leistung_hints", "quelle_url", "stand")}
        by[key] = {"r": r, "code": code, "hints": hints, "weg": weg, "extra": extra}
    for (system, code), x in by.items():
        r = x["r"]
        con.execute("INSERT INTO codes VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            system, code, r["label_de"], r.get("label_einfach"), code_norm(r["parent"]) if r.get("parent") else None,
            jdump(x["hints"]), jdump(x["weg"]), r.get("quelle_url"), r.get("stand"), r["_source_id"], jdump(x["extra"])))
        con.execute("INSERT INTO codes_fts(system, code, label) VALUES (?,?,?)", (system, code, norm(r["label_de"])))
    per_sys = {}
    for (system, _), x in by.items():
        per_sys[system] = per_sys.get(system, 0) + 1
    return {"total": len(by), "nach_system": per_sys, "hints_durch_policy_entfernt": len(removed),
            "beispiele_entfernt": removed[:10], "hints_ohne_leistung_im_graph": sorted(dangling)}


# --------------------------------------------------------------------------- Build
def build(db_path: Path = DB_PATH, sources_dir: Path = SOURCES, strict=False, quiet=False, embeddings=None,
          swap=True, links_dir: Path | None = None):
    """Baut nach <db_path>.new. swap=True ersetzt db_path sofort (Tests/Einzelaufruf ohne Gates);
    update.py/CLI bauen mit swap=False, prüfen Gates und rufen dann finalize()."""
    tax = Taxonomie()
    links_dir = links_dir or linkmod.LINKS_DIR
    seed, seed_p = load_seed()
    loaded, skipped = [], []
    if sources_dir.exists():
        for d in sorted(x for x in sources_dir.iterdir() if x.is_dir() and not x.name.startswith((".", "_"))):
            if d.name in SKIP_SOURCES:
                skipped.append(d.name)
                continue
            loaded.append(load_source(d))

    if seed_p.errors:
        print("SEED-FEHLER:\n  " + "\n  ".join(seed_p.errors), file=sys.stderr)
        if strict:
            sys.exit(2)

    new = db_path.with_suffix(".sqlite.new")
    if new.exists():
        new.unlink()
    con = sqlite3.connect(new)
    con.executescript(SCHEMA)

    all_codes = []
    all_docs, all_leist, all_stellen, all_form = [], list(seed["leistungen"]), list(seed["stellen"]), list(seed["formulare"])
    report = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "quellen": {},
              "uebersprungen": {s: "keine Wissensquelle (Personendaten → Vault, ARCHITEKTUR §2)" for s in skipped},
              "seed": {k: len(v) for k, v in seed.items() if k != "documents"}, "taxonomie": len(tax.entries)}
    for sid, data, manifest, p, status in loaded:
        all_docs += data["documents"]
        all_leist += data["leistungen"]
        all_stellen += data["stellen"]
        all_form += data["formulare"]
        all_codes += data["codes"]
        con.executemany("INSERT INTO extras VALUES (?,?,?,?)",
                        [(a, b, tax.canon(c) if c else c, d) for a, b, c, d in data["_extras"]])
        con.execute("INSERT INTO quellen VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            sid, status, (manifest or {}).get("fetched_at"), int((sources_dir / sid / "SOURCE.md").exists()),
            len(data["documents"]), len(data["leistungen"]), len(data["stellen"]), len(data["formulare"]),
            len(p.errors), len(p.warnings), jdump({"errors": p.errors[:200], "warnings": p.warnings[:200]}),
            jdump(manifest) if manifest else None))
        report["quellen"][sid] = {"status": status, **{k.lstrip("_"): len(v) for k, v in data.items()},
                                  "errors": len(p.errors), "warnings": len(p.warnings),
                                  "source_md": (sources_dir / sid / "SOURCE.md").exists(), "manifest": manifest is not None,
                                  "ingest_py": (sources_dir / sid / "ingest.py").exists(),
                                  "beispiel_fehler": p.errors[:5], "beispiel_warnungen": p.warnings[:5]}
        if strict and p.errors:
            print(f"[{sid}] {len(p.errors)} Fehler (strict)", file=sys.stderr)
            sys.exit(2)

    # documents (+ Duplikat-Erkennung)
    seen_ids, seen_text, dup_ids, dup_text = set(), {}, 0, 0
    doc_rows = []
    for r in all_docs:
        sid = r["_source_id"]
        if r["id"] in seen_ids:
            dup_ids += 1
            continue
        seen_ids.add(r["id"])
        th = hashlib.sha1(norm(r["text"]).encode()).hexdigest()
        if th in seen_text and seen_text[th] != sid:
            dup_text += 1  # gleicher Text aus anderer Quelle → behalten (eigene Zitierbarkeit), nur zählen
        seen_text.setdefault(th, sid)
        cur = con.execute("INSERT INTO documents(id,source_id,url,title,section,text,lang,traeger,bundesland,bereich,doc_type,"
                          "valid_from,fetched_at,sha256,license_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                              r["id"], sid, r["url"], r.get("title"), r.get("section"), r["text"], r.get("lang", "de"),
                              jdump(r.get("traeger") or []), jdump(r.get("bundesland") or []), jdump(r.get("bereich") or []),
                              r.get("doc_type"), r.get("valid_from"), r.get("fetched_at"), r.get("sha256"), r.get("license_note")))
        con.execute("INSERT INTO documents_fts(rowid,title,section,body) VALUES (?,?,?,?)",
                    (cur.lastrowid, norm(r.get("title")), norm(r.get("section")), norm(r["text"])))
        doc_rows.append((cur.lastrowid, " – ".join(x for x in (r.get("title"), r.get("section")) if x) + "\n" + r["text"][:1500]))
    report["documents"] = {"total": len(seen_ids), "doppelte_ids_verworfen": dup_ids, "gleicher_text_mehrere_quellen": dup_text}

    # Formulare kanonisch: (1) formulare_live (Linkcheck, Live-URL) gewinnt, (2) sonst Dedupe über local_pdf/url_pdf,
    # Seed-ID bevorzugt. faliases: Quell-formular_id → kanonische ID.
    live = linkmod.read_formulare_live(links_dir)
    faliases = {}
    for f in live:
        for a in f.get("alias_ids") or []:
            if a != f["formular_id"]:
                faliases[a] = f["formular_id"]
    canon = {}
    for f in live:
        for key in (f.get("url_pdf"), f.get("local_pdf")):
            if key:
                canon.setdefault(key, f["formular_id"])
    for r in sorted(all_form, key=lambda r: r["_source_id"] != "seed"):
        fid = faliases.get(r["formular_id"], r["formular_id"])
        for key in (r.get("local_pdf"), r.get("url_pdf")):
            if key:
                canon.setdefault(key, fid)
        target = next((canon[k] for k in (r.get("url_pdf"), r.get("local_pdf")) if k and canon.get(k)), fid)
        if target != r["formular_id"]:
            faliases[r["formular_id"]] = target
        r["formular_id"] = target
    for r in all_leist:
        if isinstance(r.get("antrag"), dict) and r["antrag"].get("formular_id"):
            r["antrag"] = {**r["antrag"], "formular_id": faliases.get(r["antrag"]["formular_id"], r["antrag"]["formular_id"])}
    report["formular_aliase"] = len(faliases)

    # Leistungen
    merged, claims, alias_vor = merge_leistungen(all_leist, tax)
    con.executemany("INSERT INTO leistung_claims VALUES (?,?,?,?,?,?,?,?,?)", claims)
    leist_rows = []
    for lid, m in merged.items():
        data = {k: v for k, v in m.items() if not k.startswith("_")}
        data["_varianten"] = m.get("_varianten", {})
        data["_herkunft"] = m.get("_herkunft", {})
        data["_raw_ids"] = m.get("_raw_ids", [])
        data["_entschieden"] = m.get("_entschieden", {})
        cur = con.execute("INSERT INTO leistungen VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            lid, m.get("name"), m.get("kurz_einfach"), jdump(m.get("bereich") or []), jdump(m.get("traeger") or []),
            None if m.get("innerhalb_sv") is None else int(bool(m.get("innerhalb_sv"))), jdump(m.get("bundesland") or []),
            jdump(data), jdump(m["_sources"]), len(m["_sources"]), m["_review_status"], jdump(m["_conflicts"]), m.get("_stand")))
        tx = tax.entries.get(lid, {})
        body = " ".join([m.get("kurz_einfach") or "", m.get("zielgruppe") or "", " ".join(m.get("trigger_im_dokument") or []),
                         " ".join(v.get("text", "") for v in m.get("voraussetzungen") or []), lid.replace("_", " "),
                         " ".join(m.get("_raw_ids", [])).replace("_", " "), " ".join(tx.get("varianten", [])).replace("_", " "),
                         m.get("zustaendig") or ""])
        con.execute("INSERT INTO leistungen_fts(leistung_id,name,body) VALUES (?,?,?)", (lid, norm(m.get("name")), norm(body)))
        # Format wie im Modell-Benchmark (ARCHITEKTUR §1): "name: kurz_einfach"
        leist_rows.append((cur.lastrowid, f"{m.get('name')}: {m.get('kurz_einfach') or m.get('zielgruppe') or ''}"))

    # Stellen
    st = merge_simple(all_stellen, "stelle_id")
    for k, r in st.items():
        geo = r.get("geo") or [None, None]
        con.execute("INSERT INTO stellen VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            k, r.get("name"), r.get("typ"), r.get("adresse"), str(r.get("plz") or "") or None, r.get("bundesland"),
            r.get("telefon"), r.get("email"), r.get("url"), r.get("oeffnungszeiten"),
            jdump([tax.canon(x) for x in r.get("zustaendig_fuer") or []]),
            geo[0] if len(geo) > 1 else None, geo[1] if len(geo) > 1 else None, r.get("quelle_url"),
            ",".join(r["_sources"]), r.get("stand") or r.get("fetched_at"), jdump(r["_variants"])))
    # Formulare: Quellen + Seed, danach formulare_live drüber (kanonisch)
    for f in live:
        f = dict(f)
        f["_source_id"] = "linkcheck"
        all_form.append(f)
    fo = merge_simple(all_form, "formular_id")
    live_ids = {f["formular_id"]: f for f in live}
    for k, r in fo.items():
        lv = live_ids.get(k, {})
        for fld in ("url_pdf", "name", "traeger", "felder", "art", "sha256", "version", "gefunden_auf", "leistung_ids", "quelle_url"):
            if lv.get(fld) not in (None, "", []):
                r[fld] = lv[fld]
        con.execute("INSERT INTO formulare VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            k, r.get("name"), r.get("traeger"), r.get("url_pdf"), r.get("local_pdf"),
            None if r.get("fillable") is None else int(bool(r.get("fillable"))), jdump(r.get("felder") or []),
            jdump([tax.canon(x) for x in r.get("leistung_ids") or []]), r.get("wer_fuellt_aus"), r.get("quelle_url"),
            ",".join(r["_sources"]), lv.get("geprueft_am") or r.get("stand") or r.get("fetched_at"), jdump(r["_variants"]),
            r.get("art"), r.get("sha256"), r.get("version"), jdump(r.get("gefunden_auf") or []), int(bool(lv)),
            int(lv.get("zeigen", True)) if lv else 1, lv.get("url_status")))

    # Codes (Schema E): nur administrativ. Hint-Policy als Sicherheitsnetz.
    report["codes"] = load_codes(con, all_codes, tax, merged)

    # Kanten
    edges = []
    for lid, m in merged.items():
        for dep in m.get("abhaengigkeiten") or []:
            dep = tax.canon(dep)
            if dep != lid:
                edges.append((lid, dep, "setzt_voraus", ",".join(m["_sources"]), int(dep not in merged)))
        fid = (m.get("antrag") or {}).get("formular_id") if isinstance(m.get("antrag"), dict) else None
        if fid:
            edges.append((lid, fid, "antrag_formular", ",".join(m["_sources"]), int(fid not in fo)))
    for k, r in fo.items():
        for lid in r.get("leistung_ids") or []:
            lid = tax.canon(lid)
            edges.append((lid, k, "antrag_formular", ",".join(r["_sources"]), int(lid not in merged)))
    for k, r in st.items():
        for lid in r.get("zustaendig_fuer") or []:
            lid = tax.canon(lid)
            edges.append((lid, k, "zustaendige_stelle", ",".join(r["_sources"]), int(lid not in merged)))
    for a, b, t in tax.edges():
        if a in merged or b in merged:
            edges.append((a, b, t, "taxonomie", int(a not in merged or b not in merged)))
    edges = list({(a, b, t): (a, b, t, s, d) for a, b, t, s, d in edges}.values())
    con.executemany("INSERT INTO kanten VALUES (?,?,?,?,?)", edges)

    # Links (falls Linkcheck gelaufen ist)
    report["links"] = linkmod.load_links(con, links_dir)

    # Embeddings (Hybrid-Suche)
    if embeddings is None:
        embeddings = embed.available()[0]
    if embeddings:
        report["embeddings"] = embed.build_vectors(con, {"doc_vec": doc_rows, "leist_vec": leist_rows}, quiet=quiet)
    else:
        report["embeddings"] = {"aktiv": False, "grund": "deaktiviert" if embeddings is False else embed.available()[1]}
    emb = report["embeddings"]

    report["leistungen"] = {
        "total": len(merged),
        "nach_status": {s: sum(1 for m in merged.values() if m["_review_status"] == s) for s in
                        ("kuratiert", "kuratiert+quellen", "kandidat", "konflikt")},
        "konflikte": {lid: [f"{c['feld']}: {c['art']}" for c in m["_conflicts"]] for lid, m in merged.items() if m["_conflicts"]},
        "mit_traeger_auspraegungen": sorted(lid for lid, m in merged.items() if m.get("traeger_auspraegungen")),
        "ohne_quelle": sorted(lid for lid, m in merged.items() if not m.get("quellen")),
        "alias_vorschlaege": alias_vor,
        "kanten_ins_leere": [e[:3] for e in edges if e[4]],
    }
    report["stellen"] = {"total": len(st), "mit_geo": sum(1 for r in st.values() if r.get("geo"))}
    report["formulare"] = {"total": len(fo), "live_kanonisch": len(live)}
    report["seed_fehler"] = seed_p.errors
    con.executemany("INSERT INTO meta VALUES (?,?)", [("built_at", report["built_at"]), ("report", jdump(report)),
                                                       ("emb_model", emb.get("modell") if emb.get("aktiv") else None),
                                                       ("emb_dim", str(emb.get("dim")) if emb.get("aktiv") else None)])
    con.commit()
    con.close()

    snapshot = {"built_at": report["built_at"], "documents": defaultdict(dict), "leistungen": {}, "stellen": {}, "formulare": {}}
    for r in all_docs:
        snapshot["documents"][r["_source_id"]][r["id"]] = r.get("sha256") or h(r["text"])
    for lid, m in merged.items():
        core = {k: v for k, v in m.items() if not k.startswith("_") and k != "quellen"}
        snapshot["leistungen"][lid] = {"hash": h(core), "sources": m["_sources"], "status": m["_review_status"], "name": m.get("name")}
    for k, r in st.items():
        snapshot["stellen"][k] = h({f: v for f, v in r.items() if not f.startswith("_")})
    for k, r in fo.items():
        snapshot["formulare"][k] = h({f: v for f, v in r.items() if not f.startswith("_")})
    report["_snapshot"] = snapshot
    report["_new_path"] = str(new)
    if swap:
        finalize(new, db_path, report, quiet=quiet)
    return report


def finalize(new: Path, db_path: Path, report: dict, quiet=False):
    """Atomarer Swap .new → lotse.sqlite + Snapshot/Report/graph.json schreiben (nur nach bestandenen Gates aufrufen)."""
    snapshot = report.pop("_snapshot", None)
    report.pop("_new_path", None)
    Path(new).replace(db_path)  # atomar: Lotse liest nie eine halbe DB
    if snapshot:
        (db_path.parent / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    (db_path.parent / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    export_graph(db_path)
    if not quiet:
        print_report(report)


def export_graph(db_path: Path):
    """graph.json: nur Leistungsgraph + Seed/Quellen-Stellen/Formulare (ohne Volltext) – für Frontends ohne Backend."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    g = {"built_at": con.execute("SELECT value FROM meta WHERE key='built_at'").fetchone()[0],
         "leistungen": [], "kanten": [dict(r) for r in con.execute("SELECT * FROM kanten")],
         "stellen": [dict(r) for r in con.execute("SELECT stelle_id,name,typ,adresse,plz,bundesland,telefon,url,zustaendig_fuer,quelle_url,source_id FROM stellen")],
         "formulare": [dict(r) for r in con.execute("SELECT formular_id,name,traeger,local_pdf,url_pdf,leistung_ids,wer_fuellt_aus,source_id FROM formulare "
                                                    "WHERE formular_id IN (SELECT nach FROM kanten WHERE typ='antrag_formular')")]}
    for r in con.execute("SELECT * FROM leistungen ORDER BY leistung_id"):
        d = json.loads(r["data_json"])
        d.pop("_herkunft", None)
        g["leistungen"].append(d | {"review_status": r["review_status"], "sources": json.loads(r["sources"]),
                                    "konflikte": json.loads(r["conflicts_json"]), "stand": r["stand"]})
    con.close()
    (db_path.parent / "graph.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")


def print_report(r):
    print(f"lotse.sqlite gebaut {r['built_at']}")
    print(f"  Seed: {r['seed']}")
    for sid, q in r["quellen"].items():
        print(f"  [{sid:15}] {q['status']:10} docs={q['documents']:5} leist={q['leistungen']:3} stellen={q['stellen']:4} "
              f"form={q['formulare']:3} fehler={q['errors']} warn={q['warnings']}")
        for e in q["beispiel_fehler"][:3]:
            print(f"      ✗ {e}")
    L = r["leistungen"]
    print(f"  documents={r['documents']}  stellen={r['stellen']}  formulare={r['formulare']}")
    print(f"  links={r.get('links')}  embeddings={ {k: v for k, v in (r.get('embeddings') or {}).items() if k != 'cache_datei'} }")
    if r.get("uebersprungen"):
        print(f"  übersprungen: {list(r['uebersprungen'])}")
    print(f"  leistungen={L['total']} {L['nach_status']}")
    for lid, c in L["konflikte"].items():
        print(f"    ⚠ Konflikt {lid}: {c}")
    if L["alias_vorschlaege"]:
        print(f"    Alias-Vorschläge: {L['alias_vorschlaege'][:10]}")
    if r.get("codes"):
        print(f"  codes: {r['codes']['nach_system']}  Hints per Policy entfernt: {r['codes']['hints_durch_policy_entfernt']}"
              f"  Hints ohne Leistung: {r['codes']['hints_ohne_leistung_im_graph']}")
    if L["kanten_ins_leere"]:
        print(f"    Kanten ins Leere: {L['kanten_ins_leere'][:10]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="bei Schemafehlern abbrechen")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--sources", type=Path, default=SOURCES)
    a = ap.parse_args()
    build(a.db, a.sources, a.strict)
