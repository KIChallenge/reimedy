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
  GET  /formular/<id>/template[?alle=1]        → Template (Felder mit bbox + semantik), Standard nur geprüfte (sonst 404)
  GET  /formular/<id>/empfaenger?plz=&traeger= → zuständige Stelle, Kanal, Rückfragen (forms/empfaenger.jsonl)
  GET  /formular/<id>/pdf                      → angereicherte PDF-Kopie, sonst 302 auf die geprüfte Live-URL, sonst 404
  GET  /forms/ontologie                        → Feld-Ontologie (Schlüssel für vault_map)
  GET  /traeger?id=&plz=                       → Träger-Register mit zuständiger Landesstelle
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
from common import BL_NORM, BUILD, DB_PATH, STATE_DIR, code_norm, fts_query, norm, plz_bundesland, rel  # noqa: E402
from links import FORMULAR_ARTEN_AUSBLENDEN, LINK_MAX_AGE_DAYS  # noqa: E402
from taxonomy import Taxonomie  # noqa: E402

MISSES = STATE_DIR / "misses.jsonl"
SYNONYME = BUILD / "query_synonyme.json"


def _load_syn():
    try:
        return [(re.compile(r["muster"]), r["begriffe"], r.get("nicht") or []) for r in json.loads(SYNONYME.read_text(encoding="utf-8"))["regeln"]]
    except Exception:
        return []


def expand_query(query: str, regeln) -> list[str]:
    """Kuratierte Umgangssprache → Fachbegriffe (deterministisch, transparent)."""
    nq, out = norm(query), []
    for rx, begriffe, *_ in regeln:
        if rx.search(nq):
            out += [b for b in begriffe if b not in out]
    return out

# PLZ → Bundesland (grob, erste Ziffer; Fallback). Genauer: plz_bundesland() mit den Grenzbereichen.
PLZ_BL = {"1": "W", "2": "N", "3": "N", "4": "O", "5": "S", "6": "T", "7": "B", "8": "St", "9": "K"}
BL_NORM = {"NÖ": "N", "NOE": "N", "OÖ": "O", "OOE": "O", "ST": "St", "STMK": "St"}
PLZ_ZENTREN = BUILD / "plz_zentren.json"
# Leistungen ohne eigene Stellen-Zuordnung, die einem Stellen-Typ entsprechen (zustaendig_fuer bleibt leer)
LEISTUNG_TYP = {"hausarzt_pve": "pve"}


def bl_norm(bl):
    return BL_NORM.get(bl, bl) if bl else bl


def plz_bundesland(plz) -> str | None:
    """PLZ → Bundesland inkl. bekannter Grenzbereiche (wie forms/forms_api.py)."""
    p = str(plz or "").strip()
    if not (len(p) == 4 and p.isdigit()):
        return PLZ_BL.get(p[:1]) if p[:1].isdigit() else None
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


def _plz_zentren():
    try:
        return json.loads(PLZ_ZENTREN.read_text(encoding="utf-8"))["zentren"]
    except Exception:
        return {}

