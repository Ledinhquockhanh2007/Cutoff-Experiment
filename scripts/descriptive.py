#!/usr/bin/env python3
"""
descriptive.py – Thống kê mô tả, phân rã phương sai, lợi ích ghép cặp, độ chính xác theo R.

Cách chạy (từ thư mục cutoff-experiment):
    python scripts/descriptive.py

Tùy chọn:
    --results <dir>   thư mục kết quả (mặc định: results_run3)
    --out <dir>       thư mục đầu ra (mặc định: results_run3/analysis_v2)
    --B <int>         số mẫu bootstrap (mặc định: 2000)
    --seed <int>      seed bootstrap (mặc định: 20261029)
    --help            hiển thị trợ giúp

Đầu ra:
    <out>/tables/design_table.csv
    <out>/tables/desc_random.csv
    <out>/tables/desc_other.csv
    <out>/tables/variance_components.csv
    <out>/tables/pairing_gain.csv
    <out>/tables/precision_vs_R.csv
    <out>/figures/fig_precision_vs_R.png + .pdf
"""
from __future__ import annotations

import argparse
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# ──────────────────────────────────────────────────────────────── hằng số thiết kế
FULL_GRID = list(range(1, 33)) + [40, 48, 64]
SPARSE_GRID = [1, 2, 4, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64]
SCALES = [2**12, 2**16, 2**19]
SCALE_LABELS = {2**12: "2^12", 2**16: "2^16", 2**19: "2^19"}

# Best cutoffs per scale (random) from rq1_best_cutoff.csv
BEST_CUTOFF_RANDOM = {2**12: 29, 2**16: 31, 2**19: 27}

# j=0 and j=12 N values per scale (exact: round(S * 2**(j/24)))
def nj(S, j):
    return round(S * 2 ** (j / 24))

SCALE_N_J0_J12 = {S: (nj(S, 0), nj(S, 12)) for S in SCALES}
# 2^12: (4096, 5793); 2^16: (65536, 92682); 2^19: (524288, 741455)

# ──────────────────────────────────────────────────────────────── màu & style
INK, INK2, GRID_C, NEUTRAL = "#0b0b0b", "#52514e", "#e2e1dc", "#8d8c86"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Segoe UI", "Arial"],
    "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight",
    "font.size": 9.5, "axes.titlesize": 10.5, "axes.labelsize": 10,
    "xtick.labelsize": 9, "ytick.labelsize": 9,
    "legend.fontsize": 8.5, "legend.frameon": False,
    "axes.edgecolor": NEUTRAL, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID_C, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
})


# ══════════════════════════════════════════════════════════════════════════════
# I/O helpers
# ══════════════════════════════════════════════════════════════════════════════

def load_raw(results_dir: Path) -> pd.DataFrame:
    """Nạp và nối 3 fork, lọc gc_during_run == False, tính t_ms."""
    frames = []
    for f in [1, 2, 3]:
        fp = results_dir / f"raw_fork{f}.csv"
        df = pd.read_csv(fp)
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df[df["gc_during_run"] == False].copy()
    # QUY ƯỚC: time_ns ĐÃ là thời gian của MỘT lần sắp (Benchmark.measure chia k sẵn).
    # KHÔNG được chia thêm cho batch_k. (Lỗi cũ ở T01 chia batch_k làm sai thang 2^12).
    df["t_ms"] = df["time_ns"] / 1e6   # một lần sắp, đơn vị ms

    # Assert kiểm tra: trung vị t_ms tại N = 2^16 (65536), k = 1 phải bằng
    # trung vị của time_ns/1e6 tính độc lập từ file CSV thô đọc lại.
    raw_check_frames = [pd.read_csv(results_dir / f"raw_fork{f}.csv") for f in [1, 2, 3]]
    raw_check = pd.concat(raw_check_frames, ignore_index=True)
    raw_check = raw_check[raw_check["gc_during_run"] == False]
    mask_k1_16 = (raw_check["N"] == 65536) & (raw_check["batch_k"] == 1)
    expected_median_ms = float((raw_check.loc[mask_k1_16, "time_ns"] / 1e6).median())
    actual_median_ms = float(df.loc[(df["N"] == 65536) & (df["batch_k"] == 1), "t_ms"].median())

    assert np.isclose(actual_median_ms, expected_median_ms), \
        f"Assert failed: actual median {actual_median_ms} != expected {expected_median_ms}"
    assert np.isclose(expected_median_ms, 8.5515), \
        f"Assert failed: expected median {expected_median_ms} != 8.5515 ms"

    # Kiểm tra không có cột nào trong script chia cho batch_k hay phụ thuộc batch_k
    used_cols = [c for c in df.columns if "batch_k" in c and c != "batch_k"]
    assert len(used_cols) == 0, f"Assert failed: phát hiện cột phụ thuộc batch_k: {used_cols}"
    print(f"  [KIỂM TRA] Assert passed: median(N=2^16, k=1) = {actual_median_ms:.4f} ms trùng khớp độc lập (8.5515 ms).")
    print("  [CẢNH BÁO] Tuyệt đối không dùng batch_k để chia lại thời gian (time_ns đã là thời gian 1 lần sắp).")

    return df


def save_csv(df: pd.DataFrame, path: Path, **kwargs):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, **kwargs)
    print(f"  Đã lưu: {path}")


