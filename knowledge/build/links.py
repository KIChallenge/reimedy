"""Live-Links (ARCHITEKTUR §3): lädt build/links/links.jsonl + formulare_live.jsonl (geliefert von linkcheck/kb-links).

links(url PK, kind, final_url, http_status, content_type, bytes, sha256, checked_at, last_ok_at, fail_count,
      first_seen, ersetzt_durch, eltern_url, data_json)
formulare_live ist KANONISCH für die Tabelle formulare: überschreibt url_pdf/sha256/version/art/felder und
liefert alias_ids (Quell-formular_ids → kanonische ID).
Die API (search.py) liefert nur Links mit last_ok_at < LINK_MAX_AGE_DAYS.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from common import BUILD, jdump, rel

LINKS_DIR = BUILD / "links"
LINK_MAX_AGE_DAYS = 7
FORMULAR_ARTEN_AUSBLENDEN = {"tarif_vertrag", "video", "info_seite"}

LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS links(url TEXT PRIMARY KEY, kind TEXT, final_url TEXT, http_status INT, content_type TEXT,
  bytes INT, sha256 TEXT, checked_at TEXT, last_ok_at TEXT, fail_count INT, first_seen TEXT, ersetzt_durch TEXT,
  eltern_url TEXT, ok INT, ersatz_regel TEXT, data_json TEXT);
CREATE INDEX IF NOT EXISTS links_final ON links(final_url);
"""
COLS = ["url", "kind", "final_url", "http_status", "content_type", "bytes", "sha256", "checked_at", "last_ok_at",
        "fail_count", "first_seen", "ersetzt_durch", "eltern_url", "ok", "ersatz_regel"]


def _jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                pass
    return out


def read_formulare_live(links_dir: Path = LINKS_DIR):
    """Normalisiert das kb-links-Format: url → url_pdf, gefunden_auf[].formular_id → alias_ids, lotse_zeigen → zeigen."""
    out = []
    for f in _jsonl(links_dir / "formulare_live.jsonl"):
        if not f.get("formular_id"):
            continue
        f = dict(f)
        st = f.get("url_status")
        if "url_pdf" not in f:  # älteres Format: url = Datei-URL, außer bei Elternseiten-Ersatz
            f["url_pdf"] = f.get("url") if st not in ("ersetzt_b", "tot", "keine_url") else None
        if st == "ersetzt_b" and f.get("url"):
            f["eltern_url"] = f["url"]  # Elternseite: „Formular dort herunterladen", NIE als PDF ausgeben
            f["quelle_url"] = f.get("quelle_url") or f["url"]
        ga = f.get("gefunden_auf") or []
        f.setdefault("alias_ids", [g.get("formular_id") for g in ga if isinstance(g, dict) and g.get("formular_id")])
        f["zeigen"] = f.get("lotse_zeigen", True) is not False
        out.append(f)
    return out


def load_links(con: sqlite3.Connection, links_dir: Path = LINKS_DIR) -> dict:
    con.executescript(LINKS_SCHEMA)
    con.execute("DELETE FROM links")
    rows = _jsonl(links_dir / "links.jsonl")
    for r in rows:
        if not r.get("url"):
            continue
        con.execute(f"INSERT OR REPLACE INTO links({','.join(COLS)},data_json) VALUES ({','.join('?' * (len(COLS) + 1))})",
                    [r.get(c) for c in COLS] + [jdump({k: v for k, v in r.items() if k not in COLS and k not in ("refs", "kinds")})])
    n_ok = con.execute("SELECT count(*) FROM links WHERE ok AND last_ok_at IS NOT NULL AND "
                       f"julianday('now') - julianday(last_ok_at) < {LINK_MAX_AGE_DAYS}").fetchone()[0]
    return {"links": len(rows), "frisch_ok": n_ok, "quelle": rel(links_dir / "links.jsonl"),
            "formulare_live": len(read_formulare_live(links_dir))}
