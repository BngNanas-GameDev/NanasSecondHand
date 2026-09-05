//! rs_sidecar: baca Q-table JSON + hitung kunci pola + jawab best-action per kategori.
//! std-only (tanpa crates). Output: satu baris JSON.
//! Pakai: rs_sidecar.exe "<nama file>"
use std::env;
use std::path::PathBuf;

// ---------------- JSON minimal: {"k": {"a": float}} ----------------
enum J {
    Obj(Vec<(String, J)>), // Vec = urutan file terjaga (tie-break sama dgn Python)
    Num(f64),
    Str(String),
}

struct Pr<'a> {
    b: &'a [u8],
    i: usize,
}

impl<'a> Pr<'a> {
    fn ws(&mut self) {
        while self.i < self.b.len() && (self.b[self.i] as char).is_whitespace() {
            self.i += 1;
        }
    }
    fn eat(&mut self, c: u8) -> bool {
        if self.b.get(self.i) == Some(&c) {
            self.i += 1;
            true
        } else {
            false
        }
    }
    fn parse_str(&mut self) -> String {
        assert!(self.eat(b'"'), "expected string");
        let mut s = String::new();
        loop {
            let c = self.b[self.i];
            if c == b'"' {
                self.i += 1;
                break;
            }
            if c == b'\\' {
                self.i += 1;
                let e = self.b[self.i];
                match e {
                    b'n' => s.push('\n'),
                    b't' => s.push('\t'),
                    b'r' => s.push('\r'),
                    b'u' => {
                        let h = std::str::from_utf8(&self.b[self.i + 1..self.i + 5])
                            .unwrap_or("003f");
                        let cp = u32::from_str_radix(h, 16).unwrap_or(0x3f);
                        s.push(char::from_u32(cp).unwrap_or('?'));
                        self.i += 4;
                    }
                    _ => s.push(e as char),
                }
                self.i += 1;
            } else {
                let rest = std::str::from_utf8(&self.b[self.i..]).unwrap_or("");
                let ch = rest.chars().next().unwrap_or('?');
                s.push(ch);
                self.i += ch.len_utf8();
            }
        }
        s
    }
    fn parse_num(&mut self) -> f64 {
        let st = self.i;
        while self.i < self.b.len() && !b",}] \t\n\r".contains(&self.b[self.i]) {
            self.i += 1;
        }
        std::str::from_utf8(&self.b[st..self.i])
            .unwrap_or("0")
            .parse()
            .unwrap_or(0.0)
    }
    fn parse_val(&mut self) -> J {
        self.ws();
        match self.b.get(self.i) {
            Some(b'{') => self.parse_obj(),
            Some(b'"') => J::Str(self.parse_str()),
            _ => J::Num(self.parse_num()),
        }
    }
    fn parse_obj(&mut self) -> J {
        assert!(self.eat(b'{'));
        let mut v = Vec::new();
        loop {
            self.ws();
            if self.eat(b'}') {
                break;
            }
            let k = self.parse_str();
            self.ws();
            assert!(self.eat(b':'));
            let val = self.parse_val();
            v.push((k, val));
            self.ws();
            if self.eat(b',') {
                continue;
            }
        }
        J::Obj(v)
    }
}

// ---------------- kamus typo (mirror bahan_dict.TYPO_MAP) ----------------
fn typo_fix(w: &str) -> String {
    const MAP: &[(&str, &str)] = &[
        ("cromo", "kromo"),
        ("chromo", "kromo"),
        ("kroomo", "kromo"),
        ("komo", "kromo"),
        ("sriker", "stiker"),
        ("stker", "stiker"),
        ("sicker", "stiker"),
        ("sticker", "stiker"),
        ("vynil", "vinyl"),
        ("vinil", "vinyl"),
        ("vynyl", "vinyl"),
        ("finyl", "vinyl"),
        ("vinly", "vinyl"),
        ("jasmin", "jasmine"),
        ("concorde", "concord"),
        ("trasparant", "transparant"),
        ("transparan", "transparant"),
        ("hps", "hvs"),
        ("hfs", "hvs"),
        ("rajawli", "rajawali"),
        ("rajwali", "rajawali"),
        ("hamji", "hanji"),
        ("haji", "hanji"),
        ("artpaper", "art paper"),
        ("artcarton", "art carton"),
    ];
    for (k, v) in MAP {
        if *k == w {
            return v.to_string();
        }
    }
    w.to_string()
}

