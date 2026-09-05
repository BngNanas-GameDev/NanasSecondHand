"""Alur: File masuk -> LLM parse -> RL jawab -> LLM koreksi -> user nilai"""
import random
import re
import time, json, sys, traceback
from pathlib import Path

BASE = Path(__file__).parent.parent
CONFIG = BASE / "config.json"
try:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
except FileNotFoundError:
    print("[E001] config.json tidak ditemukan")
    cfg = {"input_folder":"input","output_folder":"impose"}
except json.JSONDecodeError:
    print("[E001] config.json corrupt, gunakan default")
    cfg = {"input_folder":"input","output_folder":"impose"}

INPUT = Path(cfg.get("input_folder","input"))
OUTPUT = Path(cfg.get("output_folder","impose"))
UDA = Path(cfg.get("uda_folder", str(INPUT / "uda")))

sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))
try:
    from imposition_bridge import impose_file
except ImportError as e:
    print(f"[E012] Gagal load imposition_bridge: {e}")
    def impose_file(*a, **k): raise RuntimeError("[E012] imposition_bridge tidak tersedia")
try:
    import preset_learner_rl as rl
except ImportError as e:
    print(f"[E005] Gagal load preset_learner_rl: {e}")
    rl = None
try:
    from llm_zen import llm_teacher_preset, llm_parse_filename
except ImportError as e:
    print(f"[E006] Gagal load llm_zen: {e}")
    llm_teacher_preset = None
    llm_parse_filename = lambda x: x
try:
    from bahan_dict import has_bahan, guess_bahan
except ImportError as e:
    print(f"[E006] Gagal load bahan_dict: {e}")
    has_bahan = lambda t: True
    guess_bahan = lambda t: None
try:
    from stats import log_event
except ImportError:
    log_event = lambda *a, **k: None

def err(code, msg):
    print(f"[{code}] {msg}")

def _sebab(e):
    """Ringkasan penyebab gagal tanpa path/nama file (privasi pelanggan)."""
    m = re.sub(r"'[^']*'", "'?'", str(e))
    m = re.sub(r"[A-Za-z]:\\[^\s]*", "?", m)
    return m[:80]

skipped=set()

