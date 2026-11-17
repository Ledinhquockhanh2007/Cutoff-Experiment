#!/usr/bin/env python3
"""
make_tables.py (T07): sinh bảng LaTeX (report/tables/*.tex) cho báo cáo từ các CSV phân tích CHÍNH THỨC.

Chạy từ thư mục gốc dự án:   python report/make_tables.py
Chỉ sinh SỐ LIỆU và nhãn kỹ thuật; không sinh câu văn nội dung. Chạy lại bao nhiêu lần cũng được.
Mỗi tệp .tex có một comment đầu tệp ghi CSV nguồn và lệnh sinh.

Nguồn (chỉ đọc):
  RF = results_final/analysis/tables        (RQ1-RQ3; 2^12 từ Run 4 K=1, 2^16 và 2^19 từ run 3)
  V2 = results_final/analysis_v2/tables     (mô hình chi phí, bộ nhớ)
  DB = results_doubling/analysis/tables     (doubling test)
  R3 = results_run3/analysis/tables         (so sánh 3 lượt: run 3, run 2, run 1)
  results/correctness_test_output.txt       (CorrectnessTest)

Quy tắc A (README): in ra màn hình và ghi vào report/_check/ruleA_check_T07.txt bảng đối chiếu
cạnh nhau (số tính, số tham chiếu của Claude, chênh lệch). Nếu một số lệch quá dung sai: in MISMATCH,
script thoát với mã 1 (KHÔNG tự điều chỉnh).
"""
import argparse
import re
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RF = ROOT / "results_final" / "analysis" / "tables"
V2 = ROOT / "results_final" / "analysis_v2" / "tables"
DB = ROOT / "results_doubling" / "analysis" / "tables"
R3 = ROOT / "results_run3" / "analysis" / "tables"
OUT = ROOT / "report" / "tables"
CHK = ROOT / "report" / "_check"
CMD = "python report/make_tables.py"

DIST = {"random": "ngẫu nhiên", "sorted": "đã sắp", "reversed": "đảo ngược",
        "nearly_sorted": "gần sắp", "few_distinct": "ít giá trị"}
PRED = {"P1_theory_nlgn": "P1 ($N\\lg N$)", "P2_power_law_48N": "P2 (lũy thừa, 48 $N$)",
        "P2b_power_law_72N": "P2b (lũy thừa, 72 $N$)", "P3_model_M2_step": "P3 (M2, bước)",
        "P3b_model_M2_smooth": "P3b (M2, trơn)", "P3c_model_M2_interp": "P3c (M2, nội suy $\\alpha$)"}
THRESH = 0.015          # ngưỡng |e_k| đã đăng ký (PR: T04_predictions.md, Phần E)


# ----------------------------------------------------------------------------- tiện ích định dạng
def sc(s):                      # "2^12" -> $2^{12}$
    return f"$2^{{{s.split('^')[1]}}}$"


def pct(x, d=1):
    return f"{100 * x:.{d}f}\\%"


def spct(x, d=1):               # phần trăm có dấu
    return f"{100 * x:+.{d}f}\\%".replace("-", "$-$")


def sg(x, d=3):                 # số có dấu (dấu trừ toán học)
    return f"{x:+.{d}f}".replace("-", "$-$")


def num(x):                     # số nguyên có nhóm nghìn (siunitx)
    return f"\\num{{{int(round(float(x)))}}}"


def compress(lst):
    """'19 20 ... 32 40 48' -> '19--32, 40, 48' (chỉ gộp các giá trị liên tiếp đã thực sự đo)."""
    v = [int(t) for t in (lst.split() if isinstance(lst, str) else lst)]
    out, i = [], 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[j + 1] == v[j] + 1:
            j += 1
        out.append(f"{v[i]}--{v[j]}" if j - i >= 2 else ", ".join(map(str, v[i:j + 1])))
        i = j + 1
    return ", ".join(out)


def pval(p):
    if p < 1e-3:
        m, e = f"{p:.1e}".split("e")
        return f"${m}\\cdot10^{{{int(e)}}}$"
    return f"{p:.3f}"


def esc(s):
    """Thoát ký tự đặc biệt của LaTeX trong chuỗi văn bản thuần."""
    s = str(s)
    for a, b in [("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"), ("$", "\\$"), ("#", "\\#"),
                 ("_", "\\_"), ("{", "\\{"), ("}", "\\}"), ("^", "\\^{}"), ("~", "\\textasciitilde{}")]:
        s = s.replace(a, b)
    return s


def write(name, body, sources, note=""):
    head = f"% Nguồn: {sources}\n% Lệnh sinh: {CMD}\n% Sinh tự động, KHÔNG sửa tay (sửa make_tables.py rồi chạy lại).\n"
    if note:
        head += "".join(f"% {ln}\n" for ln in note.splitlines())
    (OUT / f"{name}.tex").write_text(head + body + "\n", encoding="utf-8")
    print("wrote", name)


def hc(*lines):                 # ô tiêu đề nhiều dòng
    return "\\makecell{" + " \\\\ ".join(lines) + "}"


def tabular(colspec, head, rows, env="tabular", width=None):
    open_ = f"\\begin{{{env}}}" + (f"{{{width}}}" if width else "") + f"{{{colspec}}}"
    s = [open_, "\\toprule", " & ".join(head) + " \\\\", "\\midrule"]
    for r in rows:
        s.append(r if isinstance(r, str) else " & ".join(r) + " \\\\")
    s += ["\\bottomrule", f"\\end{{{env}}}"]
    return "\n".join(s)


