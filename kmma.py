"""KMMA — KonsepMedia Module Auto.
Alur: load wma_daily.json -> login KM -> fetch order -> validasi -> isi form -> simpan.
API: get_detail (JSON) -> get_detail_flow (JSON) -> save_flow (POST).
"""
import datetime
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
ENV_PATH = BASE / "env" / "kmma" / ".env"
CFG_PATH = BASE / "kmma.json"
DAILY_PATH = BASE / "wma_daily.json"

POLL_INTERVAL = 300
ACTION_DELAY = 1
API_DELAY = 5
NOTA_RETRY = 600

R_BAHAN = re.compile(r"(Ap\d+gr|Ac\d+gr|Stiker\s+\w+|HVS|Concord|BC\s+\w+|Master|BNTU)", re.I)
R_NOTA = re.compile(r"(ON\d{12})")
R_TOTAL = re.compile(r"TOTAL\s*=\s*(\d+)\s*(BESAR|KECIL)", re.I)


def load_env():
    env = {}
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


def load_cfg():
    try:
        return json.loads(CFG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cfg(cfg):
    CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def load_daily():
    try:
        data = json.loads(DAILY_PATH.read_text(encoding="utf-8"))
        today = datetime.date.today().isoformat()
        if data.get("date") == today and data.get("entries"):
            return data["entries"]
    except Exception:
        pass
    return []


def extract_bahan(filename):
    m = R_BAHAN.search(filename)
    return m.group(0) if m else None


def extract_nota(filename):
    m = R_NOTA.search(filename)
    return m.group(1) if m else None


def extract_total(filename):
    m = R_TOTAL.search(filename)
    if m:
        return int(m.group(1)), m.group(2).upper()
    return None, None


def match_bahan(filename_bahan, km_material_name):
    """Cek apakah bahan dari filename match bahan KM."""
    fb = filename_bahan.lower().replace(" ", "")
    km = km_material_name.lower().replace(" ", "")
    # langsung substring match
    if fb in km:
        return True
    # extract prefix+angka: Ap190, Ac260, dll
    m_fn = re.match(r'(ap|ac)(\d+)', fb)
    if m_fn:
        prefix, num = m_fn.groups()
        # cek "230gr" langsung di material KM
        if f"{num}gr" in km:
            return True
    # stiker/sticker (variasi ejaan)
    for name in ["stiker", "sticker", "concord", "hvs", "idcard", "id card"]:
        if name in fb:
            # cek variasi: stiker/sticker
            variants = {"stiker": "sticker", "sticker": "stiker"}
            km_check = variants.get(name, name)
            if name in km or km_check in km:
                return True
    return False


class KMClient:
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    def __init__(self):
        self.base = "https://www.konsepmedia.com/administrator"
        self.cookie = None
        self._last_ts = 0

    def _throttle(self):
        elapsed = time.time() - self._last_ts
        if elapsed < API_DELAY:
            time.sleep(API_DELAY - elapsed)
        self._last_ts = time.time()

    def _request(self, method, path, data=None):
        self._throttle()
        url = f"{self.base}/{path}"
        body = None
        headers = {"User-Agent": self.UA}
        if data:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.cookie:
            headers["Cookie"] = self.cookie
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                if not self.cookie:
                    for h in r.headers.get_all("Set-Cookie") or []:
                        if "ci_session" in h:
                            self.cookie = h.split(";")[0]
                            break
                return r.read().decode("utf-8", errors="replace")
        except Exception:
            return None

    def preflight(self):
        self._request("GET", "login")

    def login(self, username, password):
        self.preflight()
        html = self._request("POST", "login/process", {
            "username": username, "password": password, "ci_csrf_token": "",
        })
        if html and ("logout" in html.lower() or "home" in html.lower()):
            return True
        return False

    def fetch_orders_page(self):
        """Fetch workflow page, return list of order dicts dari tabel HTML."""
        orders = []
        seen = set()
        page = 1
        while True:
            url = f"workflow_production?status=PESANAN+SUDAH+DIVERIFIKASI&limited_show=200"
            if page > 1:
                url += f"&per_page=200&data-ci-pagination-page={page}"
            html = self._request("GET", url)
            if not html:
                break
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
            found = 0
            for row in rows:
                m = re.search(r'data-id="(\d+)"', row)
                if not m:
                    continue
                data_id = m.group(1)
                if data_id in seen:
                    continue
                seen.add(data_id)
                found += 1
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
                clean = [re.sub(r'<[^>]+>', ' ', c).strip() for c in cells]
                nota = ""
                for c in clean:
                    nm = re.search(r'(ON\d{12})', c)
                    if nm:
                        nota = nm.group(1)
                        break
                bahan = ""
                qty = ""
                for c in clean:
                    if re.search(r'(Art Carton|Sticker|Stiker|Concord|ID Card|HVS|Art Paper)', c, re.I):
                        bahan = re.sub(r'\s+', ' ', c).strip()
                        break
                for ci, c in enumerate(clean):
                    if c.isdigit() and ci > 0:
                        prev = clean[ci - 1] if ci > 0 else ""
                        if not prev.isdigit():
                            qty = c
                            break
                if nota:
                    orders.append({
                        "data_id": data_id, "nota": nota,
                        "bahan_km": bahan, "qty_km": qty,
                    })
            if found == 0:
                break
            if f'data-ci-pagination-page="{page + 1}"' not in html:
                break
            page += 1
            time.sleep(ACTION_DELAY)
        return orders

    def get_detail(self, data_id):
        """POST get_detail -> JSON transaction + flow steps."""
        time.sleep(ACTION_DELAY)
        resp = self._request("POST", "workflow_production/get_detail", {
            "id": data_id, "tt": "",
        })
        if not resp:
            return None
        try:
            return json.loads(resp)
        except Exception:
            return None

    def get_detail_flow(self, idproduct_step, idtransaction_detail):
        """POST get_detail_flow -> JSON material/machine/sdm options."""
        time.sleep(ACTION_DELAY)
        resp = self._request("POST", "workflow_production/get_detail_flow", {
            "id": idproduct_step, "id_td": idtransaction_detail,
        })
        if not resp:
            return None
        try:
            data = json.loads(resp)
            if data.get("err_code") == 0:
                return data
        except Exception:
            pass
        return None

    def save_flow(self, payload):
        """POST save_flow -> JSON success/error."""
        time.sleep(ACTION_DELAY)
        resp = self._request("POST", "workflow_production/save_flow", payload)
        if not resp:
            return False, "network error"
        try:
            data = json.loads(resp)
            if data.get("err_code") == 0:
                return True, "ok"
            return False, data.get("err_message", "unknown")
        except Exception:
            if "berhasil" in resp.lower():
                return True, "ok"
        return False, "save failed"


def log_skip(reason, nota):
    cfg = load_cfg()
    skip = cfg.get("skip_forever", {})
    skip[nota] = reason
    cfg["skip_forever"] = skip
    save_cfg(cfg)
    print(f"  [SKIP] {nota}: {reason}")


def should_skip(nota):
    cfg = load_cfg()
    if nota in cfg.get("skip_forever", {}):
        return True
    retry = cfg.get("skipped_nota", {})
    if nota in retry:
        try:
            last_dt = datetime.datetime.fromisoformat(retry[nota]["last_try"])
            if (datetime.datetime.now() - last_dt).total_seconds() < NOTA_RETRY:
                return True
        except Exception:
            pass
    return False


def mark_nota_retry(nota):
    cfg = load_cfg()
    retry = cfg.get("skipped_nota", {})
    retry[nota] = {
        "reason": "kode tidak ada di list KM",
        "last_try": datetime.datetime.now().isoformat(),
    }
    cfg["skipped_nota"] = retry
    save_cfg(cfg)


def process_entry(client, entry):
    filename = entry["filename"]
    machine_wma = entry["machine"]
    operator_wma = entry["operator"]

    nota = extract_nota(filename)
    if not nota:
        print(f"  [!] {filename[:50]}... - kode NOTA tidak ditemukan, skip")
        return

    if should_skip(nota):
        return

    bahan_file = extract_bahan(filename)
    qty_file, jenis_file = extract_total(filename)

    orders = client.fetch_orders_page()
    if not orders:
        print("  [KMMA-E05] gagal ambil daftar order")
        return

    matched = None
    for o in orders:
        if o["nota"] == nota:
            matched = o
            break

    if not matched:
        mark_nota_retry(nota)
        print(f"  [KMMA-E02] {nota} tidak ada di list KM, retry 10 menit")
        return

    if bahan_file and matched.get("bahan_km"):
        if not match_bahan(bahan_file, matched["bahan_km"]):
            log_skip("bahan tidak sesuai: {} vs {}".format(bahan_file, matched["bahan_km"]), nota)
            return

    if qty_file and matched.get("qty_km"):
        try:
            qty_km_int = int(matched["qty_km"])
            if qty_file != qty_km_int:
                log_skip("jumlah tidak sesuai: {} vs {}".format(qty_file, qty_km_int), nota)
                return
        except ValueError:
            pass

    detail = client.get_detail(matched["data_id"])
    if not detail or not detail.get("flow"):
        print(f"  [KMMA-E05] {nota} - gagal ambil detail")
        return

    step = detail["flow"][0]
    id_step = step["idproduct_step"]
    id_td = step["idtransaction_detail"]

    flow = client.get_detail_flow(id_step, id_td)
    if not flow:
        print(f"  [KMMA-E05] {nota} - gagal ambil form options")
        return

    mat_id = None
    mat_name = ""
    for m in flow.get("material", []):
        if bahan_file and match_bahan(bahan_file, m["material_name"]):
            mat_id = m["idproduct_material"]
            mat_name = m["material_name"]
            break

    if not mat_id:
        print(f"  [KMMA-E03] {nota} - bahan '{bahan_file}' tidak ada di dropdown KM")
        return

    mac_id = None
    mac_name = ""
    for mc in flow.get("machine", []):
        if machine_wma.lower() in mc["machine_name"].lower():
            mac_id = mc["idproduct_machine"]
            mac_name = mc["machine_name"]
            break
    if not mac_id:
        for mc in flow.get("machine", []):
            if "develop" in machine_wma.lower() and "develop" in mc["machine_name"].lower():
                mac_id = mc["idproduct_machine"]
                mac_name = mc["machine_name"]
                break
            elif "ricoh" in machine_wma.lower() and "ricoh" in mc["machine_name"].lower():
                mac_id = mc["idproduct_machine"]
                mac_name = mc["machine_name"]
                break

    if not mac_id:
        print(f"  [KMMA-E05] {nota} - mesin '{machine_wma}' tidak ada di dropdown KM")
        return

    sdm_id = None
    sdm_name = ""
    for s in flow.get("sdm", []):
        if operator_wma.lower() == s["name"].lower():
            sdm_id = s["id"]
            sdm_name = s["name"]
            break
    if not sdm_id:
        print(f"  [KMMA-E05] {nota} - operator '{operator_wma}' tidak ada di dropdown KM")
        return

    print(f"  [OK] {nota} - {matched.get('bahan_km', '?')} x {qty_file} - {mat_name} | {mac_name} | {sdm_name}")

    payload = {
        "flow_material_0[]": mat_id,
        "is_flow_material_manual_0[]": "0",
        "flow_machine_0": mac_id,
        "flow_qty_0": str(qty_file),
        "flow_sdm_0[]": sdm_id,
        "flow_id": "",
        "id": id_step,
        "idtransaction_detail": id_td,
        "idtransaction_transfer": "",
        "idtransaction_reproduction": "",
    }

    ok, msg = client.save_flow(payload)
    if ok:
        print(f"  [KMMA-OK] {nota} - SIMPAN berhasil")
    else:
        print(f"  [KMMA-E06] {nota} - SIMPAN gagal: {msg}")


def run():
    env = load_env()
    username = env.get("KMMA_USERNAME")
    password = env.get("KMMA_PASSWORD")
    if not username or not password:
        print("  [KMMA-E01] credentials tidak ada di env/kmma/.env")
        return

    print("  ===== KMMA - KonsepMedia Module Auto =====")
    print(f"  polling {POLL_INTERVAL // 60} menit | jeda {ACTION_DELAY} dtk | API {API_DELAY} dtk")

    client = KMClient()

    while True:
        entries = load_daily()
        if not entries:
            print(f"  [{datetime.datetime.now():%H:%M:%S}] wma_daily.json kosong, tunggu {POLL_INTERVAL // 60} menit...")
            time.sleep(POLL_INTERVAL)
            continue

        print(f"\n  [{datetime.datetime.now():%H:%M:%S}] {len(entries)} entries dari WMA")

        if not client.cookie:
            print("  login KonsepMedia...")
            if not client.login(username, password):
                print("  [KMMA-E01] login gagal, retry 1 menit...")
                time.sleep(60)
                continue
            print("  login OK")

        for entry in entries:
            process_entry(client, entry)
            time.sleep(ACTION_DELAY)

        print(f"  selesai, tunggu {POLL_INTERVAL // 60} menit...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n  stop.")

