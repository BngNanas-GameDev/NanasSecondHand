"""
Konica Minolta INEO 2060 — Aturan Paper Profile Settings.

Alur: bahan + duplex + finishing → semua print settings.

Paper Profile Settings (dari Job Centro):
    Paper Profile   : nama profile (dropdown)
    Paper Tray      : Bypass / Tray 1 / Tray 2
    Paper Size      : auto oleh profile
    Feed Direction  : auto oleh profile
    Paper Type      : auto oleh profile (Coated GL / Fine / Coated MO / Sticker)
    Weight          : auto oleh profile (angka gr)
    Weight Unit     : g/m² (selalu)
    Color           : auto oleh profile
    Pre-Punched     : Off (selalu)

Manual Settings:
    Simplex/Duplex  : berdasarkan mode (1s/2s/dr)
    Glossy          : berdasarkan bahan
    N-to-1          : berdasarkan finishing (booklet)
    Face Up/Down    : berdasarkan duplex + finishing
"""
from __future__ import annotations
import re


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PAPER PROFILE TABLE — SEMUA 28 PROFILE DARI PRINTER
# ═══════════════════════════════════════════════════════════════════════════════
# Tuple: (name, paper_type, weight_min, weight_max, feed_dir, width, height)
# weight = berat kertas dalam g/m²

PROFILES = {
    # id = PaperProfile id di printer (dari GetHotFolderTicketInfo, 2026-09-18)
    # === BYPASS (MediaSource MANUAL) ===
    "BYPASS_STICKER_A3+":      {"id": 13, "type": "Sticker",     "wmin": 106, "wmax": 135, "feed": "Short Edge", "size": (325, 487)},
    "Bypass_A3+_230gr":        {"id": 3,  "type": "Coated GL",   "wmin": 217, "wmax": 256, "feed": "Short Edge", "size": (325, 487)},
    "BYPASS_190gr_A3+":        {"id": 21, "type": "Coated GL",   "wmin": 177, "wmax": 216, "feed": "Short Edge", "size": (325, 487)},
    "BYPASS_330x487mm":        {"id": 14, "type": "Coated GL",   "wmin": 177, "wmax": 256, "feed": "Short Edge", "size": (330, 487)},
    "BYPASS_AC310gr":          {"id": 37, "type": "Coated GL",   "wmin": 257, "wmax": 350, "feed": "Short Edge", "size": (325, 487)},

    # === TRAY 2 (MediaSource TRAY2) ===
    "TRAY_AP_120GR_A3+":       {"id": 5,  "type": "Coated GL",   "wmin": 106, "wmax": 135, "feed": "Short Edge", "size": (325, 487)},
    "TRAY_AP_150_A3+":         {"id": 6,  "type": "Coated GL",   "wmin": 136, "wmax": 176, "feed": "Short Edge", "size": (325, 487)},
    "HVS 100gr":               {"id": 24, "type": "Fine",        "wmin":  92, "wmax": 105, "feed": "Short Edge", "size": (325, 487)},
}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. BAHAN → PAPER PROFILE
# ═══════════════════════════════════════════════════════════════════════════════

BAHAN_TO_PROFILE = {
    # Sticker — semua stiker pakai BYPASS_STICKER_A3+
    "Vinyl":        "BYPASS_STICKER_A3+",
    "Stiker":       "BYPASS_STICKER_A3+",
    "Hologram":     "BYPASS_STICKER_A3+",
    "Gold":         "BYPASS_STICKER_A3+",
    "Silver":       "BYPASS_STICKER_A3+",
    "Stiker Kromo": "BYPASS_STICKER_A3+",
    "Stiker HVS":   "BYPASS_STICKER_A3+",
    "Transparant":  "BYPASS_STICKER_A3+",

    # Art Paper — Ac/Ap230,260 → BYPASS_A3+_230gr
    "Ap120gr":      "TRAY_AP_120GR_A3+",
    "Ap150gr":      "TRAY_AP_150_A3+",
    "Ap190gr":      "BYPASS_190gr_A3+",
    "Ap230gr":      "Bypass_A3+_230gr",
    "Ap260gr":      "Bypass_A3+_230gr",
    "Ap310gr":      "BYPASS_AC310gr",

    # Art Carton
    "Ac190gr":      "BYPASS_190gr_A3+",
    "Ac230gr":      "Bypass_A3+_230gr",
    "Ac260gr":      "Bypass_A3+_230gr",
    "Ac310gr":      "BYPASS_AC310gr",

    # HVS (.158: profil "HVS 100gr" id 24; tiket .157 tanpa profil)
    "Hvs100gr":     "HVS 100gr",

    # Specialty — Rajawali, Jasmine, Concord, Pindo, Kromo kertas → BYPASS_330x487mm
    "Concord":      "BYPASS_330x487mm",
    "Rajawali":     "BYPASS_330x487mm",
    "Pindo":        "BYPASS_330x487mm",
    "Jasmine":      "BYPASS_330x487mm",
    "Kromo":        "BYPASS_330x487mm",
}


