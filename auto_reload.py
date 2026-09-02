"""Auto-reload: restart watcher saat .py berubah"""
import subprocess, sys, time, os
from pathlib import Path

BASE = Path(__file__).parent
PY_FILES = list(BASE.glob("*.py")) + list(BASE.glob("scripts/*.py"))
md_times = {f: f.stat().st_mtime for f in PY_FILES}

print("[Auto-Reload] Memantau perubahan kode...")
print(f"[Auto-Reload] {len(PY_FILES)} file dipantau")

proc = None
def start():
    global proc
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait()
    print("[Auto-Reload] Start watcher.py...")
    proc = subprocess.Popen([sys.executable, str(BASE / "scripts" / "watcher.py")])

start()

try:
    while True:
        time.sleep(1)
        for f in PY_FILES:
            if not f.exists(): continue
            new_mtime = f.stat().st_mtime
            if new_mtime > md_times.get(f, 0):
                print(f"\n[Auto-Reload] {f.name} berubah, restart...")
                md_times[f] = new_mtime
                start()
                break
except KeyboardInterrupt:
    if proc: proc.terminate()
    print("\n[Auto-Reload] Stop")
