# allergene – häufige Allergene und Unverträglichkeiten

Stand: 06.11.2026. Aufruf: `uv run knowledge/sources/allergene/ingest.py` (kein Netzwerk; die Liste steht im Skript).

## Ausgabe
| Datei | Inhalt |
|---|---|
| `codes.jsonl` | `system: "Allergen"` (Schema E), je Eintrag `kategorie`, `synonyme`, optional `snomed` |

Kategorien: Lebensmittel (die 14 kennzeichnungspflichtigen Allergene nach LMIV Anhang II plus häufige weitere), Unverträglichkeit, Pollen und Umwelt, Tiere, Insekten, Kontakt, Arzneimittel-Gruppen.

## Wofür
Vorschläge im Profil unter „Allergien und Unverträglichkeiten“ (`/api/codes?system=Allergie`). Die Suche findet auch über die `synonyme` (der Build indexiert sie in `codes_fts`), etwa „Nuss“ → Haselnuss, Erdnüsse, Nüsse (Schalenfrüchte).

Arzneimittel kommen aus zwei weiteren Quellen:
- **Wirkstoffe:** ATC aus `svbox_local` (Erstattungskodex-Datei `atccode.txt`).
- **Markennamen:** live aus dem BASG-Register der reimedy-Knowledge-API (`REIMEDY_KB_URL`, Standard `https://reimedy-server.mynu.me`, `GET /api/concepts/search?domain=Drug`). Dazu gehört je Präparat der Wirkstoff (Aspirin → Acetylsalicylsäure). Das Register wird bewusst nicht kopiert (siehe `reimedy_kb/SOURCE.md`, BASG).

## Grenzen
- Nur Namen zum Erfassen eigener Angaben. Keine Aussage über Schwere, Häufigkeit oder Kreuzreaktionen, keine Deutung.
- SNOMED-Codes nur dort, wo sie am reimedy-server geprüft wurden (Erdnüsse, Baumnüsse, Pollen, Hausstaubmilben, Wespengift, Latex); sonst `null`.
- Kuratiert vom Lotse-Team. Ergänzungen direkt in `ALLERGENE` in `ingest.py`, danach Ingest und Build neu ausführen.
