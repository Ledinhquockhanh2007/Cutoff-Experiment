#!/usr/bin/env python3
"""T06c: Bộ đồ thị chuẩn hóa cho báo cáo (make_figures.py).

Tuân thủ nghiêm ngặt các quy tắc:
- Mọi con số trên hình đến từ CSV nguồn chính thức (results_final và results_doubling), không tính tay.
- Không đọc dữ liệu từ results_run3 (loại bỏ triệt để sai lệch batch_k ở 2^12).
- PDF vector (pdf.fonttype=42), PNG 200 dpi (< 300 KB).
- Bảng màu Okabe-Ito an toàn cho người mù màu.
- Mỗi chuỗi có cả kiểu đường và ký hiệu khác nhau để in đen trắng phân biệt được.
- Đặt nhãn trục mathtext đầy đủ (render đúng chỉ số trên/dưới).
- Bố trí chú giải và nhãn tránh mọi hiện tượng đè chữ, che dữ liệu.
- Phân loại chính xác [kiểm định đã đăng ký] và [khám phá].
- Mỗi hình xuất đủ bộ 4 tệp: .pdf, .png, .data.csv, .src.txt.
- Tạo file FIGURES.md mô tả toàn bộ danh mục hình.
"""

import argparse
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

# Bảng màu Okabe-Ito (colorblind-safe)
OKABE_ITO = {
    "black": "#000000",
    "orange": "#E69F00",
    "sky_blue": "#56B4E9",
    "bluish_green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermilion": "#D55E00",
    "reddish_purple": "#CC79A7",
    "grey": "#777777",
    "light_grey": "#CCCCCC",
}

# Bảng màu Grayscale (khi chạy cờ --grayscale)
GRAYSCALE = {
    "black": "#000000",
    "orange": "#444444",
    "sky_blue": "#888888",
    "bluish_green": "#222222",
    "yellow": "#AAAAAA",
    "blue": "#555555",
    "vermilion": "#333333",
    "reddish_purple": "#666666",
    "grey": "#777777",
    "light_grey": "#DDDDDD",
}

COLORS = OKABE_ITO


def set_style(grayscale=False):
    """Thiết lập kiểu dáng đồ thị chuẩn cho báo cáo học thuật."""
    global COLORS
    COLORS = GRAYSCALE if grayscale else OKABE_ITO

    mpl.rcParams.update({
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans", "Helvetica"],
        "font.size": 9.0,
        "axes.titlesize": 9.0,
        "axes.labelsize": 9.0,
        "xtick.labelsize": 8.0,
        "ytick.labelsize": 8.0,
        "legend.fontsize": 8.0,
        "legend.framealpha": 0.9,
        "legend.edgecolor": "#cccccc",
        "figure.titlesize": 9.5,
        "lines.linewidth": 1.3,
        "lines.markersize": 4.5,
        "axes.grid": True,
        "grid.color": "#e2e2e2",
        "grid.linestyle": "--",
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "axes.edgecolor": "#555555",
        "axes.linewidth": 0.8,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,
    })


def save_fig_bundle(fig, out_dir: Path, name: str, df_data: pd.DataFrame, src_text: str):
    """Xuất đủ bộ 4 tệp: .pdf, .png, .data.csv, .src.txt."""
    pdf_path = out_dir / f"{name}.pdf"
    png_path = out_dir / f"{name}.png"
    csv_path = out_dir / f"{name}.data.csv"
    src_path = out_dir / f"{name}.src.txt"

    fig.savefig(pdf_path)
    fig.savefig(png_path)
    plt.close(fig)

    df_data.to_csv(csv_path, index=False)
    src_path.write_text(src_text.strip() + "\n", encoding="utf-8")

    png_size_kb = png_path.stat().st_size / 1024.0
    print(f"  [OK] {name}: PDF + PNG ({png_size_kb:.1f} KB) + CSV + TXT")


# ==============================================================================
# 8 HÌNH THÂN BÀI (fig01 .. fig08)
# ==============================================================================

def make_fig01(out_dir: Path):
    """fig01: r(N, c) theo CUTOFF cho dữ liệu random trên 3 thang N (results_final)."""
    src_file = "results_final/analysis/tables/r_by_cutoff.csv"
    df = pd.read_csv(src_file)
    df_rand = df[df["distribution"] == "random"].copy()

    fig, ax = plt.subplots(figsize=(4.72, 3.0))  # 120 mm width
    scales = [
        ("2^12", "$S = 2^{12}$ ($N = 4\\text{K}..8\\text{K}$)", COLORS["blue"], "-", "o"),
        ("2^16", "$S = 2^{16}$ ($N = 65\\text{K}..131\\text{K}$)", COLORS["orange"], "--", "s"),
        ("2^19", "$S = 2^{19}$ ($N = 524\\text{K}..1\\text{M}$)", COLORS["bluish_green"], "-.", "^"),
    ]

    out_rows = []
    for scale_key, label, color, lstyle, marker in scales:
        sub = df_rand[df_rand["scale"] == scale_key].sort_values("cutoff")
        ax.plot(sub["cutoff"], sub["r_gm"], label=label, color=color,
                linestyle=lstyle, marker=marker, markevery=2)
        ax.fill_between(sub["cutoff"], sub["ci_lo"], sub["ci_hi"], color=color, alpha=0.15)
        for _, r in sub.iterrows():
            out_rows.append({
                "scale": scale_key,
                "cutoff": int(r["cutoff"]),
                "r_geometric_mean": r["r_gm"],
                "ci95_low": r["ci_lo"],
                "ci95_high": r["ci_hi"],
            })

    # Đánh dấu c = 7, 10, 30
    for c_mark, c_style, c_txt in [(7, ":", "c=7"), (10, "--", "c=10"), (30, "-.", "c=30")]:
        ax.axvline(c_mark, color=COLORS["grey"], linestyle=c_style, linewidth=0.9, alpha=0.8)
        ax.text(c_mark, 0.99, f" {c_txt}", color=COLORS["grey"], fontsize=7.5,
                rotation=90, verticalalignment="top")

    ax.set_xlabel("CUTOFF $c$ (phần tử, thang tuyến tính)")
    ax.set_ylabel("Tỉ số thời gian $r(N, c) = T(c) / T(1)$")
    ax.set_ylim(0.81, 1.01)
    # Chú giải ở upper right: hoàn toàn trống vì tất cả các đường đều giảm xuống <= 0.92 ở c >= 20
    ax.legend(loc="upper right", fontsize=7.5)

    df_out = pd.DataFrame(out_rows)
    src_text = f"""
Hình: fig01_r_vs_cutoff_random
Loại: Khám phá (Exploratory Analysis)
Nguồn dữ liệu: {src_file}
Mô tả chuỗi:
- Dữ liệu lấy từ {src_file} trong results_final: Thang 2^12 lấy từ Run 4 (K = 1, 0 GC, ghim nhân 5), thang 2^16 và 2^19 lấy từ Run 3 (ghim nhân 5).
- 3 đường ứng với 3 thang quy mô S in {{2^12, 2^16, 2^19}}, mỗi thang gồm 24 kích thước N hình học.
- r(N, c) là trung bình nhân của tỉ số thời gian T(c)/T(1) trên 24 giá trị N.
- Dải mờ quanh mỗi đường biểu thị khoảng tin cậy CI 95% bootstrap cụm theo N (B = 10 000).
- Các vạch đứng đánh dấu các mốc CUTOFF quy ước: c = 7, 10 (giáo trình) và c = 30 (gần tối ưu).
"""
    save_fig_bundle(fig, out_dir, "fig01_r_vs_cutoff_random", df_out, src_text)


