#!/usr/bin/env python3
"""
cache_step_vs_smooth.py – So sánh mô hình bước nhảy cache và mô hình trơn theo ln N (T02c Phần C).

Mô hình trên 24 N của thang 2^19 (theo từng fork, c in {1, 30}):
  (a) Tuyến tính trơn: y = alpha0 + beta0 * ln N
  (b) Tuyến tính + bước: y = alpha1 + beta1 * ln N + gamma * 1{N >= 699 051}
trong đó y = T / merged_len (ns / phần tử được merge).

Cách chạy:
    python scripts/cache_step_vs_smooth.py
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

import numpy as np
import pandas as pd
from statsmodels.formula.api import ols


def compare_step_vs_smooth(
    results_dir: Path,
    counts_file: Path,
    out_file: Path,
    cutoffs: list[int],
) -> pd.DataFrame:
    dfs = []
    for f in [1, 2, 3]:
        fp = results_dir / f"raw_fork{f}.csv"
        df_f = pd.read_csv(fp)
        dfs.append(df_f)
    raw = pd.concat(dfs, ignore_index=True)
    sub19 = raw[(raw["distribution"] == "random") & (~raw["gc_during_run"]) & (raw["N"] >= 524288)].copy()

    counts = pd.read_csv(counts_file)
    counts = counts[counts["distribution"] == "random"]

    merged = pd.merge(sub19, counts[["N", "cutoff", "merged_len"]], on=["N", "cutoff"])

    grouped = merged.groupby(["fork", "cutoff", "N"]).agg(
        time_ns=("time_ns", "mean"),
        merged_len=("merged_len", "first"),
    ).reset_index()

    grouped["y"] = grouped["time_ns"] / grouped["merged_len"]
    grouped["log_N"] = np.log(grouped["N"])
    grouped["step"] = (grouped["N"] >= 699051).astype(int)

    rows = []
    print("================================================================================")
    print("cache_step_vs_smooth.py – So sánh mô hình bước nhảy cache và tuyến tính trơn")
    print("================================================================================")

    for c in cutoffs:
        print(f"\n--- Cutoff {c} (thang 2^19: N = 524 288 .. 1 018 725, ngưỡng L3 = 699 051) ---")
        for f in [1, 2, 3]:
            df_f = grouped[(grouped["cutoff"] == c) & (grouped["fork"] == f)].copy()
            mean_y = df_f["y"].mean()

            # (a) Mô hình tuyến tính trơn
            m_a = ols("y ~ log_N", data=df_f).fit()
            aic_a = m_a.aic
            slope_a = m_a.params["log_N"]
            se_slope_a = m_a.bse["log_N"]
            p_slope_a = m_a.pvalues["log_N"]
            r2_a = m_a.rsquared

            # (b) Mô hình tuyến tính + bước nhảy
            m_b = ols("y ~ log_N + step", data=df_f).fit()
            aic_b = m_b.aic
            slope_b = m_b.params["log_N"]
            se_slope_b = m_b.bse["log_N"]
            gamma = m_b.params["step"]
            se_gamma = m_b.bse["step"]
            t_gamma = m_b.tvalues["step"]
            p_gamma = m_b.pvalues["step"]
            r2_b = m_b.rsquared

            gamma_pct = (gamma / mean_y) * 100.0
            se_gamma_pct = (se_gamma / mean_y) * 100.0
            delta_aic = aic_b - aic_a  # AIC_b - AIC_a

            rows.append({
                "cutoff": c,
                "fork": f,
                "mean_y_ns_per_elem": mean_y,
                "smooth_slope": slope_a,
                "smooth_se": se_slope_a,
                "smooth_p": p_slope_a,
                "smooth_r2": r2_a,
                "smooth_aic": aic_a,
                "step_slope": slope_b,
                "step_gamma_ns": gamma,
                "step_gamma_se": se_gamma,
                "step_gamma_t": t_gamma,
                "step_gamma_p": p_gamma,
                "step_gamma_pct": gamma_pct,
                "step_gamma_pct_se": se_gamma_pct,
                "step_r2": r2_b,
                "step_aic": aic_b,
                "delta_aic": delta_aic,
                "best_model": "step" if delta_aic < -2.0 else ("smooth" if delta_aic > 2.0 else "tie (smooth parsimonious)"),
            })

            print(f"Fork {f}:")
            print(f"  TB y = {mean_y:.4f} ns/elem")
            print(f"  (a) Trơn     : slope = {slope_a:.4f} (se={se_slope_a:.4f}, p={p_slope_a:.4e}), R² = {r2_a:.4f}, AIC = {aic_a:.2f}")
            print(f"  (b) Có bước  : slope = {slope_b:.4f}, step = {gamma:+.4f} ({gamma_pct:+.2f}% ± {se_gamma_pct:.2f}%, t={t_gamma:.2f}, p={p_gamma:.4f}), R² = {r2_b:.4f}, AIC = {aic_b:.2f}")
            print(f"  Delta AIC (b - a): {delta_aic:+.2f} → {'Mô hình bước tốt hơn' if delta_aic < -2.0 else 'Không hỗ trợ mô hình bước (trơn tốt hơn hoặc tương đương)'}")

    res_df = pd.DataFrame(rows)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    res_df.to_csv(out_file, index=False)
    print()
    print(f"  → Đã lưu bảng: {out_file}")
    return res_df


def main():
    parser = argparse.ArgumentParser(
        description="cache_step_vs_smooth.py – So sánh mô hình bước nhảy cache và trơn (T02c Phần C).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results_run3"),
                        help="Thư mục raw_fork*.csv")
    parser.add_argument("--counts-file", type=Path, default=Path("results_run3/counts.csv"),
                        help="Đường dẫn counts.csv")
    parser.add_argument("--out-file", type=Path, default=Path("results_run3/analysis_v2/tables/cache_step_vs_smooth.csv"),
                        help="Đường dẫn file kết quả")
    parser.add_argument("--cutoffs", type=str, default="1,30",
                        help="Danh sách cutoffs phân tích")
    args = parser.parse_args()

    cutoffs = [int(c.strip()) for c in args.cutoffs.split(",") if c.strip()]
    compare_step_vs_smooth(args.results_dir, args.counts_file, args.out_file, cutoffs)


if __name__ == "__main__":
    main()
