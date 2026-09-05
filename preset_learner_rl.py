"""
Pure RL per kategori — Q-learning tabular TANPA heuristic/LLM fallback
State: frozenset keywords tanpa nama pelanggan
Action: value per kategori
Reward: +1 benar, -1 koreksi, +0.5 sukses
Q-update: Q += 0.3*(reward - Q)
Default cold-start jika state belum ada -> action default conf 0.35
"""
import json, pathlib, re, random
from pathlib import Path

BASE = Path(__file__).parent
DATA_DIR = BASE / "data" / "memory_rl"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = ["sheet","bahan","duplex","dx","finishing","repeat"]
ALPHA = 0.3
EPSILON = 0.15  # explore 15% saat Q belum matang

# default cold-start — finishing gampang ketik: crop / bleed
DEFAULTS = {
    "sheet": "A3+ Full (32.5x48.7cm)",
    "bahan": "-",
    "duplex": "1s",
    "dx": "-",
    "finishing": "crop",
    "repeat": "repeat",
}
FINISH_MAP = {
    "crop": {"mode":"crop","bleed_mm":0,"inner_crop":True,"mark_len_mm":5,"bleed_on":True,"line_color":"gray"},
    "bleed": {"mode":"crop","bleed_mm":2,"inner_crop":False,"mark_len_mm":5,"bleed_on":True,"line_color":"gray"},
    "normal": {},
    "": {},
}

