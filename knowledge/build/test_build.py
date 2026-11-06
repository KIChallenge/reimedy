#!/usr/bin/env python3
"""Tests für Loader/Merge/Suche mit synthetischen Quellen (unabhängig vom Ingestion-Stand).
    uv run --python 3.12 --with pytest pytest -q knowledge/build/test_build.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_db  # noqa: E402
from common import fts_query, norm  # noqa: E402
from search import Lotse  # noqa: E402


def w(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def make_sources(tmp: Path):
    s = tmp / "sources"
    w(s / "src_a/out/documents.jsonl", [
        {"id": "a:1#0", "source_id": "src_a", "url": "https://a.example/pflegegeld", "title": "Pflegegeld",
         "section": "Voraussetzungen", "text": "Pflegegeld gebührt bei einem Pflegebedarf von mehr als 65 Stunden monatlich. Anträge beim Pensionsversicherungsträger.",
         "bereich": ["D"], "bundesland": ["AT"], "doc_type": "leistungsinfo", "fetched_at": "2026-11-05T10:00:00Z", "sha256": "x1"},
        {"id": "a:2#0", "source_id": "src_a", "url": "https://a.example/fsw", "title": "Heimhilfe Wien", "text": "Die Heimhilfe unterstützt im Alltag.",
         "bereich": ["D"], "bundesland": ["W"], "fetched_at": "2026-11-05T10:00:00Z"},
        "{kaputt",
        {"id": "a:3#0", "source_id": "src_a", "title": "ohne url und text"},
    ])
    w(s / "src_a/out/leistungen.jsonl", [
        {"leistung_id": "rezeptgebuehr_befreiung", "name": "Rezeptgebührenbefreiung", "kosten": "Rezeptgebühr 7,70 Euro",
         "quellen": [{"url": "https://a.example/rgb", "stand": "2026-11-01"}], "confidence": "hoch", "bereich": ["E"],
         "unterlagen": ["Einkommensnachweis", "Meldezettel"]},
        {"leistung_id": "Neue Leistung", "name": "falsche id", "quellen": [{"url": "u"}]},
        {"leistung_id": "zyklus_a", "name": "A", "abhaengigkeiten": ["zyklus_b"], "quellen": [{"url": "u"}]},
        {"leistung_id": "zyklus_b", "name": "B", "abhaengigkeiten": ["zyklus_a"], "quellen": [{"url": "u"}]},
        {"leistung_id": "wochengeld", "name": "Wochengeld", "quellen": [{"url": "https://a.example/wg", "stand": "2026-10-01"}], "bereich": ["E"]},
    ])
    w(s / "src_a/out/manifest.json".replace(".json", ".jsonl"), [])  # leere Extra-Datei stört nicht
    (s / "src_a/out/manifest.jsonl").unlink()
    (s / "src_a/out/manifest.json").write_text(json.dumps({"source_id": "src_a", "fetched_at": "2026-11-05T10:00:00Z", "urls": []}))
    w(s / "src_b/out/stellen.jsonl", [
        {"stelle_id": "pve_1030", "name": "PVE Landstraße", "typ": "pve", "plz": "1030", "bundesland": "W", "zustaendig_fuer": ["hausarzt"]},
        {"stelle_id": "pve_1100", "name": "PVE Favoriten", "typ": "pve", "plz": "1100", "bundesland": "W"},
        {"stelle_id": "pve_8010", "name": "PVE Graz", "typ": "pve", "plz": "8010", "bundesland": "St"},
    ])
    w(s / "src_b/out/rechtsgrundlagen.jsonl", [{"leistung_id": "pflegegeld", "title": "§ 4 BPGG"}])
    return s


def make_links(tmp: Path):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    fresh, old = now.isoformat(timespec="seconds"), (now - timedelta(days=30)).isoformat(timespec="seconds")
    w(tmp / "links/links.jsonl", [
        {"url": "https://a.example/pflegegeld", "kind": "seite", "final_url": "https://a.example/pflegegeld", "http_status": 200, "ok": True,
         "checked_at": fresh, "last_ok_at": fresh},
        {"url": "https://www.fsw.at", "kind": "seite", "final_url": "https://www.fsw.at/", "http_status": 200, "ok": True,
         "checked_at": fresh, "last_ok_at": fresh},
        {"url": "https://tot.example/antrag.pdf", "kind": "formular_pdf", "final_url": None, "http_status": 404, "ok": False,
         "checked_at": fresh, "last_ok_at": old, "eltern_url": "https://www.fsw.at"},
    ])
    w(tmp / "links/formulare_live.jsonl", [
        {"formular_id": "fsw_antrag_foerderung", "name": "Antrag auf Förderung (live)", "art": "antrag",
         "url_pdf": "https://tot.example/antrag.pdf", "alias_ids": ["fsw_fsw_antrag_auf_foerderung_von_leistungen"],
         "geprueft_am": fresh},
        {"formular_id": "fsw_tarif", "name": "Tarifvertrag", "art": "tarif_vertrag", "url_pdf": "https://www.fsw.at"},
    ])
    return tmp / "links"


def build(tmp_path):
    s = make_sources(tmp_path)
    db = tmp_path / "t.sqlite"
    rep = build_db.build(db, s, quiet=True, embeddings=False, links_dir=make_links(tmp_path))
    return rep, Lotse(db, log_misses=False, hybrid=False)


def test_norm_umlaute():
    assert norm("Ärztin Größe") == "aerztin groesse"
    assert norm("Rezept­gebühr") == "rezeptgebuehr"
    assert '"pflegegeld"*' in fts_query("Pflegegeld beantragen")


def test_validation_per_source(tmp_path):
    rep, _ = build(tmp_path)
    a = rep["quellen"]["src_a"]
    assert a["documents"] == 2 and a["errors"] >= 3  # kaputtes JSON, fehlende Pflichtfelder, falsche ID
    assert a["status"] == "teilweise"
    assert rep["quellen"]["src_b"]["status"] == "ok"


def test_merge_alias_and_conflict(tmp_path):
    rep, L = build(tmp_path)
    # Alias rezeptgebuehr_befreiung → rezeptgebuehrenbefreiung; 7,70 ≠ 7,55 aus Seed → Konflikt sichtbar, nicht überschrieben
    g = L.get_leistung("rezeptgebuehrenbefreiung")
    assert g["review_status"] == "konflikt"
    assert any(c["feld"] == "kosten" for c in g["konflikte"])
    assert "7,55" in g["kosten"]  # kuratierter Seed gewinnt
    assert {"seed", "src_a"} <= set(g["sources"])
    assert "Meldezettel" in g["unterlagen"]  # Listen werden vereinigt
    assert any(c["source_id"] == "src_a" and c["field"] == "kosten" for c in g["claims"])  # jede Aussage mit Quelle
    # Alias-Zugriff funktioniert auch
    assert L.get_leistung("rezeptgebuehr_befreiung")["leistung_id"] == "rezeptgebuehrenbefreiung"
    # Neuer Kandidat ohne Seed → muss reviewt werden
    assert L.get_leistung("wochengeld")["review_status"] == "kandidat"


def test_search_graph_first_and_rag(tmp_path):
    _, L = build(tmp_path)
    r = L.search("pflegegeld beantragen")
    assert r["graph_treffer"] and r["leistungen"][0]["leistung_id"] == "pflegegeld"
    assert r["dokumente"] and r["dokumente"][0]["url"].startswith("https://a.example")
    assert r["dokumente"][0]["stand"]
    assert "_meta" in r and r["_meta"]["db_stand"]
    # Bundesland-Filter: W-Dokument nicht bei bundesland=St
    assert not any(d["id"] == "a:2#0" for d in L.search("Heimhilfe", bundesland="St")["dokumente"])
    assert any(d["id"] == "a:2#0" for d in L.search("heimhilfe", bundesland="W")["dokumente"])


def test_dependencies_and_extras(tmp_path):
    _, L = build(tmp_path)
    g = L.get_leistung("fahrtkostenzuschuss")
    assert g["reihenfolge"] == ["rezeptgebuehrenbefreiung", "fahrtkostenzuschuss"]
    assert g["formulare"][0]["formular_id"] == "oegk_fahrtkosten_wien"
    p = L.get_leistung("pflegegeld")
    assert any(x.get("title") == "§ 4 BPGG" for x in p["rechtsgrundlagen_und_extras"])


def test_stellen_near(tmp_path):
    _, L = build(tmp_path)
    r = L.stellen_near("1030", typ="pve")
    names = [s["name"] for s in r["stellen"]]
    assert names[0] == "PVE Landstraße" and "PVE Graz" not in names
    # Alias in zustaendig_fuer (hausarzt → hausarzt_pve) wird für Kanten aufgelöst
    assert any(s["stelle_id"] == "pve_1030" for s in L.get_leistung("hausarzt_pve")["stellen"])


def test_triggers_entlassungsbrief(tmp_path):
    _, L = build(tmp_path)
    text = ("Mobile Hauskrankenpflege organisieren. Pflegegeldanspruch prüfen. "
            "Fahrtmöglichkeiten zu Behandlungsterminen klären. Rezeptgebührenbefreiung prüfen.")
    ids = {h["leistung_id"] for h in L.triggers(text)["leistungen"]}
    assert {"mobile_pflege_fsw", "pflegegeld", "fahrtkostenzuschuss", "rezeptgebuehrenbefreiung"} <= ids


def test_cycle_safe(tmp_path):
    _, L = build(tmp_path)
    assert set(L.get_leistung("zyklus_a")["reihenfolge"]) == {"zyklus_a", "zyklus_b"}


def test_codes_lookup_and_hint_policy(tmp_path):
    s = make_sources(tmp_path)
    q = {"quelle_url": "https://termgit.example", "stand": "2026"}
    w(s / "src_c/out/codes.jsonl", [
        {"system": "ICD-10-AT", "code": "C00-D48", "label_de": "Neubildungen", "parent": None, "leistung_hints": ["reha_onkologisch"], **q},
        {"system": "ICD-10-AT", "code": "C15-C26", "label_de": "Verdauungsorgane", "parent": "C00-D48", "leistung_hints": ["onkologische_reha"], **q},
        {"system": "ICD-10-AT", "code": "C20", "label_de": "Bösartige Neubildung des Rektums", "parent": "C15-C26", "leistung_hints": [], **q},
        {"system": "ICD-10-AT", "code": "D10-D36", "label_de": "Gutartige Neubildungen", "parent": "C00-D48", "leistung_hints": [], **q},
        {"system": "ICD-10-AT", "code": "D17", "label_de": "Gutartige Neubildung des Fettgewebes", "parent": "D10-D36", "leistung_hints": ["reha_onkologisch"], **q},
        {"system": "ATC", "code": "A04AA01", "label_de": "Ondansetron", "leistung_hints": [], **q},
        {"system": "ICD-10-AT", "code": "X1"},  # ohne label → Fehler
    ])
    db = tmp_path / "c.sqlite"
    rep = build_db.build(db, s, quiet=True, embeddings=False, links_dir=tmp_path / "nolinks")
    assert rep["quellen"]["src_c"]["errors"] == 1
    assert rep["codes"]["hints_durch_policy_entfernt"] >= 2  # C00-D48 (Bereich reicht über D09 hinaus) und D17
    L = Lotse(db, log_misses=False, hybrid=False)
    r = L.lookup_code("ICD-10-AT", "c20.9")  # Unterkode unbekannt → Elterncode, gekennzeichnet
    assert r["code"] == "C20" and r["ueber_elterncode"] and r["label_de"] == "Bösartige Neubildung des Rektums"
    assert [h["code"] for h in r["hierarchie"]] == ["C15-C26", "C00-D48"]
    k = L.codes_to_leistung_hints(["C20", "D17", {"system": "ATC", "code": "A04AA01"}, "Q99"])
    ids = {x["leistung_id"] for x in k["kandidaten"]}
    assert ids == {"reha_onkologisch"}  # über Alias + Vererbung von C15-C26; D17 und ATC lösen nichts aus
    assert k["unbekannte_codes"] == [{"system": "ICD-10-AT", "code": "Q99"}]
    assert "nicht" in k["hinweis"]


def test_links_live_only(tmp_path):
    _, L = build(tmp_path)
    r = L.search("pflegegeld beantragen")
    assert r["dokumente"][0]["url"] == "https://a.example/pflegegeld" and r["dokumente"][0]["geprueft_am"]
    heim = [d for d in L.search("heimhilfe")["dokumente"] if d["id"] == "a:2#0"][0]
    assert heim["url"] is None  # nie geprüft → nicht ausliefern
    f = L.formular("fsw_antrag_foerderung")
    assert f["name"] == "Antrag auf Förderung (live)"  # formulare_live ist kanonisch
    assert f["url_pdf"] == "https://www.fsw.at/" and "dort herunterladen" in f["hinweis"]  # toter Link → Elternseite
    assert "error" in L.formular("fsw_tarif")  # tarif_vertrag wird nicht als Formular ausgeliefert


def test_taxonomie(tmp_path):
    s = make_sources(tmp_path)
    w(s / "src_t/out/leistungen.jsonl", [
        {"leistung_id": "unterstuetzungsfonds", "name": "Unterstützungsfonds", "kosten": "bis 500 Euro", "quellen": [{"url": "https://o.example"}]},
        {"leistung_id": "unterstuetzungsfonds_bvaeb", "name": "Unterstützungsfonds (BVAEB)", "kosten": "bis 900 Euro", "quellen": [{"url": "https://b.example"}]},
        {"leistung_id": "medizinische_hauskrankenpflege", "name": "Medizinische HKP", "quellen": [{"url": "https://o.example/hkp"}]},
        {"leistung_id": "hauskrankenpflege", "name": "Mobile Dienste und Hauskrankenpflege", "quellen": [{"url": "https://g.example"}]},
        {"leistung_id": "rezeptgebuehrenobergrenze", "name": "Obergrenze", "quellen": [{"url": "https://o.example/og"}]},
    ])
    (s / "elga/out").mkdir(parents=True)
    w(s / "elga/out/documents.jsonl", [{"id": "e:1", "source_id": "elga", "url": "x", "text": "Befund von Frau X"}])
    db = tmp_path / "x.sqlite"
    rep = build_db.build(db, s, quiet=True, embeddings=False, links_dir=tmp_path / "nolinks")
    assert "elga" in rep["uebersprungen"] and "elga" not in rep["quellen"]
    L = Lotse(db, log_misses=False, hybrid=False)
    u = L.get_leistung("unterstuetzungsfonds_bvaeb")  # Trägervariante → eine Leistung mit Ausprägung
    assert u["leistung_id"] == "unterstuetzungsfonds" and "BVAEB" in u["traeger_auspraegungen"]
    assert u["review_status"] != "konflikt"  # 500 vs 900 sind verschiedene Träger, kein Widerspruch
    m = L.get_leistung("medizinische_hauskrankenpflege")
    assert m["leistung_id"] == "medizinische_hauskrankenpflege"
    assert "mobile_pflege_fsw" in {x["leistung_id"] for x in m["nicht_verwechseln_mit"]}
    assert L.get_leistung("hauskrankenpflege")["leistung_id"] == "mobile_dienste"  # NICHT mobile_pflege_fsw
    og = L.get_leistung("rezeptgebuehrenobergrenze")
    assert og["leistung_id"] == "rezeptgebuehrenobergrenze" and og["teil_von"][0]["leistung_id"] == "rezeptgebuehrenbefreiung"


def test_stellen_geo(tmp_path):
    s = make_sources(tmp_path)
    w(s / "src_g/out/stellen.jsonl", [
        {"stelle_id": "apo_a", "name": "Apotheke nah", "typ": "apotheke", "plz": "1030", "bundesland": "W", "geo": [48.2010, 16.3940]},
        {"stelle_id": "apo_b", "name": "Apotheke fern", "typ": "apotheke", "plz": "1030", "bundesland": "W", "geo": [48.1900, 16.4100]},
        {"stelle_id": "apo_c", "name": "Apotheke Floridsdorf", "typ": "apotheke", "plz": "1210", "bundesland": "W", "geo": [48.2600, 16.4000]},
    ])
    db = tmp_path / "g.sqlite"
    build_db.build(db, s, quiet=True, embeddings=False, links_dir=tmp_path / "nolinks")
    L = Lotse(db, log_misses=False, hybrid=False)
    r = L.stellen_near(typ="apotheke", lat=48.2012, lon=16.3942)
    assert [x["stelle_id"] for x in r["stellen"]] == ["apo_a", "apo_b", "apo_c"] and r["stellen"][0]["entfernung_km"] < 0.1
    assert L.stellen_near("1030", typ="apotheke")["ursprung"]  # PLZ-Mittelpunkt aus Daten


def test_query_synonyme():
    from search import _load_syn, expand_query
    regeln = _load_syn()
    assert "Pflegegeld" in expand_query("Meine Mama packt's nimma allein daham", regeln)
    assert "Rezeptgebühr" in expand_query("Die Medikamente sind so teuer", regeln)
    assert expand_query("Zahnspange Kind", regeln) == ["Kieferorthopädie", "Zahnspange"]
    assert expand_query("Wie hoch ist die Rezeptgebühr?", regeln) == []


def test_db_path_env_und_health(tmp_path, monkeypatch):
    import search as S
    _, L = build(tmp_path)
    h = L.health()
    assert h["db"] == "t.sqlite" and not str(h).count(str(tmp_path))  # keine absoluten lokalen Pfade
    # Volume leer → Image-DB wird übernommen; Volume neuer → bleibt
    vol = tmp_path / "vol" / "lotse.sqlite"
    monkeypatch.setattr(S, "BUILD", tmp_path)
    (tmp_path / "lotse.sqlite").write_bytes((tmp_path / "t.sqlite").read_bytes())
    assert "Image" in S.ensure_db(vol) and vol.exists()
    assert S.ensure_db(vol).startswith("volume")


def test_formular_unbekannte_leistung_keine_kante(tmp_path):
    s = make_sources(tmp_path)
    w(s / "src_f/out/formulare.jsonl", [{"formular_id": "fsw_test_formular", "name": "x",
                                         "leistung_ids": ["mobile_pflege_fsw", "fsw_foerderung_pflege_betreuung"]}])
    rep = build_db.build(tmp_path / "f.sqlite", s, quiet=True, embeddings=False, links_dir=tmp_path / "nolinks")
    assert not [e for e in rep["leistungen"]["kanten_ins_leere"] if e[0] == "fsw_foerderung_pflege_betreuung"]
    assert "fsw_test_formular→fsw_foerderung_pflege_betreuung" in rep["leistungen"]["formular_leistung_ids_unbekannt"]


def test_http_stellen_leistung_und_leistung_id(tmp_path, monkeypatch):
    """API-Vertrag: /stellen akzeptiert leistung UND leistung_id (README/Client nutzen leistung_id)."""
    import json as _json
    import socket
    import threading
    import time
    import urllib.request
    import search as S
    _, _L = build(tmp_path)
    monkeypatch.setattr(S, "BUILD", tmp_path / "kein_image")  # ensure_db: nichts kopieren
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
    threading.Thread(target=S.serve, kwargs={"port": port, "db": tmp_path / "t.sqlite"}, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    ids = {}
    for param in ("leistung", "leistung_id"):
        d = _json.load(urllib.request.urlopen(f"{base}/stellen?plz=1030&{param}=mobile_pflege_fsw", timeout=3))
        ids[param] = [s["stelle_id"] for s in d["stellen"]]
    assert ids["leistung"] == ids["leistung_id"] == ["fsw_beratungszentrum_pflege"]


def test_traeger_register(tmp_path):
    from common import plz_bundesland
    assert [plz_bundesland(p) for p in ("1030", "3100", "2425", "4020", "5280", "5020", "6900", "6020", "7000", "8010", "9020", "9900")] == \
        ["W", "N", "B", "O", "O", "S", "V", "T", "B", "St", "K", "T"]
    _, L = build(tmp_path)
    r = L.traeger(plz="9020")
    t = {x["id"]: x for x in r["traeger"]}
    assert t["oegk"]["zustaendig"]["stelle"]["name"] == "ÖGK Kärnten"
    assert t["pva"]["zustaendig"]["stelle"]["email"] == "pva-lsk@pv.at"
    assert t["oegk"]["reimedy_ref"] == {"vocabulary_id": "Austrian_Payer", "concept_code": "2000000001", "concept_id": 2000000001}
    assert t["kfa"]["zustaendig"]["status"] == "rueckfrage"
    assert L.traeger("fsw", plz="8010")["traeger"][0]["zustaendig"]["status"] == "nicht_zustaendig"


def test_kurz_einfach_override_und_varianten(tmp_path):
    s = make_sources(tmp_path)
    w(s / "src_k/out/leistungen.jsonl", [
        {"leistung_id": "mentale_gesundheit_angebote", "name": "Mentale Gesundheit", "kurz_einfach": "Gönnen Sie sich Glücksmomente.",
         "quellen": [{"url": "https://www.oegk.at/x"}]},
        {"leistung_id": "angehoerigen_entlastung", "name": "Entlastung", "quellen": [{"url": "https://g.example"}]},
    ])
    build_db.build(tmp_path / "k.sqlite", s, quiet=True, embeddings=False, links_dir=tmp_path / "nolinks")
    L = Lotse(tmp_path / "k.sqlite", log_misses=False, hybrid=False)
    m = L.get_leistung("mentale_gesundheit_angebote")
    assert "Glücksmomente" not in m["kurz_einfach"] and m["kurz_einfach_quelle"]
    assert L.get_leistung("angehoerigen_entlastung")["leistung_id"] == "pflegende_angehoerige_unterstuetzung"
    assert L.get_leistung("hausarzt_kontrolle")["leistung_id"] == "hausarzt_pve"


def test_forms_endpunkte_ohne_und_mit_modul(tmp_path, monkeypatch):
    import search as S
    _, L = build(tmp_path)
    monkeypatch.setattr(S, "BUILD", tmp_path)  # kein forms/ → 404 'noch nicht verfügbar'
    assert L.forms_ontologie()["status"] == 404
    assert L.formular_pdf("fsw_antrag_foerderung") is None  # toter PDF-Link → nie auf die Elternseite (HTML) umleiten
    fd = tmp_path / "forms"
    fd.mkdir()
    (fd / "forms_api.py").write_text(
        "def ontologie(): return {'keys': ['person.vorname']}\n"
        "def template(fid, nur_geprueft=True): return {'formular_id': fid, 'geprueft': True} if fid == 'x' else None\n"
        "def empfaenger(fid, plz=None, traeger=None): return {'formular_id': fid, 'plz': plz, 'kandidaten': ['pva', 'svs']}\n"
        "def pdf(fid): return (b'%PDF', 'application/pdf', fid + '.pdf') if fid == 'x' else None\n")
    assert L.forms_ontologie()["keys"] == ["person.vorname"]
    assert L.formular_template("x")["geprueft"] and L.formular_template("y")["status"] == 404
    e = L.formular_empfaenger("x", plz="9020")
    assert e["plz"] == "9020" and e["zustaendig_je_traeger"]["pva"]["stelle_id"] == "pva_k"
    assert e["zustaendig_je_traeger"]["svs"]["name"] == "SVS-Kundencenter Kärnten" and e["rueckfragen"]
    assert L.formular_pdf("x")[2] == "x.pdf"


def test_impfplan_intervalle(tmp_path):
    s = make_sources(tmp_path)
    z = {"version": "Impfplan Österreich 2026/2027, Version 1.1 vom 14.10.2026", "gueltig_ab": "2026-10-14"}
    w(s / "impfplan/out/impfplan_intervalle.jsonl", [
        {"id": "tdap_bis_60", "krankheit": "Diphtherie-Tetanus-Pertussis", "alter_von": 18, "alter_bis": 59, "intervall": "alle 10 Jahre",
         "intervall_monate": 120, "zitat": "… bis zum vollendeten 60. Lebensjahr alle 10 Jahre.", "seite": 22, **z},
        {"id": "tdap_ab_60", "krankheit": "Diphtherie-Tetanus-Pertussis", "alter_von": 60, "intervall": "alle 5 Jahre",
         "intervall_monate": 60, "zitate": [{"seite": 22, "zitat": "Ab dem vollendeten 60. Lebensjahr … alle 5 Jahre."}],
         "zitat": "Ab dem vollendeten 60. Lebensjahr … alle 5 Jahre.", **z},
        {"id": "kaputt", "krankheit": "X"},  # ohne Zitat/Version → Fehler
    ])
    rep = build_db.build(tmp_path / "i.sqlite", s, quiet=True, embeddings=False, links_dir=tmp_path / "nolinks")
    assert rep["quellen"]["impfplan"]["errors"] == 1
    L = Lotse(tmp_path / "i.sqlite", log_misses=False, hybrid=False)
    r = L.impfplan("pertussis", alter=78)
    assert [x["id"] for x in r["intervalle"]] == ["tdap_ab_60"] and r["intervalle"][0]["intervall_monate"] == 60
    assert r["versionen"] == [z["version"]] and r["intervalle"][0]["zitate"][0]["seite"] == 22
    assert [x["id"] for x in L.impfplan("pertussis", alter=40)["intervalle"]] == ["tdap_bis_60"]