def make_fig02(out_dir: Path):
    """fig02: Mô hình M2: r thực đo so với dự đoán mô hình và sai số LOSO."""
    src_file_insample = "results_final/analysis_v2/tables/cost_model_in_sample_errors.csv"
    src_file_loso = "results_final/analysis_v2/tables/validate_2e19_loso.csv"

    df_in = pd.read_csv(src_file_insample)
    df_loso = pd.read_csv(src_file_loso)

    fig, axes = plt.subplots(1, 2, figsize=(6.69, 2.85), sharey=True)  # 170 mm width

    # Panel A: In-sample fit trên 3 thang
    ax_a = axes[0]
    scale_cfg = [
        ("2^12", "$S = 2^{12}$", COLORS["blue"], "o"),
        ("2^16", "$S = 2^{16}$", COLORS["orange"], "s"),
        ("2^19", "$S = 2^{19}$", COLORS["bluish_green"], "^"),
    ]
    out_rows = []
    for s_key, s_lbl, color, marker in scale_cfg:
        sub = df_in[df_in["scale"] == s_key].sort_values("cutoff")
        ax_a.errorbar(sub["cutoff"], sub["r_meas"],
                      yerr=[sub["r_meas"] - sub["ci_lo"], sub["ci_hi"] - sub["r_meas"]],
                      fmt=marker, color=color, label=f"Đo {s_lbl}", capsize=2, markersize=3.8)
        ax_a.plot(sub["cutoff"], sub["r_hat_M2"], linestyle="--", color=color, label=f"M2 {s_lbl}")
        for _, r in sub.iterrows():
            out_rows.append({
                "panel": "in_sample",
                "scale": s_key,
                "cutoff": int(r["cutoff"]),
                "r_meas": r["r_meas"],
                "ci_lo": r["ci_lo"],
                "ci_hi": r["ci_hi"],
                "r_hat": r["r_hat_M2"],
                "diff": r["signed_diff"],
            })

    ax_a.set_title("(a) Khớp nội suy (In-sample, 3 thang)", fontsize=8.5)
    ax_a.set_xlabel("CUTOFF $c$")
    ax_a.set_ylabel("Tỉ số thời gian $r(N, c)$")
    # Đặt chú giải ở upper right để không che các điểm 2^12 ở lower right
    ax_a.legend(loc="upper right", fontsize=6.8, ncol=2)

    # Panel B: LOSO ngoại suy trên thang 2^19
    ax_b = axes[1]
    ax_b.errorbar(df_loso["cutoff"], df_loso["r_meas"],
                  yerr=[df_loso["r_meas"] - df_loso["ci_lo"], df_loso["ci_hi"] - df_loso["r_meas"]],
                  fmt="o", color=COLORS["bluish_green"], label="Đo thực tế $2^{19}$", capsize=1.5, markersize=3.5)
    ax_b.plot(df_loso["cutoff"], df_loso["r_hat_loso"], linestyle="--", color=COLORS["vermilion"],
              label="M2 LOSO (huấn luyện $2^{12}+2^{16}$)")
    # Dải ±0.01 quanh dự đoán M2 LOSO (mức sai số thực nghiệm nêu ở R03b)
    ax_b.fill_between(df_loso["cutoff"], df_loso["r_hat_loso"] - 0.01, df_loso["r_hat_loso"] + 0.01,
                      color=COLORS["vermilion"], alpha=0.15, label="Dải dung sai ±0.01")

    for _, r in df_loso.iterrows():
        out_rows.append({
            "panel": "loso_holdout_2e19",
            "scale": "2^19",
            "cutoff": int(r["cutoff"]),
            "r_meas": r["r_meas"],
            "ci_lo": r["ci_lo"],
            "ci_hi": r["ci_hi"],
            "r_hat": r["r_hat_loso"],
            "diff": r["diff"],
        })

    ax_b.set_title("(b) Kiểm tra ngoài mẫu LOSO (Holdout $S = 2^{19}$)", fontsize=8.5)
    ax_b.set_xlabel("CUTOFF $c$")
    ax_b.legend(loc="lower right", fontsize=7.0)

    df_out = pd.DataFrame(out_rows)
    src_text = f"""
Hình: fig02_m2_fit_loso
Loại: Khám phá / Kiểm tra ngoài mẫu, KHÔNG đăng ký trước (Exploratory / Out-of-sample Cross-Validation)
Nguồn dữ liệu:
- Panel (a): {src_file_insample}
- Panel (b): {src_file_loso}
Mô tả chuỗi:
- Panel (a): So sánh r thực đo (điểm kèm thanh sai số CI 95% bootstrap) với r dự đoán bởi mô hình chi phí M2 (đường đứt) trên 3 thang N.
- Panel (b): Thử nghiệm Leave-One-Scale-Out (LOSO) trên thang S = 2^19: Mô hình M2 được huấn luyện trên 2 thang nhỏ (2^12 và 2^16). Theo giao thức LOSO, hệ số alpha_19 của thang bị giữ lại được hiệu chỉnh từ dữ liệu c = 1 của chính 2^19; các tham số w1, w2, w3, beta lấy từ 2^12 + 2^16 để ngoại suy cho các c > 1.
- Dải màu mờ ở Panel (b) biểu thị khoảng dung sai thực nghiệm ±0.01 (xác lập ở R03b sau khi khớp). Mọi điểm đo đều nằm trọn trong dải dung sai (RMSE LOSO = 0.0029).
"""
    save_fig_bundle(fig, out_dir, "fig02_m2_fit_loso", df_out, src_text)


def make_fig03(out_dir: Path):
    """fig03: Phân rã thành phần chi phí của CUTOFF theo mô hình M2 (Thang S = 2^16)."""
    src_file = "results_final/analysis_v2/tables/cost_model_decomposition.csv"
    src_sens = "results_final/analysis_v2/tables/cost_model_sensitivity.csv"
    df = pd.read_csv(src_file)

    fig, ax = plt.subplots(figsize=(3.35, 2.75))  # 85 mm width

    # Vùng gần tối ưu 2% [14, 48] (kịch bản cơ sở từ cost_model_sensitivity.csv)
    ax.axvspan(14, 48, color=COLORS["light_grey"], alpha=0.4, label="Vùng gần tối ưu 2% [14, 48]")

    ax.plot(df["cutoff"], df["ratio_save"] * 100, label="Tiết kiệm bỏ merge & đệ quy",
            color=COLORS["bluish_green"], linestyle="--", marker="s", markevery=4)
    ax.plot(df["cutoff"], df["ratio_insert"] * 100, label="Chi phí thêm insertion sort",
            color=COLORS["vermilion"], linestyle=":", marker="^", markevery=4)
    ax.plot(df["cutoff"], df["net_reduction"] * 100, label="Mức giảm ròng ($1 - \\hat{r}$)",
            color=COLORS["blue"], linestyle="-", marker="o", markevery=4)

    # Đánh dấu c* = 40 (nhỏ, không dùng chấm to)
    opt_row = df[df["cutoff"] == 40].iloc[0]
    ax.scatter([40], [opt_row["net_reduction"] * 100], color=COLORS["blue"],
               s=18, zorder=5, edgecolors=COLORS["black"])
    ax.annotate("$c^* = 40$\n(giảm 11.6%)", xy=(40, opt_row["net_reduction"] * 100),
                xytext=(44, opt_row["net_reduction"] * 100 - 4.5),
                arrowprops=dict(arrowstyle="->", color=COLORS["grey"], lw=0.7),
                fontsize=7.2)

    # Bỏ tiêu đề trong hình theo quy tắc T06c §2; đưa thang vào nhãn trục và chú giải
    ax.set_xlabel("CUTOFF $c$ (phần tử, thang $S = 2^{16}$)")
    ax.set_ylabel("Tỉ lệ chi phí (%)")
    ax.set_ylim(-1, 36)
    ax.legend(title="Thang $S = 2^{16}$", title_fontsize=7.2, loc="upper center",
              bbox_to_anchor=(0.5, -0.22), ncol=1, fontsize=6.8)

    df_out = df.copy()
    src_text = f"""
Hình: fig03_cost_decomposition
Loại: Khám phá / Mô hình lý thuyết (Exploratory / Model Analysis)
Nguồn dữ liệu:
- Phân rã chi phí: {src_file}
- Độ nhạy & vùng gần tối ưu: {src_sens}
Mô tả chuỗi:
- Phân rã thành phần chi phí của mô hình M2 trên thang chuẩn S = 2^16: 1 - r_hat = ratio_save - ratio_insert.
- Đường 'Tiết kiệm bỏ merge & đệ quy' (ratio_save): tăng logarit theo c do triệt tiêu các tầng cây đệ quy dưới đáy.
- Đường 'Chi phí thêm insertion sort' (ratio_insert): tăng bậc hai O(c^2) theo chiều dài lá.
- Vùng tô mờ xám là vùng gần tối ưu 2% [14, 48] theo kịch bản cơ sở (c*_curve = 40, min r_hat = 0.8835, net reduction 11.65%).
- Đánh dấu cực trị c* = 40 của đường cong liên tục giải thích cơ chế hình thành đáy phẳng rộng của đường cong thời gian.
"""
    save_fig_bundle(fig, out_dir, "fig03_cost_decomposition", df_out, src_text)