// ---------------- parsed: bahan/ukuran/duplex/dx/finishing/repeat (mirror llm_teacher_preset) ----------------
const CANON: &[(&str, &str)] = &[
    ("transparant", "Transparant"),
    ("art carton", "Art Carton"),
    ("art paper", "Art Paper"),
    ("rajawali", "Rajawali"),
    ("hologram", "Hologram"),
    ("hvs100gr", "Hvs100gr"),
    ("ac260gr", "Ac260gr"),
    ("ac190gr", "Ac190gr"),
    ("ac230gr", "Ac230gr"),
    ("ac310gr", "Ac310gr"),
    ("ap120gr", "Ap120gr"),
    ("ap150gr", "Ap150gr"),
    ("ap190gr", "Ap190gr"),
    ("concord", "Concord"),
    ("concorde", "Concord"),
    ("jasmine", "Jasmine"),
    ("silver", "Silver"),
    ("vinyl", "Vinyl"),
    ("kromo", "Kromo"),
    ("pindo", "Pindo"),
    ("ivory", "Ivory"),
    ("gold", "Gold"),
    ("hvs", "Hvs100gr"),
];

fn fix_text(low: &str) -> String {
    // ganti tiap kata typo, karakter lain (angka/spasi) dipertahankan (mirror fix_typos)
    let mut out = String::new();
    let mut w = String::new();
    for ch in low.chars() {
        if ch.is_ascii_alphabetic() {
            w.push(ch);
        } else {
            if !w.is_empty() {
                out.push_str(&typo_fix(&w));
                w.clear();
            }
            out.push(ch);
        }
    }
    if !w.is_empty() {
        out.push_str(&typo_fix(&w));
    }
    out
}

fn strip_word_2s(s: &str, w: &str) -> String {
    // buang "<w>\s*2s" tanpa batas kata (mirror re.sub Python)
    let mut out = String::new();
    let mut rest = s;
    loop {
        match rest.find(w) {
            Some(p) => {
                let mut k = p + w.len();
                let rb = rest.as_bytes();
                while k < rb.len() && rb[k] == b' ' {
                    k += 1;
                }
                if rest[k..].starts_with("2s") {
                    out.push_str(&rest[..p]);
                    out.push(' ');
                    rest = &rest[k + 2..];
                } else {
                    out.push_str(&rest[..p + 1]);
                    rest = &rest[p + 1..];
                }
            }
            None => {
                out.push_str(rest);
                break;
            }
        }
    }
    out
}

fn strip_fin_2s(low: &str) -> String {
    // finishing TANPA hologram (hologram = bahan, kondisional terpisah)
    let fins = [
        "doff", "dof", "laminasi", "laminating", "glossy", "gloss", "matte", "canvas",
        "uv", "varnish",
    ];
    let mut tmp = format!(" {} ", low);
    for f in fins {
        tmp = strip_word_2s(&tmp, f);
    }
    tmp
}

fn strip_hologram_cond(tmp: &str, fixed: &str) -> String {
    // hologram = finishing hanya jika ada bahan lain
    if tmp.contains("hologram")
        && CANON.iter().any(|(k, _)| *k != "hologram" && fixed.contains(k))
    {
        let mut s = String::new();
        let mut rest = tmp;
        loop {
            match rest.find("hologram") {
                Some(p) => {
                    let mut k = p + 8;
                    let rb = rest.as_bytes();
                    while k < rb.len() && rb[k] == b' ' {
                        k += 1;
                    }
                    if rest[k..].starts_with("2s") {
                        s.push_str(&rest[..p]);
                        s.push(' ');
                        rest = &rest[k + 2..];
                    } else {
                        s.push_str(&rest[..p + 1]);
                        rest = &rest[p + 1..];
                    }
                }
                None => {
                    s.push_str(rest);
                    break;
                }
            }
        }
        return s;
    }
    tmp.to_string()
}

