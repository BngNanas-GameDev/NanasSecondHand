"""NSH Lite: seperti NSH utama, TANPA Q-learning table.

Alur per file: cek skip -> parse guru -> impose -> pindah ke uda.
Preset 100% dari aturan guru (tidak belajar, tidak bertanya).
Pakai: python lite.py "<nama file>" [file ...] | --dir "<folder>"
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from llm_zen import llm_teacher_preset, skip_reason, ringkas

_SKIPPED = set()       # sudah di-skip permanen (skip_reason 1x atau gagal 3x)
_COOLDOWN = {}  # nama file -> timestamp gagal terakhir
_FAIL_COUNT = {}  # nama file -> jumlah gagal berturut (diluar cooldown)
_SEEN = {}  # path.lower() -> timestamp pertama kali terlihat (cooldown sebelum impose)
COOLDOWN_S = 5
COOLDOWN_BEFORE = 5  # tunggu 5 detik setelah file muncul baru impose
MAX_FAIL = 3
# E030=locked percobaan, E031=tidak bisa ditarik (3x locked), E032=gagal impose 3x (bukan locked)


def normalize_dx(v):
    m = re.search(r"1d\s*(\d+)\s*(?:[=:@]\s*)?@?\s*(\d[\d.]*)?\s*(kecil|besar)?",
                  str(v), re.I)
    if not m:
        return str(v).strip()
    s = f"1d{m.group(1)}"
    if m.group(2):
        s += f" = {m.group(2).replace('.', '')}"
    if m.group(3):
        s += f" {m.group(3).upper()}"
    return s


def preset_for(filename):
    p = llm_teacher_preset(filename) or {}
    if p.get("dx"):
        p["dx"] = normalize_dx(p["dx"])
    return p


def to_bridge(preset, filename):
    """Preset guru -> format imposition_bridge."""
    b = dict(preset)
    b["repeat_mode"] = preset.get("repeat", "repeat")
    if preset.get("finishing") == "bleed":
        b.update({"mode": "crop", "bleed_mm": 2, "inner_crop": False,
                  "mark_len_mm": 5, "bleed_on": True, "line_color": "gray"})
    else:
        b.update({"mode": "crop", "bleed_mm": 0, "inner_crop": True,
                  "mark_len_mm": 5, "bleed_on": True, "line_color": "gray"})
    b["label"] = filename
    return b


G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; D = "\033[90m"; RST = "\033[0m"
USE_COLOR = sys.stdout.isatty()


def _log(color, tag, msg, detail=""):
    c = color if USE_COLOR else ""
    r = RST if USE_COLOR else ""
    d = f" {D}{detail}{R}" if detail else ""
    print(f"{c}{tag}{r} {msg}{d}")


def process_one(fn, bridge, outdir, udadir):
    """Proses satu file. Return True jika di-impose."""
    import time as _time
    name = Path(fn).name
    if name in _SKIPPED:
        return False
    sk = skip_reason(name)
    if sk:
        if name not in _SKIPPED:
            _log(Y, "[SKIP]", name, f"-> {sk} {D}(sekali, tidak spam){RST if USE_COLOR else ''}")
            _SKIPPED.add(name)
        return False
    p = preset_for(name)
    rk = ringkas(name)
    rec = {"file": name, "ringkas": rk, "preset": p}
    # file sudah hilang di disk (duplikat glob / dipindah manual) -> diam, bukan error
    if not Path(fn).exists():
        return False
    try:
        dst = outdir / name
        import io as _io
        from contextlib import redirect_stdout
        _buf = _io.StringIO()
        with redirect_stdout(_buf):
            bridge(fn, str(dst), to_bridge(p, name))
        target = udadir / name
        if target.exists():
            target = udadir / f"{Path(name).stem}_{int(_time.time())}{Path(name).suffix}"
        try:
            Path(fn).rename(target)
        except FileNotFoundError:
            pass  # sudah dipindah di iterasi sebelumnya (duplikat)
        rec["impose"] = str(dst)
        rec["uda"] = str(target)
        _log(G, "[ OK ]", name, f"| {rk} -> {dst.name} -> uda/")
        _COOLDOWN.pop(name, None)
        _FAIL_COUNT.pop(name, None)
        return True
    except Exception as e:
        now = _time.time()
        if now - _COOLDOWN.get(name, 0) < COOLDOWN_S:
            return False
        _COOLDOWN[name] = now
        cnt = _FAIL_COUNT.get(name, 0) + 1
        _FAIL_COUNT[name] = cnt
        ename = type(e).__name__
        emsg_low = str(e).lower()
        # file sudah dipindah (duplikat glob *.pdf + *.PDF di Windows) -> diam, bukan error
        if ename == "FileNotFoundError" or "no such file" in emsg_low or "tidak ditemukan" in emsg_low or getattr(e, "code", "") == "E010":
            _FAIL_COUNT.pop(name, None)
            return False
        code = "E008"
        err_msg = str(e)[:100].strip() or ename
        is_locked = ename == "PermissionError" or "denied" in emsg_low or "locked" in emsg_low or "being used by another" in emsg_low
        if is_locked:
            code = "E030"
            err_msg = "File dibuka/locked oleh program lain"
        elif "corrupt" in emsg_low or "pdf" in emsg_low and "error" in emsg_low:
            err_msg = f"PDF error: {str(e)[:80]}"
            code = "E008"
        rec["impose_error"] = f"[{code}] {err_msg} ({cnt}/{MAX_FAIL})"
        if cnt >= MAX_FAIL:
            if code == "E030":
                final_code = "E031"
                reason = "tidak bisa ditarik"
            else:
                final_code = "E032"
                reason = "gagal impose"
            rec["impose_error"] = f"[{final_code}] {reason} ({name}) - {err_msg}"
            rec["skip"] = f"{reason} [{final_code}]"
            try:
                log_file = Path(fn).parent / f"Tidak Bisa Ditarik ({name}).txt"
                log_file.write_text(f"tidak bisa ditarik ({name})\n[{final_code}] {err_msg}\n", encoding="utf-8")
                rec["txt"] = str(log_file)
            except Exception:
                log_file = None
            _log(R, f"[{final_code} SKIP]", f'tidak bisa ditarik ({name})', f"{err_msg} -> {log_file.name if log_file else 'txt gagal'} (di folder Input)")
            _SKIPPED.add(name)
            _FAIL_COUNT.pop(name, None)
            return False
        _log(Y if code == "E030" else R, f"[{code} {cnt}/{MAX_FAIL}]", name, err_msg)
        return False


def load_cfg():
    p = BASE / "lite.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cfg(cfg):
    (BASE / "lite.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                                    encoding="utf-8")


def ask_folders():
    cfg = load_cfg()
    ind = Path(cfg.get("input_folder", str(BASE / "input")))
    outd = Path(cfg.get("output_folder", str(BASE / "impose")))
    udad = Path(cfg.get("uda_folder", str(BASE / "uda")))
    print("=" * 60)
    print(" NSH Lite - Setup Folder")
    print("=" * 60)
    print(f"Folder Input saat ini : {ind}")
    print(f"Folder Output saat ini: {outd}")
    print(f"Folder Uda saat ini   : {udad}")
    print("")
    try:
        a = input("Folder INPUT? Copas path (Enter=tetap): ").strip().strip('"').strip("'")
        if a:
            ind = Path(a)
            cfg["input_folder"] = str(ind)
        b = input("Folder OUTPUT? Copas path (Enter=tetap): ").strip().strip('"').strip("'")
        if b:
            outd = Path(b)
            cfg["output_folder"] = str(outd)
        c = input("Folder UDA? Copas path (Enter=tetap): ").strip().strip('"').strip("'")
        if c:
            udad = Path(c)
            cfg["uda_folder"] = str(udad)
        save_cfg(cfg)
    except (EOFError, KeyboardInterrupt):
        print("\nSetup dibatalkan.")
    return ind, outd, udad


def watch_loop():
    """Mode watcher seperti run.bat NSH utama: pantau folder input selamanya."""
    import time as _time
    sys.path.insert(0, str(Path(r"C:\Users\ID2\Documents\VSCODE\Agent\Nanas Second Hand\scripts")))
    from imposition_bridge import impose_file
    indir, outdir, udadir = ask_folders()
    for d in (indir, outdir, udadir):
        d.mkdir(exist_ok=True)
    print(f"{C}NSH Lite watcher{RST}")
    print(f"  Input : {indir}")
    print(f"  Output: {outdir}")
    print(f"  Uda   : {udadir}")
    print(f"  Legenda: {G}[ OK ] berhasil{RST}  {Y}[SKIP] di-skip{RST}  {R}[E030/E031/E032] error{RST}")
    print(f"  Ctrl+C untuk stop\n")
    try:
        while True:
            seen = {}
            for f in list(indir.glob("*.pdf")) + list(indir.glob("*.PDF")):
                seen[str(f).lower()] = f
            # hapus entri file yang sudah hilang
            for k in list(_SEEN.keys()):
                if k not in seen:
                    _SEEN.pop(k, None)
            now = _time.time()
            n = 0
            for key, f in seen.items():
                first = _SEEN.get(key)
                if first is None:
                    _SEEN[key] = now
                    continue  # baru muncul, tunggu COOLDOWN_BEFORE
                if now - first < COOLDOWN_BEFORE:
                    continue  # masih cooldown sebelum impose
                # cek file masih ditulis (size/mtime berubah) -> reset timer
                try:
                    mt = f.stat().st_mtime
                    if now - mt < COOLDOWN_BEFORE:
                        _SEEN[key] = now
                        continue
                except Exception:
                    continue
                if process_one(str(f), impose_file, outdir, udadir):
                    n += 1
                    _SEEN.pop(key, None)
            if n:
                print(f"{D}--- {n} file selesai ---{RST}")
            _time.sleep(1)
    except KeyboardInterrupt:
        print("\nStop watcher")


def main():
    args = sys.argv[1:]
    do_impose = "--impose" in args
    args = [a for a in args if a != "--impose"]
    if not args:
        watch_loop()
        return
    bridge = None
    if do_impose:
        sys.path.insert(0, str(Path(r"C:\Users\ID2\Documents\VSCODE\Agent\Nanas Second Hand\scripts")))
        from imposition_bridge import impose_file
        bridge = impose_file
    names = []
    if args[0] == "--dir" and len(args) > 1:
        d = Path(args[1])
        names = [str(f) for f in list(d.glob("*.pdf")) + list(d.glob("*.PDF"))]
    else:
        names = args
    outdir = BASE / "impose"
    udadir = BASE / "uda"
    if do_impose:
        outdir.mkdir(exist_ok=True)
        udadir.mkdir(exist_ok=True)
    for fn in names:
        if do_impose and bridge:
            process_one(fn, bridge, outdir, udadir)
            continue
        name = Path(fn).name
        sk = skip_reason(name)
        if sk:
            _log(Y, "[SKIP]", name, f"-> {sk}")
            continue
        p = preset_for(name)
        _log(C, "[PREVIEW]", name, f"| {ringkas(name)} | {p}")


if __name__ == "__main__":
    main()
