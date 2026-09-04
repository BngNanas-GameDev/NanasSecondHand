"""Tool khusus penyelesaian state ambigu.

Menampilkan tiap state ambigu + contoh file + dua jawaban bersaing,
kamu tunjuk pemenang: [A]/[B] menang, [C] keduanya benar (tak terputus),
[Enter] lewati. Pemenang dilatih reward=1 (langsung overtake).
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import preset_learner_rl as rl

DATA = BASE / "data" / "memory_rl"
UNRES_PATH = BASE / "data" / "unresolvable.json"
CATS = ["sheet", "bahan", "duplex", "dx", "finishing", "repeat"]


def load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def find_ambiguous():
    out = []
    for cat in CATS:
        q = load_json(DATA / f"{cat}.json")
        for st, acts in q.items():
            vals = sorted(acts.values(), reverse=True)
            if len(vals) > 1 and vals[0] - vals[1] < rl.AMBIG_GAP:
                top = sorted(acts.items(), key=lambda x: -x[1])[:2]
                out.append((cat, st, top[0], top[1]))
    return out


def load_unres():
    d = load_json(UNRES_PATH)
    return {c: set(v) for c, v in d.items()} if isinstance(d, dict) else {}


def save_unres(d):
    UNRES_PATH.write_text(json.dumps({c: sorted(v) for c, v in d.items()},
                                     ensure_ascii=False, indent=2), encoding="utf-8")


def example_files(state, folders, limit=3):
    out, seen = [], set()
    for folder in folders:
        if not folder or not folder.exists():
            continue
        for f in list(folder.glob("*.pdf")) + list(folder.glob("*.PDF")):
            try:
                if f.name not in seen and rl._key_str(rl._state_key(f.name)) == state:
                    seen.add(f.name)
                    out.append(f.name)
                    if len(out) >= limit:
                        return out
            except Exception:
                pass
    return out


def main():
    cfg = load_json(BASE / "config.json")
    folders = [Path(cfg.get("input_folder", "input")),
               Path(cfg.get("output_folder", "impose")),
               Path(cfg.get("uda_folder", "uda"))]
    unres = load_unres()
    items = [(c, s, a, b) for c, s, a, b in find_ambiguous()
             if s not in unres.get(c, set())]
    if not items:
        print("Tidak ada state ambigu yang perlu diputus.")
        return
    print(f"{len(items)} state ambigu. A/B=menangkan, C=keduanya benar, Enter=lewati\n")
    done = {"A/B": 0, "C": 0, "skip": 0}
    for i, (cat, st, a, b) in enumerate(items, 1):
        print(f"[{i}/{len(items)}] {cat} | {st}")
        print(f"  A: {a[0]} (Q={a[1]})")
        print(f"  B: {b[0]} (Q={b[1]})")
        ex = example_files(st, folders)
        print(f"  contoh file: {', '.join(ex) if ex else '- (tidak ketemu)'}")
        try:
            ans = input("  putus? [A/B/C/Enter]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nBerhenti.")
            break
        if ans == "a":
            if not ex:
                print("  -> butuh contoh file, dilewati"); done["skip"] += 1; continue
            rl.train_rl(ex[0], a[0], cat, reward=1)
            print(f"  -> {a[0]} menang"); done["A/B"] += 1
        elif ans == "b":
            if not ex:
                print("  -> butuh contoh file, dilewati"); done["skip"] += 1; continue
            rl.train_rl(ex[0], b[0], cat, reward=1)
            print(f"  -> {b[0]} menang"); done["A/B"] += 1
        elif ans == "c":
            unres.setdefault(cat, set()).add(st)
            print("  -> ditandai tak-terputus (struktural)"); done["C"] += 1
        else:
            done["skip"] += 1
    save_unres(unres)
    print(f"\nSelesai: {done['A/B']} diputus, {done['C']} struktural, {done['skip']} dilewati")


if __name__ == "__main__":
    main()
