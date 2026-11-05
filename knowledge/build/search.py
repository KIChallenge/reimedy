#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["fastembed>=0.4", "sqlite-vec==0.1.9", "numpy"]
# ///
"""Lotse-Tools über lotse.sqlite – Graph zuerst, RAG (FTS) als Fallback. Jede Antwort trägt Quelle + Stand.

Python:   from search import Lotse; L = Lotse(); L.search("Pflegegeld beantragen", bundesland="W")
CLI:      uv run --python 3.12 knowledge/build/search.py "zahnspange kind"
HTTP:     uv run --python 3.12 knowledge/build/search.py --serve [--port 8765]
  GET  /health                                 → DB-Stand, Quellenstatus
  GET  /search?q=…&bereich=D&bundesland=W      → {leistungen:[…], dokumente:[…], graph_treffer}
  GET  /leistung/<id>                          → Leistung + Voraussetzungen-Kette, Formulare, Stellen, Konflikte, Claims
  GET  /stellen?plz=1030&typ=beratung&leistung=pflegegeld
  GET  /formular/<id>
  POST /triggers  {"text": "…Entlassungsbrief…"} → Leistungen, deren Trigger im Dokument vorkommen (mit Fundstelle)
  GET  /code/<system>/<code>                   → wörtliches Label, Hierarchie, Leistungs-Hinweise (nur administrativ)
  GET  /codes?q=…&system=ICD-10-AT             → Code-Suche über Labels
  POST /codes/hints {"codes":["C20", {"system":"ATC","code":"…"}]} → Leistungs-Kandidaten
  GET  /misses                                 → Fragen ohne Graph-Treffer (Kuratierungs-Kandidaten)
Nur stdlib.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import HINT_POLICY_ICD, hint_allowed  # noqa: E402
from common import BUILD, DB_PATH, code_norm, fts_query, norm  # noqa: E402
from links import FORMULAR_ARTEN_AUSBLENDEN, LINK_MAX_AGE_DAYS  # noqa: E402
from taxonomy import Taxonomie  # noqa: E402

MISSES = BUILD / "misses.jsonl"
SYNONYME = BUILD / "query_synonyme.json"


def _load_syn():
    try:
        return [(re.compile(r["muster"]), r["begriffe"]) for r in json.loads(SYNONYME.read_text(encoding="utf-8"))["regeln"]]
    except Exception:
        return []


def expand_query(query: str, regeln) -> list[str]:
    """Kuratierte Umgangssprache → Fachbegriffe (deterministisch, transparent)."""
    nq, out = norm(query), []
    for rx, begriffe in regeln:
        if rx.search(nq):
            out += [b for b in begriffe if b not in out]
    return out

# PLZ → Bundesland (grob, erste Ziffer; reicht für „Stellen in meiner Region")
PLZ_BL = {"1": "W", "2": "N", "3": "N", "4": "O", "5": "S", "6": "T", "7": "B", "8": "St", "9": "K"}

DISCLAIMER = ("Allgemeine Information zu Leistungen und Zuständigkeiten, keine medizinische oder rechtsverbindliche Auskunft. "
              "Ob ein Anspruch besteht, entscheidet der zuständige Träger.")


def _haversine(a, b):
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _j(s, default=None):
    if s is None:
        return default
    try:
        return json.loads(s)
    except (TypeError, json.JSONDecodeError):
        return default


class Lotse:
    RRF_K = 60
    VEC_MIN = 0.45   # Cosinus-Ähnlichkeit, ab der ein reiner Vektor-Treffer als „Graph-Treffer" zählt (sonst → misses)

    def __init__(self, db: Path = DB_PATH, log_misses=True, hybrid: bool | None = None):
        self.db_path = db
        self.con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.log_misses = log_misses
        self.built_at = self._meta("built_at")
        self.tax = Taxonomie()
        self.syn = _load_syn()
        self.emb_model = self._meta("emb_model")
        self.emb = None
        self.mode = "fts"
        if hybrid is not False and self.emb_model:
            try:
                import embed
                if embed.load_vec(self.con):
                    self.emb = embed.Embedder.get(self.emb_model)
                    self.mode = "hybrid"
            except Exception as e:  # fastembed/sqlite-vec fehlen → FTS weiter nutzbar
                self.mode = f"fts (hybrid nicht verfügbar: {type(e).__name__})"
        self.has_links = bool(self.con.execute("SELECT name FROM sqlite_master WHERE name='links'").fetchone()) and \
            self.con.execute("SELECT count(*) FROM links").fetchone()[0] > 0

    def _meta(self, k):
        r = self.con.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
        return r[0] if r else None

    def _envelope(self, payload: dict) -> dict:
        payload["_meta"] = {"db_stand": self.built_at, "suche": self.mode,
                            "links_geprueft": self.has_links, "hinweis": DISCLAIMER}
        return payload

    # ------------------------------------------------------------------ Links (ARCHITEKTUR §3)
    def link(self, url: str | None, kind: str | None = None) -> dict | None:
        """Nur Links mit last_ok_at < 7 Tage. Toter Link → Elternseite mit Hinweis → sonst None (ausgeblendet).
        Nicht-HTTP (lokale Fallback-PDFs, sozdok:-IDs) wird als 'lokal' durchgereicht."""
        if not url:
            return None
        if not str(url).startswith("http"):
            return {"url": url, "art": "lokal", "geprueft_am": None}
        r = self.con.execute("SELECT * FROM links WHERE url=? OR final_url=? ORDER BY last_ok_at DESC LIMIT 1",
                             (url, url)).fetchone() if self.has_links else None
        if r is None:
            return {"url": None, "original_url": url, "link_status": "ungeprueft", "geprueft_am": None}
        fresh = r["ok"] and r["last_ok_at"] and self.con.execute(
            f"SELECT julianday('now') - julianday(?) < {LINK_MAX_AGE_DAYS}", (r["last_ok_at"],)).fetchone()[0]
        if fresh:
            return {"url": r["final_url"] or url, "geprueft_am": r["checked_at"] or r["last_ok_at"], "kind": r["kind"]}
        if r["ersetzt_durch"] and r["ersetzt_durch"] != url:
            ers = self.link(r["ersetzt_durch"], kind)
            if ers and ers.get("url") and (r["ersatz_regel"] or "").startswith("b"):
                ers = ers | {"hinweis": "Direktlink nicht erreichbar – Formular dort herunterladen", "original_url": url}
            return ers
        if r["eltern_url"]:
            el = self.link(r["eltern_url"])
            if el and el.get("url"):
                return el | {"hinweis": "Direktlink nicht erreichbar – Formular dort herunterladen", "original_url": url}
        return {"url": None, "original_url": url, "link_status": "tot", "geprueft_am": r["checked_at"]}

    def _quellen(self, qs):
        out = []
        for q in qs or []:
            q = q if isinstance(q, dict) else {"url": q}
            lk = self.link(q.get("url"))
            out.append({**q, "url": (lk or {}).get("url"), "geprueft_am": (lk or {}).get("geprueft_am"),
                        **({"link_status": lk["link_status"]} if lk and lk.get("link_status") else {})})
        return out

    # ------------------------------------------------------------------ search (Graph zuerst, hybrid FTS+Vektor, RRF)
    def search(self, query: str, bereich: str | None = None, bundesland: str | None = None, limit: int = 8,
               begriffe: list[str] | None = None) -> dict:
        """query = Originalfrage; begriffe = Fachbegriffe aus der Umschreibung durch System 1 (optional, ARCHITEKTUR §1)."""
        auto = [b for b in expand_query(query, self.syn) if b not in (begriffe or [])]
        full = " ".join([query] + list(begriffe or []) + auto)
        q = fts_query(full)
        qvec = self.emb.query(full).tobytes() if self.emb else None
        K = self.RRF_K

        # --- Leistungen
        fts_rank, vec_rank, vec_sim, name_hits = {}, {}, {}, {}
        if q:
            for i, r in enumerate(self.con.execute(
                    "SELECT leistung_id FROM leistungen_fts WHERE leistungen_fts MATCH ? ORDER BY bm25(leistungen_fts, 0, 5.0, 1.0) LIMIT 60", (q,))):
                fts_rank[r[0]] = i
            stems = [t.strip('"*') for t in q.split(" OR ")]
            for r in self.con.execute("SELECT leistung_id, name FROM leistungen"):
                ntoks = norm(r[1]).replace("-", " ").split()
                c = sum(any(t.startswith(st) for t in ntoks) for st in stems if len(st) >= 4)
                if c:
                    name_hits[r[0]] = c
        if qvec:
            for i, r in enumerate(self.con.execute(
                    "SELECT l.leistung_id, v.distance FROM leist_vec v JOIN leistungen l ON l.rowid=v.rowid "
                    "WHERE v.embedding MATCH ? AND k = 40 ORDER BY v.distance", (qvec,))):
                vec_rank[r[0]] = i
                vec_sim[r[0]] = 1 - r[1]
        name_rank = {lid: i for i, (lid, _) in enumerate(sorted(name_hits.items(), key=lambda x: -x[1]))}
        scores = {}
        for ranks in (fts_rank, vec_rank, name_rank):
            for lid, rk in ranks.items():
                scores[lid] = scores.get(lid, 0) + 1 / (K + rk)
        leistungen = []
        for lid in sorted(scores, key=lambda x: -scores[x]):
            r = self.con.execute("SELECT * FROM leistungen WHERE leistung_id=?", (lid,)).fetchone()
            ber, bl = _j(r["bereich"], []), _j(r["bundesland"], [])
            if bereich and bereich not in ber:
                continue
            if bundesland and bl and "AT" not in bl and bundesland not in bl:
                continue
            d = _j(r["data_json"], {})
            bonus = 0.002 if r["review_status"].startswith("kuratiert") else 0
            leistungen.append({
                "leistung_id": lid, "name": r["name"], "kurz_einfach": r["kurz_einfach"],
                "bereich": ber, "traeger": _j(r["traeger"], []), "bundesland": bl, "typ": d.get("typ"),
                "review_status": r["review_status"], "confidence": d.get("confidence"),
                "hat_konflikt": bool(_j(r["conflicts_json"], [])),
                "quellen": self._quellen(d.get("quellen", [])[:3]), "stand": r["stand"],
                "score": round(scores[lid] + bonus, 4),
                "treffer": {"fts": lid in fts_rank, "name": lid in name_hits,
                            "vektor_sim": round(vec_sim[lid], 3) if lid in vec_sim else None}})
        leistungen.sort(key=lambda x: -x["score"])
        leistungen = leistungen[:limit]

        # --- Dokumente (RAG)
        filt, fargs = "", []
        if bereich:
            filt += " AND d.bereich LIKE ?"
            fargs.append(f'%"{bereich}"%')
        if bundesland:
            filt += " AND (d.bundesland LIKE '%\"AT\"%' OR d.bundesland LIKE ? OR d.bundesland='[]')"
            fargs.append(f'%"{bundesland}"%')
        drank, dvrank, snips = {}, {}, {}
        if q:
            for i, r in enumerate(self.con.execute(
                    "SELECT d.rid, snippet(documents_fts, 2, '«', '»', ' … ', 24) AS snip FROM documents_fts "
                    f"JOIN documents d ON d.rid=documents_fts.rowid WHERE documents_fts MATCH ? {filt} "
                    "ORDER BY bm25(documents_fts, 3.0, 2.0, 1.0) LIMIT 40", [q] + fargs)):
                drank[r[0]] = i
                snips[r[0]] = r[1]
        if qvec:
            rows = self.con.execute("SELECT rowid, distance FROM doc_vec WHERE embedding MATCH ? AND k = 80 ORDER BY distance",
                                    (qvec,)).fetchall()
            ids = [r[0] for r in rows]
            if ids:
                ok = {x[0] for x in self.con.execute(
                    f"SELECT d.rid FROM documents d WHERE d.rid IN ({','.join('?' * len(ids))}) {filt}", ids + fargs)}
                for i, r in enumerate(x for x in rows if x[0] in ok):
                    dvrank[r[0]] = i
        dsc = {}
        for ranks in (drank, dvrank):
            for rid, rk in ranks.items():
                dsc[rid] = dsc.get(rid, 0) + 1 / (K + rk)
        dokumente = []
        for rid in sorted(dsc, key=lambda x: -dsc[x])[:limit]:
            r = self.con.execute("SELECT * FROM documents WHERE rid=?", (rid,)).fetchone()
            lk = self.link(r["url"])
            dokumente.append({
                "id": r["id"], "source_id": r["source_id"], "title": r["title"], "section": r["section"],
                "text": r["text"][:1200], "snippet": snips.get(rid), "url": (lk or {}).get("url"),
                "geprueft_am": (lk or {}).get("geprueft_am"), "doc_type": r["doc_type"],
                "stand": r["valid_from"] or r["fetched_at"], "abgerufen": r["fetched_at"],
                "bereich": _j(r["bereich"], []), "bundesland": _j(r["bundesland"], []), "score": round(dsc[rid], 4)})

        graph_treffer = any(l["treffer"]["fts"] or l["treffer"]["name"] or (l["treffer"]["vektor_sim"] or 0) >= self.VEC_MIN
                            for l in leistungen)
        if not graph_treffer and self.log_misses:
            self._log_miss(full, bereich, bundesland, len(dokumente))
        return self._envelope({"query": query, "begriffe": begriffe or [], "begriffe_auto": auto, "fts": q, "graph_treffer": graph_treffer,
                               "leistungen": leistungen, "dokumente": dokumente})

    def _log_miss(self, query, bereich, bundesland, n_docs):
        try:
            with MISSES.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "query": query,
                                     "bereich": bereich, "bundesland": bundesland, "rag_treffer": n_docs},
                                    ensure_ascii=False) + "\n")
        except OSError:
            pass

    def misses(self, n=100):
        if not MISSES.exists():
            return self._envelope({"misses": []})
        lines = MISSES.read_text(encoding="utf-8").splitlines()[-n:]
        counts: dict[str, dict] = {}
        for ln in lines:
            m = _j(ln, {})
            k = norm(m.get("query"))
            c = counts.setdefault(k, {"query": m.get("query"), "anzahl": 0, "rag_treffer": m.get("rag_treffer")})
            c["anzahl"] += 1
        return self._envelope({"misses": sorted(counts.values(), key=lambda x: -x["anzahl"])})

    # ------------------------------------------------------------------ Leistung
    def get_leistung(self, leistung_id: str, mit_claims=True) -> dict:
        lid = self.tax.canon(leistung_id)
        r = self.con.execute("SELECT * FROM leistungen WHERE leistung_id=?", (lid,)).fetchone()
        if not r:
            return self._envelope({"error": f"Leistung '{leistung_id}' nicht im Graph", "leistung_id": leistung_id})
        d = _j(r["data_json"], {})
        out = {**{k: v for k, v in d.items() if not k.startswith("_")},
               "review_status": r["review_status"], "sources": _j(r["sources"], []), "stand": r["stand"],
               "konflikte": _j(r["conflicts_json"], []), "varianten": d.get("_varianten", {})}
        out["quellen"] = self._quellen(d.get("quellen"))
        if isinstance(out.get("antrag"), dict) and out["antrag"].get("online_url"):
            lk = self.link(out["antrag"]["online_url"])
            out["antrag"] = {**out["antrag"], "online_url": (lk or {}).get("url"), "online_url_geprueft_am": (lk or {}).get("geprueft_am")}

        def k(sql, col="nach"):
            return [self._lname(x[col]) | {"fehlt_im_graph": bool(x["dangling"])} for x in self.con.execute(sql, (lid,))]
        # Kanten (deterministisch – „Code entscheidet")
        out["setzt_voraus"] = k("SELECT * FROM kanten WHERE von=? AND typ='setzt_voraus'")
        out["ist_voraussetzung_fuer"] = k("SELECT * FROM kanten WHERE nach=? AND typ='setzt_voraus'", "von")
        out["teil_von"] = k("SELECT * FROM kanten WHERE von=? AND typ='teil_von'")
        out["umfasst"] = k("SELECT * FROM kanten WHERE nach=? AND typ='teil_von'", "von")
        def uniq(xs):
            seen = set()
            return [x for x in xs if not (x["leistung_id"] in seen or seen.add(x["leistung_id"]))]
        out["nicht_verwechseln_mit"] = uniq(k("SELECT * FROM kanten WHERE (von=? AND typ='nicht_verwechseln_mit')") +
                                            k("SELECT * FROM kanten WHERE (nach=? AND typ='nicht_verwechseln_mit')", "von"))
        out["alternative_zu"] = uniq(k("SELECT * FROM kanten WHERE von=? AND typ='alternative_zu'") +
                                     k("SELECT * FROM kanten WHERE nach=? AND typ='alternative_zu'", "von"))
        out["formulare"] = [f for f in (self._formular_kurz(x["nach"]) for x in self.con.execute(
            "SELECT DISTINCT nach FROM kanten WHERE von=? AND typ='antrag_formular'", (lid,))) if f]
        out["stellen"] = [self._stelle(s) for s in self.con.execute(
            "SELECT s.* FROM kanten k JOIN stellen s ON s.stelle_id=k.nach WHERE k.von=? AND k.typ='zustaendige_stelle'", (lid,))]
        out["reihenfolge"] = self._reihenfolge(lid)
        out["rechtsgrundlagen_und_extras"] = [{"source_id": x["source_id"], "datei": x["file"], **(_j(x["data_json"], {}) or {})}
                                              for x in self.con.execute("SELECT * FROM extras WHERE leistung_id=?", (lid,))]
        if mit_claims:
            out["claims"] = [dict(c) | {"value": _j(c["value_json"])} for c in self.con.execute(
                "SELECT source_id, origin, field, value_json, quelle_url, stand, confidence FROM leistung_claims WHERE leistung_id=?", (lid,))]
            for c in out["claims"]:
                c.pop("value_json", None)
        return self._envelope(out)

    def _lname(self, lid):
        r = self.con.execute("SELECT name, review_status FROM leistungen WHERE leistung_id=?", (lid,)).fetchone()
        return {"leistung_id": lid, "name": r["name"] if r else (self.tax.entries.get(lid) or {}).get("name")}

    def _reihenfolge(self, lid, seen=None, stack=None):
        """Topologische Reihenfolge der Voraussetzungen: was zuerst erledigt werden muss (z. B. Rezeptgebührenbefreiung → Fahrtkostenzuschuss).
        Zyklen aus Quellen (A setzt B voraus, B setzt A voraus) werden abgebrochen statt endlos zu laufen."""
        seen = seen if seen is not None else []
        stack = stack if stack is not None else set()
        stack.add(lid)
        for x in self.con.execute("SELECT nach FROM kanten WHERE von=? AND typ='setzt_voraus'", (lid,)):
            if x["nach"] not in seen and x["nach"] not in stack:
                self._reihenfolge(x["nach"], seen, stack)
        stack.discard(lid)
        if lid not in seen:
            seen.append(lid)
        return seen

    # ------------------------------------------------------------------ Stellen
    def _stelle(self, s):
        d = dict(s)
        d["zustaendig_fuer"] = _j(d["zustaendig_fuer"], [])
        d["varianten"] = _j(d.pop("variants_json"), [])
        lk = self.link(d.get("url"))
        d["url"], d["url_geprueft_am"] = (lk or {}).get("url"), (lk or {}).get("geprueft_am")
        ql = self.link(d.get("quelle_url"))
        d["quelle"] = {"url": (ql or {}).get("url"), "geprueft_am": (ql or {}).get("geprueft_am"),
                       "source_id": d.get("source_id"), "stand": d.get("stand")}
        d["geo"] = [d.pop("lat"), d.pop("lon")] if d.get("lat") is not None else None
        d.pop("lat", None), d.pop("lon", None)
        return d

    def plz_geo(self, plz: str):
        """PLZ → Mittelpunkt aus den Stellen mit Koordinaten in dieser PLZ (datengetrieben, kein externer Dienst)."""
        r = self.con.execute("SELECT avg(lat), avg(lon), count(*) FROM stellen WHERE plz=? AND lat IS NOT NULL", (plz,)).fetchone()
        return (r[0], r[1]) if r and r[2] else None

    def stellen_near(self, plz: str | None = None, typ: str | None = None, leistung_id: str | None = None, limit=10,
                     lat: float | None = None, lon: float | None = None) -> dict:
        """Echte Distanz (Haversine), wo Koordinaten vorhanden sind; sonst Rangfolge PLZ → Bezirk → Bundesland → österreichweit."""
        sql, args = "SELECT * FROM stellen WHERE 1=1", []
        if typ:
            sql += " AND typ=?"
            args.append(typ)
        if leistung_id:
            sql += " AND zustaendig_fuer LIKE ?"
            args.append(f'%"{self.tax.canon(leistung_id)}"%')
        rows = [self._stelle(r) for r in self.con.execute(sql, args)]
        plz = (plz or "").strip()
        bl = PLZ_BL.get(plz[:1]) if plz else None
        origin = (lat, lon) if lat is not None and lon is not None else (self.plz_geo(plz) if plz else None)

        def rank(s):
            sp = s.get("plz") or ""
            if origin and s.get("geo"):
                return (0, _haversine(origin, s["geo"]), "Entfernung")
            if plz and sp == plz:
                return (1, 0, "gleiche PLZ")
            if plz and sp[:3] == plz[:3] and sp:
                return (2, 0, "gleicher Bezirk/Region")
            if bl and s.get("bundesland") == bl:
                return (3, 0, "gleiches Bundesland")
            if s.get("bundesland") in ("AT", None, ""):
                return (4, 0, "österreichweit")
            return (9, 0, "anderes Bundesland")
        ranked = []
        for s in rows:
            rk, dist, why = rank(s)
            if rk < 9 and not (rk == 0 and bl and s.get("bundesland") not in (bl, "AT", None, "") and dist > 80):
                ranked.append((rk if rk else 0, dist, s | {"naehe": why, **({"entfernung_km": round(dist, 2)} if rk == 0 else {})}))
        ranked.sort(key=lambda x: (x[0] if x[0] else 0, x[1], x[2]["name"] or ""))
        # Geo-Treffer zuerst nach Distanz, danach die ohne Koordinaten nach PLZ-Logik
        return self._envelope({"plz": plz, "bundesland": bl, "typ": typ, "leistung_id": leistung_id,
                               "ursprung": origin, "stellen": [s for *_, s in ranked[:limit]],
                               "hinweis_naehe": "Entfernung (Luftlinie) wo Koordinaten vorhanden; sonst Rangfolge nach PLZ/Bundesland."})

    # ------------------------------------------------------------------ Formulare
    def _formular_kurz(self, fid):
        r = self.con.execute("SELECT formular_id, name, traeger, local_pdf, url_pdf, wer_fuellt_aus, art, version, live, zeigen, url_status, quelle_url "
                             "FROM formulare WHERE formular_id=?", (fid,)).fetchone()
        if not r:
            return {"formular_id": fid, "fehlt_im_graph": True}
        r = dict(r)
        if (r["art"] or "") in FORMULAR_ARTEN_AUSBLENDEN:
            return None
        if r["zeigen"] == 0:
            # Ausnahme: Antrag ohne öffentliches PDF (z. B. fsw_bedarfsmeldung_wg) → lokale Kopie + Elternseite statt verschwinden
            if not (r.get("local_pdf") and r.get("url_status") == "keine_url" and r["art"] in ("antrag", "beilage")):
                return None
        d = dict(r)
        d.pop("url_status", None)
        d.pop("zeigen", None)
        lk = self.link(d.pop("url_pdf"))
        d["url_pdf"], d["geprueft_am"] = (lk or {}).get("url"), (lk or {}).get("geprueft_am")
        if lk and lk.get("hinweis"):
            d["hinweis"] = lk["hinweis"]
        el = self.link(d.pop("quelle_url", None))
        if not d["url_pdf"] and d.get("local_pdf"):
            d["hinweis"] = "Kein öffentlich herunterladbares PDF bestätigt – lokale Kopie (SV-Box) nur als Fallback, Stand prüfen"
            if el and el.get("url"):
                d["online_seite"], d["online_seite_geprueft_am"] = el["url"], el.get("geprueft_am")
                d["hinweis"] += "; aktuelle Fassung auf der Seite des Trägers"
        return d

    def formular(self, formular_id: str) -> dict:
        r = self.con.execute("SELECT * FROM formulare WHERE formular_id=?", (formular_id,)).fetchone()
        if not r:
            return self._envelope({"error": f"Formular '{formular_id}' unbekannt"})
        if not self._formular_kurz(formular_id):
            return self._envelope({"error": f"'{formular_id}' wird dem Lotsen nicht als Formular gezeigt (art={r['art']})"})
        d = dict(r)
        d["felder"] = _j(d.pop("felder_json"), [])
        d["leistung_ids"] = _j(d["leistung_ids"], [])
        d["varianten"] = _j(d.pop("variants_json"), [])
        d["gefunden_auf"] = _j(d["gefunden_auf"], [])
        k = self._formular_kurz(formular_id) or {}
        d["url_pdf"], d["geprueft_am"] = k.get("url_pdf"), k.get("geprueft_am")
        for f in ("hinweis", "online_seite", "online_seite_geprueft_am"):
            if k.get(f):
                d[f] = k[f]
        ql = self.link(d.get("quelle_url"))
        d["quelle"] = {"url": (ql or {}).get("url") or d["url_pdf"] or d.get("local_pdf"), "source_id": d.get("source_id"),
                       "stand": d.get("stand"), "geprueft_am": (ql or {}).get("geprueft_am") or d["geprueft_am"]}
        return self._envelope(d)

    # ------------------------------------------------------------------ Trigger (für System 2)
    def triggers(self, text: str) -> dict:
        """Welche Leistungen nennt ein Dokument (Entlassungsbrief) – deterministisch über trigger_im_dokument, mit Fundstelle.
        Das ist KEINE Anspruchsprüfung, nur „das Dokument erwähnt X → Leistung Y prüfen"."""
        nt = norm(text)
        hits = []
        for r in self.con.execute("SELECT leistung_id, name, data_json FROM leistungen"):
            d = _j(r["data_json"], {})
            found = []
            for t in d.get("trigger_im_dokument") or []:
                nt_ = norm(t)
                if len(nt_) < 4:
                    continue
                i = nt.find(nt_)
                if i >= 0:
                    found.append({"trigger": t, "kontext": nt[max(0, i - 60): i + len(nt_) + 60]})
            if found:
                hits.append({"leistung_id": r["leistung_id"], "name": r["name"], "treffer": found})
        hits.sort(key=lambda h: -len(h["treffer"]))
        return self._envelope({"leistungen": hits})

    # ------------------------------------------------------------------ Codes (Schema E, nur administrativ)
    CODE_HINWEIS = ("Code-Bezeichnung wörtlich aus der Quelle. Der Lotse deutet Codes nicht und trifft keine "
                    "Risiko- oder Therapieaussage – Fragen dazu klärt die behandelnde Ärztin.")

    def _code_row(self, system, code):
        c = code_norm(code)
        variants = [c]
        if system == "ICD-10-AT" and "." not in c and len(c) > 3 and "-" not in c:
            variants.append(c[:3] + "." + c[3:])  # C200 → C20.0
        for v in variants:
            r = self.con.execute("SELECT * FROM codes WHERE system=? AND code=?", (system, v)).fetchone()
            if r:
                return r, False
        # Fallback: nächster Elterncode (C20.9 → C20) – als solcher gekennzeichnet
        while system == "ICD-10-AT" and len(c) > 3:
            c = c[:-1].rstrip(".")
            r = self.con.execute("SELECT * FROM codes WHERE system=? AND code=?", (system, c)).fetchone()
            if r:
                return r, True
        return None, False

    def _code_dict(self, r):
        return {"system": r["system"], "code": r["code"], "label_de": r["label_de"], "label_einfach": r["label_einfach"],
                "parent": r["parent"], "leistung_hints": _j(r["leistung_hints"], []), "quelle": {"url": r["quelle_url"],
                "stand": r["stand"], "source_id": r["source_id"]}, **(_j(r["data_json"], {}) or {})}

    def _ancestors(self, r):
        chain, seen = [], set()
        while r is not None and r["parent"] and r["parent"] not in seen:
            seen.add(r["parent"])
            r = self.con.execute("SELECT * FROM codes WHERE system=? AND code=?", (r["system"], r["parent"])).fetchone()
            if r:
                chain.append(r)
        return chain

    def lookup_code(self, system: str, code: str) -> dict:
        """Code → wörtliches Label, Hierarchie, Leistungs-Hinweise (Kandidaten). Keine Deutung."""
        r, via_parent = self._code_row(system, code)
        if not r:
            return self._envelope({"system": system, "code": code, "gefunden": False, "hinweis": self.CODE_HINWEIS})
        out = self._code_dict(r) | {"gefunden": True, "angefragt": code, "ueber_elterncode": via_parent,
                                    "hierarchie": [{"code": a["code"], "label_de": a["label_de"]} for a in self._ancestors(r)],
                                    "hinweis": self.CODE_HINWEIS}
        return self._envelope(out)

    def search_codes(self, q: str, system: str | None = None, limit=10) -> dict:
        fq = fts_query(q)
        rows = []
        if fq:
            sql = "SELECT c.* FROM codes_fts f JOIN codes c ON c.system=f.system AND c.code=f.code WHERE codes_fts MATCH ?"
            args = [fq]
            if system:
                sql += " AND c.system=?"
                args.append(system)
            rows = self.con.execute(sql + " ORDER BY bm25(codes_fts) LIMIT ?", args + [limit]).fetchall()
        return self._envelope({"query": q, "codes": [self._code_dict(r) for r in rows], "hinweis": self.CODE_HINWEIS})

    def codes_to_leistung_hints(self, codes: list) -> dict:
        """Codes aus einem Dokument (z. B. ICD aus Entlassungsbrief, ATC aus e-Medikation) → Leistungs-KANDIDATEN zum Prüfen.
        Hints werden entlang der Hierarchie geerbt (C20 erbt vom Kapitel C00–C97). Keine Anspruchs- oder medizinische Aussage."""
        hints: dict[str, dict] = {}
        unbekannt = []
        for c in codes:
            system, code = (c.get("system", "ICD-10-AT"), c.get("code")) if isinstance(c, dict) else ("ICD-10-AT", c)
            r, _ = self._code_row(system, code)
            if not r:
                unbekannt.append({"system": system, "code": code})
                continue
            for node in [r] + self._ancestors(r):
                for h in _j(node["leistung_hints"], []):
                    pol = HINT_POLICY_ICD.get(h)
                    if system == "ICD-10-AT" and pol and not hint_allowed(r["code"], pol):
                        continue  # vererbter Hint gilt nicht für diesen konkreten Code (z. B. D17 unter C00–D48)
                    e = hints.setdefault(h, {"leistung_id": h, "ausgeloest_durch": []})
                    trig = {"system": system, "code": r["code"], "label_de": r["label_de"],
                            "hint_von": node["code"] if node is not r else None}
                    if trig not in e["ausgeloest_durch"]:
                        e["ausgeloest_durch"].append(trig)
        out = []
        for h, e in hints.items():
            l = self.con.execute("SELECT name, review_status FROM leistungen WHERE leistung_id=?", (h,)).fetchone()
            out.append(e | {"name": l["name"] if l else None, "im_graph": bool(l),
                            "review_status": l["review_status"] if l else None})
        return self._envelope({"kandidaten": out, "unbekannte_codes": unbekannt,
                               "hinweis": "Kandidaten zum Prüfen (z. B. Zuständigkeit, Antrag) – kein Anspruch, keine medizinische Aussage. "
                                          + self.CODE_HINWEIS})

    def health(self) -> dict:
        rep = _j(self._meta("report"), {})
        return self._envelope({"db": str(self.db_path), "built_at": self.built_at,
                               "quellen": [dict(r) | {"errors_json": None, "manifest_json": None}
                                           for r in self.con.execute("SELECT * FROM quellen")],
                               "leistungen": rep.get("leistungen", {}).get("nach_status"),
                               "documents": rep.get("documents"), "stellen": rep.get("stellen"), "formulare": rep.get("formulare"),
                               "links": rep.get("links"), "embeddings": rep.get("embeddings"), "gates": _j(self._meta("gates"), None),
                               "uebersprungen": rep.get("uebersprungen")})


