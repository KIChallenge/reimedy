"""Minimaler OpenAI-kompatibler Client (Azure-Deployment des Hackathons) für Offline-Schritte.

Liest LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_STRONG aus der Umgebung oder aus der Datei in LLM_ENV_FILE
(Standard: ../_reimedy_svhack/.env). Der Key wird nie ausgegeben oder geschrieben.
Nur für den Build (Semantik-Zuordnung, Vision-Prüfung); Ergebnisse werden eingefroren.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

DEFAULT_ENV = Path(__file__).resolve().parents[4] / "_reimedy_svhack" / ".env"


def _env() -> dict:
    e = {k: os.environ.get(k) for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL_STRONG", "LLM_MODEL_FAST")}
    p = Path(os.environ.get("LLM_ENV_FILE", DEFAULT_ENV))
    if not all(e.values()) and p.is_file():
        for line in p.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() in e and not e[k.strip()]:
                    e[k.strip()] = v.strip().strip('"').strip("'")
    return e


def available() -> bool:
    e = _env()
    return bool(e["LLM_BASE_URL"] and e["LLM_API_KEY"])


def chat_json(prompt: str, system: str = "", images: list[bytes] | None = None, timeout: float = 120) -> dict:
    import httpx
    e = _env()
    content: list | str = prompt
    if images:
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}} for b in images]
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
    body = {"model": e["LLM_MODEL_STRONG"] or e["LLM_MODEL_FAST"], "messages": msgs,
            "response_format": {"type": "json_object"}}
    r = httpx.post(e["LLM_BASE_URL"].rstrip("/") + "/chat/completions", json=body, timeout=timeout,
                   headers={"api-key": e["LLM_API_KEY"], "Authorization": f"Bearer {e['LLM_API_KEY']}"})
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"].strip()
    txt = txt.removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(txt)