fn guess_bahan(low: &str) -> Option<String> {
    let fixed = fix_text(low);
    let t = strip_hologram_cond(&strip_fin_2s(&fixed), &fixed);
    let b = t.as_bytes();
    // (ac|ap)\d+\s*gr
    let mut i = 0;
    while i + 1 < b.len() {
        if (b[i] == b'a') && (b[i + 1] == b'c' || b[i + 1] == b'p') {
            let mut j = i + 2;
            while j < b.len() && is_digit(b[j]) {
                j += 1;
            }
            if j > i + 2 {
                let mut k = j;
                while k < b.len() && b[k] == b' ' {
                    k += 1;
                }
                if t[k..].starts_with("gr") {
                    let mut s = format!("{}gr", &t[i..j]);
                    s[0..1].make_ascii_uppercase();
                    return Some(s);
                }
            }
            i = j;
        } else {
            i += 1;
        }
    }
    for (k, v) in CANON {
        if t.contains(k) {
            return Some(v.to_string());
        }
    }
    None
}

fn parse_duplex(low: &str) -> String {
    // hologram = stiker, tidak mungkin cetak 2s -> SELALU finishing di sini.
    // (untuk bahan, hologram tetap kertas -> lihat guess_bahan/strip_hologram_cond)
    // Stiker (Vinyl/Hologram/Gold/Silver, Kromo+stiker) TIDAK PERNAH 2s.
    // Kromo KERTAS (tanpa kata stiker) bisa 1s/2s normal.
    if let Some(b) = guess_bahan(low) {
        if ["Vinyl", "Hologram", "Gold", "Silver"].contains(&b.as_str()) {
            return "1s".to_string();
        }
        if b == "Kromo" && (low.contains("stiker") || low.contains("sticker")) {
            return "1s".to_string();
        }
    }
    if low.contains("data sama") || low.contains("bolak balik sama") {
        return "dr".to_string();
    }
    let tmp = strip_word_2s(&strip_fin_2s(&format!(" {} ", low)), "hologram");
    if tmp.contains("2s")
        || low.contains("bolak")
        || low.contains("dua muka")
        || low.contains("depan belakang")
        || low.contains("2 sisi")
    {
        return "2s".to_string();
    }
    "1s".to_string()
}

fn parse_dx(original: &str) -> Option<String> {
    // 1d\d+\s*[=:@]*\s*@?\d[\d.]*\s*(KECIL|BESAR), kapital unit ikut aslinya
    let low = original.to_lowercase();
    if !original.is_ascii() {
        return parse_dx_low(&low).map(|s| s.to_lowercase());
    }
    let b = low.as_bytes();
    let ob = original.as_bytes();
    let mut i = 0;
    while i + 1 < b.len() {
        if b[i] == b'1' && b[i + 1] == b'd' {
            let mut j = i + 2;
            while j < b.len() && is_digit(b[j]) {
                j += 1;
            }
            if j == i + 2 {
                i += 1;
                continue;
            }
            let mut k = j;
            while k < b.len() && (b[k] == b'=' || b[k] == b':' || b[k] == b'@' || b[k] == b' ') {
                k += 1;
            }
            if k < b.len() && b[k] == b'@' {
                k += 1;
            }
            // angka boleh bertitik ribuan: 1.000
            if k >= b.len() || !is_digit(b[k]) {
                i += 1;
                continue;
            }
            while k < b.len() && (is_digit(b[k]) || b[k] == b'.') {
                k += 1;
            }
            while k < b.len() && b[k] == b' ' {
                k += 1;
            }
            let ulen = if low[k..].starts_with("kecil") {
                5
            } else if low[k..].starts_with("besar") {
                5
            } else {
                i += 1;
                continue;
            };
            let raw = std::str::from_utf8(&ob[i..k + ulen]).unwrap_or(&original[i..i]);
            return Some(raw.split_whitespace().collect::<Vec<_>>().join(" "));
        }
        i += 1;
    }
    None
}