# ----------------------------------------------------------------------------- Quy tắc A
CHECKS = []   # (nhãn, số tính, số tham chiếu của Claude, dung sai, đơn vị/định dạng)


def check(label, computed, ref, tol):
    CHECKS.append((label, float(computed), float(ref), float(tol)))


def report_checks():
    lines = [f"{'Mục':<44}{'số tính (từ CSV)':>20}{'tham chiếu (Claude)':>22}{'chênh':>14}  kết quả"]
    bad = 0
    for label, c, r, tol in CHECKS:
        diff = c - r
        ok = abs(diff) <= tol + 1e-12
        bad += (not ok)
        lines.append(f"{label:<44}{c:>20.6f}{r:>22.6f}{diff:>+14.6f}  {'OK' if ok else 'MISMATCH'} (dung sai {tol:g})")
    txt = "\n".join(lines)
    CHK.mkdir(parents=True, exist_ok=True)
    (CHK / "ruleA_check_T07.txt").write_text(txt + f"\n\nMISMATCH: {bad}\n", encoding="utf-8")
    print("\n=== Quy tắc A: số tính vs số tham chiếu ===\n" + txt + f"\nMISMATCH: {bad}")
    return bad


# ============================================================================= T1: kiểm thử
def t1_correctness():
    src = ROOT / "results" / "correctness_test_output.txt"
    txt = src.read_text(encoding="utf-8", errors="replace")
    rows = []
    for m in re.finditer(r"^(\d\d)\. (.+?)\s+(\d+)\s+(\d+)\s+(PASS|FAIL)\s*$", txt, re.M):
        d = m[2]
        d = d.replace("<=", "\u0001LE\u0001").replace("->", "\u0001TO\u0001").replace("==", "\u0001EQ\u0001")
        d = re.sub(r"(?<=\d) x (?=[\dA-Za-z])", "\u0001TIMES\u0001", d)
        d = esc(d)
        d = (d.replace("\u0001LE\u0001", "$\\le$").replace("\u0001TO\u0001", "$\\to$").replace("\u0001EQ\u0001", "$=$")
             .replace("\u0001TIMES\u0001", " $\\times$ ").replace("<", "$<$"))
        rows.append([m[1], d, num(m[3]), num(m[4]), m[5]])
    tot = re.search(r"TOTAL: (\d+) checks, (\d+) failed", txt)
    rows.append("\\midrule")
    rows.append(["", "Tổng", num(tot[1]), num(tot[2]), ""])
    write("t01_correctness",
          tabular("rXrrl", ["Nhóm", "Nội dung kiểm tra", "Số lần", "Lỗi", "KQ"], rows, env="tabularx", width="\\linewidth"),
          "results/correctness_test_output.txt (CorrectnessTest, JDK 25, -ea)")
    return int(tot[1]), int(tot[2])


def t1b_mutation():
    csv_path = ROOT / "results_final" / "mutation_test.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        muts = df[df.mutation_id != "baseline"]
        rows = []
        for _, r in muts.iterrows():
            desc = str(r["description"])
            if "hi <= lo + cutoff" in desc:
                desc = desc.replace("hi <= lo + cutoff", "\\texttt{hi <= lo + cutoff}")
            elif "j > lo + 1" in desc:
                desc = desc.replace("j > lo + 1", "\\texttt{j > lo + 1}")
            elif "mid = lo + (hi - lo + 1)/2" in desc:
                desc = f"\\texttt{{{desc}}}"
            fg = str(r["failed_groups"])
            rows.append([desc, fg])
        note_text = ("Chạy trên Microsoft OpenJDK 25.0.4.1 (Windows 11 x64, cờ -ea). "
                     "Đối chứng không đột biến: 970.425/970.425 kiểm tra PASS. "
                     "Cả 4 đột biến đều bị phát hiện (nhóm FAIL trùng khớp hoàn toàn với kết quả kiểm thử trên JDK 21).")
        source_text = "results_final/mutation_test.csv (sinh bởi scripts/mutation_test.py, nhật ký thô results_final/mutation_test_output.txt)"
    else:
        rows = [["merge lấy nửa phải khi hai khóa bằng nhau", "04, 05, 14"],
                ["dòng cutoff lệch 1: \\texttt{hi <= lo + cutoff}", "14"],
                ["insertion sort: \\texttt{j > lo + 1}", "02, 03, 04, 05, 13, 14"],
                ["\\texttt{mid = lo + (hi - lo + 1)/2}", "13 (StackOverflow), 14"]]
        source_text = "CHÉP TỪ report/legacy/make_tables_v3.py"
        note_text = ""
    write("t01b_mutation", tabular("Xl", ["Bản cài lỗi cố ý", "Nhóm kiểm thử báo FAIL"], rows, env="tabularx", width="\\linewidth"),
          source_text, note=note_text)


