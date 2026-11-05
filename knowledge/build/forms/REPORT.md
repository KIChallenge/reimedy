# Formulare: Templates, Prüfung, Empfänger (ARCHITEKTUR §8.1)

Stand: 2026-11-05 · erzeugt von `report.py`
Vorgabe Arne: *„Alle Formulare müssen von Michi ausfüllbar sein, als PDF speicherbar und an die korrekte Stelle versendbar.“*
## Abdeckung
| | Anzahl |
|---|---|
| Formulare im Lotsen (`lotse_zeigen`) | 350 |
| **geprüft** (Template wird ausgeliefert) | **137** |
| ungeprüft (Template vorhanden, Prüfung offen/negativ) | 90 |
| nicht möglich | 123 |
| Empfänger bestimmt (`empfaenger.jsonl`) | 350 |

Nach Quelle: acroform/geprueft: 54, acroform/ungeprueft: 25, generiert/geprueft: 83, generiert/nicht_moeglich: 3, generiert/ungeprueft: 65, keine/nicht_moeglich: 8

Felder gesamt 15962, davon mit Ontologie-Schlüssel 3817, von Michi füllbar 2664, ärztlich (gesperrt) 976. Angereicherte AcroForm-Kopien: 81.

### Nicht möglich – Gründe

| Grund | Anzahl |
|---|---|
| Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt | 84 |
| Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar | 16 |
| Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) | 11 |
| Infoblatt/Merkblatt ohne Ausfüllfelder | 8 |
| keine Ausfüllbereiche erkannt | 2 |
| Bild-PDF ohne Textebene – OCR (Vision) ausstehend | 1 |
| kein PDF im Cache (Download fehlgeschlagen) | 1 |

## Demo-Formulare

| Formular | Status | Methode | Felder | Michi füllt |
|---|---|---|---|---|
| `antrag_ahv_reha_unfall` Antrag auf Anschlussheilverfahren oder Rehabilitat | geprueft | geometrie+vision_llm+sichtpruefung | 62 | 7 |
| `antrag_reha_kur` Antrag auf Rehabilitations-, Kur- bzw. Erholungsau | geprueft | geometrie+vision_llm+sichtpruefung | 92 | 21 |
| `bvaeb_9096928de6` Antrag auf Befreiung von der Rezeptgebühr / vom Be | geprueft | geometrie+vision_llm+sichtpruefung | 70 | 8 |
| `fsw_antrag_foerderung` FSW Antrag auf Förderung von Leistungen | geprueft | geometrie+vision_llm+sichtpruefung | 122 | 41 |
| `fsw_bedarfsmeldung_wg` FSW Bedarfsmeldung Senior:innen-WG (Basispaket) | geprueft | geometrie+vision_llm+sichtpruefung | 21 | 7 |
| `fsw_einrichtungswunsch` FSW Beilage Einrichtungswunsch Wohn- und Pflegehäu | geprueft | geometrie+vision_llm+sichtpruefung | 13 | 7 |
| `oegk_fahrtkosten_wien` Antrag auf Zuschuss zu Fahrtkosten (Wien) | geprueft | geometrie+vision_llm+sichtpruefung | 13 | 6 |
| `pva_pal080` Antrag auf Pflegegeld (PAL 080) | geprueft | geometrie+vision_llm+sichtpruefung | 100 | 33 |
| `svs_8e5303e0b6` KV-154 (10200) Antrag auf Rezeptgebührenbefreiung_ | geprueft | geometrie+vision_llm+sichtpruefung | 52 | 7 |

Rezeptgebührenbefreiung **ÖGK**: In `formulare_live` gibt es kein ÖGK-Antragsformular. `oegk_infoblatt` ist ein Infoblatt (als `antrag` klassifiziert) und bekommt daher kein Template. Geprüfte Alternativen: BVAEB `bvaeb_9096928de6`, SVS `svs_8e5303e0b6`.

## Wie es funktioniert

1. `fetch_pdfs.py` lädt die Live-PDFs (≤1 Req/s/Host) in `cache/<sha256>.pdf` (gitignored).
2. `build_templates.py`: AcroForm → Widgets, bbox, Tooltip-/Nachbar-Label; flach → Ausfüllbereiche geometrisch (Unterstrich-/Punktlinien,
   Linien, leere Kästen, Kästchenreihen = Zeichen-Kästchen, Ankreuzkästchen, Tabellenzellen mit Label). `semantik` per Regeln
   (`semantik.py`), Abschnitts-Sperren (ärztlicher Teil, Amtsvermerk), dann eingefrorene Zuordnungen (`semantik_frozen.json`;
   Demo-Formulare = Goldstandard aus Michi `b5-comms/server/forms/mappings.py`).
3. `pruefen.py`: Testperson (`ontologie.json` → `beispiel`, fiktiv) probefüllen (`fill.py`, derselbe Ablauf wie Michis Filler),
   Geometrie prüfen (Wert passt, keine Überlappung, kein Drucktext im Feld), Seiten rendern, **Vision-LLM** bzw. **Sichtprüfung**.
   Felder, in die ein typischer Wert nicht passt, werden auf `michi_fuellt=false` gesetzt (Michi fragt nach). Nur bei bestandener
   Prüfung setzt es `geprueft`. Der Fingerabdruck (bbox + semantik) bindet die Sichtprüfung an genau diese Template-Version.
4. `make_pdfs.py`: AcroForm-angereicherte Kopien flacher PDFs, nur amtliche Werke (SV-Träger, Bund), siehe `pdf/LIZENZ.md`.
5. `build_empfaenger.py`: `empfaenger.jsonl` + `empfaenger_stellen.json` (Snapshot aus `traeger.json`). Regel:
   fix · landesstelle_nach_plz · auszahlende_stelle (Pflegegeld, § 22 BPGG) · nach_versicherung · unbekannt.
6. `forms_api.py`: `ontologie()`, `template(id)`, `pdf(id)`, `empfaenger(id, plz, traeger)` – verdrahtet in `search.py` (knowledge-db).

**Harte Grenzen:** `wer=arzt`, `unterschrift.*`, `medizinisch.*`, `behoerde.*`, `einkommen.*` und `bank.*` haben `michi_fuellt=false`.
Keine Diagnose, keine Befunddeutung. Die Ontologie wird nur additiv geändert.

**Neu bauen:** `fetch_pdfs.py` → `build_templates.py` → `pruefen.py --alle --vision` → `make_pdfs.py` → `build_empfaenger.py` → `report.py`.
Ändert sich ein sha256 (neue Formularversion), entsteht ein neues Template `<id>@<sha12>.json`, das erst nach erneuter Prüfung ausgeliefert wird.

## Alle Formulare