// fallback utk nama non-ASCII: kerja di string-lower (unit ikut lower)
fn parse_dx_low(low: &str) -> Option<String> {
    let b = low.as_bytes();
    let mut i = 0;
    while i + 1 < b.len() {
        if b[i] == b'1' && b[i + 1] == b'd' {
            let mut j = i + 2;
            while j < b.len() && is_digit(b[j]) {
                j += 1;
            }
            if j == i + 2 {
                i += 1;
                continue;
            }
            let mut k = j;
            while k < b.len() && (b[k] == b'=' || b[k] == b':' || b[k] == b'@' || b[k] == b' ') {
                k += 1;
            }
            if k < b.len() && b[k] == b'@' {
                k += 1;
            }
            if k >= b.len() || !is_digit(b[k]) {
                i += 1;
                continue;
            }
            while k < b.len() && (is_digit(b[k]) || b[k] == b'.') {
                k += 1;
            }
            while k < b.len() && b[k] == b' ' {
                k += 1;
            }
            let ulen = if low[k..].starts_with("kecil") || low[k..].starts_with("besar") {
                5
            } else {
                i += 1;
                continue;
            };
            return Some(low[i..k + ulen].split_whitespace().collect::<Vec<_>>().join(" "));
        }
        i += 1;
    }
    None
}

fn parse_repeat(low: &str) -> String {
    let is_booklet = low.contains("booklet") || low.contains("staples");
    // mirror re.search greedy: anchor 1d paling kiri, '@' valid TERAKHIR
    let (last_kecil, any_besar) = repeat_parts(low);
    // @besar dulu (mirror llm_zen)
    if any_besar {
        return "repeat".to_string();
    }
    if let Some(x) = last_kecil {
        if is_booklet {
            return if x == "1" {
                "booklet(collate)".to_string()
            } else {
                "booklet(repeat)".to_string()
            };
        }
        return if x == "1" {
            "collate-cut".to_string()
        } else {
            format!("collate-cut({})", x)
        };
    }
    if is_booklet {
        return "booklet".to_string();
    }
    "repeat".to_string()
}

// ekor "@...\d+...kecil/besar" mulai dari posisi p (p = setelah '@')
fn at_tail(low: &str, p: usize) -> Option<(String, bool)> {
    let b = low.as_bytes();
    let mut m = p;
    while m < b.len() && b[m] == b' ' {
        m += 1;
    }
    let ds = m;
    while m < b.len() && is_digit(b[m]) {
        m += 1;
    }
    if m == ds {
        return None;
    }
    let num = low[ds..m].to_string();
    while m < b.len() && b[m] == b' ' {
        m += 1;
    }
    if low[m..].starts_with("kecil") {
        Some((num, false))
    } else if low[m..].starts_with("besar") {
        Some((num, true))
    } else {
        None
    }
}

fn repeat_parts(low: &str) -> (Option<String>, bool) {
    let b = low.as_bytes();
    // anchor 1d paling kiri
    let mut anchor = None;
    let mut i = 0;
    while i + 1 < b.len() {
        if b[i] == b'1' && b[i + 1] == b'd' {
            let mut j = i + 2;
            while j < b.len() && is_digit(b[j]) {
                j += 1;
            }
            if j > i + 2 {
                anchor = Some(j);
                break;
            }
            i = j;
        } else {
            i += 1;
        }
    }
    let start = match anchor {
        Some(s) => s,
        None => return (None, false),
    };
    let mut last_kecil = None;
    let mut any_besar = false;
    let mut k = start;
    while k < b.len() {
        if b[k] == b'@' {
            if let Some((num, besar)) = at_tail(low, k + 1) {
                if besar {
                    any_besar = true;
                } else {
                    last_kecil = Some(num);
                }
            }
        }
        k += 1;
    }
    (last_kecil, any_besar)
}

// ---------------- port _state_key / _key_str ----------------
fn is_digit(b: u8) -> bool {
    b.is_ascii_digit()
}
fn is_alpha(b: u8) -> bool {
    b.is_ascii_lowercase()
}

fn strip_prefix_word(s: &str, word: &str) -> String {
    // ^[^_]+_<WORD>_+  (s sudah lowercase)
    if let Some(p) = s.find('_') {
        if p > 0 {
            let after = &s[p + 1..];
            if after.starts_with(word) {
                let mut k = word.len();
                let ab = after.as_bytes();
                while k < ab.len() && ab[k] == b'_' {
                    k += 1;
                }
                if k > word.len() {
                    return after[k..].to_string();
                }
            }
        }
    }
    s.to_string()
}