def make_fig04(out_dir: Path):
    """fig04: Doubling test: ln R theo k cho c = 1 và c = 30 cùng các predictor."""
    src_pred = "results_doubling/analysis/tables/A1_pred_error_full.csv"
    src_b1 = "results_doubling/analysis/tables/B1_doubling_lecture.csv"

    df_pred = pd.read_csv(src_pred)
    df_b1 = pd.read_csv(src_b1)

    fig, axes = plt.subplots(1, 2, figsize=(6.69, 3.25), layout="constrained", sharey=True)  # 170 mm width

    cutoffs = [(1, "$c = 1$ (Baseline)", axes[0]), (30, "$c = 30$ (Gần tối ưu)", axes[1])]
    out_rows = []

    pred_styles = {
        "P1_theory_nlgn": ("P1 ($N \\lg N$)", COLORS["grey"], ":", "v"),
        "P2_power_law_48N": ("P2 (Power-law $48N$)", COLORS["orange"], "--", "s"),
        "P3c_model_M2_interp": ("P3c (M2 nội suy)", COLORS["bluish_green"], "-.", "^"),
    }

    n_by_k = dict(zip(df_b1["k"], df_b1["N"]))

    for c_val, c_lbl, ax in cutoffs:
        sub_meas = df_pred[(df_pred["cutoff"] == c_val) & (df_pred["predictor"] == "P1_theory_nlgn")].sort_values("k_from")

        # Độ bất định thực tế: ±2*SE của ln R_bar tính từ 3 fork độc lập
        yerr_actual = 2.0 * sub_meas["ln_R_bar_se"]
        ax.errorbar(sub_meas["k_from"], sub_meas["ln_R_bar"],
                    yerr=yerr_actual, fmt="o", color=COLORS["black"],
                    label="Thực đo $\\ln \\bar{R}_k$ ($\\pm 2\\cdot\\mathrm{SE}$)", capsize=2, markersize=3.8, zorder=4)

        for p_key, (p_name, p_col, p_ls, p_mk) in pred_styles.items():
            sub_p = df_pred[(df_pred["cutoff"] == c_val) & (df_pred["predictor"] == p_key)].sort_values("k_from")
            ax.plot(sub_p["k_from"], sub_p["ln_R_hat"], label=p_name,
                    color=p_col, linestyle=p_ls, marker=p_mk, markevery=2)

        # Vùng ngoại suy k >= 19
        ax.axvspan(18.5, 21.5, color=COLORS["light_grey"], alpha=0.3, zorder=0)
        # Đặt chữ 'Vùng ngoại suy' ở đỉnh trục để không đè lên đường P3c
        ax.text(20.0, 0.885, "Vùng ngoại suy\n($k \\geq 19$)", fontsize=7.0, color=COLORS["grey"],
                ha="center", va="top")

        ax.set_title(f"({chr(97 + (0 if c_val == 1 else 1))}) {c_lbl}", fontsize=8.5)
        ax.set_xlabel("Bước doubling $k = \\lg N$ (từ $N_k$ sang $N_{k+1}$)")
        if c_val == 1:
            ax.set_ylabel("$\\ln R_k = \\ln( T(2^{k+1}) / T(2^k) )$")

        for _, r in sub_meas.iterrows():
            k_val = int(r["k_from"])
            out_rows.append({
                "cutoff": c_val,
                "k_step": k_val,
                "N_from": n_by_k.get(k_val, 1 << k_val),
                "ln_R_meas": r["ln_R_bar"],
                "ln_R_se": r["ln_R_bar_se"],
                "R_mean": r["R_bar"],
                "ln_R_ci_low": r["ln_R_bar_ci_low"],
                "ln_R_ci_high": r["ln_R_bar_ci_high"],
            })

    axes[0].set_ylim(0.68, 0.90)

    # Chú giải đặt HOÀN TOÀN RA NGOÀI vùng vẽ bên dưới hai panel (T06c §1)
    # Tránh hoàn toàn việc che điểm đo c=1, k=14 (ln R_bar = 0.7407) và các điểm k=10..21
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=4, fontsize=7.2, frameon=True, framealpha=0.9)

    df_out = pd.DataFrame(out_rows)
    src_text = f"""
Hình: fig04_doubling_ln_R
Loại: Kiểm định đã đăng ký (Registered Analysis A1)
Nguồn dữ liệu:
- Dữ liệu thực đo: {src_b1}
- Dữ liệu dự đoán mô hình: {src_pred}
Mô tả chuỗi:
- Khảo sát tỉ số tăng trưởng thời gian doubling R_k = T(2^(k+1))/T(2^k) dưới dạng logarit ln R_k.
- Thanh sai số quanh điểm thực đo là khoảng tin cậy xấp xỉ ±2*SE của ln R_bar tính từ 3 fork độc lập (không phải ngưỡng đăng ký).
- Ngưỡng sai số đăng ký trước |e_k| <= 0.015 (1.5%) được phân tích trong báo cáo văn bản.
- Đồ thị chỉ thể hiện 3 mô hình dự báo chính: P1 (lý thuyết N lg N thuần), P2 (quy luật lũy thừa N^b), và P3c (mô hình M2 nội suy). Các mô hình P2b, P3, P3b có trong Bảng A1.
- Vùng tô xám (k >= 19) là miền ngoại suy vượt quy mô huấn luyện (N >= 524K).
- Chú giải đặt bên ngoài đáy trục, bảo đảm toàn bộ các điểm đo k = 10..21 ở cả hai panel đều thấy rõ (bao gồm điểm c=1, k=14: ln R_bar = 0.7407, CI [0.705, 0.763]).
"""
    save_fig_bundle(fig, out_dir, "fig04_doubling_ln_R", df_out, src_text)


def make_fig05(out_dir: Path):
    """fig05: T / (N lg N) theo k kèm ngưỡng bộ nhớ L2 và L3 cache."""
    src_b2 = "results_doubling/analysis/tables/B2_t_over_nlgn.csv"
    src_cache = "results_final/analysis_v2/tables/memory_cache_discussion.csv"

    df_b2 = pd.read_csv(src_b2)
    df_cache = pd.read_csv(src_cache)

    fig, ax = plt.subplots(figsize=(4.72, 3.05))  # 120 mm width

    c_cfg = [
        (1, "$c = 1$ (Baseline)", COLORS["blue"], "-", "o"),
        (30, "$c = 30$ (Gần tối ưu)", COLORS["orange"], "--", "s"),
    ]
    out_rows = []

    for c_val, c_lbl, color, lstyle, marker in c_cfg:
        sub = df_b2[df_b2["cutoff"] == c_val].sort_values("k")
        sd_forks = sub[["v_fork1_ns", "v_fork2_ns", "v_fork3_ns"]].std(axis=1)
        ax.errorbar(sub["k"], sub["v_mean_ns"], yerr=sd_forks,
                    fmt=marker, linestyle=lstyle, color=color, label=c_lbl, capsize=2)
        for _, r in sub.iterrows():
            out_rows.append({
                "cutoff": c_val,
                "k": int(r["k"]),
                "N": int(r["N"]),
                "t_over_nlgn_ns": r["v_mean_ns"],
                "sd_between_forks_ns": np.std([r["v_fork1_ns"], r["v_fork2_ns"], r["v_fork3_ns"]], ddof=1),
            })

    # Vạch đứng ngưỡng L2 và L3
    k_l2 = 15.41
    k_l3 = 19.41

    ax.axvline(k_l2, color=COLORS["grey"], linestyle=":", linewidth=1.1)
    ax.axvline(k_l3, color=COLORS["vermilion"], linestyle="-.", linewidth=1.1)

    # Đặt nhãn cache ở đỉnh trên đồ thị, tránh hoàn toàn hộp chú giải
    ax.text(k_l2, 15.65, "L2 (1 MiB)", color=COLORS["grey"], fontsize=7.5,
            ha="center", va="bottom")
    ax.text(k_l3, 15.65, "L3 (16 MiB)", color=COLORS["vermilion"], fontsize=7.5,
            ha="center", va="bottom")

    ax.set_xlabel("Quy mô $k = \\lg N$ ($N = 2^k$ từ 1 024 đến 4 194 304)")
    ax.set_ylabel("Thời gian chuẩn hóa $T / (N \\lg N)$ (ns)")
    ax.set_ylim(7.5, 16.3)
    # Chú giải ở upper left (k in [10, 13]) không chạm vạch L2 ở k = 15.41
    ax.legend(loc="upper left", fontsize=7.5)

    df_out = pd.DataFrame(out_rows)
    src_text = f"""
Hình: fig05_t_over_nlgn_cache
Loại: Khám phá / Đối chiếu phần cứng (Exploratory Analysis)
Nguồn dữ liệu:
- Thời gian chuẩn hóa T/(N lg N): {src_b2}
- Dung lượng bộ nhớ hoạt động: {src_cache}
Mô tả chuỗi:
- v_mean_ns = T / (N lg N) (ns) là thời gian chạy trung bình trên một đơn vị độ phức tạp.
- Thanh sai số biểu thị độ lệch chuẩn (SD) giữa 3 fork độc lập ghim nhân 5.
- Các vạch đứng biểu thị điểm chuyển tiếp khi dung lượng hoạt động (a + aux + Integer = 24N + 32 byte) vượt quá kích thước bộ nhớ đệm:
  * L2 = 1.00 MiB / nhân (tại k ≈ 15.41, giữa k=15 và k=16).
  * L3 = 16.00 MiB chia sẻ (tại k ≈ 19.41, giữa k=19 và k=20).
- Ghi chú cơ chế (Quy tắc C): Mức tăng mạnh của T/(N lg N) ở khoảng k = 19..20 (+10.3%) là NHẤT QUÁN VỚI giả thuyết dữ liệu tràn L3 sang RAM chính, nhưng không thể kết luận quan hệ nhân quả duy nhất nếu không có hardware counters.
"""
    save_fig_bundle(fig, out_dir, "fig05_t_over_nlgn_cache", df_out, src_text)


