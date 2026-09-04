"""Zen Free LLM guru untuk RL — muse-spark-1.2-contributor-free"""
import os, json, pathlib, re
try:
    import requests
except:
    requests=None

ZEN_URL = "https://openrouter.ai/api/v1/chat/completions"
AUTH_PATH = pathlib.Path.home() / ".local" / "share" / "opencode" / "auth.json"

class LLMError(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg
        super().__init__(f"[{code}] {msg}")

def _get_key():
    if not AUTH_PATH.exists():
        raise LLMError("E019", f"auth.json tidak ditemukan: {AUTH_PATH}")
    try:
        d=json.loads(AUTH_PATH.read_text(encoding="utf-8"))
        v=d.get("openrouter","")
        if isinstance(v, dict): v=v.get("key","")
        if not v:
            raise LLMError("E019", "API key kosong di auth.json")
        return v
    except json.JSONDecodeError:
        raise LLMError("E019", "auth.json corrupt")

def call_llm(prompt, system="Jawab hanya JSON 1 baris.", temperature=0.2, max_tokens=120):
    if not requests:
        raise LLMError("E022", "requests module tidak terinstall")
    try:
        key=_get_key()
    except LLMError as e:
        raise e
    models=["nvidia/nemotron-3.5-lightning:free","inclusionai/ling-3.0-flash-fin:free","liquid/lfm-2.5-2.6b:free"]
    headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"}
    last_error = None
    for model in models:
        try:
            r=requests.post(ZEN_URL, headers=headers, json={
                "model": model,
                "messages": [{"role":"system","content":system},{"role":"user","content":prompt}],
                "temperature": temperature, "max_tokens": max_tokens
            }, timeout=15)
            if r.status_code==200:
                j=r.json()
                txt=j["choices"][0]["message"]["content"].strip()
                if "thinking process" in txt.lower() or "thinking" in txt.lower():
                    lines=txt.split("\n")
                    for line in lines:
                        l=line.strip()
                        if l and not any(l.startswith(x) for x in ["Here","1.","2.","3.","4.","-","*","**","User","I.","The","If","For","Based","Let","Now"]):
                            return l
                    continue
                return txt
            else:
                last_error = f"HTTP {r.status_code}"
        except requests.exceptions.Timeout:
            last_error = "timeout"
            continue
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            continue
    raise LLMError("E020", f"Semua model gagal: {last_error}")

def llm_parse_filename(filename):
    """LLM baca nama file jadi enak dibaca"""
    # fallback: parse sendiri tanpa LLM
    import re
    tmp = re.sub(r'[_\-\(\)]', ' ', filename)
    tmp = re.sub(r'\s+', ' ', tmp).strip()
    tmp = re.sub(r'\.pdf$', '', tmp, flags=re.I)
    return tmp

def parse_duplex(filename):
    """1s/2s/dr dari filename. 'Doff 2s'/'Laminasi 2s'/dll itu finishing, bukan duplex."""
    low = filename.lower()
    if "data sama" in low or "bolak balik sama" in low:
        return "dr"
    tmp = re.sub(r"(doff|dof|laminasi|laminating|glossy|gloss|hologram|canvas|uv|varnish)\s*2s", " ", low)
    if ("2s" in tmp or "bolak" in low or "dua muka" in low
            or "depan belakang" in low or "2 sisi" in low):
        return "2s"
    return "1s"


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
    m=_re.search(r"1d\d+\s*[=:@]*\s*@?\d*\s*(KECIL|BESAR)", filename, _re.I)
    if m: preset["dx"]=_re.sub(r"\s+"," ", m.group(0)).strip()
    preset["sheet"]="A3+ Full (32.5x48.7cm)"
    preset["finishing"]="crop"
    if "potong bleed" in filename.lower() or "bleed 2mm" in filename.lower(): preset["finishing"]="bleed"
    is_booklet = "booklet" in filename.lower() or "staples" in filename.lower()
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