fn strip_paren_a_n_l(s: &str) -> String {
    // \(a\d+l[^)]*\) -> spasi
    let b = s.as_bytes();
    let mut out = String::new();
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'(' {
            let mut j = i + 1;
            if j < b.len() && b[j] == b'a' {
                j += 1;
                let ds = j;
                while j < b.len() && is_digit(b[j]) {
                    j += 1;
                }
                if j > ds && j < b.len() && b[j] == b'l' {
                    j += 1;
                    while j < b.len() && b[j] != b')' {
                        j += 1;
                    }
                    if j < b.len() {
                        out.push(' ');
                        i = j + 1;
                        continue;
                    }
                }
            }
        }
        out.push(b[i] as char);
        i += 1;
    }
    out
}

fn strip_on_digits(s: &str) -> String {
    // on\d+ -> spasi
    let b = s.as_bytes();
    let mut out = String::new();
    let mut i = 0;
    while i < b.len() {
        if s[i..].starts_with("on") {
            let mut j = i + 2;
            while j < b.len() && is_digit(b[j]) {
                j += 1;
            }
            if j > i + 2 {
                out.push(' ');
                i = j;
                continue;
            }
        }
        out.push(b[i] as char);
        i += 1;
    }
    out
}

fn normalize(s: &str) -> String {
    let low = s.to_lowercase();
    let mut out = String::new();
    let mut sp = true;
    for ch in low.chars() {
        if ch.is_ascii_alphanumeric() {
            out.push(ch);
            sp = false;
        } else if !sp {
            out.push(' ');
            sp = true;
        }
    }
    out.trim().to_string()
}

fn word_az_digits(w: &str) -> bool {
    let b = w.as_bytes();
    if b.is_empty() {
        return false;
    }
    let mut i = 0;
    while i < b.len() && is_alpha(b[i]) {
        i += 1;
    }
    if i == 0 {
        return false;
    }
    let mut j = i;
    while j < b.len() && is_digit(b[j]) {
        j += 1;
    }
    j > i && j == b.len()
}

fn bucket_uk(w: u32, h: u32) -> String {
    // Area cetak 320x482 (kertas 325x487): portrait / landscape / oversize
    if w <= 320 && h <= 482 {
        "1-320x1-482".to_string()
    } else if w <= 482 && h <= 320 {
        "1-482x1-320".to_string()
    } else {
        "oversize".to_string()
    }
}

fn find_uk(low: &str) -> Option<String> {
    find_uk_exact(low).map(|(w, h)| bucket_uk(w, h))
}

fn find_uk_exact(low: &str) -> Option<(u32, u32)> {
    // \d+x\d+mm pertama -> dimensi eksak (data, bukan kunci)
    let b = low.as_bytes();
    let mut i = 0;
    while i < b.len() {
        if is_digit(b[i]) {
            let mut j = i;
            while j < b.len() && is_digit(b[j]) {
                j += 1;
            }
            let w: u32 = low[i..j].parse().unwrap_or(0);
            if j < b.len() && b[j] == b'x' {
                let mut k = j + 1;
                while k < b.len() && is_digit(b[k]) {
                    k += 1;
                }
                if k > j + 1 && low[k..].starts_with("mm") {
                    let h: u32 = low[j + 1..k].parse().unwrap_or(0);
                    return Some((w, h));
                }
            }
            i = j;
        } else {
            i += 1;
        }
    }
    None
}

fn find_dx(low: &str) -> Option<String> {
    // 1d\d+ pertama
    let b = low.as_bytes();
    let mut i = 0;
    while i + 1 < b.len() {
        if b[i] == b'1' && b[i + 1] == b'd' {
            let mut j = i + 2;
            while j < b.len() && is_digit(b[j]) {
                j += 1;
            }
            if j > i + 2 {
                return Some(low[i..j].to_string());
            }
            i = j;
        } else {
            i += 1;
        }
    }
    None
}

