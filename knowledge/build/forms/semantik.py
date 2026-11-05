"""Regelbasierte Zuordnung Feld → Ontologie-Schlüssel und Feld → wer (ARCHITEKTUR §8.1.2).

Konservativ: Im Zweifel `semantik=None` (Michi fragt nach) und medizinische/ärztliche Inhalte
werden gesperrt (`wer=arzt` bzw. `semantik=medizinisch.angaben`), nie geraten.
"""
from __future__ import annotations

import re
import unicodedata


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.replace("ß", "ss").lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"[_\-/:,.;()\[\]*]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --- Sperren (zuerst geprüft) ----------------------------------------------------------
UNTERSCHRIFT = re.compile(r"unterschrift|unterfertig|fertigung|signatur|firmenmassige zeichnung|stampiglie|handzeichen")
STEMPEL = re.compile(r"stempel|eingangsvermerk|eingelangt|vom (versicherungs)?trager auszuf|von der (anstalt|behorde|kasse|svs|ogk|bvaeb) auszuf|amtsvermerk|aktenzahl|bearbeitungsvermerk|interne vermerk|nur fur interne")
ARZT = re.compile(r"\barzt|arztin|arztl|aerzt|diagnose|\bicd\b|befund|therapie|verordn|indikation|anamnese|medizinische begrundung|stellungnahme|behandelnde|ordination|vertragsarzt|facharzt|krankenanstalt.*stempel|klinische|operation|op datum|\bdgn\b")
MEDIZIN = re.compile(r"leiden|beschwerde|krankheit|erkrank|medikament|arznei|behinderung|einschrankung|beeintrachtig|demenz|inkontinenz|rollstuhl|sehbehind|horbehind|gehbehind|gehfahig|gehen mit|gehen ohne|selbstandig gehen|pflegebedarf|hilfsbedarf|korperpflege|baden|duschen|anziehen|orientierung|psychisch|geistig|blind|gehorlos|sauerstoff|dialyse|chemo|strahlen|bestrahlung|schwanger|entbindung|geburtstermin|allergi|unfallhergang|verletzung|korperteil|schmerz|symptom|gewicht|grosse in cm|blutdruck|harn|stuhl|transfer|treppe|mobilitat|prothese|heilbehelf|hilfsmittel")
EINKOMMEN = re.compile(r"einkommen|einkunfte|vermogen|bruttobezug|nettobezug|gehalt|\blohn|umsatz|gewinn|unterhalt|ersparnis|sparbuch|liegenschaft")


# Dritte, die nicht in der Ontologie sind (Zeug:innen, Organisationen, Nummern) → nie raten
FREMD = re.compile(r"zeug ?in|zeuge|partnerorganisation|ansprechperson|kund innennummer|kundennummer|unterschreibenden person|schule|einrichtung|organisation|verein|behandler|apothek|krankenhaus|krankenanstalt|spital|wohngemeinschaft|\bwg\b")

# --- Rollen-Präfix ------------------------------------------------------------------------
VERTRETER = re.compile(r"vertret|bevollmacht|vollmacht|sachwalter|erwachsenenvertret|ausfullende|andere person|vertrauensperson|kontaktperson|antragsteller in fur|zustellbevollm")
VERSICHERTE = re.compile(r"hauptversichert|von der die anspruchsberechtigung|anspruchsvermittelnd|versicherte r wenn")
KIND = re.compile(r"\bkind|tochter|sohn|minderjahrig")
PARTNER = re.compile(r"ehegatt|ehepartner|lebensgefahrt|lebenspartner|eingetragene partner|ehefrau|ehemann")
ARBEITGEBER = re.compile(r"dienstgeber|arbeitgeber|firma\b|betrieb\b")

