#!/usr/bin/env python3
"""
power_law.py – Phân tích mô hình lũy thừa T = a*N^b và số mũ cục bộ (T02 / T02b):
  - B1: Khảo sát tương quan âm giữa ln a và b; bổ sung ước lượng thời gian tại các N tham chiếu
        N_ref in {5710, 65536, 91353, 730825} kèm CI 95% (delta-method).
  - B2: Đánh giá độ bất định của b theo fork (df = 2), so sánh giữa các lượt chạy bằng phép
        kiểm Welch (3 vs 3) thay vì OLS SE ảo tưởng coi 72 điểm là độc lập.
  - B3: Khảo sát tương tác fork x thang: tái tạo bảng trung bình nhân T/(N lg N) (ns) theo fork,
        số mũ cục bộ theo từng fork, và phân rã phương sai 2-way ANOVA (scale, fork, fork x scale).
  - B4: Số mũ thuật toán b_alg từ số đếm thực tế (merged_len, accesses trong counts.csv);
        tính phần vượt b_time - b_alg theo T_bar và theo từng fork.
  - B5: Phân tích ngưỡng cache theo từng fork, chuẩn hóa theo công việc thật: T / merged_len (ns),
        so sánh hai nửa N của 2^19 (< 699 051 và >= 699 051) và đối chiếu với mốc trong L3 (2^16).

Cách chạy:
    $env:PYTHONUTF8=1
    python scripts/power_law.py

Tùy chọn:
    --run3-dir <path>     thư mục kết quả run 3 (mặc định: results_run3)
    --run2-dir <path>     thư mục kết quả run 2 (mặc định: results)
    --run1-dir <path>     thư mục kết quả run 1 (mặc định: results_run1)
    --counts-file <path>  file counts.csv (mặc định: results_run3/counts.csv)
    --out-dir <path>      thư mục đầu ra (mặc định: results_run3/analysis_v2)
    --cutoffs <list>      danh sách CUTOFF (mặc định: 1,7,10,30)
    --seed <int>          seed ngẫu nhiên (mặc định: 20261029)
    --help                hiển thị trợ giúp
"""

from __future__ import annotations

import argparse
import functools
import math
import sys
from pathlib import Path

# Đảm bảo in tiếng Việt không bị lỗi cp1252 trên Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

# ──────────────────────────────────────────────────────────────── hằng số & cấu hình
SCALES = [2**12, 2**16, 2**19]
SCALE_LABELS = {2**12: "2^12", 2**16: "2^16", 2**19: "2^19"}

# Các kích thước N tham chiếu cho B1: tâm hình học của 3 thang và mốc 2^16 chung
N_REFS = [5710, 65536, 91353, 730825]
N_REF_LABELS = {
    5710: "tâm 2^12 (5710)",
    65536: "2^16 (65536)",
    91353: "tâm 2^16 (91353)",
    730825: "tâm 2^19 (730825)",
}

BYTES_PER_ELEM = 24  # 4B ref array + 4B ref aux + 16B Integer object (compressed OOPs)
CACHE_LEVELS = {
    "L2": (1 * 1024 * 1024, 1 * 1024 * 1024 / BYTES_PER_ELEM),    # 1 MB / nhân -> N ≈ 43 691
    "L3": (16 * 1024 * 1024, 16 * 1024 * 1024 / BYTES_PER_ELEM),  # 16 MB dùng chung -> N ≈ 699 051
}

# Màu sắc & giao diện
INK, INK2, GRID_C, NEUTRAL = "#0b0b0b", "#52514e", "#e2e1dc", "#8d8c86"
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


