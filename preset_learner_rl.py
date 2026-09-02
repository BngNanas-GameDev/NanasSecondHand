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

def _finishing_to_preset(v):
    if isinstance(v, dict): return v
    return FINISH_MAP.get(str(v).lower().strip(), {"mode":"crop","bleed_mm":0,"inner_crop":False,"mark_len_mm":5,"bleed_on":True} if str(v).lower()=="crop" else {})

def _normalize(s):
    return re.sub(r'[^a-z0-9]+',' ', s.lower()).strip()

def _state_key(filename):
    tmp = re.sub(r"^[^_]+_DITUNGGU_+", "", filename, flags=re.I)
    tmp = re.sub(r"^[^_]+_TUNGGU_+", "", tmp, flags=re.I)
    tmp = re.sub(r"\(A\d+L[^)]*\)", " ", tmp, flags=re.I)
    tmp = re.sub(r"ON\d+", " ", tmp, flags=re.I)
    fn = _normalize(tmp)
    words=[]
    for w in fn.split():
        if len(w)<3: continue
        if w in ("pdf","dan","untuk","lembar","ditunggu","tunggu"): continue
        if re.match(r"^[a-z]+\d+$", w): continue
        if re.match(r"^a\d+l$", w): continue
        if re.match(r"^on\d+$", w): continue
        words.append(w)
        if len(words)>=4: break
    m_uk = re.search(r"\d+x\d+mm", filename.lower())
    if m_uk and m_uk.group(0) not in words:
        words.append(m_uk.group(0))
    m_dx = re.search(r"1d\d+", filename.lower())
    if m_dx and m_dx.group(0) not in words:
        words.append(m_dx.group(0))
    return frozenset(words[:5])

def _key_str(state):
    return "|".join(sorted(state))

def _load_q(cat):
    p = DATA_DIR / f"{cat}.json"
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: return {}
    return {}

def _save_q(cat, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{cat}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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
    old_q = q_table[state].get(action_key, 0)
    new_q = old_q + ALPHA * (reward - old_q)
    # jika koreksi (reward 1) dan masih kalah dari best lain, paksa overtake biar koreksi langsung muncul
    if reward==1:
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
    """Aturan: @xKecil → collate-cut, + BOOKLET/Staples tengah → booklet varian"""
    is_booklet = "booklet" in filename.lower() or "staples tengah" in filename.lower() or "staples" in filename.lower()
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
        elif cat=="duplex": preset["duplex"]=v
        elif cat=="dx": preset["dx"]=v
        elif cat=="sheet": preset["sheet"]=v
        elif cat=="bahan": preset["bahan"]=v
        elif cat=="repeat": preset["repeat_mode"]=_dx_repeat_rule(filename, v)
        conf_avg+=c
    conf_avg/=len(cats)
    return preset, conf_avg, results

def teacher_train(filename, reward=0.8):
    """LLM guru train RL saat cold-start, fallback rule jika LLM gagal"""
    try:
        from llm_zen import llm_teacher_preset
        preset = llm_teacher_preset(filename)
        if not preset:
            # fallback rule tanpa LLM: kromo/vinyl/ac..gr + 1d..
            import re as _re
            preset={}
            if _re.search(r"ac\d+gr", filename, re.I): preset["bahan"]=_re.search(r"ac\d+gr", filename, re.I).group(0).capitalize()
            elif "kromo" in filename.lower(): preset["bahan"]="Kromo"
            elif "vinyl" in filename.lower(): preset["bahan"]="Vinyl"
            m=_re.search(r"1d\d+\s*[=:@]*\s*\d*\s*KECIL", filename, re.I)
            if m: preset["dx"]=_re.sub(r"\s+"," ", m.group(0)).strip()
            # sheet default, finishing crop
            preset["sheet"]="A3+ Full (32.5x48.7cm)"; preset["finishing"]="crop"
            m=_re.search(r"1d\d+.*@\s*(\d+)\s*kecil", filename, re.I)
            if m: preset["repeat"]=f"collate-cut({m.group(1)})" if m.group(1)!="1" else "collate-cut"
            elif "booklet" in filename.lower(): preset["repeat"]="booklet"
            else: preset["repeat"]="repeat"
            # duplex dari 1s/2s
            if "2s" in filename.lower(): preset["duplex"]="2s"
            else: preset["duplex"]="1s"
            if not preset.get("bahan") or not preset.get("dx"): return None
        norm={}
        if "sheet" in preset: norm["sheet"]=preset["sheet"]
        if "bahan" in preset: norm["bahan"]=preset["bahan"]
        if "duplex" in preset: norm["duplex"]=preset["duplex"]=="2s" if isinstance(preset["duplex"], str) else bool(preset["duplex"])
        if "dx" in preset: norm["dx"]=preset["dx"]
        if "finishing" in preset: norm["finishing"]=preset["finishing"]
        if "repeat" in preset: norm["repeat_mode"]=preset["repeat"]
        return train_parallel_rl(filename, norm, reward=reward)
    except Exception as e:
        print(f"[Guru] gagal: {e}")
        return None

def train_parallel_rl(filename, corrected_preset, reward=1):
    import concurrent.futures
    def task(cat):
        val=None
        if cat=="sheet" and "sheet" in corrected_preset: val=corrected_preset["sheet"]
        elif cat=="bahan" and "bahan" in corrected_preset: val=corrected_preset["bahan"]
        elif cat=="duplex" and "duplex" in corrected_preset: val=str(corrected_preset["duplex"])
        elif cat=="dx" and "dx" in corrected_preset: val=corrected_preset["dx"]
        elif cat=="finishing":
            if "finishing" in corrected_preset: val=str(corrected_preset["finishing"]).lower()
            elif corrected_preset.get("bleed_mm")==2: val="bleed"
            elif corrected_preset.get("mode")=="crop": val="crop"
            else: val="crop"
        elif cat=="repeat" and "repeat_mode" in corrected_preset: val=corrected_preset["repeat_mode"]
        else: return cat, None
        res=train_rl(filename, val, cat, reward=reward)
        return cat, res
    cats=CATEGORIES
    results={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(task, cat): cat for cat in cats}
        for fut in concurrent.futures.as_completed(futs):
            cat, res = fut.result()
            if res: results[cat]=res
    return results