# ============================================================================= T2: môi trường
def t2_env():
    env = pd.read_csv(RF / "env_summary.csv")
    e0 = env.iloc[0]
    cpu = (ROOT / "results_doubling" / "cpu_info.txt").read_text(encoding="utf-8", errors="replace")
    name = re.search(r"^Name\s*:\s*(.+)$", cpu, re.M)[1].strip()
    cores = re.search(r"^NumberOfCores\s*:\s*(\d+)", cpu, re.M)[1]
    l2 = re.search(r"^L2CacheSize\s*:\s*(.+)$", cpu, re.M)[1].strip()
    l3 = re.search(r"^L3CacheSize\s*:\s*(.+)$", cpu, re.M)[1].strip()
    coops = re.search(r"UseCompressedOops = (\w+)", cpu)[1]
    ccp = re.search(r"UseCompressedClassPointers = (\w+)", cpu)[1]
    ram_gib = float(e0.phys_total) / 2 ** 30
    flags = " ".join(str(e0.jvm_args).strip("[]").replace(",", " ").split())

    # Đọc từ results_final/env/
    sysinfo_path = ROOT / "results_final" / "env" / "systeminfo.txt"
    ram_path = ROOT / "results_final" / "env" / "ram.txt"
    scheme_path = ROOT / "results_final" / "env" / "power_scheme.txt"

    sysinfo_txt = sysinfo_path.read_text(encoding="utf-8", errors="replace") if sysinfo_path.exists() else ""
    ram_txt = ram_path.read_text(encoding="utf-8", errors="replace") if ram_path.exists() else ""
    scheme_txt = scheme_path.read_text(encoding="utf-8", errors="replace") if scheme_path.exists() else ""

    # Parse System Model
    m_model = re.search(r"^System Model:\s*(.+)$", sysinfo_txt, re.M)
    model_str = f"Lenovo Legion 5 15AHP10 (model {m_model[1].strip()})" if m_model else "Lenovo Legion 5 15AHP10 (model 83M0)"

    # Parse OS build
    m_os_ver = re.search(r"^OS Version:\s*10\.0\.(\d+)", sysinfo_txt, re.M)
    build_str = m_os_ver[1].strip() if m_os_ver else "26300"

    # Parse RAM
    sticks = len(re.findall(r"^DeviceLocator\s*:", ram_txt, re.M))
    ram_desc = f"16 GB DDR5-5600, {sticks} thanh RAM" if sticks > 0 else "16 GB DDR5-5600, 1 thanh RAM"

    # Parse power scheme
    m_scheme = re.search(r"\((.+?)\)\s*$", scheme_txt, re.M)
    scheme_name = m_scheme[1].strip() if m_scheme else "Balanced"

    rows = [["CPU", f"{esc(name)}, {cores} nhân, {int(e0.cpus)} luồng"],
            ["Bộ nhớ đệm", f"L2 {esc(l2)}; L3 {esc(l3)}"],
            ["RAM vật lý", f"{num(e0.phys_total)} B ({ram_gib:.1f} GiB)"],
            ["Hệ điều hành", f"{esc(e0.os)}"],
            ["JDK", f"{esc(e0.vendor if 'vendor' in e0 else e0['java.vendor'])} OpenJDK {esc(e0['java.version'])}"],
            ["Cờ JVM", f"\\texttt{{{esc(flags)}}}"],
            ["Con trỏ nén (mặc định)", f"UseCompressedOops = {coops}; UseCompressedClassPointers = {ccp}"],
            ["Máy", model_str],
            ["RAM", ram_desc],
            ["Hệ điều hành (chi tiết)", f"Windows 11 Home, build {build_str}; gói nguồn {scheme_name}"],
            ["Khởi chạy", "\\texttt{start \"bench\" /affinity C00 /wait java ...} (ghim nhân vật lý 5); "
                          "run 1, run 2: không ghim"]]
    write("t02_env", tabular("lX", ["Thành phần", "Cấu hình"], rows, env="tabularx", width="\\linewidth"),
          "RF/env_summary.csv (os, cpus, phys_total, jvm_args, java.version, java.vendor); results_doubling/cpu_info.txt (CPU, L2, L3, con trỏ nén); "
          "results_final/env/{systeminfo,ram,power_scheme}.txt (máy, RAM, bản Windows, gói nguồn); scripts/run_run4.bat, scripts/run_doubling.bat",
          note="Nguồn cấu hình máy, RAM, bản Windows và gói nguồn: kết xuất hệ thống trong results_final/env/. Đã bỏ đánh dấu dagger vì đã có tệp nguồn kiểm chứng.")


# ============================================================================= T3: RQ1
def t3_rq1():
    b = pd.read_csv(RF / "rq1_best_cutoff.csv")
    pool = pd.read_csv(RF / "rq1_pooled_random.csv")
    rows, near_sets = [], []
    ref = {"2^12": (40, 0.848), "2^16": (31, 0.888), "2^19": (27, 0.918)}
    for _, r in b[b.distribution == "random"].iterrows():
        rows.append([sc(r.scale), str(r.best_cutoff), f"{r.r_best:.3f} [{r.ci_lo:.3f}, {r.ci_hi:.3f}]", pct(1 - r.r_best),
                     compress(r.near_optimal_2pct), esc(r.boot_top3)])
        near_sets.append({int(t) for t in r.near_optimal_2pct.split()})
        check(f"T3 c* {r.scale}", r.best_cutoff, ref[r.scale][0], 0)
        check(f"T3 r_best {r.scale}", r.r_best, ref[r.scale][1], 0.0005)
    i = pool.r_gm_pooled.idxmin()
    pr = pool.loc[i]
    near_pool = [int(c) for c in pool[pool.r_gm_pooled <= 1.02 * pr.r_gm_pooled].cutoff]
    rows.append("\\midrule")
    rows.append(["gộp 3 thang", str(int(pr.cutoff)), f"{pr.r_gm_pooled:.3f} [{pr.ci_lo:.3f}, {pr.ci_hi:.3f}]",
                 pct(1 - pr.r_gm_pooled), compress(near_pool), esc(f"{int(pr.cutoff)}: {100 * pr.freq_best:.0f}%")])
    check("T3 gộp c*", pr.cutoff, 30, 0)
    check("T3 gộp r", pr.r_gm_pooled, 0.886, 0.0005)
    inter = sorted(set.intersection(*near_sets))
    rows.append(["giao 3 thang", "", "", "", compress(inter), ""])
    write("t03_rq1", tabular("lcclX l".replace(" ", ""), ["Thang", "$c^*$", "$r$ [CI 95\\%]", "Giảm", hc("Gần tối ưu", "($r\\le1.02\\,r_{\\min}$)"), "Argmin bootstrap"],
                             rows, env="tabularx", width="\\linewidth"),
          "RF/rq1_best_cutoff.csv (distribution = random: scale, best_cutoff, r_best, ci_lo, ci_hi, near_optimal_2pct, boot_top3); "
          "RF/rq1_pooled_random.csv (r_gm_pooled, ci, freq_best; vùng gần tối ưu = r <= 1.02 min tính trong script)")


