# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=4"]
# ///
"""svbox_local: lokale SV-Box-Daten (_Source/) -> Wissens-DB-Format (CONTRACT.md Schemas A, B, C, D, E).

Aufruf:  uv run knowledge/sources/svbox_local/ingest.py [--force]
Idempotent: pro Eingabedatei wird sha256 im manifest.json gehalten; nur neue/geaenderte
Dateien werden neu verarbeitet (Teilergebnisse in out/_parts/), danach werden die finalen
out/*.jsonl aus allen Teilen neu zusammengesetzt. Nur lesen in _Source/, schreiben nur hier.
Nicht enthalten (andere Sessions): Rechtstexte (sozdok_ris), Befunde (elga).
"""
from __future__ import annotations
import glob, unicodedata, hashlib, html, json, logging, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

logging.getLogger("pypdf").setLevel(logging.ERROR)
from pypdf import PdfReader  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                      # Repo-Root (knowledge/sources/svbox_local -> ..)
SRC = ROOT / "_Source"
OUT = HERE / "out"
PARTS = OUT / "_parts"
SOURCE_ID = "svbox_local"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
LIC = ("Lokale SV-Box-Daten des Hackathons (_Source/); Originaldokumente der ÖGK bzw. "
       "Österreichischen Zahnärztekammer/FSW/PVA. Nur Hackathon-Nutzung; Zitate mit Quellenangabe.")


# ----------------------------------------------------------------------------- helpers
def gl(d: Path, pattern: str) -> list[Path]:
    """glob, unicode-normalisierungs-unabhängig (macOS NFD vs NFC)."""
    import fnmatch, unicodedata
    pat = unicodedata.normalize("NFC", pattern)
    return sorted(f for f in d.iterdir() if fnmatch.fnmatch(unicodedata.normalize("NFC", f.name), pat))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def doc_prefix(p: Path) -> str:
    return f"{SOURCE_ID}:{sha1(rel(p))[:12]}"


def file_url(p: Path) -> str:
    return "file:" + rel(p)


def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def pdf_pages_raw(p: Path) -> list[str]:
    r = PdfReader(str(p))
    return [(pg.extract_text() or "") for pg in r.pages]


def norm(t: str) -> str:
    """Fliesstext: Silbentrennung zusammenziehen, Zeilen verbinden, Aufzaehlungszeichen -> •."""
    t = re.sub(r"(?m)^\s*y\s+", "• ", t)
    t = re.sub(r"(?<=[a-zäöüß])-\n(?=[a-zäöüß])", "", t)
    t = re.sub(r"\s*\n\s*(?=•)", " ", t)
    t = re.sub(r"\s*\n\s*", " ", t)
    t = re.sub(r"[ \t ]+", " ", t)
    return t.strip()


def chunk_text(t: str, maxlen: int = 1900) -> list[str]:
    """Teilt an Satzenden in <= maxlen Zeichen."""
    sents = re.split(r"(?<=[.!?:])\s+(?=[A-ZÄÖÜ•„\d])", t)
    out, cur = [], ""
    for s in sents:
        while len(s) > maxlen:  # Notfall: harter Schnitt an Leerzeichen
            cut = s.rfind(" ", 0, maxlen)
            cut = cut if cut > 200 else maxlen
            if cur:
                out.append(cur); cur = ""
            out.append(s[:cut]); s = s[cut:].lstrip()
        if len(cur) + len(s) + 1 > maxlen and cur:
            out.append(cur); cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        out.append(cur)
    return out


PROTECT = ["z.B.", "d.h.", "u.a.", "Abs.", "Nr.", "ca.", "inkl.", "bzw.", "Dr.", "Mag.", "lit.", "ggf.", "vgl.", "evtl.", "max.", "mind.", "Tel.", "Z."]


def sentences(t: str) -> list[str]:
    for i, a in enumerate(PROTECT):
        t = t.replace(a, a.replace(".", f"․"))
    t = re.sub(r"(?<=\s)(\d{1,2})\.(?=\s[A-ZÄÖÜ])", lambda m: m.group(1) + "․", t)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„\d])|\s*•\s*", t)
    return [p.replace("․", ".").strip() for p in parts if p and len(p.strip()) > 25]


def pick(sents: list[str], pat: str, n: int = 4, maxlen: int = 420) -> list[str]:
    rx = re.compile(pat, re.I)
    out = []
    for s in sents:
        if rx.search(s) and s not in out:
            out.append(s[:maxlen].rsplit(" ", 1)[0] if len(s) > maxlen else s)
        if len(out) >= n:
            break
    return out


# ============================================================================ 1. Broschüre
BRO_CHAPTERS = [
    # (Titel, gedruckte Startseite, Kopfzeilen-Regex, Bereich, Gruppe)
    ("Sicher versorgt", 4, r"sicher versorgt", ["F"], "Meine ÖGK"),
    ("Mein Krankenversicherungsbeitrag", 5, r"Mein Krankenversiche", ["F"], "Meine ÖGK"),
    ("Meine Pflichtversicherung", 6, r"Meine Pflichtversicherung", ["F"], "Gut versichert"),
    ("Meine Mitversicherung", 6, r"Meine Mitversicherung", ["F", "E"], "Gut versichert"),
    ("Freiwillige Versicherung", 20, r"Freiwillige Versicherung", ["F"], "Gut versichert"),
    ("Vorsorgeuntersuchung", 23, r"vorsorgeuntersuchung\s+Sie wollen", ["A"], "Gesund leben"),
    ("Jugendlichenuntersuchung", 24, r"Jugendlichenuntersuchung\s+Die", ["A"], "Gesund leben"),
    ("Brustkrebs-Früherkennungsprogramm „früh erkennen”", 25, r"Brustkrebs-Früherkennungs", ["A"], "Gesund leben"),
    ("Diabetes im Griff mit „Therapie Aktiv”", 26, r"Diabetes im Griff", ["B", "C"], "Gesund leben"),
    ("Bewusst leben +", 26, r"Bewusst leben \+", ["B"], "Gesund leben"),
    ("Betriebliche Gesundheitsförderung", 27, r"Betriebliche Gesundheitsf", ["B"], "Gesund leben"),
    ("Schulische Gesundheitsförderung", 28, r"Schulische Gesundheitsf", ["B"], "Gesund leben"),
    ("Vereinscoaching", 29, r"Vereinscoaching", ["B"], "Gesund leben"),
    ("Frei von Tabak und Nikotin", 30, r"Frei von Tabak", ["B"], "Gesund leben"),
    ("Momente für mich", 31, r"Momente für mich", ["B"], "Gesund leben"),
    ("Richtig essen von Anfang an", 32, r"Richtig essen von Anfang", ["B"], "Gesund leben"),
    ("Impfungen", 32, r"Impfungen", ["A"], "Gesund leben"),
    ("Beweg' dich – Gesunder Rücken", 33, r"Beweg.{0,3}dich", ["B"], "Gesund leben"),
    ("Magazin „Meine Gesundheit”", 34, r"Magazin", ["B"], "Gesund leben"),
    ("Ärztliche Hilfe", 34, r"Ärztliche Hilfe", ["C"], "Gesund werden"),
    ("Ärztliche Behandlung im Urlaub", 40, r"Ärztliche Behandlung im Urlaub", ["C"], "Gesund werden"),
    ("Heilmittel", 42, r"Befreiung von der Rezeptgebühr\s+Ohne", ["C", "E"], "Gesund werden"),
    ("Heilbehelfe", 45, r"heilbehelfe\s+Sie brauchen", ["C"], "Gesund werden"),
    ("Hilfsmittel", 46, r"hilfsmittel\s+Ob Prothesen", ["C"], "Gesund werden"),
    ("Krankenhauspflege", 47, r"Krankenhauspflege\s+Sie müssen", ["C"], "Gesund werden"),
    ("Medizinische Hauskrankenpflege", 48, r"Medizinische\s+hauskrankenpflege", ["C", "D"], "Gesund werden"),
    ("Medizinische Maßnahmen der Rehabilitation", 48, r"Medizinische Maßnahmen\s+der rehabilitation", ["C"], "Gesund werden"),
    ("Krankenstand", 49, r"Krankenstand\s+Ein Krankenstand", ["E"], "Gesund werden"),
    ("Krankengeld", 53, r"Krankengeld\s", ["E"], "Gesund werden"),
    ("Wiedereingliederungsgeld", 58, r"Wiedereingliederungsgeld\s", ["E", "C"], "Gesund werden"),
    ("Rehabilitationsgeld", 60, r"Rehabilitationsgeld\s", ["E", "C"], "Gesund werden"),
    ("Kur und Erholung", 62, r"Kur und erholung", ["C"], "Gesund werden"),
    ("Transportkosten", 62, r"transportkosten", ["C"], "Gesund werden"),
    ("Sachleistungen (Mutterschaft)", 66, r"Ein Kind kommt\s+Sie bekommen", ["C"], "Ein Kind kommt"),
    ("Wochengeld", 66, r"Wochengeld\s", ["E"], "Ein Kind kommt"),
    ("Sonderwochengeld", 67, r"Sonderwochengeld\s", ["E"], "Ein Kind kommt"),
    ("Kinderbetreuungsgeld", 68, r"Kinderbetreuungsgeld\s", ["E"], "Ein Kind kommt"),
    ("Eltern-Kind-Pass-Untersuchungen", 74, r"Eltern-Kind-Pass", ["A"], "Ein Kind kommt"),
    ("Frühe Hilfen", 75, r"Frühe Hilfen", ["B", "E"], "Ein Kind kommt"),
    ("Konservierende-chirurgische Zahnbehandlung", 76, r"Konservierend", ["C"], "Gesunde Zähne"),
    ("Kieferorthopädie und Zahnspangen", 77, r"Kieferorthop", ["C"], "Gesunde Zähne"),
    ("Zahnersatz", 80, r"Zahnersatz", ["C"], "Gesunde Zähne"),
    ("Gratis-Mundhygiene für Kinder und Jugendliche", 81, r"Gratis-Mundhygiene", ["A", "B"], "Gesunde Zähne"),
    ("Telefonische Gesundheitsberatung 1450", 82, r"Telefonische Gesundheitsberatung", ["A", "C", "F"], "Service plus"),
    ("Online für Sie da", 83, r"Online für Sie da", ["F"], "Service plus"),
    ("Ombudsstelle", 85, r"Ombudsstelle", ["F"], "Service plus"),
    ("Unterstützungsfonds", 85, r"Unterstützungsfonds", ["E"], "Service plus"),
    ("ELGA – die elektronische Gesundheitsakte", 85, r"ELGA", ["F"], "Service plus"),
    ("Meine Gesundheitseinrichtungen", 89, r"Meine Zahngesundheitszentren", ["F"], "Meine Gesundheitseinrichtungen"),
]

