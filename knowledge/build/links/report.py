#!/usr/bin/env python3
"""Erzeugt links/REPORT.md aus links.jsonl, formulare_live.jsonl, seed_status.json, review_queue.jsonl.

    python3 knowledge/build/links/report.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent


def jl(p):
    p = HERE / p
    return [json.loads(x) for x in p.open(encoding="utf-8")] if p.exists() else []


def pct(a, b):
    return f"{100 * a / b:.1f} %" if b else "–"


def main():
    links = jl("links.jsonl")
    forms = jl("formulare_live.jsonl")
    review = jl("review_queue.jsonl")
    seed = json.loads((HERE / "seed_status.json").read_text(encoding="utf-8")) if (HERE / "seed_status.json").exists() else {}
    web = [r for r in links if r.get("error") != "keine_web_url"]
    checked = [r for r in web if r.get("checked_at")]
    L = []
    w = L.append
    w(f"# Live-Links – Bericht (Stand {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC)\n")
    w("Erzeugt von `report.py`. Code: `linkcheck.py` → `formulare_live.py` → `report.py` (alle in `knowledge/build/links/`).\n")

    # ---------------- Demo-Formulare
    w("## 1. Demo-Seed-Formulare (Gate: 100 % live)\n")
    n_live = sum(1 for s in seed.values() if s.get("url_status") == "live")
    w(f"**{n_live}/{len(seed)} mit Live-PDF-URL des Trägers.**\n")
    w("| formular_id | Status | lokal vs. live | Abgleich | Felder lokal → live | Live-URL |")
    w("|---|---|---|---|---|---|")
    for fid, s in seed.items():
        d = s.get("feld_diff_lokal_vs_live")
        fd = f"{s.get('local_n_felder')} → {s.get('live_n_felder')}"
        w(f"| `{fid}` | {s.get('url_status')} | **{s.get('lokal_vs_live')}** | {s.get('match') or '–'} | {fd} | {s.get('url') or '–'} |")
    w("")
    w("- Bei sha256-identischen Dateien sind die Feldnamen 1:1 gleich. Das **B5-Feld-Mapping kann ohne Änderung auf die Live-Version** zeigen.")
    w("- `fsw_bedarfsmeldung_wg`: Auf fsw.at gibt es **kein öffentliches PDF**. Die Infoseite verlinkt nur die Broschüre; das Formular hat das Feld "
      "„Name Partnerorganisation“ und wird vermutlich über den WG-Träger ausgefüllt. Ersatz nach Regel b: Elternseite "
      "https://www.fsw.at/p/seniorinnen-wohngemeinschaften-basispaket, ausgefüllt wird die lokale Kopie (mit Stand-Hinweis). "
      "Folge fürs Gate: **6/7 mit Datei-Link, 7/7 mit Live-Link**. Offener Punkt: beim FSW (01 24 5 24) nach der Download-URL fragen.")
    w("- pv.at leitet `…&version=…` auf die versionslose URL um. Gespeichert ist `final_url`, die stabil bleibt, wenn die PVA eine neue Version hochlädt; der Hash zeigt die Änderung an.\n")
    w("- Recherchierte Kandidaten-URLs stehen in `seed_kandidaten.json`. linkcheck prüft sie mit; zugeordnet wird nur bei sha256-Gleichheit bzw. Feldähnlichkeit.\n")
    abw = {fid: s for fid, s in seed.items() if s.get("feld_diff_lokal_vs_live")}
    if abw:
        w("### ⚠ Feldnamen-Abweichungen lokal ↔ live (betrifft Feld-Mapping B5, `server/forms/`)\n")
        w("B5 mappt auf Feldnamen. Wenn B5 gegen die **lokale** Kopie mappt, aber die **Live**-Version ausliefert, fehlen diese Felder:\n")
        for fid, s in abw.items():
            d = s["feld_diff_lokal_vs_live"]
            w(f"- `{fid}`: {d['gleich']} gleich, **{len(d['entfernt'])} nur lokal**, **{len(d['neu'])} nur live**")
            if d["entfernt"]:
                w(f"  - nur lokal: {', '.join('`'+x+'`' for x in d['entfernt'][:25])}{' …' if len(d['entfernt']) > 25 else ''}")
            if d["neu"]:
                w(f"  - nur live: {', '.join('`'+x+'`' for x in d['neu'][:25])}{' …' if len(d['neu']) > 25 else ''}")
        w("")
        w("Empfehlung: B5 mappt gegen die Feldliste in `formulare_live.jsonl` (`felder`, aus dem Live-PDF). "
          "Wo die Live-Version nicht ausfüllbar oder anders ist, füllt B5 die lokale Kopie aus und verlinkt zusätzlich die Live-URL zum Download.\n")

    # ---------------- Quote je Quelle
    w("## 2. Live-Quote je Quelle\n")
    w("### 2.1 Alle URLs (die die API ausliefern kann)\n")
    w(f"URLs gesamt {len(links)}, davon Web {len(web)} (Rest: `sozdok:`/`file:`-Kennungen ohne Web-Link). Geprüft: {len(checked)} "
      f"(davon {sum(1 for r in checked if r.get('check_via') == 'manifest')} über frisches `manifest.json` der Quelle, ohne eigenen Request).\n")
    w("| kind | URLs | geprüft | ok | Quote ok/geprüft |")
    w("|---|---|---|---|---|")
    for k in ["formular_pdf", "online_antrag", "stelle", "quelle", "seite"]:
        rs = [r for r in web if r.get("kind") == k]
        c = [r for r in rs if r.get("checked_at")]
        ok = sum(1 for r in c if r.get("ok"))
        w(f"| {k} | {len(rs)} | {len(c)} | {ok} | {pct(ok, len(c))} |")
    w("")
    w("Noch nicht geprüft sind vor allem die ~7.600 Arzt-Websites aus `wien_ogd` (Host praxisplan.at) und 3.018 RIS-Seiten (sozdok_ris). "
      "linkcheck prüft höchstens 1.500 Seiten/Stellen pro Host und Lauf (`--host-cap`, die ältesten zuerst), damit wir keine Domain massenhaft crawlen. "
      "Die volle Abdeckung entsteht über mehrere tägliche Läufe. **Policy-Frage an den Koordinator:** Ungeprüfte `stelle`-URLs bis dahin ausblenden (strenge §3.2) oder mit Hinweis zeigen?\n")
    w("### 2.2 Formular-URLs je Quelle (`formulare.url_pdf`)\n")
    per = defaultdict(lambda: Counter())
    for r in web:
        if r.get("kind") != "formular_pdf":
            continue
        for src in {ref["source"] for ref in r.get("refs") or []}:
            st = "ungeprueft" if not r.get("checked_at") else ("ok" if r.get("ok") else "tot")
            per[src][st] += 1
    w("| Quelle | ok | tot | ungeprüft | Quote |")
    w("|---|---|---|---|---|")
    for src in sorted(per):
        c = per[src]
        w(f"| {src} | {c['ok']} | {c['tot']} | {c['ungeprueft']} | {pct(c['ok'], c['ok'] + c['tot'])} |")
    w("")

    # ---------------- Formular-Registry
    w("## 3. Kanonische Formular-Registry (`formulare_live.jsonl`)\n")
    w(f"{len(forms)} kanonische Formulare (dedupliziert über sha256 und `final_url`). "
      f"Mehrfach gefunden: {sum(1 for f in forms if len(f['gefunden_auf']) > 1)}.\n")
    w("| art | n | davon live | lotse_zeigen |")
    w("|---|---|---|---|")
    for a, n in Counter(f["art"] for f in forms).most_common():
        fs = [f for f in forms if f["art"] == a]
        w(f"| {a} | {n} | {sum(1 for f in fs if f['url_status'] == 'live')} | {sum(1 for f in fs if f['lotse_zeigen'])} |")
    w("")
    w("`url_status`: " + ", ".join(f"{k} {v}" for k, v in Counter(f["url_status"] for f in forms).most_common()) + "\n")
    w("Regel: Die Lotse-API zeigt nur `lotse_zeigen=true` (art ∈ antrag|beilage|merkblatt **und** Link live oder ersetzt). "
      "`tarif_vertrag` (ÄK-Wien-Verträge/Tarife für Ärzt:innen), `info_seite` (HTML statt Datei), `video`, `sonstiges` (Broschüren) erscheinen nicht als Formular.\n")

    # ---------------- Fehler + Ersatz
    w("## 4. Tote Links und Ersatzentscheidungen (ARCHITEKTUR §3.2)\n")
    dead = [r for r in checked if not r.get("ok")]
    w(f"{len(dead)} geprüfte URLs nicht ok. Ersatzregel: "
      + ", ".join(f"{k} {v}" for k, v in Counter(r.get("ersatz_regel") or "–" for r in dead).most_common()) + "\n")
    w("| kind | URL | Fehler | Ersatz | Regel | Quelle (Datei:Zeile) |")
    w("|---|---|---|---|---|---|")
    for r in sorted(dead, key=lambda r: (["formular_pdf", "online_antrag", "stelle", "quelle", "seite"].index(r.get("kind", "seite")), r["url"]))[:120]:
        ref = (r.get("refs") or [{}])[0]
        w(f"| {r.get('kind')} | {r['url'][:110]} | {r.get('error') or r.get('http_status')} | {(r.get('ersetzt_durch') or '–')[:80]} | "
          f"{r.get('ersatz_regel')} | {ref.get('source')}/{ref.get('file')}:{ref.get('line')} |")
    if len(dead) > 120:
        w(f"| … | {len(dead) - 120} weitere in `links.jsonl` (`ok=false`) | | | | |")
    w("")

    # ---------------- Kaputte relative URLs
    w("## 5. Kaputte relative URLs → Fix gehört in die Quelle\n")
    rel = [r for r in web if r["url"].startswith(("http:///", "https:///"))]
    for r in rel:
        for ref in r.get("refs") or []:
            w(f"- **{ref['source']}** `sources/{ref['source']}/out/{ref['file']}` Zeile {ref['line']} (`{ref['feld']}`, id `{ref['id']}`): `{r['url']}`"
              f" → Ersatz: {r.get('ersetzt_durch') or '–'} ({r.get('ersatz_regel')})")
    w("")
    w("Ursache: Das bvaeb-HTML enthält wörtlich `href=\"http:///cdscontent/load?…\"` (z. B. `sources/bvaeb/raw/1326bc857f…html`). "
      "`urljoin()` lässt das unverändert. **Fix** in `sources/svs/_common.py` → `norm_portal_url()` (gemeinsam für svs/bvaeb): "
      "wenn `scheme` http(s) und `netloc` leer, `netloc` (und `https`) von der Basis-URL übernehmen. Bis dahin repariert `linkcheck.py` "
      "die URL selbst (Host der Quelle) und prüft sie live (Regel `a_relative_url_repariert`).\n")

    # ---------------- Review
    w("## 6. Review-Queue (`review_queue.jsonl`)\n")
    for k, v in Counter(r["typ"] for r in review).most_common():
        w(f"- {k}: {v}")
    w("")

    # ---------------- Schnittstelle
    w("## 7. Schnittstelle für knowledge-db (`build_db.py`)\n")
    w("""Alle Dateien liegen in `knowledge/build/links/`. Reihenfolge im Update-Lauf: `linkcheck.py` → `formulare_live.py` → `report.py`.