| Formular | Träger | Status | Quelle | Felder/Michi | Grund bzw. Methode |
|---|---|---|---|---|---|
| `antrag_ahv_reha_unfall` | KV/PV | geprueft | acroform | 62/7 | geometrie+vision_llm+sichtpruefung |
| `antrag_reha_kur` | SV (Träger im Formular wählen) | geprueft | acroform | 92/21 | geometrie+vision_llm+sichtpruefung |
| `bvaeb_0a67df4f3c` | BVAEB | geprueft | acroform | 26/14 | geometrie+vision_llm |
| `bvaeb_1ce2e2b953` | BVAEB | geprueft | acroform | 102/4 | geometrie+vision_llm |
| `bvaeb_2ed325adef` | BVAEB | geprueft | acroform | 101/33 | geometrie+vision_llm |
| `bvaeb_4677209e4a` | BVAEB | geprueft | acroform | 34/3 | geometrie+vision_llm |
| `bvaeb_47c564ebf1` | BVAEB | geprueft | acroform | 29/10 | geometrie+vision_llm |
| `bvaeb_79d36c1b4d` | BVAEB | geprueft | acroform | 34/4 | geometrie+vision_llm |
| `bvaeb_7fc8ec1068` | BVAEB | geprueft | acroform | 17/2 | geometrie+vision_llm |
| `bvaeb_82e5d4f0a4` | BVAEB | geprueft | acroform | 31/7 | geometrie+vision_llm |
| `bvaeb_8a92793171` | BVAEB | geprueft | acroform | 22/16 | geometrie+vision_llm |
| `bvaeb_9096928de6` | BVAEB | geprueft | acroform | 70/8 | geometrie+vision_llm+sichtpruefung |
| `bvaeb_92ce5203f6` | BVAEB | geprueft | acroform | 43/24 | geometrie+vision_llm |
| `bvaeb_95328111e5` | BVAEB | geprueft | acroform | 14/3 | geometrie+vision_llm |
| `bvaeb_a0ee6b64e7` | BVAEB | geprueft | acroform | 14/6 | geometrie+vision_llm |
| `bvaeb_ab4e6964a7` | BVAEB | geprueft | acroform | 35/5 | geometrie+vision_llm |
| `bvaeb_ac0155333c` | BVAEB | geprueft | acroform | 13/3 | geometrie+vision_llm |
| `bvaeb_b492dbff04` | BVAEB | geprueft | acroform | 14/9 | geometrie+vision_llm |
| `bvaeb_bb7ad8f6dc` | BVAEB | geprueft | generiert | 2/1 | geometrie+vision_llm |
| `bvaeb_c5da34e556` | BVAEB | geprueft | acroform | 32/14 | geometrie+vision_llm |
| `bvaeb_d3f6e376f9` | BVAEB | geprueft | generiert | 48/1 | geometrie+vision_llm |
| `bvaeb_f39df4b02c` | BVAEB | geprueft | generiert | 12/2 | geometrie+vision_llm |
| `fsw_240315_verwendungsnachweis_dl_halbjaehrlich_handschriftlich_bf` | FSW | geprueft | generiert | 21/0 | geometrie+vision_llm |
| `fsw_anliegen_fsw_interaktiv` | FSW | geprueft | acroform | 26/21 | geometrie+vision_llm |
| `fsw_antrag_auf_aenderung_bzw_verlaengerung_der_foerderung` | FSW | geprueft | acroform | 34/6 | geometrie+vision_llm |
| `fsw_antrag_auf_ratenzahlung` | FSW | geprueft | acroform | 15/3 | geometrie+vision_llm |
| `fsw_antrag_beilage_angehoerige` | FSW | geprueft | acroform | 18/15 | geometrie+vision_llm |
| `fsw_antrag_beilage_freizeitfahrtendienst` | FSW | geprueft | acroform | 20/3 | geometrie+vision_llm |
| `fsw_antrag_beilage_personengemeinschaft` | FSW | geprueft | acroform | 26/5 | geometrie+vision_llm |
| `fsw_antrag_foerderung` | FSW | geprueft | acroform | 122/41 | geometrie+vision_llm+sichtpruefung |
| `fsw_antrag_foerderung_klimaticket` | FSW | geprueft | acroform | 53/26 | geometrie+vision_llm |
| `fsw_antrag_pflegegeldergaenzungsleistung_erhoehung_neubemessung_pge` | FSW | geprueft | acroform | 69/8 | geometrie+vision_llm |
| `fsw_antrag_pflegegeldergaenzungsleistung_verlaengerung_pge` | FSW | geprueft | acroform | 57/9 | geometrie+vision_llm |
| `fsw_bedarfsmeldung_wg` | FSW | geprueft | acroform | 21/7 | geometrie+vision_llm+sichtpruefung |
| `fsw_befundbericht_kinder` | FSW | geprueft | acroform | 117/5 | geometrie+vision_llm |
| `fsw_befundbericht_wohnen_und_pflege` | FSW | geprueft | acroform | 41/3 | geometrie+vision_llm |
| `fsw_einrichtungswunsch` | FSW | geprueft | acroform | 13/7 | geometrie+vision_llm+sichtpruefung |
| `fsw_pge_pa_antrag_handschriftlich` | FSW | geprueft | generiert | 110/5 | geometrie+vision_llm |
| `fsw_sepa_lastschriftmandat` | FSW | geprueft | acroform | 15/11 | geometrie+vision_llm |
| `oegk_aktuellen_erstattungssaetze` | ÖGK | geprueft | generiert | 14/0 | geometrie+vision_llm |
| `oegk_alkoholfragebogen_vu` | ÖGK | geprueft | generiert | 2/0 | geometrie+vision_llm |
| `oegk_allgemeine_gesundheitsfragen` | ÖGK | geprueft | acroform | 30/7 | geometrie+vision_llm |
| `oegk_antrag_auf_kostenuebernahme_gemaess_anlage_4` | ÖGK | geprueft | generiert | 118/1 | geometrie+vision_llm |
| `oegk_antrag_verbaende_und_kontaktstellen` | ÖGK | geprueft | acroform | 113/15 | geometrie+vision_llm |
| `oegk_au_meldung` | ÖGK | geprueft | generiert | 22/1 | geometrie+vision_llm |
| `oegk_befundblatt_neu_vu` | ÖGK | geprueft | generiert | 187/0 | geometrie+vision_llm |
| `oegk_bestaetigung_ueber_voraussichtlichen_entbindungstermin` | ÖGK | geprueft | generiert | 5/1 | geometrie+vision_llm |
| `oegk_bewilligung_fuer_zahnbehandlung` | ÖGK | geprueft | generiert | 5/1 | geometrie+vision_llm |
| `oegk_ct_zuweisung` | ÖGK | geprueft | generiert | 42/0 | geometrie+vision_llm |
| `oegk_fahrtkosten_wien` | ÖGK | geprueft | acroform | 13/6 | geometrie+vision_llm+sichtpruefung |
| `oegk_fertig_ausdruckenund_per_post_schicken` | ÖGK | geprueft | acroform | 39/9 | geometrie+vision_llm |
| `oegk_kieferorthopaedie` | ÖGK | geprueft | generiert | 48/3 | geometrie+vision_llm |
| `oegk_koloskopie_vu` | ÖGK | geprueft | generiert | 13/1 | geometrie+vision_llm |
| `oegk_kostenuebernahme_fuer_zahnersatz` | ÖGK | geprueft | generiert | 21/2 | geometrie+vision_llm |
| `oegk_kostenzuschuss_psychotherapeutische_behandlung` | ÖGK | geprueft | acroform | 33/6 | geometrie+vision_llm |
| `oegk_meldung_mutterschaftshilfe` | ÖGK | geprueft | generiert | 36/6 | geometrie+vision_llm |
| `oegk_mr_zuweisung` | ÖGK | geprueft | acroform | 4/0 | geometrie+vision_llm |
| `oegk_vo_fuer_heilbehelfe_und_hilfsmittel` | ÖGK | geprueft | generiert | 19/0 | geometrie+vision_llm |
| `oegk_vo_fuer_sehbehelfe_und_augenprothesen` | ÖGK | geprueft | generiert | 31/0 | geometrie+vision_llm |
| `oegk_zeitbestaetigung_fuer_dienstgeber` | ÖGK | geprueft | generiert | 6/2 | geometrie+vision_llm |
| `oegv_form_1150` |  | geprueft | acroform | 20/5 | geometrie+vision_llm |
| `oegv_form_233` |  | geprueft | acroform | 39/25 | geometrie+vision_llm |
| `pva_pal080` | PVA | geprueft | acroform | 100/33 | geometrie+vision_llm+sichtpruefung |
| `sms_05_individualfoeerderung_foerderansuchen_allgemein_bundeswei` | Sozialministeriumservice | geprueft | acroform | 70/17 | geometrie+vision_llm |
| `sms_acc_09_individualfoerderung_assistenzhund_fertig` | Sozialministeriumservice | geprueft | acroform | 57/14 | geometrie+vision_llm |
| `sms_acc_20_u_fonds_antragsformular_fertig` | Sozialministeriumservice | geprueft | acroform | 149/17 | geometrie+vision_llm |
| `sms_ersatzpflegebestaetigung` | Sozialministeriumservice | geprueft | generiert | 1/0 | geometrie+vision_llm |
| `svs_0070dd8de1` | SVS | geprueft | generiert | 93/0 | geometrie+vision_llm |
| `svs_020a5678d0` | SVS | geprueft | generiert | 8/1 | geometrie+vision_llm |
| `svs_0a20090f43` | SVS | geprueft | generiert | 33/13 | geometrie+vision_llm |
| `svs_0ab0eb276b` | SVS | geprueft | generiert | 29/4 | geometrie+vision_llm |
| `svs_0ab29d9bdf` | SVS | geprueft | generiert | 7/3 | geometrie+vision_llm |
| `svs_0c5aa467a0` | SVS | geprueft | generiert | 44/15 | geometrie+vision_llm |
| `svs_12cf32e0b3` | SVS | geprueft | generiert | 24/3 | geometrie+vision_llm |
| `svs_1411e7434f` | SVS | geprueft | generiert | 47/9 | geometrie+vision_llm |
| `svs_1b61761d5c` | SVS | geprueft | generiert | 11/0 | geometrie+vision_llm |
| `svs_21857ba383` | SVS | geprueft | generiert | 13/5 | geometrie+vision_llm |
| `svs_2260a44917` | SVS | geprueft | generiert | 34/8 | geometrie+vision_llm |
| `svs_295e174633` | SVS | geprueft | generiert | 31/4 | geometrie+vision_llm |
| `svs_29a2c56be7` | SVS | geprueft | generiert | 51/7 | geometrie+vision_llm |
| `svs_2a5d79d382` | SVS | geprueft | generiert | 44/9 | geometrie+vision_llm |
| `svs_2a7ede4498` | SVS | geprueft | generiert | 45/8 | geometrie+vision_llm |
| `svs_2f0c2c8cee` | SVS | geprueft | generiert | 48/7 | geometrie+vision_llm |
| `svs_3279cb3c96` | SVS | geprueft | generiert | 100/10 | geometrie+vision_llm |
| `svs_346feb4ecf` | SVS | geprueft | generiert | 8/4 | geometrie+vision_llm |
| `svs_361135b683` | SVS | geprueft | generiert | 7/1 | geometrie+vision_llm |
| `svs_37916134ae` | SVS | geprueft | generiert | 39/7 | geometrie+vision_llm |
| `svs_37975c4cb5` | SVS | geprueft | generiert | 137/29 | geometrie+vision_llm |
| `svs_3b575deede` | SVS | geprueft | generiert | 62/13 | geometrie+vision_llm |
| `svs_3cf19bb39a` | SVS | geprueft | generiert | 8/5 | geometrie+vision_llm |
| `svs_3e89a7492c` | SVS | geprueft | generiert | 9/2 | geometrie+vision_llm |
| `svs_44d3928abe` | SVS | geprueft | acroform | 11/4 | geometrie+vision_llm |
| `svs_4abe172341` | SVS | geprueft | generiert | 8/4 | geometrie+vision_llm |
| `svs_4ce64bed8c` | SVS | geprueft | acroform | 34/5 | geometrie+vision_llm |
| `svs_5118c37e30` | SVS | geprueft | acroform | 29/10 | geometrie+vision_llm |
| `svs_569414ac79` | SVS | geprueft | generiert | 52/14 | geometrie+vision_llm |
| `svs_572e3a1873` | SVS | geprueft | generiert | 123/0 | geometrie+vision_llm |
| `svs_5aed63facc` | SVS | geprueft | generiert | 76/14 | geometrie+vision_llm |
| `svs_5e55aeb0bb` | SVS | geprueft | generiert | 38/14 | geometrie+vision_llm |
| `svs_653977d251` | SVS | geprueft | generiert | 147/18 | geometrie+vision_llm |
| `svs_65616c1550` | SVS | geprueft | generiert | 12/4 | geometrie+vision_llm |
| `svs_69fb6a8e11` | SVS | geprueft | acroform | 35/5 | geometrie+vision_llm |
| `svs_6d308ca16b` | SVS | geprueft | generiert | 65/13 | geometrie+vision_llm |
| `svs_6e0a5fdd9b` | SVS | geprueft | generiert | 8/1 | geometrie+vision_llm |
| `svs_6e22a33e3f` | SVS | geprueft | generiert | 7/4 | geometrie+vision_llm |
| `svs_7678bec1e2` | SVS | geprueft | generiert | 16/2 | geometrie+vision_llm |
| `svs_778189f5ad` | SVS | geprueft | generiert | 49/2 | geometrie+vision_llm |
| `svs_7d5802d3d8` | SVS | geprueft | acroform | 45/10 | geometrie+vision_llm |
| `svs_7f190f005a` | SVS | geprueft | acroform | 2/0 | geometrie+vision_llm |
| `svs_81122ff00f` | SVS | geprueft | generiert | 31/0 | geometrie+vision_llm |
| `svs_81e79096f1` | SVS | geprueft | generiert | 12/2 | geometrie+vision_llm |
| `svs_838f02e277` | SVS | geprueft | generiert | 35/16 | geometrie+vision_llm |
| `svs_842e58e23c` | SVS | geprueft | acroform | 94/2 | geometrie+vision_llm |
| `svs_84e1ffa3ee` | SVS | geprueft | generiert | 158/3 | geometrie+vision_llm |
| `svs_8e5303e0b6` | SVS | geprueft | generiert | 52/7 | geometrie+vision_llm+sichtpruefung |
| `svs_8fb4b88d50` | SVS | geprueft | generiert | 33/0 | geometrie+vision_llm |
| `svs_91b49b251d` | SVS | geprueft | generiert | 21/4 | geometrie+vision_llm |
| `svs_92e87cc6f1` | SVS | geprueft | generiert | 52/11 | geometrie+vision_llm |
| `svs_9b817d61ff` | SVS | geprueft | generiert | 42/5 | geometrie+vision_llm |
| `svs_9ba9cd8c83` | SVS | geprueft | generiert | 12/7 | geometrie+vision_llm |
| `svs_a340919067` | SVS | geprueft | generiert | 32/0 | geometrie+vision_llm |
| `svs_a8e19b3632` | SVS | geprueft | generiert | 32/0 | geometrie+vision_llm |
| `svs_aa0774943e` | SVS | geprueft | generiert | 24/7 | geometrie+vision_llm |
| `svs_ade32a824d` | SVS | geprueft | generiert | 8/5 | geometrie+vision_llm |
| `svs_b0f52f06ae` | SVS | geprueft | generiert | 68/5 | geometrie+vision_llm |
| `svs_b309d0e7d1` | SVS | geprueft | generiert | 11/4 | geometrie+vision_llm |
| `svs_b3b63a9928` | SVS | geprueft | generiert | 45/7 | geometrie+vision_llm |
| `svs_c256fa7b5e` | SVS | geprueft | generiert | 42/2 | geometrie+vision_llm |
| `svs_ca3160edc9` | SVS | geprueft | generiert | 8/1 | geometrie+vision_llm |
| `svs_d249925502` | SVS | geprueft | generiert | 3/1 | geometrie+vision_llm |
| `svs_d56de5a120` | SVS | geprueft | generiert | 32/0 | geometrie+vision_llm |
| `svs_d7043a0c64` | SVS | geprueft | generiert | 123/0 | geometrie+vision_llm |
| `svs_d71a8bbaeb` | SVS | geprueft | generiert | 32/1 | geometrie+vision_llm |
| `svs_dd35620949` | SVS | geprueft | generiert | 106/0 | geometrie+vision_llm |
| `svs_ee74891811` | SVS | geprueft | generiert | 11/0 | geometrie+vision_llm |
| `svs_f189140cd4` | SVS | geprueft | acroform | 11/5 | geometrie+vision_llm |
| `svs_fdff7f61d9` | SVS | geprueft | generiert | 7/4 | geometrie+vision_llm |
| `bvaeb_065d8e895c` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_1098f9c623` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_1403d06bcc` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_1763dc833a` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_33a743386a` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_45a5fbabcb` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_5883d051d5` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_5a1a9fa3be` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_5bc6b8dffc` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_5e7a0bd8bd` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_5e7d1d0757` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_86a3bfe0c1` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_896332b9b5` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_ae64677c4d` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_af85004bfd` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_b3a645b562` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_b98a28852d` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_bc56f75b63` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_dc951b7f88` | BVAEB | nicht_moeglich | keine | 0/0 | Infoblatt/Merkblatt ohne Ausfüllfelder |
| `bvaeb_f02f463367` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_f0fdd1ddcc` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_fe7b5d744c` | BVAEB | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `fsw_ausfuellhilfe` | FSW | nicht_moeglich | keine | 0/0 | Infoblatt/Merkblatt ohne Ausfüllfelder |
| `fsw_information_zum_verwendungsnachweis_pge_fuer_pa_bf` | FSW | nicht_moeglich | keine | 0/0 | Infoblatt/Merkblatt ohne Ausfüllfelder |
| `oegk_antrag_auf_familienzuschlag` | ÖGK | nicht_moeglich | generiert | 0/0 | Bild-PDF ohne Textebene – OCR (Vision) ausstehend |
| `oegk_ausfuellhilfe_antrag_selbsthilfegruppen_und_selbsthilfeorgan` | ÖGK | nicht_moeglich | keine | 0/0 | Infoblatt/Merkblatt ohne Ausfüllfelder |
| `oegk_ausfuellhilfe_antrag_verbaende_und_kontaktstellen` | ÖGK | nicht_moeglich | keine | 0/0 | Infoblatt/Merkblatt ohne Ausfüllfelder |
| `oegk_infoblatt` | ÖGK | nicht_moeglich | keine | 0/0 | Infoblatt/Merkblatt ohne Ausfüllfelder |
| `oegk_rezeptgebuehrenbefreiung` | ÖGK | nicht_moeglich |  | / | kein PDF im Cache (Download fehlgeschlagen) |
| `oegv_form_1002` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_1008` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_1171` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_1182` |  | nicht_moeglich | keine | 0/0 | Infoblatt/Merkblatt ohne Ausfüllfelder |
| `oegv_form_1183` |  | nicht_moeglich | keine | 0/0 | Infoblatt/Merkblatt ohne Ausfüllfelder |
| `oegv_form_1185` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_1186` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_1187` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_1188` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_1189` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_12` |  | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `oegv_form_290` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_70` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_819` |  | nicht_moeglich |  | / | Live-Link ersetzt durch Elternseite (kein PDF auffindbar, §3 Regel 2b) |
| `oegv_form_943` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `sms_01_behindertenpass_antrag_bundesweit_fertig` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_02_behindertenpass_parkausweis_29bstvo_antrag_bundesweit_fer` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_ansuchen_pflegekurse` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_antrag_mobilitaetszuschuss_2026` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_antrag_pflegekarenzgeld_kinderreha` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_24hb_ansuchen_final` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_24hb_antrag_bundesweit_bg_end` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_24hb_antrag_bundesweit_hr_end` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_24hb_antrag_bundesweit_hu_end` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_24hb_antrag_bundesweit_pl_end` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_24hb_antrag_bundesweit_ro_end` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_24hb_antrag_bundesweit_sk_end` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_pflegekarenzgeld_familienhospizkarenz_antrag_bundeswe` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_pflegekarenzgeld_pflegekarenz_antrag_bundesweit` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `sms_pflege_pflegende_angehoerige_antrag_bundesweit` | Sozialministeriumservice | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `svs_08c67b09d4` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_0ddb8c08eb` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_0f3e57a9a6` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_119da7417b` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_121801c48a` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_135b6ca309` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_1c72512e1b` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_1f3d9bab8d` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_242f379243` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_267ca5f971` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_2b74591a7a` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_31a2409f9b` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_37a0a4e492` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_3c84fa8684` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_3f90063303` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_472195c587` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_49018a6cbe` | SVS | nicht_moeglich | generiert | 0/0 | keine Ausfüllbereiche erkannt |
| `svs_49c8a54594` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_4c92497fe9` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_51ed947fa5` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_53c4ad582c` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_5b5418ab90` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_5cc4906ec2` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_65b6094c70` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_6ccf6e8ab4` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_72da9b6956` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_74e122a2da` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_7ae3283450` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_7e4eba193d` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_7ed51b9264` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_826e3c6fdc` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_83356b783e` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_873a96b2ee` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_88225eaf41` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_8e2d25e5b3` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_910ac7e409` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_93a8e6d064` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_957881df55` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_9649e76a44` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_9986ab3647` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_9b7ed48e5d` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_a781424829` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_ab9bf50811` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_b0c94ab028` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_b611711e7e` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_ba604a1d6e` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_c02e4d0e11` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_c178d86228` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_c3601c59f1` | SVS | nicht_moeglich |  | / | Word-Datei (.doc/.docx) statt PDF – Konvertierung (LibreOffice) im Build noch nicht verfügbar |
| `svs_cc625de488` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_dcd1ee9558` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_de79deb4dd` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_ded4396284` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_e2685bfcde` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_ed0063c15e` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_f04e94f7de` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_f0fd72c75d` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_f112e03cb1` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_f64bd39fcc` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_f9acc43d54` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_fc26178445` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_fd85531df4` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `svs_fdc851d526` | SVS | nicht_moeglich | generiert | 0/0 | keine Ausfüllbereiche erkannt |
| `svs_ff6805b370` | SVS | nicht_moeglich |  | / | Online-Antrag (kein PDF) – Michi verlinkt das Online-Formular, Empfänger ist gesetzt |
| `bvaeb_1f57895949` | BVAEB | ungeprueft | generiert | 42/18 | Wert steht im richtigen Feld, aber der Eintrag erscheint doppelt/überlappend in derselben Kopfzeile.; Die Versicherungsnummer steht zweimal nebeneinander im sel |
| `bvaeb_511d7d28c5` | BVAEB | ungeprueft | generiert | 34/1 | Blauer Wert steht im richtigen Feld, überdeckt aber den gedruckten Label-Text teilweise |
| `bvaeb_5d0b1eec8a` | BVAEB | ungeprueft | acroform | 117/29 | Wert steht im falschen Feld (gehört nicht zu dieser Zeile/Personentabelle).; Wert steht im falschen Feld (mehrfach in der Leistungs-/Zeittabelle statt im passen |
| `bvaeb_98ad753e16` | BVAEB | ungeprueft | acroform | 28/7 | Überlappung Name_1 / Adresse_1; Überlappung Name_1 / Postleitzahl_Ort_1; Überlappung Name_1 / Dienstgeber_1; Überlappung Name_2 / Adresse_1; Überlappung Name_2  |
| `bvaeb_9d7f0d0bf6` | BVAEB | ungeprueft | acroform | 185/57 | Wert steht im Feld der antragstellenden Person; unter dem Abschnitt 'ZU PFLEGENDE PERSON' ist dieselbe Versicherungsnummer ebenfalls eingetragen und gehört nich |
| `bvaeb_b810982b07` | BVAEB | ungeprueft | generiert | 33/23 | Wert scheint in mehrere wiederholte Personenzeilen eingetragen; einige davon wirken wie Tabellen-/Zusatzzeilen statt nur Antragsstellerin; Mehrfach in wiederhol |
| `bvaeb_c3b9f02942` | BVAEB | ungeprueft | acroform | 59/14 | Name der Vertreterin steht im Feld für das Kind/Jugendlichen, nicht bei der antragstellenden Person.; Wert erscheint im Feld „Versicherte/r Name“ bzw. bei der Z |
| `bvaeb_d215f68314` | BVAEB | ungeprueft | acroform | 17/6 | Wert steht im Feld des Antragstellers und passt zum Label; aber die Person ist als Antragsteller/ינ markiert, nicht als Vater. Falls als Vater gemeint, keine Ta |
| `bvaeb_d5d8b8b408` | BVAEB | ungeprueft | generiert | 10/3 | Blauer Wert steht im richtigen Feld, aber der gedruckte Text im Feld wird teilweise überdeckt und ist dadurch unleserlich.; Blauer Wert steht im richtigen Feld, |
| `bvaeb_d9d797a31a` | BVAEB | ungeprueft | acroform | 28/23 | Familienname der Arbeitnehmer:in im Feld für Arbeitgeber:in eingetragen; Sozialversicherungsnummer im Feld für Arbeitgeber:in eingetragen; PLZ im Feld für Arbei |
| `bvaeb_f2f5519e61` | BVAEB | ungeprueft | acroform | 44/17 | Wert steht im Abschnitt zu Pflichtversicherung/Eigenpension und wirkt dort nicht eindeutig dem vorgesehenen Feld zugeordnet; zudem ist der Eintrag unplausibel d |
| `fsw_240315_verwendungsnachweis_halbjaehrlich_handschriftlich_bf` | FSW | ungeprueft | generiert | 208/7 | Blauer Text steht im falschen Bereich bzw. über dem Feldrand statt sauber im Ort/Datum-Feld; Der blaue Wert liegt im falschen Formularbereich und gehört hier of |
| `fsw_240315_verwendungsnachweis_monatlich_handschriftlich_bf` | FSW | ungeprueft | generiert | 37/1 | Blauer Wert steht teilweise auf gedrucktem Formulartext bzw. am unteren Rand des Feldes; Wert ist in ein Feld für die antragstellende Person gesetzt; auf den ge |
| `fsw_haftungserklaerung` | FSW | ungeprueft | acroform | 33/20 | Wert 'Tochter' gehört nicht zur ersten obsorgeberechtigten Person; das Feld ist falsch befüllt bzw. semantisch unplausibel.; Wert 'Tochter' gehört nicht zur zwe |
| `fsw_jahreskarte_der_wl_fuer_gehoerlose_menschen` | FSW | ungeprueft | acroform | 74/35 | Datum im falschen Format/abgeschnitten (Jahr endet sichtbar als 1948 statt 2025).; Nur 'Karl' eingetragen; Feld verlangt Familien- und Vorname. |
| `fsw_mobile_fruehfoerderung` | FSW | ungeprueft | acroform | 66/16 | Wert steht im passenden Feld, aber die angegebene Testperson heißt Anna Berger; im Formular ist als Vorname Lena eingetragen, das passt nicht zur Person.; Wert  |
| `fsw_vollmacht` | FSW | ungeprueft | acroform | 25/18 | Überlappung Ort VollmachtnehmerIn / Geburtsdatum VollmachtgeberIn; Überlappung Ort VollmachtnehmerIn / Familienname VollmachtnehmerIn; Überlappung Ort Vollmacht |
| `oegk_anamnesebogen_vu` | ÖGK | ungeprueft | generiert | 107/3 | Blauer Wert liegt im Feld für das Ausfülldatum (TT-MM-JJ), nicht bei der Sozialversicherungsnummer; zudem überdeckt er den gedruckten Feldbereich.; Blauer Wert  |
| `oegk_antrag_selbsthilfegruppen_und_selbsthilfeorganisationen` | ÖGK | ungeprueft | acroform | 124/15 | Wert steht offenbar im Feld der antragstellenden Organisation/Personenangabe, passt aber nicht zu Anna Berger bzw. der dort angegebenen Person.; Eingetragener W |
| `oegk_au_meldung_fuer_kundencenter` | ÖGK | ungeprueft | generiert | 7/2 | Blaueingabe steht im falschen Feld; passt nicht zum Label/Feldinhalt der Wohnadresse.; Blaueingabe steht im Feld 'Wohnadresse' statt in einem passenden Vorname- |
| `oegk_bestaetigung_der_aerztlichen_untersuchung_bei_inanspruchnahm` | ÖGK | ungeprueft | generiert | 10/2 | Wert steht im richtigen Feld, aber wirkt knapp und leicht innerhalb des Formulartextbereichs; kein schwerer Fehler; blauer Text liegt im richtigen Datumsfeld, ü |
| `oegk_erklaerung` | ÖGK | ungeprueft | generiert | 4/3 | Wert steht im richtigen Feld, aber die Schreibweise ist invers zur Beschriftung (Vorname/Nachname-Reihenfolge nicht klar passend zum Label).; Blauer Wert ragt l |
| `oegk_fragebogen_zur_anamnese_krankengeschichte` | ÖGK | ungeprueft | generiert | 107/4 | steht im Feld für das Ausfülldatum/Datum, nicht passend zum Sozialversicherungsnummern-Label; steht im Datum-Feld nahe/auf der Datumszeile statt klar im passend |
| `oegk_genehmigung_fuer_grosse_psychotherapie` | ÖGK | ungeprueft | generiert | 28/2 | Wert steht im Versicherungsnummer-Feld statt im Vorname-Feld; falsches Feld.; Blauer Text liegt im rechten Eingabebereich der Indikationsstellung/Therapieplan-S |
| `oegk_leeres_formularherunterladen` | ÖGK | ungeprueft | generiert | 61/6 | Wert steht im falschen Feld; gehört nicht in das kleine „für“-Feld.; Wert ist nicht passend zur Feldbeschriftung; Personenname steht nicht eindeutig als Vor- un |
| `oegv_form_1005` |  | ungeprueft | generiert | 41/2 | Blaue '2' steht im passenden Feld, ragt aber in den gedruckten Textbereich der Zeile hinein; Blaue '2' steht im passenden Feld, ragt aber in den gedruckten Text |
| `oegv_form_1583` |  | ungeprueft | acroform | 506/31 | Wert steht im falschen Feld: Anna ist als Sandra eingetragen.; Mehrere Werte sind offensichtlich in benachbarte falsche Felder gerutscht (z. B. Ort/Telefon/E-Ma |
| `oegv_form_1584` |  | ungeprueft | acroform | 311/21 | Wert steht im Feld für frühere Namen, passt aber offenbar nicht zur Person/ist als identischer Nachname doppelt eingetragen; Mehrere Werte scheinen in benachbar |
| `oegv_form_265` | PVA, BVAEB | ungeprueft | acroform | 54/24 | Wert wurde im Feld 'männlich' eingetragen, obwohl 'weiblich' gefüllt werden sollte; Hausnr. / Stiege / Tür fehlt bzw. ist in der Zeile nicht passend zum Adressf |
| `oegv_form_301` | PVA, SVS, BVAEB | ungeprueft | acroform | 169/34 | Überlappung VSNR_1#p8 / Name Vers |
| `oegv_form_303` | PVA, BVAEB | ungeprueft | acroform | 375/50 | Wert passt nicht ins Feld/Label: eingefügt statt SVNR ein Geburtsdatum; Wert passt nicht ins Feld/Label: eingefügt statt SVNR ein Geburtsdatum; Titel-Feld mit ' |
| `oegv_form_38` | PVA, BVAEB | ungeprueft | generiert | 244/22 | Wert steht im Kinder-Tabelle/Zeile, nicht beim antragstellenden Personenfeld und gehört nicht zu Anna Berger als Hauptantragstellerin.; VSNR/Geburtsdatum wirkt  |
| `oegv_form_417` | PVA, BVAEB | ungeprueft | acroform | 748/52 | Der eingetragene Wert 'Lena' steht im Feldbereich für Staatsangehörigkeit und passt weder zum Label noch zur Personentabelle.; Der Wert 'Österreich' steht in ei |
| `oegv_form_68` |  | ungeprueft | acroform | 60/16 | Überlappung Geburtsdatum / Staatsbürgerschaft; Überlappung Geburtsdatum / wohnhaft  PLZ; Überlappung Geburtsdatum / wohnhaft Ort; Überlappung Geburtsdatum / woh |
| `oegv_form_77` | PVA, BVAEB | ungeprueft | acroform | 583/59 | Wert 'Sandra' steht im Feld für die Vertreterin und passt zur Person; Wert 'Beispielgasse' steht im Adressbereich der Vertreterin, die restlichen Adressbestandt |
| `oegv_form_876` | SVS | ungeprueft | generiert | 198/38 | Wert steht im Feld für die versicherte Person; auf Personenzuordnung unauffällig; Wert im passenden Feld; Wert erscheint mehrfach im richtigen Personenfeld; una |
| `pva_antrag_kur_reha` | PVA | ungeprueft | acroform | 92/16 | Name steht im Feld für Angehörige/weitere Person statt bei der antragstellenden Person; Feldbezug falsch; Geburtsjahr/Vorjahresfeld wirkt der falschen Person bz |
| `pva_gvr001_uebergangsgeld` | PVA | ungeprueft | acroform | 361/26 | Mehrere Werte sind gegenseitig vertauscht bzw. in falschen Feldern platziert (z.B. Berger, Anna, Huber).; Blauer Wert steht im falschen Feld (Wien statt Geschle |
| `sms_acc_11_individualfoerderung_kfz_antrag_bundesweit_23_ferti` | Sozialministeriumservice | ungeprueft | acroform | 149/11 | Blauer Wert steht nicht im vorgesehenen Datum-Feld, sondern links über der Linie/außerhalb des Unterschriftsbereichs. |
| `svs_02a6e5560a` | SVS | ungeprueft | generiert | 81/23 | Wert steht im falschen Feldbereich bzw. doppelt im Namensblock und ragt in benachbarte Zellen; Wert liegt in der falschen Spalte/Überlappung zum benachbarten Na |
| `svs_05ba22bfec` | SVS | ungeprueft | acroform | 43/24 | Wert steht im Feld für Familienname/Nachname statt Vorname; Feld bleibt leer, obwohl dort ein Wert vorgesehen ist; Versicherungsnummer wirkt um einen Ziffernblo |
| `svs_0857765cf6` | SVS | ungeprueft | generiert | 205/36 | Wert wirkt in Kopf-/Namensfeld statt passendem Antragsfeld platziert; Mehrfach in verschiedenen Feldern derselben Person eingetragen; eines liegt im falschen Te |
| `svs_087aa96b7f` | SVS | ungeprueft | generiert | 32/12 | Wert '05.11.2026' steht im Datum-Feld, nicht im Feld zur Frage nach Selbstversicherung.; Wert 'nein' und das Datum wurden beide im Bereich der Frage platziert;  |
| `svs_0b0397c909` | SVS | ungeprueft | generiert | 207/56 | Blauer Text steht mehrfach in den falschen Teilfeldern bzw. überlappend in Nachbarfeldern; Zuordnung nicht sauber erkennbar.; Feld ist gefüllt, wirkt aber teilw |
| `svs_165250e244` | SVS | ungeprueft | generiert | 14/9 | Wert steht im falschen Feldbereich bzw. im Bereich der Versicherungsnummer, nicht sauber im passenden Antragssteller-Feld; Wert wirkt aufgeteilt/überlagert bena |
| `svs_1d9377fa4c` | SVS | ungeprueft | generiert | 23/4 | Zwei blaue Vornamen eingetragen; das zweite Feld wirkt dem Kind/anderen Bereich zugeordnet statt der antragstellenden Person. |
| `svs_1fa1b79e09` | SVS | ungeprueft | generiert | 36/1 | Wert steht im Feld für den besuchenden nahen Angehörigen statt im Patientenfeld; falsche Person/Tabelle |
| `svs_27deb3a04c` | SVS | ungeprueft | generiert | 8/5 | Wert steht im falschen Feld; eingetragen ist nur 'ja' statt des Namensfelds der Person.; Wert liegt im richtigen Feld, aber knapp am unteren Rand; kein schwerer |
| `svs_29dfd03b3c` | SVS | ungeprueft | generiert | 210/29 | Vorname ist doppelt eingetragen; ein Eintrag sitzt im Titel-/Leerbereich des Vorname-Feldes und wirkt nicht sauber einem Feld zugeordnet; Wert steht im falschen |
| `svs_2c0f5c2465` | SVS | ungeprueft | generiert | 29/11 | Text steht in einem Feldbereich, der offenbar für die versicherte Person gedacht ist, wirkt aber nicht passend zur Feldbezeichnung bzw. überlappt den Bereich de |
| `svs_2cbcc28731` | SVS | ungeprueft | generiert | 113/7 | Wert steht im Feld der versicherten Person, nicht bei der antragstellenden Person Anna Berger; zudem passt die Person nicht zum Formularteil.; Anrede ist in ein |
| `svs_307139b381` | SVS | ungeprueft | generiert | 8/4 | Datum steht im roten Feld und überdeckt den gedruckten Formulartext teilweise; Wert steht im Feld für Geburtsort/Ort und passt zum Label; keine Layout-Fehlplatz |
| `svs_41a31dc531` | SVS | ungeprueft | generiert | 189/50 | Feld ist für die versicherte Person befüllt, gehört also nicht nur zur Antragstellerin; hier aber plausibel zur Person selbst.; Blauer Text sitzt in den vorgese |
| `svs_43c09993d6` | SVS | ungeprueft | generiert | 51/14 | Wert steht im Feld der Antragsteller-Zeile, aber die Platzierung wirkt nicht sauber dem richtigen Beschriftungsfeld zugeordnet; außerdem mehrfacher Eintrag ders |
| `svs_5db13e8d84` | SVS | ungeprueft | generiert | 85/17 | Wert erscheint zweimal im selben Feldbereich; Berger steht im Titel-Feld statt nur im Familienname-Feld; Wert steht im richtigen Feld, aber wirkt auf die Formul |
| `svs_6077b075b0` | SVS | ungeprueft | generiert | 84/13 | Blauer Wert steht in der Zeile/Feldposition ohne passendes Label; wirkt wie versehentlich in freier Tabellenzelle statt im Vorname-Feld der hinterbliebenen Pers |
| `svs_64d7a2fa52` | SVS | ungeprueft | generiert | 40/10 | Wert steht im Feld für den Versicherungszweig, plausibel passend; kein Fehler erkennbar, aber die Eintragung wirkt auf Seite 1 als Auswahl statt Freitext.; Im F |
| `svs_6bb2c05b5b` | SVS | ungeprueft | generiert | 176/10 | Wert steht im Tabellenbereich für weitere Personen/nebentätige Personen, nicht im Hauptfeld der antragstellenden Person; Blauer Text überdeckt gedruckte Tabelle |
| `svs_6f835bdf72` | SVS | ungeprueft | generiert | 107/4 | Wert steht nicht im passenden Feld für die Sozialversicherungsnummer, sondern liegt über der Zeile/außerhalb des vorgesehenen Feldes.; Wert steht im Ausfülldatu |
| `svs_764bfe25d7` | SVS | ungeprueft | generiert | 38/11 | Blauer Text 'Wien' steht im Geburtsdatum-Bereich und passt nicht zum Label; wirkt im falschen Feld.; Blauer Wert überdeckt/berührt gedruckten Text im Formularbe |
| `svs_7fd685b258` | SVS | ungeprueft | generiert | 210/41 | Blauer Wert 'verwitwet' steht im Feld für Aufenthaltsort statt im Personenstand-Feld; Zweiter Vorname 'Anna' ist im Feld/Teilbereich für Titel bzw. unpassendes  |
| `svs_83f5e7f885` | SVS | ungeprueft | generiert | 49/20 | Mehrere Status-Felder wurden mit demselben Wert „verwitwet“ befüllt; passt nur zu einem Status-Feld, die anderen sind falsch zugeordnet.; Befüllt im Bereich des |
| `svs_872e7c08de` | SVS | ungeprueft | generiert | 124/36 | Wert steht im falschen Feldbereich; er liegt nicht sauber im Vorname-Feld bzw. überlappt den Beschriftungsbereich.; Wert sitzt im falschen/überlappenden Feldber |
| `svs_8b3041804f` | SVS | ungeprueft | generiert | 51/8 | steht im Feld Familienname und Vorname des/der Versicherten, wirkt aber wie ein Personenfeld für die versicherte Person/Partnerin und nicht für die Vertreterin; |
| `svs_8e9deedf69` | SVS | ungeprueft | generiert | 48/3 | Blauer Wert steht im Feld der versicherten Person, wirkt aber laut Vorgabe auf die Vertreterin bezogen; auf dem Formular ist dieses Feld nur für Angehörige geda |
| `svs_94be936a97` | SVS | ungeprueft | generiert | 108/39 | Blauer Wert ist im Datumsfeld mehrfach eingetragen und überlappt den Bereich des Stichtags; zudem wirkt die Zuordnung der einzelnen Teilfelder nicht sauber.; De |
| `svs_9632b0f532` | SVS | ungeprueft | generiert | 164/38 | Wert gehört offenbar zur Vertreterin, steht aber im Feld der versicherten Person; im Vorname-Feld steht zusätzlich/überlappend noch ein zweiter Wert; Feld wirkt |
| `svs_9789119039` | SVS | ungeprueft | generiert | 15/8 | Wert 'Vorsorgevollmacht' steht offenbar im Feld für den Betriebsführer und passt nicht zur Person/Position; zudem wirkt der Bereich überlagert.; Rote Markierung |
| `svs_a3e61b98e0` | SVS | ungeprueft | generiert | 8/4 | Blauer Wert steht im falschen Feld/zu weit links über dem Textlabel statt sauber im Ausfüllbereich der Zeile.; Blauer Wert ist im richtigen Bereich, aber liegt  |
| `svs_a51d6609b2` | SVS | ungeprueft | generiert | 143/29 | Wert steht im falschen Personenstand-Feld; Text passt nicht zum Label.; Blauer Text steht im Tabellenbereich auf Seite 1; Feldzuordnung wirkt korrekt, aber ähnl |
| `svs_a75a51eb62` | SVS | ungeprueft | generiert | 224/13 | Wert steht teils im Kopf-/Tabellenbereich und nicht sauber im vorgesehenen Feld; außerdem doppelt eingetragen.; Im Feld platziert, aber der blaue Text wirkt in  |
| `svs_ace9027e9b` | SVS | ungeprueft | generiert | 7/4 | Feld ist doppelt ausgefüllt; ein Eintrag steht offenbar in der Zeile für Angehörigendaten und gehört nicht zur versicherten Person. |
| `svs_aec8f41370` | SVS | ungeprueft | generiert | 220/39 | Wert scheint in Kopf-/Zeilenbereich der Tabelle zu liegen und überdeckt bzw. berührt gedruckten Text.; Eintrag liegt sehr nah am gedruckten Tabellenrand; kein k |
| `svs_af4e3a6dc6` | SVS | ungeprueft | generiert | 99/31 | Vorname und Familienname sind in den Feldern doppelt bzw. teilweise im jeweils falschen Feldbereich platziert; auf S. 1 steht der Familienname auch im Vorname-B |
| `svs_b547a057ec` | SVS | ungeprueft | generiert | 100/34 | Werte wirken in den vorgesehenen Feldern platziert, aber die Kopfzeile zeigt unterschiedliche Personenbezüge (Berger Sandra statt Anna Berger); Der Wert steht i |
| `svs_c98bfa5613` | SVS | ungeprueft | generiert | 130/34 | Wert steht doppelt/teilweise im falschen Bereich: ein Eintrag liegt im Nachbarfeld bzw. überlappt mit der Feldstruktur.; Ein Vorname-Eintrag wirkt im falschen F |
| `svs_ca0209d3a4` | SVS | ungeprueft | generiert | 98/9 | Wert im Feld der Telefonnummer platziert statt bei Versicherungsnummer; Versicherungsnummer statt Telefonnummer eingetragen; Adresswert erscheint doppelt im sel |
| `svs_ca759a2171` | SVS | ungeprueft | generiert | 224/27 | Wert steht im Feld der verstorbenen Person; für Anna Berger als Antragstellerin nicht passend.; Werte sind in der Rubrik „Verstorbene Person“ eingetragen und da |
| `svs_ce3087cbd9` | SVS | ungeprueft | acroform | 117/33 | blauer Wert im falschen Feld; dort steht ein Name statt Datum; blauer Wert im falschen Feld; dort steht ein Name statt Datum; blauer Wert im falschen Feld; dort |
| `svs_d1714bfd91` | SVS | ungeprueft | generiert | 104/21 | Name und Vorname sind vertauscht bzw. doppelt/falsch befüllt; Der Eintrag steht im Bereich der versicherten Person, aber die Namensfelder sind falsch zugeordnet |
| `svs_d1dedfbaf2` | SVS | ungeprueft | generiert | 7/3 | Wert steht im Feld für Anrede/Personenstandszeile und wirkt für die antragstellende Person passend, aber der blaue Text überdeckt den gedruckten Feldtext teilwe |
| `svs_d60dbb1d91` | SVS | ungeprueft | generiert | 51/11 | Wert steht im Kopfbereich bzw. teils außerhalb des vorgesehenen Feldes und liegt über gedrucktem Tabellenrand/Trennlinien.; Wert erscheint mehrfach im selben Be |
| `svs_da67a428d4` | SVS | ungeprueft | generiert | 82/21 | Wert steht sichtbar außerhalb des vorgesehenen Feldes bzw. liegt auf dem grünen Rand/übergang zum nächsten Abschnitt.; Wert ist im falschen Feld platziert; dort |
| `svs_de6db7e6fc` | SVS | ungeprueft | generiert | 240/49 | Wert steht im Feld der Antragstellenden Person bzw. zusätzlich im falschen Bereich auf Seite 2; Vertreterinnenbereich ist ansonsten leer/mehrfach befüllt; Wert  |
| `svs_f05fde2918` | SVS | ungeprueft | generiert | 120/12 | Wert 'Berger Sandra' liegt im Feld der versicherten Person, wirkt aber wie Vertreterin/versicherte Person verwechselt; zusätzlich steht daneben 'Sandra Berger'  |
| `svs_f72386e769` | SVS | ungeprueft | generiert | 25/12 | Wert steht im Feld für den Antragsteller, passt aber offenbar nicht zur antragstellenden Person/Vertreter-Zuordnung im Layout; Wert steht in einer Tabelle für w |
| `svs_f7f9d5ea65` | SVS | ungeprueft | generiert | 257/42 | Wert steht im falschen Personenstand-Feld bzw. falsche Beschriftung; Eintrag sitzt im Abschnitt für weitere Angehörige, nicht bei Anna Berger; Einträge gehören  |
| `svs_f839ad647c` | SVS | ungeprueft | generiert | 54/11 | Blauer Wert steht nicht im passenden Vorname-Feld bzw. ist versetzt im Adressbereich platziert.; Nachname ist im Kopfbereich des Datenblocks platziert; Label/Fe |
| `svs_f92a457213` | SVS | ungeprueft | generiert | 17/5 | Blauer Wert steht nicht im passenden Ankreuzfeld, sondern in der Zeile darunter und überdeckt gedruckten Formulartext.; Wert sitzt knapp im Feld; keine eindeuti |
| `svs_fbd7bfa4e7` | SVS | ungeprueft | generiert | 20/9 | Wert steht im Feld des zweiten Elternteils; dieses sollte zur Vertreterin gehören, nicht zur antragstellenden Person bzw. wirkt wie falsche Personenzuordnung; K |
