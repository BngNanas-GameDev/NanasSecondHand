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
    // Bucket A3+ (325x487): portrait / landscape / oversize
    if w <= 320 && h <= 485 {
        "1-320x1-485".to_string()
    } else if w <= 485 && h <= 320 {
        "1-485x1-320".to_string()
    } else {
        "oversize".to_string()
    }
}

fn find_uk(low: &str) -> Option<String> {
    // \d+x\d+mm pertama -> bucket
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
                    return Some(bucket_uk(w, h));
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
        words.push(w.to_string());
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

// ---------------- main ----------------
fn esc(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() {
        eprintln!("pakai: rs_sidecar.exe \"<nama file>\"");
        std::process::exit(2);
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
    let mut parts: Vec<String> = vec![format!("\"state\":\"{}\"", esc(&state))];
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