class RLError(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg
        super().__init__(f"[{code}] {msg}")

def _finishing_to_preset(v):
    if isinstance(v, dict): return v
    return FINISH_MAP.get(str(v).lower().strip(), {"mode":"crop","bleed_mm":0,"inner_crop":False,"mark_len_mm":5,"bleed_on":True} if str(v).lower()=="crop" else {})

def _normalize(s):
    return re.sub(r'[^a-z0-9]+',' ', s.lower()).strip()

def normalize_dx(v):
    """Kanonis: '1d1=3Kecil' / '1d2 = 2 KECIL repeat' / '1d4 = 1.000 KECIL'
    -> '1d1 = 3 KECIL'. Titik ribuan dibuang."""
    m = re.search(r"1d\s*(\d+)\s*(?:[=:@]\s*)?@?\s*(\d[\d.]*)?\s*(kecil|besar)?", str(v), re.I)
    if not m:
        return str(v).strip()
    s = f"1d{m.group(1)}"
    if m.group(2):
        s += f" = {m.group(2).replace('.', '')}"
    if m.group(3):
        s += f" {m.group(3).upper()}"
    return s

def _bucket_uk(s):
    """Ukuran produk -> bucket A3+ (325x487): portrait / landscape / oversize."""
    m = re.match(r"(\d+)x(\d+)mm", s)
    if not m:
        return s
    w, h = int(m.group(1)), int(m.group(2))
    if w <= 320 and h <= 482:
        return "1-320x1-482"
    if w <= 482 and h <= 320:
        return "1-482x1-320"
    return "oversize"

def _state_key(filename):
    tmp = re.sub(r"^[^_]+_DITUNGGU_+", "", filename, flags=re.I)
    tmp = re.sub(r"^[^_]+_TUNGGU_+", "", tmp, flags=re.I)
    tmp = re.sub(r"\(A\d+L[^)]*\)", " ", tmp, flags=re.I)
    tmp = re.sub(r"ON\d+", " ", tmp, flags=re.I)
    fn = _normalize(tmp)
    try:
        from bahan_dict import TYPO_MAP as _TYPO
    except ImportError:
        _TYPO = {}
    words=[]
    for w in fn.split():
        if len(w)<3: continue
        if re.fullmatch(r"\d+", w): continue  # angka murni = noise (TOTAL/jumlah)
        if re.match(r"^\d+x\d+mm$", w): continue  # ukuran eksak -> cukup bucketnya
        if w in ("pdf","dan","untuk","lembar","ditunggu","tunggu"): continue
        if re.match(r"^[a-z]+\d+$", w): continue
        if re.match(r"^a\d+l$", w): continue
        if re.match(r"^on\d+$", w): continue
        for part in _TYPO.get(w, w).split():  # hamji->hanji, dst.
            words.append(part)
            if len(words)>=4: break
        if len(words)>=4: break
    m_uk = re.search(r"\d+x\d+mm", filename.lower())
    if m_uk:
        bkt = _bucket_uk(m_uk.group(0))
        if bkt not in words:
            words.append(bkt)
    m_dx = re.search(r"1d\d+", filename.lower())
    if m_dx and m_dx.group(0) not in words:
        words.append(m_dx.group(0))
    return frozenset(words[:5])

def _key_str(state):
    return "|".join(sorted(state))

def _load_q(cat):
    p = DATA_DIR / f"{cat}.json"
    if p.exists():
        try: 
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise RLError("E016", f"Q-table corrupt: {cat}.json")
        except Exception as e:
            raise RLError("E016", f"Q-table load gagal: {e}")
    return {}

def _save_q(cat, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        (DATA_DIR / f"{cat}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except PermissionError:
        raise RLError("E016", f"Q-table save gagal: permission denied - {cat}.json")
    except Exception as e:
        raise RLError("E016", f"Q-table save gagal: {e}")

def suggest_rl(filename, cat):
    """Pure RL: Q max jika ada, else default. Finishing pakai string crop/bleed."""
    state = _key_str(_state_key(filename))
    q_table = _load_q(cat)
    if state in q_table and q_table[state]:
        actions = q_table[state]
        best_action = max(actions, key=lambda a: actions[a])
        best_q = actions[best_action]
        if best_q <= 0:
            return DEFAULTS[cat], 0.35, {"rl": False, "state": state, "reason": "Q<=0 default"}
        if random.random() < EPSILON and len(actions) > 1:
            other = [a for a in actions if a != best_action]
            if other:
                pick = random.choice(other)
                q = actions[pick]
                return pick, 0.4, {"rl": True, "Q": q, "state": state, "explore": True}
        conf = min(0.95, 0.5 + best_q*0.3)
        return best_action, conf, {"rl": True, "Q": best_q, "state": state}
    return DEFAULTS[cat], 0.35, {"rl": False, "state": state, "cold": True}

def train_rl(filename, corrected_value, cat, reward=1):
    state = _key_str(_state_key(filename))
    q_table = _load_q(cat)
    if state not in q_table:
        q_table[state] = {}
    if cat=="finishing" and isinstance(corrected_value, dict):
        if corrected_value.get("bleed_mm")==2: corrected_value="bleed"
        elif corrected_value.get("mode")=="crop": corrected_value="crop"
        else: corrected_value="crop"
    action_key = str(corrected_value)
    if cat == "dx":
        action_key = normalize_dx(action_key)
    old_q = q_table[state].get(action_key, 0)
    new_q = old_q + ALPHA * (reward - old_q)
    # jika koreksi manusia (1) atau guru (0.8) masih kalah dari best lain,
    # paksa overtake biar koreksi langsung muncul di preset guru
    if reward >= 0.8:
        other_max = max([v for k,v in q_table[state].items() if k!=action_key], default=0)
        if new_q <= other_max:
            new_q = round(other_max + 0.1, 3)
        else:
            new_q = round(new_q, 3)
    else:
        new_q = round(new_q, 3)
    q_table[state][action_key] = new_q
    _save_q(cat, q_table)
    return {"state": state, "action": action_key, "old_Q": old_q, "new_Q": new_q, "reward": reward}

def _dx_repeat_rule(filename, repeat_val):
    """Aturan: @xKecil → collate-cut, @xBESAR → repeat, + BOOKLET/Staples tengah → booklet varian"""
    is_booklet = "booklet" in filename.lower() or "staples tengah" in filename.lower() or "staples" in filename.lower()
    if re.search(r"1d\d+.*@\s*\d+\s*besar", filename, re.I):
        return "repeat"
    m = re.search(r"1d\d+.*@\s*(\d+)\s*kecil", filename, re.I)
    if m:
        x = m.group(1)
        if is_booklet:
            return f"booklet(collate)" if x=="1" else f"booklet(repeat)"
        return f"collate-cut({x})" if x!="1" else "collate-cut"
    if "@" in filename and "kecil" in filename.lower():
        return "booklet(collate)" if is_booklet else "collate-cut"
    if is_booklet:
        # booklet tanpa @ → default booklet
        return "booklet"
    return repeat_val

def suggest_parallel_rl(filename):
    import concurrent.futures
    cats = CATEGORIES
    results={}
    def task(cat):
        return cat, suggest_rl(filename, cat)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(task, cat): cat for cat in cats}
        for fut in concurrent.futures.as_completed(futs):
            cat, res = fut.result()
            results[cat]=res
    preset={}
    conf_avg=0
    for cat in cats:
        v,c,_ = results[cat]
        if cat=="finishing":
            preset.update(_finishing_to_preset(v))
        elif cat=="duplex":
            # aturan dr: data sama / balak balik sama
            if "data sama" in filename.lower() or "bolak balik sama" in filename.lower():
                preset["duplex"]="dr"
            else:
                preset["duplex"]=v
        elif cat=="dx": preset["dx"]=v
        elif cat=="sheet": preset["sheet"]=v
        elif cat=="bahan": preset["bahan"]=v
        elif cat=="repeat": preset["repeat_mode"]=_dx_repeat_rule(filename, v)
        conf_avg+=c
    conf_avg/=len(cats)
    return preset, conf_avg, results

def _dstr(v):
    """Normalisasi nilai duplex ke 1s/2s/dr."""
    if v is True or str(v).lower() in ("true", "2s"):
        return "2s"
    if v is False or str(v).lower() in ("false", "1s"):
        return "1s"
    if str(v).lower() == "dr":
        return "dr"
    return str(v)


def _fstr(preset):
    """Jawaban finishing sebagai string crop/bleed."""
    if isinstance(preset, dict):
        if preset.get("finishing"):
            return str(preset["finishing"]).lower()
        if preset.get("bleed_mm") == 2:
            return "bleed"
        if preset.get("mode") == "crop":
            return "crop"
    return "crop"


def guru_preset_for(filename):
    """Preset guru (norm) tanpa melatih. Return None jika guru angkat tangan."""
    from llm_zen import llm_teacher_preset
    preset = llm_teacher_preset(filename)
    if not preset:
        import re as _re
        try:
            from bahan_dict import guess_bahan as _guess
        except ImportError:
            _guess = lambda t: None
        preset = {}
        _g = _guess(filename)
        if _g:
            preset["bahan"] = _g
        m = _re.search(r"1d\d+\s*[=:@]*\s*@?\d[\d.]*\s*(KECIL|BESAR)", filename, re.I)
        if m:
            preset["dx"] = _re.sub(r"\s+", " ", m.group(0)).strip()
        preset["sheet"] = "A3+ Full (32.5x48.7cm)"
        preset["finishing"] = "crop"
        m = _re.search(r"1d\d+.*@\s*(\d+)\s*kecil", filename, re.I)
        if _re.search(r"1d\d+.*@\s*\d+\s*besar", filename, re.I):
            preset["repeat"] = "repeat"
        elif m:
            preset["repeat"] = f"collate-cut({m.group(1)})" if m.group(1) != "1" else "collate-cut"
        elif "booklet" in filename.lower():
            preset["repeat"] = "booklet"
        else:
            preset["repeat"] = "repeat"
        try:
            from llm_zen import parse_duplex as _pd
            preset["duplex"] = _pd(filename)
        except ImportError:
            _low2 = filename.lower()
            _stiker = any(k in _low2 for k in ("vinyl", "hologram", "gold", "silver"))
            _stiker = _stiker or (any(k in _low2 for k in ("kromo", "cromo")) and ("stiker" in _low2 or "sticker" in _low2))
            if _stiker:
                preset["duplex"] = "1s"
            else:
                _tmp = re.sub(r"(doff|dof|laminasi|laminating|glossy|gloss|matte|hologram|canvas|uv|varnish)\s*2s", " ", _low2)
                preset["duplex"] = "2s" if "2s" in _tmp else "1s"
    if not preset.get("bahan") or not preset.get("dx"):
        return None
    norm = {}
    if "sheet" in preset:
        norm["sheet"] = preset["sheet"]
    if "bahan" in preset:
        norm["bahan"] = preset["bahan"]
    if "duplex" in preset:
        _d = preset["duplex"]
        if isinstance(_d, str) and _d.lower() in ("1s", "2s", "dr"):
            norm["duplex"] = _d.lower()
        elif _d is True or str(_d).lower() in ("true", "2s"):
            norm["duplex"] = "2s"
        else:
            norm["duplex"] = "1s"
    if "dx" in preset:
        norm["dx"] = preset["dx"]
    if "finishing" in preset:
        norm["finishing"] = preset["finishing"]
    if "repeat" in preset:
        norm["repeat_mode"] = preset["repeat"]
    return norm


def _action_for(cat, preset):
    """Nilai preset -> action space train_rl. None jika tak ada."""
    if cat == "sheet" and "sheet" in preset:
        return preset["sheet"]
    elif cat == "bahan" and "bahan" in preset:
        return preset["bahan"]
    elif cat == "duplex" and "duplex" in preset:
        return _dstr(preset["duplex"])
    elif cat == "dx" and "dx" in preset:
        return preset["dx"]
    elif cat == "finishing":
        if "finishing" in preset:
            return str(preset["finishing"]).lower()
        elif preset.get("bleed_mm") == 2:
            return "bleed"
        elif preset.get("mode") == "crop":
            return "crop"
        return "crop"
    elif cat == "repeat" and "repeat_mode" in preset:
        return preset["repeat_mode"]
    return None


def auto_train(filename, rl_raw, guru_norm):
    """Tes-auto tanpa manusia, PER KATEGORI: setuju -> +1, dikoreksi ->
    benar +1 (overtake) + salah -1. Return (setuju, koreksi)."""
    setuju = koreksi = 0
    for cat in CATEGORIES:
        g = _action_for(cat, guru_norm) if cat != "repeat" else guru_norm.get("repeat_mode")
        r = _action_for(cat, rl_raw) if cat != "repeat" else rl_raw.get("repeat_mode", rl_raw.get("repeat"))
        if cat == "dx":
            g = normalize_dx(g) if g else None
            r = normalize_dx(r) if r else None
        if g is None or r is None:
            continue
        if g == r:
            train_rl(filename, g, cat, reward=1)
            setuju += 1
        else:
            train_rl(filename, g, cat, reward=1)
            train_rl(filename, r, cat, reward=-1)
            koreksi += 1
    return setuju, koreksi


def teacher_train(filename, rl_preset=None, reward=0.8, cold_cats=None):
    """LLM guru train RL saat cold-start, fallback rule jika LLM gagal.
    cold_cats: kategori yang RL-nya masih default -> jangan dihukum."""
    """LLM guru train RL saat cold-start, fallback rule jika LLM gagal"""
    try:
        norm = guru_preset_for(filename)
        if not norm:
            return None
        res = train_parallel_rl(filename, norm, reward=reward)
        # diferensial: kategori yang DIKOREKSI guru -> jawaban RL-nya dihukum ringan.
        # yang disetujui sudah ikut ter-reinforce di train di atas.
        if rl_preset:
            try:
                cold = set(cold_cats or [])
                pairs = [("sheet", "sheet", str), ("bahan", "bahan", str),
                         ("dx", "dx", normalize_dx),
                         ("repeat", "repeat_mode", str)]
                for cat, rk, fn in pairs:
                    if cat in norm and rk in rl_preset:
                        if fn(norm[cat]) != fn(rl_preset[rk]) and cat not in cold:
                            train_rl(filename, fn(rl_preset[rk]), cat, reward=-0.5)
                if "duplex" in norm and "duplex" in rl_preset:
                    if _dstr(norm["duplex"]) != _dstr(rl_preset["duplex"]) and "duplex" not in cold:
                        train_rl(filename, _dstr(rl_preset["duplex"]), "duplex", reward=-0.5)
                if "finishing" in norm:
                    if _fstr({"finishing": norm["finishing"]}) != _fstr(rl_preset) and "finishing" not in cold:
                        train_rl(filename, _fstr(rl_preset), "finishing", reward=-0.5)
            except Exception as e:
                print(f"[Guru] diferensial gagal: {e}")
        return res
    except Exception as e:
        print(f"[Guru] gagal: {e}")
        return None

def train_parallel_rl(filename, corrected_preset, reward=1):
    import concurrent.futures
    def task(cat):
        val = _action_for(cat, corrected_preset)
        if val is None:
            return cat, None
        res = train_rl(filename, val, cat, reward=reward)
        return cat, res
    cats=CATEGORIES
    results={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(task, cat): cat for cat in cats}
        for fut in concurrent.futures.as_completed(futs):
            cat, res = fut.result()
            if res: results[cat]=res
    return results

AMBIG_GAP = 0.05  # selisih Q top-2 di bawah ini = ambigu

VALID_PATH = BASE / "data" / "validasi.json"  # state -> jumlah validasi manusia
VALID_MIN_AUTO = 2  # syarat AUTO: divalidasi manusia minimal ini


def _load_valid():
    try:
        d = json.loads(VALID_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def catat_validasi(filename):
    """Catat satu penilaian manusia (Enter/koreksi/adjudikasi)."""
    state = _key_str(_state_key(filename))
    try:
        d = _load_valid()
        d[state] = int(d.get(state, 0)) + 1
        VALID_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[E023] Validasi gagal dicatat: {e}")
    return state


def validasi_count(filename):
    return int(_load_valid().get(_key_str(_state_key(filename)), 0))

def state_maturity(filename):
    """Fase 1: (is_new, is_ambig, min_gap) untuk keputusan AUTO."""
    state = _key_str(_state_key(filename))
    is_new, is_ambig = False, False
    min_gap = 1.0
    for cat in CATEGORIES:
        acts = _load_q(cat).get(state, {})
        if not acts:
            is_new = True
            continue
        vals = sorted(acts.values(), reverse=True)
        if len(vals) > 1:
            gap = vals[0] - vals[1]
            min_gap = min(min_gap, gap)
            if gap < AMBIG_GAP:
                is_ambig = True
    return is_new, is_ambig, round(min_gap, 3)
