#!/usr/bin/env python3
"""
k_natural_experiment.py – Phân tích thí nghiệm tự nhiên về sai lệch do lô batch_k (T02c Phần A).

Phân tích:
  1. Tái lập kết quả OLS FE bộ dữ liệu + fork trên log(T/(N lg2 N)) cho c = 1 và c = 30.
  2. Bổ sung SE cluster theo bộ dữ liệu (24 cụm N) cho c in {1, 7, 10, 30}.
  3. Phân tích biến phụ thuộc ln r = ln T(c) - ln T(1) cho c in {7, 10, 30} kèm quy đổi % đổi khi K giảm từ 8 xuống 3.
  4. Bảng mô tả N và K theo từng fork, chỉ ra 11 bộ dữ liệu có K khác nhau.

Cách chạy:
    python scripts/k_natural_experiment.py
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

# Đảm bảo in UTF-8 không lỗi cp1252 trên Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from statsmodels.formula.api import ols


def load_scale_12(results_dir: Path) -> pd.DataFrame:
    """Nạp dữ liệu random thang 2^12 (N < 32768), lọc gc_during_run == False."""
    dfs = []
    for f in [1, 2, 3]:
        fp = results_dir / f"raw_fork{f}.csv"
        df_f = pd.read_csv(fp)
        dfs.append(df_f)
    raw = pd.concat(dfs, ignore_index=True)
    sub = raw[(raw["distribution"] == "random") & (~raw["gc_during_run"]) & (raw["N"] < 32768)].copy()
    sub["nlgn"] = sub["N"] * np.log2(sub["N"])
    sub["t_norm"] = sub["time_ns"] / sub["nlgn"]
    sub["log_y"] = np.log(sub["t_norm"])
    sub["log_k"] = np.log(sub["batch_k"])
    return sub


def analyze_natural_experiment(results_dir: Path, out_file: Path) -> pd.DataFrame:
    df = load_scale_12(results_dir)

    # 1. Bảng mô tả N và K theo fork
    k_pivot = df.groupby(["N", "fork"])["batch_k"].first().unstack()
    k_pivot.columns = [f"k_fork{c}" for c in k_pivot.columns]
    k_pivot["k_diff_across_forks"] = k_pivot.nunique(axis=1) > 1
    diff_count = k_pivot["k_diff_across_forks"].sum()

    print("================================================================================")
    print("k_natural_experiment.py – Phân tích thí nghiệm tự nhiên về batch_k (T02c)")
    print("================================================================================")
    print(f"Tổng số bộ dữ liệu thang 2^12: {len(k_pivot)}")
    print(f"Số bộ dữ liệu có K khác nhau giữa các fork: {diff_count}/24")
    print()
    print("Bảng mô tả K theo từng fork (11 bộ có K khác nhau được đánh dấu *):")
    for n_val, r in k_pivot.iterrows():
        mark = "*" if r["k_diff_across_forks"] else " "
        print(f"  {mark} N={n_val:5d}: fork1={r['k_fork1']}, fork2={r['k_fork2']}, fork3={r['k_fork3']}")
    print()

    # 2. Trung bình theo (bộ dữ liệu, fork) cho từng cutoff
    grouped = df.groupby(["cutoff", "N", "fork"]).agg(
        log_y=("log_y", "mean"),
        log_k=("log_k", "first"),
        mean_log_t=("time_ns", lambda x: np.mean(np.log(x))),
        batch_k=("batch_k", "first"),
    ).reset_index()

    out_rows = []

    # Phân tích 1 & 2: y = ln(time_ns / (N lg2 N))
    print("--- 1 & 2. Hồi quy y = ln(T / (N lg2 N)) trên ln K (FE bộ dữ liệu + fork) ---")
    for c in [1, 7, 10, 30]:
        d_c = grouped[grouped["cutoff"] == c].copy()
        
        # OLS SE thường (homoskedastic)
        m_ols = ols("log_y ~ log_k + C(N) + C(fork)", data=d_c).fit()
        b_ols = m_ols.params["log_k"]
        se_ols = m_ols.bse["log_k"]
        t_ols = m_ols.tvalues["log_k"]
        p_ols = m_ols.pvalues["log_k"]

        # Cluster SE theo N (24 cụm)
        m_cl = ols("log_y ~ log_k + C(N) + C(fork)", data=d_c).fit(cov_type="cluster", cov_kwds={"groups": d_c["N"]})
        b_cl = m_cl.params["log_k"]
        se_cl = m_cl.bse["log_k"]
        t_cl = m_cl.tvalues["log_k"]
        p_cl = m_cl.pvalues["log_k"]

        # Phần trăm giảm thời gian khi nhân đôi K: (2^b - 1) * 100%
        pct_double_k = (math.pow(2.0, b_cl) - 1.0) * 100.0

        out_rows.append({
            "model_type": "y = ln(T / (N lg N))",
            "cutoff": c,
            "dep_var": "log_t_norm",
            "beta_log_k": b_cl,
            "se_ols": se_ols,
            "t_ols": t_ols,
            "p_ols": p_ols,
            "se_cluster": se_cl,
            "t_cluster": t_cl,
            "p_cluster": p_cl,
            "abs_t_ge_2_cluster": abs(t_cl) >= 2.0,
            "pct_change_double_k": pct_double_k,
            "pct_change_k8_to_k3": (math.exp(b_cl * math.log(3.0 / 8.0)) - 1.0) * 100.0,
            "ci95_k8_to_k3_lo": (math.exp((b_cl - 1.96 * se_cl) * math.log(3.0 / 8.0)) - 1.0) * 100.0,
            "ci95_k8_to_k3_hi": (math.exp((b_cl + 1.96 * se_cl) * math.log(3.0 / 8.0)) - 1.0) * 100.0,
            "conclusion": "Dấu hiệu sơ bộ (không đạt ngưỡng |t|>=2 sau khi cluster SE)" if abs(t_cl) < 2.0 else "Đạt ý nghĩa thống kê",
        })

        print(f"Cutoff {c:2d}: beta = {b_cl:.4f} | OLS SE = {se_ols:.4f} (p={p_ols:.4f}) | "
              f"Cluster SE = {se_cl:.4f} (t={t_cl:.3f}, p={p_cl:.4f}) | "
              f"nhân đôi K giảm ≈ {abs(pct_double_k):.1f}% | |t|>=2: {abs(t_cl) >= 2.0}")

    print()
    print("--- 3. Hồi quy ln r = ln T(c) - ln T(1) trên ln K (FE bộ dữ liệu + fork) ---")
    # Pivot cutoffs để tính ln r ghép cặp hoàn hảo trong cùng (N, fork, K)
    piv = grouped.pivot(index=["N", "fork", "batch_k"], columns="cutoff", values="mean_log_t").reset_index()
    piv["log_k"] = np.log(piv["batch_k"])

    for c in [7, 10, 30]:
        piv[f"log_r_{c}"] = piv[c] - piv[1]
        m_r_ols = ols(f"log_r_{c} ~ log_k + C(N) + C(fork)", data=piv).fit()
        m_r_cl = ols(f"log_r_{c} ~ log_k + C(N) + C(fork)", data=piv).fit(cov_type="cluster", cov_kwds={"groups": piv["N"]})

        b_r = m_r_cl.params["log_k"]
        se_r_ols = m_r_ols.bse["log_k"]
        p_r_ols = m_r_ols.pvalues["log_k"]
        se_r_cl = m_r_cl.bse["log_k"]
        t_r_cl = m_r_cl.tvalues["log_k"]
        p_r_cl = m_r_cl.pvalues["log_k"]

        # Quy đổi: r thay đổi bao nhiêu % khi K từ 8 xuống 3
        # delta ln r = beta * ln(3/8) -> r_ratio = exp(beta * ln(3/8))
        r_change_k8_k3 = (math.exp(b_r * math.log(3.0 / 8.0)) - 1.0) * 100.0
        ci_lo = (math.exp((b_r - 1.96 * se_r_cl) * math.log(3.0 / 8.0)) - 1.0) * 100.0
        ci_hi = (math.exp((b_r + 1.96 * se_r_cl) * math.log(3.0 / 8.0)) - 1.0) * 100.0

        out_rows.append({
            "model_type": f"ln r(c={c}) = ln T({c}) - ln T(1)",
            "cutoff": c,
            "dep_var": f"log_r_{c}",
            "beta_log_k": b_r,
            "se_ols": se_r_ols,
            "t_ols": m_r_ols.tvalues["log_k"],
            "p_ols": p_r_ols,
            "se_cluster": se_r_cl,
            "t_cluster": t_r_cl,
            "p_cluster": p_r_cl,
            "abs_t_ge_2_cluster": abs(t_r_cl) >= 2.0,
            "pct_change_double_k": (math.pow(2.0, b_r) - 1.0) * 100.0,
            "pct_change_k8_to_k3": r_change_k8_k3,
            "ci95_k8_to_k3_lo": ci_lo,
            "ci95_k8_to_k3_hi": ci_hi,
            "conclusion": "Dấu hiệu sơ bộ (không đạt ngưỡng |t|>=2 sau khi cluster SE)" if abs(t_r_cl) < 2.0 else "Đạt ý nghĩa thống kê",
        })

        print(f"Cutoff {c:2d} (ln r): beta = {b_r:.4f} | OLS SE = {se_r_ols:.4f} (p={p_r_ols:.4f}) | "
              f"Cluster SE = {se_r_cl:.4f} (t={t_r_cl:.3f}, p={p_r_cl:.4f}) | "
              f"K từ 8 xuống 3 làm r đổi {r_change_k8_k3:+.2f}% [95% CI: {ci_lo:+.2f}%, {ci_hi:+.2f}%] | |t|>=2: {abs(t_r_cl) >= 2.0}")

    out_df = pd.DataFrame(out_rows)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_file, index=False)
    print()
    print(f"  → Đã lưu bảng kết quả: {out_file}")
    return out_df


def main():
    parser = argparse.ArgumentParser(
        description="k_natural_experiment.py – Phân tích thí nghiệm tự nhiên về batch_k (T02c Phần A).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results_run3"),
                        help="Thư mục chứa raw_fork*.csv")
    parser.add_argument("--out-file", type=Path, default=Path("results_run3/analysis_v2/tables/k_natural_experiment.csv"),
                        help="Đường dẫn file CSV kết quả")
    parser.add_argument("--seed", type=int, default=20261029,
                        help="Seed cố định")
    args = parser.parse_args()

    np.random.seed(args.seed)
    analyze_natural_experiment(args.results_dir, args.out_file)


if __name__ == "__main__":
    main()
