"""Semantik-Schicht (ARCHITEKTUR §1): lokales multilinguales Embedding (fastembed/ONNX) + sqlite-vec, modell-agnostisch.

Modellwahl (Reihenfolge): Env LOTSE_EMB_MODEL → build/emb_model.txt → DEFAULT_MODEL. Jedes fastembed-TextEmbedding-Modell geht
(paraphrase-multilingual-MiniLM-L12-v2, paraphrase-multilingual-mpnet-base-v2, minishlab/potion-multilingual-128M, e5 …).
Cache: build/emb_cache/<modell>.npz – Schlüssel = sha256 des eingebetteten Textes, Vektoren L2-normiert, int8 (×127).
Nur neue/geänderte Abschnitte werden gerechnet; das Docker-Build (B8) rechnet bei unverändertem Stand nichts.
Ohne fastembed/sqlite-vec/numpy läuft alles weiter (nur FTS) – kein harter Abhängigkeitsbruch.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path

from common import BUILD, rel

DEFAULT_MODEL = "minishlab/potion-multilingual-128M"  # Benchmark 7/7 (ARCHITEKTUR §1); Override: emb_model.txt / LOTSE_EMB_MODEL
CACHE_DIR = BUILD / "emb_cache"
MODEL_FILE = BUILD / "emb_model.txt"


def model_name() -> str:
    if os.environ.get("LOTSE_EMB_MODEL"):
        return os.environ["LOTSE_EMB_MODEL"].strip()
    if MODEL_FILE.exists() and MODEL_FILE.read_text().strip():
        return MODEL_FILE.read_text().strip()
    return DEFAULT_MODEL


def available() -> tuple[bool, str]:
    try:
        import numpy  # noqa: F401
        import sqlite_vec  # noqa: F401
        from fastembed import TextEmbedding  # noqa: F401
        return True, ""
    except Exception as e:  # pragma: no cover
        return False, f"{type(e).__name__}: {e}"


def load_vec(con: sqlite3.Connection) -> bool:
    try:
        import sqlite_vec
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
        return True
    except Exception:
        return False


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Embedder:
    _instances: dict[str, "Embedder"] = {}

    def __init__(self, model: str | None = None):
        from fastembed import TextEmbedding
        self.model = model or model_name()
        self.m = TextEmbedding(self.model)
        self.e5 = "e5" in self.model.lower()
        self.dim = len(next(iter(self.m.embed(["x"]))))

    @classmethod
    def get(cls, model: str | None = None) -> "Embedder":
        m = model or model_name()
        if m not in cls._instances:
            cls._instances[m] = Embedder(m)
        return cls._instances[m]

    def _norm(self, v):
        import numpy as np
        v = np.asarray(v, dtype=np.float32)
        n = np.linalg.norm(v, axis=-1, keepdims=True)
        n[n == 0] = 1
        return v / n

    def query(self, text: str):
        t = ("query: " + text) if self.e5 else text
        return self._norm(next(iter(self.m.embed([t]))))

    def passages(self, texts: list[str], batch=64):
        ts = [("passage: " + t) if self.e5 else t for t in texts]
        return self._norm(list(self.m.embed(ts, batch_size=batch)))


def cache_path(model: str) -> Path:
    return CACHE_DIR / (model.replace("/", "__") + ".npz")


def load_cache(model: str):
    import numpy as np
    p = cache_path(model)
    if not p.exists():
        return {}
    z = np.load(p, allow_pickle=False)
    return dict(zip(z["keys"].tolist(), z["q"]))


def save_cache(model: str, cache: dict):
    import numpy as np
    CACHE_DIR.mkdir(exist_ok=True)
    keys = sorted(cache)
    q = np.stack([cache[k] for k in keys]) if keys else np.zeros((0, 0), dtype=np.int8)
    tmp = cache_path(model).with_suffix(".tmp.npz")
    np.savez_compressed(tmp, keys=np.array(keys), q=q)
    tmp.replace(cache_path(model))


def build_vectors(con: sqlite3.Connection, items: dict[str, list[tuple[int, str]]], model: str | None = None,
                  quiet=False) -> dict:
    """items: {"doc_vec": [(rowid, text)], "leist_vec": [...]}. Legt vec0-Tabellen an. Gibt Statistik zurück."""
    import numpy as np
    ok, why = available()
    if not ok:
        return {"aktiv": False, "grund": why}
    if not load_vec(con):
        return {"aktiv": False, "grund": "sqlite-vec lässt sich nicht laden"}
    model = model or model_name()
    t0 = time.time()
    cache = load_cache(model)
    emb = None
    stats = {"aktiv": True, "modell": model, "neu_berechnet": 0, "aus_cache": 0}
    used = set()
    for table, rows in items.items():
        keys = [_key(t) for _, t in rows]
        missing = [(i, rows[i][1]) for i, k in enumerate(keys) if k not in cache]
        if missing:
            emb = emb or Embedder.get(model)
            if not quiet:
                print(f"  Embeddings {table}: {len(missing)} neu ({model}) …", file=sys.stderr, flush=True)
            B = 512
            for s in range(0, len(missing), B):
                chunk = missing[s:s + B]
                vecs = emb.passages([t for _, t in chunk])
                for (i, _), v in zip(chunk, vecs):
                    cache[keys[i]] = np.clip(np.round(v * 127), -127, 127).astype(np.int8)
                if not quiet and s and s % (B * 10) == 0:
                    print(f"    {s}/{len(missing)}", file=sys.stderr, flush=True)
            stats["neu_berechnet"] += len(missing)
            save_cache(model, cache)  # Zwischenstand sichern
        stats["aus_cache"] += len(rows) - len(missing)
        dim = len(next(iter(cache.values())))
        con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(f"CREATE VIRTUAL TABLE {table} USING vec0(embedding float[{dim}] distance_metric=cosine)")
        data = []
        for (rowid, _), k in zip(rows, keys):
            used.add(k)
            v = cache[k].astype(np.float32) / 127.0
            v /= (np.linalg.norm(v) or 1.0)
            data.append((rowid, v.astype(np.float32).tobytes()))
        con.executemany(f"INSERT INTO {table}(rowid, embedding) VALUES (?, ?)", data)
        stats["dim"] = dim
    # Cache auf benutzte Schlüssel trimmen (kein unbegrenztes Wachstum im Repo)
    pruned = {k: v for k, v in cache.items() if k in used}
    if len(pruned) != len(cache) or stats["neu_berechnet"]:
        save_cache(model, pruned)
    stats["sekunden"] = round(time.time() - t0, 1)
    stats["cache_datei"] = rel(cache_path(model))
    return stats