fn state_key(filename: &str) -> String {
    let low = filename.to_lowercase();
    let mut tmp = strip_prefix_word(&low, "ditunggu");
    tmp = strip_prefix_word(&tmp, "tunggu");
    tmp = strip_paren_a_n_l(&tmp);
    tmp = strip_on_digits(&tmp);
    let fnorm = normalize(&tmp);
    let stop = ["pdf", "dan", "untuk", "lembar", "ditunggu", "tunggu"];
    let mut words: Vec<String> = Vec::new();
    for w in fnorm.split_whitespace() {
        if w.chars().count() < 3 {
            continue;
        }
        // angka murni = noise (TOTAL/jumlah)
        if !w.is_empty() && w.bytes().all(is_digit) {
            continue;
        }
        // ukuran eksak (\d+x\d+mm) -> cukup bucketnya
        let b0 = w.as_bytes();
        let mut di = 0;
        while di < b0.len() && is_digit(b0[di]) {
            di += 1;
        }
        let mut is_size = false;
        if di > 0 && di < b0.len() && b0[di] == b'x' {
            let mut dj = di + 1;
            while dj < b0.len() && is_digit(b0[dj]) {
                dj += 1;
            }
            if dj > di + 1 && dj + 2 == b0.len() && &w[dj..] == "mm" {
                is_size = true;
            }
        }
        if is_size {
            continue;
        }
        if stop.contains(&w) {
            continue;
        }
        if word_az_digits(w) {
            continue;
        }
        // ^a\d+l$
        let b = w.as_bytes();
        if b.len() >= 3 && b[0] == b'a' && b[b.len() - 1] == b'l' && b[1..b.len() - 1].iter().all(|c| is_digit(*c)) {
            continue;
        }
        // ^on\d+$
        if w.starts_with("on") && w.len() > 2 && w[2..].bytes().all(is_digit) {
            continue;
        }
        // normalisasi typo: hamji->hanji, sriker->stiker, dst. (mirror Python)
        for part in typo_fix(w).split_whitespace() {
            words.push(part.to_string());
            if words.len() >= 4 {
                break;
            }
        }
        if words.len() >= 4 {
            break;
        }
    }
    if let Some(u) = find_uk(&low) {
        if !words.contains(&u) {
            words.push(u);
        }
    }
    if let Some(d) = find_dx(&low) {
        if !words.contains(&d) {
            words.push(d);
        }
    }
    let mut v: Vec<String> = words.into_iter().take(5).collect();
    v.sort();
    v.dedup(); // = frozenset Python: kata dobel dibuang
    v.join("|")
}

// ---------------- generate: ribuan filename sintetis dari master-list ----------------
fn run_generate(n: usize) {
    let bahan = [
        "Ac260gr", "Ac230gr", "Ac190gr", "Ac150gr", "Ac120gr", "Ap120gr", "Ap150gr",
        "Ap190gr", "Vinyl", "Kromo", "Hvs100gr", "Concord", "Jasmine", "Rajawali",
        "Pindo", "Ivory", "Gold", "Silver", "Transparant",
    ];
    let duplex = ["1s", "2s", "1s", "2s", "1s", "dr"];
    let dx = [
        "(1d1 = 1 KECIL)",
        "(1d2 = 2 KECIL)",
        "(1d3 = 3 KECIL)",
        "(1d4 = 60 KECIL)",
        "(1d6 = 12 KECIL)",
        "(1d8 = 8 KECIL)",
        "(1d12 = 24 KECIL)",
        "(1d24 = 120 KECIL)",
        "(1d25 = 100 KECIL)",
        "(1d40 = 200 KECIL)",
        "(1d50 = 50 KECIL)",
        "(1d2 = @2 KECIL)",
        "(1d25 = @11 KECIL)",
        "(1d4 = @4 KECIL @1 BESAR)",
        "(1d1 = @1BESAR)",
    ];
    let size = [
        "(uk.1x1mm)",
        "(uk.2x2mm)",
        "(uk.1x2mm)",
        "(uk.1x3mm)",
        "(uk.60x90mm)",
        "(uk.59x94mm)",
        "(uk.100x180mm)",
        "(uk.250x400mm)",
        "(uk.480x320mm)",
        "(uk.320x480mm)",
        "(uk.297x210mm)",
        "(uk.210x297mm)",
    ];
    let fin = ["(Potong)", "(Manual Cutter)", "(Potong Bleed 2mm)", "(Potong)"];
    let extra = ["", "", "", " Booklet", " Staples tengah", " (Doff 2s)"];
    for i in 0..n {
        // langkah koprima biar kombinasi tercampur deterministik
        let b = bahan[(i * 7) % bahan.len()];
        let d = duplex[(i * 11) % duplex.len()];
        let dpx = if d == "dr" { "bolak balik sama" } else { d };
        let x = dx[(i * 13) % dx.len()];
        let s = size[(i * 5) % size.len()];
        let f = fin[(i * 3) % fin.len()];
        let e = extra[(i * 17) % extra.len()];
        println!("R{:05}_{} {} {} {} - {}{}.pdf", i, b, dpx, s, x, f, e);
    }
}