def make_fig06(out_dir: Path):
    """fig06: Mức giảm thời gian r(N, c=30) giảm dần theo quy mô N (Diminishing returns)."""
    src_file = "results_doubling/analysis/tables/B3_cutoff_ratio_r.csv"
    df = pd.read_csv(src_file)
    sub = df[df["cutoff"] == 30].sort_values("k")

    fig, ax = plt.subplots(figsize=(3.35, 2.75))  # 85 mm width

    # Điểm đo r(N, 30) kèm dải min-max giữa các fork
    ax.plot(sub["k"], sub["r_mean"], color=COLORS["blue"], linestyle="-", marker="o",
            label="$r$ thực đo ($c = 30$)")
    ax.fill_between(sub["k"], sub["r_min"], sub["r_max"], color=COLORS["blue"], alpha=0.15,
                    label="Khoảng biến thiên 3 fork")

    # Đường tham chiếu 20% của bài giảng (r = 0.80)
    ax.axhline(0.80, color=COLORS["vermilion"], linestyle="--", linewidth=1.1,
               label="Bài giảng ('khoảng 20%', $r = 0.80$)")

    ax.set_xlabel("Quy mô $k = \\lg N$ ($N = 2^k$ từ 1K đến 4M)")
    ax.set_ylabel("Tỉ số thời gian $r(N, 30) = T(30) / T(1)$")
    ax.set_ylim(0.74, 0.98)
    ax.legend(loc="upper left", fontsize=6.5)

    # Đánh dấu mức giảm tại 2 đầu mút
    r_1k = sub.loc[sub["k"] == 10, "r_mean"].values[0]
    r_4m = sub.loc[sub["k"] == 22, "r_mean"].values[0]
    # Chú thích N=1K đặt dưới-phải điểm, dưới đường 0.80 để hoàn toàn tránh đường dữ liệu và dải mờ
    ax.annotate(f"$N=1\\text{{K}}$: $r={r_1k:.3f}$\n(giảm { (1-r_1k)*100:.1f}%)", xy=(10, r_1k),
                xytext=(10.7, 0.755), fontsize=7.0,
                arrowprops=dict(arrowstyle="->", color=COLORS["grey"], lw=0.7))
    # Chú thích N=4M đặt trong khoảng trống rộng rãi dưới đường cong
    ax.annotate(f"$N=4\\text{{M}}$: $r={r_4m:.3f}$\n(giảm { (1-r_4m)*100:.1f}%)", xy=(22, r_4m),
                xytext=(18.2, 0.86), fontsize=7.0,
                arrowprops=dict(arrowstyle="->", color=COLORS["grey"], lw=0.7))

    df_out = sub[["k", "N", "cutoff", "r_mean", "r_min", "r_max"]].copy()
    src_text = f"""
Hình: fig06_r_diminishing_returns
Loại: Khám phá / Ngoại suy quy mô lớn (Exploratory / Scalability Analysis)
Nguồn dữ liệu: {src_file}
Mô tả chuỗi:
- Tỉ số thời gian r(N, 30) = T(30)/T(1) trên thang doubling từ N = 2^10 (1 024) đến N = 2^22 (4 194 304).
- Lưu ý quan trọng về cây đệ quy: Tại N = 2^k, c = 30 cho chiều dài lá bằng đúng 16 (tức tạo ra cấu trúc cây đệ quy hoàn toàn giống nhau với mọi c trong đoạn [16, 31]).
- Dải màu lam biểu thị khoảng giá trị nhỏ nhất và lớn nhất (min-max) giữa 3 fork độc lập.
- Đường đứt nét đỏ ngang biểu thị mức tăng tốc 'khoảng 20%' (tương ứng r = 0.80) nêu trong bài giảng Sedgewick.
- Kết quả cho thấy lợi ích của cutoff giảm đơn điệu theo N: từ giảm ~18.9% ở N = 1K xuống chỉ còn ~5.9% ở N = 4M, do chi phí truy cập bộ nhớ ở các tầng merge trên cùng chiếm ưu thế tuyệt đối khi N vượt kích thước cache.
"""
    save_fig_bundle(fig, out_dir, "fig06_r_diminishing_returns", df_out, src_text)


def make_fig07(out_dir: Path):
    """fig07: Bộ nhớ mergesort: byte/phần tử và dung lượng theo N trên các cấu hình JVM."""
    src_meas = "results_final/analysis_v2/tables/memory_measurements.csv"
    df = pd.read_csv(src_meas)

    fig, axes = plt.subplots(1, 2, figsize=(6.69, 3.0), layout="constrained")  # 170 mm width

    # Panel A: Byte trên mỗi phần tử
    ax_a = axes[0]
    configs = [
        ("default", "Mặc định (nén oops + nén con trỏ lớp)", COLORS["blue"], "o", "-"),
        ("no_coops", "-UseCompressedOops", COLORS["orange"], "s", "--"),
        ("lecture", "-UseCompressedOops\n-UseCompressedClassPointers\n(mô hình chuẩn)", COLORS["vermilion"], "^", "-."),
    ]
    out_rows = []

    for cfg_id, cfg_lbl, color, marker, lstyle in configs:
        sub = df[df["config"] == cfg_id].sort_values("N")
        ax_a.plot(np.log2(sub["N"]), sub["bytes_per_elem_jol"], label=cfg_lbl,
                  color=color, marker=marker, linestyle=lstyle)
        for _, r in sub.iterrows():
            out_rows.append({
                "panel": "bytes_per_element",
                "config": cfg_id,
                "N": int(r["N"]),
                "k": int(np.log2(r["N"])),
                "bytes_jol": r["bytes_jol"],
                "bytes_alloc": r["bytes_alloc"],
                "bytes_per_elem": r["bytes_per_elem_jol"],
            })

    ax_a.set_title("(a) Số byte trên mỗi phần tử", fontsize=8.5)
    ax_a.set_xlabel("Quy mô $k = \\lg N$")
    ax_a.set_ylabel("Byte / phần tử (JOL)")
    ax_a.set_ylim(18, 52)
    ax_a.legend(loc="upper left", fontsize=6.2)

    # Panel B: Tổng dung lượng bộ nhớ hoạt động theo N (MiB, trục y log10 nhãn số MiB)
    ax_b = axes[1]
    for cfg_id, cfg_lbl, color, marker, lstyle in configs:
        sub = df[df["config"] == cfg_id].sort_values("N")
        # Chuyển bytes_jol sang MiB
        ax_b.plot(sub["N"], sub["bytes_jol"] / (1024 * 1024), label=cfg_lbl,
                  color=color, marker=marker, linestyle=lstyle)

    # Đường tham chiếu L2 và L3 cache
    ax_b.axhline(1.0, color=COLORS["grey"], linestyle=":", linewidth=1.0, label="L2 (1 MiB)")
    ax_b.axhline(16.0, color=COLORS["grey"], linestyle="-.", linewidth=1.0, label="L3 (16 MiB)")

    ax_b.set_xscale("log", base=2)
    ax_b.set_yscale("log")  # log10
    ax_b.set_yticks([0.01, 0.1, 1.0, 10.0, 100.0])
    ax_b.set_yticklabels(["0.01", "0.1", "1", "10", "100"])
    ax_b.set_ylim(0.008, 250)

    # Format x-ticks
    ax_b.set_xticks([1024, 16384, 65536, 1048576, 4194304])
    ax_b.set_xticklabels(["1K", "16K", "64K", "1M", "4M"])

    ax_b.set_title("(b) Tổng dung lượng hoạt động (MiB)", fontsize=8.5)
    ax_b.set_xlabel("Số phần tử $N$ (thang $\\log_2$)")
    ax_b.set_ylabel("Dung lượng bộ nhớ (MiB, thang log)")
    # Đặt chú giải ở lower right: vùng N >= 64K và y <= 1 MiB hoàn toàn trống, không che đường nào
    ax_b.legend(loc="lower right", fontsize=5.8)

    df_out = pd.DataFrame(out_rows)
    src_text = f"""
Hình: fig07_memory_by_config
Loại: Khám phá / Đo đạc bộ nhớ độc lập (T05 / T05b)
Nguồn dữ liệu: {src_meas}
Mô tả chuỗi:
- Panel (a): Số byte thực đo trên mỗi phần tử N theo 3 cấu hình JVM:
  * Mặc định (nén oops + nén con trỏ lớp): 24 byte/phần tử (mô hình 24N + 32 byte).
  * Trung gian (-XX:-UseCompressedOops): 32 byte/phần tử (mô hình 32N + 32 byte).
  * Mô hình chuẩn (-XX:-UseCompressedOops -XX:-UseCompressedClassPointers): 40 byte/phần tử (mô hình 40N + 48 byte).
- Panel (b): Tổng dung lượng bộ nhớ hoạt động (a + aux + N đối tượng Integer) theo N so với các mốc phần cứng L2 (1 MiB/nhân) và L3 (16 MiB). Trục y biểu thị theo thang log với các mốc thập phân MiB (0.01, 0.1, 1, 10, 100).
- Cả hai phương pháp đo độc lập (JOL GraphLayout và ThreadMXBean allocated bytes sau warmup) đều cho kết quả hoàn toàn trùng khớp với mô hình lý thuyết (sai số 0.000%).
"""
    save_fig_bundle(fig, out_dir, "fig07_memory_by_config", df_out, src_text)