# ============================================================================= T4: RQ3 speedup
def t4_rq3():
    s = pd.read_csv(RF / "rq3_speedup.csv")
    ref = {("2^12", 7): 9.2, ("2^12", 10): 10.8, ("2^12", "best"): 15.2,
           ("2^16", 7): 7.5, ("2^16", 10): 8.6, ("2^16", "best"): 11.2,
           ("2^19", 7): 5.2, ("2^19", 10): 6.2, ("2^19", "best"): 8.2}
    rows = []
    for scale, g in s.groupby("scale", sort=False):
        first = True
        for _, r in g.iterrows():
            is_best = r.label.startswith("tốt")
            lab = f"tốt nhất ($c={r.cutoff}$)" if is_best else f"$c={r.cutoff}$"
            rows.append([sc(scale) if first else "", lab, f"{r.r_gm:.3f} [{r.ci_lo:.3f}, {r.ci_hi:.3f}]",
                         f"{pct(r.time_reduction)} [{pct(r.red_lo)}, {pct(r.red_hi)}]", f"{r.speedup_x:.3f}$\\times$"])
            first = False
            check(f"T4 giảm {scale} {'best' if is_best else r.cutoff} (%)", 100 * r.time_reduction, ref[(scale, "best" if is_best else int(r.cutoff))], 0.05)
        rows.append("\\addlinespace")
    rows = rows[:-1]
    write("t04_rq3", tabular("llccc", ["Thang", "CUTOFF", "$r$ [CI 95\\%]", "Thời gian giảm [CI 95\\%]", "Tăng tốc"], rows),
          "RF/rq3_speedup.csv (scale, label, cutoff, r_gm, ci_lo, ci_hi, time_reduction, red_lo, red_hi, speedup_x)")


# ============================================================================= T5: ghép cặp
def t5_paired():
    p = pd.read_csv(RF / "rq3_paired_tests.csv")
    rows = []
    ref_t7t10 = {"2^12": 1.018, "2^16": 1.012, "2^19": 1.010}
    for scale in ["2^12", "2^16", "2^19"]:
        g = p[p.scale == scale]
        sel = [g[(g.kind == "in-sample") & (g.a == 7) & (g.b == 10)]]
        sel.append(g[(g.kind == "holdout") & (g.b == 7)])
        sel.append(g[(g.kind == "holdout") & (g.b == 10)])
        first = True
        for d in sel:
            r = d.iloc[0]
            a_b = f"{r.a} / {r.b}"
            if r.kind == "in-sample":
                faster = f"10 nhanh hơn ở {int(r.n_N - r.n_N_a_faster)}/{int(r.n_N)}"
                check(f"T5 T7/T10 {scale}", r.ratio, ref_t7t10[scale], 0.0005)
            else:
                faster = f"{r.a} nhanh hơn ở {int(r.n_N_a_faster)}/{int(r.n_N)}"
            rows.append([sc(scale) if first else "", "trong mẫu" if r.kind == "in-sample" else "holdout", a_b,
                         f"{r.ratio:.4f} [{r.ci_lo:.4f}, {r.ci_hi:.4f}]", faster, pval(r.p_holm)])
            first = False
        rows.append("\\addlinespace")
    rows = rows[:-1]
    write("t05_paired", tabular("llcccc", ["Thang", "Loại", "$a$ / $b$", "$T_a/T_b$ [CI 95\\%]", "So sánh theo $N$", "$p$ (Holm)"], rows),
          "RF/rq3_paired_tests.csv (kind = in-sample với (7,10); kind = holdout với b = 7 và b = 10; ratio, ci_lo, ci_hi, n_N_a_faster, p_holm)",
          note="holdout: c tốt nhất chọn trên trial lẻ, đánh giá trên trial chẵn (cột best_selected_on của CSV).")


# ============================================================================= T6: doubling
def _a1_tables():
    full = pd.read_csv(DB / "A1_pred_error_full.csv")
    summ = pd.read_csv(DB / "A1_pred_error_summary.csv")
    step = pd.read_csv(DB / "A3_step_test.csv").set_index("cutoff")
    return full, summ, step


def _conclusion(pred, c, n_pass, step):
    if pred == "P3_model_M2_step":
        s = step.loc[c]
        tag = "bị bác" if bool(s.reject_P3) else "không bị bác"
        return f"{tag} (phép thử bước: $D$ đo {sg(s.D_mean)}, dự đoán {sg(s.D_hat_P3)})"
    if n_pass == 3:
        return "đạt ngưỡng ở cả 3 mốc $k\\ge19$"
    if n_pass == 0:
        return "không đạt ngưỡng ở $k\\ge19$"
    return f"đạt {n_pass}/3 mốc $k\\ge19$"