```
uv run --python 3.12 --with httpx,pypdf knowledge/build/links/linkcheck.py      # inkrementell, --budget-min, --kinds, --force
uv run --python 3.12 --with pypdf       knowledge/build/links/formulare_live.py
python3 knowledge/build/links/report.py
```

**`links.jsonl`** → Tabelle `links` (eine Zeile pro URL, Schlüssel `url` = URL wie in den Quellen, ohne `#Fragment`):
`url, kind (formular_pdf|online_antrag|stelle|quelle|seite), kinds[], final_url, http_status, ok, content_type, bytes, sha256 (nur PDFs), checked_at, last_ok_at, fail_count, first_seen, error, method (HEAD|GET|GET-Range), check_via ('manifest' = aus frischem Quell-Manifest übernommen), ersetzt_durch, eltern_url (Fundseite), ersatz_regel (a_gleicher_sha256|a_relative_url_repariert|b_elternseite|c_ausblenden_review), refs[{source,file,line,feld,id}]`.
Nicht-Web-Kennungen (`sozdok:`, `file:`) stehen mit `error='keine_web_url'`, `ok=null` drin – nicht als Link ausliefern.

**API-Regel:** eine URL nur ausliefern, wenn `ok` und `last_ok_at` < 7 Tage; sonst `ersetzt_durch` (mit Hinweis „Formular dort herunterladen“ bei `b_elternseite`), sonst ausblenden. Ausgeliefert wird `final_url`; `geprueft_am` = `checked_at`.

