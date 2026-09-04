"""NSH Monitor: dashboard Q-table + statistik benar/salah + rekomendasi."""
import copy
import json
import sys
import time
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).parent
else:
    BASE = Path(__file__).parent

sys.path.insert(0, str(BASE))
from stats import read_events

DATA_DIR = BASE / "data" / "memory_rl"
CATS = ["sheet", "bahan", "duplex", "dx", "finishing", "repeat"]

try:
    from cleanup import clean_duplex, clean_bahan, clean_dx
    HAVE_CLEANUP = True
except Exception:
    HAVE_CLEANUP = False


def load_q(cat):
    p = DATA_DIR / f"{cat}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def analyze():
    """Kembalikan (ringkasan_event, stat_kategori, masalah, rekomendasi)."""
    now = int(time.time())
    ev = read_events()
    cnt = {"benar": 0, "koreksi": 0, "sukses": 0, "gagal": 0, "auto": 0}
    last_ts = 0
    for e in ev:
        t = e.get("type")
        if t in cnt:
            cnt[t] += 1
        if e.get("ts", 0) > last_ts:
            last_ts = e["ts"]
    dinilai = cnt["benar"] + cnt["koreksi"]
    rate = (cnt["koreksi"] / dinilai * 100) if dinilai else 0
    base_ts = max([e["ts"] for e in ev if e.get("type") == "baseline"] + [0])
    fresh = [e for e in ev if e.get("ts", 0) > base_ts]
    fcnt = {"benar": 0, "koreksi": 0, "sukses": 0, "gagal": 0, "auto": 0}
    for e in fresh:
        if e.get("type") in fcnt:
            fcnt[e["type"]] += 1
    fdinilai = fcnt["benar"] + fcnt["koreksi"]

    cat_stat = {}
    ambig_total = 0
    badq_total = 0
    try:
        unres = json.loads((BASE / "data" / "unresolvable.json").read_text(encoding="utf-8"))
    except Exception:
        unres = {}
    for cat in CATS:
        q = load_q(cat)
        states = len(q)
        bests = []
        matang = mentah = 0
        for st, acts in q.items():
            if not acts:
                continue
            vals = sorted(acts.values(), reverse=True)
            b = vals[0]
            bests.append(b)
            if b >= 0.65:
                matang += 1
            elif b < 0.35:
                mentah += 1
            if len(vals) > 1 and vals[0] - vals[1] < 0.05 and st not in unres.get(cat, []):
                ambig_total += 1
            badq_total += sum(1 for v in vals if v <= 0)
        avg = round(sum(bests) / len(bests), 3) if bests else 0
        cat_stat[cat] = dict(states=states, avg=avg, matang=matang, mentah=mentah)

    dirty = {"duplex": 0, "bahan": 0, "dx": 0}
    if HAVE_CLEANUP:
        d = copy.deepcopy(load_q("duplex"))
        dirty["duplex"] = clean_duplex(d)
        b = copy.deepcopy(load_q("bahan"))
        nb, _ = clean_bahan(b)
        dirty["bahan"] = nb
        x = copy.deepcopy(load_q("dx"))
        nx, _ = clean_dx(x)
        dirty["dx"] = nx

    rec = []
    if not ev:
        rec.append("Belum ada data penilaian (stats kosong). Nilai beberapa file dulu di watcher.")
    else:
        if rate > 30:
            rec.append(f"Koreksi tinggi ({rate:.0f}%). RL belum stabil — tetap nilai manual.")
        elif dinilai >= 20 and rate <= 10:
            rec.append(f"Koreksi rendah ({rate:.0f}% dari {dinilai}). Siap ke auto-threshold.")
        if cnt["gagal"]:
            rec.append(f"Ada {cnt['gagal']} impose gagal. Cek ERROR_CODES.md.")
        if last_ts and now - last_ts > 7 * 86400:
            rec.append("Tidak ada aktivitas >7 hari.")
    if sum(dirty.values()):
        rec.append(f"Q-table kotor (duplex:{dirty['duplex']} bahan:{dirty['bahan']} dx:{dirty['dx']}). Tekan 'Cleanup Now'.")
    if ambig_total:
        rec.append(f"{ambig_total} state ambigu (2 jawaban Q mepet). Tegaskan lewat koreksi manual.")
    if badq_total:
        rec.append(f"{badq_total} action Q<=0 (dihukum gagal). Akan pulih sendiri lewat training.")
    for cat, s in cat_stat.items():
        if 0 < s["states"] < 10:
            rec.append(f"Kategori '{cat}' baru {s['states']} pola — masih tahap belajar.")
    if not rec:
        rec.append("Semua sehat. Pertahankan penilaian rutin.")

    summary = dict(total_ev=len(ev), dinilai=dinilai, rate=round(rate, 1),
                   last_ts=last_ts, base_ts=base_ts,
                   fdinilai=fdinilai, fbenar=fcnt["benar"], fkoreksi=fcnt["koreksi"],
                   fsukses=fcnt["sukses"], fgagal=fcnt["gagal"], fauto=fcnt["auto"],
                   **cnt)
    return summary, cat_stat, dirty, ambig_total, rec