def resolve_bahan(filename: str, bahan: str = "") -> str:
    """Bedakan 'Stiker Kromo' vs 'Kromo' kertas dari filename.

    - kromo/cromo/chromo + stiker/sticker → "Stiker Kromo" (stiker)
    - kromo/cromo/chromo tanpa stiker     → "Kromo" (kertas)
    - selain itu → bahan apa adanya.
    """
    low = (filename or "").lower()
    if any(k in low for k in ("kromo", "cromo", "chromo")):
        if "stiker" in low or "sticker" in low:
            return "Stiker Kromo"
        return "Kromo"
    if "hvs" in low and ("stiker" in low or "sticker" in low):
        return "Stiker HVS"
    return bahan


def resolve_profile(bahan: str) -> str:
    """Ambil profile name dari bahan. Fallback: weight lookup."""
    if bahan in BAHAN_TO_PROFILE:
        return BAHAN_TO_PROFILE[bahan]

    # Weight lookup
    wt = _extract_weight(bahan)
    pt = _paper_type(bahan)
    for name, info in PROFILES.items():
        if info["type"] == pt and wt and info["wmin"] <= wt <= info["wmax"]:
            return name

    return "Bypass_A3+_230gr"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. BAHAN → PAPER TYPE
# ═══════════════════════════════════════════════════════════════════════════════

BAHAN_PAPER_TYPE = {
    "Vinyl": "Sticker", "Stiker": "Sticker", "Hologram": "Sticker",
    "Gold": "Sticker", "Silver": "Sticker", "Stiker Kromo": "Sticker",
    "Transparant": "Sticker", "Stiker HVS": "Sticker",
    "Ap120gr": "Coated GL", "Ap150gr": "Coated GL", "Ap190gr": "Coated GL",
    "Ap230gr": "Coated GL", "Ap260gr": "Coated GL", "Ap310gr": "Coated GL",
    "Ac190gr": "Coated GL", "Ac230gr": "Coated GL", "Ac260gr": "Coated GL",
    "Ac310gr": "Coated GL", "Kromo": "Coated GL",
    "Master": "Coated MO",
    "Hvs100gr": "Fine",
    "Concord": "Fine", "Rajawali": "Fine", "Pindo": "Fine",
    "Jasmine": "Fine", "Ivory": "Fine",
}

def _paper_type(bahan: str) -> str:
    return BAHAN_PAPER_TYPE.get(bahan, "Coated GL")

def _extract_weight(bahan: str) -> int | None:
    """Ambil angka berat dari nama bahan. 'Ap260gr' -> 260. Abaikan A3/F4."""
    # Buang suffix ukuran kertas
    t = re.sub(r"\b[AF]\d+\b", "", bahan)
    m = re.search(r"(\d+)", t)
    return int(m.group(1)) if m else None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TRAY SELECTION
# ═══════════════════════════════════════════════════════════════════════════════

BYPASS_BAHAN = {
    "Ap190gr", "Ap230gr", "Ap260gr", "Ap310gr",
    "Ac190gr", "Ac230gr", "Ac260gr", "Ac310gr",
    "Concord", "Pindo", "Rajawali", "Jasmine", "Kromo",
    "Vinyl", "Stiker", "Hologram", "Gold", "Silver",
    "Stiker Kromo", "Stiker HVS", "Transparant",
}

TRAY2_BAHAN = {"Ap120gr", "Ap150gr", "Ac120gr", "Ac150gr", "Hvs100gr"}

def _tray(bahan: str) -> str:
    if bahan in BYPASS_BAHAN:
        return "Bypass Tray"
    if bahan in TRAY2_BAHAN:
        return "Tray 2"
    return "Tray 1"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SIMPLEX / DUPLEX