# Kapitel -> Leistungs-Kandidat (leistung_id, Name, kurz_einfach). Kapitel ohne Eintrag: nur Dokumente.
BRO_LEISTUNG = {
    "Meine Mitversicherung": ("mitversicherung", "Mitversicherung von Angehörigen (beitragsfrei)",
                              "Ehepartner:innen, Kinder und weitere Angehörige können oft ohne eigenen Beitrag bei Ihnen mitversichert sein."),
    "Freiwillige Versicherung": ("freiwillige_versicherung", "Freiwillige Versicherung / Selbstversicherung",
                                 "Wer nicht pflichtversichert ist, kann sich freiwillig in der Krankenversicherung versichern."),
    "Vorsorgeuntersuchung": ("vorsorgeuntersuchung", "Vorsorgeuntersuchung (Gesundheits-Check)",
                             "Kostenloser Gesundheits-Check ab 18 Jahren, meist bei der Hausärztin oder dem Hausarzt."),
    "Jugendlichenuntersuchung": ("jugendlichenuntersuchung", "Jugendlichenuntersuchung",
                                 "Kostenloser jährlicher Gesundheits-Check für pflichtversicherte Jugendliche von 15 bis 18."),
    "Brustkrebs-Früherkennungsprogramm „früh erkennen”": ("brustkrebs_frueherkennung", "Brustkrebs-Früherkennungsprogramm „früh erkennen”",
                                                         "Mammografie mit e-card alle zwei Jahre, ohne Überweisung."),
    "Diabetes im Griff mit „Therapie Aktiv”": ("therapie_aktiv", "Therapie Aktiv (Diabetes-Betreuungsprogramm)",
                                               "Strukturiertes Betreuungsprogramm bei Diabetes über teilnehmende Ärzt:innen."),
    "Bewusst leben +": ("bewusst_leben_plus", "Bewusst leben +", "Gesundheitsförderungsangebot der ÖGK."),
    "Frei von Tabak und Nikotin": ("rauchfrei_programm", "Frei von Tabak und Nikotin", "Unterstützung beim Rauchstopp."),
    "Impfungen": ("impfungen", "Impfungen (Impfprogramme)", "Impfungen im Rahmen der öffentlichen Impfprogramme."),
    "Beweg' dich – Gesunder Rücken": ("gesunder_ruecken", "Beweg' dich – Gesunder Rücken", "Bewegungsprogramm für den Rücken."),
    "Ärztliche Hilfe": ("aerztliche_hilfe", "Ärztliche Hilfe (e-card, Vertragsärzt:innen, Wahlärzt:innen)",
                        "Behandlung bei Vertragsärzt:innen mit e-card; bei Wahlärzt:innen gibt es Kostenerstattung."),
    "Ärztliche Behandlung im Urlaub": ("behandlung_im_ausland", "Ärztliche Behandlung im Urlaub / Ausland",
                                       "Was die ÖGK bei Krankheit im Ausland übernimmt."),
    "Heilmittel": ("rezeptgebuehrenbefreiung", "Befreiung von der Rezeptgebühr",
                   "Wer wenig Einkommen hat oder bestimmte Leistungen bezieht, zahlt keine Rezeptgebühr."),
    "Heilbehelfe": ("heilbehelfe", "Heilbehelfe (Brillen, Einlagen, Kompressionsstrümpfe)",
                    "Zuschuss der ÖGK mit ärztlicher Verordnung, mit Selbstbehalt."),
    "Hilfsmittel": ("hilfsmittel", "Hilfsmittel (Prothesen, Rollstühle u. a.)", "Hilfsmittel auf ärztliche Verordnung, teils vorher zu genehmigen."),
    "Krankenhauspflege": ("krankenhauspflege", "Krankenhauspflege (Spitalsaufenthalt)",
                          "Die ÖGK übernimmt die Kosten in der allgemeinen Gebührenklasse; Kostenbeitrag für längstens 28 Tage pro Jahr."),
    "Medizinische Hauskrankenpflege": ("medizinische_hauskrankenpflege", "Medizinische Hauskrankenpflege",
                                       "Medizinische Pflege zu Hause statt im Spital (keine Grundpflege), zeitlich befristet."),
    "Medizinische Maßnahmen der Rehabilitation": ("reha_medizinisch", "Medizinische Rehabilitation (Reha-Aufenthalt)",
                                                  "Stationäre oder ambulante Reha mit ärztlichem Antrag und Bewilligung."),
    "Krankengeld": ("krankengeld", "Krankengeld", "Geldleistung bei Krankenstand."),
    "Wiedereingliederungsgeld": ("wiedereingliederungsgeld", "Wiedereingliederungsgeld", "Geldleistung bei stufenweisem Wiedereinstieg nach langem Krankenstand."),
    "Rehabilitationsgeld": ("rehabilitationsgeld", "Rehabilitationsgeld", "Geldleistung bei vorübergehender Berufsunfähigkeit."),
    "Kur und Erholung": ("kur_erholung", "Kur- und Erholungsaufenthalt", "Freiwillige Leistung; vorher beantragen, ärztlich begründet."),
    "Transportkosten": ("krankentransport", "Krankentransport / Fahrtkosten", "Transportkosten bei ärztlich bescheinigter Gehunfähigkeit."),
    "Sachleistungen (Mutterschaft)": ("mutterschaft_sachleistungen", "Sachleistungen bei Mutterschaft", "Versorgung in Schwangerschaft und Geburt."),
    "Wochengeld": ("wochengeld", "Wochengeld", "Geldleistung rund um die Geburt."),
    "Sonderwochengeld": ("sonderwochengeld", "Sonderwochengeld", "Geldleistung bei individuellem Beschäftigungsverbot."),
    "Kinderbetreuungsgeld": ("kinderbetreuungsgeld", "Kinderbetreuungsgeld", "Familienleistung nach der Geburt."),
    "Eltern-Kind-Pass-Untersuchungen": ("eltern_kind_pass", "Eltern-Kind-Pass-Untersuchungen", "Kostenlose Untersuchungen für Schwangere und Kinder."),
    "Frühe Hilfen": ("fruehe_hilfen", "Frühe Hilfen", "Unterstützung für Familien in der frühen Kindheit."),
    "Konservierende-chirurgische Zahnbehandlung": ("zahnbehandlung", "Konservierend-chirurgische Zahnbehandlung", "Zahnbehandlung auf e-card bei Vertragszahnärzt:innen."),
    "Kieferorthopädie und Zahnspangen": ("kieferorthopaedie_gratis_zahnspange", "Kieferorthopädie / Gratis-Zahnspange",
                                         "Kostenlose Zahnspange bei starker Fehlstellung (IOTN 4 oder 5), Behandlungsbeginn vor dem 18. Geburtstag."),
    "Zahnersatz": ("zahnersatz", "Zahnersatz", "Kostenzuschuss bzw. Sachleistung bei Zahnersatz."),
    "Gratis-Mundhygiene für Kinder und Jugendliche": ("mundhygiene_kinder_jugendliche", "Gratis-Mundhygiene für Kinder und Jugendliche",
                                                       "Kostenlose professionelle Mundhygiene für Kinder und Jugendliche."),
    "Telefonische Gesundheitsberatung 1450": ("gesundheitstelefon_1450", "Telefonische Gesundheitsberatung 1450",
                                              "Rund um die Uhr unter 1450 anrufen; erste Anlaufstelle bei Beschwerden. Im Notfall 144."),
    "Unterstützungsfonds": ("unterstuetzungsfonds", "Unterstützungsfonds", "Finanzielle Hilfe in Härtefällen."),
    "ELGA – die elektronische Gesundheitsakte": ("elga_info", "ELGA – elektronische Gesundheitsakte", "Zugang zu den eigenen Gesundheitsdaten."),
}

