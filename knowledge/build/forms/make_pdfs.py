"""AcroForm-angereicherte Kopien flacher PDFs (ARCHITEKTUR §8.1.2) → forms/pdf/<formular_id>@<sha12>.pdf

  uv run --no-project --with pymupdf knowledge/build/forms/make_pdfs.py

Nur für geprüfte Templates mit quelle=generiert und nur, wenn Herkunft/Lizenz das erlaubt:
Formulare von Sozialversicherungsträgern und Bundesbehörden sind amtliche Werke (§ 7 UrhG: Körperschaften öffentlichen
Rechts) – die Kopie ändert den Inhalt nicht, sie legt nur Eingabefelder über die vorhandenen Ausfüllbereiche.
Andere Herkünfte (FSW, Vereine, Ärztekammer, Gemeinden …) bekommen nur das Template; Michi füllt dort per Overlay.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fill import acroform_kopie  # noqa: E402

ERLAUBT = {"SVS", "BVAEB", "ÖGK", "PVA", "AUVA", "Sozialministeriumservice", "KV/PV", "PVA, BVAEB", "PVA, SVS, BVAEB",
           "SV (Träger im Formular wählen)"}
ERLAUBT_PREFIX = ("svs_", "bvaeb_", "oegk_", "pva_", "sms_", "auva_")


def erlaubt(t: dict) -> tuple[bool, str]:
    if t.get("traeger") in ERLAUBT or t["formular_id"].startswith(ERLAUBT_PREFIX):
        return True, "amtliches Werk eines SV-Trägers bzw. einer Bundesbehörde (§ 7 UrhG)"
    return False, f"Herkunft {t.get('traeger') or 'unbekannt'}: keine Kopie, nur Template (Overlay)"


def main():
    out_dir = HERE / "pdf"
    out_dir.mkdir(exist_ok=True)
    n, skip = 0, {}
    keep = set()
    for p in sorted((HERE / "templates").glob("*.json")):
        t = json.loads(p.read_text())
        if t["quelle"] != "generiert" or not t.get("geprueft") or not t["felder"]:
            continue
        ok, grund = erlaubt(t)
        if not ok:
            skip[t["formular_id"]] = grund
            continue
        src = HERE / "cache" / f"{t['sha256']}.pdf"
        if not src.exists():
            continue
        dst = out_dir / f"{t['formular_id']}@{t['sha256'][:12]}.pdf"
        dst.write_bytes(acroform_kopie(t, src.read_bytes()))
        keep.add(dst.name)
        n += 1
    for old in out_dir.glob("*.pdf"):
        if old.name not in keep:
            old.unlink()
    (HERE / "pdf" / "LIZENZ.md").write_text(
        "# AcroForm-angereicherte Kopien\n\nNur Formulare von SV-Trägern und Bundesbehörden (amtliche Werke, § 7 UrhG). "
        "Der Inhalt ist unverändert; ergänzt sind nur Eingabefelder (Name = feld_id des Templates). "
        "Kanonisch bleibt die Live-URL des Trägers (ARCHITEKTUR §3).\n\nOhne Kopie (nur Template):\n" +
        "".join(f"- {k}: {v}\n" for k, v in sorted(skip.items())))
    print(n, "Kopien,", len(skip), "ohne Kopie (Herkunft)", file=sys.stderr)


if __name__ == "__main__":
    main()
