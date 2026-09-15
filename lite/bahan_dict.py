"""Kamus bahan + toleransi typo.

Contoh: 'Sriker Cromo' -> dikenali sebagai Stiker + Kromo.
Dipakai: skip-check watcher, guru llm_zen, fallback preset_learner_rl.
"""
import difflib
import re

# keyword (lower) -> nama kanonis
CANONICAL = {
    "vinyl": "Vinyl",
    "kromo": "Kromo",
    "ac260gr": "Ac260gr",
    "ac190gr": "Ac190gr",
    "ac230gr": "Ac230gr",
    "ac310gr": "Ac310gr",
    "ap120gr": "Ap120gr",
    "ap150gr": "Ap150gr",
    "ap190gr": "Ap190gr",
    "hvs100gr": "Hvs100gr",
    "hvs": "Hvs100gr",
    "concord": "Concord",
    "concorde": "Concord",
    "rajawali": "Rajawali",
    "pindo": "Pindo",
    "jasmine": "Jasmine",
    "ivory": "Ivory",
    "transparant": "Transparant",
    "hologram": "Hologram",
    "gold": "Gold",
    "silver": "Silver",
}

# kata produk (lolos skip-check, tapi BUKAN bahan untuk guru)
EXTRA_SKIP = {"stiker", "sticker", "kalkir"}

# typo umum -> keyword benar
TYPO_MAP = {
    "cromo": "kromo", "chromo": "kromo", "kroomo": "kromo", "komo": "kromo",
    "sriker": "stiker", "stker": "stiker", "sicker": "stiker",
    "sticker": "stiker",
    "vynil": "vinyl", "vinil": "vinyl", "vynyl": "vinyl", "finyl": "vinyl",
    "vinly": "vinyl",
    "jasmin": "jasmine",
    "concorde": "concord",
    "trasparant": "transparant", "transparan": "transparant",
    "hps": "hvs", "hfs": "hvs",
    "rajawli": "rajawali", "rajwali": "rajawali",
}

FIN_2S = r"(doff|dof|laminasi|laminating|glossy|gloss|matte|hologram|canvas|uv|varnish)\s*2s"

_ALL_FORMS = list(CANONICAL.keys()) + list(TYPO_MAP.keys()) + list(EXTRA_SKIP)


def strip_finishing(low):
    """Buang frasa finishing 'X 2s'. Hologram kondisional (bahan sekaligus)."""
    t = re.sub(FIN_2S, " ", low)
    if "hologram" in t and any(k != "hologram" and k in t for k in CANONICAL.keys()):
        t = re.sub(r"hologram\s*2s", " ", t)
    return t


def fix_typos(text):
    """Ganti kata typo dengan bentuk benar (whole-word)."""
    def _rep(m):
        w = m.group(0)
        key = TYPO_MAP.get(w.lower())
        return key if key else w
    return re.sub(r"[A-Za-z]+", _rep, text)


def _fuzzy_word(word):
    """Kembalikan keyword benar untuk satu kata, atau None."""
    w = word.lower()
    if w in CANONICAL or w in EXTRA_SKIP:
        return TYPO_MAP.get(w, w)
    if w in TYPO_MAP:
        return TYPO_MAP[w]
    if len(w) < 4 or re.fullmatch(r"\d+", w):
        return None
    m = difflib.get_close_matches(w, _ALL_FORMS, n=1, cutoff=0.82)
    if not m:
        return None
    key = m[0]
    return TYPO_MAP.get(key, key)


def has_bahan(text):
    """True jika ada nama bahan (toleran typo). Untuk skip-check."""
    t = fix_typos(text).lower()
    for key in list(CANONICAL.keys()) + list(EXTRA_SKIP):
        if key in t:
            return True
    for w in re.findall(r"[a-z]+", t):
        if _fuzzy_word(w) is not None:
            return True
    return False


def guess_bahan(text):
    """Tebak nama bahan kanonis (toleran typo), atau None. Untuk guru/koreksi."""
    t = strip_finishing(fix_typos(text).lower())
    low = t.lower()
    m = re.search(r"(ac|ap)\d+\s*gr", low)
    if m:
        return re.sub(r"\s+", "", m.group(0)).capitalize()
    for key in sorted(CANONICAL.keys(), key=len, reverse=True):
        if key in low:
            return CANONICAL[key]
    for w in re.findall(r"[a-z]+", low):
        hit = _fuzzy_word(w)
        if hit in CANONICAL:
            return CANONICAL[hit]
    return None
