# Live-Links – Bericht (Stand 2026-11-05 22:05 UTC)

Erzeugt von `report.py`. Code: `linkcheck.py` → `formulare_live.py` → `report.py` (alle in `knowledge/build/links/`).

## 1. Demo-Seed-Formulare (Gate: 100 % live)

**6/7 mit Live-PDF-URL des Trägers.**

| formular_id | Status | lokal vs. live | Abgleich | Felder lokal → live | Live-URL |
|---|---|---|---|---|---|
| `pva_pal080` | live | **identisch** | sha256_identisch | 102 → 102 | https://www.pv.at/cdscontent/load?contentid=10008.781956 |
| `oegk_fahrtkosten_wien` | live | **identisch** | sha256_identisch | 13 → 13 | https://www.oegk.at/cdscontent/load?contentid=10008.777900&version=1785415038 |
| `antrag_reha_kur` | live | **identisch** | sha256_identisch | 96 → 96 | https://www.sozialversicherung.at/cdscontent/load?contentid=10008.555945&version=1767088043 |
| `antrag_ahv_reha_unfall` | live | **identisch** | sha256_identisch | 59 → 59 | https://www.pv.at/cdscontent/load?contentid=10008.781971 |
| `fsw_antrag_foerderung` | live | **identisch** | sha256_identisch | 122 → 122 | https://www.fsw.at/downloads/foerderwesen_anerkennung/foerderansuchen/subjektfoerderung/fsw-antrag-auf-foerderung-von-leistungen.pdf |
| `fsw_einrichtungswunsch` | live | **identisch** | sha256_identisch | 13 → 13 | https://www.fsw.at/downloads/foerderwesen_anerkennung/foerderansuchen/subjektfoerderung/FSW-Antrag-Beilage-Einrichtungswunsch.pdf |
| `fsw_bedarfsmeldung_wg` | ersetzt_b | **nicht_gefunden** | – | 21 → None | https://www.fsw.at/p/seniorinnen-wohngemeinschaften-basispaket |

- Bei sha256-identischen Dateien sind die Feldnamen 1:1 gleich. Das **B5-Feld-Mapping kann ohne Änderung auf die Live-Version** zeigen.
- `fsw_bedarfsmeldung_wg`: Auf fsw.at gibt es **kein öffentliches PDF**. Die Infoseite verlinkt nur die Broschüre; das Formular hat das Feld „Name Partnerorganisation“ und wird vermutlich über den WG-Träger ausgefüllt. Ersatz nach Regel b: Elternseite https://www.fsw.at/p/seniorinnen-wohngemeinschaften-basispaket, ausgefüllt wird die lokale Kopie (mit Stand-Hinweis). Folge fürs Gate: **6/7 mit Datei-Link, 7/7 mit Live-Link**. Offener Punkt: beim FSW (01 24 5 24) nach der Download-URL fragen.
- pv.at leitet `…&version=…` auf die versionslose URL um. Gespeichert ist `final_url`, die stabil bleibt, wenn die PVA eine neue Version hochlädt; der Hash zeigt die Änderung an.

- Recherchierte Kandidaten-URLs stehen in `seed_kandidaten.json`. linkcheck prüft sie mit; zugeordnet wird nur bei sha256-Gleichheit bzw. Feldähnlichkeit.

## 2. Live-Quote je Quelle

### 2.1 Alle URLs (die die API ausliefern kann)

URLs gesamt 26288, davon Web 15066 (Rest: `sozdok:`/`file:`-Kennungen ohne Web-Link). Geprüft: 6296 (davon 800 über frisches `manifest.json` der Quelle, ohne eigenen Request).

| kind | URLs | geprüft | ok | Quote ok/geprüft |
|---|---|---|---|---|
| formular_pdf | 874 | 874 | 873 | 99.9 % |
| online_antrag | 124 | 124 | 117 | 94.4 % |
| stelle | 9497 | 3477 | 3300 | 94.9 % |
| quelle | 743 | 743 | 741 | 99.7 % |
| seite | 3828 | 1078 | 1073 | 99.5 % |