# --- Grundregeln: (regex auf norm(label+name), schlüssel-suffix) -----------------------------
# Reihenfolge = Priorität. Schlüssel mit "{p}" bekommen das Rollenpräfix (person|vertreter|versicherte_person|kind|partner).
PERSON_RULES: list[tuple[str, str]] = [
    (r"versicherungsnummer|vers nr|vsnr|sv nr|svnr|sozialversicherungsnummer|\bvnr\b|versicherungsnr", "{p}.svnr"),
    (r"geburtsjahr", "{p}.geburtsjahr"),
    (r"geburtsdatum|geb datum|geboren am|\bgeb\b|geburtstag", "{p}.geburtsdatum"),
    (r"geburtsort", "{p}.geburtsort"),
    (r"geburtsland", "{p}.geburtsland"),
    (r"geburtsname|fruhere namen|fruherer name|fruherer familienname", "{p}.geburtsname"),
    (r"staatsburger|staatsangehorig|nationalitat", "{p}.staatsbuergerschaft"),
    (r"(familienstand|personenstand) seit", "{p}.familienstand_seit"),
    (r"familienstand|personenstand", "{p}.familienstand"),
    (r"geschlecht", "{p}.geschlecht"),
    (r"akad grad|akademischer grad|^titel\b|\btitel$", "{p}.titel"),
    (r"vorubergehend|voruebergehend", "aufenthalt.temporaer.voll"),
    (r"^(?!.*(strasse|gasse|platz|plz|postleitzahl|\bort\b|hausn|e ?mail|stiege|\btur\b|turn|\btop\b|schule|einrichtung|arbeitgeber|dienstgeber|firma|bank)).*(anschrift|adresse|wohnadresse)", "{a}.voll"),
    (r"^patient ?in$|^patient$|^name$|^versicherte ?r?$", "{p}.name_voll_umgekehrt"),
    (r"zuname und vorname|familienname und vorname|nachname und vorname|familien und vorname|familienname vorname|nachname vorname|zuname vorname", "{p}.name_voll_umgekehrt"),
    (r"vor und (zu|familien|nach)name|vorname und (zu|familien|nach)name|vorname familienname|vor und nachname", "{p}.name_voll"),
    (r"vorname", "{p}.vorname"),
    (r"familienname|nachname|zuname|^name( des| der)? (antragsteller|versicherten|patient|kund)|patient in$|patient$|patientin|patient\b|antragsteller in$|^antragsteller", "{p}.familienname"),
    (r"^beruf|\bberuf$|berufsbezeichnung|ausgeubter beruf", "{p}.beruf"),
]
ADR_RULES: list[tuple[str, str]] = [
    (r"plz ort|postleitzahl ort|plz und ort|plz wohnort", "{a}.plz_ort"),
    (r"\bplz\b|postleitzahl", "{a}.plz"),
    (r"strasse.*(nr|hausnummer)|wohnsitz|wohnhaft", "{a}.strasse_hausnr"),
    (r"hausnummer stiege tur|hausnr stiege tur|nr stiege tur|hausnr stg tur", "{a}.hausnr_stiege_tuer"),
    (r"strasse|gasse", "{a}.strasse"),
    (r"hausnummer|hausnr|\bhnr\b|haus nr", "{a}.hausnr"),
    (r"\bstiege\b|\bstg\b", "{a}.stiege"),
    (r"\btur\b|turnr|turnummer|\btop\b", "{a}.tuer"),
    (r"\bort\b|wohnort|gemeinde|stadt", "{a}.ort"),
    (r"\bland\b|\bstaat\b", "{a}.land"),
]
MISC_RULES: list[tuple[str, str]] = [
    (r"\biban\b", "bank.iban"),
    (r"\bbic\b|swift", "bank.bic"),
    (r"kontoinhaber|kontowortlaut", "bank.kontoinhaber"),
    (r"kreditinstitut|bankinstitut|\bbank\b|geldinstitut", "bank.institut"),
    (r"ort datum|ort und datum|datum ort", "ort_datum.heute"),
    (r"e ?mail", "{k}.email"),
    (r"telefon|tel nr|\btel\b|handy|mobilnummer|mobiltelefon|erreichbar", "{k}.telefon"),
    (r"beschaftigt bei|dienstgeber in|^dienstgeber|^arbeitgeber|name des (dienst|arbeit)gebers", "arbeitgeber.name"),
    (r"pensionsversicherungstrager|pensionsauszahlende|pension von|pensionstrager", "pension.traeger"),
    (r"zustandige?r? (sv )?(sozialversicherungs)?trager|krankenversicherungstrager|krankenkasse|versicherungstrager|versichert bei|zustandiger trager", "versicherung.traeger"),
    (r"pensionsversicherungstrager|pensionsauszahlende|pension von|pensionstrager", "pension.traeger"),
    (r"pflegegeldstufe|stufe des pflegegeld", "pflegegeld.stufe"),
    (r"beitragskonto", "arbeitgeber.beitragskontonummer"),
    (r"gisa|gewerbe ?register", "unternehmen.gisa"),
    (r"\buid\b", "unternehmen.uid"),
    (r"firmenwortlaut|firmenname|name des betrieb|unternehmen", "unternehmen.name"),
    (r"^(?!.*(geburt|seit|von|bis|beginn|ende|unfall|aufnahme|entlass|ausstell|zuletzt|eintritt|austritt|tod|sterbe|heirat|scheidung|gultig|letzte|erste|antritt|termin)).*(\bdatum\b|antragsdatum|datum$)", "datum.heute"),
]


def _rolle(t: str, kontext: str) -> str | None:
    """Präfix anhand Label (stark) oder Abschnitts-Kontext (schwach)."""
    for txt in (t, kontext):
        if not txt:
            continue
        if VERTRETER.search(txt):
            return "vertreter"
        if PARTNER.search(txt):
            return "partner"
        if KIND.search(txt):
            return "kind"
        if VERSICHERTE.search(txt) and txt is t:
            return "versicherte_person"
    return None


