"""Guru aturan untuk RL (dulu LLM, kini murni aturan lokal + kamus bahan)"""
import re

def llm_parse_filename(filename):
    """LLM baca nama file jadi enak dibaca"""
    # fallback: parse sendiri tanpa LLM
    tmp = re.sub(r'[_\-\(\)]', ' ', filename)
    tmp = re.sub(r'\s+', ' ', tmp).strip()
    tmp = re.sub(r'\.pdf$', '', tmp, flags=re.I)
    return tmp

STIKER_1S = {"Vinyl", "Hologram", "Gold", "Silver", "Stiker HVS"}


def parse_duplex(filename):
    """1s/2s/dr dari filename. 'Doff/Hologram 2s'/dll itu finishing, bukan duplex.
    Stiker (Vinyl/Hologram/Gold/Silver, Kromo+stiker) TIDAK PERNAH 2s.
    Kromo KERTAS (tanpa kata stiker) bisa 1s/2s normal."""
    low = filename.lower()
    try:
        from bahan_dict import guess_bahan as _gb
        _b = _gb(low)
    except ImportError:
        _b = None
        if any(k in low for k in ("vinyl", "hologram", "gold", "silver")):
            return "1s"
        if any(k in low for k in ("kromo", "cromo")) and ("stiker" in low or "sticker" in low):
            return "1s"
        if "hvs" in low and ("stiker" in low or "sticker" in low):
            return "1s"
    if _b in STIKER_1S:
        return "1s"
    if _b == "Kromo" and ("stiker" in low or "sticker" in low):
        return "1s"
    if ("data sama" in low or "datasama" in low
            or "bolak balik sama" in low or "gambar sama" in low
            or "nomor sama" in low or "nomer sama" in low
            or "bolak balik gbr sama" in low or "gbr sama" in low
            or "serupa" in low):
        return "dr"
    tmp = re.sub(r"(doff|dof|laminasi|laminating|glossy|gloss|matte|hologram|canvas|uv|varnish)\s*2s", " ", low)
    if ("2s" in tmp or "bolak" in low or "dua muka" in low
            or "depan belakang" in low or "2 sisi" in low):
        return "2s"
    return "1s"


def skip_reason(filename):
    """Cermin aturan skip watcher. Return alasan atau None jika lolos."""
    import re as _re
    low = filename.lower()
    if not low.endswith(".pdf"):
        return "bukan PDF"
    if "kisscut" in low or "diecut" in low:
        return "kisscut/diecut"
    if "hardcover" in low:
        return "hardcover"
    if "map" in low:
        return "map"
    if "depan" in low or "belakang" in low:
        return "depan/belakang"
    try:
        from bahan_dict import has_bahan as _hb
        if not _hb(filename):
            return "tidak ada nama bahan"
    except ImportError:
        pass
    if "master" in low or "kalkir" in low:
        return "master/kalkir"
    if not _re.search(r"1d\d+", low):
        return "tidak ada dx"
    if "test" in low or "tes" in low:
        for kw in ("spiral kiri", "spiral atas", "spiral kanan", "staples punggung",
                   "lem panas", "staples tengah", "booklet"):
            if kw in low:
                return f"test/tes + {kw}"
    return None


def ringkas(filename):
    """Format bersih: bahan | duplex | dx | finishing | repeat. '-' jika tak ada."""
    p = llm_teacher_preset(filename)
    fin = p.get("finishing", "-")
    if fin == "bleed":
        fin = "bleed 2mm"
    return " | ".join([str(p.get("bahan") or "-"), str(p.get("duplex") or "-"),
                       str(p.get("dx") or "-"), str(fin),
                       str(p.get("repeat") or "-")])


def llm_teacher_preset(filename):
    """Guru: tebak preset dengan aturan @xKecil + booklet/staples (fallback rule jika LLM gagal)"""
    import re as _re
    try:
        from bahan_dict import guess_bahan
    except ImportError:
        guess_bahan = lambda t: None
    preset={}
    _g = guess_bahan(filename)
    if _g: preset["bahan"]=_g
    m=_re.search(r"1d\d+\s*[=:@]*\s*@?\d[\d.]*\s*(KECIL|BESAR)", filename, _re.I)
    if m: preset["dx"]=_re.sub(r"\s+"," ", m.group(0)).strip()
    preset["sheet"]="A3+ Full (32.5x48.7cm)"
    preset["finishing"]="crop"
    _flow = _re.sub(r"bled+", "bleed", filename.lower())  # toleran typo Bledd
    if "potong bleed" in _flow or "bleed 2mm" in _flow: preset["finishing"]="bleed"
    low = filename.lower()
    # booklet hanya jika kata "booklet" ATAU frasa "staples tengah" utuh.
    # "staples" saja (mis. staples punggung) BUKAN booklet.
    is_booklet = "booklet" in low or "staples tengah" in low or "staple tengah" in low
    m=_re.search(r"1d\d+.*@\s*(\d+)\s*kecil", filename, _re.I)
    if _re.search(r"1d\d+.*@\s*\d+\s*besar", filename, _re.I):
        preset["repeat"]="repeat"
    elif m:
        x = m.group(1)
        if is_booklet:
            preset["repeat"] = "booklet(collate)" if x=="1" else "booklet(repeat)"
        else:
            preset["repeat"] = "collate-cut" if x=="1" else f"collate-cut({x})"
    elif is_booklet:
        preset["repeat"]="booklet"
    else:
        preset["repeat"]="repeat"
    preset["duplex"] = parse_duplex(filename)
    return preset