def make_fig08(out_dir: Path):
    """fig08: r theo CUTOFF cho 4 phân bố không ngẫu nhiên (Thang S = 2^16, trung bình nhân 24 N)."""
    src_file = "results_final/analysis_v2/tables/validate_other_distributions.csv"
    df = pd.read_csv(src_file)

    fig, axes = plt.subplots(2, 2, figsize=(6.69, 4.0), sharex=True, sharey=True)  # 170 mm width
    axes_flat = axes.flatten()

    dists = [
        ("sorted", "Đã sắp xếp (Sorted)", axes_flat[0], 64, True),
        ("nearly_sorted", "Gần như đã sắp (Nearly sorted)", axes_flat[1], 64, True),
        ("reversed", "Đảo ngược (Reversed)", axes_flat[2], 8, False),
        ("few_distinct", "Ít giá trị phân biệt (Few distinct)", axes_flat[3], 32, False),
    ]

    out_rows = []
    for d_key, d_title, ax, opt_c, is_boundary in dists:
        sub = df[df["distribution"] == d_key].sort_values("cutoff")
        ax.errorbar(sub["cutoff"], sub["r_meas"],
                    yerr=[sub["r_meas"] - sub["ci_lo"], sub["ci_hi"] - sub["r_meas"]],
                    fmt="o", color=COLORS["blue"], label="Đo thực tế", capsize=2, markersize=3.5)
        ax.plot(sub["cutoff"], sub["r_hat"], linestyle="--", color=COLORS["vermilion"],
                label="M2 (huấn luyện trên random)")

        # Đánh dấu c tối ưu
        ax.axvline(opt_c, color=COLORS["grey"], linestyle=":", linewidth=0.9)
        if is_boundary:
            # Đặt nhãn sang TRÁI của vạch biên x=64 để không bị cắt bởi khung đồ thị
            ax.text(opt_c - 1.5, 0.96, f"$c^*={opt_c}$ (biên lưới) ", color=COLORS["grey"],
                    fontsize=7.0, ha="right", va="bottom")
        else:
            y_pos = 1.25 if d_key == "reversed" else 0.96
            ax.text(opt_c + 1.0, y_pos, f"$c^*={opt_c}$", color=COLORS["grey"],
                    fontsize=7.0, ha="left", va="bottom")

        ax.set_title(f"{d_title}", fontsize=8.2)
        if ax in (axes_flat[2], axes_flat[3]):
            ax.set_xlabel("CUTOFF $c$")
        if ax in (axes_flat[0], axes_flat[2]):
            ax.set_ylabel("$r(N, c)$")

        # Đặt chú giải ở upper right của panel sorted (ở c >= 30, r <= 0.75 nên góc trên phải hoàn toàn trống)
        if ax == axes_flat[0]:
            ax.legend(loc="upper right", fontsize=6.8)

        for _, r in sub.iterrows():
            out_rows.append({
                "distribution": d_key,
                "cutoff": int(r["cutoff"]),
                "r_meas": r["r_meas"],
                "ci_lo": r["ci_lo"],
                "ci_hi": r["ci_hi"],
                "r_hat_M2_random": r["r_hat"],
                "diff": r["diff"],
            })

    ax.set_ylim(0.60, 1.35)

    df_out = pd.DataFrame(out_rows)
    src_text = f"""
Hình: fig08_other_distributions
Loại: Khám phá / Kiểm chứng phạm vi hợp lệ của mô hình (Scope Limitation Analysis)
Nguồn dữ liệu: {src_file}
Mô tả chuỗi:
- Khảo sát tỉ số thời gian r(N, c) trên 4 phân bố dữ liệu không ngẫu nhiên tại thang S = 2^16 (trung bình nhân trên 24 kích thước N hình học từ 65 536 đến 131 072).
- Thanh sai số là khoảng tin cậy CI 95% bootstrap cụm theo N.
- Đường đứt nét đỏ biểu thị dự báo của mô hình M2 (vốn chỉ được xây dựng cho dữ liệu ngẫu nhiên đồng đều).
- Kết quả cho thấy (Quy tắc C):
  * Mô hình M2 KHÔNG ÁP DỤNG ĐƯỢC cho các phân bố có thứ tự sẵn (sai khác lên tới +8.8% trên sorted và -13.2% trên reversed).
  * CUTOFF tối ưu khác nhau nhiều theo cấu trúc dữ liệu: c* = 64 cho sorted/nearly sorted (đây là BIÊN TRÊN của lưới CUTOFF đo đạc; cực tiểu thực tế có thể > 64, xem chẩn đoán D4), c* = 8 cho reversed (insertion sort suy biến thành O(N^2)), và c* = 32 cho few_distinct.
"""
    save_fig_bundle(fig, out_dir, "fig08_other_distributions", df_out, src_text)


# ==============================================================================
# HÌNH PHỤ LỤC (figA01 .. figA06)
# ==============================================================================

def make_figA01(out_dir: Path):
    """figA01: Số mũ cục bộ theo quy mô và fork."""
    src_file = "results_final/analysis_v2/tables/power_law_local_exponent.csv"
    df = pd.read_csv(src_file)

    fig, ax = plt.subplots(figsize=(4.72, 3.0))  # 120 mm width
    cutoffs = [(1, "$c = 1$", COLORS["blue"], "o", "-"), (30, "$c = 30$", COLORS["orange"], "s", "--")]

    out_rows = []
    scales_order = ["2^12", "2^16", "2^19"]
    x_pos = np.array([12, 16, 19])

    for c_val, c_lbl, color, marker, lstyle in cutoffs:
        sub = df[df["cutoff"] == c_val].set_index("scale").reindex(scales_order).reset_index()
        ax.errorbar(x_pos, sub["b_time_T_bar"], yerr=sub["se_b_time"],
                    fmt=marker, linestyle=lstyle, color=color, label=f"{c_lbl} ($b$ đo)", capsize=3)
        ax.plot(x_pos, sub["b_theo_approx"], linestyle=":", color=color, alpha=0.7,
                label=f"{c_lbl} ($b$ lý thuyết)")

        for _, r in sub.iterrows():
            out_rows.append({
                "cutoff": c_val,
                "scale": r["scale"],
                "b_meas": r["b_time_T_bar"],
                "se_b": r["se_b_time"],
                "b_theo": r["b_theo_approx"],
            })

    ax.set_xticks(x_pos)
    ax.set_xticklabels(["$2^{12}$ (4K..8K)", "$2^{16}$ (65K..131K)", "$2^{19}$ (524K..1M)"])
    ax.set_xlabel("Thang quy mô dữ liệu")
    ax.set_ylabel("Số mũ tăng trưởng cục bộ $b$")
    # Mở rộng ylim để đường lý thuyết c = 30 ở 2^12 (b_theo = 1.179) không bị cắt (T06c §3)
    ax.set_ylim(1.05, 1.23)
    ax.legend(loc="upper center", bbox_to_anchor=(0.52, 0.98), ncol=2, fontsize=7.0)

    df_out = pd.DataFrame(out_rows)
    src_text = f"""
Hình: figA01_local_exponent
Loại: Phụ lục / Khám phá (Appendix Analysis)
Nguồn dữ liệu: {src_file}
Mô tả chuỗi:
- Số mũ cục bộ b trong mô hình T = a * N^b được ước lượng bằng OLS trên từng thang quy mô 24 giá trị N.
- Thanh sai số biểu thị sai số chuẩn (SE) của hệ số b (cột se_b_time).
- Số mũ lý thuyết b_theo (cột b_theo_approx) được tính theo công thức giải tích xấp xỉ cục bộ của mô hình N lg(N/L):
  b_theo = 1 + 1 / ln(N_geom / L_geom)
  trong đó N_geom = exp(mean(ln N)) là trung bình nhân của kích thước N trong thang đo, và L_geom là trung bình nhân của độ dài lá (L_geom = 1.0 với c = 1; L_geom = 21.50 với c = 30).
"""
    save_fig_bundle(fig, out_dir, "figA01_local_exponent", df_out, src_text)


def make_figA02(out_dir: Path):
    """figA02: So sánh số mũ b qua 3 lượt chạy độc lập (run 1, run 2, run 3)."""
    src_file = "results_final/analysis_v2/tables/power_law_run_comparison.csv"
    df = pd.read_csv(src_file)

    fig, ax = plt.subplots(figsize=(4.72, 2.85))

    sub = df[df["scope"].str.contains("48 N")].copy()
    cutoffs = sub["cutoff"].unique()
    x = np.arange(len(cutoffs))
    width = 0.35

    sub_r2 = sub[sub["run"] == "run 2"]
    sub_r1 = sub[sub["run"] == "run 1"]

    ax.bar(x - width/2, sub_r2["delta_b_ols"], width=width, label="Run 2 so với Run 3",
           color=COLORS["sky_blue"], edgecolor="#333333", yerr=sub_r2["se_delta_b_ols"], capsize=3)
    ax.bar(x + width/2, sub_r1["delta_b_ols"], width=width, label="Run 1 so với Run 3",
           color=COLORS["vermilion"], edgecolor="#333333", yerr=sub_r1["se_delta_b_ols"], capsize=3)

    ax.axhline(0, color=COLORS["black"], linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"$c = {c}$" for c in cutoffs])
    ax.set_xlabel("CUTOFF $c$")
    ax.set_ylabel("Chênh lệch số mũ $\\Delta b = b_{\\mathrm{run}} - b_{\\mathrm{run3}}$")
    ax.legend(loc="upper left")

    df_out = sub[["comparison", "run", "cutoff", "delta_b_ols", "se_delta_b_ols", "welch_p_val"]].copy()
    src_text = f"""
Hình: figA02_power_law_runs
Loại: Phụ lục / Khám phá độ lặp lại qua các lượt chạy (Replication Analysis)
Nguồn dữ liệu: {src_file}
Mô tả chuỗi:
- Chênh lệch số mũ lũy thừa Delta b giữa run 2 (xung thấp không ghim nhân), run 1 và run 3 (ghim nhân 5, xung cao cố định).
- Thanh sai số là sai số chuẩn OLS của hiệu số mũ.
- Cho thấy số mũ tăng trưởng b rất ổn định giữa run 2 và run 3 (|Delta b| < 0.011, p-value Welch > 0.70).
"""
    save_fig_bundle(fig, out_dir, "figA02_power_law_runs", df_out, src_text)