ONT_KEYS: set[str] = set()


def _fmt(key: str, rolle: str | None) -> str:
    p = rolle or "person"
    a = {"person": "adresse", "vertreter": "vertreter.adresse", "versicherte_person": "versicherte_person.adresse"}.get(p, "adresse")
    k = {"vertreter": "vertreter"}.get(p, "kontakt")
    out = key.format(p=p, a=a, k=k)
    return out


def classify(label: str | None, name: str | None, kontext: str = "", typ: str = "text",
             abschnitt_wer: str | None = None) -> tuple[str | None, str]:
    """→ (semantik, wer). `abschnitt_wer` = wer laut Abschnittsüberschrift (arzt|behoerde|None)."""
    t = norm(" ".join(x for x in (label, name) if x))
    lab = norm(label)
    k = norm(kontext)
    if FREMD.search(t):
        return None, "versicherte"
    if re.search(r"^datum\b|datum der unterschrift|datum unterschrift", lab or t) and not re.search(r"geburt|zeug", t) and typ not in ("checkbox", "radio"):
        return "datum.heute", "versicherte"
    if UNTERSCHRIFT.search(t) or typ == "unterschrift":
        r = _rolle(t, k)
        return ("unterschrift.vertreter" if r == "vertreter" else "unterschrift.person"), "unterschrift"
    if STEMPEL.search(t) or abschnitt_wer == "behoerde":
        return "behoerde.vermerk", "behoerde"
    if abschnitt_wer == "arzt" or ARZT.search(t):
        return "arzt.angaben", "arzt"
    if MEDIZIN.search(t):
        return "medizinisch.angaben", "versicherte"
    if typ in ("checkbox", "radio") and not re.search(r"geschlecht|familienstand|personenstand|staatsburger", t):
        return None, "versicherte"
    rolle = _rolle(t, k)
    for rx, key in MISC_RULES:
        if re.search(rx, t):
            s = _fmt(key, rolle)
            return (s if not ONT_KEYS or s in ONT_KEYS else None), "versicherte"
    if EINKOMMEN.search(t):
        return "einkommen.angaben", "versicherte"
    if typ in ("checkbox", "radio") and not re.search(r"geschlecht|familienstand|personenstand|staatsburger", t):
        return None, "versicherte"
    for rx, key in PERSON_RULES + ADR_RULES:
        if re.search(rx, t):
            if rolle in ("kind", "partner") and "{a}" in key:
                rolle_eff = None  # Adresse von Kind/Partner = meist Wohnadresse der Person → nicht raten
                return None, "versicherte"
            s = _fmt(key, rolle)
            if ONT_KEYS and s not in ONT_KEYS:
                return None, "versicherte"
            return s, "versicherte"
    if ARBEITGEBER.search(t):
        if re.search(r"anschrift|adresse", t):
            return "arbeitgeber.adresse", "versicherte"
        if re.search(r"name|bezeichnung", t) or lab in ("dienstgeber", "arbeitgeber"):
            return "arbeitgeber.name", "versicherte"
    return None, "versicherte"


# Abschnittsmarker auf der Seite: Text → wer für alle Felder darunter (bis zum nächsten Marker)
ABSCHNITT_ARZT = re.compile(r"(von|vom|durch) (der |dem |den )?(behandelnden )?(arzt|arztin|aerzt|arztinnen|krankenanstalt|krankenhaus|facharzt)|arztliche[rns]? (bestatigung|stellungnahme|befund|gutachten|bericht|verordnung|zuweisung|angaben|bescheinigung|attest)|arztlicher teil|arzt ?auszufullen|arztin ?auszufullen|medizinischer teil|medizinische angaben|nur fur (den|die) (arzt|arztin)")
ABSCHNITT_BEHOERDE = re.compile(r"vom (versicherungs)?trager auszufullen|wird von der .{0,30} ausgefullt|nur fur interne|von der (svs|ogk|bvaeb|pva|anstalt|kasse|behorde) auszufullen|amtsvermerk|eingangsstempel")
ABSCHNITT_PERSON = re.compile(r"von (der|dem) (versicherten|antragsteller|patient|kund)|angaben (zur|zum|der|des) (person|antragsteller|versicherten|patient)|personaldaten|personliche daten|antragsteller ?in|daten der|angaben zu")


def abschnitt_wer(text: str) -> str | None:
    t = norm(text)
    if ABSCHNITT_BEHOERDE.search(t):
        return "behoerde"
    if ABSCHNITT_ARZT.search(t):
        return "arzt"
    if ABSCHNITT_PERSON.search(t):
        return "person"
    return None