APOTHEKEN_NOTDIENST = {
    "telefon": "1455", "name": "Apothekenruf 1455 (Österreichische Apothekerkammer)",
    "beschreibung": "Rund um die Uhr: nennt die nächste dienstbereite Apotheke (Nacht-, Wochenend-, Feiertagsdienst).",
    "suche_url": "https://www.apothekerkammer.at/apothekensuche",
    "hinweis": "Öffnungszeiten der einzelnen Apotheken sind in den Wiener OGD-Daten nicht enthalten; für Nachtdienste gibt es "
               "keine offene API. Bei gesundheitlichen Fragen: 1450, im Notfall 144.",
    "quellen": ["https://www.apothekerkammer.at/apothekensuche",
                "https://www.pressetext.com/news/apothekenruf-1455-begruesst-gesundheitstelefon-1450.html"],
    "stand": "2026-11-06"}

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
        # Regeln mit "nicht": Leistungen, die bei dieser Frage nur über ein Wortteil (vorsorge* → Vorsorgevollmacht) treffen
        nq_ = norm(query)
        nicht = {x for rx, _, nn in self.syn if nn and rx.search(nq_) for x in nn}
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
            if lid in nicht:
                continue
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
        # W4 (Entscheidung Arne 06.11.): kein Label „ungeprüft“; bei Quellkonflikten die NEUERE Angabe zuerst,
        # alle Varianten (mit Quelle + Stand) unter `details`, absteigend nach Stand. Additiv.
        def _st(v):
            return str(v.get("stand") or "")
        details = {}
        for k_, vs in (d.get("_varianten") or {}).items():
            details[k_] = sorted(vs, key=_st, reverse=True)
        for c in out["konflikte"]:
            c["varianten"] = sorted(c.get("varianten") or [], key=_st, reverse=True)
            if c["varianten"]:
                out[c["feld"]] = c["varianten"][0]["value"]  # neuere Angabe zuerst
                c["angezeigt"] = {"source_id": c["varianten"][0].get("source_id"), "stand": c["varianten"][0].get("stand")}
            details[c["feld"]] = c["varianten"]
        for v in details.values():
            for x in v:
                if x.get("quelle_url"):
                    lk = self.link(x["quelle_url"])
                    x["quelle_url"], x["geprueft_am"] = (lk or {}).get("url") or (x["quelle_url"] if not str(x["quelle_url"]).startswith("http") else None), (lk or {}).get("geprueft_am")
        out["details"] = details
        if isinstance(out.get("antrag"), dict) and out["antrag"].get("online_url"):
            lk = self.link(out["antrag"]["online_url"])
            out["antrag"] = {**out["antrag"], "online_url": (lk or {}).get("url"), "online_url_geprueft_am": (lk or {}).get("geprueft_am")}

        def k(sql, col="nach"):
            return [self._lname(x[col]) | {"fehlt_im_graph": bool(x["dangling"])} for x in self.con.execute(sql, (lid,))]
        # Kanten (deterministisch – „Code entscheidet")
        out["setzt_voraus"] = k("SELECT * FROM kanten WHERE von=? AND typ='setzt_voraus'")
        out["ist_voraussetzung_fuer"] = k("SELECT * FROM kanten WHERE nach=? AND typ='setzt_voraus'", "von")
        # ungerichtet verwandt (aus Quellen, KEINE Reihenfolge): beide Richtungen
        out["verwandt"] = [x for x in (k("SELECT * FROM kanten WHERE von=? AND typ='verwandt'") +
                                       k("SELECT * FROM kanten WHERE nach=? AND typ='verwandt'", "von"))]
        _seen = set()
        out["verwandt"] = [x for x in out["verwandt"] if not (x["leistung_id"] in _seen or _seen.add(x["leistung_id"]))]
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

    def plz_geo(self, plz: str, grob=True):
        """PLZ → Mittelpunkt. 1) Stellen mit Koordinaten in dieser PLZ (datengetrieben), 2) grob: plz_zentren.json
        (längster PLZ-Präfix, Stadtzentrum). Gibt (lat, lon) oder None; self._plz_genau[plz] sagt, welche Stufe."""
        plz = str(plz or "").strip()
        if not plz:
            return None
        cache = self.__dict__.setdefault("_plz_cache", {})
        if (plz, grob) in cache:
            return cache[(plz, grob)]
        r = self.con.execute("SELECT avg(lat), avg(lon), count(*) FROM stellen WHERE plz=? AND lat IS NOT NULL", (plz,)).fetchone()
        res = ((r[0], r[1]), "plz") if r and r[2] else None
        if not res and grob:
            z = _plz_zentren()
            for n in range(len(plz), 0, -1):
                if plz[:n] in z:
                    res = ((z[plz[:n]][0], z[plz[:n]][1]), "region")
                    break
        self.__dict__.setdefault("_plz_genau", {})[plz] = res[1] if res else None
        cache[(plz, grob)] = res[0] if res else None
        return cache[(plz, grob)]

    def stellen_near(self, plz: str | None = None, typ: str | None = None, leistung_id: str | None = None, limit=10,
                     lat: float | None = None, lon: float | None = None, name: str | None = None) -> dict:
        """Entfernung (Haversine): Stellen-Koordinaten, sonst PLZ-Mittelpunkt der Stelle. Gleiches Bundesland zuerst
        (andere Bundesländer nur, wenn dort nichts ist), dann österreichweite Stellen. Dubletten (Name+Adresse) einmal.
        Leistung ohne eigene Stellen (z. B. hausarzt_pve) → passender Typ; sonst Fallback: Stellen der Träger der Leistung."""
        lid = self.tax.canon(leistung_id) if leistung_id else None
        if lid in LEISTUNG_TYP and not typ:
            typ, lid_filter = LEISTUNG_TYP[lid], None
        else:
            lid_filter = lid

        def query(typ_, lid_, typ_in=None):
            sql, args = "SELECT * FROM stellen WHERE 1=1", []
            if typ_:
                sql += " AND typ=?"
                args.append(typ_)
            if typ_in:
                sql += f" AND typ IN ({','.join('?' * len(typ_in))})"
                args += list(typ_in)
            if lid_:
                sql += " AND zustaendig_fuer LIKE ?"
                args.append(f'%"{lid_}"%')
            if name:
                sql += " AND name LIKE ?"
                args.append(f"%{name}%")
            return [self._stelle(r) for r in self.con.execute(sql, args)]

        rows = query(typ, lid_filter)
        ersatz = None
        if not rows and lid_filter:
            # Keine Stelle für diese Leistung im Datenbestand → Stellen der Träger der Leistung (ehrlich markiert)
            r = self.con.execute("SELECT traeger FROM leistungen WHERE leistung_id=?", (lid_filter,)).fetchone()
            tr = [x for x in _j(r[0], []) if x and len(x) >= 3] if r else []
            if tr:
                cand = query(typ, None, None if typ else ("traeger",))
                rows = [s for s in cand if any(norm(x) in norm(s.get("name") or "") for x in tr)]
                if rows:
                    ersatz = {"grund": f"Keine Einrichtung für '{lid_filter}' im Datenbestand – zuständige Träger-Stellen",
                              "traeger": tr}
        plz = (plz or "").strip()
        bl = plz_bundesland(plz) if plz else None
        origin = (lat, lon) if lat is not None and lon is not None else (self.plz_geo(plz) if plz else None)
        origin_genau = "koordinaten" if lat is not None and lon is not None else (self.__dict__.get("_plz_genau", {}).get(plz) if plz else None)

        def rank(s):
            sp = s.get("plz") or ""
            sbl = bl_norm(s.get("bundesland")) or (plz_bundesland(sp) if sp else None)
            if sbl == "AT":
                tier = 1
            elif bl and sbl and sbl != bl:
                tier = 2
            else:
                tier = 0
            g, geo_art = s.get("geo"), "koordinaten"
            if not g and sp and origin:
                pg = self.plz_geo(sp, grob=False)  # nur datengetrieben – Regions-Mittelpunkte wären für Stellen zu grob
                g, geo_art = (list(pg), "plz_mittelpunkt") if pg else (None, None)
            if origin and g:
                return tier, 0, _haversine(origin, g), ("Entfernung" if geo_art == "koordinaten" else "Entfernung (PLZ-Mittelpunkt)")
            if plz and sp == plz:
                return tier, 1, 0, "gleiche PLZ"
            if plz and sp[:3] == plz[:3] and sp:
                return tier, 2, 0, "gleicher Bezirk/Region"
            if tier == 0 and bl:
                return tier, 3, 0, "gleiches Bundesland"
            if tier == 1:
                return tier, 4, 0, "österreichweit"
            return tier, 5, 0, "anderes Bundesland"

        ranked, seen = [], set()
        for s in rows:
            key = (norm(s.get("name") or ""), norm(s.get("adresse") or "") or s.get("plz") or "")
            if key in seen:
                continue
            seen.add(key)
            tier, stufe, dist, why = rank(s)
            extra = {"naehe": why}
            if why.startswith("Entfernung"):
                ungenau = why != "Entfernung" or origin_genau == "region"
                extra["entfernung_km" if not ungenau else "entfernung_ca_km"] = round(dist, 1 if ungenau else 2)
            ranked.append((tier, stufe, dist, s["name"] or "", s | extra))
        if any(r[0] == 0 for r in ranked):  # Treffer im eigenen Bundesland → andere Bundesländer weglassen
            ranked = [r for r in ranked if r[0] != 2]
        ranked.sort(key=lambda x: x[:4])
        extra = {}
        if typ == "apotheke":
            # D9: Öffnungszeiten fehlen in Wien-OGD, Nachtdienste haben keine offene API (ARCHITEKTUR §5) → deterministischer Verweis
            extra["notdienst"] = APOTHEKEN_NOTDIENST
        out = {"plz": plz, "bundesland": bl, "typ": typ, "leistung_id": leistung_id, **extra,
               "ursprung": origin, "ursprung_genauigkeit": origin_genau, "stellen": [x[-1] for x in ranked[:limit]],
               "hinweis_naehe": "Entfernung (Luftlinie): Koordinaten der Stelle, sonst PLZ-Mittelpunkt (ca.). "
                                "Gleiches Bundesland zuerst, dann österreichweite Stellen."}
        if ersatz:
            out["ersatz"] = ersatz
        return self._envelope(out)

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
            if not (r.get("local_pdf") and r.get("url_status") in ("keine_url", "ersetzt_b") and r["art"] in ("antrag", "beilage")):
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
        if not d["url_pdf"] and el and el.get("url"):
            d["online_seite"], d["online_seite_geprueft_am"] = el["url"], el.get("geprueft_am")
            d["hinweis"] = (d.get("hinweis", "") + "; " if d.get("hinweis") else "") + "Formular auf der Seite des Trägers herunterladen"
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

    # ------------------------------------------------------------------ Formular-Templates/Empfänger (§8.1.5, Modul von kb-forms)
    @staticmethod
    def _forms():
        """knowledge/build/forms/forms_api.py (kb-forms). Fehlt es, antworten die Endpunkte mit 404 'noch nicht verfügbar'."""
        fdir = BUILD / "forms"
        if not (fdir / "forms_api.py").exists():
            return None
        import importlib.util
        path = (fdir / "forms_api.py").resolve()
        name = "lotse_forms_api"  # eigener Modulname: kein Konflikt mit anderen 'forms_api' in sys.modules
        try:
            m = path.stat().st_mtime
            mod = sys.modules.get(name)
            if mod is None or Path(getattr(mod, "__file__", "")).resolve() != path or getattr(mod, "_lotse_mtime", None) != m:
                spec = importlib.util.spec_from_file_location(name, path)
                mod = importlib.util.module_from_spec(spec)
                if str(fdir) not in sys.path:
                    sys.path.insert(0, str(fdir))  # falls forms_api eigene Nachbarmodule importiert
                spec.loader.exec_module(mod)
                mod._lotse_mtime = m
                sys.modules[name] = mod
            return mod
        except Exception:
            return None

    def _nf(self, what):
        return self._envelope({"error": f"{what} noch nicht verfügbar", "status": 404})

    def forms_ontologie(self) -> dict:
        f = self._forms()
        return self._envelope(f.ontologie()) if f else self._nf("Feld-Ontologie")

    def formular_template(self, formular_id: str, nur_geprueft: bool = True) -> dict:
        f = self._forms()
        if not f:
            return self._nf("Formular-Templates")
        t = f.template(formular_id) if nur_geprueft else f.template(formular_id, nur_geprueft=False)
        return self._envelope(t) if t else self._envelope({"error": f"kein {'geprüftes ' if nur_geprueft else ''}Template für '{formular_id}'", "status": 404})

    def formular_empfaenger(self, formular_id: str, plz: str | None = None, traeger: str | None = None) -> dict:
        f = self._forms()
        if not f:
            return self._nf("Empfänger")
        e = f.empfaenger(formular_id, plz=plz, traeger=traeger)
        if not e:
            return self._envelope({"error": f"kein Empfänger für '{formular_id}'", "status": 404})
        # Zuständigkeit je Kandidat-Träger aus dem Träger-Register der DB (einzige Quelle); additiv zu forms_api.zustaendig
        if plz or e.get("bundesland"):
            je = {}
            for tid in e.get("kandidaten") or ([e["traeger_id"]] if e.get("traeger_id") else []):
                r = self.traeger(tid, plz=plz, bundesland=None if plz else e.get("bundesland"))["traeger"]
                if not r:
                    je[tid] = {"status": "unbekannt", "grund": "Träger nicht im Register"}
                    continue
                z = dict(r[0].get("zustaendig") or {})
                st = z.pop("stelle", None)
                if st:
                    z["stelle_id"], z["name"] = st.get("id"), st.get("name")
                    z["post_adresse"] = ", ".join(x for x in (st.get("adresse"), " ".join(y for y in (st.get("plz"), st.get("ort")) if y)) if x) or None
                    z.update({k: st[k] for k in ("telefon", "email", "url", "hinweis") if st.get(k)})
                elif z.get("status") == "zentrale":
                    zt = r[0].get("zentrale") or {}
                    z["post_adresse"] = ", ".join(x for x in (zt.get("adresse"), " ".join(y for y in (zt.get("plz"), zt.get("ort")) if y)) if x) or None
                    z.update({k: zt[k] for k in ("telefon", "email", "url") if zt.get(k)})
                je[tid] = z
            e["zustaendig_je_traeger"] = je
            if len(je) > 1:
                e.setdefault("rueckfragen", [])
                if not any("Pension" in str(x) or "Träger" in str(x) for x in e["rueckfragen"]):
                    e["rueckfragen"].append("Welcher Träger zahlt die Pension bzw. ist zuständig? (" + ", ".join(je) + ")")
            e["zustaendig_quelle"] = "lotse.sqlite traeger/traeger_stellen"
        return self._envelope(e)

    def formular_pdf(self, formular_id: str):
        """(bytes, content_type, filename) der AcroForm-angereicherten Kopie, sonst ('redirect', url) auf die geprüfte Live-URL, sonst None."""
        f = self._forms()
        r = f.pdf(formular_id) if f else None
        if r:
            return r
        k = self._formular_kurz(formular_id) or {}
        if k.get("url_pdf") and not k.get("hinweis"):  # nur echte, geprüfte Datei-URL – nie auf eine Elternseite (HTML) umleiten
            return ("redirect", k["url_pdf"])
        return None

    # ------------------------------------------------------------------ Impfplan (Quelle impfplan, loesungen/05 §6.4)
    def impfplan(self, krankheit: str | None = None, alter: int | None = None) -> dict:
        """Intervalle laut Österreichischem Impfplan (mit Version, wörtlichen Zitaten, Seite). Nur Weitergabe der
        Empfehlung des Plans; Eignung im Einzelfall klärt die Ärztin."""
        if not self.con.execute("SELECT name FROM sqlite_master WHERE name='impfplan_intervalle'").fetchone():
            return self._envelope({"intervalle": [], "error": "Impfplan nicht geladen"})
        sql, args = "SELECT * FROM impfplan_intervalle WHERE 1=1", []
        if krankheit:
            sql += " AND (lower(krankheit) LIKE ? OR lower(impfung) LIKE ? OR id LIKE ?)"
            k = f"%{krankheit.lower()}%"
            args += [k, k, k]
        if alter is not None:
            sql += " AND (alter_von IS NULL OR alter_von <= ?) AND (alter_bis IS NULL OR alter_bis >= ?)"
            args += [alter, alter]
        rows = []
        for r in self.con.execute(sql + " ORDER BY krankheit, alter_von", args):
            d = {k: r[k] for k in r.keys()}
            d["zitate"] = _j(d.pop("zitate_json"), [])
            d["kostenlos_impfprogramm"] = None if d["kostenlos_impfprogramm"] is None else bool(d["kostenlos_impfprogramm"])
            rows.append(d)
        versions = sorted({r["version"] for r in rows})
        return self._envelope({"krankheit": krankheit, "alter": alter, "versionen": versions, "intervalle": rows,
                               "hinweis": "Empfehlung laut Österreichischem Impfplan (Version angegeben). Ob die Impfung im "
                                          "Einzelfall passt, klärt die Ärztin. Fälligkeit nie als „überfällig“ formulieren."})

    # ------------------------------------------------------------------ Träger-Register (§8.1.4)
    def _url_kuratiert(self, url, stand):
        """Link-Regel; kuratierte Träger-URLs, die der Linkcheck (noch) nicht kennt, tragen den Kuratierungsstand."""
        lk = self.link(url)
        if lk and lk.get("url"):
            return lk["url"], lk.get("geprueft_am")
        if lk and lk.get("link_status") == "ungeprueft":
            return url, stand
        return None, None

    def _ts(self, r):
        d = {k: r[k] for k in r.keys()}
        d["url"], d["url_geprueft_am"] = self._url_kuratiert(d["url"], d["stand"])
        d["quelle_url"], _ = self._url_kuratiert(d["quelle_url"], d["stand"])
        return {k: v for k, v in d.items() if v is not None}

    def traeger(self, traeger_id: str | None = None, plz: str | None = None, bundesland: str | None = None) -> dict:
        """Alle Träger (oder einer) mit Landesstellen/Stellen. Mit plz/bundesland zusätzlich die ZUSTÄNDIGE Stelle
        je Träger (aufloesung=landesstelle_nach_bundesland). Referenz auf reimedy-Server über (vocabulary_id, concept_code)."""
        bl = BL_NORM.get(bundesland, bundesland) if bundesland else plz_bundesland(plz)
        sql, args = "SELECT * FROM traeger", []
        if traeger_id:
            sql += " WHERE id=?"
            args.append(traeger_id)
        out = []
        for t in self.con.execute(sql, args).fetchall():
            d = {k: t[k] for k in t.keys()}
            for f in ("sparten", "zentrale_json", "online_json"):
                d[f.replace("_json", "")] = _j(d.pop(f), None)
            if d.get("zentrale") and d["zentrale"].get("url"):
                d["zentrale"]["url"], d["zentrale"]["url_geprueft_am"] = self._url_kuratiert(d["zentrale"]["url"], d["stand"])
            d["quelle_url"], _ = self._url_kuratiert(d["quelle_url"], d["stand"])
            d["reimedy_ref"] = ({"vocabulary_id": d.pop("reimedy_vocabulary_id"), "concept_code": d.pop("reimedy_concept_code"),
                                 "concept_id": d.pop("reimedy_concept_id")} if d.get("reimedy_concept_code") else None)
            for k in ("reimedy_vocabulary_id", "reimedy_concept_code", "reimedy_concept_id"):
                d.pop(k, None)
            stellen = [self._ts(r) for r in self.con.execute(
                "SELECT * FROM traeger_stellen WHERE traeger_id=? ORDER BY rolle, bundesland, name", (t["id"],))]
            d["stellen"] = stellen
            if bl:
                if d["nur_bundesland"] and d["nur_bundesland"] != bl:
                    d["zustaendig"] = {"status": "nicht_zustaendig", "grund": f"nur für Bundesland {d['nur_bundesland']}"}
                elif d["aufloesung"] == "landesstelle_nach_bundesland":
                    hit = [s for s in stellen if s.get("bundesland") == bl and s.get("rolle") in ("landesstelle", "aussenstelle")]
                    hit.sort(key=lambda s: s.get("rolle") != "landesstelle")
                    d["zustaendig"] = ({"status": "landesstelle", "bundesland": bl, "stelle": hit[0]} if hit else
                                       {"status": "zentrale", "bundesland": bl, "grund": "keine Landesstelle für dieses Bundesland im Register"})
                elif d["aufloesung"] == "regional_unbekannt":
                    d["zustaendig"] = {"status": "rueckfrage", "grund": d.get("kontakt_hinweis")}
                else:
                    d["zustaendig"] = {"status": "zentrale"}
            out.append(d)
        return self._envelope({"plz": plz, "bundesland": bl, "traeger": out,
                               "hinweis_plz": "Bundesland aus PLZ abgeleitet (grob, Grenzfälle per bundesland= überschreiben)" if plz and not bundesland else None})

    def health(self) -> dict:
        rep = _j(self._meta("report"), {})
        return self._envelope({"db": self.db_path.name, "built_at": self.built_at,
                               "quellen": [dict(r) | {"errors_json": None, "manifest_json": None}
                                           for r in self.con.execute("SELECT * FROM quellen")],
                               "leistungen": rep.get("leistungen", {}).get("nach_status"),
                               "documents": rep.get("documents"), "stellen": rep.get("stellen"), "formulare": rep.get("formulare"),
                               "links": rep.get("links"), "embeddings": rep.get("embeddings"), "gates": _j(self._meta("gates"), None),
                               "uebersprungen": rep.get("uebersprungen")})


