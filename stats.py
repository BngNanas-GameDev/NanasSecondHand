"""Pencatat aktivitas NSH -> data/stats.jsonl (satu baris satu event)."""
import json
import time
from pathlib import Path

BASE = Path(__file__).parent
STATS = BASE / "data" / "stats.jsonl"


def log_event(etype, detail=""):
    """etype: benar | koreksi | sukses | gagal. Tidak menyimpan nama file."""
    try:
        STATS.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": int(time.time()), "type": etype, "detail": str(detail)[:120]}
        with STATS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_events():
    if not STATS.exists():
        return []
    out = []
    try:
        lines = STATS.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out