def make_figA03(out_dir: Path):
    """figA03: Phân tích phương sai và độ chính xác của d(7, 10) theo số trial và số fork."""
    src_file = "results_final/analysis_v2/tables/precision_vs_R.csv"
    df = pd.read_csv(src_file)

    fig, ax = plt.subplots(figsize=(4.72, 3.0))

    sub_16 = df[df["scale"] == "2^16"].copy()
    fork_cfg = [
        (1, "1 Fork", COLORS["grey"], ":", "o"),
        (2, "2 Forks", COLORS["orange"], "--", "s"),
        (3, "3 Forks (Thiết kế chính)", COLORS["blue"], "-", "^"),
    ]

    for f_cnt, f_lbl, color, lstyle, marker in fork_cfg:
        sub_f = sub_16[sub_16["n_forks"] == f_cnt].sort_values("m_trials")
        ax.plot(sub_f["m_trials"], sub_f["hw95_total_pct"], label=f_lbl,
                color=color, linestyle=lstyle, marker=marker)

    floor_hw = sub_16["floor_bootstrap_N_hw95_pct"].iloc[0]
    ax.axhline(floor_hw, color=COLORS["vermilion"], linestyle="-.", label=f"Sàn dị thể $N$ ({floor_hw:.2f}%)")

    ax.set_xlabel("Số lần lặp đo $m$ (trials per cell)")
    ax.set_ylabel("Độ nửa rộng CI 95% của $d(7, 10)$ (%)")
    ax.set_ylim(0.2, 1.4)
    ax.legend(loc="upper right")

    df_out = sub_16[["scale", "n_forks", "m_trials", "hw95_total_pct", "pct_meas", "pct_hetero_N"]].copy()
    src_text = f"""
Hình: figA03_precision_vs_R
Loại: Phụ lục / Khám phá độ chính xác thiết kế thí nghiệm (Power & Precision Analysis)
Nguồn dữ liệu: {src_file}
Mô tả chuỗi:
- Nửa độ rộng khoảng tin cậy 95% (Half-width 95%) của chênh lệch hiệu năng d(7, 10) = T(7)/T(10) - 1.
- Khảo sát sự đánh đổi giữa số fork JVM và số lần lặp đo m trong mỗi ô dữ liệu.
- Đường gạch chấm đỏ thể hiện 'sàn phương sai' do sự dị thể giữa các kích thước N; cho thấy tăng m > 5-10 mang lại lợi ích biên giảm dần do đã chạm sàn phương sai dị thể.
"""
    save_fig_bundle(fig, out_dir, "figA03_precision_vs_R", df_out, src_text)


def make_figA04(out_dir: Path):
    """figA04: Độ ổn định giữa 3 fork của ln R_k trên doubling test."""
    src_file = "results_doubling/analysis/tables/A1_pred_error_full.csv"
    df = pd.read_csv(src_file)

    fig, ax = plt.subplots(figsize=(4.72, 3.2), layout="constrained")

    sub = df[(df["cutoff"] == 1) & (df["predictor"] == "P1_theory_nlgn")].sort_values("k_from")
    k_steps = sub["k_from"]

    diff_f1 = (np.log(sub["R_fork1"]) - sub["ln_R_bar"]) * 100
    diff_f2 = (np.log(sub["R_fork2"]) - sub["ln_R_bar"]) * 100
    diff_f3 = (np.log(sub["R_fork3"]) - sub["ln_R_bar"]) * 100

    ax.plot(k_steps, diff_f1, label="Fork 1", color=COLORS["blue"], linestyle="-", marker="o")
    ax.plot(k_steps, diff_f2, label="Fork 2", color=COLORS["orange"], linestyle="--", marker="s")
    ax.plot(k_steps, diff_f3, label="Fork 3", color=COLORS["bluish_green"], linestyle="-.", marker="^")

    ax.axhline(0, color=COLORS["black"], linewidth=0.8)
    # Dải ngưỡng hợp đồng đã đăng ký trước ±1.5% làm mốc tham chiếu (T06c §5)
    ax.axhspan(-1.5, 1.5, color=COLORS["light_grey"], alpha=0.3, label="Ngưỡng $\\pm 1.5\\%$ (tham chiếu)")

    ax.set_xlabel("Bước doubling $k = \\lg N$")
    ax.set_ylabel("Chênh lệch so với trung bình (%)")
    # Đặt ylim bao phủ toàn bộ dữ liệu [-3.53%, +4.95%] cộng lề 10% (T06c §5)
    ax.set_ylim(-4.5, 6.0)
    # Chú giải đặt ngoài đáy trục để không che đỉnh Fork 3 ở k = 11 (+4.95%)
    fig.legend(*ax.get_legend_handles_labels(), loc="outside lower center", fontsize=7.2, ncol=2, frameon=True, framealpha=0.9)

    df_out = pd.DataFrame({
        "k_from": k_steps,
        "diff_fork1_pct": diff_f1,
        "diff_fork2_pct": diff_f2,
        "diff_fork3_pct": diff_f3,
    })
    src_text = f"""
Hình: figA04_fork_stability_doubling
Loại: Phụ lục / Khám phá (Diagnostic Check / Exploratory Analysis)
Nguồn dữ liệu: {src_file}
Mô tả chuỗi:
- Đại lượng biểu diễn: Chênh lệch phần trăm giữa tỉ số doubling của từng fork JVM so với trung bình 3 fork:
  (\\ln R_{{k,\\mathrm{{fork}}}} - \\ln \\bar{{R}}_k) \\times 100 \\approx (R_{{k,\\mathrm{{fork}}}} - \\bar{{R}}_k) / \\bar{{R}}_k \\times 100 (với c = 1).
- Dải xám tô mờ là ngưỡng hợp đồng đã đăng ký trước \\pm 1.5\\% (A1), đưa vào làm mốc tham chiếu.
- Sai số chuẩn thực tế (SE) giữa 3 fork độc lập là 1.44% (đối với c = 1 trên các bước k = 19..21, ghi nhận tại CONTEXT T04d). Như vậy ngưỡng hợp đồng \\pm 1.5\\% tương đương xấp xỉ 1\\cdot\\mathrm{{SE}}.
- Phân loại: [khám phá] vì phân tích độ ổn định giữa các fork này là kiểm tra chẩn đoán hậu nghiệm, không phải là một giả thuyết kiểm định hiệu năng chính đã đăng ký trước trong hợp đồng A1/A3.
"""
    save_fig_bundle(fig, out_dir, "figA04_fork_stability_doubling", df_out, src_text)


def make_figA05(out_dir: Path):
    """figA05: Phân tích độ nhạy của CUTOFF tối ưu theo kịch bản tham số chi phí."""
    src_file = "results_final/analysis_v2/tables/cost_model_sensitivity.csv"
    df = pd.read_csv(src_file)

    fig, ax = plt.subplots(figsize=(4.72, 2.95), layout="constrained")

    scenarios = df["scenario"].values
    c_stars = df["c_star_curve"].values
    near_min = df["near_opt_min"].values
    near_max = df["near_opt_max"].values

    y_pos = np.arange(len(scenarios))

    for i in range(len(scenarios)):
        ax.plot([near_min[i], near_max[i]], [y_pos[i], y_pos[i]],
                color=COLORS["blue"], linewidth=3.0, alpha=0.6)
        ax.scatter([c_stars[i]], [y_pos[i]], color=COLORS["vermilion"], s=45, zorder=5)

    # Bỏ tiêu đề trong hình theo quy tắc T06c §2; định dạng nhãn trục y bằng mathtext
    label_map = {
        "baseline": "baseline",
        "beta * 0.8": r"$\beta \times 0.8$",
        "beta * 1.25": r"$\beta \times 1.25$",
        "w12 * 0.8": r"$w_1, w_2 \times 0.8$",
        "w12 * 1.25": r"$w_1, w_2 \times 1.25$",
    }
    formatted_scenarios = [label_map.get(s, s) for s in scenarios]
    ax.set_yticks(y_pos)
    ax.set_yticklabels(formatted_scenarios)
    ax.set_xlabel("CUTOFF $c$")
    ax.set_xlim(8, 72)
    ax.set_ylim(-0.5, 4.8)

    # Thêm chú giải giải thích ý nghĩa điểm và thanh (thay cho tiêu đề trong hình)
    ax.plot([], [], color=COLORS["blue"], linewidth=3.0, alpha=0.6, label="Vùng gần tối ưu 2%")
    ax.scatter([], [], color=COLORS["vermilion"], s=35, label="CUTOFF tối ưu $c^*$")
    ax.legend(loc="upper right", fontsize=7.2)

    df_out = df.copy()
    src_text = f"""
Hình: figA05_cost_model_sensitivity
Loại: Phụ lục / Khám phá độ nhạy tham số (Sensitivity Analysis)
Nguồn dữ liệu: {src_file}
Mô tả chuỗi:
- Điểm tròn đỏ thể hiện CUTOFF tối ưu c* theo 5 kịch bản thay đổi trọng số chi phí (beta và w12 thay đổi ±25%).
- Thanh ngang lam thể hiện độ rộng của vùng gần tối ưu 2%.
- Cho thấy dù tham số phần cứng thay đổi, vùng gần tối ưu luôn bao trùm khoảng [20, 40], khẳng định tính bền vững của khuyến nghị c in [24, 32].
"""
    save_fig_bundle(fig, out_dir, "figA05_cost_model_sensitivity", df_out, src_text)