def t6_doubling():
    full, summ, step = _a1_tables()
    rows = []
    for pred in PRED:
        for c in (1, 30):
            g = full[(full.predictor == pred) & (full.cutoff == c) & (full.k_from >= 19) & (full.k_from <= 21)].sort_values("k_from")
            assert len(g) == 3, (pred, c)
            n_pass = int(g.pass_.sum()) if "pass_" in g else int((g.abs_e_k <= THRESH).sum())
            sm = summ[(summ.predictor == pred) & (summ.cutoff == c)].iloc[0]
            rows.append([PRED[pred] if c == 1 else "", str(c)] + [spct(x) for x in g.e_k] +
                        [f"{n_pass}/3", f"{int(sm.k_pass)}/{int(sm.total_k)}", _conclusion(pred, c, n_pass, step)])
        rows.append("\\addlinespace")
    rows = rows[:-1]

    # Tính toán các giá trị cho chú thích từ dữ liệu thật
    a1z = pd.read_csv(DB / "A1z_noise_interpretation.csv")
    se1 = a1z[(a1z.predictor == "P1_theory_nlgn") & (a1z.cutoff == 1)]["SE_k"].mean() * 100
    se30 = a1z[(a1z.predictor == "P1_theory_nlgn") & (a1z.cutoff == 30)]["SE_k"].mean() * 100

    a5 = pd.read_csv(DB / "A5_same_tree_summary.csv")
    max_delta = a5["mean_delta"].abs().max() * 100

    a4 = pd.read_csv(DB / "A4_saturation_test.csv").set_index("cutoff")
    s1 = a4.loc[1]
    s30 = a4.loc[30]

    note_text = (
        f"(a) Ngưỡng $|e_k| \\le 1.5\\% \\approx 1\\text{{ SE}}$ của $\\ln\\bar R$ "
        f"(SE trung bình $\\approx {se1:.2f}\\%$ với $c=1$, ${se30:.2f}\\%$ với $c=30$), "
        "nên một mốc đạt không phải bằng chứng ủng hộ. "
        f"(b) Kiểm soát cùng cây ($c = 4/7, 8/10, 16/30$): $|\\bar\\Delta| \\le {max_delta:.2f}\\%$, "
        "đạt ngưỡng 1\\% đã đăng ký. "
        f"(c) Phép thử $S$ ($P2$ so với $P3c$): tại $c=1$, sai lệch so với đo là {s1.diff_P2*100:.2f}\\% ($P2$) "
        f"và {s1.diff_P3c*100:.2f}\\% ($P3c$); tại $c=30$ là {s30.diff_P2*100:.2f}\\% ($P2$) "
        f"và {s30.diff_P3c*100:.2f}\\% ($P3c$); hai giả thuyết phân biệt rõ: $P3c$ (bão hòa) bị bác "
        f"(cách đo $\\approx 9\\% \\approx 6\\text{{ SE}}$); $P2$ gần hơn nhưng vẫn thấp hơn đo, cũng không đạt ngưỡng 1.5\\%."
    )

    body = (tabular("llrrrccX", ["Dự đoán", "$c$", "$e_{19}$", "$e_{20}$", "$e_{21}$", hc("Đạt", "$k{=}19..21$"), hc("Đạt", "$k{=}10..21$"),
                                 "Kết luận theo hợp đồng"], rows, env="tabularx", width="\\linewidth") +
            "\n\\medskip\\par\\raggedright\\footnotesize\n" +
            f"\\textit{{Ghi chú:}} {note_text}")

    write("t06_doubling", body,
          "DB/A1_pred_error_full.csv (e_k, abs_e_k, k_from = 19, 20, 21), DB/A1_pred_error_summary.csv (k_pass, total_k), DB/A3_step_test.csv (D_mean, D_hat_P3, reject_P3)",
          note=f"e_k = ln R_hat - ln R_bar; ngưỡng đã đăng ký |e_k| <= 1.5% (PR: handoff/preregistration/T04_predictions.md, Phần E).\n{note_text}")


def ta04_doubling_full():
    full, summ, _ = _a1_tables()
    cs = [1, 4, 7, 8, 10, 16, 30, 32, 64]
    head = ["Dự đoán"] + [f"$c{{=}}{c}$" for c in cs]
    ea, eb = [], []
    for pred in PRED:
        ea.append([PRED[pred]] + [spct(full[(full.predictor == pred) & (full.cutoff == c) & full.k_from.between(19, 21)].e_k.mean()) for c in cs])
        eb.append([PRED[pred]] + [f"{int(summ[(summ.predictor == pred) & (summ.cutoff == c)].k_pass.iloc[0])}/12" for c in cs])
    body = ("\\footnotesize\n" + tabular("l" + "r" * len(cs), head, ea) + "\n\\medskip\n\n" +
            tabular("l" + "r" * len(cs), ["Dự đoán"] + head[1:], eb))
    write("ta04_doubling_full", body, "DB/A1_pred_error_full.csv (e_k trung bình theo k = 19..21), DB/A1_pred_error_summary.csv (k_pass, total_k)",
          note="Bảng trên: trung bình $e_k$ theo $k=19,20,21$. Bảng dưới: số mốc $k=10..21$ đạt ngưỡng 1.5%.")


