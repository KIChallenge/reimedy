"""Kuratierte Taxonomie (taxonomie.json) – ersetzt aliases.json.

- varianten            → DIESELBE Leistung (Merge)
- traeger_auspraegungen → Quell-ID wird Träger-Ausprägung der Leistung (z. B. unterstuetzungsfonds_bvaeb → unterstuetzungsfonds[BVAEB])
- automatisch: <id>_<traeger> mit <id> in der Taxonomie → Ausprägung (wenn <id>_<traeger> nicht selbst Eintrag ist)
- eltern               → Kante teil_von (eigene Leistung, KEIN Merge)
- nicht_verwechseln_mit, alternative_zu → Kanten (kein Merge)
"""
from __future__ import annotations

import json
from pathlib import Path

from common import BUILD

TAX_PATH = BUILD / "taxonomie.json"
TRAEGER_SUFFIX = {"oegk": "ÖGK", "svs": "SVS", "bvaeb": "BVAEB", "pva": "PVA", "auva": "AUVA"}


class Taxonomie:
    def __init__(self, path: Path = TAX_PATH):
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"leistungen": []}
        self.entries = {e["id"]: e for e in data["leistungen"]}
        self.var = {}
        self.aus = {}
        for e in self.entries.values():
            for v in e.get("varianten", []):
                self.var[v] = e["id"]
            for tr, ids in (e.get("traeger_auspraegungen") or {}).items():
                for i in ids:
                    self.aus[i] = (e["id"], tr)

    def resolve(self, raw: str) -> tuple[str, str | None]:
        """raw leistung_id → (kanonische id, Träger-Ausprägung oder None)."""
        if raw in self.entries:
            return raw, None
        if raw in self.var:
            return self.var[raw], None
        if raw in self.aus:
            return self.aus[raw]
        base, _, suf = raw.rpartition("_")
        if suf in TRAEGER_SUFFIX and base:
            b = base if base in self.entries else self.var.get(base)
            if b:
                return b, TRAEGER_SUFFIX[suf]
        return raw, None

    def canon(self, raw: str) -> str:
        return self.resolve(raw)[0]

    def edges(self):
        for e in self.entries.values():
            if e.get("eltern"):
                yield e["id"], e["eltern"], "teil_von"
            for x in e.get("nicht_verwechseln_mit", []):
                yield e["id"], x, "nicht_verwechseln_mit"
            for x in e.get("alternative_zu", []):
                yield e["id"], x, "alternative_zu"

    def info(self, lid):
        e = self.entries.get(lid)
        if not e:
            return {}
        return {k: e.get(k) for k in ("typ", "notiz") if e.get(k)}
