"""Seed Q-table dari filename sintetis Rust (base idempoten).

- Sumber: rs_sidecar.exe --generate N (master-list, deterministik)
- Guru: llm_teacher_preset (murni aturan, tanpa LLM)
- Aturan: hanya isi action yang BELUM ada (Q=0.3 flat, di bawah ambang AUTO).
  Tidak pernah menyentuh pengetahuan yang sudah ada.
Pakai: python seed.py [N=3000]
"""
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from preset_learner_rl import _state_key, _key_str, normalize_dx, CATEGORIES
from llm_zen import llm_teacher_preset


def norm(preset):
    n = {}
    if "sheet" in preset:
        n["sheet"] = preset["sheet"]
    if "bahan" in preset:
        n["bahan"] = preset["bahan"]
    if "duplex" in preset:
        d = preset["duplex"]
        if isinstance(d, str) and d.lower() in ("1s", "2s", "dr"):
            n["duplex"] = d.lower()
        elif d is True or str(d).lower() in ("true", "2s"):
            n["duplex"] = "2s"
        else:
            n["duplex"] = "1s"
    if "dx" in preset:
        n["dx"] = preset["dx"]
    if "finishing" in preset:
        n["finishing"] = preset["finishing"]
    if "repeat" in preset:
        n["repeat_mode"] = preset["repeat"]
    return n


def val_for(cat, np):
    if cat == "sheet" and "sheet" in np:
        return np["sheet"]
    elif cat == "bahan" and "bahan" in np:
        return np["bahan"]
    elif cat == "duplex" and "duplex" in np:
        d = np["duplex"]
        if d is True or str(d).lower() in ("true", "2s"):
            return "2s"
        elif d is False or str(d).lower() in ("false", "1s"):
            return "1s"
        elif str(d).lower() == "dr":
            return "dr"
        return str(d)
    elif cat == "dx" and "dx" in np:
        return normalize_dx(np["dx"])
    elif cat == "finishing":
        if "finishing" in np:
            return str(np["finishing"]).lower()
        elif np.get("bleed_mm") == 2:
            return "bleed"
        elif np.get("mode") == "crop":
            return "crop"
        return "crop"
    elif cat == "repeat" and "repeat_mode" in np:
        return np["repeat_mode"]
    return None


def feed_names(names, tables):
    """Seed idempoten: hanya isi action yang BELUM ada (Q=0.3 flat).
    Tidak pernah menyentuh pengetahuan yang sudah ada."""
    fed, skip = 0, 0
    for fn in names:
        preset = llm_teacher_preset(fn)
        if not preset.get("bahan") or not preset.get("dx"):
            skip += 1
            continue
        np = norm(preset)
        st = _key_str(_state_key(fn))
        for c in CATEGORIES:
            v = val_for(c, np)
            if v is None:
                continue
            acts = tables[c].setdefault(st, {})
            if str(v) not in acts:
                acts[str(v)] = 0.3
                fed += 1
    return fed, skip


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    r = subprocess.run([str(BASE / "rs_sidecar.exe"), "--generate", str(n)],
                       capture_output=True, text=True)
    names = [line for line in r.stdout.splitlines() if line.strip()]
    tables = {}
    for c in CATEGORIES:
        p = BASE / "data" / "memory_rl" / f"{c}.json"
        tables[c] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    fed, skip = feed_names(names, tables)
    for c in CATEGORIES:
        (BASE / "data" / "memory_rl" / f"{c}.json").write_text(
            json.dumps(tables[c], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"fed: {fed}, skip: {skip}")
    print("states:", {c: len(tables[c]) for c in CATEGORIES})


if __name__ == "__main__":
    main()