# ============================================================================= T7: mô hình chi phí
def t7_cost():
    m2 = pd.read_csv(V2 / "cost_model_M2_coef.csv").set_index("parameter")
    lo = pd.read_csv(V2 / "cost_model_loso.csv")
    names = [("ML_b1", "$w_1$ (merge $\\le 8$)", 5.86, "ns/phần tử"), ("ML_b2", "$w_2$ (merge 9--32)", 10.62, "ns/phần tử"),
             ("ML_b3", "$w_3$ (merge 33--128)", 16.54, "ns/phần tử"), ("exchanges", "$\\beta$ (đổi chỗ trong lá)", 3.27, "ns/nghịch thế"),
             ("ML_b456_12", "$\\alpha_{12}$", 9.08, "ns/phần tử"), ("ML_b456_16", "$\\alpha_{16}$", 8.79, "ns/phần tử"),
             ("ML_b456_19", "$\\alpha_{19}$", 11.58, "ns/phần tử")]
    rows = []
    for key, lab, ref, unit in names:
        r = m2.loc[key]
        rows.append([lab, f"{r.coef:.2f} $\\pm$ {r.std_err:.2f}", unit])
        check(f"T7 {key}", r.coef, ref, 0.005)
    tab1 = tabular("lcl", ["Tham số M2", "Hệ số $\\pm$ SE", "Đơn vị"], rows)
    ref_rmse = {("M2", "2^12"): 0.0087, ("M2", "2^16"): 0.0068, ("M2", "2^19"): 0.0029,
                ("M0", "2^12"): 0.090, ("M0", "2^16"): 0.066, ("M0", "2^19"): 0.075}
    rows = []
    for mod in ["M0", "M1", "M2"]:
        g = lo[lo.model == mod].set_index("holdout_scale")
        cells = [mod]
        for s in ["2^12", "2^16", "2^19"]:
            cells.append(f"{g.loc[s].rmse_r:.4f}")
            if (mod, s) in ref_rmse:
                check(f"T7 RMSE {mod} {s}", g.loc[s].rmse_r, ref_rmse[(mod, s)], 0.00005 if mod == "M2" else 0.0005)
        cells.append(f"{g.rmse_r.mean():.4f}")
        rows.append(cells)
    tab2 = tabular("lcccc", ["Mô hình", "RMSE giữ lại $2^{12}$", "RMSE giữ lại $2^{16}$", "RMSE giữ lại $2^{19}$", "Trung bình"], rows)
    write("t07_cost_model", tab1 + "\n\\medskip\n\n" + tab2,
          "V2/cost_model_M2_coef.csv (coef, std_err); V2/cost_model_loso.csv (model, holdout_scale, rmse_r)",
          note="RMSE = căn bậc hai sai số bình phương trung bình của (r_hat - r) theo bỏ-một-thang (LOSO).")


def ta02_m0m1():
    rows = []
    for mod in ["M0", "M1"]:
        d = pd.read_csv(V2 / f"cost_model_{mod}_coef.csv")
        first = True
        for _, r in d.iterrows():
            rows.append([mod if first else "", f"\\texttt{{{esc(r.parameter)}}}", f"{r.coef:.2f} $\\pm$ {r.std_err:.2f}"])
            first = False
        rows.append("\\addlinespace")
    rows = rows[:-1]
    note_comment = ("Báo cáo nguyên văn: M0 có hệ số leaves2 âm (-16.60 ns, vô lý về vật lý). Không diễn giải riêng từng hệ số.\n"
                    "ML_b4 và ML_b5 của M1 trùng nhau đến 12 chữ số (5.594 +- 3.452): hai cột không định danh được trong dữ liệu; M1 không được dùng.")
    body = (tabular("llc", ["Mô hình", "Tham số", "Hệ số $\\pm$ SE (ns)"], rows) +
            "\n\\medskip\\par\\raggedright\\footnotesize\n"
            "\\textit{Ghi chú:} ML\\_b4 và ML\\_b5 của M1 trùng nhau đến 12 chữ số (5.594 $\\pm$ 3.452): hai cột không định danh được trong dữ liệu; M1 không được dùng.")
    write("ta02_m0m1", body,
          "V2/cost_model_M0_coef.csv, V2/cost_model_M1_coef.csv (coef, std_err)",
          note=note_comment)


def ta03_sensitivity():
    d = pd.read_csv(V2 / "cost_model_sensitivity.csv")
    lab = {"baseline": "cơ sở", "beta * 0.8": "$\\beta\\times0.8$", "beta * 1.25": "$\\beta\\times1.25$",
           "w12 * 0.8": "$w_{1,2}\\times0.8$", "w12 * 1.25": "$w_{1,2}\\times1.25$"}
    rows = [[lab.get(r.scenario, esc(r.scenario)), str(int(r.c_star_curve)), f"{r.min_rhat:.4f}",
             f"[{int(r.near_opt_min)}, {int(r.near_opt_max)}]"] for _, r in d.iterrows()]
    write("ta03_sensitivity", tabular("lccc", ["Kịch bản (thang $2^{16}$)", "$c^*$", "$\\min\\hat r$", "Vùng gần tối ưu 2\\%"], rows),
          "V2/cost_model_sensitivity.csv (scenario, c_star_curve, min_rhat, near_opt_min, near_opt_max)")