Noch nicht geprüft sind vor allem die ~7.600 Arzt-Websites aus `wien_ogd` (Host praxisplan.at) und 3.018 RIS-Seiten (sozdok_ris). linkcheck prüft höchstens 1.500 Seiten/Stellen pro Host und Lauf (`--host-cap`, die ältesten zuerst), damit wir keine Domain massenhaft crawlen. Die volle Abdeckung entsteht über mehrere tägliche Läufe. **Policy-Frage an den Koordinator:** Ungeprüfte `stelle`-URLs bis dahin ausblenden (strenge §3.2) oder mit Hinweis zeigen?

### 2.2 Formular-URLs je Quelle (`formulare.url_pdf`)

| Quelle | ok | tot | ungeprüft | Quote |
|---|---|---|---|---|
| aek_wien | 279 | 0 | 0 | 100.0 % |
| bvaeb | 154 | 1 | 0 | 99.4 % |
| fsw | 25 | 0 | 0 | 100.0 % |
| oegk | 109 | 0 | 0 | 100.0 % |
| oesterreich_gv | 41 | 0 | 0 | 100.0 % |
| pva | 4 | 0 | 0 | 100.0 % |
| seed_kandidat | 11 | 0 | 0 | 100.0 % |
| sozialministeriumservice | 24 | 0 | 0 | 100.0 % |
| svs | 235 | 0 | 0 | 100.0 % |
| zusatz | 1 | 0 | 0 | 100.0 % |

## 3. Kanonische Formular-Registry (`formulare_live.jsonl`)

954 kanonische Formulare (dedupliziert über sha256 und `final_url`). Mehrfach gefunden: 40.

| art | n | davon live | lotse_zeigen |
|---|---|---|---|
| antrag | 310 | 215 | 310 |
| tarif_vertrag | 303 | 303 | 0 |
| sonstiges | 283 | 261 | 0 |
| beilage | 32 | 31 | 32 |
| info_seite | 16 | 16 | 0 |
| merkblatt | 8 | 8 | 8 |
| video | 2 | 2 | 0 |

`url_status`: live 836, online 102, ersetzt_b 15, ersetzt_a 1

Regel: Die Lotse-API zeigt nur `lotse_zeigen=true` (art ∈ antrag|beilage|merkblatt **und** Link live oder ersetzt). `tarif_vertrag` (ÄK-Wien-Verträge/Tarife für Ärzt:innen), `info_seite` (HTML statt Datei), `video`, `sonstiges` (Broschüren) erscheinen nicht als Formular.

## 4. Tote Links und Ersatzentscheidungen (ARCHITEKTUR §3.2)

192 geprüfte URLs nicht ok. Ersatzregel: c_ausblenden_review 187, b_elternseite 4, a_relative_url_repariert 1