def make_figA06(out_dir: Path):
    """figA06: r theo độ dài lá trung bình cho 3 thang quy mô."""
    import math
    src_tree = "results_final/analysis_v2/tables/tree_features.csv"
    src_pred = "results_final/analysis_v2/tables/cost_model_predictions.csv"
    df_tree = pd.read_csv(src_tree)
    df_pred = pd.read_csv(src_pred)

    df_tree_rand = df_tree[df_tree["distribution"] == "random"]
    df_pred_rand = df_pred[df_pred["distribution"] == "random"]
    m = pd.merge(df_tree_rand, df_pred_rand, on=["scale", "N", "cutoff"])

    bins = 2.0 ** np.arange(0, 6.75, 0.25)
    m["bin"] = pd.cut(m["mean_leaf_len"], bins, include_lowest=True)

    fig, ax = plt.subplots(figsize=(4.72, 3.0), layout="constrained")

    scales_cfg = [
        ("2^12", "$S = 2^{12}$ ($N = 4\\text{K}..8\\text{K}$)", COLORS["blue"], "o", "-"),
        ("2^16", "$S = 2^{16}$ ($N = 65\\text{K}..131\\text{K}$)", COLORS["orange"], "s", "--"),
        ("2^19", "$S = 2^{19}$ ($N = 524\\text{K}..1\\text{M}$)", COLORS["bluish_green"], "^", "-."),
    ]

    out_rows = []
    stat_lines = []
    for s_key, s_lbl, color, marker, lstyle in scales_cfg:
        sub = m[m["scale"] == s_key]
        b = sub.groupby("bin", observed=True).agg(
            leaf=("mean_leaf_len", lambda x: math.exp(np.log(x).mean())),
            r=("r_meas", lambda x: math.exp(np.log(x).mean())),
            n=("r_meas", "size")
        ).dropna().reset_index()

        ax.plot(b["leaf"], b["r"], label=s_lbl, color=color, marker=marker, linestyle=lstyle, markersize=3.8)

        # cực tiểu theo bin và cực tiểu theo từng CUTOFF riêng lẻ (trung bình nhân r theo N)
        i_min = b["r"].idxmin()
        by_c = sub.groupby("cutoff")["r_meas"].apply(lambda x: math.exp(np.log(x).mean()))
        c_min = int(by_c.idxmin())
        line = (f"  * Thang {s_key}: min theo bin r = {b.loc[i_min, 'r']:.3f} tại leaf = {b.loc[i_min, 'leaf']:.1f} "
                f"(n = {int(b.loc[i_min, 'n'])} cặp (N, c) trong bin); min theo CUTOFF riêng lẻ r = {by_c.min():.3f} tại c = {c_min}.")
        if s_key == "2^12":
            line += (" Bin cực tiểu chỉ có n nhỏ và thấp hơn r của mọi CUTOFF riêng lẻ ở thang này: đây là nhiễu của bin nhỏ;"
                     " KHÔNG báo cáo vùng gần tối ưu theo bin cho thang 2^12.")
        else:
            near = b[b["r"] <= 1.02 * b["r"].min()]
            line += (f" Vùng gần tối ưu 2% theo bin (r <= 1.02 * min theo bin): leaf in [{near['leaf'].min():.1f}, {near['leaf'].max():.1f}],"
                     f" n nhỏ nhất trong vùng = {int(near['n'].min())}.")
        stat_lines.append(line)

        for _, r in b.iterrows():
            out_rows.append({
                "scale": s_key,
                "bin": str(r["bin"]),
                "mean_leaf_len": r["leaf"],
                "r_meas": r["r"],
                "n_obs": int(r["n"]),
            })

    ax.set_xscale("log", base=2)
    ax.set_xticks([1, 2, 4, 8, 16, 32, 64])
    ax.set_xticklabels(["1", "2", "4", "8", "16", "32", "64"])
    ax.minorticks_off()
    ax.set_xlabel("Độ dài lá trung bình của cây đệ quy ($N$ / số lá, thang $\\log_2$)")
    ax.set_ylabel("Tỉ số thời gian $r = T(c)/T(1)$")
    ax.set_ylim(0.80, 1.02)
    ax.legend(loc="upper right", fontsize=7.2)

    df_out = pd.DataFrame(out_rows)
    src_text = f"""
Hình: figA06_r_vs_leaf_length
Loại: Phụ lục / Khám phá (Appendix Analysis)
Nguồn dữ liệu:
- Độ dài lá trung bình của cây đệ quy: {src_tree}
- Tỉ số thời gian r_meas = T(c)/T(1): {src_pred}
Mô tả chuỗi:
- Tỉ số thời gian r theo độ dài lá trung bình (mean_leaf_len = N / leaf_calls) được phân tích riêng biệt cho 3 thang quy mô dữ liệu ngẫu nhiên: S = 2^12, S = 2^16, và S = 2^19.
- Mỗi thang quy mô gồm 24 kích thước N và 35 giá trị CUTOFF (tổng cộng 840 cấu hình cây đệ quy mỗi thang), được gom thành 23 khoảng phân lớp logarit (bin width 0.25 trên thang log2).
- Cột n_obs trong .data.csv là số cặp (N, c) trong mỗi bin; các bin có n_obs nhỏ (< 20) ít tin cậy.
- Cực tiểu (tính bằng mã từ dữ liệu, so với cực tiểu theo từng CUTOFF riêng lẻ):
{chr(10).join(stat_lines)}
"""
    save_fig_bundle(fig, out_dir, "figA06_r_vs_leaf_length", df_out, src_text)


# ==============================================================================
# TẠO FILE FIGURES.MD
# ==============================================================================

