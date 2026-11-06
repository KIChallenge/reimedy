# Quelle `impfplan`: Österreichischer Impfplan (BMASGPK)

Stand: 06.11.2026. Version: **Impfplan Österreich 2026/2027, Version 1.1 vom 14.10.2026** (ersetzt Version 1.0 vom 17.09.2026).
Download: <https://broschuerenservice.sozialministerium.gv.at/Home/Download?publicationId=420&attachmentName=Impfplan_Oesterreich_2026_2027.pdf>
Übersichtsseite (alle Versionen, Archiv): <https://www.sozialministerium.gv.at/Themen/Gesundheit/Impfen/impfplan.html>

## Was `ingest.py` tut
`uv run knowledge/sources/impfplan/ingest.py [--offline]`
- Lädt das PDF (242 Seiten) über einen bedingten GET mit ETag und Last-Modified. Der sha256 kommt in `out/manifest.json`.
- `out/impfplan_intervalle.jsonl` ist **kuratiert**. Jede Zeile hat die Felder `krankheit`, `impfung`, `altersgruppe`, `alter_von`/`alter_bis`, `intervall`, `intervall_monate` (null = einmalig bzw. keine Auffrischung), `dosen`, `zeitpunkt`, `kostenlos_impfprogramm`, `zitate[{seite, zitat, url}]`, `version`, `gueltig_ab` und `leistung_id`.
- **Jedes Zitat wird bei jedem Lauf wörtlich gegen den PDF-Text der angegebenen Seite geprüft.** Fehlt eines, bricht der Lauf ab. Damit liefern wir nach einer neuen Fassung keine veralteten Intervalle aus.
- `out/documents.jsonl` enthält die Seiten der genutzten Kapitel als zitierbare Abschnitte (RAG): Diphtherie/Tdap S. 20–22, Influenza S. 52–56, Pertussis S. 82–84, Pneumokokken S. 89–92, Herpes Zoster S. 123–126.

## Abdeckung (6 Zeilen)
| id | Intervall laut Plan | Seiten |
|---|---|---|
| influenza_erwachsene | jährlich, idealerweise Mitte Oktober/November, gratis im Impfprogramm | 52, 55, 56 |
| influenza_ab_60 | jährlich, mit Impfstoffen speziell für diese Altersgruppe | 56 |
| tdap_bis_60 | Auffrischung alle 10 Jahre | 22 |
| tdap_ab_60 | Auffrischung alle 5 Jahre | 22 |
| zoster_ab_60 | 2 Dosen, Abstand mind. 2 Monate (2–6); derzeit keine Auffrischung; ab 60 gratis | 123, 126 |
| pneumokokken_ab_60 | einmalig PCV21 (Capvaxive), gratis im Impfprogramm | 89, 90, 92 |

## Lücken
- Kinderimpfplan (6-fach, MMR, HPV, Meningokokken …), COVID-19, FSME, RSV und spezielle Indikationen sind **nicht** als Intervalle modelliert. Für Kinder gilt laut 05 der Verweis „mit der Kinderärztin besprechen“. Die Seiten zu den modellierten Kapiteln sind im RAG enthalten.
- Abweichende Intervalle bei spezieller Indikation (Immunsuppression usw.) sind bewusst nicht drin. Das klärt die Ärztin.
- Das Merkblatt der MedUni Innsbruck ist laut Auftrag von 05 **nicht** aufgenommen.

## Nutzung (Grenze)
Der Lotse gibt die Empfehlung **des Impfplans** mit Version weiter („Laut Österreichischem Impfplan 2026/2027 …“) und rechnet `letzte_eintragung + intervall_monate` als „laut Impfplan ab … vorgesehen“, nie als „überfällig“. Ob eine Impfung im Einzelfall passt, klärt die Ärztin (loesungen/05 §6.4).

## Update-Strategie
Der Impfplan erscheint jährlich, meist im September/Oktober, dazu kommen Zwischenversionen. Bei einer neuen Fassung `URL`, `VERSION` und `GUELTIG_AB` in `ingest.py` anpassen und dann laufen lassen. Die Zitatprüfung zeigt, welche Intervalle sich geändert haben, etwa Tdap: 2025/26 noch 5 Jahre, 2026/27 wieder 10 Jahre bis 60.

## Lizenz
Öffentliches Dokument des Bundesministeriums. Wir verwenden nur kurze wörtliche Zitate mit Quelle, Seite und Version, keine Bearbeitung des Inhalts.