def save_fig(fig: plt.Figure, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    fig.savefig(path.with_suffix(".pdf"))
    print(f"  Đã lưu: {path} + .pdf")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Bảng thiết kế (design_table.csv)
# ══════════════════════════════════════════════════════════════════════════════

def compress_cutoff_list(cutoffs: list[int]) -> str:
    """Nén danh sách CUTOFF: 1–32, 40, 48, 64 v.v. Chỉ nén khi dãy liên tiếp >= 3."""
    cutoffs = sorted(cutoffs)
    if not cutoffs:
        return ""
    parts = []
    i = 0
    while i < len(cutoffs):
        j = i
        while j + 1 < len(cutoffs) and cutoffs[j + 1] == cutoffs[j] + 1:
            j += 1
        if j - i + 1 >= 3:
            parts.append(f"{cutoffs[i]}-{cutoffs[j]}")
            i = j + 1
        else:
            parts.append(str(cutoffs[i]))
            i += 1
    return ", ".join(parts)


def scale_label_of(n: int) -> str:
    """Gán nhãn thang từ giá trị N."""
    for S in SCALES:
        Ns = nj(S, 0)
        Ne = nj(S, 23)
        if Ns <= n <= Ne:
            return SCALE_LABELS[S]
    return "unknown"


def make_design_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dist in ["random", "sorted", "reversed", "nearly_sorted", "few_distinct"]:
        sub = df[df["distribution"] == dist]
        Ns_unique = sorted(sub["N"].unique())
        # Xác định các thang có trong phân bố này
        if dist == "random":
            scales_here = ["2^12", "2^16", "2^19"]
        else:
            scales_here = ["2^16"]

        for scale_lbl in scales_here:
            S = [k for k, v in SCALE_LABELS.items() if v == scale_lbl][0]
            Ns_scale = [n for n in Ns_unique if scale_label_of(n) == scale_lbl]
            if not Ns_scale:
                continue
            cutoffs = sorted(sub[sub["N"].isin(Ns_scale)]["cutoff"].unique())

            # Số trial mỗi fork: lấy mode (mỗi ô có thể khác nhau ở thang 2^12 vs 2^16/2^19 random)
            trial_counts = sub[sub["N"].isin(Ns_scale)].groupby(
                ["fork", "N", "cutoff"])["trial"].nunique()
            trial_per_fork_mode = int(trial_counts.mode().iloc[0]) if len(trial_counts) else 0

            n_forks = sub["fork"].nunique()
            n_meas = len(sub[sub["N"].isin(Ns_scale)])
            batch_k_vals = sorted(int(x) for x in sub[sub["N"].isin(Ns_scale)]["batch_k"].unique())

            rows.append({
                "distribution": dist,
                "scale": scale_lbl,
                "n_N": len(Ns_scale),
                "N_min": min(Ns_scale),
                "N_max": max(Ns_scale),
                "cutoffs": compress_cutoff_list(cutoffs),
                "n_cutoff": len(cutoffs),
                "trials_per_fork": trial_per_fork_mode,
                "n_fork": n_forks,
                "n_measurements": n_meas,
                "batch_k_values": str(batch_k_vals),
            })

    design_df = pd.DataFrame(rows)
    total_meas = design_df["n_measurements"].sum()
    total_row = pd.DataFrame([{
        "distribution": "TOTAL",
        "scale": "",
        "n_N": design_df["n_N"].sum(),
        "N_min": "",
        "N_max": "",
        "cutoffs": "",
        "n_cutoff": "",
        "trials_per_fork": "",
        "n_fork": "",
        "n_measurements": total_meas,
        "batch_k_values": "",
    }])
    design_df = pd.concat([design_df, total_row], ignore_index=True)
    return design_df


# ══════════════════════════════════════════════════════════════════════════════
# 2. Thống kê mô tả thời gian
# ══════════════════════════════════════════════════════════════════════════════

def descriptive_stats_one(sub: pd.DataFrame, dist: str, scale_lbl: str, N: int, cutoff: int) -> dict:
    """Thống kê mô tả cho một ô (dist, scale, N, cutoff)."""
    vals = sub["t_ms"].values
    n = len(vals)
    if n == 0:
        return {}
    mean_ms = vals.mean()
    sd_ms = vals.std(ddof=1) if n > 1 else 0.0
    cv_pct = 100 * sd_ms / mean_ms if mean_ms > 0 else 0.0
    med_ms = np.median(vals)
    min_ms = vals.min()
    max_ms = vals.max()

    # Trung bình của từng fork (fork 1..3)
    fork_means = []
    for f in [1, 2, 3]:
        sub_f = sub[sub["fork"] == f]
        fork_means.append(sub_f["t_ms"].mean() if len(sub_f) > 0 else float("nan"))
    f1_m, f2_m, f3_m = fork_means
    valid_f = [m for m in fork_means if not math.isnan(m)]
    F = len(valid_f)
    if F >= 2:
        sd_fork = float(np.std(valid_f, ddof=1))
        mean_f = float(np.mean(valid_f))
        cv_between_fork_pct = 100.0 * sd_fork / mean_f if mean_f > 0 else 0.0
        se_fork = sd_fork / math.sqrt(F)
        t_crit_f = stats.t.ppf(0.975, df=F - 1)
        ci_fork_lo = mean_f - t_crit_f * se_fork
        ci_fork_hi = mean_f + t_crit_f * se_fork
    else:
        cv_between_fork_pct = 0.0
        ci_fork_lo = ci_fork_hi = mean_ms

    # CI 95% pooled mean (t-distribution, giả định 30 lần đo độc lập)
    if n > 1:
        se_pooled = sd_ms / math.sqrt(n)
        t_crit_p = stats.t.ppf(0.975, df=n - 1)
        ci_pooled_lo = mean_ms - t_crit_p * se_pooled
        ci_pooled_hi = mean_ms + t_crit_p * se_pooled
    else:
        ci_pooled_lo = ci_pooled_hi = mean_ms

    # mean / (N lg N) in ns  →  t_ms * 1e6 / (N * log2(N))
    nlgn = N * math.log2(N)
    mean_per_NlgN_ns = mean_ms * 1e6 / nlgn if nlgn > 0 else float("nan")
    return {
        "distribution": dist,
        "scale": scale_lbl,
        "N": N,
        "cutoff": cutoff,
        "n": n,
        "mean_ms": round(mean_ms, 6),
        "sd_ms": round(sd_ms, 6),
        "cv_pct": round(cv_pct, 3),
        "mean_fork1_ms": round(f1_m, 6) if not math.isnan(f1_m) else None,
        "mean_fork2_ms": round(f2_m, 6) if not math.isnan(f2_m) else None,
        "mean_fork3_ms": round(f3_m, 6) if not math.isnan(f3_m) else None,
        "cv_between_fork_pct": round(cv_between_fork_pct, 3),
        "median_ms": round(med_ms, 6),
        "min_ms": round(min_ms, 6),
        "max_ms": round(max_ms, 6),
        "ci95_fork_lo_ms": round(ci_fork_lo, 6),
        "ci95_fork_hi_ms": round(ci_fork_hi, 6),
        "ci95_pooled_lo_ms": round(ci_pooled_lo, 6),
        "ci95_pooled_hi_ms": round(ci_pooled_hi, 6),
        "mean_per_NlgN_ns": round(mean_per_NlgN_ns, 4),
    }


def make_desc_random(df: pd.DataFrame) -> pd.DataFrame:
    """desc_random.csv: random × 3 thang × 2 N × 5 cutoff."""
    rows = []
    rdf = df[df["distribution"] == "random"]
    for S in SCALES:
        scale_lbl = SCALE_LABELS[S]
        j0_N, j12_N = SCALE_N_J0_J12[S]
        best_c = BEST_CUTOFF_RANDOM[S]
        cutoffs_sel = sorted(set([1, 7, 10, 30, best_c]))
        for N in [j0_N, j12_N]:
            for c in cutoffs_sel:
                sub = rdf[(rdf["N"] == N) & (rdf["cutoff"] == c)]
                if len(sub) == 0:
                    continue
                row = descriptive_stats_one(sub, "random", scale_lbl, N, c)
                if row:
                    rows.append(row)
    return pd.DataFrame(rows)


def make_desc_other(df: pd.DataFrame) -> pd.DataFrame:
    """desc_other.csv: 4 phân bố khác × 2 N × cutoff ∩ lưới thưa."""
    rows = []
    S = 2**16
    scale_lbl = "2^16"
    j0_N, j12_N = SCALE_N_J0_J12[S]
    other_dists = ["sorted", "reversed", "nearly_sorted", "few_distinct"]
    # cutoff ∈ {1, 8, 10, 32, 64} ∩ sparse grid
    target_cutoffs = [c for c in [1, 8, 10, 32, 64] if c in SPARSE_GRID]
    for dist in other_dists:
        sub_dist = df[df["distribution"] == dist]
        for N in [j0_N, j12_N]:
            for c in target_cutoffs:
                sub = sub_dist[(sub_dist["N"] == N) & (sub_dist["cutoff"] == c)]
                if len(sub) == 0:
                    continue
                row = descriptive_stats_one(sub, dist, scale_lbl, N, c)
                if row:
                    rows.append(row)
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Phân rã phương sai (variance_components.csv)
# ══════════════════════════════════════════════════════════════════════════════

def variance_components_one(sub: pd.DataFrame) -> tuple[float, float]:
    """
    Tách phương sai trong-JVM và giữa-JVM trên log(t_ms).
    Mô hình: Y_fij = mu + alpha_f + eps_fij   (alpha_f ~ N(0,sigma_b^2), eps ~ N(0,sigma_w^2))
    Method of moments (ANOVA một chiều):
        MS_between = sum_f n_f * (ybar_f - ybar)^2 / (F-1)
        MS_within  = sum_f sum_i (y_fi - ybar_f)^2 / (N_total - F)
        sigma_w^2 = MS_within
        sigma_b^2 = max(0, (MS_between - MS_within) / n0)
            với n0 = (N_total - sum_f n_f^2/N_total) / (F-1)
    Trả về: (sd_within_pct, sd_between_pct) — % của mean(log t)
    """
    log_t = np.log(sub["t_ms"].values)
    forks = sub["fork"].values
    fork_ids = np.unique(forks)
    F = len(fork_ids)
    if F < 2:
        return 0.0, 0.0

    N_total = len(log_t)
    grand_mean = log_t.mean()

    fork_means = {}
    fork_ns = {}
    for fk in fork_ids:
        mask = forks == fk
        fork_means[fk] = log_t[mask].mean()
        fork_ns[fk] = mask.sum()

    # MS_between
    ss_between = sum(fork_ns[fk] * (fork_means[fk] - grand_mean) ** 2 for fk in fork_ids)
    ms_between = ss_between / (F - 1)

    # MS_within
    ss_within = sum(
        np.sum((log_t[forks == fk] - fork_means[fk]) ** 2) for fk in fork_ids
    )
    df_within = N_total - F
    ms_within = ss_within / df_within if df_within > 0 else 0.0

    sigma_w2 = ms_within

    n0_num = N_total - sum(fork_ns[fk] ** 2 for fk in fork_ids) / N_total
    n0 = n0_num / (F - 1)
    sigma_b2 = max(0.0, (ms_between - ms_within) / n0) if n0 > 0 else 0.0

    # Sửa Lỗi 1: SD(log t) * 100 (xấp xỉ hệ số biến thiên tương đối %)
    sd_w = math.sqrt(sigma_w2)
    sd_b = math.sqrt(sigma_b2)
    return 100.0 * sd_w, 100.0 * sd_b


def make_variance_components(df: pd.DataFrame) -> pd.DataFrame:
    """Phân rã phương sai cho mọi ô (dist, N, c); báo cáo trung vị & p90 theo thang."""
    rows = []
    for dist in df["distribution"].unique():
        sub_dist = df[df["distribution"] == dist]
        for N in sub_dist["N"].unique():
            sub_N = sub_dist[sub_dist["N"] == N]
            scale_lbl = scale_label_of(N)
            for c in sub_N["cutoff"].unique():
                sub = sub_N[sub_N["cutoff"] == c]
                sd_w, sd_b = variance_components_one(sub)
                rows.append({
                    "distribution": dist,
                    "scale": scale_lbl,
                    "N": N,
                    "cutoff": c,
                    "sd_within_pct": round(sd_w, 4),
                    "sd_between_pct": round(sd_b, 4),
                })
    cell_df = pd.DataFrame(rows)

    # Tổng hợp: trung vị & p90 theo thang (và toàn bộ)
    summary_rows = []
    for scale_lbl in ["2^12", "2^16", "2^19", "all"]:
        if scale_lbl == "all":
            sub = cell_df
        else:
            sub = cell_df[cell_df["scale"] == scale_lbl]
        if len(sub) == 0:
            continue
        summary_rows.append({
            "scale": scale_lbl,
            "n_cells": len(sub),
            "sd_within_median_pct": round(sub["sd_within_pct"].median(), 4),
            "sd_within_p90_pct": round(sub["sd_within_pct"].quantile(0.9), 4),
            "sd_between_median_pct": round(sub["sd_between_pct"].median(), 4),
            "sd_between_p90_pct": round(sub["sd_between_pct"].quantile(0.9), 4),
        })

    cell_df_out = cell_df.copy()
    summary_df = pd.DataFrame(summary_rows)
    return cell_df_out, summary_df


# ══════════════════════════════════════════════════════════════════════════════
# 4. Lợi ích ghép cặp (pairing_gain.csv)
# ══════════════════════════════════════════════════════════════════════════════

def make_pairing_gain(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Với mỗi ô (dist, N, c): so sánh Var(log r ghép cặp) với Var phản thực tế
    nếu t_c và t_1 đo độc lập = Var(log t_c) + Var(log t_1).
    var_reduction = 1 - Var_paired / (Var_c + Var_1).
    Hai biến thể:
      (a) phương sai tổng (gồm giữa-JVM)
      (b) chỉ trong-fork (trung tâm hóa theo fork)
    Bảng riêng: SD_between của log r so với SD_between của log t.
    """
    rows = []
    between_rows = []

    for dist in df["distribution"].unique():
        sub_dist = df[df["distribution"] == dist]
        for N in sub_dist["N"].unique():
            sub_N = sub_dist[sub_dist["N"] == N]
            scale_lbl = scale_label_of(N)
            c1_sub = sub_N[sub_N["cutoff"] == 1].set_index(["fork", "seed", "trial"])
            for c in sub_N["cutoff"].unique():
                if c == 1:
                    continue
                sub_c = sub_N[sub_N["cutoff"] == c].set_index(["fork", "seed", "trial"])
                # Ghép cặp
                common_idx = c1_sub.index.intersection(sub_c.index)
                if len(common_idx) < 2:
                    continue

                tc = sub_c.loc[common_idx, "t_ms"].values
                t1 = c1_sub.loc[common_idx, "t_ms"].values
                forks = np.array([idx[0] for idx in common_idx])
                u_forks = np.unique(forks)
                F = len(u_forks)

                log_tc = np.log(tc)
                log_t1 = np.log(t1)
                log_r = log_tc - log_t1

                # (a) Phương sai tổng (gồm giữa-JVM)
                var_c_tot = float(np.var(log_tc, ddof=1))
                var_1_tot = float(np.var(log_t1, ddof=1))
                var_cf_tot = var_c_tot + var_1_tot
                var_paired_tot = float(np.var(log_r, ddof=1))
                red_tot = (1.0 - var_paired_tot / var_cf_tot) * 100.0 if var_cf_tot > 0 else 0.0

                # (b) Chỉ trong-fork (trung tâm hóa theo fork)
                log_tc_w = np.zeros_like(log_tc)
                log_t1_w = np.zeros_like(log_t1)
                log_r_w = np.zeros_like(log_r)
                for fk in u_forks:
                    m = (forks == fk)
                    log_tc_w[m] = log_tc[m] - log_tc[m].mean()
                    log_t1_w[m] = log_t1[m] - log_t1[m].mean()
                    log_r_w[m] = log_r[m] - log_r[m].mean()

                df_w = len(common_idx) - F
                var_c_w = float(np.sum(log_tc_w ** 2) / df_w) if df_w > 0 else 0.0
                var_1_w = float(np.sum(log_t1_w ** 2) / df_w) if df_w > 0 else 0.0
                var_cf_w = var_c_w + var_1_w
                var_paired_w = float(np.sum(log_r_w ** 2) / df_w) if df_w > 0 else 0.0
                red_w = (1.0 - var_paired_w / var_cf_w) * 100.0 if var_cf_w > 0 else 0.0

                # SD_between của log t_c và log r qua ANOVA method of moments
                def calc_sd_b(y: np.ndarray) -> float:
                    N_tot = len(y)
                    gm = y.mean()
                    f_means = {fk: y[forks == fk].mean() for fk in u_forks}
                    f_ns = {fk: (forks == fk).sum() for fk in u_forks}
                    ss_b = sum(f_ns[fk] * (f_means[fk] - gm) ** 2 for fk in u_forks)
                    ms_b = ss_b / (F - 1) if F > 1 else 0.0
                    ss_w = sum(np.sum((y[forks == fk] - f_means[fk]) ** 2) for fk in u_forks)
                    ms_w = ss_w / df_w if df_w > 0 else 0.0
                    n0 = (N_tot - sum(f_ns[fk] ** 2 for fk in u_forks) / N_tot) / (F - 1) if F > 1 else 1.0
                    sig_b2 = max(0.0, (ms_b - ms_w) / n0) if n0 > 0 else 0.0
                    return math.sqrt(sig_b2)

                sd_b_tc = calc_sd_b(log_tc) * 100.0
                sd_b_r = calc_sd_b(log_r) * 100.0
                sd_b_ratio = (sd_b_r / sd_b_tc) if sd_b_tc > 0 else 0.0
                sd_b_red = (1.0 - sd_b_ratio) * 100.0 if sd_b_tc > 0 else 0.0
                var_b_red = (1.0 - (sd_b_r ** 2) / (sd_b_tc ** 2)) * 100.0 if sd_b_tc > 0 else 0.0

                rows.append({
                    "distribution": dist,
                    "scale": scale_lbl,
                    "N": N,
                    "cutoff": c,
                    "n_paired": len(common_idx),
                    "var_c_tot": round(var_c_tot, 8),
                    "var_1_tot": round(var_1_tot, 8),
                    "var_cf_tot": round(var_cf_tot, 8),
                    "var_paired_tot": round(var_paired_tot, 8),
                    "var_reduction_total_pct": round(red_tot, 2),
                    "var_c_within": round(var_c_w, 8),
                    "var_1_within": round(var_1_w, 8),
                    "var_cf_within": round(var_cf_w, 8),
                    "var_paired_within": round(var_paired_w, 8),
                    "var_reduction_within_pct": round(red_w, 2),
                    "sd_between_tc_pct": round(sd_b_tc, 4),
                    "sd_between_r_pct": round(sd_b_r, 4),
                    "sd_b_reduction_pct": round(sd_b_red, 2),
                    "var_b_reduction_pct": round(var_b_red, 2),
                })

                between_rows.append({
                    "distribution": dist,
                    "scale": scale_lbl,
                    "N": N,
                    "cutoff": c,
                    "sd_b_tc_pct": sd_b_tc,
                    "sd_b_r_pct": sd_b_r,
                    "sd_b_ratio": sd_b_ratio,
                    "sd_b_reduction_pct": sd_b_red,
                    "var_b_reduction_pct": var_b_red,
                })

    gain_df = pd.DataFrame(rows)
    between_df = pd.DataFrame(between_rows)

    # Tóm tắt pairing gain theo thang
    summary_rows = []
    for scale_lbl in ["2^12", "2^16", "2^19", "all"]:
        sub = gain_df if scale_lbl == "all" else gain_df[gain_df["scale"] == scale_lbl]
        if len(sub) == 0:
            continue
        summary_rows.append({
            "scale": scale_lbl,
            "n_cells": len(sub),
            "red_total_median_pct": round(sub["var_reduction_total_pct"].median(), 2),
            "red_total_p10_pct": round(sub["var_reduction_total_pct"].quantile(0.1), 2),
            "red_total_p90_pct": round(sub["var_reduction_total_pct"].quantile(0.9), 2),
            "red_within_median_pct": round(sub["var_reduction_within_pct"].median(), 2),
            "red_within_p10_pct": round(sub["var_reduction_within_pct"].quantile(0.1), 2),
            "red_within_p90_pct": round(sub["var_reduction_within_pct"].quantile(0.9), 2),
        })
    summary_df = pd.DataFrame(summary_rows)

    # Tóm tắt SD_between log r vs log t theo thang
    between_summary_rows = []
    for scale_lbl in ["2^12", "2^16", "2^19", "all"]:
        sub = between_df if scale_lbl == "all" else between_df[between_df["scale"] == scale_lbl]
        if len(sub) == 0:
            continue
        between_summary_rows.append({
            "scale": scale_lbl,
            "n_cells": len(sub),
            "sd_b_tc_median_pct": round(sub["sd_b_tc_pct"].median(), 2),
            "sd_b_r_median_pct": round(sub["sd_b_r_pct"].median(), 2),
            "sd_b_ratio_median": round(sub["sd_b_ratio"].median(), 3),
            "sd_b_reduction_median_pct": round(sub["sd_b_reduction_pct"].median(), 2),
            "var_b_reduction_median_pct": round(sub["var_b_reduction_pct"].median(), 2),
        })
    between_summary_df = pd.DataFrame(between_summary_rows)

    return gain_df, summary_df, between_summary_df


# ══════════════════════════════════════════════════════════════════════════════
# 5. Độ chính xác theo số lần lặp (precision_vs_R.csv + hình)
# ══════════════════════════════════════════════════════════════════════════════

def make_precision_vs_R(
    df: pd.DataFrame, B: int, seed: int, out_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Phân rã phương sai của d = mean_N(log(T7/T10)) theo (f, m) ∈ {1,2,3} × {1,2,3,5,10}:
      (i) thành phần đo lường: mean_N(Var_within(log r | N)) / (24 * f * m) + Var_between_fork(d) / f
      (ii) thành phần không đồng nhất N: Var_N(d_N) / 24 (trừ phần nhiễu đo ở R đầy đủ)
    Báo cáo SE_total, tỉ lệ 2 thành phần, sàn bootstrap-theo-N (ở R đầy đủ),
    kiểm tra d theo từng fork riêng (df=2), và vẽ hình SE_total theo m cho f=1,2,3.
    """
    rng = np.random.default_rng(seed)
    prec_rows = []
    fork_rows = []

    rdf = df[df["distribution"] == "random"].copy()

    for S in SCALES:
        scale_lbl = SCALE_LABELS[S]
        Ns_scale = sorted([N for N in rdf["N"].unique() if scale_label_of(N) == scale_lbl])
        sub_scale = rdf[rdf["N"].isin(Ns_scale)].copy()
        R_max = int(sub_scale["trial"].max())

        # Pivot để tính log(T7 / T10) theo (fork, trial, N)
        piv = sub_scale[sub_scale["cutoff"].isin([7, 10])].pivot_table(
            index=["fork", "trial", "N"], columns="cutoff", values="t_ms"
        ).reset_index()
        piv["log_ratio"] = np.log(piv[7] / piv[10])

        d_obs = float(piv["log_ratio"].mean())
        abs_d_pct = abs(d_obs) * 100.0

        # Phép kiểm d theo từng fork riêng (df=2)
        f_means = piv.groupby("fork")["log_ratio"].mean()
        m1 = float(f_means[1])
        m2 = float(f_means[2])
        m3 = float(f_means[3])
        fork_mean_val = float(np.mean([m1, m2, m3]))
        var_fork_d = float(np.var([m1, m2, m3], ddof=1))
        sd_fork_d = math.sqrt(var_fork_d)
        se_fork_d = sd_fork_d / math.sqrt(3)
        t_crit_f = stats.t.ppf(0.975, df=2)
        ci_f_lo = fork_mean_val - t_crit_f * se_fork_d
        ci_f_hi = fork_mean_val + t_crit_f * se_fork_d

        fork_rows.append({
            "scale": scale_lbl,
            "d_fork1_pct": round(m1 * 100.0, 3),
            "d_fork2_pct": round(m2 * 100.0, 3),
            "d_fork3_pct": round(m3 * 100.0, 3),
            "d_mean_pct": round(fork_mean_val * 100.0, 3),
            "d_sd_pct": round(sd_fork_d * 100.0, 3),
            "d_se_pct": round(se_fork_d * 100.0, 3),
            "ci95_fork_lo_pct": round(ci_f_lo * 100.0, 3),
            "ci95_fork_hi_pct": round(ci_f_hi * 100.0, 3),
            "ci95_contains_zero": bool(ci_f_lo <= 0 <= ci_f_hi),
        })

        # Phương sai trong-fork tại từng N và trung bình trên 24 N
        var_w_list = []
        d_N_list = []
        for N_val, grp in piv.groupby("N"):
            d_N_list.append(float(grp["log_ratio"].mean()))
            ss_w = grp.groupby("fork")["log_ratio"].apply(lambda x: np.sum((x - x.mean()) ** 2)).sum()
            df_w = len(grp) - grp["fork"].nunique()
            ms_w = ss_w / df_w if df_w > 0 else 0.0
            var_w_list.append(ms_w)

        mean_var_w = float(np.mean(var_w_list))

        # Thành phần không đồng nhất N: Var_N(d_N)/24 trừ phần nhiễu đo ở R đầy đủ
        var_d_N_sample = float(np.var(d_N_list, ddof=1))
        meas_noise_d_N = var_fork_d + mean_var_w / (3.0 * R_max)
        var_N_pure = max(0.0, var_d_N_sample - meas_noise_d_N)
        var_hetero_N = var_N_pure / 24.0

        # Sàn bootstrap-theo-N ở R đầy đủ (lấy mẫu lại N trong thang, B mẫu)
        d_N_arr = np.array(d_N_list)
        boot_idx = rng.integers(0, len(d_N_arr), size=(B, len(d_N_arr)))
        boot_means = d_N_arr[boot_idx].mean(axis=1)
        floor_se = float(np.std(boot_means, ddof=1))
        floor_hw = float((np.percentile(boot_means, 97.5) - np.percentile(boot_means, 2.5)) / 2.0)

        # Lưới (f, m) ∈ {1,2,3} × {1,2,3,5,10}
        m_list = [1, 2, 3, 5, 10] if R_max >= 10 else [1, 2, 3, 5]
        for f in [1, 2, 3]:
            for m in m_list:
                var_meas = mean_var_w / (24.0 * f * m) + var_fork_d / f
                var_total = var_meas + var_hetero_N
                se_total = math.sqrt(var_total)
                pct_meas = (var_meas / var_total) * 100.0 if var_total > 0 else 0.0
                pct_hetero = (var_hetero_N / var_total) * 100.0 if var_total > 0 else 0.0
                hw95_total = 1.96 * se_total
                ci_contains_zero = bool(hw95_total * 100.0 >= abs_d_pct)

                prec_rows.append({
                    "scale": scale_lbl,
                    "n_forks": f,
                    "m_trials": m,
                    "d_obs_pct": round(abs_d_pct, 4),
                    "var_meas": round(var_meas, 10),
                    "var_hetero_N": round(var_hetero_N, 10),
                    "var_total": round(var_total, 10),
                    "se_total_pct": round(se_total * 100.0, 4),
                    "hw95_total_pct": round(hw95_total * 100.0, 4),
                    "pct_meas": round(pct_meas, 1),
                    "pct_hetero_N": round(pct_hetero, 1),
                    "ci_contains_zero": ci_contains_zero,
                    "floor_bootstrap_N_se_pct": round(floor_se * 100.0, 4),
                    "floor_bootstrap_N_hw95_pct": round(floor_hw * 100.0, 4),
                })

    prec_df = pd.DataFrame(prec_rows)
    fork_df = pd.DataFrame(fork_rows)

    # ── Vẽ hình: SE_total theo m cho f = 1, 2, 3, kẻ ngang |d| và sàn bootstrap-N
    fig, axes = plt.subplots(1, len(SCALES), figsize=(14, 4.5), sharey=False)
    styles = [
        {"color": SERIES[0], "marker": "o", "ls": "-", "label": "f = 1 fork"},
        {"color": SERIES[1], "marker": "s", "ls": "--", "label": "f = 2 forks"},
        {"color": SERIES[2], "marker": "^", "ls": "-.", "label": "f = 3 forks"},
    ]

    for ax, S in zip(axes, SCALES):
        scale_lbl = SCALE_LABELS[S]
        sub = prec_df[prec_df["scale"] == scale_lbl]
        if len(sub) == 0:
            continue
        d_val_pct = sub["d_obs_pct"].iloc[0]
        floor_se_pct = sub["floor_bootstrap_N_se_pct"].iloc[0]

        for f_idx, f_val in enumerate([1, 2, 3]):
            sub_f = sub[sub["n_forks"] == f_val]
            ms = sub_f["m_trials"].values
            ses = sub_f["se_total_pct"].values
            st = styles[f_idx]
            ax.plot(ms, ses, color=st["color"], marker=st["marker"],
                    linestyle=st["ls"], lw=1.5, ms=5, label=st["label"])

        # Đường kẻ ngang |d| và sàn bootstrap-N
        ax.axhline(d_val_pct, color="#d9381e", lw=1.2, linestyle="--",
                   label=f"|d| = {d_val_pct:.2f}%")
        ax.axhline(floor_se_pct, color="#555555", lw=1.2, linestyle=":",
                   label=f"Sàn bootstrap-N (SE={floor_se_pct:.2f}%)")

        ax.set_title(f"Scale {scale_lbl} (|d| = {d_val_pct:.2f}%)")
        ax.set_xlabel("Số trial m")
        ax.set_ylabel("SE_total (%)")
        max_m = int(sub["m_trials"].max())
        ax.set_xticks([1, 2, 3, 5, 10] if max_m >= 10 else [1, 2, 3, 5])
        ax.set_xlim(left=0.5, right=max_m + 0.5)
        ax.set_ylim(bottom=0)
        ax.legend()

    fig.suptitle("Độ chính xác phép đo d = log(T7/T10): SE_total theo (f, m) vs. Sàn bootstrap-N", fontsize=11)
    fig.tight_layout()
    save_fig(fig, out_dir / "figures" / "fig_precision_vs_R.png")

    return prec_df, fork_df


# ══════════════════════════════════════════════════════════════════════════════
# 6. Kiểm tra sanity (c=1 và c=30 tại N=2^16)
# ══════════════════════════════════════════════════════════════════════════════

def sanity_check_model(df: pd.DataFrame, model_path: Path) -> list[str]:
    """
    So sánh mean(t_ms) tại N=2^16 cho c=1 và c=30 với giá trị từ runtime_model.csv
    a_ns * N^b / 1e6 → t_ms  →  compare pct diff.
    """
    msgs = []
    if not model_path.exists():
        msgs.append(f"  [WARN] Không tìm thấy {model_path}, bỏ qua sanity check model.")
        return msgs

    model = pd.read_csv(model_path)
    N_check = 65536  # 2^16
    rdf = df[(df["distribution"] == "random") & (df["N"] == N_check)]

    for c in [1, 30]:
        row_m = model[model["cutoff"] == c]
        if len(row_m) == 0:
            msgs.append(f"  [WARN] Không có dòng cutoff={c} trong runtime_model.csv")
            continue
        a_ns = row_m["a_ns"].iloc[0]
        b = row_m["b"].iloc[0]
        t_model_ms = a_ns * (N_check ** b) / 1e6

        sub = rdf[rdf["cutoff"] == c]
        t_measured_ms = sub["t_ms"].mean()
        pct_diff = 100 * abs(t_measured_ms - t_model_ms) / t_model_ms
        status = "OK" if pct_diff <= 5 else "WARN"
        msgs.append(
            f"  c={c}: model={t_model_ms:.4f} ms, measured={t_measured_ms:.4f} ms, "
            f"diff={pct_diff:.2f}% [{status}]"
        )
    return msgs


def sanity_check_n(df: pd.DataFrame) -> list[str]:
    """Kiểm tra n = trial × fork cho mỗi ô."""
    msgs = []
    cell_n = df.groupby(["distribution", "N", "cutoff"]).size().reset_index(name="count")
    n_forks = df["fork"].nunique()
    # trial count per fork per cell
    trial_counts = df.groupby(["distribution", "N", "cutoff", "fork"])["trial"].nunique()
    expected = trial_counts.groupby(["distribution", "N", "cutoff"]).sum()

    mismatches = cell_n.set_index(["distribution", "N", "cutoff"])["count"].compare(expected)
    if len(mismatches) == 0:
        msgs.append(f"  n = trial×fork: tất cả {len(cell_n)} ô khớp.")
    else:
        msgs.append(f"  [WARN] {len(mismatches)} ô không khớp n = trial×fork:")
        msgs.append(str(mismatches.head(10)))
    return msgs


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Thống kê mô tả cho thí nghiệm CUTOFF (T01).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--results", default="results_run3",
                        help="Thư mục kết quả chứa raw_fork*.csv")
    parser.add_argument("--out", default="results_run3/analysis_v2",
                        help="Thư mục đầu ra")
    parser.add_argument("--B", type=int, default=2000,
                        help="Số mẫu bootstrap")
    parser.add_argument("--seed", type=int, default=20261029,
                        help="Seed bootstrap")
    args = parser.parse_args()

    results_dir = Path(args.results)
    out_dir = Path(args.out)
    out_tables = out_dir / "tables"
    out_tables.mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)

    print("=== descriptive.py ===")
    print(f"Kết quả: {results_dir}  |  Đầu ra: {out_dir}  |  B={args.B}  |  seed={args.seed}")
    print()

    # ── Nạp dữ liệu ──
    print("[1/6] Nạp dữ liệu...")
    df = load_raw(results_dir)
    print(f"  Tổng hàng sau gc-filter: {len(df):,} (kỳ vọng 81 720)")

    # ── Bảng thiết kế ──
    print("[1/6] Bảng thiết kế...")
    design_df = make_design_table(df)
    save_csv(design_df, out_tables / "design_table.csv")
    total_row = design_df[design_df["distribution"] == "TOTAL"]
    print(f"  Tổng lần đo = {total_row['n_measurements'].values[0]:,}")

    # ── Thống kê mô tả random ──
    print("[2/6] Thống kê mô tả random...")
    desc_rnd = make_desc_random(df)
    save_csv(desc_rnd, out_tables / "desc_random.csv")

    # ── Thống kê mô tả other ──
    print("[2/6] Thống kê mô tả phân bố khác...")
    desc_oth = make_desc_other(df)
    save_csv(desc_oth, out_tables / "desc_other.csv")

    # ── Phân rã phương sai ──
    print("[3/6] Phân rã phương sai (ANOVA method of moments)...")
    vc_cells, vc_summary = make_variance_components(df)
    save_csv(vc_cells, out_tables / "variance_components.csv")
    save_csv(vc_summary, out_tables / "variance_components_summary.csv")
    print("  Tóm tắt phân rã phương sai:")
    print(vc_summary.to_string(index=False))

    # ── Lợi ích ghép cặp ──
    print("[4/6] Lợi ích ghép cặp (phản thực tế total & within)...")
    gain_cells, gain_summary, between_summary = make_pairing_gain(df)
    save_csv(gain_cells, out_tables / "pairing_gain.csv")
    save_csv(gain_summary, out_tables / "pairing_gain_summary.csv")
    save_csv(between_summary, out_tables / "pairing_between_summary.csv")
    print("  Tóm tắt lợi ích ghép cặp:")
    print(gain_summary.to_string(index=False))
    print("  Tóm tắt triệt tiêu SD giữa-JVM:")
    print(between_summary.to_string(index=False))

    # ── Precision vs R ──
    print(f"[5/6] Precision vs R (phân rã phương sai d, B={args.B}, seed={args.seed})...")
    prec_df, fork_df = make_precision_vs_R(df, args.B, args.seed, out_dir)
    save_csv(prec_df, out_tables / "precision_vs_R.csv")
    save_csv(fork_df, out_tables / "precision_d_by_fork.csv")
    print("  Phép kiểm d theo từng fork riêng (df=2):")
    print(fork_df.to_string(index=False))
    print("  Tóm tắt precision vs R:")
    for S in SCALES:
        scale_lbl = SCALE_LABELS[S]
        sub = prec_df[prec_df["scale"] == scale_lbl]
        d_val = sub["d_obs_pct"].iloc[0]
        f1_m1 = sub[(sub["n_forks"] == 1) & (sub["m_trials"] == 1)]
        f3_full = sub[(sub["n_forks"] == 3) & (sub["m_trials"] == sub["m_trials"].max())]
        se_f1_m1 = f1_m1["se_total_pct"].iloc[0] if len(f1_m1) else 0.0
        z_f1_m1 = f1_m1["ci_contains_zero"].iloc[0] if len(f1_m1) else False
        se_f3_full = f3_full["se_total_pct"].iloc[0] if len(f3_full) else 0.0
        pct_h = f3_full["pct_hetero_N"].iloc[0] if len(f3_full) else 0.0
        floor_se = f3_full["floor_bootstrap_N_se_pct"].iloc[0] if len(f3_full) else 0.0
        print(f"    Scale {scale_lbl} (|d|={d_val:.2f}%): "
              f"f=1,m=1 SE={se_f1_m1:.3f}% (0 in CI: {z_f1_m1}) | "
              f"f=3,full SE={se_f3_full:.3f}% (hetero={pct_h:.1f}%, floor={floor_se:.3f}%)")

    # ── Sanity checks ──
    print("[6/6] Sanity checks...")
    model_path = results_dir / "analysis" / "tables" / "runtime_model.csv"
    msgs_model = sanity_check_model(df, model_path)
    for m in msgs_model:
        print(m)
    msgs_n = sanity_check_n(df)
    for m in msgs_n:
        print(m)

    print()
    print("=== Hoàn tất ===")
    print(f"Tất cả file đã lưu vào {out_dir}")


if __name__ == "__main__":
    main()