# Zusatz-Kandidaten aus bestimmten Kapiteln (gleicher Text, anderer Zweck)
BRO_EXTRA = [
    dict(chapter="Heilmittel", leistung_id="rezeptgebuehrenobergrenze", name="Rezeptgebührenobergrenze (2 % des Jahresnettoeinkommens)",
         kurz="Wer im Kalenderjahr viele Rezeptgebühren gezahlt hat, wird ab Erreichen der Obergrenze für den Rest des Jahres befreit.",
         vor=r"Obergrenze|Jahresnettoeinkommen|Mindestgrenze|Rest des Jahres|31\.12\.|Rezeptgebühren, die vom", kosten=r"Prozent|Rezeptgebühr in Höhe",
         abh=["rezeptgebuehrenbefreiung"], bereich=["E", "C"]),
    dict(chapter="Heilmittel", leistung_id="heilmittel_bewilligungspflicht", name="Bewilligungspflichtige Medikamente (Medizinischer Dienst)",
         kurz="Einige Arzneien muss die Ärztin bzw. der Arzt vorab vom Medizinischen Dienst der ÖGK genehmigen lassen.",
         vor=r"bewilligungspflichtig|Medizinischen Dienst|Rezeptgebühr in Höhe", kosten=r"Rezeptgebühr in Höhe", abh=[], bereich=["C"]),
]

# Rezeptgebührenbefreiung: feste Anker (Regex über Kapiteltext) -> kurzer Klartext
RGB_ANKER = [
    ("OHNE Antrag befreit, z. B.: Bezieher:innen einer Ausgleichszulage, Zivildiener:innen, Bezieher:innen von Mindestsicherung/Sozialhilfe, Asylwerber:innen",
     r"Beispielsweise.*?Asylwerberinnen und Asylwerber"),
    ("OHNE Antrag befreit: Patient:innen mit anzeigepflichtigen übertragbaren Krankheiten (nur Medikamente für diese Krankheit)",
     r"Für Patientinnen und Patienten mit anzeigepflichtigen übertragbaren Krankheiten\..*?erforderlich sind\."),
    ("MIT Antrag (Einkommensgrenze 2026): monatliche Nettoeinkünfte bis 1.308,39 € (Alleinstehende) bzw. 2.064,12 € (Ehepaare/Partnerschaften/Lebensgemeinschaften); +201,88 € pro Kind unter bestimmten Voraussetzungen",
     r"Für Personen, deren monatliche Nettoeinkünfte.*?pro Kind um 201,88 Euro\."),
    ("MIT Antrag bei überdurchschnittlichen Krankheitsausgaben (2026): monatliche Nettoeinkünfte bis 1.504,65 € (Alleinstehende) bzw. 2.373,74 € (Paare); +201,88 € pro Kind",
     r"Für Personen, die infolge ihrer Krankheit überdurchschnittliche Ausgaben nachweisen.*?pro Kind um 201,88 Euro\."),
    ("Nettoeinkommen = Summe aller Einkünfte minus gesetzliche Abzüge; Einkommen des Ehe-/Lebenspartners im gemeinsamen Haushalt zur Gänze, sonstiger Haushaltspersonen mit 12,5 %",
     r"Unter einem Nettoeinkommen versteht man.*?12,5 Prozent berücksichtigt\."),
    ("Nicht befreibar: freiwillig Versicherte nach § 16 Abs. 1 ASVG mit Hilfe/Zuschuss zum Lebensbedarf vom Sozialhilfeträger (und deren Angehörige)",
     r"Freiwillig versicherte Personen nach § 16 Abs\. 1 ASVG.*?nicht von der Rezeptgebühr befreit werden\."),
]