def run_cleanup():
    if not HAVE_CLEANUP:
        return "Modul cleanup tidak tersedia."
    out = []
    q = load_q("duplex")
    out.append(f"duplex: {clean_duplex(q)} merge")
    (DATA_DIR / "duplex.json").write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
    q = load_q("bahan")
    nb, sb = clean_bahan(q)
    (DATA_DIR / "bahan.json").write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
    out.append(f"bahan: {nb} hapus, {sb} state buang")
    q = load_q("dx")
    nx, sx = clean_dx(q)
    (DATA_DIR / "dx.json").write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
    out.append(f"dx: {nx} hapus, {sx} state buang")
    return "; ".join(out)


def main():
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title("NSH Monitor")
    root.geometry("640x560")

    frm = ttk.Frame(root, padding=10)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="Nanas Second Hand — Monitor", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    sub = ttk.Label(frm, text="", foreground="gray")
    sub.pack(anchor="w", pady=(0, 8))

    txt = tk.Text(frm, height=24, wrap="word", font=("Consolas", 10))
    txt.pack(fill="both", expand=True)

    def refresh():
        try:
            s, cats, dirty, ambig, rec = analyze()
        except Exception as e:
            messagebox.showerror("NSH Monitor", f"Gagal baca data: {e}")
            return
        last = time.strftime("%d-%m %H:%M", time.localtime(s["last_ts"])) if s["last_ts"] else "-"
        lines = [
            f"Data dimakan (dinilai) : {s['dinilai']}  (benar:{s['benar']} koreksi:{s['koreksi']} auto:{s['auto']})",
            f"Sejak pembersihan      : {s['fdinilai']}  (benar:{s['fbenar']} koreksi:{s['fkoreksi']} auto:{s['fauto']} sukses:{s['fsukses']} gagal:{s['fgagal']})",
            f"Tingkat koreksi        : {s['rate']}%",
            f"Impose sukses / gagal  : {s['sukses']} / {s['gagal']}",
            f"Aktivitas terakhir     : {last}",
            "",
            f"{'Kategori':<10}{'Pola':>6}{'AvgQ':>7}{'Matang':>8}{'Mentah':>8}",
        ]
        for c in CATS:
            st = cats[c]
            lines.append(f"{c:<10}{st['states']:>6}{st['avg']:>7}{st['matang']:>8}{st['mentah']:>8}")
        lines += [
            "",
            f"Kotor: duplex={dirty['duplex']} bahan={dirty['bahan']} dx={dirty['dx']} | Ambigu: {ambig}",
            "",
            "Rekomendasi:",
        ]
        for i, r in enumerate(rec, 1):
            lines.append(f"  {i}. {r}")
        txt.delete("1.0", "end")
        txt.insert("1.0", "\n".join(lines))
        sub.config(text=f"Update: {time.strftime('%H:%M:%S')} | {BASE}")

    def on_cleanup():
        if not HAVE_CLEANUP:
            messagebox.showwarning("NSH Monitor", "Modul cleanup tidak ikut dibundel.")
            return
        try:
            msg = run_cleanup()
        except Exception as e:
            messagebox.showerror("NSH Monitor", f"Cleanup gagal: {e}")
            return
        refresh()
        messagebox.showinfo("NSH Monitor", f"Selesai: {msg}")

    bar = ttk.Frame(frm)
    bar.pack(fill="x", pady=(8, 0))
    ttk.Button(bar, text="Refresh", command=refresh).pack(side="left")
    ttk.Button(bar, text="Cleanup Now", command=on_cleanup).pack(side="left", padx=(8, 0))

    def auto():
        refresh()
        root.after(60000, auto)

    refresh()
    root.after(60000, auto)
    root.mainloop()


if __name__ == "__main__":
    main()