# ---------------------------------------------------------------------- HTTP
def _built_at(path: Path):
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        r = c.execute("SELECT value FROM meta WHERE key='built_at'").fetchone()
        c.close()
        return r[0] if r else None
    except sqlite3.Error:
        return None


def ensure_db(db: Path = DB_PATH) -> str:
    """Container: DB_PATH liegt auf dem Volume. Ist es leer oder die im Image gebaute DB neuer (Redeploy mit neuen Daten),
    wird die Image-DB atomar dorthin kopiert. Ein neuerer nächtlicher Stand im Volume bleibt unangetastet."""
    import shutil
    bundled = BUILD / "lotse.sqlite"
    if db.resolve() == bundled.resolve() or not bundled.exists():
        return "lokal"
    vb, bb = _built_at(db) if db.exists() else None, _built_at(bundled)
    if vb and (not bb or vb >= bb):
        return f"volume ({vb})"
    db.parent.mkdir(parents=True, exist_ok=True)
    tmp = db.with_suffix(".sqlite.seed")
    shutil.copy2(bundled, tmp)
    tmp.replace(db)
    for f in ("build_report.json", "snapshot.json", "graph.json"):
        if (BUILD / f).exists() and not (db.parent / f).exists():
            shutil.copy2(BUILD / f, db.parent / f)
    return f"aus Image übernommen ({bb}, Volume hatte {vb})"


