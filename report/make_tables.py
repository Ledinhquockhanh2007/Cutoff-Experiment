#!/usr/bin/env python3
"""
make_tables.py: sinh các bảng LaTeX (report/tables/*.tex) từ kết quả phân tích.
Chạy từ thư mục cutoff-experiment:   python report/make_tables.py
Chỉ sinh SỐ LIỆU (bảng); không sinh câu văn. Chạy lại bao nhiêu lần cũng được (không đụng tới main.tex).
Nguồn:
  results_run3/analysis/tables/*.csv   (run 3 = lượt chính; --compare run 2 = results, run 1 = results_run1)
  results/correctness_test_output.txt  (CorrectnessTest trên máy, JDK 25)
  results_run3/env_fork1.txt           (môi trường)
"""
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / "results_run3" / "analysis" / "tables"
OUT = ROOT / "report" / "tables"
OUT.mkdir(parents=True, exist_ok=True)

DIST = {"random": "ngẫu nhiên", "sorted": "đã sắp", "reversed": "đảo ngược",
        "nearly_sorted": "gần sắp (\\textasciitilde 1\\%)", "few_distinct": "ít giá trị (10)"}
RUN = {"run 3 (ghim nhân 5)": "run 3", "run 2": "run 2", "run 1": "run 1"}


def sc(s):            # "2^12" -> $2^{12}$
    return f"$2^{{{s.split('^')[1]}}}$"


def pct(x, d=1):
    return f"{100 * x:.{d}f}\\%"


def compress(lst):
    """'19 20 ... 32 40 48' -> '19--32, 40, 48' (chỉ gộp các giá trị liên tiếp đã thực sự đo)."""
    v = [int(t) for t in str(lst).split()]
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
    return f"{p:.3g}"


def write(name, body, comment):
    (OUT / f"{name}.tex").write_text(f"% {comment}\n% Sinh tự động bởi report/make_tables.py, KHÔNG sửa tay.\n{body}\n", encoding="utf-8")
    print("wrote", name)


def tabular(colspec, head, rows):
    s = [f"\\begin{{tabular}}{{{colspec}}}", "\\toprule", " & ".join(head) + " \\\\", "\\midrule"]
    for r in rows:
        s.append(r if isinstance(r, str) else " & ".join(r) + " \\\\")
    s += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(s)


# ---------------- Bảng 1: kiểm thử tính đúng
txt = (ROOT / "results" / "correctness_test_output.txt").read_text(encoding="utf-8", errors="replace")
rows = []
for m in re.finditer(r"^(\d\d)\. (.+?)\s+(\d+)\s+(\d+)\s+(PASS|FAIL)\s*$", txt, re.M):
    rows.append([m[1], m[2].replace("_", "\\_").replace("<=", "$\\le$").replace("->", "$\\to$")
                 .replace("==", "$=$").replace(" x ", " $\\times$ ").replace("^", "\\^{}"), f"{int(m[3]):,}".replace(",", "\\,"), m[4]])
tot = re.search(r"TOTAL: (\d+) checks, (\d+) failed", txt)
rows.append("\\midrule")
rows.append(["", "Tổng", f"{int(tot[1]):,}".replace(",", "\\,"), tot[2]])
write("t_correctness", tabular("rp{0.62\\linewidth}rr", ["Nhóm", "Nội dung kiểm tra", "PASS", "FAIL"], rows),
      "Bảng: các nhóm của CorrectnessTest (results/correctness_test_output.txt)")

# ---------------- Bảng 2: mutation test (chạy trên sandbox của AI, JDK 21; nguồn: log AI)
rows = [["merge lấy nửa phải khi hai khóa bằng nhau", "04, 05, 14"],
        ["dòng cutoff lệch 1: \\texttt{hi <= lo + cutoff}", "chỉ 14"],
        ["insertion sort: \\texttt{j > lo + 1}", "02, 03, 04, 05, 13, 14"],
        ["\\texttt{mid = lo + (hi - lo + 1)/2}", "13 (StackOverflow), 14"]]
