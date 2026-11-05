"""Gemeinsame Helfer für die Wissens-DB: Pfade, Normalisierung, Schema-Validierung (CONTRACT.md A–D)."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

BUILD = Path(__file__).resolve().parent
KNOWLEDGE = BUILD.parent
ROOT = KNOWLEDGE.parent
SOURCES = KNOWLEDGE / "sources"
# Container (B8): DB_PATH zeigt auf das Volume (z. B. /data/lotse.sqlite), damit das nächtliche update.py ohne Redeploy tauscht.
DB_PATH = Path(os.environ.get("DB_PATH") or BUILD / "lotse.sqlite")
# Laufzeit-Zustand (snapshot, build_report, changes, review_queue, misses, logs) liegt neben der DB → überlebt Redeploys.
STATE_DIR = Path(os.environ.get("STATE_DIR") or DB_PATH.parent)


def rel(p) -> str:
    """Pfad relativ zum Repo (für Berichte/Health), sonst nur der Dateiname – nie absolute lokale Pfade ausliefern."""
    p = Path(p)
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return p.name

SOURCE_IDS = ["oegk", "aek_wien", "fsw", "svs", "bvaeb", "sozdok_ris", "gesundheit_gv", "oesterreich_gv", "svbox_local"]
BEREICHE = {"A": "Vorsorge", "B": "Gesundheitsförderung", "C": "Behandlung/Reha/Nachsorge",
            "D": "Pflege", "E": "Sozial/Finanziell", "F": "Administration"}
BUNDESLAENDER = {"AT", "W", "N", "B", "O", "S", "St", "ST", "K", "T", "V", "STMK", "NÖ", "OÖ"}
DOC_TYPES = {"leistungsinfo", "formular", "recht", "kontakt", "faq", "broschuere", "tarif"}
STELLEN_TYPEN = {"traeger", "beratung", "einrichtung", "hotline", "arzt", "apotheke", "pve"}
CONFIDENCE = {"hoch", "mittel", "niedrig"}
CONF_RANK = {"hoch": 3, "mittel": 2, "niedrig": 1, None: 0}

# --------------------------------------------------------------------------- Normalisierung
_UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ẞ": "ss"})
_SUFFIXES = ("ungen", "innen", "ungs", "en", "er", "es", "em", "e", "n", "s")


def norm(text: str | None) -> str:
    """Kleinschreibung, Umlaute → ae/oe/ue/ss, restliche Diakritika weg, Soft-Hyphen/Trennstriche am Zeilenende weg.
    So findet „Pflegegeldantrag", „pflegegeld-antrag" und „Pflegegéld" dasselbe; „Ärztin" == „Aerztin"."""
    if not text:
        return ""
    t = text.replace("­", "").replace("-\n", "")
    t = t.translate(_UML).lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


def stem(tok: str) -> str:
    """Sehr leichtes deutsches Stemming (nur Endungen), damit „Leistungen"→„leist", „Anträge"→„antraeg"."""
    for suf in _SUFFIXES:
        if len(tok) > len(suf) + 3 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


STOP = set("der die das den dem des ein eine einer eines einem und oder in im ist sind fuer mit von zu zum zur auf an "
           "bei was wie wo wer ich mein meine meiner mir mich sie ihr es wir kann muss habe hat haben nicht auch noch "
           "bekomme bekommt gibt es welche welcher welches man denn da jetzt so machen mache macht brauche braucht brauchen tun bitte gerne unsere unser als mehr mutter mama vater papa oma opa tochter sohn eltern frau mann".split())


def fts_query(q: str) -> str:
    """Freitext → FTS5-MATCH-Ausdruck: normalisieren, Stoppwörter weg, Stamm + Präfix, OR-verknüpft (bm25 sortiert)."""
    toks = [t for t in re.findall(r"[a-z0-9]+", norm(q)) if t not in STOP and len(t) > 1]
    parts = []
    for t in toks:
        s = stem(t)
        parts.append(f'"{s}"*' if len(s) >= 3 else f'"{s}"')
    return " OR ".join(dict.fromkeys(parts))


NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


AMOUNT_RE = re.compile(r"(\d+(?:[.,]\d+)*)\s*(?:€|euro\b|eur\b|prozent\b|%|stunden\b|h\b)", re.I)
AMOUNT_RE2 = re.compile(r"(?:€|eur)\s*(\d+(?:[.,]\d+)*)", re.I)


def numbers(text: str | None) -> set[str]:
    """Beträge/Prozent/Stunden (mit Einheit) aus einem Text – Grundlage der Konflikterkennung.
    Zahlen ohne Einheit (Paragraphen, Jahreszahlen, Rechenbeispiel-Zeilen) zählen nicht."""
    if not text:
        return set()
    t = str(text)
    return {n.replace(".", "").replace(",", ".") for n in AMOUNT_RE.findall(t) + AMOUNT_RE2.findall(t)}