**`formulare_live.jsonl`** → ersetzt die `formulare`-Tabelle (kanonisch, dedupliziert):
`formular_id` (Seed-ID, sonst Träger-ID), `name, traeger, art (antrag|beilage|merkblatt|tarif_vertrag|info_seite|video|sonstiges), art_grund, lotse_zeigen (bool – nur diese als Formular zeigen), url_status (live|ersetzt_a|ersetzt_b|tot|keine_url|ungeprueft), url (live bzw. Ersatz-URL), url_original, online_url, quelle_url, quelle_url_ok, content_type, sha256, bytes, pages, fillable, n_felder, felder[{name,typ,label}] (aus dem LIVE-PDF), leistung_ids[], wer_fuellt_aus, local_pdf (nur Fallback), lokal_vs_live (nur Seeds), url_pdf (Datei-URL, nur wenn live/ersetzt_a und PDF), version, alias_ids[] (alle deduplizierten Quell-formular_ids), gefunden_auf[{source,formular_id,url,zeile}], gefunden_auf_urls[], geprueft_am, last_ok_at`.
Join zu `leistungen.antrag.formular_id`: über `formular_id` **oder** `alias_ids[]` (die alten Quell-IDs bleiben dort erhalten).

**`formular_versionen.jsonl`**: `formular_id, version, sha256, url, n_felder, felder_hash, felder[], first_seen, last_seen, diff_zur_vorversion{entfernt,neu,gleich}`.

**`review_queue.jsonl`**: `typ (formular_neue_version|seed_formular_felder_abweichend|seed_formular_ohne_live_pdf|formular_link_tot_ohne_ersatz), formular_id, …, created_at` – bitte in die zentrale `build/review_queue.jsonl` mergen.

**`seed_status.json`**: je Demo-Formular `url_status, url, lokal_vs_live, match, live_sha256, local_sha256, feld_diff_lokal_vs_live` → Gate „Demo-Formulare 100 % live“.

**`pdf_meta.jsonl`** (Schlüssel sha256): `pages, acroform, felder[], title, text_head, first_url` – Zwischenstand für Klassifikation/Felder.
""")
    (HERE / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print("REPORT.md geschrieben")


if __name__ == "__main__":
    main()
