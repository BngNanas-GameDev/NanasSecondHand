"""WMA — Watcher Module Auto. Jembatan file-routing <-> Watcher Dashboard.

- Nama file WMA = nama file dashboard (tanpa rename, match persis).
- Mesin diisi dari tujuan routing (DEVELOP/RICOH/...), operator per sesi.
- Dashboard API: GET /api/files, POST /api/files/{id}, GET /api/config.
- Pakai: wma.bat (sesi) | python wma.py --check "<file>" | --report ...
"""
import datetime
import json
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
CFG_PATH = BASE / "wma.json"

DASH_URL = "http://192.168.5.54:5000"
OPERATORS = ("Nanas", "Eric", "Rahmadi")  # ejaan persis dashboard


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


def find_file_id(filename, days_back=1):
    """Cari id dashboard by nama file persis. Return (id, row) atau (None, None)."""
    today = datetime.date.today()
    for d in range(days_back + 1):
        day = (today - datetime.timedelta(days=d)).isoformat()
        try:
            rows = _get(f"/api/files?date_from={day}&date_to={day}")
        except Exception as e:
            return None, f"dashboard tak terjangkau: {e}"
        for row in rows:
            if (row.get("filename") or "") == filename:
                return row.get("id"), row
    return None, None


def report(filename, machine, operator=None):
    """Isi mesin + operator dashboard untuk satu nama file.
    Return (True, id) atau (False, alasan)."""
    cfg = load_cfg()
    op = operator or cfg.get("operator") or OPERATORS[0]
    fid, row = find_file_id(filename)
    if not fid:
        return False, f"{filename} tidak ada di dashboard ({row or 'tidak ketemu'})"
    if isinstance(row, dict) and row.get("machine_name") and row.get("operator"):
        return False, f"sudah terisi ({row.get('machine_name')}/{row.get('operator')})"
    try:
        _post(f"/api/files/{fid}", {"machine_name": machine, "operator": op})
    except Exception as e:
        return False, f"POST gagal: {e}"
    return True, fid


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
        print("pakai: --check \"<file>\" | --report \"<file>\" --machine \"Develop 1\" | --operator")
