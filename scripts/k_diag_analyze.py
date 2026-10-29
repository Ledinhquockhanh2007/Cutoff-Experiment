#!/usr/bin/env python3
"""
k_diag_analyze.py – Phân tích dữ liệu thực nghiệm KDiag (T02c Phần B).

Đọc results_kdiag/raw_fork*.csv và xuất:
  1. T(K) / T(1) theo (N, c) kèm khoảng tin cậy Bootstrap 95%.
  2. r(c; K) = T(c) / T(1) tại từng mức K cố định.
  3. Bảng so sánh "r tại K = 1 so với r tại K thiết kế của run 3" cho từng N.
  4. Đồ thị T(K) / T(1) theo K cho 4 cutoff (PNG + PDF).

Cách chạy:
    python scripts/k_diag_analyze.py [--results-dir results_kdiag] [--run3-dir results_run3]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Đảm bảo in UTF-8 không lỗi cp1252 trên Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Màu sắc đồ thị
INK, INK2, GRID_C, NEUTRAL = "#0b0b0b", "#52514e", "#e2e1dc", "#8d8c86"
COLORS = {1: "#2a78d6", 7: "#eb6834", 10: "#1baf7a", 30: "#7b52ab"}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Segoe UI", "Arial"],
    "figure.dpi": 100,
    "savefig.dpi": 200,
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


def load_kdiag_data(results_dir: Path) -> pd.DataFrame:
    """Nạp toàn bộ raw_fork*.csv trong results_kdiag, lọc gc_during_run == False."""
    files = sorted(results_dir.glob("raw_fork*.csv"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy raw_fork*.csv trong {results_dir}")
    dfs = []
    for f in files:
        df_k = pd.read_csv(f)
        if df_k["gc_during_run"].dtype != bool:
            df_k["gc_during_run"] = df_k["gc_during_run"].astype(str).str.lower().eq("true")
        df_k = df_k[~df_k["gc_during_run"]].copy()
        dfs.append(df_k)
    return pd.concat(dfs, ignore_index=True)


def get_run3_k_map(run3_dir: Path) -> dict[int, int]:
    """Lấy giá trị K thiết kế của run 3 cho mỗi N (lấy median qua 3 fork)."""
    if not run3_dir.exists():
        return {}
    dfs = []
    for f in [1, 2, 3]:
        fp = run3_dir / f"raw_fork{f}.csv"
        if fp.exists():
            dfs.append(pd.read_csv(fp))
    if not dfs:
        return {}
    df = pd.concat(dfs, ignore_index=True)
    df = df[df["distribution"] == "random"]
    k_map = df.groupby("N")["batch_k"].median().astype(int).to_dict()
    return k_map


def bootstrap_ci_ratio(values_num: np.ndarray, values_denom: np.ndarray, B: int = 1000, seed: int = 20261029) -> tuple[float, float, float]:
    """Tính tỉ số mean(num)/mean(denom) và CI bootstrap 95% ghép cặp theo sample."""
    n = len(values_num)
    ratio_est = float(np.mean(values_num) / np.mean(values_denom))
    if n <= 1:
        return ratio_est, ratio_est, ratio_est
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, n, size=(B, n))
    boot_ratios = np.mean(values_num[indices], axis=1) / np.mean(values_denom[indices], axis=1)
    ci_lo = float(np.percentile(boot_ratios, 2.5))
    ci_hi = float(np.percentile(boot_ratios, 97.5))
    return ratio_est, ci_lo, ci_hi


def analyze_kdiag(
    kdiag_df: pd.DataFrame,
    run3_dir: Path,
    out_dir: Path,
    B: int = 1000,
    seed: int = 20261029,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tables_dir = out_dir / "tables"
    figures_dir = out_dir / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    run3_k_map = get_run3_k_map(run3_dir)

    print("================================================================================")
    print("k_diag_analyze.py – Phân tích hiệu ứng lô batch_k từ dữ liệu KDiag")
    print(f"  Tổng số lần đo: {len(kdiag_df):,}")
    print(f"  Các kích thước N: {sorted(kdiag_df['N'].unique())}")
    print(f"  Các mức K: {sorted(kdiag_df['k'].unique())}")
    print("================================================================================")

    # 1. T(K) / T(1) theo (N, cutoff, K)
    tk_rows = []
    # Pivot dữ liệu để ghép cặp theo (fork, trial, N, cutoff)
    piv_k = kdiag_df.pivot(
        index=["fork", "trial", "N", "cutoff"],
        columns="k",
        values="time_ns",
    ).reset_index()

    for (n_val, c_val), sub in piv_k.groupby(["N", "cutoff"]):
        if 1 not in sub.columns:
            continue
        for k_val in sorted(kdiag_df["k"].unique()):
            if k_val not in sub.columns:
                continue
            if k_val == 1:
                sub_valid = sub[[1]].dropna()
                if len(sub_valid) == 0:
                    continue
                vals_k = sub_valid[1].values
                vals_1 = vals_k
                n_samples = len(sub_valid)
            else:
                pair_df = sub[[1, k_val]].dropna()
                if len(pair_df) == 0:
                    continue
                vals_1 = pair_df[1].values
                vals_k = pair_df[k_val].values
                n_samples = len(pair_df)

            ratio_est, ci_lo, ci_hi = bootstrap_ci_ratio(
                vals_k,
                vals_1,
                B=B,
                seed=seed,
            )
            pct_change = (ratio_est - 1.0) * 100.0
            tk_rows.append({
                "N": n_val,
                "cutoff": c_val,
                "k": k_val,
                "n_samples": n_samples,
                "mean_time_k_ns": float(np.mean(vals_k)),
                "mean_time_k1_ns": float(np.mean(vals_1)),
                "T_K_over_T_1": ratio_est,
                "ci95_lo": ci_lo,
                "ci95_hi": ci_hi,
                "pct_change_vs_k1": pct_change,
            })

    tk_df = pd.DataFrame(tk_rows)
    tk_csv = tables_dir / "k_effect_tk_over_t1.csv"
    tk_df.to_csv(tk_csv, index=False)
    print(f"  → Đã lưu: {tk_csv}")

    # 2. r(c; K) = T(c)/T(1) tại từng mức K cố định
    r_rows = []
    piv_c = kdiag_df.pivot(
        index=["fork", "trial", "N", "k"],
        columns="cutoff",
        values="time_ns",
    ).reset_index()

    for (n_val, k_val), sub in piv_c.groupby(["N", "k"]):
        if 1 not in sub.columns:
            continue
        for c_val in [7, 10, 30]:
            if c_val not in sub.columns:
                continue
            pair_df = sub[[1, c_val]].dropna()
            if len(pair_df) == 0:
                continue
            r_est, ci_lo, ci_hi = bootstrap_ci_ratio(
                pair_df[c_val].values,
                pair_df[1].values,
                B=B,
                seed=seed,
            )
            r_rows.append({
                "N": n_val,
                "k": k_val,
                "cutoff": c_val,
                "n_samples": len(pair_df),
                "r_c_at_k": r_est,
                "ci95_lo": ci_lo,
                "ci95_hi": ci_hi,
            })

    r_df = pd.DataFrame(r_rows)
    r_csv = tables_dir / "r_at_fixed_k.csv"
    r_df.to_csv(r_csv, index=False)
    print(f"  → Đã lưu: {r_csv}")

    # 3. Bảng so sánh: r tại K = 1 so với r tại K thiết kế của run 3
    comp_rows = []
    for n_val in sorted(kdiag_df["N"].unique()):
        k_run3 = run3_k_map.get(n_val, np.nan)
        for c_val in [7, 10, 30]:
            sub_k1 = r_df[(r_df["N"] == n_val) & (r_df["cutoff"] == c_val) & (r_df["k"] == 1)]
            r_k1 = sub_k1["r_c_at_k"].iloc[0] if len(sub_k1) > 0 else np.nan

            if not np.isnan(k_run3) and k_run3 in kdiag_df["k"].unique():
                sub_krun3 = r_df[(r_df["N"] == n_val) & (r_df["cutoff"] == c_val) & (r_df["k"] == k_run3)]
                r_krun3 = sub_krun3["r_c_at_k"].iloc[0] if len(sub_krun3) > 0 else np.nan
            else:
                r_krun3 = np.nan

            pct_diff = ((r_k1 / r_krun3) - 1.0) * 100.0 if (not np.isnan(r_k1) and not np.isnan(r_krun3) and r_krun3 > 0) else np.nan

            comp_rows.append({
                "N": n_val,
                "cutoff": c_val,
                "k_run3": k_run3,
                "r_at_k1": r_k1,
                "r_at_k_run3": r_krun3,
                "pct_diff_k1_vs_run3": pct_diff,
            })

    comp_df = pd.DataFrame(comp_rows)
    comp_csv = tables_dir / "r_k1_vs_run3.csv"
    comp_df.to_csv(comp_csv, index=False)
    print(f"  → Đã lưu: {comp_csv}")

    # 4. Vẽ đồ thị T(K)/T(1) theo K cho 4 cutoff
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)

    # Lấy N đại diện: thang 2^12 (N = min N) và thang 2^16 (nếu có)
    ns_12 = [n for n in sorted(kdiag_df["N"].unique()) if n < 10000]
    ns_16 = [n for n in sorted(kdiag_df["N"].unique()) if n >= 65536]

    rep_n12 = ns_12[0] if ns_12 else None
    rep_n16 = ns_16[0] if ns_16 else None

    # Panel 1: Thang 2^12
    ax1 = axes[0]
    if rep_n12 is not None:
        sub_n = tk_df[tk_df["N"] == rep_n12]
        for c_val in [1, 7, 10, 30]:
            sub_c = sub_n[sub_n["cutoff"] == c_val].sort_values("k")
            if len(sub_c) == 0:
                continue
            ax1.plot(sub_c["k"], sub_c["T_K_over_T_1"], marker="o", markersize=4,
                     color=COLORS.get(c_val, "#333333"), label=f"c = {c_val}")
            ax1.fill_between(sub_c["k"], sub_c["ci95_lo"], sub_c["ci95_hi"],
                             color=COLORS.get(c_val, "#333333"), alpha=0.15)
        ax1.axhline(1.0, color=NEUTRAL, linestyle="--", linewidth=1.0)
        ax1.set_xlabel("Lô đo K (batch_k)")
        ax1.set_ylabel("Tỉ số thời gian T(K) / T(1)")
        ax1.set_title(f"Thang 2^12: N = {rep_n12}")
        ax1.legend(loc="best", fontsize=8.5)

    # Panel 2: Thang 2^16
    ax2 = axes[1]
    if rep_n16 is not None:
        sub_n = tk_df[tk_df["N"] == rep_n16]
        for c_val in [1, 7, 10, 30]:
            sub_c = sub_n[sub_n["cutoff"] == c_val].sort_values("k")
            if len(sub_c) == 0:
                continue
            ax2.plot(sub_c["k"], sub_c["T_K_over_T_1"], marker="s", markersize=4,
                     color=COLORS.get(c_val, "#333333"), label=f"c = {c_val}")
            ax2.fill_between(sub_c["k"], sub_c["ci95_lo"], sub_c["ci95_hi"],
                             color=COLORS.get(c_val, "#333333"), alpha=0.15)
        ax2.axhline(1.0, color=NEUTRAL, linestyle="--", linewidth=1.0)
        ax2.set_xlabel("Lô đo K (batch_k)")
        ax2.set_title(f"Thang 2^16: N = {rep_n16}")
        ax2.legend(loc="best", fontsize=8.5)
    else:
        ax2.text(0.5, 0.5, "Chưa có dữ liệu thang 2^16\n(sẽ có sau khi chạy bản đầy đủ)",
                 ha="center", va="center", color=INK2)
        ax2.set_title("Thang 2^16 (chưa chạy)")

    fig.suptitle("Khảo sát sai lệch do lô batch_k: T(K) / T(1) theo mức K cố định", y=1.02)
    fig_png = figures_dir / "fig_k_diag_tk_over_t1.png"
    fig_pdf = figures_dir / "fig_k_diag_tk_over_t1.pdf"
    plt.savefig(fig_png)
    plt.savefig(fig_pdf)
    plt.close(fig)
    print(f"  → Đã lưu hình: {fig_png} và {fig_pdf}")

    print("Hoàn tất phân tích k_diag_analyze.py!")
    return tk_df, r_df, comp_df


def main():
    parser = argparse.ArgumentParser(
        description="k_diag_analyze.py – Phân tích dữ liệu thực nghiệm KDiag (T02c Phần B).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results_kdiag"),
                        help="Thư mục chứa raw_fork*.csv của KDiag")
    parser.add_argument("--run3-dir", type=Path, default=Path("results_run3"),
                        help="Thư mục kết quả run 3 để lấy K thiết kế")
    parser.add_argument("--out-dir", type=Path, default=Path("results_kdiag"),
                        help="Thư mục xuất bảng và hình ảnh")
    parser.add_argument("--B", type=int, default=1000,
                        help="Số mẫu bootstrap tính CI")
    parser.add_argument("--seed", type=int, default=20261029,
                        help="Seed cố định")
    args = parser.parse_args()

    np.random.seed(args.seed)
    df = load_kdiag_data(args.results_dir)
    analyze_kdiag(df, args.run3_dir, args.out_dir, B=args.B, seed=args.seed)


if __name__ == "__main__":
    main()