# ──────────────────────────────────────────────────────────────── hàm tính độ dài lá lý thuyết
@functools.lru_cache(maxsize=None)
def mean_leaf_length(n: int, c: int) -> float:
    """Độ dài lá trung bình của cây mergesort top-down với mảng kích thước n và cutoff c."""
    @functools.lru_cache(maxsize=None)
    def leaves(m: int) -> int:
        return 1 if m <= c else leaves((m + 1) // 2) + leaves(m // 2)
    return n / leaves(n)


def scale_of(n: int) -> str:
    """Xác định thang kích thước dựa trên N."""
    if n < 10000:
        return "2^12"
    elif n < 200000:
        return "2^16"
    else:
        return "2^19"


# ──────────────────────────────────────────────────────────────── tải và tiền xử lý dữ liệu
def load_run_data(run_dir: Path, run_label: str) -> pd.DataFrame:
    """
    Tải toàn bộ raw_fork*.csv trong thư mục run.
    Lọc: distribution == 'random' và gc_during_run == False.
    QUY ƯỚC QUAN TRỌNG: cột time_ns trong CSV gốc ĐÃ LÀ thời gian một lần sắp (chia k sẵn).
    """
    raw_files = sorted(run_dir.glob("raw_fork*.csv"))
    if not raw_files:
        raise FileNotFoundError(f"Không tìm thấy raw_fork*.csv trong {run_dir}")

    dfs = []
    for f in raw_files:
        df_k = pd.read_csv(f)
        dfs.append(df_k)
    raw = pd.concat(dfs, ignore_index=True)

    if raw["gc_during_run"].dtype != bool:
        raw["gc_during_run"] = raw["gc_during_run"].astype(str).str.lower().eq("true")

    sub = raw[(raw["distribution"] == "random") & (~raw["gc_during_run"])].copy()
    sub["run"] = run_label
    sub["scale"] = sub["N"].map(scale_of)
    sub["log_t"] = np.log(sub["time_ns"].astype(float))
    return sub


def load_counts_data(counts_file: Path) -> pd.DataFrame:
    """Tải và lọc dữ liệu counts.csv cho distribution == 'random'."""
    if not counts_file.exists():
        raise FileNotFoundError(f"Không tìm thấy {counts_file}")
    df_c = pd.read_csv(counts_file)
    sub = df_c[df_c["distribution"] == "random"].copy()
    sub["scale"] = sub["N"].map(scale_of)
    return sub


def compute_t_bar_per_n(df: pd.DataFrame, cutoff: int) -> pd.DataFrame:
    """
    Tính T_bar(N) = trung bình nhân của t trên mọi fork và trial cho một cutoff.
    ln(T_bar) = mean(log_t).
    """
    sub = df[df["cutoff"] == cutoff]
    grouped = sub.groupby("N").agg(
        n_obs=("time_ns", "count"),
        mean_log_t=("log_t", "mean")
    ).reset_index()
    grouped["T_bar_ns"] = np.exp(grouped["mean_log_t"])
    grouped["T_bar_ms"] = grouped["T_bar_ns"] / 1e6
    grouped["scale"] = grouped["N"].map(scale_of)
    return grouped.sort_values("N").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────── B1: Hồi quy OLS và tương quan a–b
def fit_power_law_ols(log_N: np.ndarray, log_T: np.ndarray) -> dict:
    """
    Hồi quy OLS: log_T = intercept + b * log_N.
    Bổ sung B1:
      - corr(ln a, b) từ ma trận hiệp phương sai OLS.
      - T_hat(N_ref) = a * N_ref^b kèm SE và CI 95% theo delta-method.
    """
    n = len(log_N)
    df = n - 2
    lr = stats.linregress(log_N, log_T)
    tcrit = stats.t.ppf(0.975, df=df)

    b = lr.slope
    se_b = lr.stderr
    ci_b_lo = b - tcrit * se_b
    ci_b_hi = b + tcrit * se_b

    log_a = lr.intercept
    se_log_a = lr.intercept_stderr
    a_ns = math.exp(log_a)
    ci_a_lo = math.exp(log_a - tcrit * se_log_a)
    ci_a_hi = math.exp(log_a + tcrit * se_log_a)

    pred_log_T = log_a + b * log_N
    residuals = log_T - pred_log_T
    rel_residuals = np.exp(residuals) - 1.0  # (T_obs - T_pred) / T_pred
    max_abs_rel_res_pct = float(np.max(np.abs(rel_residuals)) * 100.0)

    # Hiệp phương sai và tương quan giữa ln a và b (B1)
    x_bar = float(np.mean(log_N))
    S_xx = float(np.sum((log_N - x_bar) ** 2))
    s2 = float(np.sum(residuals ** 2) / df)
    var_b = s2 / S_xx
    var_log_a = s2 * float(np.sum(log_N ** 2)) / (n * S_xx)
    cov_log_a_b = -s2 * x_bar / S_xx
    corr_log_a_b = cov_log_a_b / math.sqrt(var_log_a * var_b)

    # Ước lượng T_hat tại các N tham chiếu (B1)
    t_refs = {}
    for nr in N_REFS:
        ln_nr = math.log(nr)
        y_hat = log_a + b * ln_nr
        var_y = s2 * (1.0 / n + (ln_nr - x_bar) ** 2 / S_xx)
        se_y = math.sqrt(var_y)
        t_refs[nr] = {
            "y_hat": y_hat,
            "se_y": se_y,
            "T_hat_ns": math.exp(y_hat),
            "ci_T_lo_ns": math.exp(y_hat - tcrit * se_y),
            "ci_T_hi_ns": math.exp(y_hat + tcrit * se_y),
            "T_hat_ms": math.exp(y_hat) / 1e6,
            "ci_T_lo_ms": math.exp(y_hat - tcrit * se_y) / 1e6,
            "ci_T_hi_ms": math.exp(y_hat + tcrit * se_y) / 1e6,
        }

    return {
        "n_N": n,
        "df": df,
        "b": b,
        "se_b": se_b,
        "ci_b_lo": ci_b_lo,
        "ci_b_hi": ci_b_hi,
        "log_a": log_a,
        "se_log_a": se_log_a,
        "a_ns": a_ns,
        "ci_a_lo": ci_a_lo,
        "ci_a_hi": ci_a_hi,
        "R2": lr.rvalue ** 2,
        "max_abs_rel_res_pct": max_abs_rel_res_pct,
        "rel_residuals": rel_residuals,
        "pred_log_T": pred_log_T,
        "x_bar": x_bar,
        "S_xx": S_xx,
        "s2": s2,
        "corr_log_a_b": corr_log_a_b,
        "t_refs": t_refs,
    }


# ──────────────────────────────────────────────────────────────── B1 & B2: So sánh lượt chạy
def compare_two_runs(
    fit_run: dict,
    fit_ref: dict,
    fork_bs_run: np.ndarray,
    fork_bs_ref: np.ndarray,
) -> dict:
    """
    So sánh hai mô hình hồi quy (run vs run 3):
      - delta_b = b_run - b_ref kèm SE và CI 95% (df = df1 + df2 = 140).
      - ratio_a = a_run / a_ref kèm SE_log và CI 95%.
      - B1: tỉ số thời gian T_hat tại các N tham chiếu N_ref in {5710, 65536, 91353, 730825} kèm CI 95%.
      - B2: Thống kê b theo 3 fork và phép kiểm Welch (3 vs 3, không dùng SE OLS).
    """
    df_pooled = fit_run["df"] + fit_ref["df"]
    tcrit = stats.t.ppf(0.975, df=df_pooled)

    delta_b = fit_run["b"] - fit_ref["b"]
    se_delta_b = math.sqrt(fit_run["se_b"]**2 + fit_ref["se_b"]**2)
    ci_delta_b_lo = delta_b - tcrit * se_delta_b
    ci_delta_b_hi = delta_b + tcrit * se_delta_b

    diff_log_a = fit_run["log_a"] - fit_ref["log_a"]
    se_diff_log_a = math.sqrt(fit_run["se_log_a"]**2 + fit_ref["se_log_a"]**2)
    ratio_a = math.exp(diff_log_a)
    ci_ratio_a_lo = math.exp(diff_log_a - tcrit * se_diff_log_a)
    ci_ratio_a_hi = math.exp(diff_log_a + tcrit * se_diff_log_a)

    # B1: Tỉ số thời gian T_hat tại các N tham chiếu
    ratio_refs = {}
    for nr in N_REFS:
        ln_nr = math.log(nr)
        var_y_run = fit_run["s2"] * (1.0 / fit_run["n_N"] + (ln_nr - fit_run["x_bar"])**2 / fit_run["S_xx"])
        var_y_ref = fit_ref["s2"] * (1.0 / fit_ref["n_N"] + (ln_nr - fit_ref["x_bar"])**2 / fit_ref["S_xx"])
        diff_y = (fit_run["log_a"] + fit_run["b"] * ln_nr) - (fit_ref["log_a"] + fit_ref["b"] * ln_nr)
        se_diff_y = math.sqrt(var_y_run + var_y_ref)
        ratio_refs[nr] = {
            "ratio": math.exp(diff_y),
            "ci_lo": math.exp(diff_y - tcrit * se_diff_y),
            "ci_hi": math.exp(diff_y + tcrit * se_diff_y),
        }

    # B2: Thống kê b theo 3 fork và kiểm Welch
    tcrit_df2 = stats.t.ppf(0.975, df=2)
    m_run = float(np.mean(fork_bs_run))
    sd_run = float(np.std(fork_bs_run, ddof=1))
    se_run = sd_run / math.sqrt(len(fork_bs_run))
    ci_run_lo = m_run - tcrit_df2 * se_run
    ci_run_hi = m_run + tcrit_df2 * se_run

    m_ref = float(np.mean(fork_bs_ref))
    sd_ref = float(np.std(fork_bs_ref, ddof=1))
    se_ref = sd_ref / math.sqrt(len(fork_bs_ref))
    ci_ref_lo = m_ref - tcrit_df2 * se_ref
    ci_ref_hi = m_ref + tcrit_df2 * se_ref

    welch = stats.ttest_ind(fork_bs_run, fork_bs_ref, equal_var=False)

    return {
        "delta_b": delta_b,
        "se_delta_b": se_delta_b,
        "ci_delta_b_lo": ci_delta_b_lo,
        "ci_delta_b_hi": ci_delta_b_hi,
        "ratio_a": ratio_a,
        "se_diff_log_a": se_diff_log_a,
        "ci_ratio_a_lo": ci_ratio_a_lo,
        "ci_ratio_a_hi": ci_ratio_a_hi,
        "ratio_refs": ratio_refs,
        "b_mean_run": m_run,
        "b_sd_run": sd_run,
        "ci95_b_run_lo": ci_run_lo,
        "ci95_b_run_hi": ci_run_hi,
        "b_mean_ref": m_ref,
        "b_sd_ref": sd_ref,
        "ci95_b_ref_lo": ci_ref_lo,
        "ci95_b_ref_hi": ci_ref_hi,
        "welch_t_stat": float(welch.statistic),
        "welch_p_val": float(welch.pvalue),
        "welch_df": float(welch.df),
        "welch_sig": bool(welch.pvalue < 0.05),
    }


# ──────────────────────────────────────────────────────────────── B3: Tương tác Fork × Thang
def compute_fork_scale_interaction(df_run3: pd.DataFrame, cutoffs: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    B3: Khảo sát tương tác fork x thang trên run 3:
      (i) Bảng trung bình nhân của T/(N lg N) (ns) theo (scale, fork) và tỉ số với trung bình 3 fork.
      (ii) Bảng số mũ cục bộ b theo từng fork (3 fork x 3 thang) và SD giữa fork.
      (iii) Phân rã phương sai 2-way ANOVA của ln(T / (N lg N)) theo scale, fork, fork x scale.
    """
    df_calc = df_run3.copy()
    df_calc["nlgn"] = df_calc["N"] * np.log2(df_calc["N"])
    df_calc["t_per_nlgn"] = df_calc["time_ns"] / df_calc["nlgn"]

    table_rows = []
    anova_rows = []

    for c in cutoffs:
        sub_c = df_calc[df_calc["cutoff"] == c]

        # (i) & (ii) Tính theo từng thang (chỉ 2^16 và 2^19 theo T03-0)
        for sname in ["2^16", "2^19"]:
            sub_s = sub_c[sub_c["scale"] == sname]

            gm_forks = []
            b_forks = []
            for f in [1, 2, 3]:
                sub_fs = sub_s[sub_s["fork"] == f]
                # Trung bình nhân của T / (N lg N)
                gm = float(np.exp(np.mean(np.log(sub_fs["t_per_nlgn"]))))
                gm_forks.append(gm)

                # Hồi quy số mũ cục bộ của riêng fork f trên 24 N
                t_bar_f = sub_fs.groupby("N")["time_ns"].apply(lambda x: np.exp(np.mean(np.log(x)))).reset_index()
                lr_f = stats.linregress(np.log(t_bar_f["N"].values), np.log(t_bar_f["time_ns"].values))
                b_forks.append(float(lr_f.slope))

            mean_3f = float(np.mean(gm_forks))
            ratios = [gm / mean_3f for gm in gm_forks]
            sd_b_forks = float(np.std(b_forks, ddof=1))
            mean_b_forks = float(np.mean(b_forks))

            table_rows.append({
                "cutoff": c,
                "scale": sname,
                "geom_mean_T_per_NlgN_fork1_ns": gm_forks[0],
                "geom_mean_T_per_NlgN_fork2_ns": gm_forks[1],
                "geom_mean_T_per_NlgN_fork3_ns": gm_forks[2],
                "geom_mean_T_per_NlgN_3fork_mean_ns": mean_3f,
                "ratio_to_mean_fork1": ratios[0],
                "ratio_to_mean_fork2": ratios[1],
                "ratio_to_mean_fork3": ratios[2],
                "local_b_fork1": b_forks[0],
                "local_b_fork2": b_forks[1],
                "local_b_fork3": b_forks[2],
                "local_b_3fork_mean": mean_b_forks,
                "local_b_3fork_sd": sd_b_forks,
            })

        # (iii) Phân rã phương sai 2-way ANOVA trên 48 N x 3 forks = 144 điểm của cutoff c (chỉ 2^16 + 2^19)
        sub_c_scales = sub_c[sub_c["scale"].isin(["2^16", "2^19"])]
        t_bar_cells = sub_c_scales.groupby(["fork", "N", "scale"])["time_ns"].apply(
            lambda x: np.exp(np.mean(np.log(x)))
        ).reset_index()
        t_bar_cells["log_t_norm"] = np.log(t_bar_cells["time_ns"]) - np.log(t_bar_cells["N"] * np.log2(t_bar_cells["N"]))

        y = t_bar_cells["log_t_norm"].values
        gm_y = float(np.mean(y))
        ss_tot = float(np.sum((y - gm_y)**2))

        scale_means = t_bar_cells.groupby("scale")["log_t_norm"].transform("mean").values
        ss_scale = float(np.sum((scale_means - gm_y)**2))

        fork_means = t_bar_cells.groupby("fork")["log_t_norm"].transform("mean").values
        ss_fork = float(np.sum((fork_means - gm_y)**2))

        cell_means = t_bar_cells.groupby(["fork", "scale"])["log_t_norm"].transform("mean").values
        ss_cells = float(np.sum((cell_means - gm_y)**2))
        ss_inter = float(ss_cells - ss_scale - ss_fork)
        ss_within = float(np.sum((y - cell_means)**2))

        df_tot = len(y) - 1            # 143
        df_scale = 2 - 1               # 1
        df_fork = 3 - 1                # 2
        df_inter = (2 - 1) * (3 - 1)   # 2
        df_within = 6 * (24 - 1)       # 138

        ms_within = ss_within / df_within
        ms_scale = ss_scale / df_scale
        ms_fork = ss_fork / df_fork
        ms_inter = ss_inter / df_inter

        f_scale = ms_scale / ms_within
        f_fork = ms_fork / ms_within
        f_inter = ms_inter / ms_within

        p_scale = float(stats.f.sf(f_scale, df_scale, df_within))
        p_fork = float(stats.f.sf(f_fork, df_fork, df_within))
        p_inter = float(stats.f.sf(f_inter, df_inter, df_within))

        for factor, ss_k, df_k, ms_k, f_k, p_k in [
            ("scale", ss_scale, df_scale, ms_scale, f_scale, p_scale),
            ("fork", ss_fork, df_fork, ms_fork, f_fork, p_fork),
            ("fork_x_scale", ss_inter, df_inter, ms_inter, f_inter, p_inter),
            ("within_cell (N)", ss_within, df_within, ms_within, np.nan, np.nan),
            ("total", ss_tot, df_tot, ss_tot / df_tot, np.nan, np.nan),
        ]:
            anova_rows.append({
                "cutoff": c,
                "source": factor,
                "df": df_k,
                "sum_sq": ss_k,
                "mean_sq": ms_k,
                "F": f_k,
                "p_val": p_k,
                "pct_variance": (ss_k / ss_tot) * 100.0,
            })

    return pd.DataFrame(table_rows), pd.DataFrame(anova_rows)


# ──────────────────────────────────────────────────────────────── B4: Số mũ thuật toán từ counts.csv
def compute_algorithmic_exponents(
    df_run3: pd.DataFrame,
    counts_df: pd.DataFrame,
    cutoffs: list[int],
) -> pd.DataFrame:
    """
    B4: Khảo sát số mũ lý thuyết từ số đếm thực tế (counts.csv) trên 24 N của từng thang:
      - Hồi quy ln(merged_len) theo ln N -> b_merged_len
      - Hồi quy ln(accesses) theo ln N -> b_accesses
      - Đo b_time trên T_bar và trên từng fork riêng
      - Tính phần vượt b_time - b_alg
    """
    rows = []
    for c in cutoffs:
        sub_cnt = counts_df[counts_df["cutoff"] == c]
        t_bar_df = compute_t_bar_per_n(df_run3, c)
        sub_raw = df_run3[df_run3["cutoff"] == c]

        for sname in ["2^12", "2^16", "2^19"]:
            # Dữ liệu đếm
            sub_cnt_s = sub_cnt[sub_cnt["scale"] == sname].sort_values("N")
            log_N = np.log(sub_cnt_s["N"].values)
            log_ml = np.log(sub_cnt_s["merged_len"].values)
            log_acc = np.log(sub_cnt_s["accesses"].values)

            reg_ml = stats.linregress(log_N, log_ml)
            reg_acc = stats.linregress(log_N, log_acc)

            b_ml = float(reg_ml.slope)
            b_acc = float(reg_acc.slope)

            # Lý thuyết xấp xỉ 1 + 1/ln(N/L)
            N_geom = float(np.exp(np.mean(log_N)))
            if c == 1:
                L_geom = 1.0
            else:
                leaf_lens = [mean_leaf_length(int(n), c) for n in sub_cnt_s["N"]]
                L_geom = float(np.exp(np.mean(np.log(leaf_lens))))
            b_theo_approx = 1.0 + 1.0 / math.log(N_geom / L_geom)

            # Thực đo thời gian trên T_bar gộp
            sub_t = t_bar_df[t_bar_df["scale"] == sname]
            fit_time = fit_power_law_ols(np.log(sub_t["N"].values), sub_t["mean_log_t"].values)
            b_time = fit_time["b"]

            # Thực đo thời gian theo từng fork
            b_forks = []
            for f in [1, 2, 3]:
                sub_f = sub_raw[(sub_raw["scale"] == sname) & (sub_raw["fork"] == f)]
                t_f = sub_f.groupby("N")["time_ns"].apply(lambda x: np.exp(np.mean(np.log(x)))).reset_index()
                lr_f = stats.linregress(np.log(t_f["N"].values), np.log(t_f["time_ns"].values))
                b_forks.append(float(lr_f.slope))

            note = "dai N hep (he so 1.94); JVM khac voi cac thang con lai" if sname == "2^12" else ""

            rows.append({
                "cutoff": c,
                "scale": sname,
                "note": note,
                "N_min": int(sub_cnt_s["N"].min()),
                "N_max": int(sub_cnt_s["N"].max()),
                "N_geom": N_geom,
                "L_geom": L_geom,
                "b_theo_approx": b_theo_approx,
                "b_merged_len": b_ml,
                "R2_merged_len": reg_ml.rvalue**2,
                "b_accesses": b_acc,
                "R2_accesses": reg_acc.rvalue**2,
                "b_time_T_bar": b_time,
                "se_b_time": fit_time["se_b"],
                "ci_b_time_lo": fit_time["ci_b_lo"],
                "ci_b_time_hi": fit_time["ci_b_hi"],
                "excess_vs_theo_approx": b_time - b_theo_approx,
                "excess_vs_merged_len": b_time - b_ml,
                "excess_vs_accesses": b_time - b_acc,
                "b_time_fork1": b_forks[0],
                "b_time_fork2": b_forks[1],
                "b_time_fork3": b_forks[2],
                "b_time_sd_between_forks": float(np.std(b_forks, ddof=1)),
                "excess_acc_fork1": b_forks[0] - b_acc,
                "excess_acc_fork2": b_forks[1] - b_acc,
                "excess_acc_fork3": b_forks[2] - b_acc,
                "excess_ml_fork1": b_forks[0] - b_ml,
                "excess_ml_fork2": b_forks[1] - b_ml,
                "excess_ml_fork3": b_forks[2] - b_ml,
            })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────── B5: Bậc cache tách khỏi thuật toán và fork
def compute_cache_step_by_fork(
    df_run3: pd.DataFrame,
    counts_df: pd.DataFrame,
    cutoffs: list[int],
) -> pd.DataFrame:
    """
    B5: Khảo sát bậc hiệu năng bộ nhớ đệm theo từng fork:
      - Chuẩn hóa theo công việc thật: T / merged_len (ns / phần tử được merge).
      - Chia thang 2^19 theo N < 699 051 và N >= 699 051 (ngưỡng 16 MB L3 cache).
      - Đặt thang 2^16 làm mốc cơ sở (hoàn toàn nằm trong L3, working set 1.5 - 3 MB).
      - Tính tỉ lệ bước nhảy trong 2^19 (>= L3 / < L3) và tỉ lệ so với 2^16.
    """
    merged = pd.merge(
        df_run3,
        counts_df[["N", "cutoff", "merged_len", "accesses"]],
        on=["N", "cutoff"],
    )
    merged["T_per_merged_len_ns"] = merged["time_ns"] / merged["merged_len"]

    def region_of(row):
        if row["scale"] == "2^12":
            return "2^12"
        elif row["scale"] == "2^16":
            return "2^16"
        elif row["N"] < CACHE_LEVELS["L3"][1]:
            return "2^19_below_L3"
        else:
            return "2^19_above_L3"

    merged["cache_split_region"] = merged.apply(region_of, axis=1)

    rows = []
    for c in cutoffs:
        sub_c = merged[merged["cutoff"] == c]
        for f in [1, 2, 3]:
            sub_f = sub_c[sub_c["fork"] == f]

            m16 = float(sub_f[sub_f["cache_split_region"] == "2^16"]["T_per_merged_len_ns"].mean())
            m19_low = float(sub_f[sub_f["cache_split_region"] == "2^19_below_L3"]["T_per_merged_len_ns"].mean())
            m19_high = float(sub_f[sub_f["cache_split_region"] == "2^19_above_L3"]["T_per_merged_len_ns"].mean())

            step_ratio = m19_high / m19_low
            step_pct = (step_ratio - 1.0) * 100.0
            ratio_vs_16 = m19_high / m16
            pct_vs_16 = (ratio_vs_16 - 1.0) * 100.0

            rows.append({
                "cutoff": c,
                "fork": f,
                "ns_per_merged_2^16": m16,
                "ns_per_merged_2^19_below_L3": m19_low,
                "ns_per_merged_2^19_above_L3": m19_high,
                "step_ratio_within_2^19": step_ratio,
                "step_pct_within_2^19": step_pct,
                "ratio_vs_2^16": ratio_vs_16,
                "pct_vs_2^16": pct_vs_16,
            })

        # Hàng trung bình 3 fork
        m16_all = float(sub_c[sub_c["cache_split_region"] == "2^16"]["T_per_merged_len_ns"].mean())
        m19_low_all = float(sub_c[sub_c["cache_split_region"] == "2^19_below_L3"]["T_per_merged_len_ns"].mean())
        m19_high_all = float(sub_c[sub_c["cache_split_region"] == "2^19_above_L3"]["T_per_merged_len_ns"].mean())
        step_all = m19_high_all / m19_low_all
        step_all_pct = (step_all - 1.0) * 100.0
        vs16_all = m19_high_all / m16_all
        vs16_all_pct = (vs16_all - 1.0) * 100.0

        rows.append({
            "cutoff": c,
            "fork": "mean_3forks",
            "ns_per_merged_2^16": m16_all,
            "ns_per_merged_2^19_below_L3": m19_low_all,
            "ns_per_merged_2^19_above_L3": m19_high_all,
            "step_ratio_within_2^19": step_all,
            "step_pct_within_2^19": step_all_pct,
            "ratio_vs_2^16": vs16_all,
            "pct_vs_2^16": vs16_all_pct,
        })

    return pd.DataFrame(rows)


def compute_cache_step_analysis(df_run3: pd.DataFrame, counts_df: pd.DataFrame) -> pd.DataFrame:
    """
    Tính T_bar / (N lg N) và T_bar / merged_len theo N cho c=1 và c=30 của run 3 trên 72 N.
    """
    t1 = compute_t_bar_per_n(df_run3, 1).rename(
        columns={"T_bar_ns": "T_c1_ns", "T_bar_ms": "T_c1_ms"}
    )
    t30 = compute_t_bar_per_n(df_run3, 30).rename(
        columns={"T_bar_ns": "T_c30_ns", "T_bar_ms": "T_c30_ms"}
    )

    merged = pd.merge(t1[["N", "scale", "T_c1_ns", "T_c1_ms"]],
                      t30[["N", "T_c30_ns", "T_c30_ms"]], on="N")

    merged["working_set_bytes"] = merged["N"] * BYTES_PER_ELEM
    merged["working_set_MiB"] = merged["working_set_bytes"] / (1024 * 1024)

    # N lg N
    n_lg_n = merged["N"] * np.log2(merged["N"])
    merged["T_c1_per_NlgN_ns"] = merged["T_c1_ns"] / n_lg_n
    merged["T_c30_per_NlgN_ns"] = merged["T_c30_ns"] / n_lg_n
    merged["ratio_c30_over_c1"] = merged["T_c30_ns"] / merged["T_c1_ns"]

    # Bổ sung merged_len từ counts_df
    cnt1 = counts_df[counts_df["cutoff"] == 1][["N", "merged_len"]].rename(columns={"merged_len": "merged_len_c1"})
    cnt30 = counts_df[counts_df["cutoff"] == 30][["N", "merged_len"]].rename(columns={"merged_len": "merged_len_c30"})

    merged = pd.merge(merged, cnt1, on="N", how="left")
    merged = pd.merge(merged, cnt30, on="N", how="left")

    merged["T_c1_per_merged_ns"] = merged["T_c1_ns"] / merged["merged_len_c1"]
    merged["T_c30_per_merged_ns"] = merged["T_c30_ns"] / merged["merged_len_c30"]

    # Vùng cache
    merged["cache_region"] = np.where(
        merged["N"] < CACHE_LEVELS["L2"][1], "< L2 (1 MB)",
        np.where(merged["N"] < CACHE_LEVELS["L3"][1], "L2 – L3 (1–16 MB)", "> L3 (16 MB)")
    )
    return merged.sort_values("N").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────── vẽ đồ thị
def plot_power_law_runs(fits_dict: dict, t_bars_dict: dict, out_dir: Path, primary_label: str = "run 3 (ghim nhân 5)"):
    """Hình 1: Đồ thị log-log T_bar theo N cho các lượt chạy (c=1)."""
    fig, ax = plt.subplots(figsize=(6.4, 4.2))

    run_styles = {
        primary_label: {"color": "#2a78d6", "marker": "o", "label": f"{primary_label}: đo"},
        "run 3 (ghim nhân 5)": {"color": "#2a78d6", "marker": "o", "label": "run 3 (ghim nhân 5, nhanh)"},
        "run 2": {"color": "#eb6834", "marker": "s", "label": "run 2 (không ghim, chậm)"},
        "run 1": {"color": "#1baf7a", "marker": "^", "label": "run 1 (không ghim, chậm)"},
    }

    xs_fit = np.geomspace(4096, 1018725, 100)

    for rname, style in run_styles.items():
        if rname not in t_bars_dict or 1 not in t_bars_dict[rname]:
            continue
        t_bar = t_bars_dict[rname][1]
        fit = fits_dict[rname][1]

        ax.plot(t_bar["N"], t_bar["T_bar_ms"], linestyle="none",
                marker=style["marker"], markersize=4, color=style["color"],
                alpha=0.85, label=f"{style['label']}: đo")

        pred_ms = (fit["a_ns"] * (xs_fit ** fit["b"])) / 1e6
        ax.plot(xs_fit, pred_ms, linestyle="-", linewidth=1.4, color=style["color"],
                label=f"  → T ≈ {fit['a_ns']:.2f}·N^{fit['b']:.3f} ns (R²={fit['R2']:.4f})")

    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("Kích thước mảng N (thang log₂)")
    ax.set_ylabel("Thời gian một lần sắp T (ms, thang log)")
    ax.set_title("Quy luật lũy thừa T = a·N^b qua 3 lượt chạy (c = 1, random)")
    ax.legend(loc="upper left", fontsize=8.0)

    fig_png = out_dir / "figures" / "fig_power_law_runs.png"
    fig_pdf = out_dir / "figures" / "fig_power_law_runs.pdf"
    plt.savefig(fig_png)
    plt.savefig(fig_pdf)
    plt.close(fig)
    print(f"  Đã lưu hình 1: {fig_png} và {fig_pdf}")


def plot_local_exponents(alg_df: pd.DataFrame, out_dir: Path):
    """Hình 2: Số mũ cục bộ b theo thang so với lý thuyết và số đếm thuật toán."""
    fig, ax = plt.subplots(figsize=(6.4, 3.8))

    scale_order = ["2^12", "2^16", "2^19"]
    x_pos = np.arange(len(scale_order))
    width = 0.20

    # c = 1
    sub1 = alg_df[alg_df["cutoff"] == 1].set_index("scale").loc[scale_order].reset_index()
    y_err1 = [sub1["b_time_T_bar"] - sub1["ci_b_time_lo"], sub1["ci_b_time_hi"] - sub1["b_time_T_bar"]]

    ax.errorbar(x_pos - width, sub1["b_time_T_bar"], yerr=y_err1, fmt="o", color="#2a78d6",
                capsize=3.5, elinewidth=1.2, markersize=5, label="c = 1: đo T (CI 95%)")
    ax.plot(x_pos - width, sub1["b_merged_len"], marker="x", markersize=6, linestyle="--",
            color="#1b4f8a", linewidth=1.2, label="c = 1: b_{merged\\_len}")

    # c = 30
    sub30 = alg_df[alg_df["cutoff"] == 30].set_index("scale").loc[scale_order].reset_index()
    y_err30 = [sub30["b_time_T_bar"] - sub30["ci_b_time_lo"], sub30["ci_b_time_hi"] - sub30["b_time_T_bar"]]

    ax.errorbar(x_pos + width, sub30["b_time_T_bar"], yerr=y_err30, fmt="s", color="#eb6834",
                capsize=3.5, elinewidth=1.2, markersize=5, label="c = 30: đo T (CI 95%)")
    ax.plot(x_pos + width, sub30["b_accesses"], marker="+", markersize=7, linestyle="--",
            color="#8c330f", linewidth=1.2, label="c = 30: b_{accesses}")

    ax.set_xticks(x_pos)
    ax.set_xticklabels([f"Thang {s}\n(N ≈ {int(sub1.loc[i, 'N_geom'])})" for i, s in enumerate(scale_order)])
    ax.set_ylabel("Số mũ cục bộ b = d(ln T) / d(ln N)")
    ax.set_title("Số mũ cục bộ theo thang: thực đo vs. số đếm thuật toán")
    ax.legend(loc="upper right", fontsize=8.0)
    ax.set_ylim(1.02, 1.62)

    fig_png = out_dir / "figures" / "fig_local_exponent.png"
    fig_pdf = out_dir / "figures" / "fig_local_exponent.pdf"
    plt.savefig(fig_png)
    plt.savefig(fig_pdf)
    plt.close(fig)
    print(f"  Đã lưu hình 2: {fig_png} và {fig_pdf}")


def plot_cache_step(cache_df: pd.DataFrame, out_dir: Path):
    """Hình 3: Chi phí chuẩn hóa T/(N lg N) theo N cho c=1 và c=30 (run 3)."""
    fig, ax = plt.subplots(figsize=(6.4, 3.8))

    ax.plot(cache_df["N"], cache_df["T_c1_per_NlgN_ns"], marker="o", markersize=3.5,
            linestyle="-", linewidth=1.0, color="#2a78d6", label="c = 1 (baseline)")
    ax.plot(cache_df["N"], cache_df["T_c30_per_NlgN_ns"], marker="s", markersize=3.5,
            linestyle="-", linewidth=1.0, color="#eb6834", label="c = 30 (tối ưu gộp)")

    ymin, ymax = ax.get_ylim()
    top = ymax + 0.18 * (ymax - ymin)
    ax.set_ylim(ymin, top)

    for (lab, (size_bytes, n_star)), ls, ha in zip(CACHE_LEVELS.items(), ["--", ":"], ["left", "right"]):
        ax.axvline(n_star, color=NEUTRAL, linestyle=ls, linewidth=1.2)
        x_text = n_star * 1.05 if ha == "left" else n_star / 1.05
        ax.text(x_text, top - 0.03 * (top - ymin),
                f"{lab} {size_bytes // (1024*1024)} MB\n(N ≈ {n_star:.0f})",
                color=INK2, fontsize=8.0, va="top", ha=ha)

    ax.set_xscale("log", base=2)
    ax.set_xlabel("Kích thước mảng N (thang log₂)")
    ax.set_ylabel("Chi phí chuẩn hóa T / (N lg N) (ns)")
    ax.set_title("Kiểm tra bậc hiệu năng tại ngưỡng cache L2 (1 MB) và L3 (16 MB)")
    ax.legend(loc="upper left", fontsize=8.5)

    fig_png = out_dir / "figures" / "fig_power_law_cache_step.png"
    fig_pdf = out_dir / "figures" / "fig_power_law_cache_step.pdf"
    plt.savefig(fig_png)
    plt.savefig(fig_pdf)
    plt.close(fig)
    print(f"  Đã lưu hình 3: {fig_png} và {fig_pdf}")


# ──────────────────────────────────────────────────────────────── main
def main():
    parser = argparse.ArgumentParser(
        description="power_law.py – Phân tích mô hình lũy thừa T = a*N^b và số mũ cục bộ (T02b/T03-0).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--results", "--run3-dir", dest="results_dir", type=Path, default=Path("results_run3"),
                        help="Thư mục dữ liệu chính (mặc định: results_run3)")
    parser.add_argument("--run2-dir", type=Path, default=Path("results"),
                        help="Thư mục dữ liệu run 2")
    parser.add_argument("--run1-dir", type=Path, default=Path("results_run1"),
                        help="Thư mục dữ liệu run 1")
    parser.add_argument("--counts-file", type=Path, default=None,
                        help="File counts.csv chứa số đếm thuật toán (mặc định: <results>/counts.csv)")
    parser.add_argument("--out", "--out-dir", dest="out_dir", type=Path, default=Path("results_run3/analysis_v2"),
                        help="Thư mục xuất bảng và hình ảnh")
    parser.add_argument("--cutoffs", type=str, default="1,7,10,30",
                        help="Danh sách các cutoff cần phân tích (phân tách bởi dấu phẩy)")
    parser.add_argument("--seed", type=int, default=20261029,
                        help="Seed cố định để tái lập kết quả")

    args = parser.parse_args()

    np.random.seed(args.seed)

    cutoffs = [int(c.strip()) for c in args.cutoffs.split(",") if c.strip()]
    out_tables = args.out_dir / "tables"
    out_figures = args.out_dir / "figures"
    out_tables.mkdir(parents=True, exist_ok=True)
    out_figures.mkdir(parents=True, exist_ok=True)

    if args.counts_file is None:
        counts_path = args.results_dir / "counts.csv"
        if not counts_path.exists():
            counts_path = Path("results_run3/counts.csv")
    else:
        counts_path = args.counts_file

    is_final = "final" in str(args.results_dir).lower()
    primary_label = "results_final (ghim nhân 5)" if is_final else "run 3 (ghim nhân 5)"
    primary_short = "results_final" if is_final else "run 3"

    print("================================================================================")
    print("power_law.py – Khởi động phân tích mô hình lũy thừa T = a*N^b (T02b/T03-0)")
    print(f"  Thư mục dữ liệu chính: {args.results_dir} ({primary_label})")
    print(f"  Thư mục run 2 / run 1: run 2={args.run2_dir}, run 1={args.run1_dir}")
    print(f"  File số đếm:           {counts_path}")
    print(f"  Thư mục đầu ra:        {args.out_dir}")
    print(f"  Cutoffs:               {cutoffs}")
    print("================================================================================")

    # 1. Tải dữ liệu các lượt chạy
    runs_map = {
        primary_label: (args.results_dir, primary_label),
        "run 2": (args.run2_dir, "run 2"),
        "run 1": (args.run1_dir, "run 1"),
    }

    raw_dfs = {}
    for rlabel, (rdir, rshort) in runs_map.items():
        if rdir.exists():
            print(f"Tải dữ liệu {rlabel} từ {rdir}...")
            raw_dfs[rlabel] = load_run_data(rdir, rshort)
            print(f"  → Đã tải {len(raw_dfs[rlabel])} dòng dữ liệu hợp lệ (random, gc=False).")
        else:
            print(f"  [WARN] Không tìm thấy thư mục {rdir}, bỏ qua {rlabel}.")

    if primary_label not in raw_dfs:
        sys.exit(f"Lỗi: Không có dữ liệu {primary_label} (lượt chính). Dừng.")

    counts_df = load_counts_data(counts_path)
    print(f"Tải dữ liệu số đếm từ {counts_path}...")
    print(f"  → Đã tải {len(counts_df)} dòng số đếm (random).")

    # 2. Hồi quy theo từng fork riêng của mỗi run
    print("\n--- Hồi quy theo từng fork riêng (khảo sát dao động giữa-JVM) ---")
    fork_rows = []
    fork_bs_72 = {}
    fork_bs_48 = {}

    for rlabel, df_run in raw_dfs.items():
        fork_bs_72[rlabel] = {}
        fork_bs_48[rlabel] = {}
        df_run_48 = df_run[df_run["scale"].isin(["2^16", "2^19"])]

        for c in cutoffs:
            fork_bs_72[rlabel][c] = []
            fork_bs_48[rlabel][c] = []
            for f in sorted(df_run["fork"].unique()):
                # Hồi quy trên 72 N
                df_fork_72 = df_run[df_run["fork"] == f]
                t_bar_f_72 = compute_t_bar_per_n(df_fork_72, c)
                log_N_f_72 = np.log(t_bar_f_72["N"].to_numpy())
                log_T_f_72 = t_bar_f_72["mean_log_t"].to_numpy()
                fit_f_72 = fit_power_law_ols(log_N_f_72, log_T_f_72)
                fork_bs_72[rlabel][c].append(fit_f_72["b"])

                fork_rows.append({
                    "run": rlabel,
                    "scope": "72 N (toàn dải)",
                    "note": "Hồi quy 72 N" if rlabel == primary_label else "72 N (tham khảo)",
                    "fork": f,
                    "cutoff": c,
                    "n_N": 72,
                    "b": fit_f_72["b"],
                    "se_b": fit_f_72["se_b"],
                    "ci_b_lo": fit_f_72["ci_b_lo"],
                    "ci_b_hi": fit_f_72["ci_b_hi"],
                    "a_ns": fit_f_72["a_ns"],
                    "ci_a_lo": fit_f_72["ci_a_lo"],
                    "ci_a_hi": fit_f_72["ci_a_hi"],
                    "corr_log_a_b": fit_f_72["corr_log_a_b"],
                    "R2": fit_f_72["R2"],
                    "max_abs_rel_res_pct": fit_f_72["max_abs_rel_res_pct"],
                })

                # Hồi quy trên 48 N (2^16 + 2^19, dùng để so sánh sạch giữa các lượt)
                df_fork_48 = df_run_48[df_run_48["fork"] == f]
                t_bar_f_48 = compute_t_bar_per_n(df_fork_48, c)
                log_N_f_48 = np.log(t_bar_f_48["N"].to_numpy())
                log_T_f_48 = t_bar_f_48["mean_log_t"].to_numpy()
                fit_f_48 = fit_power_law_ols(log_N_f_48, log_T_f_48)
                fork_bs_48[rlabel][c].append(fit_f_48["b"])

                fork_rows.append({
                    "run": rlabel,
                    "scope": "48 N (2^16 + 2^19)",
                    "note": "48 N dùng so sánh giữa các lượt (sạch K=1)",
                    "fork": f,
                    "cutoff": c,
                    "n_N": 48,
                    "b": fit_f_48["b"],
                    "se_b": fit_f_48["se_b"],
                    "ci_b_lo": fit_f_48["ci_b_lo"],
                    "ci_b_hi": fit_f_48["ci_b_hi"],
                    "a_ns": fit_f_48["a_ns"],
                    "ci_a_lo": fit_f_48["ci_a_lo"],
                    "ci_a_hi": fit_f_48["ci_a_hi"],
                    "corr_log_a_b": fit_f_48["corr_log_a_b"],
                    "R2": fit_f_48["R2"],
                    "max_abs_rel_res_pct": fit_f_48["max_abs_rel_res_pct"],
                })

            fork_bs_72[rlabel][c] = np.array(fork_bs_72[rlabel][c])
            fork_bs_48[rlabel][c] = np.array(fork_bs_48[rlabel][c])

    fork_df = pd.DataFrame(fork_rows)
    fork_csv = out_tables / "power_law_per_fork.csv"
    fork_df.to_csv(fork_csv, index=False)
    print(f"  → Đã lưu {fork_csv}")

    # 3. Hồi quy OLS cho từng lượt và cutoff (B1)
    print("\n--- 1. Hồi quy OLS T = a*N^b trên N (random) (B1) ---")
    fit_rows = []
    fits_72 = {}
    fits_48 = {}
    t_bars_72 = {}
    t_bars_48 = {}

    tcrit_df2 = stats.t.ppf(0.975, df=2)

    for rlabel, df_run in raw_dfs.items():
        fits_72[rlabel] = {}
        fits_48[rlabel] = {}
        t_bars_72[rlabel] = {}
        t_bars_48[rlabel] = {}

        df_run_48 = df_run[df_run["scale"].isin(["2^16", "2^19"])]

        for c in cutoffs:
            # Hồi quy 72 N
            t_bar_72 = compute_t_bar_per_n(df_run, c)
            t_bars_72[rlabel][c] = t_bar_72
            log_N_72 = np.log(t_bar_72["N"].to_numpy())
            log_T_72 = t_bar_72["mean_log_t"].to_numpy()
            fit_72 = fit_power_law_ols(log_N_72, log_T_72)
            fits_72[rlabel][c] = fit_72

            f_bs_72 = fork_bs_72[rlabel][c]
            b_m_72 = float(np.mean(f_bs_72))
            b_s_72 = float(np.std(f_bs_72, ddof=1))
            b_se_72 = b_s_72 / math.sqrt(len(f_bs_72))

            row_72 = {
                "run": rlabel,
                "scope": "72 N (chính)" if rlabel == primary_label else "72 N (tham khảo)",
                "note": "Hồi quy chính 72 N (gộp 24 N thang 2^12 từ run 4 với 48 N từ run 3; đều ghim nhân 5)" if rlabel == primary_label else "72 N (run 1/2 còn K thiết kế ở 2^12)",
                "cutoff": c,
                "n_N": 72,
                "b": fit_72["b"],
                "se_b": fit_72["se_b"],
                "ci_b_lo": fit_72["ci_b_lo"],
                "ci_b_hi": fit_72["ci_b_hi"],
                "b_mean_3forks": b_m_72,
                "b_sd_3forks": b_s_72,
                "ci95_b_3forks_lo": b_m_72 - tcrit_df2 * b_se_72,
                "ci95_b_3forks_hi": b_m_72 + tcrit_df2 * b_se_72,
                "a_ns": fit_72["a_ns"],
                "se_log_a": fit_72["se_log_a"],
                "ci_a_lo": fit_72["ci_a_lo"],
                "ci_a_hi": fit_72["ci_a_hi"],
                "corr_log_a_b": fit_72["corr_log_a_b"],
                "R2": fit_72["R2"],
                "max_abs_rel_res_pct": fit_72["max_abs_rel_res_pct"],
            }
            for nr in N_REFS:
                tr = fit_72["t_refs"][nr]
                row_72[f"T_hat_{nr}_ms"] = tr["T_hat_ms"]
                row_72[f"ci95_T_{nr}_lo_ms"] = tr["ci_T_lo_ms"]
                row_72[f"ci95_T_{nr}_hi_ms"] = tr["ci_T_hi_ms"]
            fit_rows.append(row_72)

            # Hồi quy 48 N (2^16 + 2^19)
            t_bar_48 = compute_t_bar_per_n(df_run_48, c)
            t_bars_48[rlabel][c] = t_bar_48
            log_N_48 = np.log(t_bar_48["N"].to_numpy())
            log_T_48 = t_bar_48["mean_log_t"].to_numpy()
            fit_48 = fit_power_law_ols(log_N_48, log_T_48)
            fits_48[rlabel][c] = fit_48

            f_bs_48 = fork_bs_48[rlabel][c]
            b_m_48 = float(np.mean(f_bs_48))
            b_s_48 = float(np.std(f_bs_48, ddof=1))
            b_se_48 = b_s_48 / math.sqrt(len(f_bs_48))

            row_48 = {
                "run": rlabel,
                "scope": "48 N (2^16 + 2^19)",
                "note": "48 N (2^16 + 2^19, sạch K=1, dùng để so sánh giữa các lượt)",
                "cutoff": c,
                "n_N": 48,
                "b": fit_48["b"],
                "se_b": fit_48["se_b"],
                "ci_b_lo": fit_48["ci_b_lo"],
                "ci_b_hi": fit_48["ci_b_hi"],
                "b_mean_3forks": b_m_48,
                "b_sd_3forks": b_s_48,
                "ci95_b_3forks_lo": b_m_48 - tcrit_df2 * b_se_48,
                "ci95_b_3forks_hi": b_m_48 + tcrit_df2 * b_se_48,
                "a_ns": fit_48["a_ns"],
                "se_log_a": fit_48["se_log_a"],
                "ci_a_lo": fit_48["ci_a_lo"],
                "ci_a_hi": fit_48["ci_a_hi"],
                "corr_log_a_b": fit_48["corr_log_a_b"],
                "R2": fit_48["R2"],
                "max_abs_rel_res_pct": fit_48["max_abs_rel_res_pct"],
            }
            for nr in N_REFS:
                tr = fit_48["t_refs"][nr]
                row_48[f"T_hat_{nr}_ms"] = tr["T_hat_ms"]
                row_48[f"ci95_T_{nr}_lo_ms"] = tr["ci_T_lo_ms"]
                row_48[f"ci95_T_{nr}_hi_ms"] = tr["ci_T_hi_ms"]
            fit_rows.append(row_48)

            print(f"  {rlabel:25s} c={c:2d} (72 N): b = {fit_72['b']:.6f} (forks={b_m_72:.4f}, SD={b_s_72:.4f}), a = {fit_72['a_ns']:.3f} ns | (48 N): b = {fit_48['b']:.6f}")

    fits_df = pd.DataFrame(fit_rows)
    fits_csv = out_tables / "power_law_fits.csv"
    fits_df.to_csv(fits_csv, index=False)
    print(f"  → Đã lưu {fits_csv}")

    # 4. Bảng so sánh giữa các lượt (run vs primary) trên 48 điểm N (B1, B2)
    # QUY TẮC T03-0 (2a): So sánh giữa các lượt chỉ dùng 48 điểm N của 2^16 + 2^19
    print("\n--- 2. So sánh giữa các lượt chạy trên 48 điểm N (2^16 + 2^19): tỉ số T_hat và kiểm Welch (B1, B2) ---")
    comp_rows = []
    ref_label = primary_label

    for rlabel in ["run 2", "run 1"]:
        if rlabel not in fits_48:
            continue
        for c in cutoffs:
            cmp_res = compare_two_runs(
                fits_48[rlabel][c],
                fits_48[ref_label][c],
                fork_bs_48[rlabel][c],
                fork_bs_48[ref_label][c],
            )
            comp_data = {
                "comparison": f"{rlabel} vs {ref_label}",
                "run": rlabel,
                "cutoff": c,
                "n_N": 48,
                "scope": "48 N (2^16 + 2^19)",
                "delta_b_ols": cmp_res["delta_b"],
                "se_delta_b_ols": cmp_res["se_delta_b"],
                "ci_delta_b_ols_lo": cmp_res["ci_delta_b_lo"],
                "ci_delta_b_ols_hi": cmp_res["ci_delta_b_hi"],
                "ratio_a": cmp_res["ratio_a"],
                "se_diff_log_a": cmp_res["se_diff_log_a"],
                "ci_ratio_a_lo": cmp_res["ci_ratio_a_lo"],
                "ci_ratio_a_hi": cmp_res["ci_ratio_a_hi"],
                "b_mean_run": cmp_res["b_mean_run"],
                "b_sd_run": cmp_res["b_sd_run"],
                "ci95_b_run_lo": cmp_res["ci95_b_run_lo"],
                "ci95_b_run_hi": cmp_res["ci95_b_run_hi"],
                "b_mean_ref": cmp_res["b_mean_ref"],
                "b_sd_ref": cmp_res["b_sd_ref"],
                "ci95_b_ref_lo": cmp_res["ci95_b_ref_lo"],
                "ci95_b_ref_hi": cmp_res["ci95_b_ref_hi"],
                "welch_t_stat": cmp_res["welch_t_stat"],
                "welch_p_val": cmp_res["welch_p_val"],
                "welch_df": cmp_res["welch_df"],
                "welch_significant_05": cmp_res["welch_sig"],
                "note": "Chi dung 48 diem N cua 2^16 + 2^19 (run 1/2 con K thiet ke o 2^12; JVM cua 2^12 o results_final khac voi cac thang con lai). Welch df=2 theo 3 fork.",
            }
            # Tỉ số thời gian tại các N tham chiếu
            for nr in N_REFS:
                r_nr = cmp_res["ratio_refs"][nr]
                comp_data[f"ratio_T_{nr}"] = r_nr["ratio"]
                comp_data[f"ci95_ratio_T_{nr}_lo"] = r_nr["ci_lo"]
                comp_data[f"ci95_ratio_T_{nr}_hi"] = r_nr["ci_hi"]

            comp_rows.append(comp_data)
            r65 = cmp_res["ratio_refs"][65536]
            print(f"  {rlabel} vs {primary_short} (48 N), c={c:2d}: delta_b={cmp_res['delta_b']:+.4f} "
                  f"(Welch t={cmp_res['welch_t_stat']:.3f}, p={cmp_res['welch_p_val']:.3f}), "
                  f"ratio_a={cmp_res['ratio_a']:.3f}x, ratio_T(65536)={r65['ratio']:.3f}x [{r65['ci_lo']:.3f}x, {r65['ci_hi']:.3f}x]")

    comp_df = pd.DataFrame(comp_rows)
    comp_csv = out_tables / "power_law_run_comparison.csv"
    comp_df.to_csv(comp_csv, index=False)
    print(f"  → Đã lưu {comp_csv}")

    # 5. Tương tác Fork × Thang (B3) (chỉ trên 2^16 + 2^19)
    print(f"\n--- 3. Tương tác fork × thang trên {primary_label} (B3, chỉ 2^16 + 2^19) ---")
    inter_df, anova_df = compute_fork_scale_interaction(raw_dfs[primary_label], cutoffs)
    inter_csv = out_tables / "power_law_fork_scale_interaction.csv"
    anova_csv = out_tables / "power_law_fork_scale_anova.csv"
    inter_df.to_csv(inter_csv, index=False)
    anova_df.to_csv(anova_csv, index=False)
    print(f"  → Đã lưu {inter_csv} và {anova_csv}")
    print("  Tái tạo bảng B3 (trung bình nhân T/(N lg N) ns theo fork):")
    for c in [1, 30]:
        sub_i = inter_df[inter_df["cutoff"] == c]
        print(f"    Cutoff {c}:")
        for _, r in sub_i.iterrows():
            print(f"      Thang {r['scale']}: Fork 1 = {r['geom_mean_T_per_NlgN_fork1_ns']:.2f} ({r['ratio_to_mean_fork1']:.3f}), "
                  f"Fork 2 = {r['geom_mean_T_per_NlgN_fork2_ns']:.2f} ({r['ratio_to_mean_fork2']:.3f}), "
                  f"Fork 3 = {r['geom_mean_T_per_NlgN_fork3_ns']:.2f} ({r['ratio_to_mean_fork3']:.3f}) | Mean = {r['geom_mean_T_per_NlgN_3fork_mean_ns']:.2f}")

    # 6. Số mũ thuật toán từ counts.csv (B4)
    print(f"\n--- 4. Số mũ thuật toán b_alg từ counts.csv và phần vượt (B4) trên {primary_label} ---")
    alg_df = compute_algorithmic_exponents(raw_dfs[primary_label], counts_df, cutoffs)
    alg_csv = out_tables / "power_law_algorithmic_exponents.csv"
    local_csv = out_tables / "power_law_local_exponent.csv"
    alg_df.to_csv(alg_csv, index=False)
    alg_df.to_csv(local_csv, index=False)  # Cập nhật cả file cũ để đồng bộ
    print(f"  → Đã lưu {alg_csv} và cập nhật {local_csv}")
    for c in [1, 30]:
        sub_a = alg_df[alg_df["cutoff"] == c]
        print(f"    Cutoff {c}:")
        for _, r in sub_a.iterrows():
            note_str = f" [{r['note']}]" if r.get('note') else ""
            print(f"      Thang {r['scale']}: b_time = {r['b_time_T_bar']:.4f} (SD_fork={r['b_time_sd_between_forks']:.4f}) | "
                  f"b_ml = {r['b_merged_len']:.4f} (vượt {r['excess_vs_merged_len']:+.4f}) | "
                  f"b_acc = {r['b_accesses']:.4f} (vượt {r['excess_vs_accesses']:+.4f}){note_str}")

    # 7. Phân tích bậc Cache theo từng fork (B5)
    print(f"\n--- 5. Bậc cache theo từng fork, chuẩn hóa T / merged_len (B5) trên {primary_label} ---")
    cache_fork_df = compute_cache_step_by_fork(raw_dfs[primary_label], counts_df, cutoffs)
    cache_fork_csv = out_tables / "power_law_cache_by_fork.csv"
    cache_fork_df.to_csv(cache_fork_csv, index=False)
    print(f"  → Đã lưu {cache_fork_csv}")

    cache_df = compute_cache_step_analysis(raw_dfs[primary_label], counts_df)
    cache_csv = out_tables / "power_law_cache_step.csv"
    cache_df.to_csv(cache_csv, index=False)
    print(f"  → Đã lưu {cache_csv}")

    for c in [1, 30]:
        sub_cf = cache_fork_df[(cache_fork_df["cutoff"] == c) & (cache_fork_df["fork"] != "mean_3forks")]
        print(f"    Cutoff {c}:")
        for _, r in sub_cf.iterrows():
            print(f"      Fork {r['fork']}: 2^16 = {r['ns_per_merged_2^16']:.4f} ns/elem | "
                  f"2^19 (<L3) = {r['ns_per_merged_2^19_below_L3']:.4f} | 2^19 (>=L3) = {r['ns_per_merged_2^19_above_L3']:.4f} | "
                  f"step = {r['step_ratio_within_2^19']:.4f} ({r['step_pct_within_2^19']:+.2f}%) | vs 2^16 = {r['ratio_vs_2^16']:.4f} ({r['pct_vs_2^16']:+.2f}%)")

    # 8. Vẽ đồ thị kết quả
    print("\n--- 6. Vẽ đồ thị kết quả ---")
    plot_power_law_runs(fits_72, t_bars_72, args.out_dir, primary_label)
    plot_local_exponents(alg_df, args.out_dir)
    plot_cache_step(cache_df, args.out_dir)

    print(f"\nHoàn tất phân tích power_law.py trên {primary_label} (T03-0)!")
    print("================================================================================")


if __name__ == "__main__":
    main()
