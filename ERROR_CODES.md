# Error Codes Documentation

## Ringkasan
| Kode | File | Error | Severity |
|------|------|-------|----------|
| E001 | watcher.py | config.json tidak ditemukan | CRITICAL |
| E002 | watcher.py | Folder input/output tidak ada | HIGH |
| E003 | watcher.py | File sudah ada di output | LOW |
| E004 | watcher.py | Gagal pindah file ke uda/ | MEDIUM |
| E005 | watcher.py | RL suggest_parallel_rl gagal | HIGH |
| E006 | watcher.py | LLM teacher_train gagal | MEDIUM |
| E007 | watcher.py | User input error (EOFError) | LOW |
| E008 | watcher.py (blok impose) | impose_file gagal | HIGH |
| E009 | watcher.py (guard training) | Training RL gagal (terlihat, tidak silent) | MEDIUM |
| E023 | preset_learner_rl.py (catat_validasi) | Validasi manusia gagal dicatat (AUTO-gate buta sementara) | MEDIUM |
| E010 | imposition_bridge.py | ImpositionTool.exe tidak ditemukan | CRITICAL |
| E011 | imposition_bridge.py | PyInstaller extract gagal | HIGH |
| E012 | imposition_bridge.py | Engine module load gagal | HIGH |
| E013 | imposition_bridge.py | Sheet size tidak valid | MEDIUM |
| E014 | imposition_bridge.py | repeat_mode tidak valid | MEDIUM |
| E015 | imposition_bridge.py | impose_pdf error | HIGH |
| E016 | preset_learner_rl.py | Q-table load/save gagal | MEDIUM |
| E017 | preset_learner_rl.py | State key generation error | LOW |
| E018 | preset_learner_rl.py | Concurrent execution error | MEDIUM |
| E019 | llm_zen.py | API key tidak ditemukan (PENSIUN v3.0: LLM API dibuang, guru murni aturan) | - |
| E020 | llm_zen.py | LLM API call gagal (PENSIUN v3.0) | - |
| E021 | llm_zen.py | Response parse error (masih dipakai: parse filename gagal) | LOW |
| E022 | llm_zen.py | requests module tidak ada (PENSIUN v3.0: requests dibuang) | - |

---

## Detail Error Codes

### E001: config.json tidak ditemukan
**File:** `watcher.py:7`  
**Error:** `FileNotFoundError` atau `json.JSONDecodeError`  
**Cause:** File config.json corrupt atau tidak ada  
**Solution:** 
```bash
# Buat config.json baru
echo '{"input_folder":"input","output_folder":"impose"}' > config.json
```

---

### E002: Folder input/output tidak ada
**File:** `watcher.py:197-198`  
**Error:** Folder tidak ditemukan saat scan  
**Cause:** Path di config.json salah  
**Solution:** 
- Cek path di config.json
- Folder akan otomatis dibuat saat startup (`mkdir(parents=True, exist_ok=True)`)

---

### E003: File sudah ada di output
**File:** `watcher.py:39-46`  
**Error:** `[AI] Sudah ada di impose, pindah ke uda/`  
**Cause:** File sudah pernah di-impose  
**Solution:** 
- File otomatis dipindah ke `uda/`
- Jika gagal pindah, cek E004

---

### E004: Gagal pindah file ke uda/
**File:** `watcher.py:146-152`  
**Error:** `⚠ Gagal pindah: {e}`  
**Cause:** 
- File sedang digunakan program lain
- Permission denied
- Path terlalu panjang
**Solution:**
```bash
# Cek file yang sedang digunakan
# Tutup program yang mungkin menggunakan file
# Cek permission folder
```

---

### E005: RL suggest_parallel_rl gagal
**File:** `watcher.py:57`  
**Error:** Exception saat panggil `rl.suggest_parallel_rl()`  
**Cause:** 
- Q-table corrupt
- Memory insufficient
**Solution:**
```bash
# Hapus Q-table corrupt
rm data/memory_rl/*.json
# atau restore dari backup
```

---

### E006: LLM teacher_train gagal
**File:** `watcher.py:79-90`  
**Error:** `[Guru] LLM gagal, pakai jawaban RL`  
**Cause:** 
- API key expired
- Rate limit
- Network error
**Solution:**
- Sistem fallback ke regex rule otomatis
- Cek API key di `~/.local/share/opencode/auth.json`

---

### E007: User input error
**File:** `watcher.py:186`  
**Error:** `EOFError` atau `KeyboardInterrupt`  
**Cause:** User tekan Ctrl+C atau EOF  
**Solution:**
- Normal saat stop watcher
- Gunakan `Ctrl+C` untuk stop

---

### E008: impose_file gagal
**File:** `watcher.py` (blok impose)  
**Error:** `[E008] Gagal impose: {e}`  
**Cause:** 
- ImpositionTool.exe error
- File PDF corrupt
- Sheet size tidak valid
- File hilang/diganti nama saat diproses (lihat `No such file` pada sebab)
- Oversize (lihat `terlalu besar` pada sebab) → otomatis retry `allow_oversize=True`
**Cara baca sebab:** log `gagal` di `stats.jsonl` menyimpan `E008:<sebab>` tanpa nama file, mis:
- `E008:No such file or directory: '?'` → file hilang, tidak dihitung
- `E008:Halaman input (...) terlalu besar` → oversize
- `E008:permission` → permission denied
**Solution:**
- Cek E010-E015 untuk detail
- File akan di-retry dengan reward=-1 (kecuali file hilang: tidak dihitung sama sekali)

---