def build_broschuere(p: Path):
    raw = pdf_pages_raw(p)
    # Layout-Fix PDF-Seite 22: Tabelle (links/rechts) steht vor dem Auslands-Fragment und dem Heilmittel-Kopf.
    pg22 = raw[21]
    a = pg22.find("Befreiung von der Rezeptgebühr")
    b = pg22.find("schein beim ausländischen")
    c = pg22.find("\nheilmittel\n")
    if 0 <= a < b < c:
        head = pg22[:a]
        raw[21] = head + pg22[b:c] + "\n" + pg22[a:b] + pg22[c:]
    # laufende Kopfzeile (gedruckte Seitenzahlen) je PDF-Seite abspalten
    pages = {}
    printed = {}
    for i, t in enumerate(raw, 1):
        lines = t.split("\n")
        nums = re.findall(r"\d+", lines[0]) if lines and len(lines[0]) < 60 else []
        printed[i] = f"{nums[0]}–{nums[-1]}" if len(nums) >= 2 and nums[0] != nums[-1] else (nums[0] if nums else str(i))
        body = "\n".join(lines[1:] if nums else lines)
        pages[i] = body
    # ---- Dokumente: seitenweise (PDF-Seite = Doppelseite), Kapitel aus Inhaltsverzeichnis
    prefix, sha, url = doc_prefix(p), sha256_file(p), file_url(p)
    toc = [(t_, pr_, g_, b_) for (t_, pr_, _rx, b_, g_) in BRO_CHAPTERS]

    def chapters_on(pdfp):
        lo, hi = 2 * (pdfp - 1), 2 * (pdfp - 1) + 1  # gedruckte Seiten dieser Doppelseite
        res = []
        for k, (t_, pr_, g_, b_) in enumerate(toc):
            nxt = toc[k + 1][1] if k + 1 < len(toc) else 999
            if pr_ <= hi and nxt - 1 >= lo and not (nxt == pr_ and pr_ < lo):
                res.append((t_, g_, b_))
        return res

    docs, n = [], 0
    leist = []
    for pi in sorted(pages):
        if pi <= 2:
            continue  # Titel / Inhaltsverzeichnis
        t = norm(pages[pi])
        chs = chapters_on(pi)
        titles = " / ".join(c[0] for c in chs) or "Allgemein"
        bereich = sorted({x for c in chs for x in c[2]}) or ["F"]
        for j, ch in enumerate(chunk_text(t)):
            n += 1
            docs.append(dict(
                id=f"{prefix}#{n}", source_id=SOURCE_ID, url=url, title=f"ÖGK Leistungen und Services 2026: {titles}",
                section=f"Gedruckte Seiten {printed[pi]} (PDF-Seite {pi}), Teil {j+1}; Kapitel laut Inhaltsverzeichnis: {titles}",
                text=ch, lang="de", traeger=["ÖGK"], bundesland=["AT"], bereich=bereich, doc_type="broschuere",
                valid_from="2026-01-01", fetched_at=NOW, sha256=sha, license_note=LIC, page=pi))
    # Sonderdokument: Rezeptgebühren-Tabelle als eigener, zitierbarer Abschnitt
    t22 = norm(pages[22])
    m = re.search(r"Befreiung von der Rezeptgebühr Ohne.*?ist dieses zu berücksichtigen\.(?:.*?ist dieses zu berücksichtigen\.)", t22, re.S)
    if m:
        n += 1
        docs.append(dict(
            id=f"{prefix}#{n}", source_id=SOURCE_ID, url=url, title="ÖGK Leistungen und Services 2026: Befreiung von der Rezeptgebühr (Tabelle, Grenzbeträge 2026)",
            section="Gesund werden › Heilmittel › Tabelle Ohne Antrag / Mit Antrag (gedruckte Seiten 42–43; PDF-Seite 22)",
            text=m.group(0), lang="de", traeger=["ÖGK"], bundesland=["AT"], bereich=["C", "E"], doc_type="broschuere",
            valid_from="2026-01-01", fetched_at=NOW, sha256=sha, license_note=LIC, page=22))

    # ---- Leistungs-Kandidaten: Quelltext je Leistung = definierte PDF-Seiten, optional zwischen Start-/End-Regex
    PS = {  # chapter -> (pdf pages, start_rx, end_rx (inklusive))
        "Meine Mitversicherung": (range(4, 12), r"Meine Mitversicherung", r"Freiwillige Versicherung"),
        "Freiwillige Versicherung": ([11, 12], r"Freiwillige Versicherung", r"vorsorgeuntersuchung Sie wollen"),
        "Vorsorgeuntersuchung": ([12, 13], r"vorsorgeuntersuchung Sie wollen", None),
        "Jugendlichenuntersuchung": ([13], r"Jugendlichenuntersuchung Die", None),
        "Brustkrebs-Früherkennungsprogramm „früh erkennen”": ([13], r"Brustkrebs-Früherkennungs", r"Fehldiagnosen zu vermeiden|frueh-erkennen\.at\."),
        "Heilmittel": ([22, 23], None, None),
        "Heilbehelfe": ([23, 24], r"heilbehelfe Sie brauchen", None),
        "Hilfsmittel": ([24], r"hilfsmittel Ob Prothesen", None),
        "Krankenhauspflege": ([24], r"Krankenhauspflege Sie müssen", r"Eine Kostenbeteiligung bei Heilbehelfen"),
        "Medizinische Hauskrankenpflege": ([25], r"Medizinische hauskrankenpflege", r"Medizinische Maßnahmen"),
        "Medizinische Maßnahmen der Rehabilitation": ([24, 25], None, None),
        "Kur und Erholung": ([32], r"Kur und erholung", None),
        "Transportkosten": ([32, 33], None, None),
        "Konservierende-chirurgische Zahnbehandlung": ([39], r"Konservierend", None),
        "Kieferorthopädie und Zahnspangen": ([39, 40], None, None),
        "Zahnersatz": ([41], r"Zahnersatz Im Allgemeinen", None),
        "Gratis-Mundhygiene für Kinder und Jugendliche": ([41], r"Gratis-Mundhygiene für Kinder und Jugendliche", r"54,96 Euro\."),
        "Telefonische Gesundheitsberatung 1450": ([42, 43], r"telefonische Gesundheitsberatung 1450", r"Ombudsstelle"),
    }

    def chap_pages(title):
        if title in PS:
            return list(PS[title][0])
        for k, (t_, pr_, _g, _b) in enumerate(toc):
            if t_ == title:
                nxt = toc[k + 1][1] if k + 1 < len(toc) else 999
                return sorted({pr_ // 2 + 1, max(pr_ // 2 + 1, (nxt - 1) // 2 + 1)} | set(range(pr_ // 2 + 1, (nxt - 1) // 2 + 2)))
        return []

    class _CT(dict):
        def __missing__(self, title):
            pgs = chap_pages(title)
            txt = " ".join(norm(pages[i]) for i in pgs if i in pages)
            spec = PS.get(title)
            if spec:
                _, srx, erx = spec
                if srx:
                    ms = re.search(srx, txt)
                    if ms:
                        txt = txt[ms.start():]
                if erx:
                    me = re.search(erx, txt)
                    if me:
                        txt = txt[:me.end()]
            v = (txt, pgs[0] if pgs else 0, pgs[-1] if pgs else 0)
            self[title] = v
            return v
    chap_text = _CT()
    chap_text_titles = set(t_ for t_, *_ in toc)

    def mk_leistung(chapter, lid, name, kurz, bereich, vor_pat, antrag_pat, kosten_pat, fristen_pat, abh=None, fixed_vor=None):
        t, sp, ep = chap_text[chapter]
        sents = sentences(t)
        vor = []
        for txt, rx in (fixed_vor or []):
            mm = re.search(rx, t, re.S)
            if mm:
                vor.append(dict(text=txt, quelle_url=url, zitat=mm.group(0)[:900], seite=f"PDF {sp}"))
        for s_ in pick(sents, vor_pat, 5):
            vor.append(dict(text=s_, quelle_url=url, zitat=s_, seite=f"PDF {sp}" + (f"–{ep}" if ep != sp else "")))
        ant = pick(sents, antrag_pat, 3)
        kost = pick(sents, kosten_pat, 3)
        frist = pick(sents, fristen_pat, 2)
        trg = ["ÖGK"]
        return dict(
            leistung_id=lid, name=name, kurz_einfach=kurz, bereich=bereich, traeger=trg, innerhalb_sv=True,
            zielgruppe=None, voraussetzungen=vor, zustaendig="ÖGK (Österreichische Gesundheitskasse); Details laut Zitaten.",
            antrag=dict(formular_id=None, wo=" ".join(ant) if ant else None, online_url=None, zitate_ablauf=ant),
            unterlagen=[], fristen=frist, kosten=" ".join(kost) if kost else None, abhaengigkeiten=abh or [],
            trigger_im_dokument=[chapter.split(" (")[0]], bundesland=["AT"],
            quellen=[dict(url=url, stand="2026-01-01", seite=f"PDF {sp}" + (f"–{ep}" if ep != sp else ""))],
            confidence="mittel")

    VOR = r"\bwenn\b|\bnur\b|Anspruch|Voraussetzung|\bmüssen\b|\bmuss\b|\bab \d+|zwischen \d+|\bbis zum\b|ärztlich|Bewilligung|genehmig|pflichtversichert"
    ANT = r"Antrag|beantrag|anmelden|Kundenservice|e-card|Überweisung|Formular|Anordnung|verschreibt|Verordnung"
    KOST = r"Euro|Prozent|kostenlos|Zuzahlung|Selbstbehalt|Kostenanteil|Kostenbeitrag|gratis|Rezeptgebühr"
    FR = r"\d+ Tage|\d+ Wochen|\d+ Monat|Frist|spätestens|innerhalb|binnen|alle zwei Jahre|einmal pro Jahr|Kalenderjahr"
    for chapter, (lid, name, kurz) in BRO_LEISTUNG.items():
        if chapter not in chap_text_titles:
            continue
        bereich = next(b for (tt, _, _, b, _) in BRO_CHAPTERS if tt == chapter)
        fixed = RGB_ANKER if lid == "rezeptgebuehrenbefreiung" else None
        abh = {"krankentransport": ["rezeptgebuehrenbefreiung"], "heilbehelfe": ["rezeptgebuehrenbefreiung"]}.get(lid, [])
        VORX = {
            "krankentransport": r"Transport|Gehunfähig|Beförderung|Kostenübernahme|Selbstbehalt|Kilometer|Anweisung",
            "heilbehelfe": r"Heilbehelf|Brille|Kostenanteil|Kostenbeteiligung|Mindest|Höchstbetrag|Verordnung",
            "reha_medizinisch": r"Rehabilit|Reha|Zuzahlung|Antrag|Begleitperson|Unterbringung",
            "kieferorthopaedie_gratis_zahnspange": r"IOTN|Gratis|Zahnspange|Prozent|Euro|Bewilligung|Behandlungsjahr|Alter|Jahre",
            "mundhygiene_kinder_jugendliche": r"Mundhygiene|Lebensjahr|Kostenerstattung",
            "kur_erholung": r"Kur|Erholung|Antrag|Zuzahlung|ärztlich|Einkommen",
            "gesundheitstelefon_1450": r"1450|Gesundheitsberatung|Notfall|144|Rufen Sie",
            "vorsorgeuntersuchung": r"Vorsorgeuntersuchung|ab 18|ab dem 45|Koloskopie|Fragebogen|Hausärztin|kostenlos",
        }
        KOSTX = {"krankentransport": r"Selbstbehalt|Kostenanteil|Kilometergeld|Rezeptgebühr", "reha_medizinisch": r"Zuzahlung|Euro", "kur_erholung": r"Zuzahlung|Euro"}
        L = mk_leistung(chapter, lid, name, kurz, bereich, VORX.get(lid, VOR), ANT, KOSTX.get(lid, KOST), FR, abh, fixed)
        if lid == "rezeptgebuehrenbefreiung":
            L["antrag"]["wo"] = "Antrag bei der ÖGK (Befreiung 'Mit Antrag'); automatisch befreit sind die Gruppen 'Ohne Antrag' (siehe Voraussetzungen)."
            L["zielgruppe"] = "Versicherte mit geringem Einkommen bzw. bestimmten Leistungsbezügen; Grenzbeträge 2026 laut Zitat"
            L["kosten"] = "Rezeptgebühr derzeit 7,55 € pro Packung (laut Broschüre 2026)."
            L["confidence"] = "hoch"
            L["parameter_2026"] = dict(
                rezeptgebuehr_eur=7.55, nettoeinkommen_grenze_alleinstehend_eur=1308.39, nettoeinkommen_grenze_paar_eur=2064.12,
                zuschlag_pro_kind_eur=201.88, hohe_ausgaben_grenze_alleinstehend_eur=1504.65, hohe_ausgaben_grenze_paar_eur=2373.74,
                haushaltsperson_anrechnung_prozent=12.5, quelle="ÖGK Leistungen und Services 2026, S. 42–43")
        if lid == "krankentransport":
            L["parameter_2026"] = dict(selbstbehalt_taxi_fahrtendienst_eur=7.55, selbstbehalt_mit_sanitaetsbegleitung_eur=15.10,
                                       quelle="ÖGK Leistungen und Services 2026, S. 62–63")
            L["zielgruppe"] = "Versicherte/Angehörige mit ärztlicher Transportanweisung über Gehunfähigkeit"
        if lid == "kur_erholung":
            L["antrag"]["formular_id"] = "oegk_antrag_kur_reha"
            L["parameter_2026"] = dict(zuzahlung_taeglich_eur=[11.06, 18.96, 26.87], einkommensgrenzen_brutto_eur=[1889.77, 2471.16], quelle="S. 62")
        if lid == "reha_medizinisch":
            L["antrag"]["formular_id"] = "oegk_antrag_kur_reha"
            L["parameter_2026"] = dict(zuzahlung_taeglich_eur=[11.06, 18.96, 26.87], einkommensgrenzen_brutto_eur=[1889.77, 2471.16],
                                       max_tage_zuzahlung=28, quelle="S. 48")
        if lid == "heilbehelfe":
            L["parameter_2026"] = dict(hoechstbetrag_eur=1848.00, selbstbehalt_prozent=10, mindestselbstbehalt_eur=46.20,
                                       mindestanteil_brillen_eur=138.60, quelle="S. 44–45")
        if lid == "gesundheitstelefon_1450":
            L["antrag"]["wo"] = "Telefonisch unter 1450 (laut Broschüre S. 82)"
        leist.append(L)
    for ex in BRO_EXTRA:
        L = mk_leistung(ex["chapter"], ex["leistung_id"], ex["name"], ex["kurz"], ex["bereich"], ex["vor"], ANT, ex["kosten"], FR, ex["abh"])
        leist.append(L)
    # Mitversicherung ist ein langes Kapitel -> Voraussetzungen gezielt
    for L in leist:
        if L["leistung_id"] == "mitversicherung":
            t, sp, ep = chap_text["Meine Mitversicherung"]
            sents = sentences(t)
            L["voraussetzungen"] = []
            for s_ in pick(sents, r"mitversichert|Angehörige|Kinder|Ehegatt|Lebensgefährt|Antrag|Pflege|Haushalt|Einkünfte", 8):
                L["voraussetzungen"].append(dict(text=s_, quelle_url=url, zitat=s_, seite=f"PDF {sp}–{ep}"))
            L["antrag"]["formular_id"] = None
    # Stelle 1450
    stellen = [dict(stelle_id="hotline_1450", name="Telefonische Gesundheitsberatung 1450", typ="hotline", adresse=None, plz=None,
                    bundesland="AT", telefon="1450", email=None, url="https://www.1450.at", oeffnungszeiten="laut ÖGK-Broschüre: telefonische Gesundheitsberatung (Details S. 82)",
                    zustaendig_fuer=["gesundheitstelefon_1450"], geo=None, quelle_url=url),
               dict(stelle_id="hotline_144_notruf", name="Rettung / Notruf 144", typ="hotline", adresse=None, plz=None, bundesland="AT",
                    telefon="144", email=None, url=None, oeffnungszeiten="rund um die Uhr", zustaendig_fuer=[], geo=None, quelle_url=url)]
    # Quellen-Check für 144/1450 im Text
    return dict(documents=docs, leistungen=leist, stellen=stellen, formulare=[], codes=[])


# ============================================================================ 2. Honorarordnungen
AMT = r"(?:\d{1,3}(?:\.\d{3})*,\d{2}|n\.\s?a\.)"


def build_zahn_ho(p: Path):
    raw = pdf_pages_raw(p)
    prefix, sha, url = doc_prefix(p), sha256_file(p), file_url(p)
    docs, n = [], 0
    section = "Allgemeines"
    rows = []
    for pgi, t in enumerate(raw, 1):
        lines = [l.rstrip() for l in t.split("\n")]
        printed = None
        for l in lines[:3]:
            if re.fullmatch(r"\d{1,2}", l.strip()):
                printed = l.strip()
        # Erläuterungen/Fliesstext: je Seite als Dokument-Abschnitte
        scope = next((l.strip() for l in lines[:8] if re.fullmatch(r"(ÖGK|BVAEB|SVS)( ?/ ?(ÖGK|BVAEB|SVS|KFA WIEN))*", l.strip())), None)
        for l in lines:
            if re.match(r"(Honorartarif|Erläuterungen zum Honorartarif|Kostenanteile|Behandlungskostenbeiträge)", l.strip()) and len(l) < 150:
                section = l.strip()
        # Tarifzeilen: Pos + Text ... Abkürzung + Beträge
        cur = None
        for l in lines:
            m_start = re.match(r"^(\d{1,3}[a-z]?)\s+([A-ZÄÖÜ][^\n]*)$", l.strip())
            if m_start and not re.match(r"^\d+\.\s", l.strip()):
                if cur:
                    rows.append(cur)
                cur = dict(pos=m_start.group(1), parts=[m_start.group(2)], page=pgi, printed=printed, section=section, scope=scope)
            elif cur and l.strip() and not l.strip().startswith(("Pos", "ZAHNAERZTE", "ÖGK", "Nr.", "Leistungsart")):
                cur["parts"].append(l.strip())
                if len(cur["parts"]) > 8:
                    rows.append(cur); cur = None
                    continue
            else:
                pass
            if cur:
                joined = " ".join(cur["parts"])
                m_end = re.search(rf"\s([A-Za-zÄÖÜäöü]{{1,6}})\s+((?:{AMT}\s*)+)$", joined)
                if m_end:
                    cur["abk"] = m_end.group(1)
                    cur["betraege"] = re.findall(AMT, m_end.group(2))
                    cur["text"] = joined[:m_end.start()].strip()
                    rows.append(cur); cur = None
        if cur and "betraege" not in cur:
            cur = None
    seen = set()
    tarife = []
    for r in rows:
        if "betraege" not in r:
            continue
        key = (r["scope"], r["pos"], r["abk"], tuple(r["betraege"]))
        if key in seen:
            continue
        seen.add(key)
        tarife.append(r)
    for r in tarife:
        n += 1
        txt = (f"Pos. {r['pos']} ({r['abk']}): {r['text']} — Tarif in € (Spalten laut Tabellenkopf der Seite, Geltung: {r['scope'] or 'siehe Seite'}): "
               + " | ".join(r["betraege"]))
        docs.append(dict(
            id=f"{prefix}#t{n}", source_id=SOURCE_ID, url=url, title=f"Zahnärzte-Honorarordnung 2026, Pos. {r['pos']}",
            section=f"Tariftabelle, Geltung {r['scope'] or '?'} (PDF-Seite {r['page']}; gedruckte Seite {r['printed'] or '?'})", text=txt[:1990], lang="de",
            traeger=["ÖGK", "SVS", "BVAEB", "KFA Wien"], bundesland=["AT"], bereich=["C"], doc_type="tarif",
            valid_from="2026-01-01", fetched_at=NOW, sha256=sha, license_note=LIC, page=r["page"],
            tarif=dict(pos=r["pos"], abk=r["abk"], betraege=r["betraege"])))
    # Fliesstext-Abschnitte: Erläuterungen (Mundhygiene, KFO) – seitenweise, als faq/recht-ähnliches 'tarif'-Kontextdokument
    ctx_pages = list(range(7, 9)) + list(range(22, 35))
    ctx_pages += [i for i in range(1, len(raw) + 1) if re.search(r"Mundhygiene", raw[i - 1]) and i not in ctx_pages]
    for pgi in sorted(set(ctx_pages)):
        if pgi > len(raw):
            continue
        t = norm(raw[pgi - 1])
        for j, ch in enumerate(chunk_text(t)):
            n += 1
            docs.append(dict(
                id=f"{prefix}#e{n}", source_id=SOURCE_ID, url=url, title=f"Zahnärzte-Honorarordnung 2026 – Erläuterungen (PDF-Seite {pgi})",
                section=f"Erläuterungen/Bestimmungen, PDF-Seite {pgi}, Teil {j+1}", text=ch, lang="de",
                traeger=["ÖGK", "SVS", "BVAEB", "KFA Wien"], bundesland=["AT"], bereich=["C"], doc_type="tarif",
                valid_from="2026-01-01", fetched_at=NOW, sha256=sha, license_note=LIC, page=pgi))
    # Leistungs-Kandidaten
    full = {i: norm(raw[i - 1]) for i in range(1, len(raw) + 1)}
    alltext = " ".join(full[i] for i in sorted(full))

    def q(pat, n_=3, maxlen=500, text=None):
        return pick(sentences(text or alltext), pat, n_, maxlen)

    L = []
    q_mh = q(r"^Die Mundhygiene ist für Kinder und Jugendliche|^Zudem wird die Position 65|^Sie ist künftig zweimal", 4)
    mt = re.search(r"65 Mundhygiene \(für Kinder und Jugendliche vom 10\. bis 18\. Lebensjahr\)", alltext)
    if mt:
        q_mh.insert(0, mt.group(0))
    L.append(dict(
        leistung_id="mundhygiene_kinder_jugendliche", name="Gratis-Mundhygiene für Kinder und Jugendliche",
        kurz_einfach="Kinder und Jugendliche zwischen 6 und 18 können zweimal im Jahr (im Abstand von mind. 6 Monaten) eine professionelle Mundhygiene bei Vertragszahnärzt:innen bekommen. Honorar-Position 65.",
        bereich=["A", "B"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True, zielgruppe="Kinder und Jugendliche zwischen dem vollendeten 6. und 18. Lebensjahr",
        voraussetzungen=[dict(text=s_, quelle_url=url, zitat=s_) for s_ in q_mh],
        zustaendig="Vertragszahnärzt:innen von ÖGK/SVS/BVAEB (Tarifposition 65 MH, 68,70 €)",
        antrag=dict(formular_id=None, wo="Direktverrechnung mit e-card beim Vertragszahnarzt/-zahnärztin (laut Honorarordnung; kein Antrag erwähnt)", online_url=None),
        unterlagen=[], fristen=["2 x/Jahr im Abstand von mindestens 6 Monaten"], kosten="Tarif Pos. 65: 68,70 € (Honorar, Abrechnung mit Kasse) – Patientenanteil siehe Kostenanteile-Tabelle der Honorarordnung",
        abhaengigkeiten=[], trigger_im_dokument=["Mundhygiene", "Zahnreinigung", "Zahnprophylaxe"], bundesland=["AT"],
        quellen=[dict(url=url, stand="2026-01-01")], confidence="mittel",
        hinweis="Tarif-Tabelle ÖGK nennt 10–18 Jahre; Erläuterung Z. 27 und BVAEB-Pilot nennen 6–18 Jahre 2x/Jahr – Widerspruch im Dokument, bei Beratung mit Zahnarzt/ÖGK abklären."))
    q_kfo = q(r"IOTN\) 4 oder 5|IOTN 4 oder 5|vor Vollendung des 18\. Lebensjahres|keine Zuzahlung|Zuzahlung durch den Patienten", 6, 600)
    L.append(dict(
        leistung_id="kieferorthopaedie_gratis_zahnspange", name="Kieferorthopädische Behandlung / Gratis-Zahnspange (KFO)",
        kurz_einfach="Bei starker Zahn- oder Kieferfehlstellung (IOTN-Grad 4 oder 5) und Behandlungsbeginn vor dem 18. Geburtstag zahlt die Kasse die Zahnspange; keine Zuzahlung. Die Einstufung nimmt die Vertragskieferorthopädin bzw. der Vertragskieferorthopäde vor.",
        bereich=["C"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True, zielgruppe="Kinder und Jugendliche bis zum vollendeten 18. Lebensjahr",
        voraussetzungen=[dict(text=s_, quelle_url=url, zitat=s_) for s_ in q_kfo],
        zustaendig="Vertragskieferorthopäd:innen (Honorarordnung für Vertragskieferorthopäden, gültig für ÖGK, BVAEB, SVS)",
        antrag=dict(formular_id=None, wo="Feststellung IOTN (ab 12. Lebensjahr, max. 2x) und Antrag über die Vertragskieferorthopädin/den Vertragskieferorthopäden", online_url=None),
        unterlagen=[], fristen=q(r"Jahres|vor Vollendung des 10\. Lebensjahres|ab Vollendung des 12\. Lebensjahres|Behandlungsdauer", 3),
        kosten="Keine Zuzahlung durch Patient:in bei Vertrags-KFO-Leistungen (laut HO-Erläuterung); Tarife: IOTN-Feststellung 67,40 €, Hauptbehandlung gesamt 4.722,00 €, interzeptive Behandlung 1.174,00 €",
        abhaengigkeiten=[], trigger_im_dokument=["Zahnspange", "Kieferorthopädie", "IOTN", "Fehlstellung"], bundesland=["AT"],
        quellen=[dict(url=url, stand="2026-01-01")], confidence="mittel"))
    if "kieferorthopaedie_gratis_zahnspange" and False:
        pass
    return dict(documents=docs, leistungen=L, stellen=[], formulare=[], codes=[])


def build_aerzte_ho(p: Path):
    raw = pdf_pages_raw(p)
    prefix, sha, url = doc_prefix(p), sha256_file(p), file_url(p)
    docs, n = [], 0
    section = "Allgemeine Grundsätze"
    seen = set()
    for pgi, t in enumerate(raw, 1):
        lines = t.split("\n")
        m = re.search(r"ABSCHNITT\s+([IVX]+)", t)
        sec_abschnitt = f"Abschnitt {m.group(1)}" if m else None
        for l in lines:
            if l.strip().isupper() and 12 < len(l.strip()) < 90 and not re.match(r"^[\d\s,.]+$", l.strip()):
                section = l.strip()
        blocks, cur = [], []
        for l in lines:
            if l.strip() == "":
                if cur:
                    blocks.append(cur); cur = []
            else:
                cur.append(l.strip())
        if cur:
            blocks.append(cur)
        # Tarifzeilen beginnen mit Positionsnummer; Fortsetzungsblöcke ohne Nummer werden an den Vorgänger gehängt
        last = None
        for b in blocks:
            first = b[0]
            mm = re.match(r"^(\d{3,4}[a-zA-Z]?)\s+(\S.*)$", first)
            if mm and re.search(r"\d,\d{2}\s*$", " ".join(b)):
                joined = " ".join(b)
                am = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})", joined)
                key = (mm.group(1), joined[:80])
                if key in seen:
                    continue
                seen.add(key)
                n += 1
                text = f"Pos. {mm.group(1)}: {joined[len(mm.group(1)):].strip()} — Beträge in €: {', '.join(am)}"
                docs.append(dict(
                    id=f"{prefix}#t{n}", source_id=SOURCE_ID, url=url, title=f"Honorarordnung Vertragsärzte (Steiermark, Stand 01.01.2025), Pos. {mm.group(1)}",
                    section=f"{sec_abschnitt or ''} {section} (PDF-Seite {pgi})".strip(), text=text[:1990], lang="de", traeger=["ÖGK"],
                    bundesland=["ST"], bereich=["C"], doc_type="tarif", valid_from="2025-01-01", fetched_at=NOW, sha256=sha,
                    license_note=LIC, page=pgi, tarif=dict(pos=mm.group(1), betraege=am)))
    # Erläuterungen zu Visiten/Hausbesuchen als Fließtext
    for pgi in range(25, 29):
        if pgi > len(raw):
            continue
        t = norm(raw[pgi - 1])
        for j, ch in enumerate(chunk_text(t)):
            n += 1
            docs.append(dict(id=f"{prefix}#e{n}", source_id=SOURCE_ID, url=url, title=f"Honorarordnung Vertragsärzte (Steiermark) – Ordinationen, Visiten, Wegegebühren (PDF-Seite {pgi})",
                             section=f"Erläuterungen Abschnitt I, PDF-Seite {pgi}, Teil {j+1}", text=ch, lang="de", traeger=["ÖGK"], bundesland=["ST"],
                             bereich=["C"], doc_type="tarif", valid_from="2025-01-01", fetched_at=NOW, sha256=sha, license_note=LIC, page=pgi))
    alltext = " ".join(norm(raw[i]) for i in range(24, min(29, len(raw))))
    q = pick(sentences(alltext), r"Hausbesuch|Visite|nächstgelegene Vertragsarzt|bettlägerig", 6, 500)
    L = [dict(
        leistung_id="hausbesuch_arzt", name="Hausbesuch / Visite durch Vertragsärztin bzw. Vertragsarzt",
        kurz_einfach="Wer nicht in die Ordination kommen kann, kann einen Hausbesuch der nächstgelegenen Vertragsärztin bzw. des nächstgelegenen Vertragsarztes bekommen; die Kasse rechnet direkt ab.",
        bereich=["C"], traeger=["ÖGK"], innerhalb_sv=True, zielgruppe="Versicherte, die nicht in die Ordination kommen können (z. B. bettlägerig)",
        voraussetzungen=[dict(text=s_, quelle_url=url, zitat=s_) for s_ in q],
        zustaendig="Nächstgelegener Vertragsarzt/Vertragsärztin (laut HO Pkt. 2.4); Quelle gilt für Steiermark, Stand 01.01.2025 – Honorare in anderen Bundesländern können abweichen",
        antrag=dict(formular_id=None, wo="Telefonische Anforderung beim Vertragsarzt/der Vertragsärztin; kein Formular", online_url=None),
        unterlagen=[], fristen=[], kosten="Tagbesuch an Werktagen laut Tarif Pos. 003: 41,13 € (Honorar an Arzt; Verrechnung mit Kasse)",
        abhaengigkeiten=[], trigger_im_dokument=["Hausbesuch", "Visite", "Besuch"], bundesland=["ST"],
        quellen=[dict(url=url, stand="2025-01-01")], confidence="niedrig",
        hinweis="Datei heißt 'ÖGK Honorarordnung', ist aber die Honorarordnung Steiermark (Ärztekammer Steiermark/Hauptverband), Stand 01.01.2025; Wien kann abweichen.")]
    return dict(documents=docs, leistungen=L, stellen=[], formulare=[], codes=[])


# ============================================================================ 3. Erstattungskodex
def build_eko(dirp: Path):
    def rd(name):
        pth = dirp / name
        return pth.read_text(encoding="latin-1") if pth.exists() else ""

    def parse_pipe(txt, unesc):
        d = {}
        last = None
        for ln in txt.split("\n"):
            m = re.match(r"^\|(\d+)\|;\|(.*?)\|?\s*$", ln)
            if m:
                s = m.group(2)
                if unesc:
                    s = html.unescape(s).replace("<br />", "\n").replace("<br/>", "\n")
                d[m.group(1)] = s.strip()
                last = m.group(1)
            elif ln.strip() and last:
                d[last] += "\n" + (html.unescape(ln) if unesc else ln).strip()
        return d

    regel = parse_pipe(rd("regeltext_v2.txt"), True) or parse_pipe(rd("regeltext.txt"), False)
    ind = parse_pipe(rd("indtext_v2.txt"), True) or parse_pipe(rd("indtext.txt"), False)
    pdf_leg = dirp / "Zeichenerklärungen und Abkürzungen.pdf"
    stand = "EKO 1/2024 (Zeichenerklärung); Datenstand Dateien Sep 2026 (mtime)"
    FLAG = {"IND": "Indikationsvermerk 'IND' am Rezept nötig; außerhalb der Voraussetzungen chef-/kontrollärztliche Bewilligung",
            "RE1": "Abgabe erst nach ärztlicher Bewilligung des chef- und kontrollärztlichen Dienstes",
            "RE2": "Bewilligung kann durch nachfolgende Kontrolle ersetzt werden, wenn die angegebene Verwendung vorliegt und dokumentiert ist",
            "F14": "Grüner Bereich nur für Kinder/Jugendliche bis zum vollendeten 14. Lebensjahr", "F2J": "Grüner Bereich nur bis 2. Lebensjahr",
            "F6J": "Grüner Bereich nur bis 6. Lebensjahr"}
    codes = []
    med = rd("medikament.txt")
    for ln in med.split("\n"):
        if not ln.strip():
            continue
        pn = ln[0:7].strip()
        name = ln[18:117].strip()
        box = ln[118:119].strip()
        flags_raw = ln[121:125].strip()
        pack = ln[125:132].strip()
        p1 = ln[132:142].strip()
        p2 = ln[142:153].strip()
        tail = ln[153:].strip()
        flags = []
        for f in ("IND", "RE1", "RE2", "F14", "F2J", "F6J"):
            if f in flags_raw.split():
                flags.append(f)
        fachgruppen = [x for x in flags_raw.split() if x in ("A", "Au", "D", "F", "K", "L", "N", "P", "R", "U")]
        bew = "vorab_erforderlich" if "RE1" in flags else ("nachtraegliche_kontrolle_moeglich" if "RE2" in flags else ("indikationsvermerk" if "IND" in flags else "nein_laut_kennzeichen"))
        rt = regel.get(pn)
        it = ind.get(pn)
        codes.append(dict(
            system="EKO", code=pn, label_de=name, label_einfach=None, parent=None, leistung_hints=["heilmittel_bewilligungspflicht"] if bew in ("vorab_erforderlich", "nachtraegliche_kontrolle_moeglich") else [],
            quelle_url=file_url(dirp / "medikament.txt"), stand=stand,
            pharmanummer=pn, laufnummer=ln[9:15].strip(), packung=pack, bereich={"G": "grün", "Y": "gelb"}.get(box, box),
            kennzeichen=flags, fachgruppen=fachgruppen, bewilligung=bew, preis_raw=[p1, p2], zusatz_raw=tail or None,
            regeltext=rt, indikationstext_wortlaut=it,
            hinweis="Nur administrativ: Erstattungs-/Bewilligungsstatus. Texte sind wörtliche Zitate, keine Therapieaussage. Preisfelder unbestätigt (Rohwerte)."))
    # ATC-Liste: Code + Bezeichnung (keine Verknüpfung zu Packungen in den Dateien)
    for ln in rd("atccode.txt").split("\n"):
        if not ln.strip():
            continue
        m = re.match(r"^([A-Z][0-9A-Z]{0,6}?)\s*(\S.*)$", ln.rstrip())
        code = ln[:7].strip()
        label = ln[7:].strip()
        if not code:
            continue
        codes.append(dict(system="ATC", code=code, label_de=label, label_einfach=None, parent=None, leistung_hints=[],
                          quelle_url=file_url(dirp / "atccode.txt"), stand=stand,
                          hinweis="ATC-Code/Bezeichnung aus EKO-Datei; keine Zuordnung zu Packungen in den Rohdaten."))
    # Dokument: Zeichenerklärung (Quelle für Kennzeichen-Bedeutung)
    docs = []
    if pdf_leg.exists():
        raw = pdf_pages_raw(pdf_leg)
        sha = sha256_file(pdf_leg)
        pre = doc_prefix(pdf_leg)
        t = norm("\n".join(raw))
        for j, ch in enumerate(chunk_text(t)):
            docs.append(dict(id=f"{pre}#{j+1}", source_id=SOURCE_ID, url=file_url(pdf_leg), title="Erstattungskodex EKO 1/2024 – Zeichenerklärungen und Abkürzungen",
                             section=f"Zeichenerklärung Teil {j+1}", text=ch, lang="de", traeger=["Dachverband", "ÖGK"], bundesland=["AT"], bereich=["C"],
                             doc_type="faq", valid_from="2024-01-01", fetched_at=NOW, sha256=sha, license_note=LIC))
    leg_quotes = []
    if pdf_leg.exists():
        ss = sentences(t)
        for lab, rx in (("RE1: Abgabe erst nach Bewilligung", r"RE1 Die Arzneispezialit"), ("RE2: Bewilligung kann durch nachträgliche Kontrolle ersetzt werden", r"RE2 Bei diesen Arzneispezialit")):
            for z in pick(ss, rx, 1, 600):
                leg_quotes.append((lab, z))
    L = [dict(
        leistung_id="heilmittel_bewilligungspflicht", name="Bewilligungspflichtige Medikamente (EKO: RE1/RE2/IND)",
        kurz_einfach="Im Erstattungskodex ist je Packung vermerkt, ob die Kasse sie ohne Weiteres zahlt oder ob die Ärztin/der Arzt vorab eine Bewilligung des chef- und kontrollärztlichen Dienstes einholen muss (RE1) bzw. nachträglich kontrolliert wird (RE2).",
        bereich=["C"], traeger=["ÖGK", "SVS", "BVAEB"], innerhalb_sv=True, zielgruppe="Versicherte, denen ein Medikament verordnet wird",
        voraussetzungen=[dict(text=k, quelle_url=file_url(pdf_leg), zitat=v) for k, v in leg_quotes],
        zustaendig="Verordnende Ärztin/Arzt holt die Bewilligung beim chef- und kontrollärztlichen Dienst/Medizinischen Dienst der Kasse ein",
        antrag=dict(formular_id=None, wo="Ärztin/Arzt beantragt; keine Eigenaktion der Versicherten nötig", online_url=None), unterlagen=[], fristen=[],
        kosten=None, abhaengigkeiten=["rezeptgebuehrenbefreiung"], trigger_im_dokument=["bewilligungspflichtig", "chefärztliche Bewilligung", "RE1", "RE2"],
        bundesland=["AT"], quellen=[dict(url=file_url(pdf_leg), stand="EKO 1/2024")], confidence="mittel")]
    return dict(documents=docs, leistungen=L, stellen=[], formulare=[], codes=codes)


# ============================================================================ 4. Formulare
FORM_META = {
    "Antrag Kur und Reha.pdf": dict(formular_id="oegk_antrag_kur_reha", name="Antrag auf Rehabilitations-, Kur- bzw. Erholungsaufenthalt", traeger="ÖGK / Sozialversicherungsträger",
                                    leistung_ids=["kur_erholung", "reha_medizinisch"], wer="versicherte", hinweis="Teile für behandelnde Ärztin/Arzt (medizinische Begründung) enthalten"),
    "Reha_n_Unfall_052026.pdf": dict(formular_id="svbox_antrag_reha_nach_unfall", name="Antrag auf Anschlussheilverfahren oder Rehabilitation nach Unfall", traeger="Kranken-/Pensionsversicherungsträger / AUVA",
                                      leistung_ids=["reha_medizinisch"], wer="krankenhaus", hinweis="Vom antragstellenden Krankenhaus auszufüllen"),
    "Antrag-auf-Zuschuss-zu-Fahrtkosten_Wien.pdf": dict(formular_id="oegk_fahrtkostenzuschuss_wien", name="Antrag auf Zuschuss zu Fahrtkosten (für Versicherte mit Rezeptgebührenbefreiung)", traeger="ÖGK",
                                                         leistung_ids=["krankentransport", "rezeptgebuehrenbefreiung"], wer="versicherte", hinweis="Abschnitt 'Von der Einrichtung/vom Behandler auszufüllen' (Bestätigung/Stempel); setzt Rezeptgebührenbefreiung voraus"),
    "PAL080_0125_Mpfl_052026.pdf": dict(formular_id="pva_pal080", name="Antrag auf Pflegegeld nach dem BPGG (PAL 080)", traeger="PVA",
                                         leistung_ids=["pflegegeld"], wer="versicherte", hinweis="Auch durch gesetzliche Vertretung/Bevollmächtigte"),
    "fsw-antrag-auf-foerderung-von-leistungen.1779095804.pdf": dict(formular_id="fsw_antrag_foerderung", name="Antrag auf Förderung von Leistungen (FSW)", traeger="FSW",
                                                                      leistung_ids=["mobile_pflege_fsw", "wohn_pflegehaus_fsw"], wer="versicherte", hinweis="Auch durch vertretungsbefugte Person"),
    "FSW-Antrag-Beilage-Einrichtungswunsch.1779345450.pdf": dict(formular_id="fsw_beilage_einrichtungswunsch", name="Einrichtungswunsch für Wohn- und Pflegehäuser (Beilage zum FSW-Antrag)", traeger="FSW",
                                                                   leistung_ids=["fsw_wohn_pflegehaus"], wer="versicherte", hinweis="Beilage zum FSW-Antrag auf Förderung"),
    "Bedarfsmeldung-Senior_innen-Wohngemeinschaft_Basispaket.1736522017.pdf": dict(formular_id="fsw_bedarfsmeldung_senior_wg", name="Bedarfsmeldung Senior:innen-Wohngemeinschaften – Basispaket", traeger="FSW",
                                                                                      leistung_ids=["fsw_senior_wg"], wer="partnerorganisation", hinweis="Ausfüllen durch Partnerorganisation/Wohngemeinschaft mit Kund:in; Unterschrift Kund:in"),
}

HINTS = [("vorname", r"vorname"), ("familienname", r"familienname|fam\.?name|nachname|zuname"), ("titel", r"titel|akad"), ("geburtsdatum", r"geburtsdatum|geb\.?\s?datum|Tag Monat Jahr"),
         ("svnr", r"versicherungsnummer|vsnr|svnr"), ("geschlecht", r"geschlecht"), ("strasse", r"stra(ß|ss)e|gasse|adresse|anschrift"), ("plz", r"postleitzahl|plz"),
         ("ort", r"\bort\b"), ("telefon", r"telefon|tel\.?"), ("email", r"e-?mail"), ("iban", r"iban|bankkonto"), ("pflegegeldstufe", r"pflegegeldstufe"),
         ("unterschrift", r"unterschrift"), ("datum", r"\bdatum\b"), ("staatsbuergerschaft", r"staatsb"), ("personenstand", r"personenstand|familienstand")]


def hint_for(*ss):
    s = " ".join(x for x in ss if x).lower()
    for h, rx in HINTS:
        if re.search(rx, s, re.I):
            return h
    return None


def build_form(p: Path):
    meta = FORM_META.get(unicodedata.normalize("NFC", p.name))
    r = PdfReader(str(p))
    # Textfragmente je Seite mit Position
    frags = {}
    for pi, page in enumerate(r.pages):
        out = []

        def v(text, cm, tm, fd, fs, out=out):
            if text and text.strip():
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                out.append((x, y, text.strip(), fs or 8))
        try:
            page.extract_text(visitor_text=v)
        except Exception:
            pass
        frags[pi] = out
    fields = []
    for pi, page in enumerate(r.pages):
        for a in page.get("/Annots") or []:
            try:
                a = a.get_object()
            except Exception:
                continue
            if a.get("/Subtype") != "/Widget":
                continue
            # Feldname aus Parent-Kette
            names, node, ft, tu, ff = [], a, None, None, 0
            while node is not None:
                if "/T" in node:
                    names.insert(0, str(node["/T"]))
                ft = ft or node.get("/FT")
                tu = tu or node.get("/TU")
                ff = ff or int(node.get("/Ff", 0) or 0)
                node = node.get("/Parent")
                node = node.get_object() if node is not None else None
            name = ".".join(names) if names else None
            if not name:
                continue
            rect = [float(x) for x in a.get("/Rect", [0, 0, 0, 0])]
            x0, y0, x1, y1 = min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3])
            typ = "text"
            states = []
            if ft == "/Btn":
                typ = "radio" if ff & (1 << 15) else ("button" if ff & (1 << 16) else "checkbox")
                ap = a.get("/AP")
                if ap and "/N" in ap:
                    states = [str(k) for k in ap["/N"].get_object().keys() if str(k) != "/Off"]
            elif ft == "/Ch":
                typ = "choice"
            elif ft == "/Sig":
                typ = "signature"
            label, lsrc = (str(tu).strip().replace("\n", " "), "AcroForm /TU") if tu and str(tu).strip() else (None, None)
            near = None
            fr = frags.get(pi, [])
            mid = (y0 + y1) / 2
            left = [f for f in fr if f[0] < x0 + 2 and abs(f[1] - mid) < max(7, (y1 - y0) / 2 + 3) and x0 - f[0] < 260]
            if left:
                left.sort(key=lambda f: f[0])
                near = " ".join(f[2] for f in left[-3:])
            else:
                above = [f for f in fr if f[1] >= y1 - 2 and f[1] - y1 < 26 and f[0] < x1 and f[0] > x0 - 150]
                if above:
                    above.sort(key=lambda f: (f[1] - y1, abs(f[0] - x0)))
                    near = above[0][2]
            if label and not re.sub(r"[.\s_…\uf000-\uf8ff]", "", label):
                label = None
            if near and not re.sub(r"[.\s_…\uf000-\uf8ff]", "", near):
                near = None
            if not label and near:
                label, lsrc = near[-90:], "Layout (nächster Text)"
            fld = dict(name=name, label=label, typ=typ, quelle_hint=hint_for(name, label), seite=pi + 1, label_quelle=lsrc)
            if states:
                fld["optionen"] = states
            if near and label != near[-90:]:
                fld["label_nahe"] = near[-90:]
            fields.append(fld)
    # Duplikate (Radio-Kids) zusammenführen
    uniq, seen = [], {}
    for f in fields:
        k = (f["name"], f["typ"])
        if k in seen:
            seen[k].setdefault("optionen", [])
            for o in f.get("optionen", []):
                if o not in seen[k]["optionen"]:
                    seen[k]["optionen"].append(o)
            continue
        seen[k] = f
        uniq.append(f)
    meta = meta or dict(formular_id="svbox_" + re.sub(r"\W+", "_", p.stem.lower())[:40], name=p.stem, traeger=None, leistung_ids=[], wer="versicherte", hinweis=None)
    form = dict(formular_id=meta["formular_id"], name=meta["name"], traeger=meta["traeger"], url_pdf=None, local_pdf=rel(p),
                fillable=bool(uniq), felder=uniq, leistung_ids=meta["leistung_ids"], wer_fuellt_aus=meta["wer"], quelle_url=file_url(p),
                wer_fuellt_aus_hinweis=meta["hinweis"], n_felder=len(uniq), n_seiten=len(r.pages), sha256=sha256_file(p))
    # Dokument je Formular (Klartext) für die Suche
    docs = []
    pre, sha, url = doc_prefix(p), sha256_file(p), file_url(p)
    t = norm("\n".join((pg.extract_text() or "") for pg in r.pages))
    for j, ch in enumerate(chunk_text(t)):
        docs.append(dict(id=f"{pre}#{j+1}", source_id=SOURCE_ID, url=url, title=f"Formular: {meta['name']}", section=f"Formulartext Teil {j+1}", text=ch,
                         lang="de", traeger=[meta["traeger"] or ""], bundesland=["W"] if "FSW" in (meta["traeger"] or "") or "Wien" in p.name else ["AT"],
                         bereich=["F"], doc_type="formular", valid_from=None, fetched_at=NOW, sha256=sha, license_note=LIC))
    return dict(documents=docs, leistungen=[], stellen=[], formulare=[form], codes=[])