# --------------------------------------------------------------------------- Validierung
class Problems:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def _req(rec, keys, p: Problems, where):
    ok = True
    for k in keys:
        if rec.get(k) in (None, "", []):
            p.err(f"{where}: Pflichtfeld '{k}' fehlt/leer")
            ok = False
    return ok


def _list(rec, k, p, where, allowed=None):
    v = rec.get(k)
    if v is None:
        return
    if isinstance(v, str):
        p.warn(f"{where}: '{k}' sollte Liste sein, ist String – wird zu [{v!r}]")
        rec[k] = [v]
        v = rec[k]
    if not isinstance(v, list):
        p.err(f"{where}: '{k}' muss Liste sein")
        return
    if allowed:
        bad = [x for x in v if x not in allowed]
        if bad:
            p.warn(f"{where}: '{k}' unbekannte Werte {bad}")


def validate_document(r, p, where):
    ok = _req(r, ["id", "source_id", "url", "text"], p, where)
    _list(r, "bereich", p, where, BEREICHE)
    _list(r, "bundesland", p, where, BUNDESLAENDER)
    _list(r, "traeger", p, where)
    if r.get("doc_type") and r["doc_type"] not in DOC_TYPES:
        p.warn(f"{where}: doc_type '{r['doc_type']}' nicht im Vertrag")
    if len(r.get("text") or "") > 4000:
        p.warn(f"{where}: text {len(r['text'])} Zeichen (>~2000 laut Vertrag) – Chunking prüfen")
    if not r.get("fetched_at"):
        p.warn(f"{where}: fetched_at fehlt → kein Stand-Datum zitierbar")
    return ok


def validate_leistung(r, p, where):
    ok = _req(r, ["leistung_id", "name"], p, where)
    lid = r.get("leistung_id") or ""
    if lid and not re.fullmatch(r"[a-z0-9_]+", lid):
        p.err(f"{where}: leistung_id '{lid}' nicht snake_case")
        ok = False
    for k in ("bereich", "traeger", "unterlagen", "fristen", "abhaengigkeiten", "trigger_im_dokument", "bundesland", "quellen", "voraussetzungen"):
        _list(r, k, p, where, BEREICHE if k == "bereich" else None)
    for i, v in enumerate(r.get("voraussetzungen") or []):
        if isinstance(v, str):
            r["voraussetzungen"][i] = {"text": v}
            p.warn(f"{where}: voraussetzungen[{i}] ohne quelle_url/zitat")
    if not r.get("quellen"):
        p.err(f"{where}: keine 'quellen' → Aussage nicht belegbar")
        ok = False
    if r.get("confidence") and r["confidence"] not in CONFIDENCE:
        p.warn(f"{where}: confidence '{r['confidence']}' unbekannt")
    return ok


def validate_stelle(r, p, where):
    ok = _req(r, ["stelle_id", "name"], p, where)
    if r.get("typ") and r["typ"] not in STELLEN_TYPEN:
        p.warn(f"{where}: typ '{r['typ']}' nicht im Vertrag")
    _list(r, "zustaendig_fuer", p, where)
    if r.get("plz") and not re.fullmatch(r"\d{4}", str(r["plz"])):
        p.warn(f"{where}: plz '{r['plz']}' nicht 4-stellig")
    return ok


def validate_formular(r, p, where):
    ok = _req(r, ["formular_id", "name"], p, where)
    _list(r, "leistung_ids", p, where)
    _list(r, "felder", p, where)
    return ok


CODE_SYSTEMS = {"ICD-10-AT", "ATC", "BASG", "EKO", "SNOMED-Fachrichtung"}


def validate_code(r, p, where):
    ok = _req(r, ["system", "code", "label_de"], p, where)
    if r.get("system") and r["system"] not in CODE_SYSTEMS:
        p.warn(f"{where}: system '{r['system']}' nicht im Vertrag")
    _list(r, "leistung_hints", p, where)
    if not r.get("quelle_url"):
        p.warn(f"{where}: quelle_url fehlt")
    return ok


def code_norm(code: str) -> str:
    """'c20.0 ' → 'C20.0'; ICD ohne Punkt ('C200') bleibt, Lookup probiert Varianten."""
    return re.sub(r"\s+", "", str(code or "")).upper()


VALIDATORS = {"codes": validate_code, "documents": validate_document, "leistungen": validate_leistung,
              "stellen": validate_stelle, "formulare": validate_formular}


def read_jsonl(path: Path, kind: str, p: Problems, label: str):
    """Liest JSONL, validiert jede Zeile, gibt nur gültige Datensätze zurück."""
    out = []
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            where = f"{label}/{path.name}:{n}"
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                p.err(f"{where}: kein gültiges JSON ({e.msg})")
                continue
            if not isinstance(rec, dict):
                p.err(f"{where}: Zeile ist kein Objekt")
                continue
            if VALIDATORS[kind](rec, p, where):
                out.append(rec)
    return out


def jdump(v) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)
