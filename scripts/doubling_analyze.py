#!/usr/bin/env python3
"""
scripts/doubling_analyze.py

Phân tích bài kiểm tra tăng gấp đôi kích thước (doubling test) N = 2^10 .. 2^22 (T04b).
Thực hiện nghiêm ngặt theo Hợp đồng phân tích đã đăng ký (Phần E của T04_predictions.md
và T04_addendum.md).

Quy ước:
  - time_ns ĐÃ LÀ thời gian của MỘT lần sắp xếp (K = 1 cố định), KHÔNG chia batch_k.
  - G(f, N, c) = trung bình hình học của time_ns qua các trial của (fork f, N, c).
  - R_k(f, c) = G(f, 2^(k+1), c) / G(f, 2^k, c); R_bar_k(c) = trung bình hình học qua 3 fork.
  - Dự đoán đọc từ preregistration/ (không sửa file đăng ký).
  - Mục A: KIỂM ĐỊNH ĐÃ ĐĂNG KÝ (A1-A6).
  - Mục B: KHÁM PHÁ (B1-B6).

Đầu ra:
  - Bảng CSV trong results_doubling/analysis/tables/
  - Hình PNG và PDF trong results_doubling/analysis/figures/
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

# Đảm bảo UTF-8 trên Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Thêm thư mục gốc vào sys.path để import scripts.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from scripts.doubling_predict import predict_t_p3c

# Hằng số thiết kế
GRID = [1, 4, 7, 8, 10, 16, 30, 32, 64]
K_MIN = 10
K_MAX = 22
PAIRS_SAME_TREE = [(4, 7), (8, 10), (16, 30)]

# Bảng màu nhất quán với dự án
INK, INK2, GRID_C, NEUTRAL = "#0b0b0b", "#52514e", "#e2e1dc", "#8d8c86"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#8c564b", "#9467bd", "#17becf"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Segoe UI", "Arial"],
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "font.size": 9.5,
    "axes.titlesize": 10.5,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 8.5,
    "legend.frameon": False,
    "axes.edgecolor": NEUTRAL,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "axes.grid": True,
    "grid.color": GRID_C,
    "grid.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def parse_args():
    parser = argparse.ArgumentParser(description="Phân tích Doubling Test T04b theo kế hoạch đã đăng ký")
    parser.add_argument("--data-dir", type=Path, default=Path("results_doubling"),
                        help="Thư mục chứa raw_fork*.csv (mặc định: results_doubling)")
    parser.add_argument("--prereg-dir", type=Path, default=Path("preregistration"),
                        help="Thư mục chứa file đăng ký dự đoán (mặc định: preregistration)")
    parser.add_argument("--results-final", type=Path, default=Path("results_final"),
                        help="Thư mục results_final để đối chiếu tái lập (mặc định: results_final)")
    parser.add_argument("--out-dir", type=Path, default=Path("results_doubling/analysis"),
                        help="Thư mục xuất kết quả phân tích (mặc định: results_doubling/analysis)")
    parser.add_argument("--seed", type=int, default=20261030, help="Seed ngẫu nhiên cho bootstrap (mặc định: 20261030)")
    parser.add_argument("--bootstrap-iters", type=int, default=2000, help="Số lần bootstrap trong ô (mặc định: 2000)")
    parser.add_argument("--print-report", action="store_true", help="In các bảng Markdown cho báo cáo R04b")
    return parser.parse_args()


def print_markdown_report_tables(tables_dir: Path):
    """In các bảng Markdown cho báo cáo R04b trực tiếp từ các file CSV kết quả."""
    print("\n" + "=" * 80)
    print("BẢNG MARKDOWN CHO BÁO CÁO R04b (QUY TẮC 6: TRÍCH TỰ ĐỘNG TỪ CSV)")
    print("=" * 80)

    # ──────────────────────────────────────────────────────────────── A1
    df_agg = pd.read_csv(tables_dir / "A1_pred_error_aggregated.csv")
    print("\n### Bảng A1.1. Tóm tắt sai số dự đoán doubling gộp qua 9 CUTOFF (Nguồn: A1_pred_error_aggregated.csv)\n")
    print("| Predictor | Mô tả mô hình | Đạt (\\le 1.5%) | Tỷ lệ | RMSE (10..21) | RMSE (18..21) | Điểm biên |")
    print("| :--- | :--- | :---: | :---: | :---: | :---: | :---: |")
    pred_desc = {
        "P1_theory_nlgn": "Lý thuyết $N\\lg N$",
        "P2_power_law_48N": "Lũy thừa 48N ($2^{16}+2^{19}$)",
        "P2b_power_law_72N": "Lũy thừa 72N ($2^{12}+2^{16}+2^{19}$)",
        "P3_model_M2_step": "M2 bước nhảy ($\\alpha_{19}$ tại $k=18$)",
        "P3b_model_M2_smooth": "M2 trơn không tăng ($\\alpha_{16}$)",
        "P3c_model_M2_interp": "M2 nội suy bão hòa (T04c)",
    }
    for _, r in df_agg.iterrows():
        p = r["predictor"]
        print(f"| `{p}` | {pred_desc.get(p, '')} | {int(r['k_pass_total'])}/108 | {r['pass_rate']:.1%} | {r['rmse_10_21']:.4f} ({r['rmse_10_21']*100:.2f}%) | {r['rmse_18_21']:.4f} ({r['rmse_18_21']*100:.2f}%) | {int(r['borderline_total'])} |")

    # A1 chi tiết c=1 và c=30
    df_a1_sum = pd.read_csv(tables_dir / "A1_pred_error_summary.csv")
    print("\n### Bảng A1.2. Sai số dự đoán doubling tại c = 1 và c = 30 (Nguồn: A1_pred_error_summary.csv)\n")
    print("| Predictor | CUTOFF | Đạt (/12) | RMSE (10..21) | RMSE (18..21) | Điểm biên |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")
    for c in [1, 30]:
        sub = df_a1_sum[df_a1_sum["cutoff"] == c]
        for _, r in sub.iterrows():
            print(f"| `{r['predictor']}` | {c} | {int(r['k_pass'])}/12 | {r['rmse_10_21']:.4f} | {r['rmse_18_21']:.4f} | {int(r['borderline_count'])} |")

    # ──────────────────────────────────────────────────────────────── A2
    df_a2 = pd.read_csv(tables_dir / "A2_cumulative_extrapolation.csv")
    print("\n### Bảng A2. Ngoại suy tích lũy Q_k = T(2^k)/T(2^19) tại c = 1 và c = 30 (Nguồn: A2_cumulative_extrapolation.csv)\n")
    print("| $c$ | $k$ | $N$ | $\\bar{Q}$ đo | $Q$ fork1 | $Q$ fork2 | $Q$ fork3 | $\\hat{Q}$ P2 | $\\ln(\\hat{Q}/\\bar{Q})$ P2 | $\\hat{Q}$ P3c | $\\ln(\\hat{Q}/\\bar{Q})$ P3c | $\\hat{Q}$ P1 |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for c in [1, 30]:
        for k in [20, 21, 22]:
            sub_c = df_a2[(df_a2["cutoff"] == c) & (df_a2["k"] == k)]
            row_p2 = sub_c[sub_c["predictor"] == "P2_power_law_48N"].iloc[0]
            row_p3c = sub_c[sub_c["predictor"] == "P3c_model_M2_interp"].iloc[0]
            row_p1 = sub_c[sub_c["predictor"] == "P1_theory_nlgn"].iloc[0]
            n_val = int(row_p2["N"])
            q_bar = float(row_p2["Q_bar"])
            q1 = float(row_p2["Q_fork1"])
            q2 = float(row_p2["Q_fork2"])
            q3 = float(row_p2["Q_fork3"])
            q_p2 = float(row_p2["Q_hat"])
            ln_p2 = float(row_p2["ln_Q_hat_over_Q_bar"])
            q_p3c = float(row_p3c["Q_hat"])
            ln_p3c = float(row_p3c["ln_Q_hat_over_Q_bar"])
            q_p1 = float(row_p1["Q_hat"])
            print(f"| {c} | {k} | {n_val:,} | {q_bar:.3f} | {q1:.3f} | {q2:.3f} | {q3:.3f} | {q_p2:.3f} | {ln_p2:+.3f} | {q_p3c:.3f} | {ln_p3c:+.3f} | {q_p1:.3f} |")

    # ──────────────────────────────────────────────────────────────── A3
    df_a3 = pd.read_csv(tables_dir / "A3_step_test.csv")
    print("\n### Bảng A3. Phép thử bước D = ln R_(17->18) - ln R_(16->17) (Nguồn: A3_step_test.csv)\n")
    print("| CUTOFF | $D$ Fork 1 | $D$ Fork 2 | $D$ Fork 3 | $D$ Trung bình | $D$ Dự đoán P3 | $D$ Dự đoán P3c | Bác bỏ P3 ($D < 0.5 D_{\\text{P3}}$)? | Nhất quán P3c? |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for _, r in df_a3.iterrows():
        c = int(r["cutoff"])
        d1, d2, d3, dm = r["D_fork1"], r["D_fork2"], r["D_fork3"], r["D_mean"]
        dp3, dp3c = r["D_hat_P3"], r["D_hat_P3c"]
        rej_p3 = "BÁC BỎ" if r["reject_P3"] else "Không bác"
        cons_p3c = "Nhất quán" if r["consistent_P3c"] else "Không"
        print(f"| {c:2d} | {d1:+.4f} | {d2:+.4f} | {d3:+.4f} | {dm:+.4f} | {dp3:+.4f} | {dp3c:+.4f} | **{rej_p3}** | {cons_p3c} |")

    # ──────────────────────────────────────────────────────────────── A4
    df_a4 = pd.read_csv(tables_dir / "A4_saturation_test.csv")
    print("\n### Bảng A4. Phép thử bão hòa S tại k = 19..21 (P2 vs P3c) (Nguồn: A4_saturation_test.csv)\n")
    print("| CUTOFF | $S$ Fork 1 | $S$ Fork 2 | $S$ Fork 3 | $\\bar{S}$ đo | $\\hat{S}$ P2 | Chênh P2 | $\\hat{S}$ P3c | Chênh P3c | Kết luận |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
    for _, r in df_a4.iterrows():
        c = int(r["cutoff"])
        s1, s2, s3, sm = r["S_fork1"], r["S_fork2"], r["S_fork3"], r["S_mean"]
        sp2, sp3c = r["S_hat_P2"], r["S_hat_P3c"]
        dp2, dp3c = r["diff_P2"], r["diff_P3c"]
        v = r["verdict"]
        print(f"| {c:2d} | {s1:.4f} | {s2:.4f} | {s3:.4f} | {sm:.4f} | {sp2:.4f} | {dp2:.4f} {'(<=0.015)' if dp2<=0.015 else '(>0.015)'} | {sp3c:.4f} | {dp3c:.4f} {'(<=0.015)' if dp3c<=0.015 else '(>0.015)'} | {v} |")

    # ──────────────────────────────────────────────────────────────── A5
    df_a5 = pd.read_csv(tables_dir / "A5_same_tree_summary.csv")
    print("\n### Bảng A5. Đối chứng cùng cây Delta = ln G(c_lớn) - ln G(c_nhỏ) (Nguồn: A5_same_tree_summary.csv)\n")
    print("| Cặp cùng cây | Trung bình $\\Delta$ | SD $\\Delta$ | Fork 1 | Fork 2 | Fork 3 | Ngưỡng cảnh báo | Đánh giá |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
    for _, r in df_a5.iterrows():
        pair = r["pair"]
        m, sd = r["mean_delta"], r["sd_delta"]
        f1, f2, f3 = r["mean_delta_fork1"], r["mean_delta_fork2"], r["mean_delta_fork3"]
        status = "BÌNH THƯỜNG (|mean| <= 0.01)" if not r["warning_order_effect"] else "CẢNH BÁO HIỆU ỨNG THỨ TỰ"
        print(f"| {pair} | {m:+.4f} ({m*100:+.2f}%) | {sd:.4f} | {f1:+.4f} | {f2:+.4f} | {f3:+.4f} | $\\pm 0.0100$ | **{status}** |")

    # ──────────────────────────────────────────────────────────────── A6
    df_a6 = pd.read_csv(tables_dir / "A6_power_law_b.csv")
    print("\n### Bảng A6. Số mũ lũy thừa b theo fork và khoảng tin cậy 95% (Nguồn: A6_power_law_b.csv)\n")
    print("| Khoảng N | CUTOFF | $b$ Fork 1 | $b$ Fork 2 | $b$ Fork 3 | $\\bar{b}$ | SD | CI 95% ($df=2$) | $b_{\\text{P2}}$ tham chiếu | Chênh lệch |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for _, r in df_a6.iterrows():
        rng = r["range"]
        c = int(r["cutoff"])
        if c in [1, 7, 10, 30]:
            b1, b2, b3, bm, bsd = r["b_fork1"], r["b_fork2"], r["b_fork3"], r["b_mean"], r["b_sd"]
            cl, ch = r["ci_low_95"], r["ci_high_95"]
            bp2 = r["b_hat_P2"]
            diff = r["diff_vs_P2"]
            print(f"| {rng} | {c:2d} | {b1:.4f} | {b2:.4f} | {b3:.4f} | {bm:.4f} | {bsd:.4f} | [{cl:.4f}, {ch:.4f}] | {bp2:.4f} | {diff:+.4f} |")

    # ──────────────────────────────────────────────────────────────── B1
    df_b1 = pd.read_csv(tables_dir / "B1_doubling_lecture.csv")
    print("\n### Bảng B1 [Khám phá]. Bảng Doubling Test kiểu bài giảng (c = 1, 30) (Nguồn: B1_doubling_lecture.csv)\n")
    print("| $k$ | $N$ | $T(1)$ (ms) [min, max] | $R(1)$ | $\\lg R(1)$ | $T(30)$ (ms) [min, max] | $R(30)$ | $\\lg R(30)$ |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for k in range(10, 23):
        r1 = df_b1[(df_b1["cutoff"] == 1) & (df_b1["k"] == k)].iloc[0]
        r30 = df_b1[(df_b1["cutoff"] == 30) & (df_b1["k"] == k)].iloc[0]
        n_val = int(r1["N"])
        t1, t1_min, t1_max = r1["T_ms"], r1["T_ms_min"], r1["T_ms_max"]
        r1_val = f"{r1['R']:.3f}" if not pd.isna(r1['R']) else "—"
        lgr1_val = f"{r1['lg_R']:.3f}" if not pd.isna(r1['lg_R']) else "—"

        t30, t30_min, t30_max = r30["T_ms"], r30["T_ms_min"], r30["T_ms_max"]
        r30_val = f"{r30['R']:.3f}" if not pd.isna(r30['R']) else "—"
        lgr30_val = f"{r30['lg_R']:.3f}" if not pd.isna(r30['lg_R']) else "—"
        print(f"| {k:2d} | {n_val:9,d} | {t1:8.3f} [{t1_min:8.3f}, {t1_max:8.3f}] | {r1_val:>5s} | {lgr1_val:>6s} | {t30:8.3f} [{t30_min:8.3f}, {t30_max:8.3f}] | {r30_val:>5s} | {lgr30_val:>6s} |")

    # ──────────────────────────────────────────────────────────────── B4
    df_b4 = pd.read_csv(tables_dir / "B4_replication_final.csv")
    print("\n### Bảng B4 [Khám phá]. Tái lập độc lập với results_final (Nguồn: B4_replication_final.csv)\n")
    print("| Thang | $N$ | $c$ | $G_{\\text{doubling}}$ (ns) | $G_{\\text{final}}$ (ns) | Fork 1 | Fork 2 | Fork 3 | Tỉ số trung bình |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for _, r in df_b4[df_b4["cutoff"].isin([1, 7, 10, 30])].iterrows():
        s = r["scale"]
        n_val = int(r["N"])
        c = int(r["cutoff"])
        gd, gf = r["G_doubling_mean_ns"], r["G_final_mean_ns"]
        rf1, rf2, rf3, rm = r["ratio_fork1"], r["ratio_fork2"], r["ratio_fork3"], r["ratio_mean"]
        print(f"| {s} | {n_val:7,d} | {c:2d} | {gd:12.1f} | {gf:12.1f} | {rf1:.3f} | {rf2:.3f} | {rf3:.3f} | **{rm:.3f}** |")

    # ──────────────────────────────────────────────────────────────── A1z
    p_a1z = tables_dir / "A1z_noise_interpretation_summary.csv"
    if p_a1z.exists():
        df_a1z = pd.read_csv(p_a1z)
        print("\n### Bảng A1z [Diễn giải, không đăng ký]. Nhiễu thực của R_bar và z-score (Nguồn: A1z_noise_interpretation_summary.csv)\n")
        print("| Predictor | CUTOFF | Mean $z$ | Mean $|z|$ | Tỉ lệ $|z| \\le 2$ ($k=10..18$) | Tỉ lệ $|z| \\le 2$ ($k=19..21$) | Tỉ lệ $|z| \\le 2$ (toàn dải) |")
        print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
        for c in [1, 30]:
            sub = df_a1z[df_a1z["cutoff"] == c]
            for _, r in sub.iterrows():
                p = r["predictor"]
                mz, maz = r["mean_z"], r["mean_abs_z"]
                p10_18, p19_21, pall = r["pass_rate_z2_10_18"], r["pass_rate_z2_19_21"], r["pass_rate_z2_all"]
                print(f"| `{p}` | {c} | {mz:+.2f} | {maz:.2f} | {p10_18:.1%} | {p19_21:.1%} | {pall:.1%} |")

    # ──────────────────────────────────────────────────────────────── B7
    p_b7 = tables_dir / "B7_segment_exponents.csv"
    if p_b7.exists():
        df_b7 = pd.read_csv(p_b7)
        print("\n### Bảng B7 [Khám phá]. Số mũ theo đoạn (10..16, 16..19, 19..22) (Nguồn: B7_segment_exponents.csv)\n")
        print("| $c$ | Đoạn $k$ | $b$ Fork 1 | $b$ Fork 2 | $b$ Fork 3 | $\\bar{b}$ | SE | $b_{\\text{theory}}$ ($N\\lg N$) | Độ vượt |")
        print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for _, r in df_b7[df_b7["cutoff"].isin([1, 30])].iterrows():
            c = int(r["cutoff"])
            seg = r["segment"]
            b1, b2, b3, bm, bse = r["b_fork1"], r["b_fork2"], r["b_fork3"], r["b_mean"], r["b_se"]
            bth = r["b_theory_nlgn"]
            exc = r["excess_over_theory"]
            print(f"| {c} | {seg} | {b1:.4f} | {b2:.4f} | {b3:.4f} | **{bm:.4f}** | {bse:.4f} | {bth:.4f} | {exc:+.4f} |")

    # ──────────────────────────────────────────────────────────────── B8
    p_b8 = tables_dir / "B8_d_sensitivity_5trials.csv"
    if p_b8.exists():
        df_b8 = pd.read_csv(p_b8)
        print("\n### Bảng B8 [Khám phá]. Độ nhạy phép thử bước D với 5 trial đầu của N <= 2^16 (Nguồn: B8_d_sensitivity_5trials.csv)\n")
        print("| $c$ | Fork 1 (5t) | Fork 2 (5t) | Fork 3 (5t) | Mean (5t) | $D_{\\text{P3}}$ | Ngưỡng bác | Bác P3? | Fork 1 (gốc) | Fork 2 (gốc) | Fork 3 (gốc) |")
        print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        df_a3 = pd.read_csv(tables_dir / "A3_step_test.csv")
        for c in [1, 30]:
            r_5t = df_b8[df_b8["cutoff"] == c].iloc[0]
            r_orig = df_a3[df_a3["cutoff"] == c].iloc[0]
            d1, d2, d3, dm = r_5t["D_5trial_fork1"], r_5t["D_5trial_fork2"], r_5t["D_5trial_fork3"], r_5t["D_5trial_mean"]
            dp3, thresh, rej = r_5t["D_hat_P3"], r_5t["reject_threshold"], r_5t["reject_P3"]
            o1, o2, o3 = r_orig["D_fork1"], r_orig["D_fork2"], r_orig["D_fork3"]
            print(f"| {c} | {d1:+.4f} | {d2:+.4f} | {d3:+.4f} | {dm:+.4f} | {dp3:+.4f} | {thresh:+.4f} | **{'BÁC' if rej else 'KHÔNG'}** | {o1:+.4f} | {o2:+.4f} | {o3:+.4f} |")

    print("\n" + "=" * 80)
    print("HOÀN TẤT IN BẢNG MARKDOWN!")
    print("=" * 80)


def load_doubling_data(data_dir: Path) -> pd.DataFrame:
    """Đọc dữ liệu 3 fork doubling, kiểm tra tính toàn vẹn."""
    dfs = []
    for f in [1, 2, 3]:
        p = data_dir / f"raw_fork{f}.csv"
        if not p.exists():
            raise FileNotFoundError(f"Không tìm thấy {p}")
        df_f = pd.read_csv(p)
        dfs.append(df_f)
    df = pd.concat(dfs, ignore_index=True)

    # Sanity checks
    assert len(df) == 2700, f"Dữ liệu phải có 2700 hàng, thực tế: {len(df)}"
    assert (df["gc_during_run"] != False).sum() == 0, "Có dòng bị cờ gc_during_run == true!"
    assert (df["batch_k"] != 1).sum() == 0, "batch_k phải bằng 1 ở mọi dòng!"
    assert set(df["fork"].unique()) == {1, 2, 3}, "Phải có đúng 3 fork 1, 2, 3"
    assert set(df["cutoff"].unique()) == set(GRID), "Lưới cutoff không khớp GRID"
    expected_n = {1 << k for k in range(K_MIN, K_MAX + 1)}
    assert set(df["N"].unique()) == expected_n, "Các giá trị N không khớp 2^10 .. 2^22"
    return df


def compute_geometric_means(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tính G(f, N, c) = trung bình hình học của time_ns qua các trial của (fork f, N, c).
    """
    df_g = df.groupby(["fork", "N", "cutoff"])["time_ns"].apply(
        lambda s: float(np.exp(np.mean(np.log(s.to_numpy(dtype=float)))))
    ).reset_index()
    df_g.rename(columns={"time_ns": "G"}, inplace=True)
    df_g["k"] = np.round(np.log2(df_g["N"])).astype(int)
    return df_g