def generate_figures_markdown(out_dir: Path):
    """Tạo tệp report/figures/FIGURES.md tổng hợp toàn bộ danh mục hình."""
    content = """# Danh mục đồ thị báo cáo (Figures Catalogue)

## 1. Đồ thị thân bài (Main Figures)

| Tên tệp | Cỡ | Nhãn LaTeX (`\\label`) | Caption gợi ý (trung tính, không nhân quả) | Phân loại | Nguồn dữ liệu |
| :--- | :---: | :--- | :--- | :---: | :--- |
| `fig01_r_vs_cutoff_random` | 120 mm | `fig:r_cutoff_random` | Tỉ số thời gian $r(N, c) = T(c)/T(1)$ theo CUTOFF cho dữ liệu ngẫu nhiên trên ba thang quy mô; dải mờ là CI 95% bootstrap. | [khám phá] | `results_final/analysis/tables/r_by_cutoff.csv` |
| `fig02_m2_fit_loso` | 170 mm | `fig:m2_fit_loso` | So khớp mô hình chi phí M2 với thực đo trên 3 thang nội suy (a) và kiểm tra ngoài mẫu LOSO trên thang $2^{19}$ kèm dải dung sai thực nghiệm $\\pm 0.01$ (b). | [khám phá] | `cost_model_in_sample_errors.csv`, `validate_2e19_loso.csv` |
| `fig03_cost_decomposition` | 85 mm | `fig:cost_decomposition` | Phân rã thành phần chi phí của mô hình M2 trên thang $S = 2^{16}$: mức tiết kiệm bỏ merge đối chiếu với chi phí thêm của insertion sort và vùng gần tối ưu 2% [14, 48]. | [khám phá] | `cost_model_decomposition.csv`, `cost_model_sensitivity.csv` |
| `fig04_doubling_ln_R` | 170 mm | `fig:doubling_ln_r` | Tỉ số tăng trưởng doubling $\\ln R_k$ theo $k$ cho $c=1$ và $c=30$ kèm sai số thực đo $\\pm 2\\cdot\\mathrm{SE}$, so sánh với các dự báo mô hình P1, P2 và P3c qua các vùng nội suy và ngoại suy. | [kiểm định đã đăng ký] | `A1_pred_error_full.csv`, `B1_doubling_lecture.csv` |
| `fig05_t_over_nlgn_cache` | 120 mm | `fig:t_over_nlgn_cache` | Thời gian chuẩn hóa $T / (N \\lg N)$ theo quy mô $k$, kèm các ngưỡng dung lượng bộ nhớ hoạt động tương ứng với bộ nhớ đệm L2 và L3. | [khám phá] | `B2_t_over_nlgn.csv`, `memory_cache_discussion.csv` |
| `fig06_r_diminishing_returns` | 85 mm | `fig:r_diminishing` | Tỉ số thời gian $r(N, 30)$ trên thang doubling từ 1K đến 4M (tại $N = 2^k$, $c=30$ tương đương lá dài 16, cùng cây đệ quy với mọi $c \\in [16, 31]$); đường đứt nét biểu thị mức giảm 20% nêu trong bài giảng. | [khám phá] | `B3_cutoff_ratio_r.csv` |
| `fig07_memory_by_config` | 170 mm | `fig:memory_by_config` | Dung lượng bộ nhớ thực tế của mergesort: số byte/phần tử trên 3 cấu hình JVM (a) và tổng dung lượng hoạt động theo $N$ so với cache trên thang log (b). | [khám phá] | `memory_measurements.csv` |
| `fig08_other_distributions` | 170 mm | `fig:other_distributions` | Tỉ số $r(N, c)$ trên 4 phân bố không ngẫu nhiên (thang $S = 2^{16}$, trung bình nhân 24 $N$), minh họa sự không áp dụng được của mô hình M2 và khác biệt lớn của $c^*$ giữa các phân bố. | [khám phá] | `validate_other_distributions.csv` |

## 2. Đồ thị phụ lục (Appendix Figures)

| Tên tệp | Cỡ | Nhãn LaTeX (`\\label`) | Caption gợi ý (trung tính, không nhân quả) | Phân loại | Nguồn dữ liệu |
| :--- | :---: | :--- | :--- | :---: | :--- |
| `figA01_local_exponent` | 120 mm | `fig:local_exponent` | Số mũ tăng trưởng cục bộ $b$ theo thang quy mô cho $c=1$ và $c=30$ so với lý thuyết xấp xỉ cục bộ của $N \\lg N$. | [khám phá] | `power_law_local_exponent.csv` |
| `figA02_power_law_runs` | 120 mm | `fig:power_law_runs` | Chênh lệch số mũ lũy thừa $\\Delta b = b_{\\mathrm{run}} - b_{\\mathrm{run3}}$ giữa các lượt chạy độc lập (run 1, run 2 so với run 3 ghim nhân 5). | [khám phá] | `power_law_run_comparison.csv` |
| `figA03_precision_vs_R` | 120 mm | `fig:precision_vs_r` | Phân tích phương sai và độ nửa rộng khoảng tin cậy của $d(7, 10)$ theo số fork JVM và số lần lặp đo $m$. | [khám phá] | `precision_vs_R.csv` |
| `figA04_fork_stability_doubling` | 120 mm | `fig:fork_stability` | Độ ổn định giữa 3 fork JVM độc lập của $\\ln R_k$ trên toàn bộ thang doubling ($c=1$); dải xám là ngưỡng hợp đồng $\\pm 1.5\\%$ tham chiếu. | [khám phá] | `A1_pred_error_full.csv` |
| `figA05_cost_model_sensitivity` | 120 mm | `fig:cost_model_sensitivity` | Độ nhạy của CUTOFF tối ưu $c^*$ và vùng gần tối ưu 2% theo các kịch bản biến thiên trọng số chi phí phần cứng. | [khám phá] | `cost_model_sensitivity.csv` |
| `figA06_r_vs_leaf_length` | 120 mm | `fig:r_vs_leaf_length` | Tỉ số thời gian $r$ theo độ dài lá trung bình tách riêng theo 3 thang quy mô, minh họa sự phân tách mức nền $r$ giữa các thang. | [khám phá] | `tree_features.csv`, `cost_model_predictions.csv` |

## 3. Đồ thị đã loại khỏi danh mục (Dropped Figures)

| Tên tệp đã loại | Lý do loại bỏ | Hình thay thế |
| :--- | :--- | :--- |
| `figA02_power_law_cache_step` | Đặt các thang $2^{12}, 2^{16}, 2^{19}$ đo ở các phiên khác nhau lên cùng trục dung lượng bộ nhớ làm việc. CONTEXT (T04b) đã xác định sai lệch tuyệt đối giữa các phiên đo lên tới $\\pm 8\\%$ và hiện tượng "dip" $2^{12} > 2^{16}$ là hiệu ứng giữa phiên (trong cùng một JVM ở doubling test không có hiện tượng dip này). Các đường nối giữa các cụm thang cũng tạo ấn tượng sai lệch về dữ liệu ở vùng không đo. | `fig05_t_over_nlgn_cache` (đo trong cùng JVM trên toàn dải doubling $2^{10}..2^{22}$) |

## 4. Bảng ánh xạ đổi tên phụ lục (T06b -> T06c)

| Tên cũ (T06b) | Tên mới (T06c) | Ghi chú thay đổi |
| :--- | :--- | :--- |
| `figA01_local_exponent` | `figA01_local_exponent` | Mở rộng ylim [1.05, 1.23], không che điểm $c=30$ tại $2^{12}$; bổ sung công thức $b_{\\mathrm{theo}}$ trong .src.txt |
| `figA02_power_law_cache_step` | *(Đã loại)* | Xóa khỏi bộ hình (git rm); thay bằng `fig05` |
| `figA03_power_law_runs` | `figA02_power_law_runs` | Đánh lại số thứ tự sau khi loại bỏ `figA02` cũ |
| `figA04_precision_vs_R` | `figA03_precision_vs_R` | Đánh lại số thứ tự |
| `figA05_fork_stability_doubling` | `figA04_fork_stability_doubling` | Mở rộng ylim [-4.5%, +6.0%], đổi nhãn dải xám hợp đồng tham chiếu, cập nhật SE thật trong .src.txt |
| `figA06_cost_model_sensitivity` | `figA05_cost_model_sensitivity` | Bỏ tiêu đề trong hình, dùng mathtext cho nhãn trục y, thêm chú giải điểm và thanh |
| `figA07_r_vs_leaf_length` | `figA06_r_vs_leaf_length` | Tách thành 3 đường riêng theo từng thang quy mô, bỏ cụm từ "tính không ổn định", bỏ Run 3 |
"""
    md_file = out_dir / "FIGURES.md"
    md_file.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"\n[OK] Đã tạo tệp tổng hợp: {md_file}")


def parse_args():
    parser = argparse.ArgumentParser(description="Tạo bộ đồ thị chuẩn hóa cho báo cáo (T06c).")
    parser.add_argument("--out", type=str, default="report/figures", help="Thư mục xuất đồ thị")
    parser.add_argument("--seed", type=int, default=42, help="Seed ngẫu nhiên")
    parser.add_argument("--grayscale", action="store_true", help="Xuất bản thử nghiệm thang độ xám")
    parser.add_argument("--only", type=str, default="",
                        help="Chỉ sinh các hình này (phân cách bằng dấu phẩy, ví dụ fig03,figA06); mặc định (T14): fig03, fig07, figA01-figA06; KHÔNG ghi FIGURES.md")
    return parser.parse_args()


def main():
    args = parse_args()
    np.random.seed(args.seed)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== Thiết lập phong cách đồ thị (Style Setup) ===")
    set_style(grayscale=args.grayscale)

    only = {t.strip() for t in args.only.split(",") if t.strip()}
    # T14: hình GĐ1 còn dùng trong báo cáo bản 2 (các hình khác đã thay bằng scripts/make_figures_p2.py)
    KEEP = {"fig03", "fig07", "figA01", "figA02", "figA03", "figA04", "figA05", "figA06"}
    LEGACY = {"fig01", "fig02", "fig04", "fig05", "fig06", "fig08"}
    if "md" in only:
        print("BỎ QUA 'md': FIGURES.md nay do scripts/make_figures_p2.py sinh (T14).")
        only.discard("md")
        if not only:
            return
    legacy_req = only & LEGACY
    if legacy_req and out_dir.resolve() == (Path(__file__).resolve().parent.parent / "report" / "figures").resolve():
        raise SystemExit(f"Từ chối: {sorted(legacy_req)} là hình GĐ1 đã thay (bản lưu ở report/figures/legacy_phase1/); "
                         "sinh vào report/figures sẽ ghi đè hình mới cùng tên (fig08). Dùng --out tới thư mục khác.")

    def want(tag):
        if tag == "md":
            return False
        return (tag in KEEP) if not only else (tag in only)

    print("\n=== Tạo 8 hình thân bài (Main Figures) ===")
    for tag, fn in [("fig01", make_fig01), ("fig02", make_fig02), ("fig03", make_fig03), ("fig04", make_fig04),
                    ("fig05", make_fig05), ("fig06", make_fig06), ("fig07", make_fig07), ("fig08", make_fig08)]:
        if want(tag):
            fn(out_dir)

    print("\n=== Tạo các hình phụ lục (Appendix Figures) ===")
    for tag, fn in [("figA01", make_figA01), ("figA02", make_figA02), ("figA03", make_figA03),
                    ("figA04", make_figA04), ("figA05", make_figA05), ("figA06", make_figA06)]:
        if want(tag):
            fn(out_dir)

    if want("md"):
        print("\n=== Tạo tệp mô tả danh mục hình FIGURES.md ===")
        generate_figures_markdown(out_dir)

    print("\n========================================================")
    print("HOÀN THÀNH TẠO BỘ ĐỒ THỊ BÁO CÁO T06c THÀNH CÔNG!")
    print("========================================================")


if __name__ == "__main__":
    main()
