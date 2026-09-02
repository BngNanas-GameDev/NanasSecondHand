"""Alur: File masuk -> LLM parse -> RL jawab -> LLM koreksi -> user nilai"""
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

def err(code, msg):
    print(f"[{code}] {msg}")

skipped=set()
def scan_and_impose():
    pdfs = list(INPUT.glob("*.pdf")) + list(INPUT.glob("*.PDF"))
    if not pdfs:
        return 0
    count=0
    for src in pdfs:
        if "uda" in src.parts:
            continue
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
        # skip jika tidak ada nama bahan
        bahan_keywords = ["vinyl","kromo","ac260","ac190","ac230","ac310","hvs","art paper","art carton","ivory","jasmine","british","hanji","manila","kalkir","stiker","sticker","rajawali","ap120","ap150","pindo","matte","transparant"]
        if not any(k in src.name.lower() for k in bahan_keywords):
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
        # ignore test/tes + finishing
        fname_low = src.name.lower()
        is_test = "test" in fname_low or "tes" in fname_low
        if is_test:
            finishing_keywords = ["spiral kiri","spiral atas","spiral kanan","staples punggung","lem panas","staples tengah"]
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
            except: pass
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
            # normalize duplex boolean -> string
            if rl_preset.get("duplex") is True: rl_preset["duplex"]="2s"
            elif rl_preset.get("duplex") is False: rl_preset["duplex"]="1s"
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
            if cat=="duplex": v = "2s" if v==True else "1s" if v==False else str(v)
            if cat=="finishing":
                if isinstance(v, dict): v = "bleed 2mm" if v.get("bleed_mm")==2 else "crop" if v.get("mode")=="crop" else "-"
                elif v=="bleed": v = "bleed 2mm"
                elif v=="crop": v = "crop"
            print(f"   │ {cat:10}: {str(v)[:20]:20} ({flag}{q_str:10}) │")
        print("   └─────────────────────────────────────────┘")

        # 3. LLM koreksi jawaban RL
        guru_preset = rl_preset.copy()
        try:
            taught = rl.teacher_train(src.name, reward=0.8)
            if taught:
                guru_preset, guru_conf, _ = rl.suggest_parallel_rl(src.name)
                if guru_preset.get("duplex") is True: guru_preset["duplex"]="2s"
                elif guru_preset.get("duplex") is False: guru_preset["duplex"]="1s"
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

        # 4. User nilai: benar atau salah
        try:
            ans = input(f"   ✅ Benar? Enter=ya / ketik salah: ").strip()
            if not ans:
                print(f"   -> ✅ Benar")
                preset = guru_preset
                rl.train_parallel_rl(src.name, preset, reward=1)
            else:
                corrected = guru_preset.copy()
                low = ans.lower()
                if "bahan" in low:
                    if "vinyl" in low: corrected["bahan"]="Vinyl"
                    elif "kromo" in low: corrected["bahan"]="Kromo"
                    elif "ac260" in low: corrected["bahan"]="Ac260gr"
                    elif "ac190" in low: corrected["bahan"]="Ac190gr"
                    else: corrected["bahan"]=ans.split()[-1].capitalize()
                if "bleed" in low: corrected["finishing"]="bleed"; [corrected.pop(k,None) for k in ["mode","bleed_mm","inner_crop","mark_len_mm","bleed_on"]]
                elif "crop" in low: corrected["finishing"]="crop"; [corrected.pop(k,None) for k in ["mode","bleed_mm","inner_crop","mark_len_mm","bleed_on"]]
                if "dx" in low: corrected["dx"]=ans.split("dx")[-1].strip()
                if low in ("2s","2","duplex","bolak","true"): corrected["duplex"]="2s"
                elif low in ("dr","duplex repeat","bolak sama","bolak balik sama"): corrected["duplex"]="dr"
                elif low in ("1s","1","simplex","false"): corrected["duplex"]="1s"
                if "collate" in low or "booklet" in low: corrected["repeat_mode"]=ans.split()[-1] if "collate" in low else ans
                elif "repeat" in low: corrected["repeat_mode"]="repeat"
                elif "unique" in low: corrected["repeat_mode"]="unique"
                if corrected==guru_preset and len(ans)>2: corrected["bahan"]=ans
                rl.train_parallel_rl(src.name, corrected, reward=1)
                print(f"   -> ✅ Koreksi: {corrected}")
                preset = corrected
        except: preset = guru_preset

        # 5. Impose
        print()
        print(f"   [FINAL] {preset}")
        print()
        try:
            impose_file(src, dst, preset)
            print(f"   ✅ Sukses -> {dst}")
            try: rl.train_parallel_rl(src.name, preset, reward=0.5)
            except: pass
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
            err("E010", f"Input file tidak ditemukan: {src}")
        except PermissionError:
            err("E008", f"Gagal impose: permission denied - {src.name}")
        except RuntimeError as e:
            err("E008", f"Gagal impose: {e}")
        except Exception as e:
            err("E008", f"Gagal impose: {e}")
            try: rl.train_parallel_rl(src.name, preset, reward=-1)
            except: pass
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
            INPUT.mkdir(parents=True, exist_ok=True)
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