write("t_mutation", tabular("p{0.55\\linewidth}l", ["Bản cài lỗi cố ý", "Nhóm kiểm thử báo FAIL"], rows),
      "Bảng: mutation test (4 bản lỗi; chạy trên sandbox của AI, JDK 21; nguồn: log AI)")

# ---------------- Bảng 3: RQ1 (random, run 3)
b = pd.read_csv(T / "rq1_best_cutoff.csv")
rows = []
for _, r in b[b.distribution == "random"].iterrows():
    rows.append([sc(r.scale), str(r.best_cutoff), str(r.best_by_median),
                 f"{r.r_best:.3f} [{r.ci_lo:.3f}, {r.ci_hi:.3f}]", pct(1 - r.r_best),
                 compress(r.near_optimal_2pct), r.boot_top3.replace("%", "\\%")])
write("t_rq1", tabular("lccccp{0.2\\linewidth}p{0.17\\linewidth}",
      ["Thang", "$c^*$", "$c^*$ (median)", "$r$ [CI 95\\%]", "Giảm", "Gần tối ưu ($\\le$2\\%)", "Argmin bootstrap"], rows),
      "Bảng: RQ1, dữ liệu ngẫu nhiên, run 3 (T:rq1_best_cutoff)")

# ---------------- Bảng 4: RQ3 (run 3)
s = pd.read_csv(T / "rq3_speedup.csv")
rows = []
for scale, g in s.groupby("scale", sort=False):
    first = True
    for _, r in g.iterrows():
        lab = "tốt nhất ($c={}$)".format(r.cutoff) if r.label.startswith("tốt") else f"$c={r.cutoff}$"
        rows.append([sc(scale) if first else "", lab, f"{r.r_gm:.3f} [{r.ci_lo:.3f}, {r.ci_hi:.3f}]",
                     f"{pct(r.time_reduction)} [{pct(r.red_lo)}, {pct(r.red_hi)}]", f"{r.speedup_x:.3f}$\\times$"])
        first = False
    rows.append("\\addlinespace")
rows = rows[:-1]
write("t_rq3", tabular("llccc", ["Thang", "CUTOFF", "$r$ [CI 95\\%]", "Thời gian giảm [CI 95\\%]", "Tăng tốc"], rows),
      "Bảng: RQ3, c = 7, 10 và tốt nhất so với c = 1, run 3 (T:rq3_speedup)")

# ---------------- Bảng 4b: so sánh ghép cặp 7 vs 10, tốt nhất vs 7/10 (run 3)
p = pd.read_csv(T / "rq3_paired_tests.csv")
rows = []
for _, r in p.iterrows():
    if r.b == 1:
        continue
    rows.append([sc(r.scale), "in-sample" if r.kind == "in-sample" else "holdout", f"{r.a} / {r.b}",
                 f"{r.ratio:.4f} [{r.ci_lo:.4f}, {r.ci_hi:.4f}]", f"{int(r.n_N_a_faster)}/{int(r.n_N)}", pval(r.p_holm)])
write("t_paired", tabular("llcccc", ["Thang", "Loại", "$a$ / $b$", "$T_a/T_b$ [CI 95\\%]", "$a$ nhanh hơn ở", "$p$ (Holm)"], rows),
      "Bảng: so sánh ghép cặp (Wilcoxon trên 24 N, hiệu chỉnh Holm), run 3 (T:rq3_paired_tests)")

# ---------------- Bảng 5: các phân bố (thang 2^16, run 3)
rows = []
for d in ["random", "sorted", "reversed", "nearly_sorted", "few_distinct"]:
    r = b[(b.distribution == d) & ((b.scale == "2^16"))].iloc[0]
    rows.append([DIST[d], str(r.best_cutoff), f"{r.r_best:.3f} [{r.ci_lo:.3f}, {r.ci_hi:.3f}]", pct(1 - r.r_best),
                 compress(r.near_optimal_2pct)])
write("t_dist", tabular("lcccp{0.3\\linewidth}", ["Phân bố", "$c^*$", "$r$ [CI 95\\%]", "Giảm", "Gần tối ưu ($\\le$2\\%)"], rows),
      "Bảng: các phân bố, thang 2^16, run 3 (T:rq1_best_cutoff)")