# ═══════════════════════════════════════════════════════════════════════════════

def _is_simplex(duplex: str) -> bool:
    return duplex == "1s"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GLOSSY
# ═══════════════════════════════════════════════════════════════════════════════

# Ac/Ap 230, 260, 120, 150, 310, 190 + semua stiker → Glossy ON
# Pindo, Jasmine, Concord, Rajawali, HVS → Glossy OFF
_GLOSSY_ON = {
    "Ap120gr", "Ap150gr", "Ap190gr", "Ap230gr", "Ap260gr", "Ap310gr",
    "Ac120gr", "Ac150gr", "Ac190gr", "Ac230gr", "Ac260gr", "Ac310gr",
    "Vinyl", "Stiker", "Hologram", "Gold", "Silver", "Stiker Kromo", "Transparant",
}

def _is_glossy(bahan: str) -> bool:
    return bahan in _GLOSSY_ON


# ═══════════════════════════════════════════════════════════════════════════════
# 7. FACE UP / DOWN
# ═══════════════════════════════════════════════════════════════════════════════

# 1s (Simplex) → Face Up
# 2s/dr (Duplex) → Face Down
# Booklet → Face Up
def _is_face_up(duplex: str, finishing: str) -> bool:
    return duplex == "1s"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. N-TO-1
# ═══════════════════════════════════════════════════════════════════════════════

def _is_nto1(finishing: str) -> bool:
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. MAIN FUNCTION — HITUNG SEMUA SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

def get_print_settings(
    bahan: str,
    duplex: str = "1s",
    finishing: str = "crop",
    filename: str = "",
) -> dict:
    """
    Hitung SEMUA print settings dari bahan + duplex + finishing.

    Returns dict:
        paper_profile   : nama profile di Job Centro
        paper_type      : Coated GL / Fine / Coated MO / Sticker
        paper_size      : (width_mm, height_mm)
        feed_direction  : "Short Edge" / "Long Edge"
        tray            : "Bypass Tray" / "Tray 1" / "Tray 2"
        weight          : berat kertas (gr)
        weight_unit     : "g/m²"
        color           : warna kertas
        pre_punched     : "Off"
        simplex         : True/False
        glossy          : True/False
        nto1            : True/False
        face_up         : True/False
    """
    if filename:
        bahan = resolve_bahan(filename, bahan)
    profile = resolve_profile(bahan)
    info = PROFILES.get(profile, {})
    wt = _extract_weight(bahan)

    return {
        # Paper Profile (auto dari profile)
        "paper_profile":  profile,
        "paper_type":     info.get("type", "Coated GL"),
        "paper_size":     info.get("size", (325, 487)),
        "feed_direction": info.get("feed", "Short Edge"),
        "weight":         wt or info.get("wmin", 230),
        "weight_unit":    "g/m²",
        "color":          _color(bahan),
        "pre_punched":    "Off",

        # Tray (manual)
        "tray":           _tray(bahan),

        # Print settings (manual)
        # Duplex: booklet = 2s (selalu duplex)
        "simplex":        _is_simplex("2s" if finishing == "booklet" else duplex),
        "glossy":         _is_glossy(bahan),
        "nto1":           _is_nto1(finishing),
        "face_up":        _is_face_up("2s" if finishing == "booklet" else duplex, finishing),
    }


def _color(bahan: str) -> str:
    """Warna kertas. Default: 'Color'."""
    if _paper_type(bahan) == "Sticker":
        return "Color"
    if bahan == "Hvs100gr":
        return "White"
    return "Color"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. FORMAT UNTUK DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def format_settings(s: dict) -> str:
    """Format print settings jadi string readable."""
    w, h = s["paper_size"]
    parts = [
        f"Profile: {s['paper_profile']}",
        f"Size: {w}x{h}mm",
        f"Type: {s['paper_type']}",
        f"Weight: {s['weight']}{s['weight_unit']}",
        f"Tray: {s['tray']}",
        f"{'Simplex' if s['simplex'] else 'Duplex'}",
        f"Glossy: {'ON' if s['glossy'] else 'OFF'}",
    ]
    if s["nto1"]:
        parts.append("N-to-1")
    parts.append(f"Face: {'Up' if s['face_up'] else 'Down'}")
    parts.append(f"Feed: {s['feed_direction']}")
    return " | ".join(parts)