# ============================================================================ main
def main():
    force = "--force" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    PARTS.mkdir(parents=True, exist_ok=True)
    mpath = OUT / "manifest.json"
    old = json.loads(mpath.read_text()) if mpath.exists() else {"urls": []}
    old_sha = {u["url"]: u["sha256"] for u in old.get("urls", [])}
    inputs = []  # (key, builder, [files])
    lk = SRC / "Leistungskataloge"
    for f in sorted(gl(lk, "Serviceratgeber*.pdf")):
        inputs.append((f, build_broschuere, [f]))
    for f in sorted(gl(lk, "Zahn*.pdf")):
        inputs.append((f, build_zahn_ho, [f]))
    for f in sorted(gl(lk, "ÖGK Honorarordnung*.pdf")):
        inputs.append((f, build_aerzte_ho, [f]))
    ek = SRC / "Medikamenten Erstattungskodex"
    if ek.exists():
        eko_files = sorted([*ek.glob("*.txt"), *ek.glob("*.pdf")])
        inputs.append((ek, build_eko, eko_files))
    for f in sorted((SRC / "Anträge und Formulare").glob("*.pdf")):
        inputs.append((f, build_form, [f]))
    urls, active = [], set()
    for key, fn, files in inputs:
        shas = {file_url(x): sha256_file(x) for x in files}
        part = PARTS / (sha1(rel(key))[:12] + ".json")
        active.add(part.name)
        changed = force or not part.exists() or any(old_sha.get(u) != s for u, s in shas.items())
        if changed:
            print("verarbeite", rel(key))
            res = fn(key)
            part.write_text(json.dumps(res, ensure_ascii=False))
            status = "updated"
        else:
            print("unverändert", rel(key))
            status = "unchanged"
        for x in files:
            urls.append(dict(url=file_url(x), sha256=shas[file_url(x)], etag=None, last_modified=datetime.fromtimestamp(x.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), status=status))
    for pf in PARTS.glob("*.json"):
        if pf.name not in active:
            pf.unlink()  # Quelle entfernt
    merged = {k: [] for k in ("documents", "leistungen", "stellen", "formulare", "codes")}
    for pf in sorted(PARTS.glob("*.json")):
        res = json.loads(pf.read_text())
        for k in merged:
            merged[k].extend(res.get(k, []))
    # Leistungen mit gleicher ID zusammenführen (Voraussetzungen/Quellen vereinen)
    by = {}
    for L in merged["leistungen"]:
        if L["leistung_id"] in by:
            b = by[L["leistung_id"]]
            b["voraussetzungen"] += [v for v in L["voraussetzungen"] if v not in b["voraussetzungen"]]
            b["quellen"] += [q for q in L["quellen"] if q not in b["quellen"]]
            b["traeger"] = sorted(set(b["traeger"]) | set(L["traeger"]))
        else:
            by[L["leistung_id"]] = L
    merged["leistungen"] = list(by.values())
    # Formular-ID <-> Leistungs-Antrag verknüpfen
    forms = {f["formular_id"] for f in merged["formulare"]}
    for L in merged["leistungen"]:
        if L["antrag"].get("formular_id") and L["antrag"]["formular_id"] not in forms:
            L["antrag"]["formular_id"] = None
    for k, name in (("documents", "documents"), ("leistungen", "leistungen"), ("stellen", "stellen"), ("formulare", "formulare"), ("codes", "codes")):
        write_jsonl(OUT / f"{name}.jsonl", merged[k])
    man = dict(source_id=SOURCE_ID, fetched_at=NOW, n_docs=len(merged["documents"]), n_leistungen=len(merged["leistungen"]),
               n_formulare=len(merged["formulare"]), n_codes=len(merged["codes"]), n_stellen=len(merged["stellen"]), urls=urls)
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=1))
    print({k: len(v) for k, v in merged.items()})


if __name__ == "__main__":
    main()