| kind | URL | Fehler | Ersatz | Regel | Quelle (Datei:Zeile) |
|---|---|---|---|---|---|
| formular_pdf | http:///cdscontent/load?contentid=10008.676636&version=1576507368 | ungueltige_url (kein Host – relativer Link falsch aufgeloest?) | https://www.bvaeb.at/cdscontent/load?contentid=10008.676636&version=1576507368 | a_relative_url_repariert | bvaeb/formulare.jsonl:93 |
| online_antrag | https://www.formularservice.gv.at/site/fsrv/user/formular.aspx?pid=b74a92e8b7ba4434a1adff6eb9a8f8ad&pn=B00dc47 | HTTP 500 | https://www.oesterreich.gv.at/de/formsearch/form/1002 | b_elternseite | oesterreich_gv/formulare.jsonl:4 |
| online_antrag | https://www.formularservice.gv.at/site/fsrv/user/formular.aspx?pid=b74a92e8b7ba4434a1adff6eb9a8f8ad&pn=B4491c7 | HTTP 500 | – | c_ausblenden_review | sozialministeriumservice/leistungen.jsonl:4 |
| online_antrag | https://www.formularservice.gv.at/site/fsrv/user/formular.aspx?pid=b74a92e8b7ba4434a1adff6eb9a8f8ad&pn=B5a6dd7 | HTTP 500 | https://www.oesterreich.gv.at/de/formsearch/form/1171 | b_elternseite | oesterreich_gv/formulare.jsonl:36 |
| online_antrag | https://www.formularservice.gv.at/site/fsrv/user/formular.aspx?pid=b74a92e8b7ba4434a1adff6eb9a8f8ad&pn=B830ce1 | HTTP 500 | – | c_ausblenden_review | sozialministeriumservice/leistungen.jsonl:5 |
| online_antrag | https://www.formularservice.gv.at/site/fsrv/user/formular.aspx?pid=b74a92e8b7ba4434a1adff6eb9a8f8ad&pn=Bae4c36 | HTTP 500 | – | c_ausblenden_review | sozialministeriumservice/leistungen.jsonl:6 |
| online_antrag | https://www.formularservice.gv.at/site/fsrv/user/formular.aspx?pid=b74a92e8b7ba4434a1adff6eb9a8f8ad&pn=Bc9b445 | HTTP 500 | https://www.oesterreich.gv.at/de/formsearch/form/70 | b_elternseite | oesterreich_gv/formulare.jsonl:33 |
| online_antrag | https://www.formularservice.gv.at/site/fsrv/user/formular.aspx?pid=b74a92e8b7ba4434a1adff6eb9a8f8ad&pn=Bd9b2a5 | HTTP 500 | https://www.oesterreich.gv.at/de/formsearch/form/520 | b_elternseite | oesterreich_gv/formulare.jsonl:28 |
| stelle | http://flora-apotheke.co.at | ConnectError: All connection attempts failed | – | c_ausblenden_review | wien_ogd/stellen.jsonl:286 |
| stelle | http://members.chello.at/verdi-apotheke/ | ConnectError: All connection attempts failed | – | c_ausblenden_review | wien_ogd/stellen.jsonl:333 |
| stelle | http://members.nextra.at/agnes.apotheke | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:35 |
| stelle | http://www.andromeda-apotheke.at | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:186 |
| stelle | http://www.apo-einsiedler.at.vu | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:64 |
| stelle | http://www.apo21.at | HTTP 404 | – | c_ausblenden_review | wien_ogd/stellen.jsonl:131 |
| stelle | http://www.aponet.at/margaretenapo | HTTP 404 | – | c_ausblenden_review | wien_ogd/stellen.jsonl:65 |
| stelle | http://www.aponet.at/sandleitenapo | HTTP 404 | – | c_ausblenden_review | wien_ogd/stellen.jsonl:356 |
| stelle | http://www.aposchuhmeierplatz.at | HTTP 404 | – | c_ausblenden_review | wien_ogd/stellen.jsonl:251 |
| stelle | http://www.apotheke-altmannsdorf.com | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:326 |
| stelle | http://www.apotheke-zum-schutzengel.at | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:57 |
| stelle | http://www.barmherzige-brueder.at/bbwien/index1.ht | HTTP 404 | – | c_ausblenden_review | wien_ogd/stellen.jsonl:91 |
| stelle | http://www.bmi.gv.at/ | 301 | – | c_ausblenden_review | oesterreich_gv/stellen.jsonl:7 |
| stelle | http://www.caritas-salzburg.at/hilfe-angebote/betreuung-begleitung-und-pflege/fachstelle-fuer-pflegende-angeho | HTTP 404 | – | c_ausblenden_review | gesundheit_gv/stellen.jsonl:496 |
| stelle | http://www.hauptapotheke.at | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:315 |
| stelle | http://www.herzjesu-apotheke.at | ConnectError: All connection attempts failed | – | c_ausblenden_review | wien_ogd/stellen.jsonl:62 |
| stelle | http://www.igel-apotheke.at | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:263 |
| stelle | http://www.kaiserkrone.co.at | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:215 |
| stelle | http://www.marienapo-red-ribbon.at | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:20 |
| stelle | http://www.marienapo-wien20.at | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:209 |
| stelle | http://www.members.a1.net/babenbergerapo | HTTP 404 | – | c_ausblenden_review | wien_ogd/stellen.jsonl:11 |
| stelle | http://www.muttergottes-apotheke.at | HTTP 404 | – | c_ausblenden_review | wien_ogd/stellen.jsonl:58 |
| stelle | http://www.pharmcare.at/europa-apotheke/ | ConnectError: All connection attempts failed | – | c_ausblenden_review | wien_ogd/stellen.jsonl:292 |
| stelle | http://www.sonnen-apotheke.cc | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:319 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1686 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8342 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1687 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8338 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1689 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8340 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1691 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8368 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1693 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8369 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1695 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8371 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1696 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8363 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1697 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8362 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1698 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8320 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1701 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8326 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1702 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8325 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1703 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8331 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1704 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8330 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1708 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8329 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1712 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8324 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1716 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8291 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1718 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8288 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1719 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8293 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1721 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8300 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1722 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8304 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1723 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8301 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1724 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8308 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1725 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8312 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1726 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8315 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1727 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8303 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1728 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8307 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1729 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8313 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1730 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8316 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1731 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8311 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1732 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8310 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1733 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8299 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1735 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8309 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1736 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8305 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1737 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8287 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1738 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:9119 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1739 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:9112 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1740 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8845 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1765 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8394 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1767 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8505 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1768 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8616 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1769 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8727 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1775 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8817 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1781 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8823 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1782 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8822 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1784 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8824 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1785 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8826 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1787 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8820 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1788 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8830 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1789 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8831 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1790 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8821 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1792 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8834 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1794 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8828 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1796 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8835 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1798 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8837 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1799 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8947 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1800 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:9016 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1801 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:9079 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1802 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8295 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1803 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8280 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1805 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8306 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1806 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8317 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1809 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8328 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1811 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8372 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1814 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8383 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1815 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8417 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1816 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8428 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1817 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8350 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1819 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8450 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1820 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8439 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1822 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8705 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1824 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8561 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1826 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8472 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1827 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8483 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1828 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8494 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1829 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8517 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1830 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8528 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1832 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8739 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1838 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8761 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1839 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8794 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1843 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8716 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1846 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8750 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1847 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8783 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1849 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8805 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1855 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8970 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1858 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8993 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1859 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8996 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1861 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8870 |
| stelle | http://www.wienkav.at/kav/akh/Medstellen_Anzeigen.asp?id=1863 | ConnectError: [Errno 8] nodename nor servname provided, or not known | – | c_ausblenden_review | wien_ogd/stellen.jsonl:8816 |
| … | 72 weitere in `links.jsonl` (`ok=false`) | | | | |