# ---------------- Bảng mô hình thời gian chạy (run 3)
m = pd.read_csv(T / "runtime_model.csv")
rows = [[str(int(r.cutoff)), str(int(r.n_N)), f"{r.b:.4f} $\\pm$ {r.b_stderr:.4f}", f"{r.a_ns:.2f}", f"{r.R2:.5f}", f"{r.k_ns_per_NlgN:.3f}"]
        for _, r in m.iterrows()]
write("t_model", tabular("cccccc", ["CUTOFF", "Số N", "$b$", "$a$ (ns)", "$R^2$", "$T/(N\\lg N)$ (ns)"], rows),
      "Bảng: mô hình T = a N^b, random, run 3 (T:runtime_model)")

# ---------------- Bảng 6: 3 lượt, random
c = pd.read_csv(T / "compare_best.csv")
inter = pd.read_csv(T / "compare_near_intersection.csv")
rows = []
for scale in ["2^12", "2^16", "2^19"]:
    g = c[(c.distribution == "random") & (c.scale == scale)]
    first = True
    for _, r in g.iterrows():
        rows.append([sc(scale) if first else "", RUN[r.run], str(r.best_cutoff), compress(r.near_optimal_2pct),
                     pct(r.red_7), pct(r.red_10), pct(r.red_best), f"{r.T7_T10:.4f}", pval(r.p_7v10),
                     f"{r.TnlgN_c1_ns:.2f}"])
        first = False
    it = inter[(inter.distribution == "random") & (inter.scale == scale)].iloc[0]
    rows.append(["", "\\multicolumn{9}{l}{\\textit{giao 3 lượt:} " + compress(it.near_intersection_all) + "}"])
    rows.append("\\addlinespace")
rows = rows[:-1]
write("t_runs", tabular("llcp{0.17\\linewidth}cccccc",
      ["Thang", "Lượt", "$c^*$", "Gần tối ưu", "Giảm $c{=}7$", "Giảm $c{=}10$", "Giảm $c^*$", "$T_7/T_{10}$", "$p_{7\\,\\mathrm{vs}\\,10}$", "$T/(N\\lg N)$, $c{=}1$ (ns)"], rows),
      "Bảng: 3 lượt, random (T:compare_best, T:compare_near_intersection)")

# ---------------- Bảng 6b: 3 lượt, các phân bố khác
rows = []
for d in ["sorted", "reversed", "nearly_sorted", "few_distinct"]:
    g = c[c.distribution == d].set_index("run")
    it = inter[inter.distribution == d].iloc[0]
    rows.append([DIST[d]] + [f"{g.loc[k].best_cutoff} ({g.loc[k].r_best:.3f})" for k in RUN] + [compress(it.near_intersection_all)])
write("t_runs_other", tabular("lcccl", ["Phân bố ($2^{16}$)", "run 3: $c^*$ ($r$)", "run 2", "run 1", "Giao vùng gần tối ưu"], rows),
      "Bảng: 3 lượt, các phân bố khác (T:compare_best)")

# ---------------- Bảng 7: từng cặp lượt
pr = pd.read_csv(T / "compare_pairs.csv")
rows = []
for (d, s_), g in pr.groupby(["distribution", "scale"], sort=False):
    cells = [f"{x.pearson_r:.3f} ({x.max_abs_diff_pct:.2f}\\%)" for _, x in g.iterrows()]
    rows.append([DIST[d], sc(s_)] + cells)
write("t_pairs", tabular("llccc", ["Phân bố", "Thang", "run 3 -- run 2", "run 3 -- run 1", "run 2 -- run 1"], rows),
      "Bảng: Pearson của r(c) (chênh r tối đa) giữa từng cặp lượt (T:compare_pairs)")

