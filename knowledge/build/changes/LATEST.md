# Änderungsbericht Wissens-DB – 2026-11-05T2205Z

**Swap:** ja – lotse.sqlite ist neu  
**Links:** {'links': 26288, 'frisch_ok': 6104, 'quelle': 'knowledge/build/links/links.jsonl', 'formulare_live': 954}  
**Embeddings:** minishlab/potion-multilingual-128M (neu 0, Cache 30478)

## Gates

- ✓ **schema_fehlerfrei**: 0 Fehler
- ✓ **source_md_und_manifest**: alle vorhanden
- ✓ **keine_leeren_quellen**: keine
- ✓ **golden (a roh): Mama packt's nicht mehr allein**: {'erwartet': ['mobile_pflege_fsw', 'pflegegeld'], 'begriffe': None, 'top5': ['mobile_pflege_fsw', 'pflegekarenz', 'pflegegeld', 'mobile_dienste', 'pflegeberatung'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Mama packt's nicht mehr allein**: {'erwartet': ['mobile_pflege_fsw', 'pflegegeld'], 'begriffe': ['Pflegegeld', 'mobile Pflege'], 'top5': ['mobile_pflege_fsw', 'mobile_dienste', 'pflegegeld', 'pflegekarenz', 'pflegeberatung'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Meine Mama packt's nimma allein daham, was kann ich tun?**: {'erwartet': ['fsw_pflegeberatung', 'heimhilfe_wien', 'mobile_pflege_fsw', 'pflegeberatung', 'pflegegeld'], 'begriffe': None, 'top5': ['mobile_pflege_fsw', 'pflegekarenz', 'mobile_dienste', 'pflegegeld', 'heimhilfe_wien'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Meine Mama packt's nimma allein daham, was kann ich tun?**: {'erwartet': ['fsw_pflegeberatung', 'heimhilfe_wien', 'mobile_pflege_fsw', 'pflegeberatung', 'pflegegeld'], 'begriffe': ['Pflegegeld', 'Heimhilfe', 'Pflegeberatung'], 'top5': ['mobile_pflege_fsw', 'pflegekarenz', 'mobile_dienste', 'pflegegeld', 'heimhilfe_wien'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Meine Mutter braucht jetzt Hilfe, was muss ich machen?**: {'erwartet': ['fsw_pflegeberatung', 'mobile_pflege_fsw', 'pflegeberatung', 'pflegegeld'], 'begriffe': None, 'top5': ['pflegegeld', 'mobile_pflege_fsw', 'pflegeberatung', 'pflegekarenz', 'mobile_dienste'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Meine Mutter braucht jetzt Hilfe, was muss ich machen?**: {'erwartet': ['fsw_pflegeberatung', 'mobile_pflege_fsw', 'pflegeberatung', 'pflegegeld'], 'begriffe': ['Pflegegeld', 'Pflegeberatung'], 'top5': ['pflegegeld', 'mobile_pflege_fsw', 'pflegeberatung', 'pflegekarenz', 'mobile_dienste'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Taxi zur Bestrahlung**: {'erwartet': ['fahrtkostenzuschuss', 'krankentransport'], 'begriffe': None, 'top5': ['krankentransport', 'fahrtkostenzuschuss', 'fahrtendienst_fahrtkostenersatz_wien', 'fahrtkostenersatz_gehoerlose_wien', 'anschlussheilverfahren'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Taxi zur Bestrahlung**: {'erwartet': ['fahrtkostenzuschuss', 'krankentransport'], 'begriffe': ['Krankentransport', 'Fahrtkostenzuschuss'], 'top5': ['fahrtkostenzuschuss', 'krankentransport', 'fahrtendienst_fahrtkostenersatz_wien', 'fahrtkostenersatz_gehoerlose_wien', 'anschlussheilverfahren'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Wer zahlt das Taxi zur Bestrahlung?**: {'erwartet': ['fahrtkostenzuschuss', 'krankentransport'], 'begriffe': None, 'top5': ['krankentransport', 'fahrtkostenzuschuss', 'fahrtendienst_fahrtkostenersatz_wien', 'fahrtkostenersatz_gehoerlose_wien', 'krankengeld'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Wer zahlt das Taxi zur Bestrahlung?**: {'erwartet': ['fahrtkostenzuschuss', 'krankentransport'], 'begriffe': ['Krankentransport', 'Fahrtkosten'], 'top5': ['krankentransport', 'fahrtkostenzuschuss', 'fahrtendienst_fahrtkostenersatz_wien', 'fahrtkostenersatz_gehoerlose_wien', 'krankengeld'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Zahnspange Kind**: {'erwartet': ['zahnspange_kfo'], 'begriffe': None, 'top3': ['zahnspange_kfo', 'kinderimpfprogramm', 'zahnbehandlung_zahnersatz'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Zahnspange Kind**: {'erwartet': ['zahnspange_kfo'], 'begriffe': ['Kieferorthopädie'], 'top3': ['zahnspange_kfo', 'kinderimpfprogramm', 'zahnbehandlung_zahnersatz'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Mein Bub braucht vielleicht eine Zahnspange**: {'erwartet': ['zahnspange_kfo'], 'begriffe': None, 'top5': ['zahnspange_kfo', 'zahnbehandlung_zahnersatz', 'mundhygiene_kinder', 'zahnbehandlung', 'gesundheitsberatung_1450'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Mein Bub braucht vielleicht eine Zahnspange**: {'erwartet': ['zahnspange_kfo'], 'begriffe': ['Kieferorthopädie', 'Gratis-Zahnspange'], 'top5': ['zahnspange_kfo', 'zahnbehandlung_zahnersatz', 'mundhygiene_kinder', 'zahnbehandlung', 'impfungen_erwachsene'], 'modus': 'hybrid'}
- ✓ **golden (a roh): mehr bewegen**: {'erwartet': ['bewegt_im_park'], 'begriffe': None, 'top5': ['bewegungsempfehlungen', 'gesundheitskurse_bewegung', 'bewegt_im_park', 'gesunder_ruecken', 'gesundheitshunderter_svs'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): mehr bewegen**: {'erwartet': ['bewegt_im_park'], 'begriffe': ['Bewegung', 'Gesundheitsförderung'], 'top5': ['bewegungsempfehlungen', 'gesundheitskurse_bewegung', 'bewegt_im_park', 'gesunder_ruecken', 'gesundheitshunderter_svs'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Ich will was für meine Gesundheit tun, mich mehr bewegen**: {'erwartet': ['bewegt_im_park', 'gesundheitshunderter_svs', 'vorsorgeuntersuchung'], 'begriffe': None, 'top5': ['gesundheitskurse_bewegung', 'bewegungsempfehlungen', 'gesundheitshunderter_svs', 'bewegt_im_park', 'gesunder_ruecken'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Ich will was für meine Gesundheit tun, mich mehr bewegen**: {'erwartet': ['bewegt_im_park', 'gesundheitshunderter_svs', 'vorsorgeuntersuchung'], 'begriffe': ['Gesundheitsförderung', 'Bewegung'], 'top5': ['gesundheitskurse_bewegung', 'bewegungsempfehlungen', 'gesundheitshunderter_svs', 'bewegt_im_park', 'gesunder_ruecken'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Pflegegeld beantragen**: {'erwartet': ['pflegegeld'], 'begriffe': None, 'top1': ['pflegegeld'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Pflegegeld beantragen**: {'erwartet': ['pflegegeld'], 'begriffe': ['Pflegegeld', 'Antrag'], 'top1': ['pflegegeld'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Rezeptgebühr zu teuer, kleine Pension**: {'erwartet': ['rezeptgebuehrenbefreiung'], 'begriffe': None, 'top3': ['rezeptgebuehrenbefreiung', 'ausgleichszulage', 'rezeptgebuehrenobergrenze'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Rezeptgebühr zu teuer, kleine Pension**: {'erwartet': ['rezeptgebuehrenbefreiung'], 'begriffe': ['Rezeptgebührenbefreiung'], 'top3': ['rezeptgebuehrenbefreiung', 'ausgleichszulage', 'rezeptgebuehrenobergrenze'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Die Medikamente sind so teuer, die Mama hat nur eine kleine Pension**: {'erwartet': ['rezeptgebuehrenbefreiung'], 'begriffe': None, 'top5': ['rezeptgebuehrenbefreiung', 'ausgleichszulage', 'rezeptgebuehrenobergrenze', 'heilmittel_bewilligungspflicht', 'pension_allgemein'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Die Medikamente sind so teuer, die Mama hat nur eine kleine Pension**: {'erwartet': ['rezeptgebuehrenbefreiung'], 'begriffe': ['Rezeptgebührenbefreiung', 'Ausgleichszulage'], 'top5': ['rezeptgebuehrenbefreiung', 'ausgleichszulage', 'rezeptgebuehrenobergrenze', 'heilmittel_bewilligungspflicht', 'pension_allgemein'], 'modus': 'hybrid'}
- ✓ **golden (a roh): nach dem Spital wieder fit werden, Erholung**: {'erwartet': ['kur', 'reha_medizinisch', 'reha_onkologisch'], 'begriffe': None, 'top5': ['kur', 'reha_onkologisch', 'anschlussheilverfahren', 'reha_beruflich', 'reha_kinder'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): nach dem Spital wieder fit werden, Erholung**: {'erwartet': ['kur', 'reha_medizinisch', 'reha_onkologisch'], 'begriffe': ['Rehabilitation', 'Kur'], 'top5': ['kur', 'reha_onkologisch', 'anschlussheilverfahren', 'reha_beruflich', 'reha_kinder'], 'modus': 'hybrid'}
- ✓ **golden (a roh): Ich muss mir frei nehmen um die Mama zu pflegen**: {'erwartet': ['familienhospizkarenz', 'pflegekarenz'], 'begriffe': None, 'top5': ['pflegekarenz', 'pflegekarenzgeld', 'pflegegeld', 'angehoerigen_unterstuetzung_ersatzpflege', 'gesundheitsangebote_svs'], 'modus': 'hybrid'}
- ✓ **golden (b umgeschrieben): Ich muss mir frei nehmen um die Mama zu pflegen**: {'erwartet': ['familienhospizkarenz', 'pflegekarenz'], 'begriffe': ['Pflegekarenz', 'Pflegeteilzeit'], 'top5': ['pflegekarenz', 'pflegekarenzgeld', 'pflegegeld', 'angehoerigen_unterstuetzung_ersatzpflege', 'gesundheitsangebote_svs'], 'modus': 'hybrid'}
- ✓ **links_demo_formulare_100**: {'live': '6/7', 'fallback_lokal+elternseite': ['fsw_bedarfsmeldung_wg'], 'fehlt': []}
- ✓ **links_formulare_95**: 493/493 = 100%
- ✓ **traeger_register**: 9 Träger, Landesstellen vollständig
- ✓ **leistung_hat_quelle**: alle mit Quelle
- ✓ **icd_hint_policy**: ok (vom Build entfernt: 0)

## Quellen im Build
| Quelle | Status | Dok. | Leist. | Stellen | Form. | Fehler | Warn. |
|---|---|---|---|---|---|---|---|
| aek_wien | ok | 94 | 1 | 1 | 279 | 0 | 0 |
| bvaeb | ok | 1346 | 15 | 9 | 185 | 0 | 0 |
| fsw | ok | 629 | 36 | 11 | 26 | 0 | 0 |
| gesundheit_gv | ok | 2276 | 45 | 614 | 0 | 0 | 0 |
| oegk | ok | 1154 | 48 | 277 | 115 | 0 | 0 |
| oesterreich_gv | ok | 2216 | 22 | 13 | 63 | 0 | 0 |
| pva | ok | 242 | 8 | 20 | 4 | 0 | 0 |
| reimedy_kb | ok | 0 | 0 | 4 | 0 | 0 | 0 |
| sozdok_ris | ok | 19911 | 0 | 0 | 0 | 0 | 1 |
| sozialministeriumservice | ok | 136 | 7 | 2 | 24 | 0 | 0 |
| svbox_local | ok | 935 | 39 | 2 | 7 | 0 | 0 |
| svs | ok | 1378 | 13 | 6 | 300 | 0 | 0 |
| wien_ogd | ok | 10 | 0 | 9140 | 0 | 0 | 0 |

## Dokumente (neu / geändert / entfernt)
- keine Änderungen

## Leistungsgraph
- neu: 0 
- geändert: 0 
- entfernt: 0 
- Statuswechsel: 
- Konflikte: pflegegeld: ['antrag: widerspruch']; wohn_pflegehaus_fsw: ['antrag: widerspruch']; reha_onkologisch: ['antrag: widerspruch']; zahnspange_kfo: ['kosten: zahlen_abweichend']; mundhygiene_kinder: ['zustaendig: zahlen_abweichend']; reha_medizinisch: ['kosten: zahlen_abweichend', 'antrag: widerspruch']; wochengeld: ['antrag: widerspruch']; krankengeld: ['kosten: zahlen_abweichend']; foerderung_24h_betreuung: ['antrag: widerspruch']; behindertenpass: ['antrag: widerspruch']; zahnersatz: ['kosten: zahlen_abweichend']; kinderbetreuungsgeld: ['kosten: zahlen_abweichend']
- Stellen: {'neu': 0, 'entfernt': 0, 'geaendert': 0}  Formulare: {'neu': 1, 'entfernt': 0, 'geaendert': 4} (geänderte Formulare = neue Version → Feld-Mapping B5 prüfen)

**0 neue Einträge in `review_queue.jsonl`.**