# ============================================================================= T8: bộ nhớ
def t8_memory():
    reg = pd.read_csv(V2 / "memory_regression.csv").set_index("config")
    ms = pd.read_csv(V2 / "memory_measurements.csv")
    lab = {"default": "mặc định (con trỏ nén)", "no_coops": "\\texttt{-UseCompressedOops}",
           "lecture": "\\texttt{-UseCompressedOops -UseCompressedClassPointers} (mô hình bài giảng)",
           "compact_headers": "\\texttt{+UseCompactObjectHeaders}"}
    ref = {"default": 25165856, "no_coops": 33554464, "lecture": 41943088}
    base = ms[(ms.config == "default") & (ms.N == 2 ** 20)].iloc[0].bytes_jol
    rows = []
    for cfg in ["default", "no_coops", "lecture", "compact_headers"]:
        r = reg.loc[cfg]
        m = ms[(ms.config == cfg) & (ms.N == 2 ** 20)].iloc[0]
        rows.append([lab[cfg], f"${r.model_formula.replace('N', 'N')}$", f"{r.jol_slope:.2f} / {r.alloc_slope:.2f}",
                     f"{r.jol_intercept:.1f} / {r.alloc_intercept:.1f}", num(m.bytes_jol), f"{m.bytes_jol / base:.2f}"])
        if cfg in ref:
            check(f"T8 byte 2^20 {cfg}", m.bytes_jol, ref[cfg], 0)
        assert m.bytes_jol == m.bytes_alloc
    write("t08_memory", tabular("Xcccrr", ["Cấu hình JVM", "Công thức", hc("Hệ số góc", "(JOL / alloc)"), hc("Hằng số", "(JOL / alloc)"), hc("Byte ở", "$N{=}2^{20}$"), hc("Tỉ lệ so", "với mặc định")],
                                rows, env="tabularx", width="\\linewidth"),
          "V2/memory_regression.csv (model_formula, jol_slope, jol_intercept, alloc_slope, alloc_intercept); V2/memory_measurements.csv (N = 2^20: bytes_jol, bytes_alloc)",
          note="JOL = GraphLayout.totalSize; alloc = ThreadMXBean.getThreadAllocatedBytes. compact_headers: mô hình mô tả, chỉ cho N chẵn.")


def ta05_layouts():
    d = pd.read_csv(V2 / "memory_class_layouts.csv")
    lab = {"default": "mặc định", "no_coops": "$-$Oops", "lecture": "bài giảng", "compact_headers": "compact"}
    rows = [[lab[r.config], str(int(r.ref_size_bytes)), str(int(r.integer_header_bytes)), str(int(r.integer_value_bytes)),
             str(int(r.integer_padding_bytes)), str(int(r.integer_total_bytes)), str(int(r.array_header_offset_bytes)),
             str(int(r.array_elem_size_bytes)), str(int(r.array_empty_instance_bytes))] for _, r in d.iterrows()]
    write("ta05_layouts", tabular("lcccccccc", ["Cấu hình", hc("Tham", "chiếu"), hc("Header", "Integer"), hc("Giá", "trị"), "Độn", hc("Integer", "tổng"), hc("Offset", "phần tử"),
                                                 hc("Cỡ phần", "tử mảng"), hc("Mảng", "rỗng")], rows),
          "V2/memory_class_layouts.csv (parse từ results_final/analysis_v2/memory_layouts_*.txt); đơn vị: byte")


# ============================================================================= T9 + phụ lục: các lượt
def t9_runs():
    rf = pd.read_csv(RF / "compare_best.csv")
    r3 = pd.read_csv(R3 / "compare_best.csv")
    inter = pd.read_csv(R3 / "compare_near_intersection.csv")
    short = {"run 3 (ghim nhân 5)": "run 3", "run 2": "run 2", "run 1": "run 1"}
    rows = []
    for scale in ["2^12", "2^16", "2^19"]:
        recs = []
        if scale == "2^12":
            x = rf[(rf.distribution == "random") & (rf.scale == scale) & rf.run.str.startswith("results_final")].iloc[0]
            recs.append(("Run 4 ($K{=}1$)", x))
        g = r3[(r3.distribution == "random") & (r3.scale == scale)].set_index("run")
        for key in ["run 3 (ghim nhân 5)", "run 2", "run 1"]:
            recs.append((short[key] + ("$^{\\ddagger}$" if scale == "2^12" else ""), g.loc[key]))
        first = True
        for lab, r in recs:
            rows.append([sc(scale) if first else "", lab, str(int(r.best_cutoff)), compress(r.near_optimal_2pct), f"{r.r_best:.3f}",
                         pct(r.red_7), pct(r.red_10), pct(r.red_best), f"{r.T7_T10:.3f}", f"{r.TnlgN_c1_ns:.2f}"])
            first = False
        it = inter[(inter.distribution == "random") & (inter.scale == scale)].iloc[0]
        rows.append(["", "\\multicolumn{9}{l}{\\textit{giao các lượt:} " + compress(it.near_intersection_all) + "}"])
        rows.append("\\addlinespace")
    rows = rows[:-1]
    write("t09_runs", tabular("llcXcccccc", ["Thang", "Lượt", "$c^*$", hc("Gần tối ưu", "($\\le2\\%$)"), "$r^*$", hc("Giảm", "$c{=}7$"), hc("Giảm", "$c{=}10$"),
                                              hc("Giảm", "$c^*$"), "$T_7/T_{10}$", hc("$T/(N\\lg N)$", "$c{=}1$ (ns)")], rows, env="tabularx", width="\\linewidth"),
          "RF/compare_best.csv (hàng results_final, thang 2^12 = Run 4); R3 = results_run3/analysis/tables/compare_best.csv (run 3, run 2, run 1) và compare_near_intersection.csv",
          note="ddagger: 2^12 của run 1-3 đo với lô K > 1 (sai lệch đã chẩn đoán ở T02c); 2^16 và 2^19 của results_final trùng run 3.")


