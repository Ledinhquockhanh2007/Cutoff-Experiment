#!/usr/bin/env python3
"""
make_tables_p2.py (T14): sinh bảng LaTeX báo cáo bản 2 (report/tables/*.tex) từ các CSV phân tích
giai đoạn xác nhận và chẩn đoán và vài tệp nguồn khác. Chỉ sinh SỐ LIỆU và nhãn kỹ thuật, không sinh câu văn nội dung.

Chạy từ thư mục gốc dự án:   python report/make_tables_p2.py
Bảng giai đoạn khám phá (tables/p1/) do report/make_tables.py sinh.

Nguồn (chỉ đọc):
  P2  = results_phase2/analysis/tables       (T10)
  P2B = results_phase2b/analysis/tables      (T12)
  V2  = results_final/analysis_v2/tables     (mô hình chi phí, bộ nhớ của giai đoạn khám phá)
  PR  = preregistration              (mô tả giả thuyết)
  results_correctness/correctness_jdk25.txt       (CorrectnessTest, chạy lại ở T14)
  results_*/env_fork*.txt, raw_fork*.csv     (thiết kế và thời gian các phiên, bảng t03)
  git log                                    (hash commit; không gõ tay)

Quy tắc A (README): in bảng đối chiếu (số tính | số tham chiếu của đề T14 | chênh) và ghi
report/_check/ruleA_check_T14.txt; nếu lệch quá dung sai làm tròn hiển thị: thoát mã 1.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "report"))
import make_tables as mt  # noqa: E402  (tiện ích định dạng: sc, pct, num, esc, hc, tabular, pval)

P2 = ROOT / "results_phase2" / "analysis" / "tables"
P2B = ROOT / "results_phase2b" / "analysis" / "tables"
V2 = ROOT / "results_final" / "analysis_v2" / "tables"
PR = ROOT / "preregistration"
OUT = ROOT / "report" / "tables"
CHK = ROOT / "report" / "_check"
CMD = "python report/make_tables_p2.py"
S5 = ["2^12", "2^14", "2^16", "2^18", "2^19"]
S3 = ["2^12", "2^16", "2^19"]
DIST = {"random": "ngẫu nhiên", "sorted": "đã sắp", "reversed": "đảo ngược", "nearly_sorted": "gần sắp",
        "few_distinct": "ít giá trị"}
sc, esc, tabular, num = mt.sc, mt.esc, mt.tabular, mt.num


def hc(*lines):
    """mt.hc với mỗi dòng bọc {} (dòng bắt đầu bằng '[' không bị \\\\ hiểu là tham số tùy chọn)."""
    return mt.hc(*["{" + x + "}" for x in lines])


# ───────────────────────────────────────────────────────── tiện ích
def write(name, body, sources, note=""):
    head = f"% Nguồn: {sources}\n% Lệnh sinh: {CMD}\n% Sinh tự động, KHÔNG sửa tay (sửa make_tables_p2.py rồi chạy lại).\n"
    if note:
        head += "".join(f"% {ln}\n" for ln in note.splitlines())
    (OUT / f"{name}.tex").write_text(head + body + "\n", encoding="utf-8")
    print("wrote", name, f"({body.count(chr(92) * 2)} dòng có \\\\)")


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def commit_of(pattern: str) -> str:
    """Hash ngắn của commit có tiêu đề khớp regex (đầu dòng); lỗi nếu không có đúng 1 commit."""
    out = git("log", "--format=%h\t%s", "--all")
    hits = [ln.split("\t")[0] for ln in out.splitlines() if re.match(pattern, ln.split("\t", 1)[1])]
    if len(hits) != 1:
        raise SystemExit(f"DỪNG: mẫu commit {pattern!r} khớp {len(hits)} commit")
    return hits[0]


def f3(x):
    return f"{x:.3f}"


def f4(x):
    return f"{x:.4f}"


def ci(x, lo, hi, d=3):
    return f"{x:.{d}f} [{lo:.{d}f}, {hi:.{d}f}]"


def near(s):
    return esc(str(s)).replace("..", "--")


def longtable(colspec, head, rows, caption, label, size="\\footnotesize"):
    h = " & ".join(head) + " \\\\"
    s = [f"{size}", f"\\begin{{longtable}}{{{colspec}}}", f"\\caption{{{caption}}}\\label{{{label}}}\\\\",
         "\\toprule", h, "\\midrule", "\\endfirsthead",
         f"\\multicolumn{{{len(head)}}}{{l}}{{\\textit{{(tiếp theo)}}}}\\\\", "\\toprule", h, "\\midrule", "\\endhead",
         "\\bottomrule", "\\endlastfoot"]
    for r in rows:
        s.append(r if isinstance(r, str) else " & ".join(r) + " \\\\")
    s.append("\\end{longtable}")
    return "\n".join(s)


def sym(txt: str) -> str:
    """Chuỗi văn bản thuần (đã esc) -> thay ký hiệu Unicode/ASCII bằng toán LaTeX."""
    t = esc(txt)
    for a, b in [("->", "\u0001to\u0002"), ("<=", "\u0001le\u0002"), (">=", "\u0001ge\u0002"), ("≤", "\u0001le\u0002"), ("≥", "\u0001ge\u0002"),
                 ("→", "\u0001to\u0002"), ("−", "\u0001minus\u0002"), ("×", "\u0001times\u0002"), ("α", "\u0001alpha\u0002"),
                 ("Δ", "\u0001Delta\u0002"), ("±", "\u0001pm\u0002"), ("<", "\u0001lt\u0002"), (">", "\u0001gt\u0002")]:
        t = t.replace(a, b)
    rep = {"le": "$\\le$", "ge": "$\\ge$", "to": "$\\to$", "minus": "$-$", "times": "$\\times$", "alpha": "$\\alpha$",
           "Delta": "$\\Delta$", "pm": "$\\pm$", "lt": "$<$", "gt": "$>$"}
    t = re.sub("\u0001(\\w+)\u0002", lambda m: rep[m[1]], t)
    t = re.sub(r"(?<![A-Za-z0-9])2\\\^\{\}(\d+)", r"$2^{\1}$", t)
    return t.replace("$$", "${}$")   # hai khối toán liền nhau không được thành $$ (display math)


def R(w: str) -> str:
    """Cột p{w} canh trái (không giãn chữ trong ô hẹp)."""
    return ">{\\raggedright\\arraybackslash}p{" + w + "}"


def brk(t: str) -> str:
    """Cho phép xuống dòng sau '_', ',', '=', '/' trong ô hẹp (chuỗi đã là LaTeX)."""
    t = t.replace("\\_", "\\_\\allowbreak{}")
    t = re.sub(r"(?<!\\),(?! )", lambda m: ",\\allowbreak{}", t)
    t = re.sub(r"=(?![^$]*\$)", lambda m: "=\\allowbreak{}", t)
    for op in ["$<$", "$>$", "$\\le$", "$\\ge$"]:
        t = t.replace(op, op + "\\allowbreak{}")
    return t


def stack(v, lo, hi, d=3):
    return f"\\makecell{{{v:.{d}f} \\\\ {{[{lo:.{d}f}, {hi:.{d}f}]}}}}"


CHECKS = []


def check(label, computed, ref, tol):
    CHECKS.append((label, float(computed), float(ref), float(tol)))


def report_checks():
    lines = [f"{'Mục':<46}{'số tính':>16}{'tham chiếu (đề T14)':>22}{'chênh':>14}  kết quả"]
    bad = 0
    for label, c, r, tol in CHECKS:
        d = c - r
        ok = abs(d) <= tol + 1e-12
        bad += (not ok)
        lines.append(f"{label:<46}{c:>16.6f}{r:>22.6f}{d:>+14.6f}  {'OK' if ok else 'MISMATCH'} (dung sai {tol:g})")
    txt = "\n".join(lines)
    CHK.mkdir(parents=True, exist_ok=True)
    (CHK / "ruleA_check_T14.txt").write_text(txt + f"\n\nMISMATCH: {bad}\n", encoding="utf-8")
    print("\n=== Quy tắc A (T14) ===\n" + txt + f"\nMISMATCH: {bad}")
    return bad


def env_seconds(paths):
    tot = 0
    for p in paths:
        m = re.search(r"elapsed=(\d+):(\d+):(\d+)", p.read_text(encoding="utf-8", errors="replace"))
        tot += int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
    return tot


def hm(sec):
    sec = int(round(sec))
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}"


# ───────────────────────────────────────────────────────── t01, t01b, t02
VI_CORRECTNESS = {
    "00": r"JVM chạy với \texttt{-ea}",
    "01": r"\texttt{DataGenerator}: giá trị, mã hóa, tính xác định, kế hoạch sinh dữ liệu (168 bộ, seed không trùng)",
    "02": r"Mảng ra đã sắp ($0 \le N \le 300$, $1 \le c \le 70$, 5 phân bố)",
    "03": r"Đầu ra là hoán vị của đầu vào (so với \texttt{Arrays.sort})",
    "04": r"\texttt{MergeCutoff} và \texttt{MergeCutoffCounted} cho cùng kết quả (cùng đối tượng, cùng thứ tự)",
    "05": r"Tính ổn định (\texttt{Item(key, idx)})",
    "06": r"$c < 1$ ném \texttt{IllegalArgumentException}",
    "07": r"$\frac{1}{2} N \lg N \le C \le N \lg N$ ($c = 1$, $N = 2^k$)",
    "08": r"$D = N(\lg N - p)$ ($N = 2^k$, $c = 2^p$, $p < k$)",
    "09": r"$S$ khớp với mô phỏng cây đệ quy (cài đặt độc lập)",
    "10": r"$A = 4D + 2C + 4E$",
    "11": r"$E$ bằng số nghịch thế của mảng gốc trên các lá (cài đặt độc lập)",
    "12": r"Chỉ insertion sort (cả mảng là một lá, $1 \le k \le 50$): mảng đã sắp và đảo ngược",
    "13": r"Không có ngoại lệ ngoài dự kiến",
    "14": r"\texttt{MergeCutoff} (bản đo thời gian) đi qua cùng cây đệ quy: số phép so sánh khớp",
    "15": r"CUTOFF mở rộng tới 4096 (\texttt{sorted}, \texttt{nearly\_sorted}, \texttt{reversed}), $N$ tới 8192",
    "16": r"\texttt{MergeCutoffInt} cho cùng kết quả và cùng số phép so sánh với \texttt{MergeCutoff}",
    "17": r"\texttt{MergeCutoffInt}, CUTOFF mới ($56 \le c \le 256$) trên các $N$ biên và $N$ của các thang",
}
VI_KQ = {"PASS": "Đạt", "FAIL": "Không đạt"}


def t01_correctness():
    src = ROOT / "results_correctness" / "correctness_jdk25.txt"
    txt = src.read_text(encoding="utf-8")
    jdk = re.search(r"^# java\.version: (.+)$", txt, re.M)
    rows = []
    for m in re.finditer(r"^(\d\d)\. (.+?)\s+(\d+)\s+(\d+)\s+(PASS|FAIL)\s*$", txt, re.M):
        d = m[2]
        d = d.replace("<=", "\u0001LE\u0001").replace("->", "\u0001TO\u0001").replace("==", "\u0001EQ\u0001")
        d = re.sub(r"(?<=\d) x (?=[\dA-Za-z])", "\u0001TIMES\u0001", d)
        d = esc(d)
        d = (d.replace("\u0001LE\u0001", "$\\le$").replace("\u0001TO\u0001", "$\\to$").replace("\u0001EQ\u0001", "$=$")
             .replace("\u0001TIMES\u0001", " $\\times$ ").replace("<", "$<$"))
        d = VI_CORRECTNESS.get(m[1], d)
        rows.append([m[1], d, num(m[3]), num(m[4]), VI_KQ[m[5]]])
    tot = re.search(r"TOTAL: (\d+) checks, (\d+) failed", txt)
    day = re.search(r"^# Ngày chạy: (.+)$", txt, re.M)
    rows.append("\\midrule")
    rows.append(["", "Tổng", num(tot[1]), num(tot[2]), ""])
    jm = re.search(r'"([\d.]+)" (\d{4})-(\d\d)-(\d\d)', jdk[1]) if jdk else None
    jtxt = f"OpenJDK {jm[1]} ({jm[2]}-{jm[3]}-{jm[4]} LTS)" if jm else "không ghi trong tệp"
    dm = re.match(r"(\d{4})-(\d\d)-(\d\d)", day[1].strip()) if day else None
    dtxt = f"{dm[3]}/{dm[2]}/{dm[1]}" if dm else "không ghi"
    # Dòng JDK/ngày chạy đã bỏ khỏi bảng (thông tin JDK nằm ở bảng môi trường).
    write("t01_correctness",
          tabular("rXrrl", ["Nhóm", "Nội dung kiểm tra", "Số lần", "Số lỗi", "Kết quả"], rows, env="tabularx", width="\\linewidth"),
          "results_correctness/correctness_jdk25.txt (output nguyên văn của CorrectnessTest, chạy lại ở T14)",
          note=f"JDK của lần chạy (dòng đầu tệp nguồn): {jdk[1] if jdk else 'không ghi trong tệp'}")
    if not jdk or not day or "# --- output nguyên văn ---" not in txt:
        raise SystemExit("DỪNG: correctness_output.txt thiếu dòng tiêu đề (# java.version / # Ngày chạy / # --- output nguyên văn ---)")
    check("t01 CorrectnessTest tổng số kiểm tra", int(tot[1]), 984204, 0)
    check("t01 CorrectnessTest số lỗi", int(tot[2]), 0, 0)
    return sum(1 for r in rows if not isinstance(r, str)) - 1


def t01b_mutation():
    # nội dung như bảng Khám phá: dùng lại đúng hàm của make_tables.py, ghi vào report/tables/
    saved = mt.OUT
    mt.OUT = OUT
    try:
        mt.t1b_mutation()
    finally:
        mt.OUT = saved
    p = OUT / "t01b_mutation.tex"
    p.write_text(p.read_text(encoding="utf-8").replace("% Lệnh sinh: python report/make_tables.py",
                                                      f"% Lệnh sinh: {CMD} (gọi make_tables.t1b_mutation)")
                 + "% results_final/mutation_test_output.txt KHÔNG ghi phiên bản JDK; JDK 25.0.4.1 (Windows) theo R07b / CONTEXT mục T07b.\n",
                 encoding="utf-8")


def t02_env():
    cpu = (ROOT / "results_doubling" / "cpu_info.txt").read_text(encoding="utf-8", errors="replace")
    name = re.search(r"^Name\s*:\s*(.+)$", cpu, re.M)[1].strip()
    cores = re.search(r"^NumberOfCores\s*:\s*(\d+)", cpu, re.M)[1]
    lps = re.search(r"^NumberOfLogicalProcessors\s*:\s*(\d+)", cpu, re.M)
    l2 = re.search(r"^L2CacheSize\s*:\s*(.+)$", cpu, re.M)[1].strip()
    l3 = re.search(r"^L3CacheSize\s*:\s*(.+)$", cpu, re.M)[1].strip()
    coops = re.search(r"UseCompressedOops = (\w+)", cpu)[1]
    ccp = re.search(r"UseCompressedClassPointers = (\w+)", cpu)[1]
    e1 = (ROOT / "results_run5_s1" / "env_fork1.txt").read_text(encoding="utf-8")
    ed = (ROOT / "results_doubling_v2" / "env_fork1.txt").read_text(encoding="utf-8")
    g = lambda pat, t: re.search(pat, t, re.M)[1].strip()
    jv, vendor, vmv = g(r"^java\.version=(.+)$", e1), g(r"^java\.vendor=(.+)$", e1), g(r"^java\.vm\.version=(.+)$", e1)
    osn, osv = g(r"^os\.name=(.+)$", e1), g(r"^os\.version=(.+)$", e1)
    nproc, physmem = g(r"^availableProcessors=(\d+)$", e1), int(g(r"^physical_memory_total=(\d+)$", e1))
    flags = g(r"^jvm_input_arguments=\[(.+)\]$", e1).replace(",", "")
    flags_d = g(r"^jvm_input_arguments=\[(.+)\]$", ed).replace(",", "")
    sysinfo = (ROOT / "results_final" / "env" / "systeminfo.txt").read_text(encoding="utf-8", errors="replace")
    model = re.search(r"^System Model:\s*(.+)$", sysinfo, re.M)[1].strip()
    build = re.search(r"^OS Version:\s*10\.0\.(\d+)", sysinfo, re.M)[1]
    ram = (ROOT / "results_final" / "env" / "ram.txt").read_text(encoding="utf-8", errors="replace")
    sticks = len(re.findall(r"^DeviceLocator\s*:", ram, re.M))
    scheme = re.search(r"\((.+?)\)\s*$", (ROOT / "results_final" / "env" / "power_scheme.txt").read_text(encoding="utf-8", errors="replace"), re.M)[1]
    jmh = sorted(p.name for p in (ROOT / "lib").glob("jmh-core-*.jar"))
    jmh_v = re.search(r"jmh-core-(.+)\.jar", jmh[0])[1] if jmh else "không tìm thấy"
    req = {ln.split("==")[0]: ln.split("==")[1] for ln in (ROOT / "scripts" / "requirements.txt").read_text().split() if "==" in ln}
    libs = ", ".join(f"{k} {req[k]}" for k in ["numpy", "pandas", "scipy", "statsmodels", "matplotlib"] if k in req)
    rows = [["CPU", f"{esc(name)}, {cores} nhân, {nproc} luồng" + (f" ({lps[1]} LP)" if lps else "")],
            ["Bộ nhớ đệm", f"L2 {esc(l2)}; L3 {esc(l3)}"],
            ["Máy", f"Lenovo Legion 5 15AHP10 (model {esc(model)})"],
            ["RAM", f"{num(physmem)} B ({physmem / 2 ** 30:.1f} GiB), {sticks} thanh DDR5-5600"],
            ["Hệ điều hành", f"{esc(osn)} (os.version {esc(osv)}), build {build}; gói nguồn {esc(scheme)}"],
            ["JDK", f"{esc(vendor)} OpenJDK {esc(jv)} (VM {esc(vmv)})"],
            ["Cờ JVM (mọi phiên)", f"\\texttt{{{esc(flags)}}}"],
            ["Cờ JVM (doubling test chính)", f"\\texttt{{{esc(flags_d)}}}"],
            ["Con trỏ nén (mặc định)", f"UseCompressedOops = {coops}; UseCompressedClassPointers = {ccp}"],
            ["Khởi chạy", "\\texttt{start \"bench\" /affinity C00 /wait java ...} (ghim nhân vật lý 5, LP 10/11); "
                          "typeperf 1 Hz suốt mỗi phiên"],
            ["JMH", f"jmh-core {esc(jmh_v)}"],
            ["Power Throttling", "\\texttt{powercfg /powerthrottling disable} cho \\texttt{java.exe}: chỉ từ lần 3 của JMH yếu tố đầy đủ"],
            ["Phân tích", f"Python; {esc(libs)}"]]
    write("t02_env", tabular("lX", ["Thành phần", "Cấu hình"], rows, env="tabularx", width="\\linewidth"),
          "results_run5_s1/env_fork1.txt (java.*, os.*, availableProcessors, physical_memory_total, jvm_input_arguments); "
          "results_doubling_v2/env_fork1.txt (cờ JVM doubling test chính); results_doubling/cpu_info.txt (CPU, L2, L3, con trỏ nén); "
          "results_final/env/{systeminfo,ram,power_scheme}.txt; lib/jmh-core-*.jar; scripts/requirements.txt; "
          "Power Throttling: khai báo của người đo (không có tệp đo)")
    return len(rows)


# ───────────────────────────────────────────────────────── t03 thiết kế
def raw_stats(d: Path):
    files = sorted(d.glob("raw_fork*.csv"))
    df = pd.concat([pd.read_csv(p, usecols=["fork", "trial", "distribution", "N", "cutoff"]) for p in files], ignore_index=True)
    return df, len(files)


def t03_design():
    sq2 = pd.read_csv(P2 / "p2_session_quality.csv").set_index(["session", "fork"])
    sq2b = pd.read_csv(P2B / "p2b_session_quality.csv").set_index(["session", "fork"])
    c_t04 = f"{commit_of(r'Kế hoạch doubling test sơ bộ: dự đoán')}, {commit_of(r'Kế hoạch doubling test sơ bộ: bổ sung')}"
    c_t09 = commit_of(r"Kế hoạch các phép đo chính")
    c_t11 = f"{commit_of(r'Kế hoạch JMH yếu tố đầy đủ')}, {commit_of(r'Kế hoạch JMH: bổ sung')}"

    ANA = {"Sơ bộ": None, "Chính": "results_phase2/analysis", "Bổ sung": "results_phase2b/analysis"}
    ANA_SESS = {"Run 3": "results_final/analysis, results_final/analysis_v2", "Run 4": "results_final/analysis",
                "Doubling test sơ bộ": "results_doubling/analysis", "JMH yếu tố đầy đủ lần 1": "không (bị loại)", "JMH yếu tố đầy đủ lần 2": "không (bị loại)"}
    dirs_rows = []

    def status2(sess):
        r = sq2.loc[(sess, "ALL")]
        return f"ĐÁNH DẤU ({r.pct_low_clock_lt110:.1f}\\%)" if r.flagged_gt5pct else "HỢP LỆ"

    rows, nums = [], {}

    def raw_row(phase, sess, prereg, dirs, desc, status):
        dfs, nf, secs = [], 0, 0
        for d in dirs:
            df, k = raw_stats(ROOT / d)
            dfs.append(df)
            nf = max(nf, k)
            secs += env_seconds(sorted((ROOT / d).glob("env_fork*.txt")))
        df = pd.concat(dfs, ignore_index=True)
        grids = sorted({len(g.cutoff.unique()) for _, g in df.groupby("distribution")}, reverse=True)
        trials = sorted({int(g.trial.max()) for _, g in df.groupby(["distribution", "N"])}, reverse=True)
        dirs_rows.append((phase, sess, ", ".join(dirs)))
        rows.append([phase, sess, prereg, "\\texttt{" + brk(esc(", ".join(dirs))) + "}", desc, "/".join(map(str, grids)),
                     str(nf), "/".join(map(str, trials)), num(len(df)), hm(secs), status])
        nums[sess] = len(df)

    raw_row("Sơ bộ", "Run 3", "không", ["results_run3"], "5 phân bố; random 3 thang, khác $2^{16}$", "—")
    raw_row("Sơ bộ", "Run 4", "không", ["results_run4"], "random $2^{12}$", "—")
    raw_row("Sơ bộ", "Doubling test sơ bộ", c_t04, ["results_doubling"], "random, $N=2^{10..22}$", "—")
    raw_row("Chính", "Thí nghiệm chính", c_t09, ["results_run5_s1"], "random, 5 thang", status2("S1"))
    raw_row("Chính", "Các phân bố khác", c_t09, ["results_run5_s2"], "4 phân bố $\\times$ 3 thang", status2("S2"))
    raw_row("Chính", "Doubling test chính", c_t09, ["results_doubling_v2"], "random, $N=2^{10..24}$", status2("DV2"))
    raw_row("Chính", "Kiểu khóa", c_t09, ["results_d3/integer", "results_d3/double", "results_d3/int"],
            "random, 3 thang $\\times$ 3 kiểu khóa", status2("D3"))
    jmh = pd.read_csv(ROOT / "results_jmh" / "jmh_results.csv")
    dirs_rows.append(("Chính", "JMH ban đầu", "results_jmh"))
    rows.append(["Chính", "JMH ban đầu", c_t09, "\\texttt{results\\_jmh}", "random, 3 $N$ $\\times$ 4 $c$", str(jmh.shape[0]) + " cấu hình",
                 "3", "10 vòng", num(int(jmh["Samples"].sum())) + " vòng", hm(sq2.loc[("JMH", "ALL")].duration_s), status2("JMH")])
    for k, lab in [("S6_run1", "JMH yếu tố đầy đủ lần 1"), ("S6_run2", "JMH yếu tố đầy đủ lần 2")]:
        r = sq2b.loc[(k, "ALL")]
        dirs_rows.append(("Bổ sung", lab, "results_jmh_v2_rejected_lowclock" + ("_2" if k.endswith("2") else "")))
        rows.append(["Bổ sung", lab, c_t11, "\\texttt{" + brk(esc("results_jmh_v2_rejected_lowclock" + ("_2" if k.endswith("2") else ""))) + "}",
                     "(bị loại, không phân tích)", "—", "—", "—", "—", hm(r.duration_s), f"LOẠI ({r.pct_low_clock_lt110:.1f}\\%)"])
    nconf, nsamp = 0, 0
    for f in ["jmh_v2.json", "jmh_v2_gc.json"]:
        d = json.load(open(ROOT / "results_jmh_v2" / f, encoding="utf-8"))
        nconf += len(d)
        nsamp += sum(sum(len(it) for it in e["primaryMetric"]["rawData"]) for e in d)
    r = sq2b.loc[("S6_run3", "ALL")]
    dirs_rows.append(("Bổ sung", "JMH yếu tố đầy đủ lần 3", "results_jmh_v2"))
    rows.append(["Bổ sung", "JMH yếu tố đầy đủ lần 3", c_t11, "\\texttt{results\\_\\allowbreak{}jmh\\_\\allowbreak{}v2}", "random, 3 $N$ $\\times$ 4 $c$",
                 f"{nconf} cấu hình", "3", "10 vòng", num(nsamp) + " vòng", hm(r.duration_s), r.status])
    raw_row("Bổ sung", "int[] mở rộng", c_t11, ["results_int_ext"], "random int[], 3 thang", sq2b.loc[("S7", "ALL")].status)
    rows = [r[:3] + r[4:] for r in rows]          # T14b: bỏ cột Thư mục khỏi bảng thân bài (chuyển sang ta_sessions_dirs)
    head = ["Nhóm", "Phiên", hc("Kế hoạch", "(commit)"), hc("Phân bố", "$\\times$ thang"), "$c$", "Fork", "Trial",
            hc("Phép đo", "(hàng)"), hc("Thời gian", "(h:mm)"), "typeperf"]
    body = ("\\setlength{\\tabcolsep}{3pt}\n" +
            tabular("l" + R("1.9cm") + R("1.5cm") + R("2.2cm") + R("0.9cm") + "c" + R("0.9cm") + "rc" + R("1.8cm"), head, rows) +
            "\n\\par\\smallskip\\raggedright\\footnotesize Ghi chú: ngoài lần doubling test sơ bộ, các phép đo sơ bộ không có kế hoạch ghi trước khi đo; các lựa chọn hậu nghiệm được kiểm lại ở các phép đo chính. "
            "Thư mục dữ liệu và phân tích của từng phiên: Bảng~\\ref{tab:sessions_dirs} (phụ lục A).")
    write("t03_design", body,
          "raw_fork*.csv (số hàng, CUTOFF, fork, trial), env_fork*.txt (elapsed), results_jmh/jmh_results.csv (Samples), "
          "results_jmh_v2/jmh_v2*.json (rawData), P2/p2_session_quality.csv, P2B/p2b_session_quality.csv "
          "(duration_s, pct_low_clock_lt110, status); hash: git log, lọc theo tiêu đề commit kế hoạch",
          note="Cột c: số CUTOFF trong lưới theo phân bố/kiểu (nhiều giá trị = khác nhau theo phân bố). Trial: số trial theo thang.\n"
               "Thời gian: tổng elapsed của các fork (env) hoặc duration_s của typeperf (JMH). Các phép đo sơ bộ: quy tắc typeperf chưa có.")
    drows = []
    for phase, sess, d in dirs_rows:
        a = ANA_SESS.get(sess, ANA[phase])
        for x in [*d.split(", "), *(a.split(", ") if a and not a.startswith("không") else [])]:
            if not (ROOT / x).is_dir():
                raise SystemExit(f"DỪNG: thư mục không có: {x}")
        drows.append([phase, sess, "\\texttt{" + brk(esc(d)) + "}",
                      ("\\texttt{" + brk(esc(a)) + "}") if a and not a.startswith("không") else esc(a)])
    write("ta_sessions_dirs", "\\setlength{\\tabcolsep}{3pt}\n" +
          tabular("llXX", ["Nhóm", "Phiên", "Thư mục dữ liệu thô", "Thư mục phân tích (bảng CSV)"], drows, env="tabularx", width="\\linewidth"),
          "danh sách phiên của t03_design; thư mục phân tích: results_final/analysis(_v2) (sơ bộ), results_doubling/analysis, "
          "results_phase2/analysis (T10), results_phase2b/analysis (T12); script kiểm mọi thư mục có thật")
    return len(rows), nums


# ───────────────────────────────────────────────────────── t04 phán quyết (T14b: viết cho người đọc)
# Mô tả ngắn và ngưỡng: chép ĐÚNG ý quy tắc trong T09_contract.md (§1–§5), T11_contract.md (§1–§3), T11_addendum.md (A2).
DESC = {
    "H1": "Vùng tối ưu, random, 5 thang", "H2": "10 nhanh hơn 7, random, 5 thang", "H3": "Lặp lại độ lớn của các phép đo sơ bộ",
    "H4": "Lợi ích giảm theo $N$", "H5": "Không đạt ``khoảng 20\\%''", "H6": "Reversed: $c^*$ nhỏ",
    "H7": "Few distinct: $c^*$ như random", "H8": "Sorted: $c^*$ ở biên trên lưới", "H9": "Nearly sorted: cực tiểu bên trong",
    "H10": "Mô hình M2 dự đoán đúng ở thang mới", "H10b": "M2 với $\\alpha$ hiệu chỉnh từ hàng $c=1$",
    "H11": "Doubling v2 lặp lại v1", "H12": "Ngoại suy doubling tới $2^{24}$: P-tiếp và P-bão hòa",
    "H13": "Kiểm soát cùng cây (doubling test chính)", "H14": "int[] có lợi thế hơn Integer[]",
    "H15": "Cơ chế bộ nhớ của việc lợi ích giảm theo $N$", "H16": "Double[] tương đương Integer[]",
    "H17": "JMH (T08) khớp bộ đo tự viết",
    "J1": "JMH yếu tố đầy đủ tự lặp lại T08 (same + pure)", "J2": "Học nhánh khi lặp cùng đầu vào, $N=4096$ (pure)",
    "J3": "Không học được ở $N=524\\,288$ (pure)", "J4": "Hồ sơ JIT (fresh + mixed)",
    "J5": "JMH fresh + mixed khớp S1", "J6": "Trạng thái nguội (reset = gc) làm chậm đáng kể ở $N=4096$",
    "J7": "JMH same + mixed + gc khớp S1", "I1": "``Khoảng 20\\%'' với int[] (6 fork)",
    "I1b": "int[] đạt $r<0.80$", "I2": "Cực tiểu của int[] nằm trong lưới mở rộng", "I3": "Dạng gồ của int[] lặp lại",
    "I4": "Lợi ích của int[] cũng co lại theo $N$", "B1": "Dự đoán sai nhánh giảm khi lặp đầu vào ($N=4096$)",
    "B2": "Dự đoán sai nhánh không đổi ở $N=524\\,288$",
}
THRESH = {
    "H1": "$c^*\\in[17,48]$ và $\\{24,\\dots,32\\}\\subseteq$ vùng gần tối ưu (5 thang)",
    "H2": "cận dưới CI hai tầng 95\\% của $T_7/T_{10}>1$, Holm mức 0.05 (5 thang)",
    "H3": "$|r(c^*)-r_{\\mathrm{kp}}(c^*)|\\le0.015$ ở $2^{12}$, $2^{16}$, $2^{19}$ ($r_{\\mathrm{kp}}$ = 0.848/0.888/0.918)",
    "H4": "$r(c^*)$ tăng nghiêm ngặt $2^{12}<2^{16}<2^{19}$, CI hai tầng các thang liền kề không chồng nhau; ở 5 thang mọi bước giảm $\\le0.005$",
    "H5": "$r(c^*)>0.833$ (5 thang)",
    "H6": "$c^*\\in[6,16]$ (3 thang)", "H7": "$c^*\\in[17,48]$ (3 thang)",
    "H8": "$r(c)$ không tăng theo $c$ (cho phép một bước tăng $\\le0.01$) và $c^*=4096$ (3 thang)",
    "H9": "$c^*\\in\\{128,\\allowbreak 192,\\allowbreak 256,\\allowbreak 384,\\allowbreak 512,\\allowbreak 768,\\allowbreak 1024\\}$ (3 thang)",
    "H10": "RMSE $\\le0.012$ trên 35 CUTOFF và $c^*_{\\mathrm{M2}}$ thuộc vùng gần tối ưu đo được ($2^{14}$, $2^{18}$)",
    "H10b": "RMSE $\\le0.012$ ($2^{14}$, $2^{18}$)",
    "H11": "$|\\Delta|\\le 3\\sqrt{\\mathrm{SE}_{v1}^2+\\mathrm{SE}_{v2}^2}$ (6 ô: $k=19..21$, $c\\in\\{1,30\\}$)",
    "H12": "mỗi dự đoán: $|\\ln\\bar R_k-\\ln\\hat R_k|\\le 3\\,\\mathrm{SE}_k$ ở cả 4 ô ($k=22,23$; $c\\in\\{1,30\\}$)",
    "H13": "$|\\bar\\Delta|\\le1\\%$ ở mọi $k$, 3 cặp cùng cây",
    "H14": "cận trên CI của $r_{\\mathrm{int}}-r_{\\mathrm{Integer}}<0$ và $c^*_{\\mathrm{int}}\\ge c^*_{\\mathrm{Integer}}$ (3 thang)",
    "H15": "$\\Delta r_{\\mathrm{int}}<0.5\\,\\Delta r_{\\mathrm{Integer}}$ ($2^{12}\\to2^{19}$, cùng phiên)",
    "H16": "$|r_{\\mathrm{Double}}-r_{\\mathrm{Integer}}|\\le0.02$ (3 thang)",
    "H17": "$|r_{\\mathrm{JMH}}-r_{\\mathrm{S1}}|\\le0.02$ ở 9 ô ($N\\times c$, $c\\in\\{7,10,30\\}$) và $T(30)<T(10)<T(7)<T(1)$ ở cả 3 $N$",
    "J1": "$|r-r_{\\mathrm{T08}}|\\le0.03$ ở cả 9 ô",
    "J2": "$r$(fresh) $-$ $r$(same) $\\ge0.10$ với $c\\in\\{7,10,30\\}$ và Score(fresh) $\\ge1.30\\times$ Score(same) ở $c=30$",
    "J3": "$|\\ln$ Score(fresh) $-\\ln$ Score(same)$|\\le0.03$ với cả 4 $c$",
    "J4": "Score(30) $<$ Score(10) $<$ Score(7) $<$ Score(1) ở $N=65\\,536$ và $524\\,288$",
    "J5": "tiêu chí H17: 9 ô $|\\Delta r|\\le0.02$ và thứ tự đúng ở 3 $N$",
    "J6": "Score(gc) $\\ge1.5\\times$ Score(none) ở $N=4096$, $c=30$ (same + mixed)",
    "J7": "tiêu chí H17: 9 ô $|\\Delta r|\\le0.02$ và thứ tự đúng ở 3 $N$",
    "I1": "cận trên CI hai tầng của $r_{\\mathrm{int}}(c^*)<0.833$ (3 thang)",
    "I1b": "$r_{\\mathrm{int}}(c^*)<0.80$, ước lượng điểm (3 thang)",
    "I2": "$c^*_{\\mathrm{int}}\\le192$ (3 thang)",
    "I3": "$r(64)>r(32)$ và $r(96)<r(64)$ ở $2^{12}$ và $2^{16}$",
    "I4": "$\\Delta r_{\\mathrm{int}}\\ge0.5\\,\\Delta r_{\\mathrm{Integer}}$ (Integer[] ở S1), $2^{12}\\to2^{19}$",
    "B1": "M(same) $\\le0.5\\times$ M(fresh) ở $N=4096$, $c\\in\\{1,30\\}$ (M: số dự đoán sai nhánh)",
    "B2": "M(same) $\\ge0.8\\times$ M(fresh) ở $N=524\\,288$, $c\\in\\{1,30\\}$",
}


def _slash(vals, d=3):
    return "/".join(f"{v:.{d}f}" for v in vals)


def _ints(vals):
    return "/".join(str(int(v)) for v in vals)


def main_numbers(allh) -> dict:
    """'Số chính' cho từng giả thuyết, tính từ các CSV của T10/T12 (không chép chuỗi máy)."""
    def cnt(hid, prefix=""):
        s = allh[(allh.id == hid) & (allh.subcase != "OVERALL") & allh.subcase.astype(str).str.startswith(prefix)
                 & ~allh.subcase.astype(str).str.endswith("summary")]
        return int((s.condition_met.astype(str) == "True").sum()), len(s)

    def ok(hid, prefix=""):
        a, n = cnt(hid, prefix)
        return f"{a}/{n}"

    b = pd.read_csv(P2 / "p2_best.csv").set_index(["distribution", "scale"])
    t = pd.read_csv(P2 / "p2_t7_t10.csv").set_index("scale")
    sm = pd.read_csv(P2 / "p2_m2_summary.csv").set_index("scale")
    h11, h12 = pd.read_csv(P2 / "p2_H11.csv"), pd.read_csv(P2 / "p2_H12.csv")
    h13 = pd.read_csv(P2 / "p2_H13.csv")
    h13 = h13[h13.row_type == "per_k"]
    h14, h15, h16 = pd.read_csv(P2 / "p2_H14.csv").set_index("scale"), pd.read_csv(P2 / "p2_H15.csv").iloc[0], pd.read_csv(P2 / "p2_H16.csv").set_index("scale")
    jm = pd.read_csv(P2 / "p2_jmh.csv")
    jm = jm[jm.cutoff != 1]
    j1, j2, j3, j4 = (pd.read_csv(P2B / f"p2b_J{i}.csv") for i in (1, 2, 3, 4))
    j6 = pd.read_csv(P2B / "p2b_J6.csv").iloc[0]
    i1, i3, i4 = pd.read_csv(P2B / "p2b_I1.csv").set_index("scale"), pd.read_csv(P2B / "p2b_I3.csv").set_index("scale"), pd.read_csv(P2B / "p2b_I4.csv").iloc[0]
    ib = pd.read_csv(P2B / "p2b_int_best.csv").set_index("scale")
    rnd = [b.loc[("random", s)] for s in S5]
    # H3: r_Khám phá lấy giá trị đầy đủ từ results_final (như phân tích T10; hợp đồng ghi làm tròn 0.848/0.888/0.918)
    g1 = pd.read_csv(ROOT / "results_final" / "analysis" / "tables" / "rq1_best_cutoff.csv")
    g1 = g1[g1.distribution == "random"].set_index("scale")
    d3 = [abs(b.loc[("random", s)].r_star - g1.loc[s].r_best) for s in S3]
    # H4: CI rời nhau giữa các thang liền kề và bước giảm lớn nhất
    r5 = [x.r_star for x in rnd]
    max_dec = max(0.0, max(r5[i] - r5[i + 1] for i in range(4)))
    ci_ok = sum(int(b.loc[("random", a)].ci2_hi < b.loc[("random", c)].ci2_lo) for a, c in [("2^12", "2^16"), ("2^16", "2^19")])
    pt = h12[h12.predictor == "P_tiep"]["pass"].sum()
    pb = h12[h12.predictor == "P_baohoa"]["pass"].sum()
    j_ord = lambda hid: ok(hid, "order")
    j_dif = lambda hid: ok(hid, "diff")
    M = {
        "H1": f"$c^*$ = {_ints(x.c_star for x in rnd)}; đạt {ok('H1')} thang",
        "H2": f"$T_7/T_{{10}}$ = {t.loc['2^12'].ratio_T7_T10:.3f}…{t.loc['2^19'].ratio_T7_T10:.3f}; cận dưới CI nhỏ nhất {t.ci2_lo.min():.4f}; Holm $p\\le{t.p_holm.max():.4f}$",
        "H3": f"$|\\Delta|$ = {_slash(d3, 4)}",
        "H4": f"CI rời nhau ở {ci_ok}/2 cặp thang; bước giảm lớn nhất {max_dec:.3f}",
        "H5": f"$r(c^*)$ nhỏ nhất {min(r5):.3f}; cận dưới CI nhỏ nhất {min(x.ci2_lo for x in rnd):.3f}",
        "H6": f"$c^*$ = {_ints(b.loc[('reversed', s)].c_star for s in S3)}",
        "H7": f"$c^*$ = {_ints(b.loc[('few_distinct', s)].c_star for s in S3)}",
        "H8": f"$c^*$ = {_ints(b.loc[('sorted', s)].c_star for s in S3)}; đạt {ok('H8')} thang",
        "H9": f"$c^*$ = {_ints(b.loc[('nearly_sorted', s)].c_star for s in S3)}",
        "H10": f"RMSE = {sm.loc['2^14'].rmse_interp:.4f}/{sm.loc['2^18'].rmse_interp:.4f}; $c^*_{{\\mathrm{{M2}}}}$ = {int(sm.loc['2^14'].c_star_M2)} trong vùng ở {int(sm.c_star_M2_in_near_opt.sum())}/2 thang",
        "H10b": f"RMSE = {sm.loc['2^14'].rmse_calib:.4f}/{sm.loc['2^18'].rmse_calib:.4f}",
        "H11": f"đạt {int(h11['pass'].sum())}/{len(h11)} ô; $|\\Delta|$ = {h11.abs_diff.min():.3f}–{h11.abs_diff.max():.3f}",
        "H12": f"P-tiếp {int(pt)}/4 ô; P-bão hòa {int(pb)}/4 ô",
        "H13": f"đạt {int(h13['pass'].sum())}/{len(h13)} ô; $|\\bar\\Delta|$ lớn nhất {100 * h13.abs_delta_mean.max():.1f}\\%",
        "H14": f"$r_{{\\mathrm{{int}}}}-r_{{\\mathrm{{Integer}}}}$ = {'/'.join(mt.sg(h14.loc[s].diff_r_int_minus_integer) for s in S3)}; $c^*$ {_ints(h14.loc[s].c_star_int for s in S3)} so với {_ints(h14.loc[s].c_star_integer for s in S3)}",
        "H15": f"$\\Delta r_{{\\mathrm{{int}}}}$ = {h15.delta_r_int:.3f}; $0.5\\,\\Delta r_{{\\mathrm{{Integer}}}}$ = {h15.half_delta_r_integer:.3f}",
        "H16": f"$|r_{{\\mathrm{{Double}}}}-r_{{\\mathrm{{Integer}}}}|$ = {_slash((h16.loc[s].abs_diff for s in S3), 3)}",
        "H17": f"$|\\Delta r|\\le0.02$: {int(jm.pass_diff_le_002.sum())}/{len(jm)} ô; thứ tự đúng {int(jm.groupby('N').order_30_10_7_1_ok.first().sum())}/3 $N$",
        "J1": f"$|\\Delta r|\\le0.03$: {int(j1.condition_met.sum())}/{len(j1)} ô; lớn nhất {j1.abs_diff.max():.3f}",
        "J2": f"hiệu $r$ = {_slash(j2[j2.subcase.str.startswith('diff_r')].metric_value, 2)}; tỉ số Score {j2[j2.subcase.str.startswith('ratio')].metric_value.iloc[0]:.2f}",
        "J3": f"$|\\ln$ tỉ số$|$ = {j3.abs_ln_diff.min():.2f}–{j3.abs_ln_diff.max():.2f}; đạt {int(j3.condition_met.sum())}/{len(j3)} $c$",
        "J4": f"thứ tự đúng {int(j4.condition_met.sum())}/{len(j4)} $N$",
        "J5": f"$|\\Delta r|\\le0.02$: {j_dif('J5')} ô; thứ tự đúng {j_ord('J5')} $N$",
        "J6": f"tỉ số = {j6.ratio_gc_over_none:.2f} [{j6.ci_lo:.2f}, {j6.ci_hi:.2f}]",
        "J7": f"$|\\Delta r|\\le0.02$: {j_dif('J7')} ô; thứ tự đúng {j_ord('J7')} $N$",
        "I1": f"cận trên CI = {_slash(i1.loc[s].ci2_hi for s in S3)}",
        "I1b": f"$r_{{\\mathrm{{int}}}}(c^*)$ = {_slash(ib.loc[s].r_star for s in S3)}",
        "I2": f"$c^*$ = {_ints(ib.loc[s].c_star for s in S3)}",
        "I3": "; ".join(f"{sc(s)}: {i3.loc[s].r_32:.3f}, {i3.loc[s].r_64:.3f}, {i3.loc[s].r_96:.3f}" for s in ["2^12", "2^16"]) + " ($c$ = 32, 64, 96)",
        "I4": f"$\\Delta r_{{\\mathrm{{int}}}}$ = {i4.delta_r_int:.3f} [{i4.ci2_delta_lo:.3f}, {i4.ci2_delta_hi:.3f}]; $0.5\\,\\Delta r_{{\\mathrm{{Integer}}}}$ = {i4.half_delta_r_Integer_S1:.3f}",
        "B1": "hủy (AMD uProf chưa cài)",
        "B2": "hủy (AMD uProf chưa cài)",
    }
    return M


def t04_verdicts():
    h = pd.read_csv(P2 / "h_verdicts.csv")
    h2 = pd.read_csv(P2B / "h2b_verdicts.csv")
    allh = pd.concat([h, h2], ignore_index=True)
    tot = allh[(allh.subcase == "OVERALL")].reset_index(drop=True)
    M = main_numbers(allh)
    rows, counts = [], {"ĐẠT": 0, "KHÔNG ĐẠT": 0, "tách đôi": 0, "không thực hiện": 0}
    for _, r in tot.iterrows():
        v = str(r.verdict_overall)
        if v == "ĐẠT":
            vv, key = "ĐẠT", "ĐẠT"
        elif v == "KHÔNG ĐẠT":
            vv, key = "KHÔNG ĐẠT", "KHÔNG ĐẠT"
        elif v == "KHÔNG THỰC HIỆN":
            vv, key = "không thực hiện", "không thực hiện"
        elif v.startswith("XEM TỪNG DỰ ĐOÁN"):
            vv, key = "tách đôi: P-tiếp ĐẠT, P-bão hòa KHÔNG ĐẠT", "tách đôi"
        else:
            raise SystemExit(f"DỪNG: phán quyết lạ {r.id}: {v}")
        counts[key] += 1
        if r.id not in DESC or r.id not in THRESH or r.id not in M:
            raise SystemExit(f"DỪNG: thiếu mô tả/ngưỡng/số chính cho {r.id}")
        rows.append([f"\\textbf{{{esc(r.id)}}}", DESC[r.id], M[r.id], THRESH[r.id], vv])
    raw = re.compile(r"(True|False|_[a-z]|\\\^\{\}|\*)")
    for row in rows:
        for cell in row[1:4]:
            if raw.search(re.sub(r"\$[^$]*\$", "", cell)):
                raise SystemExit(f"DỪNG: ô còn chuỗi máy: {cell}")
    body = longtable("l" + R("3.2cm") + R("4.2cm") + R("4.3cm") + R("1.8cm"), ["Id", "Giả thuyết", "Số chính", "Tiêu chí đạt", "Phán quyết"], rows,
                     "Tổng hợp phán quyết của 32 giả thuyết (H: kế hoạch của các phép đo chính; J, I, B: kế hoạch của các phép đo bổ sung và phụ lục).",
                     "tab:verdicts", size="\\footnotesize\\setlength{\\tabcolsep}{4pt}")
    write("t04_verdicts", body,
          "P2/h_verdicts.csv, P2B/h2b_verdicts.csv (hàng OVERALL: verdict_overall; đếm condition_met theo điều kiện con); "
          "số chính từ P2/p2_best, p2_t7_t10, p2_m2_summary, p2_H11-H16, p2_jmh; P2B/p2b_J1-J4, J6, I1, I3, I4, p2b_int_best; "
          "mô tả và ngưỡng: dict DESC, THRESH trong make_tables_p2.py, chép theo T09_contract.md, T11_contract.md, T11_addendum.md",
          note=f"Số dòng: {len(rows)}; ĐẠT {counts['ĐẠT']}, KHÔNG ĐẠT {counts['KHÔNG ĐẠT']}, tách đôi {counts['tách đôi']}, "
               f"không thực hiện {counts['không thực hiện']}. Hàng J2xJ6 OUTCOME (kết cục, không phải giả thuyết) không đưa vào.")
    check("t04 số dòng", len(rows), 32, 0)
    check("t04 ĐẠT", counts["ĐẠT"], 21, 0)
    check("t04 KHÔNG ĐẠT", counts["KHÔNG ĐẠT"], 8, 0)
    check("t04 tách đôi (H12)", counts["tách đôi"], 1, 0)
    check("t04 không thực hiện (B1, B2)", counts["không thực hiện"], 2, 0)
    return len(rows)


# ───────────────────────────────────────────────────────── t05, t06 (random)
def t05_rq1():
    b = pd.read_csv(P2 / "p2_best.csv")
    b = b[b.distribution == "random"].set_index("scale")
    pool = pd.read_csv(P2 / "p2_pooled.csv").set_index("cutoff")
    ref_c = dict(zip(S5, [32, 32, 31, 31, 30]))
    ref_r = dict(zip(S5, [0.8443, 0.8703, 0.8873, 0.9088, 0.9165]))
    rows = []
    for s in S5:
        r = b.loc[s]
        rows.append([sc(s), str(int(r.c_star)), ci(r.r_star, r.ci2_lo, r.ci2_hi), near(r.near_optimal_2pct),
                     esc(r.boot2_argmin_top3_kp)])
        check(f"t05 c* {s}", r.c_star, ref_c[s], 0)
        check(f"t05 r(c*) {s}", r.r_star, ref_r[s], 0.00005)
    rows.append("\\midrule")
    for c in [31, 30]:
        p = pool.loc[c]
        rows.append([f"gộp 5 thang", str(c), ci(p.r, p.ci2_lo, p.ci2_hi), "", ""])
    write("t05_rq1", tabular("lcclX", ["Thang", "$c^*$", "$r(c^*)$ [CI hai tầng 95\\%]", hc("Gần tối ưu", "($r\\le1.02\\,r(c^*)$)"),
                                       hc("Argmin bootstrap", "(top 3)")], rows, env="tabularx", width="\\linewidth"),
          "P2/p2_best.csv (random: c_star, r_star, ci2_lo, ci2_hi, near_optimal_2pct, boot2_argmin_top3_kp); P2/p2_pooled.csv (cutoff 30, 31: r, ci2_lo, ci2_hi)",
          note="Hàng gộp: trung bình nhân trên 120 N của 5 thang (c = 31 là argmin của p2_pooled; c = 30 để so với các phép đo sơ bộ).")
    return len(rows) - 1


def t06_rq3():
    r = pd.read_csv(P2 / "p2_r_by_cutoff.csv")
    r = r[r.distribution == "random"].set_index(["scale", "cutoff"])
    b = pd.read_csv(P2 / "p2_best.csv")
    b = b[b.distribution == "random"].set_index("scale")
    t = pd.read_csv(P2 / "p2_t7_t10.csv").set_index("scale")
    ref_red = dict(zip(S5, [15.6, 13.0, 11.3, 9.1, 8.4]))
    ref_t = dict(zip(S5, [1.0193, 1.0174, 1.0129, 1.0105, 1.0099]))
    rows = []
    for s in S5:
        cs = int(b.loc[s].c_star)
        cells = [sc(s)]
        for c in [7, 10, cs]:
            q = r.loc[(s, c)]
            cells.append(f"{100 * (1 - q.r):.1f} [{100 * (1 - q.ci2_hi):.1f}, {100 * (1 - q.ci2_lo):.1f}]")
        q = r.loc[(s, cs)]
        cells.append(f"{1 / q.r:.3f}")
        tt = t.loc[s]
        cells += [ci(tt.ratio_T7_T10, tt.ci2_lo, tt.ci2_hi, 4), mt.pval(tt.p_holm)]
        rows.append(cells)
        check(f"t06 1-r(c*) % {s}", 100 * (1 - q.r), ref_red[s], 0.05)
        check(f"t06 T7/T10 {s}", tt.ratio_T7_T10, ref_t[s], 0.00005)
    write("t06_rq3", "\\setlength{\\tabcolsep}{3pt}\n" +
          tabular("lcccccc", ["Thang", hc("Giảm \\% tại", "$c=7$"), hc("Giảm \\% tại", "$c=10$"), hc("Giảm \\% tại", "$c^*$"),
                              hc("Tăng tốc", "$1/r(c^*)$"), hc("$T_7/T_{10}$", "[CI hai tầng 95\\%]"), hc("$p$", "(Holm)")], rows),
          "P2/p2_r_by_cutoff.csv (random: r, ci2_lo, ci2_hi tại c = 7, 10, c*); P2/p2_best.csv (c_star); "
          "P2/p2_t7_t10.csv (ratio_T7_T10, ci2_lo, ci2_hi, p_holm)",
          note="Giảm % = 100(1 - r); khoảng = 100(1 - ci2_hi), 100(1 - ci2_lo).")
    return len(rows)


# ───────────────────────────────────────────────────────── t07 phân bố khác
def t07_other_dist():
    b = pd.read_csv(P2 / "p2_best.csv").set_index(["distribution", "scale"])
    h = pd.read_csv(P2 / "h_verdicts.csv")
    hyp = {"reversed": ("H6", "[6, 16]"), "few_distinct": ("H7", "[17, 48]"), "sorted": ("H8", "4096, không tăng"),
           "nearly_sorted": ("H9", "\\{128..1024\\}")}
    rows = []
    for d in ["sorted", "nearly_sorted", "reversed", "few_distinct"]:
        hid, rng = hyp[d]
        first = True
        for s in S3:
            r = b.loc[(d, s)]
            v = h[(h.id == hid) & (h.subcase == s)].iloc[0]
            rows.append([DIST[d] if first else "", f"{hid}: {rng}" if first else "", sc(s), str(int(r.c_star)),
                         ci(r.r_star, r.ci2_lo, r.ci2_hi), near(r.near_optimal_2pct), "đạt" if bool(v.condition_met) else "không đạt"])
            first = False
        rows.append("\\addlinespace")
    rows = rows[:-1]
    write("t07_other_dist", "\\setlength{\\tabcolsep}{3pt}\n" +
          tabular("llccclc", ["Phân bố", hc("Dự đoán", "ghi trước"), "Thang", "$c^*$", "$r(c^*)$ [CI hai tầng]",
                              hc("Gần tối ưu", "($\\le2\\%$)"), "Điều kiện"], rows),
          "P2/p2_best.csv (c_star, r_star, ci2_lo, ci2_hi, near_optimal_2pct); P2/h_verdicts.csv (H6-H9 theo thang: condition_met); PR/T09_hypotheses.csv (khoảng)",
          note="H8 (sorted): điều kiện gồm c* = 4096 và r không tăng theo c (cho phép 1 bước tăng <= 0.01).")
    return 12


# ───────────────────────────────────────────────────────── t08 doubling v2
def t08_doubling_v2():
    h11 = pd.read_csv(P2 / "p2_H11.csv")
    h12 = pd.read_csv(P2 / "p2_H12.csv")
    rows1 = [[f"{int(r.k_from)}$\\to${int(r.k_to)}", str(int(r.cutoff)), f4(r.ln_R_v1), f4(r.ln_R_v2), f4(r.abs_diff),
              f4(r.threshold_3se), "đạt" if r["pass"] else "không đạt"] for _, r in h11.iterrows()]
    t1 = tabular("lcccccc", ["$k$", "$c$", "$\\ln\\bar R$ sơ bộ", "$\\ln\\bar R$ chính", "$|\\Delta|$",
                             hc("$3\\sqrt{SE_{\\mathrm{sb}}^2+SE_{\\mathrm{ch}}^2}$"), "Kết quả"], rows1)
    pn = {"P_tiep": "P-tiếp", "P_baohoa": "P-bão hòa"}
    rows2 = [[pn[r.predictor], f"{int(r.k_from)}$\\to${int(r.k_to)}", str(int(r.cutoff)), f4(r.ln_R_v2), f4(r.ln_R_hat),
              f4(r.abs_diff), f4(r.threshold_3se), "đạt" if r["pass"] else "không đạt"] for _, r in h12.iterrows()]
    t2 = tabular("llcccccc", ["Dự đoán", "$k$", "$c$", "$\\ln\\bar R$ đo", "$\\ln\\hat R$", "$|\\Delta|$", "$3\\,SE_k$", "Ô"], rows2)
    write("t08_doubling_v2", "\\textbf{(a) Lặp lại doubling test sơ bộ}\\par\\smallskip\n" + t1 +
          "\n\\bigskip\n\n\\textbf{(b) Ngoại suy tới $2^{24}$}\\par\\smallskip\n" + t2,
          "P2/p2_H11.csv (k_from, k_to, cutoff, ln_R_v1, ln_R_v2, abs_diff, threshold_3se, pass); "
          "P2/p2_H12.csv (predictor, k_from, k_to, cutoff, ln_R_v2, ln_R_hat, abs_diff, threshold_3se, pass)")
    return len(rows1) + len(rows2)


# ───────────────────────────────────────────────────────── t09 mô hình chi phí
def t09_cost_model():
    m2 = pd.read_csv(V2 / "cost_model_M2_coef.csv").set_index("parameter")
    lo = pd.read_csv(V2 / "cost_model_loso.csv")
    sm = pd.read_csv(P2 / "p2_m2_summary.csv").set_index("scale")
    names = [("ML_b1", "$w_1$ (merge $\\le 8$)", "ns/phần tử"), ("ML_b2", "$w_2$ (merge 9--32)", "ns/phần tử"),
             ("ML_b3", "$w_3$ (merge 33--128)", "ns/phần tử"), ("exchanges", "$\\beta$ (đổi chỗ trong lá)", "ns/nghịch thế"),
             ("ML_b456_12", "$\\alpha_{12}$", "ns/phần tử"), ("ML_b456_16", "$\\alpha_{16}$", "ns/phần tử"),
             ("ML_b456_19", "$\\alpha_{19}$", "ns/phần tử")]
    rows = [[lab, f"{m2.loc[k].coef:.2f} $\\pm$ {m2.loc[k].std_err:.2f}", u] for k, lab, u in names]
    ta = tabular("lcl", ["Tham số M2 (phép đo sơ bộ)", "Hệ số $\\pm$ SE", "Đơn vị"], rows)
    rows_b = []
    for mod in ["M0", "M1", "M2"]:
        g = lo[lo.model == mod].set_index("holdout_scale")
        rows_b.append([f"{mod}, LOSO, khám phá", f4(g.loc["2^12"].rmse_r), f4(g.loc["2^16"].rmse_r), f4(g.loc["2^19"].rmse_r), "", ""])
    rows_b.append("\\midrule")
    rows_b.append(["M2, $\\alpha$ nội suy (xác nhận)", "", "", "", f4(sm.loc["2^14"].rmse_interp), f4(sm.loc["2^18"].rmse_interp)])
    rows_b.append(["M2, $\\alpha$ hiệu chỉnh (xác nhận)", "", "", "", f4(sm.loc["2^14"].rmse_calib), f4(sm.loc["2^18"].rmse_calib)])
    rows_b.append(["$c^*_{M2}$ / $c^*$ đo (xác nhận)", "", "", "", f"{int(sm.loc['2^14'].c_star_M2)} / {int(sm.loc['2^14'].c_star_meas)}",
                   f"{int(sm.loc['2^18'].c_star_M2)} / {int(sm.loc['2^18'].c_star_meas)}"])
    tb = tabular("lccccc", ["RMSE$(\\hat r - r)$", "$2^{12}$", "$2^{16}$", "$2^{19}$", "$2^{14}$", "$2^{18}$"], rows_b)
    write("t09_cost_model", "\\textbf{(a)}\\par\\smallskip\n" + ta + "\n\\bigskip\n\n\\textbf{(b)}\\par\\smallskip\n" + tb,
          "V2/cost_model_M2_coef.csv (coef, std_err); V2/cost_model_loso.csv (model, holdout_scale, rmse_r); "
          "P2/p2_m2_summary.csv (rmse_interp, rmse_calib, c_star_M2, c_star_meas)",
          note="(a) và các hàng LOSO: khám phá. Các hàng xác nhận: kiểm định H10, H10b (ngưỡng RMSE <= 0.012).")
    check("t09 RMSE M2 nội suy 2^14", sm.loc["2^14"].rmse_interp, 0.0042, 0.00005)
    check("t09 RMSE M2 nội suy 2^18", sm.loc["2^18"].rmse_interp, 0.0040, 0.00005)
    return len(rows) + len(rows_b) - 1


# ───────────────────────────────────────────────────────── t10 kiểu khóa
def t10_key_types():
    d3 = pd.read_csv(P2 / "p2_d3_best.csv").set_index(["key", "scale"])
    s7 = pd.read_csv(P2B / "p2b_int_best.csv").set_index("scale")
    h14 = pd.read_csv(P2 / "p2_H14.csv").set_index("scale")
    h16 = pd.read_csv(P2 / "p2_H16.csv").set_index("scale")
    h15 = pd.read_csv(P2 / "p2_H15.csv").iloc[0]
    i4 = pd.read_csv(P2B / "p2b_I4.csv").iloc[0]
    ref_r = dict(zip(S3, [0.6972, 0.7661, 0.7832]))
    ref_c = dict(zip(S3, [128, 112, 64]))
    rows = []
    for s in S3:
        cells = [sc(s)]
        for key in ["integer", "double", "int"]:
            r = d3.loc[(key, s)]
            cells.append(f"{int(r.c_star)}: {ci(r.r_star, r.ci2_lo, r.ci2_hi)}")
        r = s7.loc[s]
        cells.append(f"{int(r.c_star)}: {ci(r.r_star, r.ci2_lo, r.ci2_hi)}")
        rows.append(cells)
        check(f"t10 int S7 r(c*) {s}", r.r_star, ref_r[s], 0.00005)
        check(f"t10 int S7 c* {s}", r.c_star, ref_c[s], 0)
    ta = tabular("lcccc", ["Thang", hc("Integer[] (3 fork)", "$c^*$: $r$ [CI]"), hc("Double[] (3 fork)", "$c^*$: $r$ [CI]"),
                           hc("int[] (3 fork)", "$c^*$: $r$ [CI]"), hc("int[] mở rộng (6 fork)", "$c^*$: $r$ [CI]")], rows)
    rows_b = []
    for s in S3:
        a, b = h14.loc[s], h16.loc[s]
        sgci = lambda x, lo, hi: f"{mt.sg(x)} [{mt.sg(lo)}, {mt.sg(hi)}]"
        rows_b.append([sc(s), sgci(a.diff_r_int_minus_integer, a.ci2_diff_lo, a.ci2_diff_hi), f3(b.abs_diff),
                       sgci(b.diff_r, b.ci2_diff_lo, b.ci2_diff_hi)])
    tb = tabular("lccc", ["Thang", hc("$r_{\\mathrm{int}}-r_{\\mathrm{Integer}}$", "[CI]"),
                          "$|r_{\\mathrm{Double}}-r_{\\mathrm{Integer}}|$",
                          hc("$r_{\\mathrm{Double}}-r_{\\mathrm{Integer}}$", "[CI]")], rows_b)
    rows_c = [["int[], thí nghiệm kiểu khóa", f3(h15.r_int_2e12), f3(h15.r_int_2e19), f3(h15.delta_r_int)],
              ["Integer[], thí nghiệm kiểu khóa", f3(h15.r_integer_2e12), f3(h15.r_integer_2e19), f3(h15.delta_r_integer)],
              ["int[], thí nghiệm mở rộng", f3(i4.r_int_2e12), f3(i4.r_int_2e19), f"{i4.delta_r_int:.3f} [{i4.ci2_delta_lo:.3f}, {i4.ci2_delta_hi:.3f}]"],
              ["Integer[], thí nghiệm chính", "", "", f3(i4.delta_r_Integer_S1)]]
    tc = tabular("lccc", ["Kiểu (nguồn)", "$r(c^*)$ ở $2^{12}$", "$r(c^*)$ ở $2^{19}$", "$\\Delta r$ [CI]"], rows_c)  # Δr > 0: dương, không dấu
    write("t10_key_types", "\\setlength{\\tabcolsep}{3pt}\n\\textbf{(a)}\\par\\smallskip\n" + ta +
          "\n\\bigskip\n\n\\textbf{(b)}\\par\\smallskip\n" + tb + "\n\\bigskip\n\n\\textbf{(c)}\\par\\smallskip\n" + tc,
          "P2/p2_d3_best.csv (key, c_star, r_star, ci2_lo, ci2_hi); P2B/p2b_int_best.csv (S7); P2/p2_H14.csv (diff_r_int_minus_integer, ci2_diff_lo/hi); "
          "P2/p2_H16.csv (diff_r, abs_diff, ci2_diff_lo/hi); P2/p2_H15.csv; P2B/p2b_I4.csv",
          note="Delta r = r(c*, 2^19) - r(c*, 2^12). CI = CI hai tầng 95%.")
    return 3 + 3 + 4


# ───────────────────────────────────────────────────────── t11 JMH
CFG = [("same", "pure", "none"), ("fresh", "pure", "none"), ("same", "mixed", "none"), ("fresh", "mixed", "none"),
       ("same", "mixed", "gc"), ("fresh", "mixed", "gc")]


def t11_jmh():
    sc_ = pd.read_csv(P2B / "p2b_jmh_scores.csv")
    rr = pd.read_csv(P2B / "p2b_jmh_r.csv")
    ab = pd.read_csv(P2B / "p2b_jmh_abs_vs_run5.csv").set_index(["N", "cutoff"])
    t08 = pd.read_csv(P2 / "p2_jmh.csv").set_index(["N", "cutoff"])
    j6 = pd.read_csv(P2B / "p2b_J6.csv").iloc[0]
    rows = [["JMH ban đầu", f"{t08.loc[(4096, 30)].jmh_score_us:.0f} $\\pm$ {t08.loc[(4096, 30)].jmh_score_err_999_us:.0f}$^{{a}}$",
             f"{t08.loc[(524288, 30)].jmh_score_us:.0f} $\\pm$ {t08.loc[(524288, 30)].jmh_score_err_999_us:.0f}$^{{a}}$"] +
            [f3(t08.loc[(n, 30)].r_jmh) for n in [4096, 65536, 524288]]]
    for cfg in CFG:
        m = (sc_.input == cfg[0]) & (sc_.profile == cfg[1]) & (sc_.reset == cfg[2]) & (sc_.cutoff == 30)
        mr = (rr.input == cfg[0]) & (rr.profile == cfg[1]) & (rr.reset == cfg[2]) & (rr.cutoff == 30)
        cells = ["+".join(cfg)]
        for n in [4096, 524288]:
            q = sc_[m & (sc_.N == n)].iloc[0]
            cells.append(stack(q.score_us, q.ci_lo, q.ci_hi, 0))
        for n in [4096, 65536, 524288]:
            q = rr[mr & (rr.N == n)].iloc[0]
            cells.append(stack(q.r, q.ci_lo, q.ci_hi))
        rows.append(cells)
    rows.append("\\midrule")
    rows.append(["Bộ đo$^{b}$", f"{ab.loc[(4096, 30)].run5_geom_time_us:.0f}", f"{ab.loc[(524288, 30)].run5_geom_time_us:.0f}"] +
                [f3(t08.loc[(n, 30)].r_run5) for n in [4096, 65536, 524288]])
    body = ("\\setlength{\\tabcolsep}{3pt}\n" +
            tabular("lccccc", ["Cấu hình", hc("Score $N{=}4096$", "$c{=}30$ (µs)"), hc("Score $N{=}524288$", "$c{=}30$ (µs)"),
                               hc("$r(4096, 30)$", "[CI]"), hc("$r(65536, 30)$", "[CI]"), hc("$r(524288, 30)$", "[CI]")], rows) +
            "\n\\par\\smallskip\\raggedright\\footnotesize $^{a}$ Score Error 99.9\\% do JMH báo (không phải CI bootstrap). "
            "$^{b}$ Trung bình nhân, thí nghiệm chính (khác phiên với JMH); r của đúng $N$ đó. CI: bootstrap 95\\% theo fork (3 fork).")
    write("t11_jmh", body,
          "P2B/p2b_jmh_scores.csv (score_us, ci_lo, ci_hi; cutoff 30); P2B/p2b_jmh_r.csv (r, ci_lo, ci_hi; cutoff 30); "
          "P2B/p2b_jmh_abs_vs_run5.csv (run5_geom_time_us); P2/p2_jmh.csv (T08: jmh_score_us, jmh_score_err_999_us, r_jmh, r_run5)",
          note="Cấu hình ghi theo input+profile+reset.")
    check("t11 J6 tỉ số gc/none (4096, 30)", j6.ratio_gc_over_none, 1.7861, 0.00005)
    return len(rows) - 1


def t12_memory():
    saved = mt.OUT
    tmp = CHK / "_tmp_p1"
    tmp.mkdir(parents=True, exist_ok=True)
    mt.OUT = tmp
    try:
        mt.t8_memory()
    finally:
        mt.OUT = saved
    txt = (tmp / "t08_memory.tex").read_text(encoding="utf-8")
    try:                                   # thư mục tạm có thể không xóa được (ổ đĩa kết nối từ máy khác): bỏ qua
        (tmp / "t08_memory.tex").unlink()
        tmp.rmdir()
    except OSError:
        pass
    txt = txt.replace("% Lệnh sinh: python report/make_tables.py", f"% Lệnh sinh: {CMD} (gọi make_tables.t8_memory; = tables/p1/t08_memory.tex, đổi tên)")
    (OUT / "t12_memory.tex").write_text(txt, encoding="utf-8")
    print("wrote t12_memory")
    return 4


# ───────────────────────────────────────────────────────── phụ lục
SESS_VI = {"S1": "Chính", "S2": "Phân bố khác", "DV2": "Doubling chính", "D3": "Kiểu khóa", "JMH": "JMH ban đầu",
           "S6_run1": "JMH lần 1", "S6_run2": "JMH lần 2", "S6_run3": "JMH lần 3", "S7": "int[] mở rộng"}
F4_VI = {"H1": "$c^*$ và vùng gần tối ưu", "H2": "CUTOFF 10 nhanh hơn 7", "H3": "Lặp lại phép đo sơ bộ",
         "H4": "$r(c^*)$ tăng theo $N$", "H5": "$r(c^*) > 0.833$ (Integer[])", "H10": "M2 dự đoán thang mới",
         "H10b": "M2, $\\alpha$ hiệu chỉnh", "H17": "JMH ban đầu khớp bộ đo"}


def f4_metrics(m: str) -> str:
    for a, b in [("min_ci2_lo", "cận dưới CI nhỏ nhất"), ("max_p_holm", "p Holm lớn nhất"), ("max_dec", "giảm lớn nhất"),
                 ("order_all=False", "thứ tự đúng ở mọi N: không"), ("order_all=True", "thứ tự đúng ở mọi N: có"),
                 ("min r(c*)", "r(c*) nhỏ nhất"), ("ci_12<16:True", "CI 2^12 < 2^16"), ("ci_16<19:True", "CI 2^16 < 2^19")]:
        m = m.replace(a, b)
    return m


def ta_session_quality():
    q = pd.concat([pd.read_csv(P2 / "p2_session_quality.csv").assign(status=lambda d: d.flagged_gt5pct.map({True: "ĐÁNH DẤU", False: "HỢP LỆ"})),
                   pd.read_csv(P2B / "p2b_session_quality.csv")], ignore_index=True)
    rows = []
    for _, r in q.iterrows():
        b = "\\textbf" if r.fork == "ALL" else ""
        st = r.status if r.fork == "ALL" else ""
        rows.append([SESS_VI.get(r.session, esc(r.session)), (b + "{Cả phiên}") if b else esc(r.fork), num(r.n_samples), f"{r.pct_outside_lp10_11:.2f}",
                     f"{r.pct_low_clock_lt110:.2f}", f"{r.perf_median:.1f}", f"{r.perf_min:.1f}", f"{r.duration_min:.1f}", st])
    body = longtable("llrrrrrrl", ["Phiên", "Fork", "Mẫu", hc("\\% ngoài", "LP 10/11"), hc("\\% xung", "$<110\\%$"), hc("Xung", "trung vị"),
                                    hc("Xung", "min"), hc("Thời gian", "(phút)"), "Trạng thái"], rows,
                     "Chất lượng các phiên đo (typeperf 1 Hz): mọi phiên đo, kể cả hai lần JMH yếu tố đầy đủ bị loại.", "tab:session_quality")
    write("ta_session_quality", body, "P2/p2_session_quality.csv, P2B/p2b_session_quality.csv (mọi cột số; status/flagged_gt5pct)",
          note="Quy tắc ghi trước khi đo: đánh dấu khi > 5% mẫu; loại và đo lại cả phiên khi > 20%.")
    return len(rows)


def ta_fork4():
    v = pd.read_csv(P2 / "p2_sensitivity_drop_f4.csv")
    s = pd.read_csv(P2 / "p2_sensitivity_drop_f4_scales.csv")
    rows = [[F4_VI.get(r.hypothesis, esc(r.hypothesis)), esc(r.verdict_5forks), esc(r.verdict_4forks), "có" if r.verdict_changed else "không",
             sym(f4_metrics(str(r.metrics_4forks)))] for _, r in v.iterrows()]
    t1 = tabular("lcccX", ["Kết luận được kiểm", "5 fork", "4 fork", "Đổi?", "Số chính (4 fork)"], rows, env="tabularx", width="\\linewidth")
    rows2 = [[sc(r.scale), str(int(r.c_star_5forks)), ci(r.r_star_5forks, r.ci2_5f_lo, r.ci2_5f_hi), str(int(r.c_star_4forks)),
              ci(r.r_star_4forks, r.ci2_4f_lo, r.ci2_4f_hi), f3(r.r_fork4_at_cstar5)] for _, r in s.iterrows()]
    t2 = tabular("lccccc", ["Thang", "$c^*$ (5)", "$r$ [CI] (5 fork)", "$c^*$ (4)", "$r$ [CI] (4 fork)", hc("$r$ fork 4", "tại $c^*$ (5)")], rows2)
    write("ta_fork4", "\\textbf{(a)}\\par\\smallskip\n" + t1 + "\n\\bigskip\n\n\\textbf{(b)}\\par\\smallskip\n" + t2,
          "P2/p2_sensitivity_drop_f4.csv (hypothesis, verdict_5forks, verdict_4forks, verdict_changed, metrics_4forks); "
          "P2/p2_sensitivity_drop_f4_scales.csv")
    return len(rows) + len(rows2)


def ta_ci_width():
    w = pd.read_csv(P2 / "p2_ci_width.csv")
    rows = [[DIST.get(r.distribution, esc(r.distribution)), sc(r.scale), str(int(r.cutoff)) + ("$^*$" if r.is_c_star else ""),
             f3(r.r), f"{r.width_ci2:.4f}", f"{r.width_ci1:.4f}", f"{r.ratio_ci2_over_ci1:.2f}"] for _, r in w.iterrows()]
    body = longtable("llrcccc", ["Phân bố", "Thang", "$c$", "$r$", hc("Rộng CI", "hai tầng"), hc("Rộng CI", "một tầng"), "Tỉ số"], rows,
                     "Độ rộng CI hai tầng so với CI một tầng (dấu sao: $c = c^*$).", "tab:ci_width")
    write("ta_ci_width", body, "P2/p2_ci_width.csv (distribution, scale, cutoff, is_c_star, r, width_ci2, width_ci1, ratio_ci2_over_ci1)")
    return len(rows)


def ta_h13():
    h = pd.read_csv(P2 / "p2_H13.csv")
    h = h[h.row_type == "per_k"]
    rows = [[esc(r.pair), str(int(r.k)), f"{100 * r.delta_mean:+.2f}".replace("-", "$-$"), f"{100 * r.se_k:.2f}",
             f"{r.z_k:+.2f}".replace("-", "$-$"), "đạt" if r["pass"] else "\\textbf{không}"] for _, r in h.iterrows()]
    body = longtable("lrrrrc", ["Cặp", "$k$", "$\\bar\\Delta$ (\\%)", "$se_k$ (\\%)", "$z_k$", hc("$|\\bar\\Delta|$", "$\\le 1\\%$")], rows,
                     "Đối chứng cùng cây: $\\bar\\Delta(k)$ theo từng $k$ và cặp CUTOFF cho cùng cây đệ quy.", "tab:h13")
    write("ta_h13", body, "P2/p2_H13.csv (row_type = per_k: pair, k, delta_mean, se_k, z_k, pass)",
          note=f"{len(rows)} ô; không đạt: {int((~h['pass']).sum())}.")
    return len(rows)


def ta_verdicts_full():
    h = pd.concat([pd.read_csv(P2 / "h_verdicts.csv"), pd.read_csv(P2B / "h2b_verdicts.csv")], ignore_index=True)
    rows = []
    for _, r in h.iterrows():
        cm = "" if pd.isna(r.condition_met) else ("đạt" if str(r.condition_met) == "True" else "không đạt")
        v = "" if pd.isna(r.verdict_overall) else sym(str(r.verdict_overall))
        rows.append([esc(r.id), brk(sym(str(r.subcase))), brk(sym(str(r.value))), brk(sym(str(r.threshold))), cm, v])
    body = longtable("p{0.8cm}p{2.2cm}p{3.9cm}p{3.2cm}p{1.1cm}p{2.4cm}", ["Mã", "Điều kiện con", "Giá trị", "Ngưỡng", "Ô", "Kết quả"], rows,
                     "Mọi điều kiện con của 32 tiêu chí ghi trước khi đo.", "tab:verdicts_full", size="\\scriptsize")
    write("ta_verdicts_full", body, "P2/h_verdicts.csv, P2B/h2b_verdicts.csv (id, subcase, value, threshold, condition_met, verdict_overall)")
    return len(rows)


def ta_jmh_full():
    s = pd.read_csv(P2B / "p2b_jmh_scores.csv")
    r = pd.read_csv(P2B / "p2b_jmh_r.csv")
    m = s.merge(r[["input", "profile", "reset", "N", "cutoff", "r", "ci_lo", "ci_hi"]], on=["input", "profile", "reset", "N", "cutoff"],
                suffixes=("", "_r"))
    assert len(m) == 72
    rows = [["+".join([x.input, x.profile, x.reset]), str(int(x.N)), str(int(x.cutoff)),
             f"{x.score_us:.1f} [{x.ci_lo:.1f}, {x.ci_hi:.1f}]", f"{x.score_error_999_us:.1f}", ci(x.r, x.ci_lo_r, x.ci_hi_r)]
            for x in m.itertuples()]
    body = longtable("lrrccc", ["Cấu hình", "$N$", "$c$", "Score (µs) [CI]", hc("Score Error", "99.9\\%"), "$r$ [CI]"], rows,
                     "JMH yếu tố đầy đủ (lần 3): mọi cấu hình; CI bootstrap 95\\% theo fork.", "tab:jmh_full")
    write("ta_jmh_full", body, "P2B/p2b_jmh_scores.csv (score_us, ci_lo, ci_hi, score_error_999_us); P2B/p2b_jmh_r.csv (r, ci_lo, ci_hi)")
    return len(rows)


def ta_jmh_effects():
    e = pd.read_csv(P2B / "p2b_jmh_effects.csv")
    rows = [[esc(x.effect), esc(x.stratum), str(int(x.N)), str(int(x.cutoff)), f"{x.score_num_us:.1f}", f"{x.score_den_us:.1f}",
             ci(x.ratio, x.ci_ratio_lo, x.ci_ratio_hi)] for x in e.itertuples()]
    body = longtable("llrrrrc", ["Hiệu ứng", "Tầng", "$N$", "$c$", "Tử (µs)", "Mẫu (µs)", "Tỉ số [CI]"], rows,
                     "Hiệu ứng của từng yếu tố trong JMH yếu tố đầy đủ (E\\_in: fresh/same; E\\_prof: mixed/pure; E\\_reset: gc/none) theo tầng.",
                     "tab:jmh_effects")
    write("ta_jmh_effects", body, "P2B/p2b_jmh_effects.csv (effect, stratum, N, cutoff, score_num_us, score_den_us, ratio, ci_ratio_lo, ci_ratio_hi)")
    return len(rows)


def ta_int_full():
    r = pd.read_csv(P2B / "p2b_int_r_by_cutoff.csv").set_index(["scale", "cutoff"])
    cs = sorted({c for _, c in r.index})
    rows = [[str(c)] + [ci(r.loc[(s, c)].r, r.loc[(s, c)].ci2_lo, r.loc[(s, c)].ci2_hi) for s in S3] for c in cs]
    body = longtable("rccc", ["$c$"] + [f"$r$ [CI] {sc(s)}" for s in S3], rows,
                     "int[] mở rộng (6 fork): $r(c)$ với CI hai tầng 95\\%, lưới 43 CUTOFF.", "tab:int_full")
    write("ta_int_full", body, "P2B/p2b_int_r_by_cutoff.csv (scale, cutoff, r, ci2_lo, ci2_hi)")
    return len(rows)


def ta_d3_full():
    r = pd.read_csv(P2 / "p2_d3_r_by_cutoff.csv").set_index(["key", "scale", "cutoff"])
    parts = []
    n = 0
    for key, lab in [("integer", "Integer[]"), ("double", "Double[]"), ("int", "int[]")]:
        cs = sorted({c for k, _, c in r.index if k == key})
        rows = [[str(c)] + [ci(r.loc[(key, s, c)].r, r.loc[(key, s, c)].ci2_lo, r.loc[(key, s, c)].ci2_hi) for s in S3] for c in cs]
        n += len(rows)
        parts.append(longtable("rccc", ["$c$"] + [f"$r$ [CI] {sc(s)}" for s in S3], rows,
                               f"Thí nghiệm kiểu khóa, {lab} (3 fork): $r(c)$ với CI hai tầng 95\\%.", f"tab:d3_full_{key}"))
    write("ta_d3_full", "\n\n".join(parts), "P2/p2_d3_r_by_cutoff.csv (key, scale, cutoff, r, ci2_lo, ci2_hi)")
    return n


def ta_prereg_commits():
    pats = [("kế hoạch", r"Kế hoạch doubling test sơ bộ: dự đoán"), ("kế hoạch", r"Kế hoạch doubling test sơ bộ: bổ sung"),
            ("dữ liệu", r"Dữ liệu doubling test sơ bộ"), ("kế hoạch", r"Kế hoạch các phép đo chính"),
            ("dữ liệu", r"Dữ liệu thô các phép đo chính"), ("phân tích", r"Phân tích các phép đo chính"),
            ("kế hoạch", r"Kế hoạch JMH yếu tố đầy đủ"), ("kế hoạch (bổ sung)", r"Kế hoạch JMH: bổ sung"),
            ("dữ liệu", r"Dữ liệu int\[\] mở rộng"), ("dữ liệu (loại)", r"Lần đo JMH thứ hai"),
            ("dữ liệu", r"Dữ liệu JMH yếu tố đầy đủ"), ("phân tích", r"Phân tích JMH yếu tố đầy đủ")]
    out = git("log", "--format=%h\t%ct\t%s", "--all")
    rows = []
    for kind, pat in pats:
        hits = [ln.split("\t") for ln in out.splitlines() if re.match(pat, ln.split("\t")[2])]
        if len(hits) != 1:
            raise SystemExit(f"DỪNG: mẫu {pat!r} khớp {len(hits)} commit")
        hsh, ts, subj = hits[0]
        t = pd.Timestamp(int(ts), unit="s", tz="UTC").tz_convert("Asia/Saigon")
        rows.append((int(ts), [f"\\texttt{{{hsh}}}", t.strftime("%Y-%m-%d %H:%M"), kind, esc(subj[:90])]))
    rows = [r for _, r in sorted(rows)]
    write("ta_prereg_commits", "\\setlength{\\tabcolsep}{3pt}\n" +
          tabular("lllX", ["Commit", "Thời điểm (UTC+7)", "Loại", "Tiêu đề commit"], rows, env="tabularx", width="\\linewidth"),
          "git log --format='%h %ct %s' --all (lọc theo tiêu đề; không gõ tay hash)",
          note="Thời điểm: committer date (%ct) đổi sang Asia/Saigon (UTC+7) cho mọi dòng.")
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="Sinh bảng .tex báo cáo bản 2 (T14) vào report/tables/. Chạy từ thư mục gốc dự án.")
    ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, fn in [("t01_correctness", t01_correctness), ("t02_env", t02_env), ("t04_verdicts", t04_verdicts),
                     ("t05_rq1", t05_rq1), ("t06_rq3", t06_rq3), ("t07_other_dist", t07_other_dist),
                     ("t08_doubling_v2", t08_doubling_v2), ("t09_cost_model", t09_cost_model), ("t10_key_types", t10_key_types),
                     ("t11_jmh", t11_jmh), ("t12_memory", t12_memory), ("ta_session_quality", ta_session_quality),
                     ("ta_fork4", ta_fork4), ("ta_ci_width", ta_ci_width), ("ta_h13", ta_h13), ("ta_verdicts_full", ta_verdicts_full),
                     ("ta_jmh_full", ta_jmh_full), ("ta_jmh_effects", ta_jmh_effects), ("ta_int_full", ta_int_full),
                     ("ta_d3_full", ta_d3_full), ("ta_prereg_commits", ta_prereg_commits)]:
        counts[name] = fn()
    t01b_mutation()
    n3, _ = t03_design()
    counts["t03_design"] = n3
    print("\nSố dòng dữ liệu theo bảng:", counts)
    bad = report_checks()
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
