"""WMA — Watcher Module Auto. Jembatan file-routing <-> Watcher Dashboard.

- Nama file WMA = nama file dashboard (tanpa rename, match persis).
- Mesin diisi dari tujuan routing (DEVELOP/RICOH/...), operator per sesi.
- Dashboard API: GET /api/files, POST /api/files/{id}, GET /api/config.
- Pakai: wma.bat (sesi) | python wma.py --check "<file>" | --report ...
"""
import datetime
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
CFG_PATH = BASE / "wma.json"

DASH_URL = "http://192.168.5.54:5000"
OPERATORS = ("Nanas", "Eric", "Rahmadi")  # ejaan persis dashboard
OPERATOR_KEYS = {"1": 0, "2": 1, "3": 2}
WMA_VERSION = "19d"

_PENDING = {}  # nama-lower -> {name, label, seen} (tetap dicocokkan walau file pergi)
PENDING_TTL_S = 48 * 3600


def load_cfg():
    try:
        return json.loads(CFG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cfg(cfg):
    CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _get(path):
    with urllib.request.urlopen(DASH_URL + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(path, payload):
    req = urllib.request.Request(
        DASH_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def ask_operator():
    """Operator sesi: 1.NANAS 2.ERIC 3.RAHMADI (Enter = terakhir)."""
    cfg = load_cfg()
    last = cfg.get("operator", OPERATORS[0])
    print(f"  Operator sesi ini?  [1] NANAS  [2] ERIC  [3] RAHMADI  (Enter={last})")
    try:
        a = input("  Pilih [1/2/3]: ").strip()
        if a in ("1", "2", "3"):
            op = OPERATORS[int(a) - 1]
        elif (a or "").capitalize() in OPERATORS:
            op = a.capitalize()
        else:
            op = last if last in OPERATORS else OPERATORS[0]
    except (EOFError, KeyboardInterrupt):
        op = last if last in OPERATORS else OPERATORS[0]
        print()
    cfg["operator"] = op
    save_cfg(cfg)
    print(f"  operator: {op}\n")
    return op


def _strip_ipy(name):
    """Buang suffix -ipy/-IPY dari nama file (imposition output)."""
    lo = name.lower()
    if lo.endswith("-ipy.pdf"):
        return name[:-8] + ".pdf"
    return name


def find_file_id(filename, days_back=1):
    """Cari id dashboard by nama file (abai -ipy suffix). Return (id, row) atau (None, None)."""
    today = datetime.date.today()
    search = _strip_ipy(filename)
    for d in range(days_back + 1):
        day = (today - datetime.timedelta(days=d)).isoformat()
        try:
            rows = _get(f"/api/files?date_from={day}&date_to={day}")
        except Exception as e:
            return None, f"dashboard tak terjangkau: {e}"
        for row in rows:
            fn = _strip_ipy(row.get("filename") or "")
            if fn == search:
                return row.get("id"), row
    return None, None


def report(filename, machine, operator=None):
    """Isi mesin + operator + status done untuk satu nama file.
    Return (True, id) atau (False, alasan)."""
    cfg = load_cfg()
    op = operator or cfg.get("operator") or OPERATORS[0]
    fid, row = find_file_id(filename)
    if not fid:
        return False, f"{filename} tidak ada di dashboard ({row or 'tidak ketemu'})"
    if isinstance(row, dict) and row.get("machine_name") and row.get("operator"):
        return False, f"sudah terisi ({row.get('machine_name')}/{row.get('operator')})"
    try:
        _post(f"/api/files/{fid}", {"machine_name": machine, "operator": op, "status": "done"})
    except Exception as e:
        return False, f"POST gagal: {e}"
    return True, fid


_WAKE = threading.Event()


def _dir_watcher(path):
    """Thread event: bangun saat ada aksi file (tanpa polling)."""
    import ctypes
    try:
        k32 = ctypes.windll.kernel32
        h = k32.CreateFileW(str(path), 0x0001, 0x00000001 | 0x00000002 | 0x00000004,
                            None, 3, 0x02000000, None)
        if h == -1:
            return
        from ctypes import wintypes
        buf = ctypes.create_string_buffer(4096)
        nbytes = wintypes.DWORD()
        while True:
            if k32.ReadDirectoryChangesW(h, buf, 4096, False, 0x00000003,
                                         ctypes.byref(nbytes), None, None):
                _WAKE.set()
            else:
                break
        k32.CloseHandle(h)
    except Exception:
        return
    finally:
        _WAKE.set()


def konica_machine():
    """Mesin Konica aktif: 157 -> Develop 1, 158 -> Develop 2.
    Return None jika dua-duanya tak siap."""
    import socket
    for ip, name in (("192.168.10.157", "Develop 1"),
                     ("192.168.10.158", "Develop 2")):
        try:
            s = socket.create_connection((ip, 445), timeout=3)
            s.close()
        except OSError:
            continue
        for share in ("ST_GLOSS_1S", "ST_GLOSSY_1S"):
            try:
                os.listdir(f"\\\\{ip}\\{share}")
                return name
            except OSError:
                continue
    return None


def dashboard_counts():
    """Hitungan hari ini dari Watcher: (total, pending, selesai, verified)."""
    today = datetime.date.today().isoformat()
    rows = _get(f"/api/files?date_from={today}&date_to={today}")
    total = len(rows)
    pending = sum(1 for r in rows if r.get("status") == "pending")
    done = [r for r in rows if r.get("status") == "done"]
    verified = sum(1 for r in done if r.get("verified"))
    return total, pending, len(done), verified


def ask_folders():
    """Folder INPUT awal: DEVELOP + RICOH + UDA (Enter = tersimpan).
    UDA dipantau untuk file yang sudah dipindah KMA tapi belum terisi mesin+operator."""
    cfg = load_cfg()
    folders = cfg.get("folders", {})
    print("  Folder INPUT awal (Enter = tersimpan):")
    try:
        a = input(f"  DEVELOP? [{folders.get('DEVELOP', '')}]: ").strip().strip('"').strip("'")
        if a:
            folders["DEVELOP"] = a
        b = input(f"  RICOH?   [{folders.get('RICOH', '')}]: ").strip().strip('"').strip("'")
        if b:
            folders["RICOH"] = b
        dev = folders.get("DEVELOP", "")
        uda_default = folders.get("UDA") or (str(Path(dev).parent / "Uda") if dev else "")
        c = input(f"  UDA?     [{uda_default}]: ").strip().strip('"').strip("'")
        folders["UDA"] = c or uda_default
    except (EOFError, KeyboardInterrupt):
        print()
    folders = {k: v for k, v in folders.items() if v and Path(v).exists()}
    if not folders:
        print("  tidak ada folder valid — isi dulu.")
        raise SystemExit(1)
    cfg["folders"] = folders
    if "machine_map" not in cfg:
        cfg["machine_map"] = {"DEVELOP": "Develop 1", "RICOH": "Ricoh", "UDA": "Develop 1"}
    cfg["machine_map"].setdefault("UDA", "Develop 1")
    save_cfg(cfg)
    return folders, cfg.get("machine_map", {})


def ask_key():
    """1/2/3 tanpa Enter (q = lewati batch)."""
    import msvcrt
    print("  Siapa yang cetak? [1] NANAS [2] ERIC [3] RAHMADI (q=lewati, tanpa Enter)")
    while True:
        try:
            ch = msvcrt.getch().decode().lower()
        except Exception:
            continue
        if ch in OPERATOR_KEYS:
            return OPERATORS[OPERATOR_KEYS[ch]]
        if ch in ("q", "\x1b"):
            return None


import concurrent.futures as _cf

_MATCH_POOL = _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="wma-match")
_MATCH_FUTS = {}  # nama-lower -> Future[(fid, row)]
_UNMATCHED_QUIET = {}  # nama file -> timestamp log terakhir
UNMATCHED_QUIET_S = 120


def scan_new(folders):
    """Discovery + pencocokan asinkron.
    File baru disubmit ke thread pool DAN hasilnya langsung dicek
    di siklus yang sama (blocking jika belum selesai, max 3 dtk).
    Return [(nama, label)]."""
    batch, seen = [], set()
    now = time.time()
    for label, folder in folders.items():
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for n in names:
            lo = n.lower()
            if not lo.endswith(".pdf") or lo in seen:
                continue
            seen.add(lo)
            key = lo
            if key not in _PENDING:
                _PENDING[key] = {"name": n, "label": label, "seen": now}
                _MATCH_FUTS[key] = _MATCH_POOL.submit(_match_one, key, n)
    # kumpulkan hasil pencocokan asinkron
    for key in list(_PENDING):
        e = _PENDING[key]
        if now - e["seen"] > PENDING_TTL_S:
            del _PENDING[key]
            _MATCH_FUTS.pop(key, None)
            continue
        fut = _MATCH_FUTS.get(key)
        if fut is None:
            _MATCH_FUTS[key] = _MATCH_POOL.submit(_match_one, key, e["name"])
            fut = _MATCH_FUTS[key]
        # file baru: tunggu hasil (max 3 dtk); file lama: skip kalau belum selesai
        if not fut.done():
            age = now - e["seen"]
            if age > 6:
                continue  # file lama, sudah dicoba, belum match
            try:
                fid, row = fut.result(timeout=3)
            except _cf.TimeoutError:
                continue
            except Exception:
                continue
        else:
            try:
                fid, row = fut.result()
            except Exception:
                del _MATCH_FUTS[key]
                continue
            del _MATCH_FUTS[key]
        if not fid:
            if now - _UNMATCHED_QUIET.get(key, 0) >= UNMATCHED_QUIET_S:
                _UNMATCHED_QUIET[key] = now
                print(f"  [?] {e['name'][:55]:55s} belum ada di dashboard, tunggu...")
            continue
        if isinstance(row, dict) and row.get("machine_name") and row.get("operator"):
            del _PENDING[key]
            continue
        batch.append((e["name"], e["label"]))
    return batch


def _match_one(key, name):
    """Satu pencocokan dashboard (jalan di thread latar)."""
    try:
        return find_file_id(name)
    except Exception as e:
        return None, str(e)


def show_counts(counts=None):
    try:
        total, pending, done, verif = counts if counts else dashboard_counts()
        print(f"  Watcher: Total={total} Pending={pending} Selesai={done} Verified={verif}")
        return (total, pending, done, verif)
    except Exception as e:
        print(f"  Watcher tak terjangkau: {e}")
        return None


def watch():
    folders, machine_map = ask_folders()
    print(f"  mesin: {machine_map}")
    for label, folder in folders.items():
        threading.Thread(target=_dir_watcher, args=(Path(folder),), daemon=True).start()
    last = None
    try:
        while True:
            fired = _WAKE.wait(30)  # bangun saat ada aksi file; jaring pengaman 30 dtk
            _WAKE.clear()
            if fired:
                time.sleep(5)  # settle: beri file kembaran sempat masuk semua
                _WAKE.clear()
            try:
                counts = dashboard_counts()
            except Exception:
                counts = None
            batch = scan_new(folders)
            if not batch and counts == last:
                continue  # tidak ada perubahan: diam total
            last = counts
            os.system("cls")
            print(f"  ----- {datetime.datetime.now().strftime('%H:%M:%S')} -----")
            print("  ===== WMA — Watcher Module Auto =====")
            show_counts(counts)
            if batch:
                print(f"  {len(batch)} file baru:")
                for n, label in batch:
                    print(f"    [{label}] {n[:70]}")
                op = ask_key()
                os.system("cls")
                print("  ===== WMA — hasil =====")
                if op:
                    print(f"  Operator: {op}")
                results = []
                if op:
                    kon = konica_machine()
                    for n, label in batch:
                        m = machine_map.get(label, label)
                        if label != "RICOH" and kon:
                            m = kon
                        ok, info = report(n, m, op)
                        results.append((n, m, op, ok, info))
                        if ok:
                            _PENDING.pop(n.lower(), None)
                            _MATCH_FUTS.pop(n.lower(), None)
                else:
                    print("  batch dilewati.")
                last = show_counts()
                for n, m, op_, ok, info in results:
                    mark = "OK " if ok else "!! "
                    print(f"  [{mark}] {n[:45]:45s} {m:10s} {op_} -> {info}")
                if op:
                    print(f"  {len([r for r in results if r[3]])}/{len(results)} jadi Selesai.")
    except KeyboardInterrupt:
        print("\n  stop.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--check" in args:
        i = args.index("--check")
        name = args[i + 1] if i + 1 < len(args) else ""
        fid, row = find_file_id(name)
        if fid:
            print(f"ketemu: id={fid} status={row.get('status')} "
                  f"mesin={row.get('machine_name') or '-'} operator={row.get('operator') or '-'}")
        else:
            print(f"tidak ketemu: {row or name}")
    elif "--report" in args:
        i = args.index("--report")
        name = args[i + 1] if i + 1 < len(args) else ""
        machine = ""
        if "--machine" in args:
            j = args.index("--machine")
            machine = args[j + 1] if j + 1 < len(args) else ""
        if not machine:
            cfg = load_cfg()
            machine = cfg.get("default_machine", "")
        if not machine:
            print("mesin kosong — pakai --machine \"Develop 1\"")
            raise SystemExit(2)
        ok, info = report(name, machine)
        print(("OK " if ok else "GAGAL ") + str(info))
    elif "--operator" in args:
        ask_operator()
    else:
        watch()