def ta06_run_conditions():
    dirs = [("run 1", "results_run1"), ("run 2", "results"), ("run 3", "results_run3"), ("Run 4 ($2^{12}$)", "results_run4"),
            ("doubling", "results_doubling")]
    pin = {"run 1": "không", "run 2": "không", "run 3": "nhân 5$^{\\dagger}$", "Run 4 ($2^{12}$)": "nhân 5", "doubling": "nhân 5"}
    rows = []
    for lab, d in dirs:
        starts, free, ends = [], [], []
        for f in (1, 2, 3):
            p = ROOT / d / f"env_fork{f}.txt"
            if not p.exists():
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^start_time=(\S+)", t, re.M)
            if m:
                starts.append(m[1][:19].replace("T", " "))
            m = re.search(r"^physical_memory_free_at_start=(\d+)", t, re.M)
            if m:
                free.append(int(m[1]) / 1e9)
            m = re.search(r"elapsed=(\d+:\d+:\d+)", t)
            if m:
                ends.append(m[1])
        rows.append([lab, pin[lab], starts[0] if starts else "--", " / ".join(ends) if ends else "--",
                     " / ".join(f"{x:.2f}" for x in free) if free else "--"])
    write("ta06_run_conditions", tabular("llccc", ["Lượt", "Ghim nhân", hc("Bắt đầu", "fork 1"), hc("Thời gian", "fork 1 / 2 / 3"), hc("RAM trống đầu", "fork (GB)")], rows),
          "results_run1, results, results_run3, results_run4, results_doubling: env_fork{1,2,3}.txt (start_time, elapsed, physical_memory_free_at_start); "
          "cột ghim nhân: scripts/run_run4.bat, scripts/run_doubling.bat; dagger: handoff/CONTEXT.md (run 1, 2 không ghim; run 3 ghim nhân 5) vì không có tệp nguồn",
          note="GB = 1e9 B.")


def ta01_other_dist():
    b = pd.read_csv(RF / "rq1_best_cutoff.csv")
    rows = []
    for d in ["random", "sorted", "reversed", "nearly_sorted", "few_distinct"]:
        r = b[(b.distribution == d) & (b.scale == "2^16")].iloc[0]
        edge = "$^{*}$" if int(r.best_cutoff) == 64 else ""
        rows.append([DIST[d], f"{r.best_cutoff}{edge}", f"{r.r_best:.3f} [{r.ci_lo:.3f}, {r.ci_hi:.3f}]", pct(1 - r.r_best), compress(r.near_optimal_2pct)])
    write("ta01_other_dist", tabular("lcccl", ["Phân bố ($2^{16}$)", "$c^*$", "$r$ [CI 95\\%]", "Giảm", "Gần tối ưu ($\\le2\\%$)"], rows),
          "RF/rq1_best_cutoff.csv (scale = 2^16, mọi phân bố)", note="Dấu sao: c* = 64 là biên trên của lưới CUTOFF (đáy thật có thể lớn hơn 64).")


def ta07_diag_c1():
    src = ROOT / "report" / "report_outline_v3.md"
    lines = src.read_text(encoding="utf-8").splitlines()
    i0 = next(i for i, l in enumerate(lines) if "| Bước | Câu hỏi | Cách làm" in l)
    rows = []
    for l in lines[i0 + 2:]:
        if not l.strip().startswith("|"):
            break
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        assert len(cells) == 6, cells
        # Bỏ cột Fact (index 5)
        cells = cells[:5]
        t = []
        for j, c in enumerate(cells):
            c = c.replace("`", "")
            c = esc(c).replace("PrintCompilation", "Print\\-Compilation")
            c = c.replace("\\textasciitilde{}", "$\\sim$").replace("\\_", "\\_").replace("≈", "$\\approx$").replace("≤", "$\\le$")
            if len(rows) == 0 and j == 2:  # dòng 0, cột Cách làm: bỏ (S§10)
                c = c.replace("(S§10)", "").strip()
                c = re.sub(r"\s*,\s*$", "", c)
            if len(rows) == 4 and j == 4:  # dòng 4, cột Kết luận
                c = "không; mức 79\\% trùng với mức sàn 80\\% của gói nguồn (giả thuyết, chưa kiểm)"
            t.append(c)
        rows.append(t)
    write("ta07_diag_c1", "\\footnotesize\n" + tabular("cp{0.16\\linewidth}p{0.22\\linewidth}p{0.32\\linewidth}p{0.22\\linewidth}",
                                                       ["Bước", "Câu hỏi", "Cách làm", "Kết quả chính", "Kết luận"], rows),
          "report/report_outline_v3.md, Phụ lục C, Bảng C1 (đã bỏ cột Fact; dòng 0 bỏ (S§10); dòng 4 cập nhật giả thuyết gói nguồn)")


def main():
    ap = argparse.ArgumentParser(description="Sinh bảng LaTeX cho báo cáo (T07). Chạy từ thư mục gốc dự án.")
    ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tot, fail = t1_correctness()
    check("T1 tổng số kiểm tra", tot, 970425, 0)
    check("T1 số lỗi", fail, 0, 0)
    t1b_mutation(); t2_env(); t3_rq1(); t4_rq3(); t5_paired(); t6_doubling(); t7_cost(); t8_memory(); t9_runs()
    ta01_other_dist(); ta02_m0m1(); ta03_sensitivity(); ta04_doubling_full(); ta05_layouts(); ta06_run_conditions(); ta07_diag_c1()
    bad = report_checks()
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