## 5. Kaputte relative URLs → Fix gehört in die Quelle

- **bvaeb** `sources/bvaeb/out/formulare.jsonl` Zeile 93 (`url_pdf`, id `bvaeb_d94f955fd5`): `http:///cdscontent/load?contentid=10008.676636&version=1576507368` → Ersatz: https://www.bvaeb.at/cdscontent/load?contentid=10008.676636&version=1576507368 (a_relative_url_repariert)

Ursache: Das bvaeb-HTML enthält wörtlich `href="http:///cdscontent/load?…"` (z. B. `sources/bvaeb/raw/1326bc857f…html`). `urljoin()` lässt das unverändert. **Fix** in `sources/svs/_common.py` → `norm_portal_url()` (gemeinsam für svs/bvaeb): wenn `scheme` http(s) und `netloc` leer, `netloc` (und `https`) von der Basis-URL übernehmen. Bis dahin repariert `linkcheck.py` die URL selbst (Host der Quelle) und prüft sie live (Regel `a_relative_url_repariert`).

## 6. Review-Queue (`review_queue.jsonl`)

- seed_formular_ohne_live_pdf: 1

## 7. Schnittstelle für knowledge-db (`build_db.py`)

Alle Dateien liegen in `knowledge/build/links/`. Reihenfolge im Update-Lauf: `linkcheck.py` → `formulare_live.py` → `report.py`.

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