# Fase 1: ambang auto-impose (conf computer: 0.5 + Q*0.3, maks 0.8)
AUTO_CONF = 0.75
AUDIT_RATE = 0.10  # 10% file auto-eligible tetap ditanya (spot-check)
def scan_and_impose():
    pdfs = list(INPUT.glob("*.pdf")) + list(INPUT.glob("*.PDF"))
    if not pdfs:
        return 0
    count=0
    for src in pdfs:
        if "uda" in src.parts:
            continue
        if not src.exists():
            continue  # file keburu dipindah/diganti nama
        # hanya PDF
        if src.suffix.lower() != ".pdf":
            if src.name not in skipped:
                print(f"[SKIP] {src.name} (bukan PDF)")
                skipped.add(src.name)
            continue
        # ignore kisscut/diecut
        if "kisscut" in src.name.lower() or "diecut" in src.name.lower():
            if src.name not in skipped:
                print(f"[SKIP] {src.name} (kisscut/diecut)")
                skipped.add(src.name)
            continue
        # ignore hardcover
        if "hardcover" in src.name.lower():
            if src.name not in skipped:
                print(f"[SKIP] {src.name} (hardcover)")
                skipped.add(src.name)
            continue
        # ignore map
        if "map" in src.name.lower():
            if src.name not in skipped:
                print(f"[SKIP] {src.name} (map)")
                skipped.add(src.name)
            continue
        # skip jika tidak ada nama bahan (toleran typo: Sriker/Cromo)
        if not has_bahan(src.name):
            if src.name not in skipped:
                print(f"[SKIP] {src.name} (tidak ada nama bahan)")
                skipped.add(src.name)
            continue
        # skip master/kalkir
        if "master" in src.name.lower() or "kalkir" in src.name.lower():
            if src.name not in skipped:
                print(f"[SKIP] {src.name} (master/kalkir)")
                skipped.add(src.name)
            continue
        # skip jika tidak ada dx (1d4, 1d12, 1d24, dll)
        if not re.search(r"1d\d+", src.name.lower()):
            if src.name not in skipped:
                print(f"[SKIP] {src.name} (tidak ada dx)")
                skipped.add(src.name)
            continue
        # ignore test/tes + finishing
        fname_low = src.name.lower()
        is_test = "test" in fname_low or "tes" in fname_low
        if is_test:
            finishing_keywords = ["spiral kiri","spiral atas","spiral kanan","staples punggung","lem panas","staples tengah","booklet"]
            for kw in finishing_keywords:
                if kw in fname_low:
                    if src.name not in skipped:
                        print(f"[SKIP] {src.name} (test/tes + {kw})")
                        skipped.add(src.name)
                    break
        dst = OUTPUT / src.name
        if dst.exists():
            try:
                UDA.mkdir(parents=True, exist_ok=True)
                src.rename(UDA / src.name)
                print(f"[AI] Sudah ada di impose, pindah ke uda/: {src.name}")
            except Exception as e:
                err("E004", f"Gagal pindah duplikat: {e}")
            continue

        print("\n" + "="*60)
        print(f"📄 File Masuk: {src.name}")

        # 1. LLM parse nama file → baca enak
        try:
            parsed = llm_parse_filename(src.name)
            if parsed:
                print(f"[LLM Parse] {parsed}")
        except Exception as e:
            err("E021", f"LLM parse gagal: {e}")

        # 2. RL jawab preset dari Q-table
        try:
            rl_preset, rl_conf, rl_results = rl.suggest_parallel_rl(src.name)
        except Exception as e:
            err("E005", f"RL suggest gagal: {e}")
            rl_preset = {"sheet":"A3+ Full (32.5x48.7cm)","bahan":"-","duplex":"1s","dx":"-","mode":"crop","bleed_mm":0,"inner_crop":True,"mark_len_mm":5,"bleed_on":True,"line_color":"gray","repeat_mode":"repeat"}
            rl_results = {}
        print()
        print("   ┌─────────────────────────────────────────┐")
        print("   │          JAWABAN RL (Q-learning)        │")
        print("   ├─────────────────────────────────────────┤")
        for cat in ["sheet","bahan","duplex","dx","finishing","repeat"]:
            v,c,i = rl_results.get(cat, ("-",0,None))
            flag = "RL" if isinstance(i, dict) and i.get("rl") else "cold"
            q_str = f" Q={i.get('Q'):.2f}" if isinstance(i, dict) and "Q" in i else ""
            if cat=="duplex": v = str(v)
            if cat=="finishing":
                if isinstance(v, dict): v = "bleed 2mm" if v.get("bleed_mm")==2 else "crop" if v.get("mode")=="crop" else "-"
                elif v=="bleed": v = "bleed 2mm"
                elif v=="crop": v = "crop"
            print(f"   │ {cat:10}: {str(v)[:20]:20} ({flag}{q_str:10}) │")
        print("   └─────────────────────────────────────────┘")

        # 3. LLM koreksi jawaban RL
        guru_preset = rl_preset.copy()
        guru_conf = 0
        try:
            _cold = {c for c in ["sheet", "bahan", "duplex", "dx", "finishing", "repeat"]
                     if not (isinstance(rl_results.get(c, (None, 0, None))[2], dict)
                             and rl_results[c][2].get("rl"))}
            taught = rl.teacher_train(src.name, rl_preset=rl_preset, reward=0.8,
                                      cold_cats=_cold)
            if taught:
                guru_preset, guru_conf, _ = rl.suggest_parallel_rl(src.name)
                diff = {k:v for k,v in guru_preset.items() if v != rl_preset.get(k)}
                if diff:
                    print(f"[Guru] Koreksi RL: {diff}")
                else:
                    print(f"[Guru] Setuju dengan RL")
            else:
                print(f"[Guru] LLM gagal, pakai jawaban RL")
        except Exception as e:
            err("E006", f"Guru train gagal: {e}")

        print()
        print("   ┌─────────────────────────────────────────┐")
        print("   │         PRESET GURU (koreksi RL)        │")
        print("   ├─────────────────────────────────────────┤")
        print(f"   │ Sheet     : {str(guru_preset.get('sheet',''))[:28]:28} │")
        print(f"   │ Bahan     : {str(guru_preset.get('bahan',''))[:28]:28} │")
        dup_str = {"1s":"1s (satu muka)","2s":"2s (dua muka, gambar beda)","dr":"dr (duplex repeat, gambar sama)"}.get(str(guru_preset.get('duplex','1s')), "1s (satu muka)")
        print(f"   │ Duplex    : {dup_str:28} │")
        print(f"   │ Dx        : {str(guru_preset.get('dx',''))[:28]:28} │")
        fin_str = "bleed 2mm" if guru_preset.get('bleed_mm')==2 else "crop" if guru_preset.get('mode')=="crop" else "-"
        print(f"   │ Finishing : {fin_str:28} │")
        print(f"   │ Repeat    : {str(guru_preset.get('repeat_mode',''))[:28]:28} │")
        print("   └─────────────────────────────────────────┘")

        # 4. User nilai, atau AUTO (Fase 1): conf tinggi + pola dikenal + tidak ambigu
        auto = False
        try:
            is_new, is_ambig, gap = rl.state_maturity(src.name)
        except Exception:
            is_new, is_ambig, gap = True, False, 0
        if guru_conf >= AUTO_CONF and not is_new and not is_ambig \
                and rl.validasi_count(src.name) >= rl.VALID_MIN_AUTO:
            if random.random() < AUDIT_RATE:
                print(f"   [AUDIT] conf={guru_conf:.2f} kena spot-check, tetap tanya")
            else:
                auto = True
                print(f"   [AUTO] conf={guru_conf:.2f} gap={gap}, langsung impose")
        eval_type, eval_detail = "none", ""
        if auto:
            preset = guru_preset
            eval_type, eval_detail = "auto", f"conf={guru_conf:.2f}"
        else:
            try:
                ans = input(f"   ✅ Benar? Enter=ya / ketik salah: ").strip()
                if not ans:
                    print(f"   -> ✅ Benar")
                    preset = guru_preset
                    eval_type = "benar"
                else:
                    corrected = guru_preset.copy()
                    low = ans.lower()
                    if "bahan" in low:
                        _g = guess_bahan(ans)
                        if _g: corrected["bahan"]=_g
                        elif low.strip() != "bahan" and not any(k in low for k in ("repeat","collate","booklet","unique","duplex","2s","1s","bleed","crop","dx")):
                            corrected["bahan"]=ans.split()[-1].capitalize()
                    if "bleed" in low: corrected["finishing"]="bleed"; [corrected.pop(k,None) for k in ["mode","bleed_mm","inner_crop","mark_len_mm","bleed_on"]]
                    elif "crop" in low: corrected["finishing"]="crop"; [corrected.pop(k,None) for k in ["mode","bleed_mm","inner_crop","mark_len_mm","bleed_on"]]
                    if "dx" in low: corrected["dx"]=ans.split("dx")[-1].strip()
                    if re.search(r"\bdr\b", low) or "duplex repeat" in low or "bolak balik sama" in low or "data sama" in low or low.strip()=="dr": corrected["duplex"]="dr"
                    elif "2s" in low or "dua muka" in low or low.strip() in ("2","duplex","bolak","true"): corrected["duplex"]="2s"
                    elif re.search(r"\b1s\b", low) or "satu muka" in low or "simplex" in low or low.strip() in ("1","false"): corrected["duplex"]="1s"
                    if "collate" in low or "booklet" in low: corrected["repeat_mode"]=ans.split()[-1] if "collate" in low else ans
                    elif "repeat" in low: corrected["repeat_mode"]="repeat"
                    elif "unique" in low: corrected["repeat_mode"]="unique"
                    if corrected==guru_preset and len(ans)>2 and not any(k in low for k in ("repeat","collate","booklet","unique","duplex","2s","1s","bleed","crop","dx","bahan")): corrected["bahan"]=ans
                    print(f"   -> ✅ Koreksi: {corrected}")
                    eval_type = "koreksi"
                    eval_detail = ",".join(k for k in corrected if corrected.get(k) != guru_preset.get(k))
                    preset = corrected
            except Exception: preset = guru_preset  # Exception saja: Ctrl+C tetap stop

        # 5. Impose (training + stats hanya jika file masih ada & sukses)
        print()
        print(f"   [FINAL] {preset}")
        print()
        if not src.exists():
            print(f"   [SKIP] {src.name} sudah dipindah/diganti nama, tidak dihitung")
            continue
        try:
            impose_file(src, dst, preset)
            print(f"   ✅ Sukses -> {dst}")
            if eval_type in ("benar", "koreksi"):
                try:
                    rl.train_parallel_rl(src.name, preset, reward=1)
                    rl.catat_validasi(src.name)
                except Exception as e:
                    err("E009", f"Training validasi gagal: {e}")
                log_event(eval_type, eval_detail)
            elif eval_type == "auto":
                log_event("auto", eval_detail)
            log_event("sukses")
            try: rl.train_parallel_rl(src.name, preset, reward=0.5)
            except Exception as e: err("E009", f"Training sukses gagal: {e}")
            try:
                UDA.mkdir(parents=True, exist_ok=True)
                target = UDA / src.name
                if target.exists(): target = UDA / f"{src.stem}_{int(time.time())}{src.suffix}"
                src.rename(target)
            except PermissionError:
                err("E004", f"Gagal pindah: permission denied - {src.name}")
            except OSError as e:
                err("E004", f"Gagal pindah: {e}")
            count+=1
        except FileNotFoundError:
            err("E010", f"Input file tidak ditemukan: {src} (tidak dihitung)")
        except PermissionError:
            err("E008", f"Gagal impose: permission denied - {src.name}")
            log_event("gagal", "E008:permission")
        except RuntimeError as e:
            err("E008", f"Gagal impose: {e}")
            log_event("gagal", f"E008:{_sebab(e)}")
        except Exception as e:
            err("E008", f"Gagal impose: {e}")
            log_event("gagal", f"E008:{_sebab(e)}")
            try: rl.train_parallel_rl(src.name, preset, reward=-1)
            except Exception as e: err("E009", f"Training hukuman gagal: {e}")
            traceback.print_exc()
    return count