// ---------------- main ----------------
fn esc(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() {
        eprintln!("pakai: rs_sidecar.exe \"<nama file>\" | --generate N");
        std::process::exit(2);
    }
    if args[0] == "--generate" {
        let n: usize = args.get(1).and_then(|s| s.parse().ok()).unwrap_or(3000);
        run_generate(n);
        return;
    }
    let filename = args.join(" ");
    let exe = env::current_exe().unwrap_or_else(|_| PathBuf::from("."));
    let base = exe.parent().unwrap_or(std::path::Path::new("."));
    let cats = ["sheet", "bahan", "duplex", "dx", "finishing", "repeat"];
    let defaults = [
        ("sheet", "A3+ Full (32.5x48.7cm)"),
        ("bahan", "-"),
        ("duplex", "1s"),
        ("dx", "-"),
        ("finishing", "crop"),
        ("repeat", "repeat"),
    ];
    let state = state_key(&filename);
    let uk_exact = find_uk_exact(&filename.to_lowercase())
        .map(|(w, h)| format!("{}x{}mm", w, h));
    let mut parts: Vec<String> = vec![format!("\"state\":\"{}\"", esc(&state))];
    match &uk_exact {
        Some(u) => parts.push(format!("\"uk_exact\":\"{}\"", esc(u))),
        None => parts.push("\"uk_exact\":null".to_string()),
    }
    // blok parsed: bahan/ukuran/duplex/dx/finishing/repeat
    let low = filename.to_lowercase();
    let pb = match guess_bahan(&low) {
        Some(b) => format!("\"{}\"", esc(&b)),
        None => "null".to_string(),
    };
    let pu = match uk_exact {
        Some(u) => format!("\"{}\"", esc(&u)),
        None => "null".to_string(),
    };
    let pdx = match parse_dx(&filename) {
        Some(d) => format!("\"{}\"", esc(&d)),
        None => "null".to_string(),
    };
    let pfin = if low.contains("potong bleed") || low.contains("bleed 2mm") {
        "bleed"
    } else {
        "crop"
    };
    parts.push(format!(
        "\"parsed\":{{\"bahan\":{},\"ukuran\":{},\"duplex\":\"{}\",\"dx\":{},\"finishing\":\"{}\",\"repeat\":\"{}\"}}",
        pb,
        pu,
        parse_duplex(&low),
        pdx,
        pfin,
        esc(&parse_repeat(&low))
    ));
    for (cat, def) in cats.iter().zip(defaults.iter().map(|(_, d)| *d)) {
        let path = base
            .join("data")
            .join("memory_rl")
            .join(format!("{}.json", cat));
        let mut action = def.to_string();
        let mut q = 0.0;
        let mut cold = true;
        if let Ok(txt) = std::fs::read_to_string(&path) {
            let mut pr = Pr {
                b: txt.as_bytes(),
                i: 0,
            };
            if let J::Obj(top) = pr.parse_val() {
                for (st, v) in top {
                    if st == state {
                        if let J::Obj(acts) = v {
                            let mut best: Option<(String, f64)> = None;
                            for (a, vv) in acts {
                                if let J::Num(n) = vv {
                                    match &best {
                                        Some((_, o)) if *o >= n => {}
                                        _ => best = Some((a, n)),
                                    }
                                }
                            }
                            if let Some((a, n)) = best {
                                action = a;
                                q = n;
                                cold = false;
                            }
                        }
                        break;
                    }
                }
            }
        }
        parts.push(format!(
            "\"{}\":{{\"action\":\"{}\",\"q\":{},\"cold\":{}}}",
            cat,
            esc(&action),
            q,
            if cold { "true" } else { "false" }
        ));
    }
    println!("{{{}}}", parts.join(","));
}