def serve(port=8765, db=DB_PATH, host=None):
    import os
    host = host or os.environ.get("HOST", "127.0.0.1")
    print(f"DB: {ensure_db(db)}")
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
                return self._send(L.stellen_near(q.get("plz"), q.get("typ"), q.get("leistung_id") or q.get("leistung"), int(q.get("limit", 10)),
                                                 float(q["lat"]) if q.get("lat") else None, float(q["lon"]) if q.get("lon") else None,
                                                 name=q.get("name")))
            if p == "/forms/ontologie":
                d = L.forms_ontologie()
                return self._send(d, d.get("status", 200))
            if m := re.fullmatch(r"/formular/([A-Za-z0-9_\-]+)/template", p):
                d = L.formular_template(m[1], q.get("alle") != "1")
                return self._send(d, d.get("status", 200))
            if m := re.fullmatch(r"/formular/([A-Za-z0-9_\-]+)/empfaenger", p):
                d = L.formular_empfaenger(m[1], q.get("plz"), q.get("traeger"))
                return self._send(d, d.get("status", 200))
            if m := re.fullmatch(r"/formular/([A-Za-z0-9_\-]+)/pdf", p):
                r = L.formular_pdf(m[1])
                if not r:
                    k = L._formular_kurz(m[1]) or {}
                    return self._send({"error": f"kein geprüftes PDF für '{m[1]}'",
                                       **{x: k[x] for x in ("online_seite", "url_pdf", "local_pdf", "hinweis") if k.get(x)}}, 404)
                if r[0] == "redirect":
                    self.send_response(302)
                    self.send_header("Location", r[1])
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    return
                body, ctype, fname = r
                self.send_response(200)
                self.send_header("Content-Type", ctype or "application/pdf")
                self.send_header("Content-Disposition", f'inline; filename="{fname}"')
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return
            if m := re.fullmatch(r"/formular/([A-Za-z0-9_\-]+)", p):
                f = L.formular(m[1])
                return self._send(f, 404 if f.get("error") and "unbekannt" in f["error"] else 200)
            if m := re.fullmatch(r"/code/([^/]+)/([^/]+)", p):
                from urllib.parse import unquote
                return self._send(L.lookup_code(unquote(m[1]), unquote(m[2])))
            if p == "/codes":
                return self._send(L.search_codes(q.get("q", ""), q.get("system")))
            if p == "/traeger" or (m := re.fullmatch(r"/traeger/([a-z_]+)", p)):
                tid = q.get("id") or (m[1] if p != "/traeger" else None)
                return self._send(L.traeger(tid, q.get("plz"), q.get("bundesland")))
            if p == "/impfplan":
                return self._send(L.impfplan(q.get("krankheit"), int(q["alter"]) if q.get("alter", "").isdigit() else None))
            if p == "/misses":
                return self._send(L.misses())
            self._send({"error": "unbekannter Pfad", "pfade": ["/health", "/search", "/leistung/<id>", "/stellen", "/formular/<id>", "/formular/<id>/template",
                                                              "/formular/<id>/empfaenger", "/formular/<id>/pdf", "/forms/ontologie", "/traeger",
                                                              "/triggers (POST)", "/misses"]}, 404)

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