def ask_folders():
    global INPUT, OUTPUT, UDA, cfg
    print("="*60)
    print(" AI Nanas Second Hand - Setup Folder")
    print("="*60)
    print(f"Folder Input saat ini : {INPUT}")
    print(f"Folder Output saat ini: {OUTPUT}")
    print(f"Folder Uda saat ini   : {UDA}")
    print("")
    try:
        inp = input("📁 Dimana folder INPUT? Copas path: ").strip().strip('"').strip("'")
        if inp:
            inp_path = Path(inp)
            if inp_path.exists() or inp_path.parent.exists():
                INPUT = inp_path
                cfg["input_folder"] = str(INPUT).replace("\\","/")
                print(f"  -> Input: {INPUT}")
            else:
                err("E002", f"Folder input tidak ada: {inp}")
        out = input("📁 Dimana folder OUTPUT? Copas path: ").strip().strip('"').strip("'")
        if out:
            out_path = Path(out)
            OUTPUT.mkdir(parents=True, exist_ok=True)
            if out_path.exists() or out_path.parent.exists():
                OUTPUT = out_path
                cfg["output_folder"] = str(OUTPUT).replace("\\","/")
                print(f"  -> Output: {OUTPUT}")
            else:
                err("E002", f"Folder output tidak ada: {out}")
        uda_inp = input("📁 Dimana folder UDA (file selesai)? Copas path: ").strip().strip('"').strip("'")
        if uda_inp:
            uda_path = Path(uda_inp)
            UDA = uda_path
            cfg["uda_folder"] = str(UDA).replace("\\","/")
            print(f"  -> Uda: {UDA}")
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except (EOFError, KeyboardInterrupt):
        print("\nSetup dibatalkan.")
    except Exception as e:
        err("E001", f"Config save gagal: {e}")

if __name__ == "__main__":
    ask_folders()
    print(f"Watcher AI Nanas Second Hand")
    print(f"Input : {INPUT}")
    print(f"Output: {OUTPUT}")
    print(f"Uda   : {UDA}")
    print(f"Tool  : C:/ImpositionTool/ImpositionTool.exe")
    print("Alur: File masuk -> LLM parse -> RL jawab -> LLM koreksi -> user nilai")
    print("Ctrl+C untuk stop")
    try:
        INPUT.mkdir(parents=True, exist_ok=True)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        UDA.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        err("E002", "Permission denied membuat folder")
    try:
        while True:
            n = scan_and_impose()
            if n:
                print(f"[AI] {n} file di-impose")
            time.sleep(2)
    except KeyboardInterrupt:
        print("Stop watcher")