### E009: Training RL gagal
**File:** guard `try/except E009` di `watcher.py` (blok sukses/gagal)
**Error:** training Q-table gagal tapi impose jalan terus
**Cause:**
- Q-table corrupt / terkunci proses lain
- Concurrent write dengan cleanup/monitor
**Solution:**
- Error kini TAMPIL (dulu silent), cek pesannya
- Jika berulang: `python cleanup.py` lalu cek `data/memory_rl/*.json`

---

### E023: Validasi gagal dicatat
**File:** `preset_learner_rl.py` (`catat_validasi`)
**Error:** `[E023] Validasi gagal dicatat`
**Cause:** `data/validasi.json` corrupt / permission
**Solution:**
- Syarat AUTO (validasi≥2) tidak terpenuhi sementara → file ditanya manual (aman)
- Hapus/rename `data/validasi.json` agar dibuat ulang kosong

---

### E010: ImpositionTool.exe tidak ditemukan
**File:** `imposition_bridge.py:7`  
**Error:** `FileNotFoundError: C:/ImpositionTool/ImpositionTool.exe`  
**Cause:** Tool tidak terinstall  
**Solution:**
```bash
# Pastikan ImpositionTool.exe ada di C:/ImpositionTool/
# atau update path di imposition_bridge.py
```

---

### E011: PyInstaller extract gagal
**File:** `imposition_bridge.py:12-16`  
**Error:** `ArchiveError` atau `KeyError`  
**Cause:** 
- ImpositionTool.exe corrupt
- Format PyInstaller berbeda
**Solution:**
```bash
# Re-download ImpositionTool.exe
# Pastikan versi terbaru
```

---

### E012: Engine module load gagal
**File:** `imposition_bridge.py:49-50`  
**Error:** `ImportError: cannot import name '...'`  
**Cause:** 
- Module dependency missing
- Version mismatch
**Solution:**
```bash
# Install dependencies
pip install pypdf reportlab
```

---

### E013: Sheet size tidak valid
**File:** `imposition_bridge.py:64-70`  
**Error:** Fallback ke default sheet  
**Cause:** Sheet name tidak ada di PRESET_SIZES  
**Solution:**
- Gunakan sheet name yang valid:
  - `A3+ Full (32.5x48.7cm)`
  - `A3 (29.7x42cm)`
  - `A4 (21x29.7cm)`
  - Custom: `((320,480),(320,480))`

---

### E014: repeat_mode tidak valid
**File:** `imposition_bridge.py:92-93`  
**Error:** Fallback ke `repeat`  
**Cause:** Mode tidak di recognized  
**Solution:**
- Gunakan mode yang valid:
  - `repeat`
  - `collate-cut`
  - `collate-cut-repeat`
  - `booklet`
  - `unique`

---

### E015: impose_pdf error
**File:** `imposition_bridge.py:126`  
**Error:** Exception dari engine  
**Cause:** 
- Input PDF corrupt
- Output path tidak writable
- Memory insufficient
**Solution:**
```bash
# Cek input PDF
# Cek permission output folder
# Cek disk space
```

---

### E016: Q-table load/save gagal
**File:** `preset_learner_rl.py:70-78`  
**Error:** `JSONDecodeError` atau `PermissionError`  
**Cause:** 
- Q-table corrupt
- File sedang ditulis
**Solution:**
```bash
# Backup Q-table
cp data/memory_rl/*.json data/memory_rl_backup/
# atau rebuild
rm data/memory_rl/*.json
```

---

### E017: State key generation error
**File:** `preset_learner_rl.py:43-64`  
**Error:** `re.error` atau `KeyError`  
**Cause:** Regex pattern error  
**Solution:**
- Error di-ignore, gunakan default state

---

### E018: Concurrent execution error
**File:** `preset_learner_rl.py:147, 222`  
**Error:** `RuntimeError` atau `TimeoutError`  
**Cause:** 
- Too many threads
- Deadlock
**Solution:**
- Max workers dikurangi (6)
- Error di-handle per-future

---

### E019: API key tidak ditemukan
**File:** `llm_zen.py:10-18`  
**Error:** `[]` (empty response)  
**Cause:** 
- auth.json tidak ada
- Key tidak ada
**Solution:**
```bash
# Cek auth.json
cat ~/.local/share/opencode/auth.json
# Pastikan ada key:
# {"openrouter": {"key": "sk-or-v1-..."}}
```

---

### E020: LLM API call gagal
**File:** `llm_zen.py:28-44`  
**Error:** Status code != 200  
**Cause:** 
- Rate limit (429)
- Unauthorized (401)
- Model not found (404)
**Solution:**
- Sistem fallback ke model lain
- Cek quota OpenRouter

---

### E021: Response parse error
**File:** `llm_zen.py:35-42`  
**Error:** Response bukan JSON  
**Cause:** 
- Model return thinking block
- Response format berbeda
**Solution:**
- Sistem auto-parse thinking block
- Fallback ke regex rule

---

### E022: requests module tidak ada
**File:** `llm_zen.py:3-5`  
**Error:** `requests=None`  
**Cause:** Module tidak terinstall  
**Solution:**
```bash
pip install requests
```

---

## Troubleshooting Quick Fix

### 1. Reset Semua
```bash
# Hapus Q-table
rm data/memory_rl/*.json

# Hapus config
rm config.json

# Restart watcher
python scripts/watcher.py
```

### 2. Cek Health
```bash
# Cek ImpositionTool
ls C:/ImpositionTool/ImpositionTool.exe

# Cek API Key
cat ~/.local/share/opencode/auth.json

# Cek Config
cat config.json
```

### 3. Debug Mode
```python
# Tambah di watcher.py
import logging
logging.basicConfig(level=logging.DEBUG)
```