# ---------------------------------------------------------------------- HTTP
def serve(port=8765, db=DB_PATH, host=None):
    import os
    host = host or os.environ.get("HOST", "127.0.0.1")
    holder = {"lotse": Lotse(db), "mtime": db.stat().st_mtime}

    def lotse():
        m = db.stat().st_mtime  # DB wurde neu gebaut → neu öffnen (Update ohne Neustart)
        if m != holder["mtime"]:
            holder["lotse"], holder["mtime"] = Lotse(db), m
        return holder["lotse"]

    class H(BaseHTTPRequestHandler):
        def _send(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False, indent=1).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self._send({})

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            p = u.path.rstrip("/")
            L = lotse()
            if p == "/health":
                return self._send(L.health())
            if p == "/search":
                return self._send(L.search(q.get("q", ""), q.get("bereich"), q.get("bundesland"), int(q.get("limit", 8)),
                                           [b for b in (q.get("begriffe") or "").split(",") if b.strip()]))
            if m := re.fullmatch(r"/leistung/([a-z0-9_]+)", p):
                return self._send(L.get_leistung(m[1], q.get("claims", "1") == "1"))
            if p == "/stellen":
                return self._send(L.stellen_near(q.get("plz"), q.get("typ"), q.get("leistung"), int(q.get("limit", 10)),
                                                 float(q["lat"]) if q.get("lat") else None, float(q["lon"]) if q.get("lon") else None))
            if m := re.fullmatch(r"/formular/([A-Za-z0-9_\-]+)", p):
                return self._send(L.formular(m[1]))
            if m := re.fullmatch(r"/code/([^/]+)/([^/]+)", p):
                from urllib.parse import unquote
                return self._send(L.lookup_code(unquote(m[1]), unquote(m[2])))
            if p == "/codes":
                return self._send(L.search_codes(q.get("q", ""), q.get("system")))
            if p == "/misses":
                return self._send(L.misses())
            self._send({"error": "unbekannter Pfad", "pfade": ["/health", "/search", "/leistung/<id>", "/stellen", "/formular/<id>", "/triggers (POST)", "/misses"]}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = _j(self.rfile.read(n).decode("utf-8"), {}) or {}
            path = urlparse(self.path).path.rstrip("/")
            if path == "/triggers":
                return self._send(lotse().triggers(body.get("text", "")))
            if path == "/codes/hints":
                return self._send(lotse().codes_to_leistung_hints(body.get("codes", [])))
            self._send({"error": "unbekannter Pfad"}, 404)

        def log_message(self, *a):
            pass

    print(f"Lotse-Wissens-API auf http://{host}:{port}  (DB {db})")
    ThreadingHTTPServer((host, port), H).serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host")
    ap.add_argument("--bereich")
    ap.add_argument("--bundesland")
    ap.add_argument("--leistung")
    a = ap.parse_args()
    if a.serve:
        serve(a.port, host=a.host)
    elif a.leistung:
        print(json.dumps(Lotse(log_misses=False).get_leistung(a.leistung, mit_claims=False), ensure_ascii=False, indent=1))
    else:
        res = Lotse().search(" ".join(a.query), a.bereich, a.bundesland)
        print(f"FTS: {res['fts']}   Graph-Treffer: {res['graph_treffer']}")
        for l in res["leistungen"]:
            print(f"  [G] {l['leistung_id']:28} {l['name']}  ({l['review_status']}, {l['confidence']})")
        for d in res["dokumente"]:
            print(f"  [D] {d['source_id']:14} {d['title']} – {d['section']}  ({d['stand']})  {d['url']}")