def compute_r_and_rbar(df_g: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Tính R_k(f, c) = G(f, 2^(k+1), c) / G(f, 2^k, c)
    và R_bar_k(c) = trung bình hình học qua mọi fork có mặt trong df_g.
    (Tổng quát hóa từ 3 fork sang F fork bất kỳ và dải k bất kỳ; giữ nguyên hành vi với 3 fork.)
    """
    piv = df_g.pivot(index=["fork", "cutoff"], columns="k", values="G")
    ks = sorted(int(k) for k in piv.columns)
    records = []
    for k in ks:
        if (k + 1) not in piv.columns:
            continue
        r_series = piv[k + 1] / piv[k]
        for (f, c), r_val in r_series.items():
            records.append({
                "fork": f,
                "cutoff": c,
                "k_from": k,
                "k_to": k + 1,
                "R": float(r_val),
                "ln_R": float(np.log(r_val)),
            })
    df_r = pd.DataFrame(records)

    forks = sorted(int(f) for f in df_r["fork"].unique())
    n_forks = len(forks)

    # R_bar, sd_fork, SE_k qua n_forks fork
    summary_records = []
    for (c, k), group in df_r.groupby(["cutoff", "k_from"]):
        r_by_f = {int(f): float(group[group["fork"] == f]["R"].values[0]) for f in forks}
        r_vals = [r_by_f[f] for f in forks]
        ln_r_vals = [float(np.log(v)) for v in r_vals]
        ln_r_bar = float(np.mean(ln_r_vals))
        r_bar = float(np.exp(ln_r_bar))
        sd_fork = float(np.std(ln_r_vals, ddof=1)) if n_forks > 1 else float("nan")
        se_k = sd_fork / math.sqrt(n_forks) if n_forks > 1 else float("nan")
        rec = {
            "cutoff": c,
            "k_from": k,
            "k_to": k + 1,
        }
        for f in forks:
            rec[f"R_fork{f}"] = r_by_f[f]
        rec.update({
            "R_min": min(r_vals),
            "R_max": max(r_vals),
            "R_bar": r_bar,
            "ln_R_bar": ln_r_bar,
            "sd_fork": sd_fork,
            "SE_k": se_k,
        })
        summary_records.append(rec)
    df_rbar = pd.DataFrame(summary_records)
    return df_r, df_rbar


def bootstrap_within_cell(df: pd.DataFrame, n_iters: int = 2000, seed: int = 20261030) -> pd.DataFrame:
    """
    Bootstrap trong-ô để ước lượng SE thực nghiệm và khoảng bách phân vị 2.5–97.5% của ln R_bar_k.
    """
    print(f"Chạy bootstrap trong-ô ({n_iters} lần, seed={seed})...")
    rng = np.random.default_rng(seed)

    # Nhóm dữ liệu log(time_ns) theo (fork, k, cutoff)
    df["log_t"] = np.log(df["time_ns"].to_numpy(dtype=float))
    df["k"] = np.round(np.log2(df["N"])).astype(int)

    cell_data = {}
    for (f, k, c), group in df.groupby(["fork", "k", "cutoff"]):
        cell_data[(f, k, c)] = group["log_t"].to_numpy()

    # Mảng lưu kết quả bootstrap: shape (n_iters, len(GRID), 12)
    # 12 mốc k: k = 10..21
    k_list = list(range(K_MIN, K_MAX))
    k_to_idx = {k: i for i, k in enumerate(k_list)}
    c_to_idx = {c: i for i, c in enumerate(GRID)}

    boot_ln_rbar = np.zeros((n_iters, len(GRID), len(k_list)), dtype=float)

    for b in range(n_iters):
        # Tính ln G* cho mọi (f, k, c)
        log_g_star = {}
        for (f, k, c), vals in cell_data.items():
            m = len(vals)
            idx = rng.integers(0, m, size=m)
            log_g_star[(f, k, c)] = np.mean(vals[idx])

        # Tính ln R_bar* cho từng (c, k)
        for c in GRID:
            ci = c_to_idx[c]
            for k in k_list:
                ki = k_to_idx[k]
                ln_r1 = log_g_star[(1, k + 1, c)] - log_g_star[(1, k, c)]
                ln_r2 = log_g_star[(2, k + 1, c)] - log_g_star[(2, k, c)]
                ln_r3 = log_g_star[(3, k + 1, c)] - log_g_star[(3, k, c)]
                boot_ln_rbar[b, ci, ki] = (ln_r1 + ln_r2 + ln_r3) / 3.0

    records = []
    for c in GRID:
        ci = c_to_idx[c]
        for k in k_list:
            ki = k_to_idx[k]
            samples = boot_ln_rbar[:, ci, ki]
            se = float(np.std(samples, ddof=1))
            ci_low = float(np.percentile(samples, 2.5))
            ci_high = float(np.percentile(samples, 97.5))
            records.append({
                "cutoff": c,
                "k_from": k,
                "k_to": k + 1,
                "ln_R_bar_se": se,
                "ln_R_bar_ci_low": ci_low,
                "ln_R_bar_ci_high": ci_high,
            })
    return pd.DataFrame(records)


def load_preregistered_predictions(prereg_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Đọc các tệp dự đoán đã đăng ký (gốc và addendum)."""
    p_orig = prereg_dir / "T04_predictions.csv"
    p_add = prereg_dir / "T04_predictions_addendum.csv"
    e_orig = prereg_dir / "T04_extrapolation.csv"
    e_add = prereg_dir / "T04_extrapolation_addendum.csv"

    if not p_orig.exists() or not p_add.exists() or not e_orig.exists() or not e_add.exists():
        raise FileNotFoundError(f"Không tìm thấy đủ tệp đăng ký trong {prereg_dir}")

    df_p1 = pd.read_csv(p_orig)
    df_p2 = pd.read_csv(p_add)
    df_preds = pd.concat([df_p1, df_p2], ignore_index=True)

    df_e1 = pd.read_csv(e_orig)
    df_e2 = pd.read_csv(e_add)
    df_extrap = pd.concat([df_e1, df_e2], ignore_index=True)
    return df_preds, df_extrap


def analyze_a1_prediction_errors(df_preds: pd.DataFrame, df_rbar: pd.DataFrame, df_boot: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    A1. Sai số dự đoán doubling:
      e_k(pred, c) = ln R_hat - ln R_bar
      Pass nếu |e_k| <= 0.015 (1.5%).
      Borderline nếu CI bootstrap của ln R_bar chứa ngưỡng ln R_hat +- 0.015.
    """
    merged = pd.merge(df_preds, df_rbar, on=["cutoff", "k_from", "k_to"])
    merged = pd.merge(merged, df_boot, on=["cutoff", "k_from", "k_to"])

    merged["ln_R_hat"] = np.log(merged["R_hat"])
    merged["e_k"] = merged["ln_R_hat"] - merged["ln_R_bar"]
    merged["abs_e_k"] = np.abs(merged["e_k"])
    merged["pass"] = merged["abs_e_k"] <= 0.015

    # Đánh dấu borderline: CI bootstrap [ci_low, ci_high] chứa (ln_R_hat - 0.015) hoặc (ln_R_hat + 0.015)
    t_minus = merged["ln_R_hat"] - 0.015
    t_plus = merged["ln_R_hat"] + 0.015
    merged["borderline"] = (
        ((merged["ln_R_bar_ci_low"] <= t_minus) & (t_minus <= merged["ln_R_bar_ci_high"])) |
        ((merged["ln_R_bar_ci_low"] <= t_plus) & (t_plus <= merged["ln_R_bar_ci_high"]))
    )

    # Tóm tắt theo (predictor, cutoff)
    summary_records = []
    for (pred, c), group in merged.groupby(["predictor", "cutoff"]):
        k_pass = int(group["pass"].sum())
        total_k = len(group)
        rmse_10_21 = float(np.sqrt(np.mean(group["e_k"] ** 2)))
        group_18_21 = group[group["k_from"] >= 18]
        rmse_18_21 = float(np.sqrt(np.mean(group_18_21["e_k"] ** 2)))
        borderline_cnt = int(group["borderline"].sum())
        summary_records.append({
            "predictor": pred,
            "cutoff": c,
            "k_pass": k_pass,
            "total_k": total_k,
            "pass_rate": k_pass / total_k,
            "rmse_10_21": rmse_10_21,
            "rmse_18_21": rmse_18_21,
            "borderline_count": borderline_cnt,
        })
    df_summary = pd.DataFrame(summary_records)

    # Tóm tắt gộp qua CUTOFF cho từng predictor
    agg_records = []
    for pred, group in merged.groupby("predictor"):
        k_pass_tot = int(group["pass"].sum())
        total_eval = len(group)
        rmse_all = float(np.sqrt(np.mean(group["e_k"] ** 2)))
        group_18_21 = group[group["k_from"] >= 18]
        rmse_18_21 = float(np.sqrt(np.mean(group_18_21["e_k"] ** 2)))
        borderline_tot = int(group["borderline"].sum())
        agg_records.append({
            "predictor": pred,
            "k_pass_total": k_pass_tot,
            "total_eval": total_eval,
            "pass_rate": k_pass_tot / total_eval,
            "rmse_10_21": rmse_all,
            "rmse_18_21": rmse_18_21,
            "borderline_total": borderline_tot,
        })
    df_agg = pd.DataFrame(agg_records)

    return merged, df_summary, df_agg


def analyze_a1z_noise_interpretation(df_a1_full: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Sửa 2 (T04d): Bảng diễn giải về nhiễu thực của R_bar (nhãn "Diễn giải, không đăng ký").
      SE_k = SD giữa 3 fork của ln R_k chia sqrt(3)
      z_k = e_k / SE_k
    """
    df = df_a1_full.copy()
    df["ln_R_f1"] = np.log(df["R_fork1"].to_numpy(dtype=float))
    df["ln_R_f2"] = np.log(df["R_fork2"].to_numpy(dtype=float))
    df["ln_R_f3"] = np.log(df["R_fork3"].to_numpy(dtype=float))

    def calc_sd(row):
        return float(np.std([row["ln_R_f1"], row["ln_R_f2"], row["ln_R_f3"]], ddof=1))

    df["sd_fork"] = df.apply(calc_sd, axis=1)
    df["SE_k"] = df["sd_fork"] / math.sqrt(3.0)
    df["z_k"] = df["e_k"] / df["SE_k"]
    df["abs_z_k"] = np.abs(df["z_k"])

    cols_full = [
        "predictor", "cutoff", "k_from", "k_to", "R_hat", "R_bar", "e_k",
        "sd_fork", "SE_k", "z_k", "abs_z_k"
    ]
    df_full_z = df[cols_full]

    # Tóm tắt theo (predictor, cutoff)
    summary_records = []
    for (pred, c), group in df.groupby(["predictor", "cutoff"]):
        mean_z = float(group["z_k"].mean())
        mean_abs_z = float(group["abs_z_k"].mean())
        # k = 10..18 (9 mốc)
        sub_10_18 = group[group["k_from"] <= 18]
        pass_z2_10_18 = float((sub_10_18["abs_z_k"] <= 2.0).mean())
        # k = 19..21 (3 mốc)
        sub_19_21 = group[group["k_from"] >= 19]
        pass_z2_19_21 = float((sub_19_21["abs_z_k"] <= 2.0).mean())
        # all 10..21 (12 mốc)
        pass_z2_all = float((group["abs_z_k"] <= 2.0).mean())

        summary_records.append({
            "predictor": pred,
            "cutoff": c,
            "mean_z": mean_z,
            "mean_abs_z": mean_abs_z,
            "pass_rate_z2_10_18": pass_z2_10_18,
            "pass_rate_z2_19_21": pass_z2_19_21,
            "pass_rate_z2_all": pass_z2_all,
            "k_pass_z2_count": int((group["abs_z_k"] <= 2.0).sum()),
            "total_k": len(group),
        })
    df_sum_z = pd.DataFrame(summary_records)
    return df_full_z, df_sum_z


def analyze_a2_cumulative_extrapolation(df_extrap: pd.DataFrame, df_g: pd.DataFrame) -> pd.DataFrame:
    """
    A2. Ngoại suy tích lũy:
      Q_k(f, c) = G(f, 2^k, c) / G(f, 2^19, c) cho k = 20, 21, 22
      So với Q_hat từ file extrapolation.
      In cả 3 giá trị theo fork và ln(Q_hat / Q_bar).
    """
    piv = df_g.pivot(index=["fork", "cutoff"], columns="k", values="G")
    q_records = []
    for k in [20, 21, 22]:
        for c in GRID:
            q1 = float(piv.loc[(1, c), k] / piv.loc[(1, c), 19])
            q2 = float(piv.loc[(2, c), k] / piv.loc[(2, c), 19])
            q3 = float(piv.loc[(3, c), k] / piv.loc[(3, c), 19])
            q_bar = float((q1 * q2 * q3) ** (1.0 / 3.0))
            q_records.append({
                "cutoff": c,
                "k": k,
                "N": 1 << k,
                "Q_fork1": q1,
                "Q_fork2": q2,
                "Q_fork3": q3,
                "Q_bar": q_bar,
                "ln_Q_bar": float(np.log(q_bar)),
            })
    df_q_measured = pd.DataFrame(q_records)

    merged = pd.merge(df_extrap, df_q_measured, on=["cutoff", "k", "N"])
    merged["ln_Q_hat"] = np.log(merged["Q_hat"])
    merged["ln_Q_hat_over_Q_bar"] = merged["ln_Q_hat"] - merged["ln_Q_bar"]
    merged["abs_ln_ratio"] = np.abs(merged["ln_Q_hat_over_Q_bar"])
    return merged


def analyze_a3_step_test(df_r: pd.DataFrame, df_preds: pd.DataFrame) -> pd.DataFrame:
    """
    A3. Phép thử bước:
      D(f, c) = ln R_17(f, c) - ln R_16(f, c)
      So với D_P3, D_P3c, D_P2.
      Quy ước:
        (i) Nhất quán nếu |D(f, c) - D_hat| <= 0.02 ở CẢ 3 fork.
        (ii) P3 bị bác nếu D(f, c) < 0.5 * D_P3(c) ở CẢ 3 fork.
    """
    # Lấy D dự đoán từ df_preds
    d_preds = {}
    for pred in ["P2_power_law_48N", "P3_model_M2_step", "P3c_model_M2_interp"]:
        d_preds[pred] = {}
        for c in GRID:
            r16 = df_preds[(df_preds["predictor"] == pred) & (df_preds["cutoff"] == c) & (df_preds["k_from"] == 16)]["R_hat"].values[0]
            r17 = df_preds[(df_preds["predictor"] == pred) & (df_preds["cutoff"] == c) & (df_preds["k_from"] == 17)]["R_hat"].values[0]
            d_preds[pred][c] = float(np.log(r17) - np.log(r16))

    records = []
    for c in GRID:
        d_forks = {}
        for f in [1, 2, 3]:
            r16_f = df_r[(df_r["fork"] == f) & (df_r["cutoff"] == c) & (df_r["k_from"] == 16)]["R"].values[0]
            r17_f = df_r[(df_r["fork"] == f) & (df_r["cutoff"] == c) & (df_r["k_from"] == 17)]["R"].values[0]
            d_forks[f] = float(np.log(r17_f) - np.log(r16_f))

        d1, d2, d3 = d_forks[1], d_forks[2], d_forks[3]
        d_mean = (d1 + d2 + d3) / 3.0

        d_p3 = d_preds["P3_model_M2_step"][c]
        d_p3c = d_preds["P3c_model_M2_interp"][c]
        d_p2 = d_preds["P2_power_law_48N"][c]

        # Kiểm tra tiêu chuẩn
        consistent_p3 = all(abs(d_forks[f] - d_p3) <= 0.02 for f in [1, 2, 3])
        consistent_p3c = all(abs(d_forks[f] - d_p3c) <= 0.02 for f in [1, 2, 3])
        consistent_p2 = all(abs(d_forks[f] - d_p2) <= 0.02 for f in [1, 2, 3])
        reject_p3 = all(d_forks[f] < 0.5 * d_p3 for f in [1, 2, 3])

        records.append({
            "cutoff": c,
            "D_fork1": d1,
            "D_fork2": d2,
            "D_fork3": d3,
            "D_mean": d_mean,
            "D_min": min(d1, d2, d3),
            "D_max": max(d1, d2, d3),
            "D_hat_P3": d_p3,
            "D_hat_P3c": d_p3c,
            "D_hat_P2": d_p2,
            "consistent_P3": consistent_p3,
            "consistent_P3c": consistent_p3c,
            "consistent_P2": consistent_p2,
            "reject_P3": reject_p3,
        })
    return pd.DataFrame(records)


def analyze_a4_saturation_test(df_r: pd.DataFrame, df_rbar: pd.DataFrame, df_preds: pd.DataFrame) -> pd.DataFrame:
    """
    A4. Phép thử bão hòa (P2 so với P3c):
      S(c) = (1/3) * sum_{k=19..21} ln R_bar_k
      So S với trung bình tương ứng của ln R_hat cho P2 và P3c.
      "Ủng hộ P3c" nếu |S - S_P3c| <= 0.015 và |S - S_P2| > 0.015.
      "Ủng hộ P2" nếu ngược lại.
      Ngoài ra "không phân biệt được".
    """
    records = []
    for c in GRID:
        # S đo qua fork
        s_forks = {}
        for f in [1, 2, 3]:
            sub_f = df_r[(df_r["fork"] == f) & (df_r["cutoff"] == c) & (df_r["k_from"].isin([19, 20, 21]))]
            s_forks[f] = float(np.mean(sub_f["ln_R"].to_numpy()))

        sub_bar = df_rbar[(df_rbar["cutoff"] == c) & (df_rbar["k_from"].isin([19, 20, 21]))]
        s_mean = float(np.mean(sub_bar["ln_R_bar"].to_numpy()))

        # S dự đoán P2 và P3c
        sub_p2 = df_preds[(df_preds["predictor"] == "P2_power_law_48N") & (df_preds["cutoff"] == c) & (df_preds["k_from"].isin([19, 20, 21]))]
        s_p2 = float(np.mean(np.log(sub_p2["R_hat"].to_numpy())))

        sub_p3c = df_preds[(df_preds["predictor"] == "P3c_model_M2_interp") & (df_preds["cutoff"] == c) & (df_preds["k_from"].isin([19, 20, 21]))]
        s_p3c = float(np.mean(np.log(sub_p3c["R_hat"].to_numpy())))

        diff_p2 = abs(s_mean - s_p2)
        diff_p3c = abs(s_mean - s_p3c)

        pass_p2 = diff_p2 <= 0.015
        pass_p3c = diff_p3c <= 0.015

        if pass_p3c and not pass_p2:
            verdict = "Ủng hộ P3c"
        elif pass_p2 and not pass_p3c:
            verdict = "Ủng hộ P2"
        elif pass_p2 and pass_p3c:
            verdict = "Không phân biệt được (cả hai đạt)"
        else:
            verdict = "Không phân biệt được (cả hai không đạt)"

        records.append({
            "cutoff": c,
            "S_fork1": s_forks[1],
            "S_fork2": s_forks[2],
            "S_fork3": s_forks[3],
            "S_mean": s_mean,
            "S_hat_P2": s_p2,
            "S_hat_P3c": s_p3c,
            "diff_P2": diff_p2,
            "diff_P3c": diff_p3c,
            "pass_P2": pass_p2,
            "pass_P3c": pass_p3c,
            "verdict": verdict,
        })
    return pd.DataFrame(records)


def analyze_a5_same_tree_control(df_g: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    A5. Đối chứng cùng cây:
      Các cặp (4, 7), (8, 10), (16, 30):
      Delta = ln G(c_lớn) - ln G(c_nhỏ).
      Báo cáo trung bình và SD của Delta qua 39 quan sát (13 N x 3 fork),
      trung bình theo fork, và trung bình theo N.
      Quy ước: nếu |trung bình Delta| > 0.01 thì cảnh báo hiệu ứng thứ tự.
    """
    piv = df_g.pivot(index=["fork", "k", "N"], columns="cutoff", values="G")

    delta_rows = []
    for (f, k, n), row in piv.iterrows():
        for c_small, c_large in PAIRS_SAME_TREE:
            delta = float(np.log(row[c_large]) - np.log(row[c_small]))
            delta_rows.append({
                "pair": f"({c_small}, {c_large})",
                "c_small": c_small,
                "c_large": c_large,
                "fork": f,
                "k": k,
                "N": n,
                "delta": delta,
            })
    df_delta = pd.DataFrame(delta_rows)

    forks = sorted(int(f) for f in df_delta["fork"].unique())

    # Tóm tắt theo cặp
    summary_records = []
    for pair, group in df_delta.groupby("pair"):
        mean_all = float(group["delta"].mean())
        sd_all = float(group["delta"].std(ddof=1))
        warning = abs(mean_all) > 0.01
        rec = {
            "pair": pair,
            "mean_delta": mean_all,
            "sd_delta": sd_all,
        }
        for f in forks:
            rec[f"mean_delta_fork{f}"] = float(group[group["fork"] == f]["delta"].mean())
        rec["warning_order_effect"] = warning
        summary_records.append(rec)
    df_pair_summary = pd.DataFrame(summary_records)

    # Tóm tắt theo (N, pair)
    n_records = []
    for (pair, k, n), group in df_delta.groupby(["pair", "k", "N"]):
        d_by_f = {int(f): float(group[group["fork"] == f]["delta"].values[0]) for f in forks}
        d_mean = float(np.mean([d_by_f[f] for f in forks]))
        rec = {
            "pair": pair,
            "k": k,
            "N": n,
        }
        for f in forks:
            rec[f"delta_fork{f}"] = d_by_f[f]
        rec["delta_mean"] = d_mean
        n_records.append(rec)
    df_by_n = pd.DataFrame(n_records)
    return df_pair_summary, df_by_n


def analyze_a6_power_law_b(df_g: pd.DataFrame, df_preds: pd.DataFrame) -> pd.DataFrame:
    """
    A6. Số mũ cuối:
      Hồi quy OLS ln G theo ln N cho k = 16..22 và k = 10..22.
      Báo cáo b theo fork, trung bình, SD, khoảng t (df=2).
      So với b_P2.
    """
    t_crit = stats.t.ppf(0.975, df=2)  # 4.30265

    # Lấy b_P2 từ df_preds
    p2_b_map = {}
    for c in GRID:
        p2_b_map[c] = float(df_preds[(df_preds["predictor"] == "P2_power_law_48N") & (df_preds["cutoff"] == c) & (df_preds["k_from"] == 10)]["b_hat"].values[0])

    records = []
    for k_range_label, k_range in [("k=16..22 (7N)", range(16, 23)), ("k=10..22 (13N)", range(10, 23))]:
        sub_g = df_g[df_g["k"].isin(k_range)]
        for c in GRID:
            b_forks = {}
            for f in [1, 2, 3]:
                sub_fc = sub_g[(sub_g["fork"] == f) & (sub_g["cutoff"] == c)]
                ln_n = np.log(sub_fc["N"].to_numpy(dtype=float))
                ln_g = np.log(sub_fc["G"].to_numpy(dtype=float))
                slope, intercept, r_val, p_val, std_err = stats.linregress(ln_n, ln_g)
                b_forks[f] = float(slope)

            b1, b2, b3 = b_forks[1], b_forks[2], b_forks[3]
            b_mean = (b1 + b2 + b3) / 3.0
            b_sd = float(np.std([b1, b2, b3], ddof=1))
            ci_half = t_crit * b_sd / math.sqrt(3.0)
            ci_low = b_mean - ci_half
            ci_high = b_mean + ci_half

            records.append({
                "range": k_range_label,
                "cutoff": c,
                "b_fork1": b1,
                "b_fork2": b2,
                "b_fork3": b3,
                "b_mean": b_mean,
                "b_sd": b_sd,
                "ci_low_95": ci_low,
                "ci_high_95": ci_high,
                "b_hat_P2": p2_b_map[c],
                "diff_vs_P2": b_mean - p2_b_map[c],
            })
    return pd.DataFrame(records)


def analyze_b1_doubling_lecture(df_g: pd.DataFrame, df_rbar: pd.DataFrame) -> pd.DataFrame:
    """
    B1. Bảng kiểu bài giảng cho c = 1, 7, 10, 30:
      N, T (ms, trung bình hình học kèm min-max), R = T(2N)/T(N), lg R.
    """
    piv = df_g.pivot(index=["cutoff", "k", "N"], columns="fork", values="G").reset_index()
    piv["T_ms_f1"] = piv[1] / 1e6
    piv["T_ms_f2"] = piv[2] / 1e6
    piv["T_ms_f3"] = piv[3] / 1e6
    piv["T_ms_bar"] = (piv["T_ms_f1"] * piv["T_ms_f2"] * piv["T_ms_f3"]) ** (1.0 / 3.0)
    piv["T_ms_min"] = piv[["T_ms_f1", "T_ms_f2", "T_ms_f3"]].min(axis=1)
    piv["T_ms_max"] = piv[["T_ms_f1", "T_ms_f2", "T_ms_f3"]].max(axis=1)

    # Ghép với R_bar
    rbar_map = {}
    for _, row in df_rbar.iterrows():
        rbar_map[(int(row["cutoff"]), int(row["k_from"]))] = (float(row["R_bar"]), float(np.log2(row["R_bar"])))

    records = []
    for c in [1, 7, 10, 30]:
        sub = piv[piv["cutoff"] == c].sort_values("k")
        for _, row in sub.iterrows():
            k = int(row["k"])
            n = int(row["N"])
            r_val, lg_r = rbar_map.get((c, k), (np.nan, np.nan))
            records.append({
                "cutoff": c,
                "k": k,
                "N": n,
                "T_ms": float(row["T_ms_bar"]),
                "T_ms_min": float(row["T_ms_min"]),
                "T_ms_max": float(row["T_ms_max"]),
                "R": r_val,
                "lg_R": lg_r,
            })
    return pd.DataFrame(records)


def analyze_b2_t_over_nlgn(df_g: pd.DataFrame) -> pd.DataFrame:
    """
    B2. T / (N lg N) theo k cho c = 1 và c = 30 (ns).
    """
    records = []
    for c in [1, 30]:
        sub = df_g[df_g["cutoff"] == c].sort_values("k")
        piv = sub.pivot(index=["k", "N"], columns="fork", values="G").reset_index()
        for _, row in piv.iterrows():
            k = int(row["k"])
            n = int(row["N"])
            denom = n * k  # N * log2(N)
            g1, g2, g3 = float(row[1]), float(row[2]), float(row[3])
            v1 = g1 / denom
            v2 = g2 / denom
            v3 = g3 / denom
            v_mean = (v1 * v2 * v3) ** (1.0 / 3.0)
            records.append({
                "cutoff": c,
                "k": k,
                "N": n,
                "v_fork1_ns": v1,
                "v_fork2_ns": v2,
                "v_fork3_ns": v3,
                "v_mean_ns": v_mean,
            })
    return pd.DataFrame(records)


def analyze_b3_cutoff_ratio_r(df_g: pd.DataFrame, results_final_dir: Path) -> pd.DataFrame:
    """
    B3. Hiệu quả của CUTOFF theo N:
      r(N, c) = trung bình hình học qua fork của G(f, N, c) / G(f, N, 1).
      Ghép với r từ results_final tại k = 12, 16, 19.
    """
    piv = df_g.pivot(index=["fork", "k", "N"], columns="cutoff", values="G")

    r_records = []
    for (f, k, n), row in piv.iterrows():
        g1 = row[1]
        for c in GRID:
            if c == 1:
                continue
            r_val = float(row[c] / g1)
            r_records.append({
                "fork": f,
                "k": k,
                "N": n,
                "cutoff": c,
                "r": r_val,
            })
    df_r_cell = pd.DataFrame(r_records)

    summary_records = []
    for (k, n, c), group in df_r_cell.groupby(["k", "N", "cutoff"]):
        r1 = group[group["fork"] == 1]["r"].values[0]
        r2 = group[group["fork"] == 2]["r"].values[0]
        r3 = group[group["fork"] == 3]["r"].values[0]
        r_mean = float((r1 * r2 * r3) ** (1.0 / 3.0))
        summary_records.append({
            "k": k,
            "N": n,
            "cutoff": c,
            "r_fork1": r1,
            "r_fork2": r2,
            "r_fork3": r3,
            "r_mean": r_mean,
            "r_min": min(r1, r2, r3),
            "r_max": max(r1, r2, r3),
        })
    df_r_summary = pd.DataFrame(summary_records)

    # Đọc results_final để đối chiếu tại N = 4096, 65536, 524288
    final_r_map = {}
    try:
        raw_final = []
        for f in [1, 2, 3]:
            pf = results_final_dir / f"raw_fork{f}.csv"
            if pf.exists():
                rf = pd.read_csv(pf)
                rf = rf[(rf["distribution"] == "random") & (rf["N"].isin([4096, 65536, 524288]))]
                raw_final.append(rf)
        if raw_final:
            df_rf = pd.concat(raw_final, ignore_index=True)
            rf_g = df_rf.groupby(["fork", "N", "cutoff"])["time_ns"].apply(
                lambda s: float(np.exp(np.mean(np.log(s.to_numpy(dtype=float)))))
            ).reset_index()
            rf_piv = rf_g.pivot(index=["fork", "N"], columns="cutoff", values="time_ns")
            for (f, n), row in rf_piv.iterrows():
                g1 = row[1]
                for c in GRID:
                    if c != 1 and c in row:
                        final_r_map[(f, n, c)] = row[c] / g1

            # Tính r_bar của results_final
            final_rbar = {}
            for n in [4096, 65536, 524288]:
                for c in GRID:
                    if c != 1:
                        vals = [final_r_map[(f, n, c)] for f in [1, 2, 3] if (f, n, c) in final_r_map]
                        if len(vals) == 3:
                            final_rbar[(n, c)] = float((vals[0] * vals[1] * vals[2]) ** (1.0 / 3.0))

            df_r_summary["r_results_final"] = df_r_summary.apply(
                lambda r: final_rbar.get((int(r["N"]), int(r["cutoff"])), np.nan), axis=1
            )
    except Exception as e:
        print(f"Lưu ý khi đọc results_final: {e}")
        df_r_summary["r_results_final"] = np.nan

    return df_r_summary


def analyze_b4_replication_final(df_g: pd.DataFrame, results_final_dir: Path) -> pd.DataFrame:
    """
    B4. Tái lập với run 3/4:
      So G(f, N, c) của doubling test với results_final cho N = 4096, 65536, 524288.
    """
    raw_final = []
    for f in [1, 2, 3]:
        pf = results_final_dir / f"raw_fork{f}.csv"
        if not pf.exists():
            return pd.DataFrame()
        rf = pd.read_csv(pf)
        rf = rf[(rf["distribution"] == "random") & (rf["N"].isin([4096, 65536, 524288]))]
        raw_final.append(rf)
    df_rf = pd.concat(raw_final, ignore_index=True)
    rf_g = df_rf.groupby(["fork", "N", "cutoff"])["time_ns"].apply(
        lambda s: float(np.exp(np.mean(np.log(s.to_numpy(dtype=float)))))
    ).reset_index()
    rf_g.rename(columns={"time_ns": "G_final"}, inplace=True)

    doubling_sub = df_g[df_g["N"].isin([4096, 65536, 524288])].copy()
    doubling_sub.rename(columns={"G": "G_doubling"}, inplace=True)

    merged = pd.merge(doubling_sub, rf_g, on=["fork", "N", "cutoff"])
    merged["ratio_doubling_over_final"] = merged["G_doubling"] / merged["G_final"]

    summary_records = []
    scale_names = {4096: "2^12", 65536: "2^16", 524288: "2^19"}
    for (n, c), group in merged.groupby(["N", "cutoff"]):
        r1 = group[group["fork"] == 1]["ratio_doubling_over_final"].values[0]
        r2 = group[group["fork"] == 2]["ratio_doubling_over_final"].values[0]
        r3 = group[group["fork"] == 3]["ratio_doubling_over_final"].values[0]
        r_mean = float((r1 * r2 * r3) ** (1.0 / 3.0))
        g_d_mean = float(np.exp(np.mean(np.log(group["G_doubling"].to_numpy()))))
        g_f_mean = float(np.exp(np.mean(np.log(group["G_final"].to_numpy()))))
        summary_records.append({
            "scale": scale_names[n],
            "N": n,
            "cutoff": c,
            "G_doubling_mean_ns": g_d_mean,
            "G_final_mean_ns": g_f_mean,
            "ratio_fork1": r1,
            "ratio_fork2": r2,
            "ratio_fork3": r3,
            "ratio_mean": r_mean,
        })
    return pd.DataFrame(summary_records)


def analyze_b5_trial_order_residuals(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    B5. Xu hướng theo thứ tự trial:
      Phần dư = ln(time_ns) - mean(ln(time_ns)) trong mỗi ô (fork, N, cutoff).
      Xem theo trial index.
    """
    df["log_t"] = np.log(df["time_ns"].to_numpy(dtype=float))
    cell_means = df.groupby(["fork", "N", "cutoff"])["log_t"].transform("mean")
    df["residual"] = df["log_t"] - cell_means

    # Trung bình qua mọi ô theo trial index (1..10)
    trial_records = []
    for t_idx, group in df.groupby("trial"):
        mean_res = float(group["residual"].mean())
        sd_res = float(group["residual"].std(ddof=1))
        n_obs = len(group)
        trial_records.append({
            "trial": t_idx,
            "mean_residual": mean_res,
            "sd_residual": sd_res,
            "count": n_obs,
        })
    df_by_trial = pd.DataFrame(trial_records)

    # Trung bình theo N và trial
    n_trial_records = []
    for (n, t_idx), group in df.groupby(["N", "trial"]):
        k = int(round(math.log2(n)))
        mean_res = float(group["residual"].mean())
        n_trial_records.append({
            "k": k,
            "N": n,
            "trial": t_idx,
            "mean_residual": mean_res,
        })
    df_by_n_trial = pd.DataFrame(n_trial_records)

    return df_by_trial, df_by_n_trial


def analyze_b6_r_p3c_vs_measured(df_r_summary: pd.DataFrame) -> pd.DataFrame:
    """
    B6. M2/P3c so với đo, tỉ số r:
      r_hat(N, c) = That_P3c(N, c) / That_P3c(N, 1) (từ doubling_predict.py).
      So với r_mean từ B3.
    """
    records = []
    for _, row in df_r_summary.iterrows():
        k = int(row["k"])
        n = int(row["N"])
        c = int(row["cutoff"])
        r_meas = float(row["r_mean"])

        t_hat_c = predict_t_p3c(k, c)
        t_hat_1 = predict_t_p3c(k, 1)
        r_hat = float(t_hat_c / t_hat_1)

        diff = r_hat - r_meas
        records.append({
            "k": k,
            "N": n,
            "cutoff": c,
            "r_measured": r_meas,
            "r_hat_P3c": r_hat,
            "diff_r": diff,
            "abs_diff_r": abs(diff),
        })
    return pd.DataFrame(records)


def analyze_b7_segment_exponents(df_g: pd.DataFrame) -> pd.DataFrame:
    """
    Sửa 3 (T04d): Bảng phụ số mũ theo đoạn (nhãn Khám phá).
      b = (ln G(2^b) - ln G(2^a)) / ((b - a) ln 2) theo từng fork,
      trung bình và SE của 3 fork, cho các đoạn 10..16, 16..19, 19..22.
    """
    piv = df_g.pivot(index=["fork", "cutoff"], columns="k", values="G")
    segments = [
        ("10..16", 10, 16),
        ("16..19", 16, 19),
        ("19..22", 19, 22),
    ]
    records = []
    for c in GRID:
        for seg_label, a, b in segments:
            b_forks = []
            for f in [1, 2, 3]:
                ga = float(piv.loc[(f, c), a])
                gb = float(piv.loc[(f, c), b])
                b_val = (math.log(gb) - math.log(ga)) / ((b - a) * math.log(2.0))
                b_forks.append(b_val)
            bm = float(np.mean(b_forks))
            bsd = float(np.std(b_forks, ddof=1))
            bse = bsd / math.sqrt(3.0)
            b_theory = 1.0 + (math.log2(b) - math.log2(a)) / (b - a)
            records.append({
                "cutoff": c,
                "segment": seg_label,
                "k_from": a,
                "k_to": b,
                "b_fork1": b_forks[0],
                "b_fork2": b_forks[1],
                "b_fork3": b_forks[2],
                "b_mean": bm,
                "b_sd": bsd,
                "b_se": bse,
                "b_theory_nlgn": b_theory,
                "excess_over_theory": bm - b_theory,
            })
    return pd.DataFrame(records)


def analyze_b8_d_sensitivity(df: pd.DataFrame, df_preds: pd.DataFrame) -> pd.DataFrame:
    """
    Sửa 4 (T04d): Phép thử độ nhạy của D khi chỉ dùng 5 trial đầu của các ô N <= 2^16 (nhãn Khám phá).
    """
    df_5 = df[df["trial"] <= 5].copy()
    df_g5 = df_5.groupby(["fork", "N", "cutoff"])["time_ns"].apply(
        lambda s: float(np.exp(np.mean(np.log(s.to_numpy(dtype=float)))))
    ).reset_index()
    df_g5["k"] = np.round(np.log2(df_g5["N"])).astype(int)
    piv5 = df_g5.pivot(index=["fork", "cutoff"], columns="k", values="time_ns")

    d_preds_p3 = {}
    for c in GRID:
        r16 = df_preds[(df_preds["predictor"] == "P3_model_M2_step") & (df_preds["cutoff"] == c) & (df_preds["k_from"] == 16)]["R_hat"].values[0]
        r17 = df_preds[(df_preds["predictor"] == "P3_model_M2_step") & (df_preds["cutoff"] == c) & (df_preds["k_from"] == 17)]["R_hat"].values[0]
        d_preds_p3[c] = float(np.log(r17) - np.log(r16))

    records = []
    for c in GRID:
        d_forks = []
        for f in [1, 2, 3]:
            r16 = piv5.loc[(f, c), 17] / piv5.loc[(f, c), 16]
            r17 = piv5.loc[(f, c), 18] / piv5.loc[(f, c), 17]
            d = math.log(r17) - math.log(r16)
            d_forks.append(d)
        dm = float(np.mean(d_forks))
        dp3 = d_preds_p3[c]
        thresh = 0.5 * dp3
        rej_p3 = all(d < thresh for d in d_forks)
        records.append({
            "cutoff": c,
            "D_5trial_fork1": d_forks[0],
            "D_5trial_fork2": d_forks[1],
            "D_5trial_fork3": d_forks[2],
            "D_5trial_mean": dm,
            "D_hat_P3": dp3,
            "reject_threshold": thresh,
            "reject_P3": rej_p3,
        })
    return pd.DataFrame(records)


def plot_figures(df_preds: pd.DataFrame, df_r: pd.DataFrame, df_rbar: pd.DataFrame,
                 df_boot: pd.DataFrame, df_g: pd.DataFrame, df_step: pd.DataFrame,
                 df_r_summary: pd.DataFrame, out_fig_dir: Path):
    """Vẽ 4 hình H1-H4 chuẩn phong cách dự án (PNG và vector PDF)."""
    out_fig_dir.mkdir(parents=True, exist_ok=True)

    # ────────────────────────────────────────────────────────────────
    # H1: ln R_bar_k theo k, c = 1 và c = 30 (2 ô)
    # ────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)

    pred_styles = {
        "P1_theory_nlgn": ("#8d8c86", ":", "P1 (N lg N)"),
        "P2_power_law_48N": ("#eb6834", "--", "P2 (48N power-law)"),
        "P2b_power_law_72N": ("#eda100", "-.", "P2b (72N power-law)"),
        "P3_model_M2_step": ("#e87ba4", "-.", "P3 (M2 step)"),
        "P3b_model_M2_smooth": ("#9467bd", ":", "P3b (M2 smooth a16)"),
        "P3c_model_M2_interp": ("#1baf7a", "-", "P3c (M2 interp/sat)"),
    }

    for ax, c in zip(axes, [1, 30]):
        # Điểm đo 3 fork (nhạt)
        sub_rf = df_r[df_r["cutoff"] == c]
        for f, col in [(1, "#a6c8e0"), (2, "#b2dfdb"), (3, "#d7ccc8")]:
            sub_f = sub_rf[sub_rf["fork"] == f].sort_values("k_from")
            ax.plot(sub_f["k_from"], sub_f["ln_R"], "o", color=col, alpha=0.6, markersize=3.5, label=f"Fork {f}" if c == 1 else None)

        # Trung bình ln R_bar + bootstrap CI
        sub_bar = df_rbar[df_rbar["cutoff"] == c].sort_values("k_from")
        sub_b = df_boot[df_boot["cutoff"] == c].sort_values("k_from")
        m = pd.merge(sub_bar, sub_b, on=["cutoff", "k_from", "k_to"])

        y_err_low = m["ln_R_bar"] - m["ln_R_bar_ci_low"]
        y_err_high = m["ln_R_bar_ci_high"] - m["ln_R_bar"]
        ax.errorbar(m["k_from"], m["ln_R_bar"], yerr=[y_err_low, y_err_high],
                    fmt="o-", color=INK, linewidth=1.8, markersize=5, capsize=3, label="Đo thực tế (R_bar +- 95% CI)" if c == 1 else None, zorder=5)

        # Các đường dự đoán
        for pred, (color, ls, lbl) in pred_styles.items():
            sub_p = df_preds[(df_preds["predictor"] == pred) & (df_preds["cutoff"] == c)].sort_values("k_from")
            ax.plot(sub_p["k_from"], np.log(sub_p["R_hat"]), linestyle=ls, color=color, linewidth=1.5,
                    label=lbl if c == 1 else None)

        ax.set_title(f"CUTOFF c = {c}")
        ax.set_xlabel("k (N: 2^k -> 2^(k+1))")
        ax.set_xticks(range(10, 22))
        ax.set_xticklabels([f"{k}" for k in range(10, 22)])

    axes[0].set_ylabel("ln R_k = ln(T(2^(k+1)) / T(2^k))")
    axes[0].legend(loc="upper right", fontsize=7.5, framealpha=0.9)
    plt.tight_layout()
    fig.savefig(out_fig_dir / "H1_ln_R_vs_k.png")
    fig.savefig(out_fig_dir / "H1_ln_R_vs_k.pdf")
    plt.close(fig)

    # ────────────────────────────────────────────────────────────────
    # H2: T / (N lg N) theo k cho c = 1 và c = 30 (ns)
    # ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 4.5))
    c_colors = {1: ("#2a78d6", "#8cb6ea"), 30: ("#eb6834", "#f7b599")}

    for c in [1, 30]:
        c_main, c_light = c_colors[c]
        sub = df_g[df_g["cutoff"] == c].copy()
        sub["v"] = sub["G"] / (sub["N"] * sub["k"])

        for f in [1, 2, 3]:
            sub_f = sub[sub["fork"] == f].sort_values("k")
            ax.plot(sub_f["k"], sub_f["v"], ":", color=c_light, linewidth=1.0,
                    label=f"c={c} fork {f}" if f == 1 else None)

        piv = sub.pivot(index="k", columns="fork", values="v")
        v_mean = (piv[1] * piv[2] * piv[3]) ** (1.0 / 3.0)
        ax.plot(v_mean.index, v_mean.values, "o-", color=c_main, linewidth=2.0, markersize=5,
                label=f"c={c} (trung bình)")

    ax.set_title("H2 [Khám phá]: Chi phí chuẩn hóa T / (N lg N) theo k (ns/phần tử)")
    ax.set_xlabel("k (N = 2^k)")
    ax.set_ylabel("T / (N lg N) (ns)")
    ax.set_xticks(range(10, 23))
    ax.legend(loc="upper left", fontsize=8.5)
    plt.tight_layout()
    fig.savefig(out_fig_dir / "H2_t_over_nlgn_vs_k.png")
    fig.savefig(out_fig_dir / "H2_t_over_nlgn_vs_k.pdf")
    plt.close(fig)

    # ────────────────────────────────────────────────────────────────
    # H3: D theo fork so với ba dự đoán (A3)
    # ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(7, 4.2))
    check_c = [1, 4, 7, 8, 10, 16, 30, 32, 64]
    x = np.arange(len(check_c))
    width = 0.2

    # Fork 1, 2, 3
    sub_step = df_step.set_index("cutoff").loc[check_c].reset_index()
    ax.bar(x - width, sub_step["D_fork1"], width, label="Đo Fork 1", color="#2a78d6", alpha=0.7)
    ax.bar(x, sub_step["D_fork2"], width, label="Đo Fork 2", color="#1baf7a", alpha=0.7)
    ax.bar(x + width, sub_step["D_fork3"], width, label="Đo Fork 3", color="#eb6834", alpha=0.7)

    # Dự đoán P3, P3c, P2
    ax.plot(x, sub_step["D_hat_P3"], "D--", color="#e87ba4", linewidth=1.5, markersize=6, label="Dự đoán P3 (bước)")
    ax.plot(x, sub_step["D_hat_P3c"], "^-", color="#1baf7a", linewidth=1.5, markersize=6, label="Dự đoán P3c (nội suy)")
    ax.axhline(0, color=NEUTRAL, linestyle=":", label="Dự đoán P2 (D = 0)")

    ax.set_title("H3: Phép thử bước D = ln R_(17->18) - ln R_(16->17) theo Fork")
    ax.set_xlabel("CUTOFF")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{c}" for c in check_c])
    ax.set_ylabel("D (ln ratio)")
    ax.legend(loc="upper right", fontsize=8.0)
    plt.tight_layout()
    fig.savefig(out_fig_dir / "H3_step_d_vs_fork.png")
    fig.savefig(out_fig_dir / "H3_step_d_vs_fork.pdf")
    plt.close(fig)

    # ────────────────────────────────────────────────────────────────
    # H4: r(N, c) theo k (B3) cho c = 7, 10, 30, 32
    # ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 4.5))
    plot_c = [7, 10, 30, 32]
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]

    for c, col in zip(plot_c, colors):
        sub_c = df_r_summary[df_r_summary["cutoff"] == c].sort_values("k")
        ax.plot(sub_c["k"], sub_c["r_mean"], "o-", color=col, linewidth=1.8, markersize=5, label=f"c={c} (đo doubling)")
        # Điểm results_final nếu có
        sub_rf = sub_c.dropna(subset=["r_results_final"])
        if len(sub_rf) > 0:
            ax.plot(sub_rf["k"], sub_rf["r_results_final"], "s", color=col, markersize=8, markerfacecolor="none",
                    markeredgewidth=1.8, label=f"c={c} (results_final)" if c == 7 else None)

    ax.set_title("H4 [Khám phá]: Hiệu quả tương đối r(N, c) = T(c)/T(1) theo k")
    ax.set_xlabel("k (N = 2^k)")
    ax.set_ylabel("r = T(c) / T(1)")
    ax.set_xticks(range(10, 23))
    ax.legend(loc="lower left", fontsize=8.0)
    plt.tight_layout()
    fig.savefig(out_fig_dir / "H4_ratio_r_vs_k.png")
    fig.savefig(out_fig_dir / "H4_ratio_r_vs_k.pdf")
    plt.close(fig)
    print("  → Đã lưu 4 hình H1-H4 (PNG + PDF) vào", out_fig_dir)


def main():
    args = parse_args()
    tables_dir = args.out_dir / "tables"
    figures_dir = args.out_dir / "figures"

    if args.print_report:
        print_markdown_report_tables(tables_dir)
        return

    print("=" * 80)
    print("T04b: PHÂN TÍCH DOUBLING TEST THEO KẾ HOẠCH ĐÃ ĐĂNG KÝ")
    print("=" * 80)

    # Tạo thư mục đầu ra
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Đọc dữ liệu
    print("\n--- 1. Đọc dữ liệu và kiểm tra toàn vẹn ---")
    df = load_doubling_data(args.data_dir)
    print(f"  → Đã đọc {len(df)} hàng dữ liệu sạch từ {args.data_dir}")

    # 2. Tính trung bình hình học G(f, N, c)
    df_g = compute_geometric_means(df)
    df_r, df_rbar = compute_r_and_rbar(df_g)

    # 3. Bootstrap trong-ô
    df_boot = bootstrap_within_cell(df, n_iters=args.bootstrap_iters, seed=args.seed)

    # 4. Đọc dự đoán preregistration
    df_preds, df_extrap = load_preregistered_predictions(args.prereg_dir)

    # ────────────────────────────────────────────────────────────────
    # A1. Sai số dự đoán doubling
    # ────────────────────────────────────────────────────────────────
    print("\n--- A1. Sai số dự đoán doubling ---")
    df_a1_full, df_a1_summary, df_a1_agg = analyze_a1_prediction_errors(df_preds, df_rbar, df_boot)
    df_a1_full.to_csv(tables_dir / "A1_pred_error_full.csv", index=False)
    df_a1_summary.to_csv(tables_dir / "A1_pred_error_summary.csv", index=False)
    df_a1_agg.to_csv(tables_dir / "A1_pred_error_aggregated.csv", index=False)

    # Sửa 2 (T04d): A1z noise interpretation
    df_a1z_full, df_a1z_summary = analyze_a1z_noise_interpretation(df_a1_full)
    df_a1z_full.to_csv(tables_dir / "A1z_noise_interpretation.csv", index=False)
    df_a1z_summary.to_csv(tables_dir / "A1z_noise_interpretation_summary.csv", index=False)
    print(f"  → Đã lưu A1 tables và A1z vào {tables_dir}")

    # ────────────────────────────────────────────────────────────────
    # A2. Ngoại suy tích lũy
    # ────────────────────────────────────────────────────────────────
    print("\n--- A2. Ngoại suy tích lũy Q_k ---")
    df_a2 = analyze_a2_cumulative_extrapolation(df_extrap, df_g)
    df_a2.to_csv(tables_dir / "A2_cumulative_extrapolation.csv", index=False)
    print(f"  → Đã lưu A2 table vào {tables_dir}")

    # ────────────────────────────────────────────────────────────────
    # A3. Phép thử bước D
    # ────────────────────────────────────────────────────────────────
    print("\n--- A3. Phép thử bước D ---")
    df_a3 = analyze_a3_step_test(df_r, df_preds)
    df_a3.to_csv(tables_dir / "A3_step_test.csv", index=False)
    print(f"  → Đã lưu A3 table vào {tables_dir}")

    # ────────────────────────────────────────────────────────────────
    # A4. Phép thử bão hòa S
    # ────────────────────────────────────────────────────────────────
    print("\n--- A4. Phép thử bão hòa S (P2 vs P3c) ---")
    df_a4 = analyze_a4_saturation_test(df_r, df_rbar, df_preds)
    df_a4.to_csv(tables_dir / "A4_saturation_test.csv", index=False)
    print(f"  → Đã lưu A4 table vào {tables_dir}")

    # ────────────────────────────────────────────────────────────────
    # A5. Đối chứng cùng cây
    # ────────────────────────────────────────────────────────────────
    print("\n--- A5. Đối chứng cùng cây ---")
    df_a5_summary, df_a5_by_n = analyze_a5_same_tree_control(df_g)
    df_a5_summary.to_csv(tables_dir / "A5_same_tree_summary.csv", index=False)
    df_a5_by_n.to_csv(tables_dir / "A5_same_tree_by_n.csv", index=False)
    print(f"  → Đã lưu A5 tables vào {tables_dir}")

    # ────────────────────────────────────────────────────────────────
    # A6. Số mũ cuối b
    # ────────────────────────────────────────────────────────────────
    print("\n--- A6. Số mũ cuối b ---")
    df_a6 = analyze_a6_power_law_b(df_g, df_preds)
    df_a6.to_csv(tables_dir / "A6_power_law_b.csv", index=False)
    print(f"  → Đã lưu A6 table vào {tables_dir}")

    # ────────────────────────────────────────────────────────────────
    # B. Khám phá (B1-B6)
    # ────────────────────────────────────────────────────────────────
    print("\n--- B1-B6. Phân tích Khám phá ---")
    df_b1 = analyze_b1_doubling_lecture(df_g, df_rbar)
    df_b1.to_csv(tables_dir / "B1_doubling_lecture.csv", index=False)

    df_b2 = analyze_b2_t_over_nlgn(df_g)
    df_b2.to_csv(tables_dir / "B2_t_over_nlgn.csv", index=False)

    df_b3 = analyze_b3_cutoff_ratio_r(df_g, args.results_final)
    df_b3.to_csv(tables_dir / "B3_cutoff_ratio_r.csv", index=False)

    df_b4 = analyze_b4_replication_final(df_g, args.results_final)
    if len(df_b4) > 0:
        df_b4.to_csv(tables_dir / "B4_replication_final.csv", index=False)

    df_b5_trial, df_b5_n = analyze_b5_trial_order_residuals(df)
    df_b5_trial.to_csv(tables_dir / "B5_trial_residuals.csv", index=False)
    df_b5_n.to_csv(tables_dir / "B5_trial_residuals_by_n.csv", index=False)

    df_b6 = analyze_b6_r_p3c_vs_measured(df_b3)
    df_b6.to_csv(tables_dir / "B6_r_p3c_vs_measured.csv", index=False)

    # Sửa 3 (T04d): B7 segment exponents
    df_b7 = analyze_b7_segment_exponents(df_g)
    df_b7.to_csv(tables_dir / "B7_segment_exponents.csv", index=False)

    # Sửa 4 (T04d): B8 D sensitivity 5 trials
    df_b8 = analyze_b8_d_sensitivity(df, df_preds)
    df_b8.to_csv(tables_dir / "B8_d_sensitivity_5trials.csv", index=False)

    print(f"  → Đã lưu B1-B8 tables vào {tables_dir}")

    # ────────────────────────────────────────────────────────────────
    # Vẽ hình H1-H4
    # ────────────────────────────────────────────────────────────────
    print("\n--- Vẽ hình H1-H4 ---")
    plot_figures(df_preds, df_r, df_rbar, df_boot, df_g, df_a3, df_b3, figures_dir)

    print("\n" + "=" * 80)
    print("HOÀN THÀNH PHÂN TÍCH T04b THÀNH CÔNG!")
    print("=" * 80)


if __name__ == "__main__":
    main()
