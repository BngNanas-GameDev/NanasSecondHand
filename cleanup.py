"""The Cleanup Team: bersihkan Q-table kotor.

Pakai: python cleanup.py          -> cek saja (dry-run)
       python cleanup.py --fix    -> bersihkan + simpan
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent
DATA_DIR = BASE / "data" / "memory_rl"

BAD_BAHAN = {"repeat", "repeat repeat", "salah"}


def _load(cat):
    p = DATA_DIR / f"{cat}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _save(cat, data):
    (DATA_DIR / f"{cat}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clean_duplex(q):
    """Merge True->2s, False->1s (ambil Q tertinggi). Return jumlah state diubah."""
    n = 0
    for acts in q.values():
        changed = False
        if "True" in acts:
            acts["2s"] = max(acts.get("2s", float("-inf")), acts.pop("True"))
            changed = True
        if "False" in acts:
            acts["1s"] = max(acts.get("1s", float("-inf")), acts.pop("False"))
            changed = True
        if changed:
            n += 1
    return n


def clean_bahan(q):
    """Hapus action nyasar (repeat/salah). Return (action dihapus, state kosong dibuang)."""
    n_del, n_state = 0, 0
    for st in list(q.keys()):
        for b in list(q[st].keys()):
            if b.strip().lower() in BAD_BAHAN:
                del q[st][b]
                n_del += 1
        if not q[st]:
            del q[st]
            n_state += 1
    return n_del, n_state


def clean_dx(q):
    """Hapus '-' jika key mengandung 1d atau ada dx asli + merge varian format. Return (tanda dihapus, state dibuang)."""
    try:
        from preset_learner_rl import normalize_dx
    except ImportError:
        normalize_dx = lambda v: v
    n_del, n_state = 0, 0
    for st in list(q.keys()):
        acts = q[st]
        merged = {}
        for k, v in acts.items():
            nk = normalize_dx(k)
            if nk != k:
                n_del += 1
            merged[nk] = max(merged.get(nk, float("-inf")), v)
        q[st] = merged
        acts = merged
        real = [k for k in acts if k.strip() not in ("-", "")]
        if "-" in acts and (re.search(r"1d\d+", st) or real):
            del acts["-"]
            n_del += 1
        if not acts:
            del q[st]
            n_state += 1
    return n_del, n_state


def main():
    fix = "--fix" in sys.argv
    mode = "FIX" if fix else "DRY-RUN"

    duplex = _load("duplex")
    bahan = _load("bahan")
    dx = _load("dx")

    # hitung di salinan dulu kalau dry-run
    import copy
    d_dup, d_bah, d_dx = copy.deepcopy(duplex), copy.deepcopy(bahan), copy.deepcopy(dx)
    n_dup = clean_duplex(d_dup)
    n_bah, n_bah_st = clean_bahan(d_bah)
    n_dx, n_dx_st = clean_dx(d_dx)

    print(f"[Cleanup Team] mode={mode}")
    print(f"  duplex: {n_dup} state perlu merge True/False")
    print(f"  bahan : {n_bah} action nyasar, {n_bah_st} state kosong")
    print(f"  dx    : {n_dx} tanda '-' bermasalah, {n_dx_st} state kosong")

    if fix:
        _save("duplex", d_dup)
        _save("bahan", d_bah)
        _save("dx", d_dx)
        print("[Cleanup Team] tersimpan. Q-table bersih.")
    else:
        print("[Cleanup Team] tambah --fix untuk eksekusi.")


if __name__ == "__main__":
    main()