# ---------------- Bảng: biến thiên giữa 9 JVM
j = pd.read_csv(T / "per_jvm_summary.csv")
rows = []
for scale, g in j.groupby("scale", sort=False):
    first = True
    for _, r in g.iterrows():
        extra = f"{int(r.n_jvm_10_faster)}/{int(r.n_jvm)}" if r.metric == "T7/T10" else ""
        rows.append([sc(scale) if first else "", r.metric.replace("T7/T10", "$T_7/T_{10}$"), f"{r['mean']:.4f}",
                     f"{r['min']:.4f}--{r['max']:.4f}", f"[{r.t_lo:.4f}, {r.t_hi:.4f}]", extra])
        first = False
    rows.append("\\addlinespace")
rows = rows[:-1]
write("t_perjvm", tabular("llcccc", ["Thang", "Đại lượng", "TB nhân", "min--max", "Khoảng $t$ 95\\%", "10 nhanh hơn 7"], rows),
      "Bảng: biến thiên giữa 9 JVM (3 lượt x 3 fork) (T:per_jvm_summary)")

# ---------------- Bảng môi trường
env = (ROOT / "results_run3" / "env_fork1.txt").read_text(encoding="utf-8")
g = lambda k: re.search(rf"^{re.escape(k)}=(.*)$", env, re.M)[1].strip()
rows = [["Máy", "Lenovo Legion 5 15AHP10 (R7000 AHP10, model 83M0)"],
        ["CPU", "AMD Ryzen 7 H 255, 8 nhân / 16 luồng, xung cơ bản 3.8 GHz; L1 512 KB, L2 8 MB (1 MB/nhân), L3 16 MB"],
        ["RAM", "16 GB DDR5-5600, SODIMM, single-channel (1/2 khe)"],
        ["Hệ điều hành", "Windows 11 Home 26H2 (build 26300.9711), x64; gói nguồn Balanced"],
        ["JDK", f"{g('java.vendor')} OpenJDK {g('java.version')} ({g('java.vm.name')})"],
        ["Cờ JVM", "\\texttt{" + g("jvm_input_arguments").strip("[]").replace(", ", " ") + "}"],
        ["Khởi chạy", "\\texttt{start /b /wait /high}; run 3 thêm \\texttt{/affinity C00} (nhân 5)"],
        ["Python", "pandas, numpy, scipy, matplotlib (xem \\texttt{scripts/requirements.txt})"]]
write("t_env", tabular("lp{0.75\\linewidth}", ["Thành phần", "Cấu hình"], rows),
      "Bảng: môi trường thí nghiệm (results_run3/env_fork1.txt + thông tin máy)")

# ---------------- Bảng: chuỗi chẩn đoán (phụ lục C), chỉ số liệu
rows = [["PrintCompilation", "2 JVM, \\texttt{-XX:+PrintCompilation}", "không có sự kiện biên dịch MergeCutoff quanh lúc chuyển mức"],
        ["Pilot A/B", "pilot sau 10 phút nghỉ; pilot chạy liền sau", "cả hai không nhảy ở warm-up"],
        ["E0\\_1, E0\\_2", "WarmupProbe 300 / 900 vòng + typeperf", "296/300 và 900/900 vòng nhanh; xung $\\approx$121\\%"],
        ["E6", "Benchmark như \\texttt{run\\_all.bat} + typeperf", "3.4--130.9 s trên nhân 0 ở 77--79\\%; sau đó nhân 5/7 ở 125--128\\%"],
        ["T2\\_c0", "ghim nhân 0 (\\texttt{/affinity 3})", "nhân 0 ở 124--127\\%, nhanh"],
        ["T2\\_c5", "ghim nhân 5 (\\texttt{/affinity C00})", "nhân 5 ở $\\approx$128\\%, nhanh"],
        ["run 3", "3 fork, ghim nhân 5 + typeperf suốt lượt", "100\\% mẫu trên nhân 5; xung trung vị 129.0--129.5\\%"]]
write("t_diag", tabular("lp{0.33\\linewidth}p{0.42\\linewidth}", ["Bước", "Cách làm", "Kết quả đo"], rows),
      "Bảng: chuỗi chẩn đoán hai mức hiệu năng (số liệu từ diag/ và results_run3/diag)")
