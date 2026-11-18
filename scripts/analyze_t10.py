#!/usr/bin/env python3
"""
scripts/analyze_t10.py — Phân tích giai đoạn 2 theo Hợp đồng đăng ký trước T09 (H1–H17, H10b).

Tuân thủ:
  - Hợp đồng: handoff/preregistration/T09_contract.md (commit c3e2b7f)
  - Định nghĩa đã chốt: handoff/tasks/T10_analysis.md §2
  - Quy tắc A–E trong handoff/README.md
  - Nhãn đầu ra: [ĐK] (kiểm định đã đăng ký), [KP] (khám phá), [MT] (mô tả)
  - Bootstrap mặc định: B = 10 000, seed gốc = 20261117 (mỗi bảng có RNG riêng, ghi vào run_log.txt)

Cách chạy (từ thư mục gốc dự án):
    python scripts/analyze_t10.py --self-check
    python scripts/analyze_t10.py --out results_phase2/analysis
"""
from __future__ import annotations

import argparse
import io
import math
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from scripts.analyze import Core, cluster_boot_means, holm, scale_of, slabel
from scripts.doubling_analyze import (
    analyze_a5_same_tree_control,
    compute_geometric_means,
    compute_r_and_rbar,
)
from scripts.predict_t09 import GRID_35, compress_range
from scripts.tree_features import tree_stats
from scripts.validate_cost_model import calibrate_alpha_c1, load_all_data, validate_2e19_loso

# ──────────────────────────────────────────────────────────────── hằng số thiết kế
DEFAULT_B = 10_000
DEFAULT_SEED = 20261117
PHASE1_SEED = 20261027
NEAR_TOL = 0.02

S1_SCALES = [2**12, 2**14, 2**16, 2**18, 2**19]
S1_SCALE_LABELS = [slabel(s) for s in S1_SCALES]
THREE_SCALES = [2**12, 2**16, 2**19]
THREE_SCALE_LABELS = [slabel(s) for s in THREE_SCALES]
NEW_SCALES = [2**14, 2**18]
NEW_SCALE_LABELS = [slabel(s) for s in NEW_SCALES]
S2_DISTS = ["sorted", "reversed", "nearly_sorted", "few_distinct"]
D3_KEYS = ["integer", "double", "int"]
JMH_NS = [4096, 65536, 524288]
JMH_CUTOFFS = [1, 7, 10, 30]

# Số tham chiếu Quy tắc A (T10 §5)
REF_COUNTS = {
    "S1": 168_000,
    "S2": 140_400,
    "DV2": 4_590,
    "D3_integer": 66_600,
    "D3_double": 66_600,
    "D3_int": 66_600,
    "JMH_rows": 12,
    "JMH_samples": 30,
}
REF_ALPHA = {"2^14": 8.931288, "2^18": 10.650196}
REF_GD1_CSTAR = {"2^12": 40, "2^16": 31, "2^19": 27}
REF_GD1_RSTAR = {"2^12": 0.848, "2^16": 0.888, "2^19": 0.918}
REF_GD1_LOSO_2E19_RMSE = 0.0029


class TeeStream:
    """Ghi đồng thời ra console và tệp log UTF-8."""

    def __init__(self, stream, log_file):
        self.stream = stream
        self.log_file = log_file

    def write(self, data):
        self.stream.write(data)
        self.log_file.write(data)

    def flush(self):
        self.stream.flush()
        self.log_file.flush()


# ──────────────────────────────────────────────────────────────── nạp dữ liệu & lõi thống kê

def load_raw_dir(directory: Path, label_name: str, expected_rows: int | None = None,
                 check_k1_no_gc: bool = True, forks: list[int] | None = None) -> pd.DataFrame:
    """Đọc raw_fork*.csv, kiểm tra Quy tắc A (kích thước, batch_k == 1, gc == false), lọc GC."""
    files = sorted(directory.glob("raw_fork*.csv"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy raw_fork*.csv trong {directory}")
    df = pd.concat([pd.read_csv(p) for p in files], ignore_index=True)
    n_raw = len(df)
    gc_bool = df["gc_during_run"].astype(str).str.lower().eq("true")
    n_gc = int(gc_bool.sum())
    n_k_ne1 = int((df["batch_k"] != 1).sum())

    if expected_rows is not None:
        print(f"  [Quy tắc A] {label_name}: đọc {n_raw:,} hàng | tham chiếu {expected_rows:,} | chênh {n_raw - expected_rows:+d} | GC={n_gc} | batch_k!=1: {n_k_ne1}")
        assert n_raw == expected_rows, f"DỪNG: {label_name} có {n_raw} hàng, tham chiếu {expected_rows}"
    if check_k1_no_gc:
        assert n_gc == 0, f"DỪNG: {label_name} có {n_gc} hàng gc_during_run=true"
        assert n_k_ne1 == 0, f"DỪNG: {label_name} có {n_k_ne1} hàng batch_k != 1"

    df = df[~gc_bool].copy()
    if forks is not None:
        df = df[df["fork"].isin(forks)].copy()
    df["gc_during_run"] = False
    df["scale"] = df["N"].map(scale_of)
    df["scale_label"] = df["scale"].map(slabel)
    df["logt"] = np.log(df["time_ns"].astype(float))
    return df


def compute_paired_A(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Tính lr(f, N, t, c) = ln T(c) - ln T(1) ghép cặp trong cùng (fork, distribution, N, trial),
    và A(f, N, c) = trung bình lr qua các trial.
    Trả về (obs_with_lr, df_A).
    """
    key = ["fork", "distribution", "N", "trial"]
    base = df[df["cutoff"] == 1][key + ["logt"]].rename(columns={"logt": "logt1"})
    obs = df.merge(base, on=key, how="inner")
    assert len(obs) == len(df), f"Mất hàng khi ghép cặp c=1: {len(obs)} vs {len(df)}"
    obs["lr"] = obs["logt"] - obs["logt1"]
    df_A = (
        obs.groupby(["distribution", "scale", "scale_label", "fork", "N", "cutoff"], as_index=False)
        .agg(A=("lr", "mean"), n_trials=("lr", "size"))
    )
    return obs, df_A


def build_A_tensor(df_A_sub: pd.DataFrame) -> tuple[np.ndarray, list[int], list[int], list[int]]:
    """
    Chuyển df_A của một (distribution, scale) thành mảng 3D shape (F, nN, nC).
    Trả về (A_arr, forks, Ns, cutoffs).
    """
    forks = sorted(int(x) for x in df_A_sub["fork"].unique())
    Ns = sorted(int(x) for x in df_A_sub["N"].unique())
    cutoffs = sorted(int(x) for x in df_A_sub["cutoff"].unique())
    f_idx = {f: i for i, f in enumerate(forks)}
    n_idx = {n: i for i, n in enumerate(Ns)}
    c_idx = {c: i for i, c in enumerate(cutoffs)}

    arr = np.full((len(forks), len(Ns), len(cutoffs)), np.nan, dtype=float)
    for row in df_A_sub.itertuples(index=False):
        arr[f_idx[int(row.fork)], n_idx[int(row.N)], c_idx[int(row.cutoff)]] = float(row.A)
    assert not np.isnan(arr).any(), "Thiếu ô trong tensor A(f, N, c)"
    return arr, forks, Ns, cutoffs


def boot_two_tier(A: np.ndarray, B: int, rng: np.random.Generator,
                  chunk: int = 1000, rng_fork: np.random.Generator | None = None) -> np.ndarray:
    """
    Bootstrap hai tầng (§0 & §2):
      A: shape (F, nN, nC).
      Mỗi lần lặp b: rút F fork có hoàn lại, rút độc lập nN giá trị N có hoàn lại;
      thống kê = trung bình A trên mọi cặp (f, N) trong tích hai mẫu rút.
    Trả về shape (B, nC).
    """
    F, nN, nC = A.shape
    rf = rng_fork if rng_fork is not None else rng
    has_nan = bool(np.isnan(A).any())
    out = np.empty((B, nC), dtype=float)
    for s in range(0, B, chunk):
        b = min(chunk, B - s)
        n_idx = rng.integers(0, nN, size=(b, nN))
        f_idx = rf.integers(0, F, size=(b, F))
        if not has_nan:
            w_f = np.zeros((b, F), dtype=float)
            np.add.at(w_f, (np.arange(b)[:, None], f_idx), 1.0 / F)
            w_n = np.zeros((b, nN), dtype=float)
            np.add.at(w_n, (np.arange(b)[:, None], n_idx), 1.0 / nN)
            out[s:s + b] = np.einsum("bf,bn,fnc->bc", w_f, w_n, A, optimize=True)
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                for i in range(b):
                    sub = A[f_idx[i]][:, n_idx[i], :]
                    out[s + i] = np.nanmean(sub, axis=(0, 1))
    return out


def boot_one_tier(A: np.ndarray, B: int, rng: np.random.Generator, chunk: int = 1000) -> np.ndarray:
    """
    Bootstrap một tầng: giữ đủ F fork (trung bình A theo fork trước -> M shape (nN, nC)),
    rút lại N bằng cluster_boot_means (import từ scripts/analyze.py).
    """
    M = np.nanmean(A, axis=0)  # (nN, nC)
    return cluster_boot_means(M, B, rng, chunk=chunk)


def summarize_group_r(df_A: pd.DataFrame, obs: pd.DataFrame, B: int,
                      seed_two: int, seed_one: int, label: str = "[ĐK]") -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Tính r(c), CI hai tầng, CI một tầng, c*, tập gần tối ưu, top-3 argmin bootstrap hai tầng
    cho mọi cặp (distribution, scale) trong df_A.
    """
    rng2 = np.random.default_rng(seed_two)
    rng1 = np.random.default_rng(seed_one)

    r_rows = []
    best_rows = []
    tensors = {}

    groups = sorted(df_A[["distribution", "scale", "scale_label"]].drop_duplicates().itertuples(index=False),
                    key=lambda x: (x.distribution, x.scale))

    for g in groups:
        d, sc, scl = g.distribution, int(g.scale), g.scale_label
        subA = df_A[(df_A["distribution"] == d) & (df_A["scale"] == sc)]
        subObs = obs[(obs["distribution"] == d) & (obs["scale"] == sc)]
        A, forks, Ns, cutoffs = build_A_tensor(subA)
        tensors[(d, scl)] = (A, forks, Ns, cutoffs)

        point_lr = A.mean(axis=(0, 1))
        point_r = np.exp(point_lr)

        bt2 = boot_two_tier(A, B, rng2)
        lo2, hi2 = np.percentile(bt2, [2.5, 97.5], axis=0)
        bt1 = boot_one_tier(A, B, rng1)
        lo1, hi1 = np.percentile(bt1, [2.5, 97.5], axis=0)

        obs_counts = subObs.groupby("cutoff")["lr"].size().to_dict()

        for j, c in enumerate(cutoffs):
            r_rows.append({
                "distribution": d,
                "scale": scl,
                "cutoff": c,
                "r": float(point_r[j]),
                "ci2_lo": float(math.exp(lo2[j])),
                "ci2_hi": float(math.exp(hi2[j])),
                "ci1_lo": float(math.exp(lo1[j])),
                "ci1_hi": float(math.exp(hi1[j])),
                "n_N": len(Ns),
                "n_forks": len(forks),
                "n_obs": int(obs_counts[c]),
                "label": label,
            })

        best_idx = int(np.argmin(point_r))
        c_star = cutoffs[best_idx]
        r_star = float(point_r[best_idx])
        near_list = [cutoffs[j] for j in range(len(cutoffs)) if point_r[j] <= (1.0 + NEAR_TOL) * r_star]

        # Tần suất argmin trong bootstrap hai tầng [KP]
        am = np.argmin(bt2, axis=1)
        cnt = np.bincount(am, minlength=len(cutoffs)) / float(B)
        top3_idx = np.argsort(-cnt)[:3]
        top3_str = ", ".join(f"{cutoffs[i]}:{cnt[i] * 100:.1f}%" for i in top3_idx if cnt[i] > 0)

        best_rows.append({
            "distribution": d,
            "scale": scl,
            "c_star": c_star,
            "r_star": r_star,
            "ci2_lo": float(math.exp(lo2[best_idx])),
            "ci2_hi": float(math.exp(hi2[best_idx])),
            "ci1_lo": float(math.exp(lo1[best_idx])),
            "ci1_hi": float(math.exp(hi1[best_idx])),
            "near_optimal_2pct": compress_range(near_list),
            "near_optimal_list": near_list,
            "boot2_argmin_top3_kp": top3_str,
            "label": label,
        })

    return pd.DataFrame(r_rows), pd.DataFrame(best_rows), tensors


def compute_h2_t7_t10(tensors: dict, scales: list[str], B: int,
                      seed_two: int, seed_one: int) -> pd.DataFrame:
    """
    H2: d = ln(T7/T10) = A(.,.,7) - A(.,.,10).
    p một phía = (1 + #{b: d_b <= 0}) / (B + 1); Holm trên 5 thang.
    ĐẠT ở thang khi p_holm < 0.05 VÀ ci2_lo > 1.0.
    """
    rng2 = np.random.default_rng(seed_two)
    rng1 = np.random.default_rng(seed_one)
    rows = []
    for scl in scales:
        A, forks, Ns, cutoffs = tensors[("random", scl)]
        i7 = cutoffs.index(7)
        i10 = cutoffs.index(10)
        D = (A[:, :, i7] - A[:, :, i10])[:, :, None]  # (F, nN, 1)
        d_point = float(D.mean())

        bt2 = boot_two_tier(D, B, rng2)[:, 0]
        bt1 = boot_one_tier(D, B, rng1)[:, 0]

        p_raw = float((1 + np.sum(bt2 <= 0.0)) / (B + 1))
        lo2, hi2 = np.percentile(bt2, [2.5, 97.5])
        lo1, hi1 = np.percentile(bt1, [2.5, 97.5])

        rows.append({
            "scale": scl,
            "d_log": d_point,
            "ratio_T7_T10": float(math.exp(d_point)),
            "ci2_lo": float(math.exp(lo2)),
            "ci2_hi": float(math.exp(hi2)),
            "ci1_lo": float(math.exp(lo1)),
            "ci1_hi": float(math.exp(hi1)),
            "p_raw": p_raw,
            "n_forks": len(forks),
            "n_N": len(Ns),
            "label": "[ĐK]",
        })
    df_h2 = pd.DataFrame(rows)
    df_h2["p_holm"] = holm(df_h2["p_raw"].to_numpy())
    df_h2["pass_scale"] = (df_h2["p_holm"] < 0.05) & (df_h2["ci2_lo"] > 1.0)
    return df_h2


def compute_pooled_random(tensors: dict, scales: list[str], B: int,
                          seed_two: int, seed_one: int) -> pd.DataFrame:
    """
    [MT] r gộp 5 thang random theo c: trung bình nhân trên mọi N của 5 thang (120 N);
    CI hai tầng rút F fork chung cho cả 5 thang, rồi rút 24 N độc lập trong từng thang.
    """
    rng2 = np.random.default_rng(seed_two)
    rng1 = np.random.default_rng(seed_one)

    As = []
    cutoffs = None
    forks_ref = None
    total_N = 0
    for scl in scales:
        A, forks, Ns, cuts = tensors[("random", scl)]
        if cutoffs is None:
            cutoffs = cuts
            forks_ref = forks
        else:
            assert cuts == cutoffs and forks == forks_ref
        As.append(A)
        total_N += len(Ns)

    F = len(forks_ref)
    nC = len(cutoffs)
    nS = len(As)
    point_lr = np.mean([A.mean(axis=(0, 1)) for A in As], axis=0)

    # Hai tầng: rút fork chung, rút N riêng từng thang
    bt2 = np.zeros((B, nC), dtype=float)
    chunk = 1000
    for s in range(0, B, chunk):
        b = min(chunk, B - s)
        f_idx = rng2.integers(0, F, size=(b, F))
        w_f = np.zeros((b, F), dtype=float)
        np.add.at(w_f, (np.arange(b)[:, None], f_idx), 1.0 / F)
        acc = np.zeros((b, nC), dtype=float)
        for A in As:
            nN = A.shape[1]
            n_idx = rng2.integers(0, nN, size=(b, nN))
            w_n = np.zeros((b, nN), dtype=float)
            np.add.at(w_n, (np.arange(b)[:, None], n_idx), 1.0 / nN)
            acc += np.einsum("bf,bn,fnc->bc", w_f, w_n, A, optimize=True)
        bt2[s:s + b] = acc / nS

    # Một tầng: giữ đủ fork, rút N riêng từng thang
    bt1 = np.zeros((B, nC), dtype=float)
    for A in As:
        bt1 += boot_one_tier(A, B, rng1)
    bt1 /= nS

    lo2, hi2 = np.percentile(bt2, [2.5, 97.5], axis=0)
    lo1, hi1 = np.percentile(bt1, [2.5, 97.5], axis=0)

    rows = []
    for j, c in enumerate(cutoffs):
        rows.append({
            "cutoff": c,
            "r": float(math.exp(point_lr[j])),
            "ci2_lo": float(math.exp(lo2[j])),
            "ci2_hi": float(math.exp(hi2[j])),
            "ci1_lo": float(math.exp(lo1[j])),
            "ci1_hi": float(math.exp(hi1[j])),
            "n_N": total_N,
            "n_forks": F,
            "label": "[MT]",
        })
    return pd.DataFrame(rows)


def compute_m2_validation(raw_s1: pd.DataFrame, df_r_s1: pd.DataFrame, df_best_s1: pd.DataFrame,
                          pred_m2_path: Path, coef_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    H10 & H10b: thẩm định mô hình M2 trên 2^14 và 2^18.
      - H10: đọc r_hat_interp trực tiếp từ T09_predictions_m2.csv (không tính lại),
             r_hat_scale(c) = exp(mean_N ln r_hat_interp(N, c)).
      - H10b: hiệu chỉnh alpha_calib từ hàng c = 1 của thang bằng calibrate_alpha_c1()
              (import từ validate_cost_model.py), với T(N, 1) = exp(mean_{f,t} ln time_ns)
              đúng định nghĩa cost_model.py, đặc trưng cây từ tree_stats() đúng predict_t09.py.
      - RMSE tính trên đủ 35 CUTOFF (kể cả c = 1, sai số 0) đúng T10 §2.
    """
    df_pred = pd.read_csv(pred_m2_path)
    df_coef = pd.read_csv(coef_path).set_index("parameter")["coef"].to_dict()
    w1 = float(df_coef["ML_b1"])
    w2 = float(df_coef["ML_b2"])
    w3 = float(df_coef["ML_b3"])
    beta = float(df_coef["exchanges"])
    alpha12 = float(df_coef["ML_b456_12"])
    alpha16 = float(df_coef["ML_b456_16"])
    alpha19 = float(df_coef["ML_b456_19"])
    alpha_interp_map = {
        "2^14": alpha12 + (alpha16 - alpha12) * (2.0 / 4.0),
        "2^18": alpha16 + (alpha19 - alpha16) * (2.0 / 3.0),
    }

    # T(N, c) đúng cost_model.py: exp(mean(log(time_ns))) trên mọi fork và trial
    t_grp = (
        raw_s1.groupby(["scale_label", "N", "cutoff"], as_index=False)["logt"]
        .mean()
        .assign(T=lambda x: np.exp(x["logt"]))
    )

    val_rows = []
    sum_rows = []

    for scl in NEW_SCALE_LABELS:
        sub_pred = df_pred[df_pred["scale"] == scl].copy()
        c_star_m2_vals = sub_pred["c_star_M2_scale"].unique()
        assert len(c_star_m2_vals) == 1
        c_star_m2 = int(c_star_m2_vals[0])

        # H10: trung bình nhân theo 24 N từ cột r_hat_interp đã đăng ký
        rhat_interp_scale = (
            sub_pred.groupby("cutoff")["r_hat_interp"]
            .apply(lambda s: float(math.exp(np.mean(np.log(s.to_numpy(dtype=float))))))
            .to_dict()
        )

        # H10b: hiệu chỉnh alpha_calib trên hàng c = 1 của thang
        ns = sorted(int(x) for x in sub_pred["N"].unique())
        assert len(ns) == 24, f"Kỳ vọng 24 N ở {scl}, thực tế {len(ns)}"
        t_c1_sub = t_grp[(t_grp["scale_label"] == scl) & (t_grp["cutoff"] == 1)].set_index("N")["T"]
        assert set(t_c1_sub.index) == set(ns), f"Tập N ở {scl} không khớp T09_predictions_m2.csv"

        T_c1_list, base_c1_list, ml456_c1_list = [], [], []
        ts_cache = {}
        for n in ns:
            ts1 = tree_stats(n, 1)
            ts_cache[(n, 1)] = ts1
            base1 = w1 * ts1[6] + w2 * ts1[7] + w3 * ts1[8] + beta * (ts1[5] / 2.0)
            ml456_1 = ts1[9] + ts1[10] + ts1[11]
            T_c1_list.append(float(t_c1_sub.loc[n]))
            base_c1_list.append(base1)
            ml456_c1_list.append(ml456_1)

        alpha_calib = calibrate_alpha_c1(T_c1_list, base_c1_list, ml456_c1_list)

        # Tính r_hat_calib(N, c) rồi trung bình nhân theo N
        rhat_calib_by_c = {c: [] for c in GRID_35}
        for n in ns:
            ts1 = ts_cache[(n, 1)]
            T1_hat = (
                w1 * ts1[6] + w2 * ts1[7] + w3 * ts1[8]
                + beta * (ts1[5] / 2.0)
                + alpha_calib * (ts1[9] + ts1[10] + ts1[11])
            )
            for c in GRID_35:
                ts = ts_cache.get((n, c)) or tree_stats(n, c)
                T_hat = (
                    w1 * ts[6] + w2 * ts[7] + w3 * ts[8]
                    + beta * (ts[5] / 2.0)
                    + alpha_calib * (ts[9] + ts[10] + ts[11])
                )
                rhat_calib_by_c[c].append(T_hat / T1_hat)

        rhat_calib_scale = {
            c: float(math.exp(np.mean(np.log(rhat_calib_by_c[c]))))
            for c in GRID_35
        }

        # Đối chiếu với r đo (từ p2_r_by_cutoff)
        meas_sub = df_r_s1[(df_r_s1["distribution"] == "random") & (df_r_s1["scale"] == scl)].set_index("cutoff")["r"]
        best_row = df_best_s1[(df_best_s1["distribution"] == "random") & (df_best_s1["scale"] == scl)].iloc[0]

        errs_interp = []
        errs_calib = []
        for c in GRID_35:
            rm = float(meas_sub.loc[c])
            rhi = float(rhat_interp_scale[c])
            rhc = float(rhat_calib_scale[c])
            ei = rhi - rm
            ec = rhc - rm
            errs_interp.append(ei)
            errs_calib.append(ec)
            val_rows.append({
                "scale": scl,
                "cutoff": c,
                "r_meas": rm,
                "r_hat_interp": rhi,
                "r_hat_calib": rhc,
                "err_interp": ei,
                "err_calib": ec,
                "label": "[ĐK]",
            })

        rmse_interp = float(np.sqrt(np.mean(np.square(errs_interp))))
        rmse_calib = float(np.sqrt(np.mean(np.square(errs_calib))))
        near_list = best_row["near_optimal_list"]
        in_near = bool(c_star_m2 in near_list)
        pass_h10 = bool((rmse_interp <= 0.012) and in_near)
        pass_h10b = bool(rmse_calib <= 0.012)

        sum_rows.append({
            "scale": scl,
            "rmse_interp": rmse_interp,
            "rmse_calib": rmse_calib,
            "c_star_M2": c_star_m2,
            "c_star_meas": int(best_row["c_star"]),
            "near_optimal_2pct_meas": best_row["near_optimal_2pct"],
            "c_star_M2_in_near_opt": in_near,
            "alpha_interp": alpha_interp_map[scl],
            "alpha_calib": alpha_calib,
            "rmse_gd1_loso_2e19_ref": REF_GD1_LOSO_2E19_RMSE,
            "pass_H10": pass_h10,
            "pass_H10b": pass_h10b,
            "label": "[ĐK]",
        })

    return pd.DataFrame(val_rows), pd.DataFrame(sum_rows)


def parse_jmh_float(val) -> float:
    if isinstance(val, (int, float, np.number)):
        return float(val)
    s = str(val).strip()
    try:
        return float(s)
    except ValueError:
        return float(s.replace(",", "."))


def compute_jmh_h17(jmh_path: Path, obs_s1: pd.DataFrame, raw_s1: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """
    H17: so sánh r_JMH(N, c) = Score(N, c)/Score(N, 1) với r_Run5(N, c) của ĐÚNG N đó trong S1.
    Thứ tự Score(30) < Score(10) < Score(7) < Score(1) ở cả 3 N.
    """
    df_j = pd.read_csv(jmh_path)
    # Tìm tên cột an toàn
    col_score = [c for c in df_j.columns if c.strip() == "Score"][0]
    col_err = [c for c in df_j.columns if "Score Error" in c][0]
    col_samples = [c for c in df_j.columns if c.strip() == "Samples"][0]
    col_n = [c for c in df_j.columns if c.strip().lower().endswith("n") and "param" in c.lower()][0]
    col_c = [c for c in df_j.columns if "cutoff" in c.lower() and "param" in c.lower()][0]
    col_unit = [c for c in df_j.columns if c.strip() == "Unit"][0]

    n_rows = len(df_j)
    samples_set = set(int(parse_jmh_float(x)) for x in df_j[col_samples])
    print(f"  [Quy tắc A] JMH: đọc {n_rows} hàng (tham chiếu {REF_COUNTS['JMH_rows']}), Samples={sorted(samples_set)} (tham chiếu [{REF_COUNTS['JMH_samples']}]), Unit={df_j[col_unit].unique().tolist()}")
    assert n_rows == REF_COUNTS["JMH_rows"], f"DỪNG: JMH có {n_rows} hàng, tham chiếu {REF_COUNTS['JMH_rows']}"
    assert samples_set == {REF_COUNTS["JMH_samples"]}, f"DỪNG: JMH Samples={samples_set}"

    df_j = df_j.copy()
    df_j["_N"] = df_j[col_n].astype(int)
    df_j["_c"] = df_j[col_c].astype(int)
    df_j["_score"] = df_j[col_score].map(parse_jmh_float)
    df_j["_err"] = df_j[col_err].map(parse_jmh_float)
    df_j["_samples"] = df_j[col_samples].map(lambda x: int(parse_jmh_float(x)))

    # Tính r_Run5(N, c) và T_Run5_us(N, c) trên đúng 3 giá trị N trong S1
    obs_sub = obs_s1[obs_s1["N"].isin(JMH_NS) & obs_s1["cutoff"].isin(JMH_CUTOFFS)]
    r_run5_map = (
        obs_sub.groupby(["N", "cutoff"])["lr"]
        .mean()
        .map(math.exp)
        .to_dict()
    )
    t_run5_us_map = (
        raw_s1[raw_s1["N"].isin(JMH_NS) & raw_s1["cutoff"].isin(JMH_CUTOFFS)]
        .groupby(["N", "cutoff"])["logt"]
        .mean()
        .map(lambda x: math.exp(x) / 1000.0)
        .to_dict()
    )

    rows = []
    all_diff_ok = True
    all_order_ok = True

    for n in JMH_NS:
        sub = df_j[df_j["_N"] == n].set_index("_c")
        s1 = float(sub.loc[1, "_score"])
        s7 = float(sub.loc[7, "_score"])
        s10 = float(sub.loc[10, "_score"])
        s30 = float(sub.loc[30, "_score"])
        order_ok = bool(s30 < s10 < s7 < s1)
        if not order_ok:
            all_order_ok = False

        for c in JMH_CUTOFFS:
            sc_val = float(sub.loc[c, "_score"])
            err_val = float(sub.loc[c, "_err"])
            r_jmh = sc_val / s1
            r_run5 = float(r_run5_map[(n, c)])
            diff = r_jmh - r_run5
            abs_diff = abs(diff)
            pass_cell = True if c == 1 else bool(abs_diff <= 0.02)
            if c != 1 and not pass_cell:
                all_diff_ok = False
            rows.append({
                "N": n,
                "cutoff": c,
                "jmh_score_us": sc_val,
                "jmh_score_err_999_us": err_val,
                "jmh_samples": int(sub.loc[c, "_samples"]),
                "r_jmh": r_jmh,
                "r_run5": r_run5,
                "diff_r": diff,
                "abs_diff": abs_diff,
                "pass_diff_le_002": pass_cell,
                "order_30_10_7_1_ok": order_ok,
                "run5_geom_time_us_kp": float(t_run5_us_map[(n, c)]),
                "note_kp": "Khác phiên đo, thời gian tuyệt đối chỉ mang tính mô tả [KP]",
                "label": "[ĐK]" if c != 1 else "[MT]",
            })

    return pd.DataFrame(rows), bool(all_diff_ok and all_order_ok)


def boot_d3_diff_pair(A1: np.ndarray, A2: np.ndarray, B: int, rng: np.random.Generator, chunk: int = 1000) -> np.ndarray:
    """
    Bootstrap hiệu r_1 - r_2 giữa hai kiểu khóa D3 ở cùng thang (§2):
      A1: shape (F1, nN) tại c*_1 cố định; A2: shape (F2, nN) tại c*_2 cố định.
      Fork rút ĐỘC LẬP cho từng kiểu khóa, N rút CHUNG (cùng chỉ số cho cả hai).
    Trả về mảng hiệu (r_1_b - r_2_b) shape (B,).
    """
    F1, nN = A1.shape
    F2, nN2 = A2.shape
    assert nN == nN2
    out = np.empty(B, dtype=float)
    for s in range(0, B, chunk):
        b = min(chunk, B - s)
        n_idx = rng.integers(0, nN, size=(b, nN))
        f1_idx = rng.integers(0, F1, size=(b, F1))
        f2_idx = rng.integers(0, F2, size=(b, F2))

        w_n = np.zeros((b, nN), dtype=float)
        np.add.at(w_n, (np.arange(b)[:, None], n_idx), 1.0 / nN)
        w_f1 = np.zeros((b, F1), dtype=float)
        np.add.at(w_f1, (np.arange(b)[:, None], f1_idx), 1.0 / F1)
        w_f2 = np.zeros((b, F2), dtype=float)
        np.add.at(w_f2, (np.arange(b)[:, None], f2_idx), 1.0 / F2)

        m1 = np.einsum("bf,bn,fn->b", w_f1, w_n, A1, optimize=True)
        m2 = np.einsum("bf,bn,fn->b", w_f2, w_n, A2, optimize=True)
        out[s:s + b] = np.exp(m1) - np.exp(m2)
    return out


def boot_d3_h15(A_int_12: np.ndarray, A_int_19: np.ndarray,
                A_intg_12: np.ndarray, A_intg_19: np.ndarray,
                B: int, rng: np.random.Generator, chunk: int = 1000) -> tuple[np.ndarray, np.ndarray]:
    """
    Bootstrap tham khảo cho H15:
      Trong cùng kiểu khóa: cùng F fork chạy cả 2^12 và 2^19 -> rút chung f_idx theo kiểu khóa,
      độc lập giữa int[] và Integer[]. N rút độc lập cho 2^12 và 2^19, nhưng chung giữa hai kiểu khóa.
    Trả về (diff_vs_half_b, ratio_b).
    """
    F1, nN12 = A_int_12.shape
    _, nN19 = A_int_19.shape
    F2 = A_intg_12.shape[0]
    assert A_intg_12.shape == (F2, nN12) and A_intg_19.shape == (F2, nN19)

    diff_half = np.empty(B, dtype=float)
    ratio = np.empty(B, dtype=float)
    for s in range(0, B, chunk):
        b = min(chunk, B - s)
        n12_idx = rng.integers(0, nN12, size=(b, nN12))
        n19_idx = rng.integers(0, nN19, size=(b, nN19))
        f1_idx = rng.integers(0, F1, size=(b, F1))
        f2_idx = rng.integers(0, F2, size=(b, F2))

        w_n12 = np.zeros((b, nN12), dtype=float)
        np.add.at(w_n12, (np.arange(b)[:, None], n12_idx), 1.0 / nN12)
        w_n19 = np.zeros((b, nN19), dtype=float)
        np.add.at(w_n19, (np.arange(b)[:, None], n19_idx), 1.0 / nN19)
        w_f1 = np.zeros((b, F1), dtype=float)
        np.add.at(w_f1, (np.arange(b)[:, None], f1_idx), 1.0 / F1)
        w_f2 = np.zeros((b, F2), dtype=float)
        np.add.at(w_f2, (np.arange(b)[:, None], f2_idx), 1.0 / F2)

        r_int_12 = np.exp(np.einsum("bf,bn,fn->b", w_f1, w_n12, A_int_12, optimize=True))
        r_int_19 = np.exp(np.einsum("bf,bn,fn->b", w_f1, w_n19, A_int_19, optimize=True))
        r_intg_12 = np.exp(np.einsum("bf,bn,fn->b", w_f2, w_n12, A_intg_12, optimize=True))
        r_intg_19 = np.exp(np.einsum("bf,bn,fn->b", w_f2, w_n19, A_intg_19, optimize=True))

        d_int = r_int_19 - r_int_12
        d_intg = r_intg_19 - r_intg_12
        diff_half[s:s + b] = d_int - 0.5 * d_intg
        ratio[s:s + b] = np.where(d_intg != 0, d_int / d_intg, np.nan)
    return diff_half, ratio


def evaluate_s1_hypotheses(df_r_s1: pd.DataFrame, df_best_s1: pd.DataFrame, df_h2: pd.DataFrame,
                           df_m2_sum: pd.DataFrame, jmh_pass: bool, df_jmh: pd.DataFrame,
                           gd1_r_path: Path) -> dict:
    """Đánh giá tập giả thuyết liên quan S1 (H1–H5, H10, H10b, H17) — dùng cho bản chính 5 fork và độ nhạy 4 fork."""
    best_map = df_best_s1[df_best_s1["distribution"] == "random"].set_index("scale")

    # H1
    h1_sub = {}
    req_set = set(range(24, 33))
    for scl in S1_SCALE_LABELS:
        row = best_map.loc[scl]
        c_ok = 17 <= int(row["c_star"]) <= 48
        near_ok = req_set.issubset(set(row["near_optimal_list"]))
        h1_sub[scl] = {"c_star": int(row["c_star"]), "near_opt": row["near_optimal_2pct"],
                       "c_ok": c_ok, "near_ok": near_ok, "met": bool(c_ok and near_ok)}
    h1_pass = all(v["met"] for v in h1_sub.values())

    # H2
    h2_pass = bool(df_h2["pass_scale"].all())

    # H3 (đọc r_GD1 từ results_final/analysis/tables/r_by_cutoff.csv)
    df_gd1 = pd.read_csv(gd1_r_path)
    gd1_rnd = df_gd1[df_gd1["distribution"] == "random"]
    h3_sub = {}
    for scl in THREE_SCALE_LABELS:
        g_sub = gd1_rnd[gd1_rnd["scale"] == scl]
        idx_min = g_sub["r_gm"].idxmin()
        r_gd1 = float(g_sub.loc[idx_min, "r_gm"])
        c_gd1 = int(g_sub.loc[idx_min, "cutoff"])
        r_p2 = float(best_map.loc[scl, "r_star"])
        c_p2 = int(best_map.loc[scl, "c_star"])
        diff = abs(r_p2 - r_gd1)
        h3_sub[scl] = {"r_p2": r_p2, "c_p2": c_p2, "r_gd1": r_gd1, "c_gd1": c_gd1,
                       "abs_diff": diff, "met": bool(diff <= 0.015)}
    h3_pass = all(v["met"] for v in h3_sub.values())

    # H4
    ci_12_16 = bool(float(best_map.loc["2^12", "ci2_hi"]) < float(best_map.loc["2^16", "ci2_lo"]))
    ci_16_19 = bool(float(best_map.loc["2^16", "ci2_hi"]) < float(best_map.loc["2^19", "ci2_lo"]))
    steps = []
    for s0, s1 in zip(S1_SCALE_LABELS[:-1], S1_SCALE_LABELS[1:]):
        delta = float(best_map.loc[s1, "r_star"]) - float(best_map.loc[s0, "r_star"])
        dec = max(0.0, -delta)
        steps.append({"pair": f"{s0}->{s1}", "delta": delta, "decrease": dec, "met": bool(dec <= 0.005)})
    max_dec = max(x["decrease"] for x in steps)
    h4_pass = bool(ci_12_16 and ci_16_19 and all(x["met"] for x in steps))

    # H5
    h5_sub = {}
    for scl in S1_SCALE_LABELS:
        row = best_map.loc[scl]
        r_s = float(row["r_star"])
        h5_sub[scl] = {"r_star": r_s, "ci2_lo": float(row["ci2_lo"]), "met": bool(r_s > 0.833)}
    h5_pass = all(v["met"] for v in h5_sub.values())

    # H10 & H10b
    h10_pass = bool(df_m2_sum["pass_H10"].all())
    h10b_pass = bool(df_m2_sum["pass_H10b"].all())

    return {
        "H1": {"pass": h1_pass, "sub": h1_sub},
        "H2": {"pass": h2_pass, "df": df_h2},
        "H3": {"pass": h3_pass, "sub": h3_sub},
        "H4": {"pass": h4_pass, "ci_12_16": ci_12_16, "ci_16_19": ci_16_19,
               "steps": steps, "max_decrease": max_dec, "best_map": best_map},
        "H5": {"pass": h5_pass, "sub": h5_sub},
        "H10": {"pass": h10_pass, "df": df_m2_sum},
        "H10b": {"pass": h10b_pass, "df": df_m2_sum},
        "H17": {"pass": jmh_pass, "df": df_jmh},
    }


# ──────────────────────────────────────────────────────────────── TỰ KIỂM GIAI ĐOẠN 1 (§3)

def run_self_check(B: int = DEFAULT_B) -> int:
    """
    Chạy đủ 6 kiểm tra tự kiểm trên dữ liệu GIAI ĐOẠN 1 (KHÔNG đọc bất kỳ dữ liệu giai đoạn 2 nào).
    In bảng cạnh nhau (số tính | số tham chiếu | chênh). Không đạt -> raise AssertionError.
    """
    print("=" * 92)
    print("T10 --self-check: TỰ KIỂM 6 HẠNG MỤC TRÊN DỮ LIỆU GIAI ĐOẠN 1 (KHÔNG CHẠM DỮ LIỆU GĐ2)")
    print("=" * 92)
    results_summary = []

    # ── Check 1 & 2: tái lập r_by_cutoff.csv (r_gm, c*, ci_lo, ci_hi) trên results_final/
    print("\n[Check 1 & 2] Tái lập results_final/analysis/tables/r_by_cutoff.csv (seed=20261027)")
    rf_dir = PROJECT_ROOT / "results_final"
    ref_r_path = rf_dir / "analysis/tables/r_by_cutoff.csv"
    ref_r = pd.read_csv(ref_r_path)

    raw_gd1 = load_raw_dir(rf_dir, "results_final (GĐ1)", expected_rows=None, check_k1_no_gc=False)
    obs_gd1, dfA_gd1 = compute_paired_A(raw_gd1)

    # Dùng đúng thứ tự duyệt (distribution, scale) của Core trong analyze.py để kiểm tra trùng khớp RNG 1e-9
    rng1 = np.random.default_rng(PHASE1_SEED)
    calc_rows = []
    for (d, sc), subA in dfA_gd1.groupby(["distribution", "scale"], sort=True):
        A, forks, Ns, cutoffs = build_A_tensor(subA)
        pt = np.exp(A.mean(axis=(0, 1)))
        bt1 = boot_one_tier(A, B, rng1)
        lo1, hi1 = np.percentile(bt1, [2.5, 97.5], axis=0)
        scl = slabel(int(sc))
        for j, c in enumerate(cutoffs):
            calc_rows.append({
                "distribution": d,
                "scale": scl,
                "cutoff": c,
                "r_calc": float(pt[j]),
                "ci1_lo_calc": float(math.exp(lo1[j])),
                "ci1_hi_calc": float(math.exp(hi1[j])),
            })
    df_calc1 = pd.DataFrame(calc_rows)
    m1 = pd.merge(
        ref_r[ref_r["distribution"] == "random"],
        df_calc1[df_calc1["distribution"] == "random"],
        on=["distribution", "scale", "cutoff"],
    )
    assert len(m1) == 3 * 35, f"Kỳ vọng 105 hàng random GĐ1, thực tế {len(m1)}"

    max_diff_r = float(np.max(np.abs(m1["r_calc"] - m1["r_gm"])))
    max_diff_lo = float(np.max(np.abs(m1["ci1_lo_calc"] - m1["ci_lo"])))
    max_diff_hi = float(np.max(np.abs(m1["ci1_hi_calc"] - m1["ci_hi"])))
    max_diff_ci = max(max_diff_lo, max_diff_hi)

    cstars_calc = {}
    for scl in THREE_SCALE_LABELS:
        sub = m1[m1["scale"] == scl]
        cstars_calc[scl] = int(sub.loc[sub["r_calc"].idxmin(), "cutoff"])
        r_min_c = float(sub["r_calc"].min())
        r_min_ref = float(sub["r_gm"].min())
        print(f"  random {scl}: c*={cstars_calc[scl]} (ref {REF_GD1_CSTAR[scl]}), r(c*)={r_min_c:.9f} | ref={r_min_ref:.9f} | diff={abs(r_min_c - r_min_ref):.2e}")
        assert cstars_calc[scl] == REF_GD1_CSTAR[scl], f"c* không khớp ở {scl}"

    print(f"  Check 1 max |r_calc - r_gm| (105 ô):   {max_diff_r:.3e}  (dung sai 1e-9)")
    print(f"  Check 2 max |ci1 - ci_ref|  (105 ô):   {max_diff_ci:.3e}  (dung sai 1e-9)")
    assert max_diff_r < 1e-9, f"Check 1 FAIL: max_diff_r={max_diff_r}"
    assert max_diff_ci < 1e-9, f"Check 2 FAIL: max_diff_ci={max_diff_ci}"
    results_summary.append(("1. r(c) & c* GĐ1 (105 ô)", f"c*={cstars_calc['2^12']}/{cstars_calc['2^16']}/{cstars_calc['2^19']}", "40/31/27", f"max_diff={max_diff_r:.2e}", "PASS"))
    results_summary.append(("2. CI một tầng GĐ1 (seed 20261027)", f"max_lo={max_diff_lo:.2e}", "ref r_by_cutoff", f"max_ci={max_diff_ci:.2e}", "PASS"))

    # ── Check 3: Doubling tổng quát hóa tái lập A1z và A5 trên results_doubling/
    print("\n[Check 3] Mã doubling tổng quát hóa tái lập A1z (SE_k, ln R_bar) và A5 (mean_delta) trên results_doubling/")
    db1_dir = PROJECT_ROOT / "results_doubling"
    raw_db1 = load_raw_dir(db1_dir, "results_doubling (GĐ1)", expected_rows=2700, check_k1_no_gc=True)
    df_g1 = compute_geometric_means(raw_db1)
    _, df_rbar1 = compute_r_and_rbar(df_g1)
    df_a5_sum1, _ = analyze_a5_same_tree_control(df_g1)

    ref_a1z = pd.read_csv(db1_dir / "analysis/tables/A1z_noise_interpretation.csv")
    ref_a1z_u = ref_a1z.drop_duplicates(subset=["cutoff", "k_from", "k_to"]).copy()
    ref_a1z_u["ln_R_bar_ref"] = np.log(ref_a1z_u["R_bar"].astype(float))
    m3_r = pd.merge(ref_a1z_u, df_rbar1, on=["cutoff", "k_from", "k_to"], suffixes=("_ref", "_calc"))
    assert len(m3_r) == 9 * 12, f"Kỳ vọng 108 hàng A1z, thực tế {len(m3_r)}"
    max_diff_lnR = float(np.max(np.abs(m3_r["ln_R_bar"] - m3_r["ln_R_bar_ref"])))
    max_diff_SE = float(np.max(np.abs(m3_r["SE_k_calc"] - m3_r["SE_k_ref"])))

    ref_a5 = pd.read_csv(db1_dir / "analysis/tables/A5_same_tree_summary.csv")
    m3_a5 = pd.merge(ref_a5, df_a5_sum1, on="pair", suffixes=("_ref", "_calc"))
    assert len(m3_a5) == 3
    max_diff_a5 = float(np.max(np.abs(m3_a5["mean_delta_calc"] - m3_a5["mean_delta_ref"])))

    print(f"  max |ln_R_bar - ref| (108 ô): {max_diff_lnR:.3e}")
    print(f"  max |SE_k - ref|     (108 ô): {max_diff_SE:.3e}")
    print(f"  max |A5 mean_delta|  (3 cặp): {max_diff_a5:.3e}")
    assert max_diff_lnR < 1e-9 and max_diff_SE < 1e-9 and max_diff_a5 < 1e-9
    results_summary.append(("3. Doubling tổng quát (A1z & A5)", f"SE diff={max_diff_SE:.2e}", "A1z & A5 GĐ1", f"max={max(max_diff_lnR, max_diff_SE, max_diff_a5):.2e}", "PASS"))

    # ── Check 4: Tái tính 3 dòng ngẫu nhiên mỗi thang mới của T09_predictions_m2.csv
    print("\n[Check 4] Tái tính 3 dòng bất kỳ mỗi thang mới (2^14, 2^18) từ T09_predictions_m2.csv (dung sai 1e-12)")
    pred_m2 = pd.read_csv(PROJECT_ROOT / "handoff/preregistration/T09_predictions_m2.csv")
    coef = pd.read_csv(rf_dir / "analysis_v2/tables/cost_model_M2_coef.csv").set_index("parameter")["coef"].to_dict()
    w1, w2, w3, beta = coef["ML_b1"], coef["ML_b2"], coef["ML_b3"], coef["exchanges"]
    a12, a16, a19 = coef["ML_b456_12"], coef["ML_b456_16"], coef["ML_b456_19"]
    alpha_new = {"2^14": a12 + (a16 - a12) * 0.5, "2^18": a16 + (a19 - a16) * (2.0 / 3.0)}

    rng_c4 = np.random.default_rng(20261117)
    max_diff_m2 = 0.0
    for scl in NEW_SCALE_LABELS:
        sub = pred_m2[(pred_m2["scale"] == scl) & (pred_m2["cutoff"] > 1)].reset_index(drop=True)
        pick = rng_c4.choice(len(sub), size=3, replace=False)
        for idx in pick:
            row = sub.iloc[int(idx)]
            n, c = int(row["N"]), int(row["cutoff"])
            a = alpha_new[scl]
            ts1 = tree_stats(n, 1)
            T1 = w1 * ts1[6] + w2 * ts1[7] + w3 * ts1[8] + beta * (ts1[5] / 2.0) + a * (ts1[9] + ts1[10] + ts1[11])
            ts = tree_stats(n, c)
            Tc = w1 * ts[6] + w2 * ts[7] + w3 * ts[8] + beta * (ts[5] / 2.0) + a * (ts[9] + ts[10] + ts[11])
            r_recalc = Tc / T1
            r_ref = float(row["r_hat_interp"])
            diff = abs(r_recalc - r_ref)
            max_diff_m2 = max(max_diff_m2, diff)
            print(f"  {scl} N={n:6d} c={c:2d}: calc={r_recalc:.15f} | ref={r_ref:.15f} | diff={diff:.2e}")
    assert max_diff_m2 < 1e-12, f"Check 4 FAIL: max_diff_m2={max_diff_m2}"
    results_summary.append(("4. Tái tính T09_predictions_m2 (6 dòng)", f"max_diff={max_diff_m2:.2e}", "T09_predictions_m2", f"{max_diff_m2:.2e}", "PASS"))

    # ── Check 5: α_calib H10b chạy trên GĐ1 (2^19 LOSO) tái lập validate_2e19_loso.csv (35 dòng)
    print("\n[Check 5] α_calib (calibrate_alpha_c1) trên GĐ1 2^19 LOSO tái lập validate_2e19_loso.csv (35 dòng)")
    df_all_gd1 = load_all_data(
        rf_dir,
        rf_dir / "analysis_v2/tables/tree_features.csv",
        rf_dir / "counts.csv",
    )
    df_loso_calc, meta_loso = validate_2e19_loso(df_all_gd1, ref_r)
    ref_loso = pd.read_csv(rf_dir / "analysis_v2/tables/validate_2e19_loso.csv")
    m5 = pd.merge(ref_loso, df_loso_calc, on="cutoff", suffixes=("_ref", "_calc"))
    assert len(m5) == 35
    max_diff_loso = float(np.max(np.abs(m5["r_hat_loso_calc"] - m5["r_hat_loso_ref"])))
    print(f"  alpha_calib (2^19 LOSO GĐ1) = {meta_loso['alpha_calib']:.9f}")
    print(f"  RMSE (c>=2, đúng GĐ1)       = {meta_loso['rmse_r']:.6f} (tham chiếu 0.0029)")
    print(f"  max |r_hat_loso - ref| (35 dòng): {max_diff_loso:.3e} (dung sai 1e-9)")
    assert max_diff_loso < 1e-9, f"Check 5 FAIL: max_diff_loso={max_diff_loso}"
    results_summary.append(("5. α_calib GĐ1 2^19 LOSO (35 dòng)", f"α={meta_loso['alpha_calib']:.6f}", "validate_2e19_loso", f"max_diff={max_diff_loso:.2e}", "PASS"))

    # ── Check 6: Bootstrap hai tầng với dữ liệu giả fork hằng số trùng CI một tầng
    print("\n[Check 6] Bootstrap hai tầng trên dữ liệu giả có 5 fork giống hệt nhau vs CI một tầng (cùng chuỗi rút N)")
    rng_syn = np.random.default_rng(12345)
    M_syn = rng_syn.normal(loc=-0.10, scale=0.03, size=(24, 10))
    A_syn = np.broadcast_to(M_syn[None, :, :], (5, 24, 10)).copy()

    bt1_syn = boot_one_tier(A_syn, B, np.random.default_rng(DEFAULT_SEED))
    bt2_syn = boot_two_tier(
        A_syn, B,
        rng=np.random.default_rng(DEFAULT_SEED),
        rng_fork=np.random.default_rng(DEFAULT_SEED + 999),
    )
    lo1_s, hi1_s = np.percentile(bt1_syn, [2.5, 97.5], axis=0)
    lo2_s, hi2_s = np.percentile(bt2_syn, [2.5, 97.5], axis=0)
    max_diff_syn = float(max(np.max(np.abs(lo2_s - lo1_s)), np.max(np.abs(hi2_s - hi1_s))))
    print(f"  max |CI2 - CI1| trên 10 cột dữ liệu fork hằng số: {max_diff_syn:.3e} (dung sai 1e-12)")
    assert max_diff_syn < 1e-12, f"Check 6 FAIL: max_diff_syn={max_diff_syn}"
    results_summary.append(("6. Bootstrap 2-tầng (fork hằng số)", f"max_diff={max_diff_syn:.2e}", "CI 1-tầng (cùng N)", f"{max_diff_syn:.2e}", "PASS"))

    print("\n" + "=" * 92)
    print("TỔNG KẾT --self-check (6/6 PASS):")
    print(f"{'Hạng mục':<42s} {'Tính được':<20s} {'Tham chiếu':<20s} {'Chênh':<16s} {'KQ'}")
    for item in results_summary:
        print(f"{item[0]:<42s} {item[1]:<20s} {item[2]:<20s} {item[3]:<16s} {item[4]}")
    print("=" * 92)
    return 0


# ──────────────────────────────────────────────────────────────── PHÂN TÍCH GIAI ĐOẠN 2 (§4)

def run_phase2_analysis(out_dir: Path, B: int = DEFAULT_B, base_seed: int = DEFAULT_SEED,
                        t11_fixes: bool = False) -> int:
    """Chạy toàn bộ phân tích giai đoạn 2 (H1–H17 + H10b + [KP] + [MT]) và xuất CSV + run_log.txt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "run_log.txt"

    orig_stdout = sys.stdout
    log_f = log_path.open("w", encoding="utf-8")
    sys.stdout = TeeStream(orig_stdout, log_f)
    try:
        return _run_phase2_body(tables_dir, B, base_seed, t11_fixes=t11_fixes)
    finally:
        sys.stdout = orig_stdout
        log_f.close()


def _run_phase2_body(tables_dir: Path, B: int, base_seed: int, t11_fixes: bool = False) -> int:
    print("=" * 96)
    print("T10: PHÂN TÍCH DỮ LIỆU GIAI ĐOẠN 2 THEO HỢP ĐỒNG T09 (commit c3e2b7f)")
    print(f"Bootstrap: B = {B}, seed gốc = {base_seed}")
    print("=" * 96)

    seeds = {
        "r_by_cutoff_s1_s2_two": base_seed,
        "r_by_cutoff_s1_s2_one": base_seed + 1,
        "h2_t7_t10_two": base_seed + 2,
        "h2_t7_t10_one": base_seed + 3,
        "pooled_random_two": base_seed + 4,
        "pooled_random_one": base_seed + 5,
        "doubling_r30_fork": base_seed + 6,
        "d3_r_by_cutoff_two": base_seed + 7,
        "d3_r_by_cutoff_one": base_seed + 8,
        "d3_H14_diff": base_seed + 9,
        "d3_H15_shrink": base_seed + 10,
        "d3_H16_diff": base_seed + 11,
        "sens_f4_r_two": base_seed + 12,
        "sens_f4_r_one": base_seed + 13,
        "sens_f4_h2_two": base_seed + 14,
        "sens_f4_h2_one": base_seed + 15,
    }
    print("\nDanh sách seed bootstrap theo bảng:")
    for k, v in seeds.items():
        print(f"  {k:<26s}: {v}")

    # ── 0. Nạp dữ liệu & Kiểm tra kích thước (Quy tắc A, §5)
    print("\n" + "-" * 96)
    print("0. NẠP DỮ LIỆU THÔ VÀ ĐỐI CHIẾU KÍCH THƯỚC (QUY TẮC A)")
    print("-" * 96)
    raw_s1 = load_raw_dir(PROJECT_ROOT / "results_run5_s1", "S1 (random, 5 thang)", expected_rows=REF_COUNTS["S1"])
    raw_s2 = load_raw_dir(PROJECT_ROOT / "results_run5_s2", "S2 (4 phân bố khác)", expected_rows=REF_COUNTS["S2"])
    raw_dv2 = load_raw_dir(PROJECT_ROOT / "results_doubling_v2", "DV2 (doubling v2)", expected_rows=REF_COUNTS["DV2"])
    raw_d3 = {}
    for key in D3_KEYS:
        raw_d3[key] = load_raw_dir(
            PROJECT_ROOT / "results_d3" / key,
            f"D3/{key}",
            expected_rows=REF_COUNTS[f"D3_{key}"],
        )

    # Đối chiếu hệ số M2 và GĐ1 (Quy tắc A)
    gd1_r_path = PROJECT_ROOT / "results_final/analysis/tables/r_by_cutoff.csv"
    pred_m2_path = PROJECT_ROOT / "handoff/preregistration/T09_predictions_m2.csv"
    pred_dv2_path = PROJECT_ROOT / "handoff/preregistration/T09_predictions_doubling_v2.csv"
    coef_m2_path = PROJECT_ROOT / "results_final/analysis_v2/tables/cost_model_M2_coef.csv"
    jmh_path = PROJECT_ROOT / "results_jmh/jmh_results.csv"

    df_gd1_ref = pd.read_csv(gd1_r_path)
    print("\nĐối chiếu GĐ1 (results_final/analysis/tables/r_by_cutoff.csv vs tham chiếu §5):")
    for scl in THREE_SCALE_LABELS:
        sub = df_gd1_ref[(df_gd1_ref["distribution"] == "random") & (df_gd1_ref["scale"] == scl)]
        idx = sub["r_gm"].idxmin()
        c_g = int(sub.loc[idx, "cutoff"])
        r_g = float(sub.loc[idx, "r_gm"])
        print(f"  GĐ1 {scl}: c*={c_g} (ref {REF_GD1_CSTAR[scl]}), r(c*)={r_g:.6f} (ref {REF_GD1_RSTAR[scl]:.3f}, chênh {abs(round(r_g, 3) - REF_GD1_RSTAR[scl]):.3f})")

    # ── 4.1 Run 5 (S1 + S2)
    print("\n" + "-" * 96)
    print("4.1 RUN 5 (S1 + S2): p2_r_by_cutoff, p2_best, p2_t7_t10, p2_fork_level, p2_ci_width, p2_pooled")
    print("-" * 96)
    obs_s1, dfA_s1 = compute_paired_A(raw_s1)
    obs_s2, dfA_s2 = compute_paired_A(raw_s2)
    obs_r5 = pd.concat([obs_s1, obs_s2], ignore_index=True)
    dfA_r5 = pd.concat([dfA_s1, dfA_s2], ignore_index=True)

    df_r_r5, df_best_r5, tensors_r5 = summarize_group_r(
        dfA_r5, obs_r5, B,
        seed_two=seeds["r_by_cutoff_s1_s2_two"],
        seed_one=seeds["r_by_cutoff_s1_s2_one"],
        label="[ĐK]",
    )
    df_r_r5.to_csv(tables_dir / "p2_r_by_cutoff.csv", index=False)
    df_best_r5.drop(columns=["near_optimal_list"]).to_csv(tables_dir / "p2_best.csv", index=False)

    # H2: T7/T10
    df_h2 = compute_h2_t7_t10(tensors_r5, S1_SCALE_LABELS, B, seeds["h2_t7_t10_two"], seeds["h2_t7_t10_one"])
    df_h2.to_csv(tables_dir / "p2_t7_t10.csv", index=False)

    # p2_fork_level.csv [MT]: r theo từng fork tại c* và c in {7, 10, 30} (cho random) và tại c* (cho S2)
    best_lookup = df_best_r5.set_index(["distribution", "scale"])["c_star"].to_dict()
    fork_rows = []
    for (d, scl), (A, forks, Ns, cutoffs) in tensors_r5.items():
        c_st = int(best_lookup[(d, scl)])
        target_cs = sorted(set([c_st] + ([7, 10, 30] if d == "random" else [])))
        sub_obs = obs_r5[(obs_r5["distribution"] == d) & (obs_r5["scale_label"] == scl)]
        for c in target_cs:
            if c not in cutoffs:
                continue
            cj = cutoffs.index(c)
            for fi, f in enumerate(forks):
                n_obs_fc = int(((sub_obs["fork"] == f) & (sub_obs["cutoff"] == c)).sum())
                fork_rows.append({
                    "distribution": d,
                    "scale": scl,
                    "fork": f,
                    "cutoff": c,
                    "is_c_star": bool(c == c_st),
                    "r": float(math.exp(A[fi, :, cj].mean())),
                    "n_N": len(Ns),
                    "n_obs": n_obs_fc,
                    "label": "[MT]",
                })
    df_fork_lvl = pd.DataFrame(fork_rows)
    df_fork_lvl.to_csv(tables_dir / "p2_fork_level.csv", index=False)

    # p2_ci_width.csv [MT]: độ rộng CI hai tầng / một tầng tại c*, 7, 10, 30 (random) và c* (S2)
    ciw_rows = []
    for (d, scl), sub in df_r_r5.groupby(["distribution", "scale"], sort=True):
        c_st = int(best_lookup[(d, scl)])
        target_cs = [c_st] + [c for c in ([7, 10, 30] if d == "random" else []) if c != c_st]
        sub_idx = sub.set_index("cutoff")
        for c in target_cs:
            if c not in sub_idx.index:
                continue
            row = sub_idx.loc[c]
            w2 = float(row["ci2_hi"] - row["ci2_lo"])
            w1 = float(row["ci1_hi"] - row["ci1_lo"])
            ciw_rows.append({
                "distribution": d,
                "scale": scl,
                "cutoff": c,
                "is_c_star": bool(c == c_st),
                "r": float(row["r"]),
                "ci2_lo": float(row["ci2_lo"]),
                "ci2_hi": float(row["ci2_hi"]),
                "ci1_lo": float(row["ci1_lo"]),
                "ci1_hi": float(row["ci1_hi"]),
                "width_ci2": w2,
                "width_ci1": w1,
                "ratio_ci2_over_ci1": w2 / w1 if w1 > 0 else float("nan"),
                "label": "[MT]",
            })
    df_ciw = pd.DataFrame(ciw_rows)
    df_ciw.to_csv(tables_dir / "p2_ci_width.csv", index=False)

    # p2_pooled.csv [MT]
    df_pooled = compute_pooled_random(
        tensors_r5, S1_SCALE_LABELS, B,
        seeds["pooled_random_two"], seeds["pooled_random_one"],
    )
    df_pooled.to_csv(tables_dir / "p2_pooled.csv", index=False)

    print(df_best_r5[["distribution", "scale", "c_star", "r_star", "ci2_lo", "ci2_hi", "near_optimal_2pct", "boot2_argmin_top3_kp"]].to_string(index=False))
    print("\nH2 (T7/T10):")
    print(df_h2[["scale", "ratio_T7_T10", "ci2_lo", "ci2_hi", "ci1_lo", "ci1_hi", "p_raw", "p_holm", "pass_scale"]].to_string(index=False))

    # ── 4.2 M2 (H10, H10b)
    print("\n" + "-" * 96)
    print("4.2 MÔ HÌNH M2 (H10, H10b): p2_m2_validation, p2_m2_summary")
    print("-" * 96)
    df_m2_val, df_m2_sum = compute_m2_validation(raw_s1, df_r_r5, df_best_r5, pred_m2_path, coef_m2_path)
    df_m2_val.to_csv(tables_dir / "p2_m2_validation.csv", index=False)
    df_m2_sum.to_csv(tables_dir / "p2_m2_summary.csv", index=False)
    for row in df_m2_sum.itertuples(index=False):
        ref_a = REF_ALPHA[row.scale]
        print(f"  [Quy tắc A] {row.scale}: alpha_interp={row.alpha_interp:.6f} (ref {ref_a:.6f}, diff={abs(row.alpha_interp - ref_a):.2e}) | alpha_calib={row.alpha_calib:.6f} | c*_M2={row.c_star_M2} (ref 40)")
    print(df_m2_sum.to_string(index=False))

    # ── 4.3 Doubling v2 (H11, H12, H13 + MT)
    print("\n" + "-" * 96)
    print("4.3 DOUBLING V2 (H11, H12, H13): p2_doubling_R, p2_H11, p2_H12, p2_H13, T/(N lg N), r30")
    print("-" * 96)
    df_g_dv2 = compute_geometric_means(raw_dv2)
    df_r_dv2, df_rbar_dv2 = compute_r_and_rbar(df_g_dv2)
    df_rbar_out = df_rbar_dv2.copy()
    df_rbar_out["label"] = "[MT]"
    df_rbar_out.to_csv(tables_dir / "p2_doubling_R.csv", index=False)

    df_pred_dv2 = pd.read_csv(pred_dv2_path)

    # H11: k in {19, 20, 21}, c in {1, 30}
    h11_rows = []
    for k in [19, 20, 21]:
        for c in [1, 30]:
            m_row = df_rbar_dv2[(df_rbar_dv2["k_from"] == k) & (df_rbar_dv2["cutoff"] == c)].iloc[0]
            p_row = df_pred_dv2[(df_pred_dv2["k"] == k) & (df_pred_dv2["cutoff"] == c)].iloc[0]
            lnR_v2 = float(m_row["ln_R_bar"])
            se_v2 = float(m_row["SE_k"])
            lnR_v1 = float(p_row["lnR_v1"])
            se_v1 = float(p_row["SE_v1"])
            diff = lnR_v2 - lnR_v1
            abs_diff = abs(diff)
            thresh = 3.0 * math.sqrt(se_v1**2 + se_v2**2)
            h11_rows.append({
                "k_from": k,
                "k_to": k + 1,
                "cutoff": c,
                "ln_R_v2": lnR_v2,
                "SE_v2": se_v2,
                "ln_R_v1": lnR_v1,
                "SE_v1": se_v1,
                "diff": diff,
                "abs_diff": abs_diff,
                "threshold_3se": thresh,
                "pass": bool(abs_diff <= thresh),
                "label": "[ĐK]",
            })
    df_h11 = pd.DataFrame(h11_rows)
    df_h11.to_csv(tables_dir / "p2_H11.csv", index=False)

    # H12: k in {22, 23}, c in {1, 30}, P_tiep vs P_baohoa
    h12_rows = []
    for pred_name, pred_col in [("P_tiep", "lnR_P_tiep"), ("P_baohoa", "lnR_P_baohoa")]:
        for k in [22, 23]:
            for c in [1, 30]:
                m_row = df_rbar_dv2[(df_rbar_dv2["k_from"] == k) & (df_rbar_dv2["cutoff"] == c)].iloc[0]
                p_row = df_pred_dv2[(df_pred_dv2["k"] == k) & (df_pred_dv2["cutoff"] == c)].iloc[0]
                lnR_v2 = float(m_row["ln_R_bar"])
                se_v2 = float(m_row["SE_k"])
                lnR_hat = float(p_row[pred_col])
                diff = lnR_v2 - lnR_hat
                abs_diff = abs(diff)
                thresh = 3.0 * se_v2
                h12_rows.append({
                    "predictor": pred_name,
                    "k_from": k,
                    "k_to": k + 1,
                    "cutoff": c,
                    "ln_R_v2": lnR_v2,
                    "ln_R_hat": lnR_hat,
                    "SE_v2": se_v2,
                    "diff": diff,
                    "abs_diff": abs_diff,
                    "threshold_3se": thresh,
                    "pass": bool(abs_diff <= thresh),
                    "label": "[ĐK]",
                })
    df_h12 = pd.DataFrame(h12_rows)
    df_h12.to_csv(tables_dir / "p2_H12.csv", index=False)

    # H13: cặp cùng cây (4,7), (8,10), (16,30) ở mọi k = 10..24 (45 ô) + gộp mọi k [MT]
    df_a5_sum2, df_a5_byn2 = analyze_a5_same_tree_control(df_g_dv2)
    df_h13_k = df_a5_byn2.copy()
    df_h13_k["abs_delta_mean"] = df_h13_k["delta_mean"].abs()
    df_h13_k["threshold"] = 0.01
    df_h13_k["pass"] = df_h13_k["abs_delta_mean"] <= 0.01
    df_h13_k["row_type"] = "per_k"
    df_h13_k["label"] = "[ĐK]"
    if t11_fixes:
        fork_cols = [f"delta_fork{f}" for f in range(1, 6)]
        sd_vals = df_h13_k[fork_cols].std(axis=1, ddof=1)
        df_h13_k["se_k"] = sd_vals / math.sqrt(len(fork_cols))
        df_h13_k["z_k"] = df_h13_k["delta_mean"] / df_h13_k["se_k"]

    pooled_a5_rows = []
    for row in df_a5_sum2.itertuples(index=False):
        rec = {
            "pair": row.pair,
            "k": -1,
            "N": -1,
            "delta_mean": float(row.mean_delta),
            "abs_delta_mean": abs(float(row.mean_delta)),
            "threshold": 0.01,
            "pass": bool(abs(float(row.mean_delta)) <= 0.01),
            "row_type": "pooled_all_k",
            "label": "[MT]",
        }
        for f in range(1, 6):
            rec[f"delta_fork{f}"] = float(getattr(row, f"mean_delta_fork{f}"))
        pooled_a5_rows.append(rec)
    df_h13 = pd.concat([df_h13_k, pd.DataFrame(pooled_a5_rows)], ignore_index=True)
    df_h13.to_csv(tables_dir / "p2_H13.csv", index=False)

    # p2_doubling_T_over_NlgN.csv [MT]: k, c in {1, 30}, T/(N lg N) trung bình nhân qua 5 fork
    t_nlgn_rows = []
    for (k, c), grp in df_g_dv2[df_g_dv2["cutoff"].isin([1, 30])].groupby(["k", "cutoff"], sort=True):
        n = int(1 << int(k))
        t_gm = float(math.exp(np.mean(np.log(grp["G"].to_numpy(dtype=float)))))
        t_nlgn_rows.append({
            "k": int(k),
            "N": n,
            "cutoff": int(c),
            "T_ns": t_gm,
            "T_ms": t_gm / 1e6,
            "T_over_NlgN_ns": t_gm / (n * int(k)),
            "label": "[MT]",
        })
    df_t_nlgn = pd.DataFrame(t_nlgn_rows)
    df_t_nlgn.to_csv(tables_dir / "p2_doubling_T_over_NlgN.csv", index=False)

    # p2_doubling_r30.csv [MT]: r(2^k, 30) = G(30)/G(1) trung bình nhân qua 5 fork, CI chỉ rút fork
    rng_r30 = np.random.default_rng(seeds["doubling_r30_fork"])
    piv_g = df_g_dv2.pivot(index=["fork", "k"], columns="cutoff", values="G")
    r30_rows = []
    ks_dv2 = sorted(int(k) for k in df_g_dv2["k"].unique())
    forks_dv2 = sorted(int(f) for f in df_g_dv2["fork"].unique())
    for k in ks_dv2:
        lrs = np.array([math.log(piv_g.loc[(f, k), 30] / piv_g.loc[(f, k), 1]) for f in forks_dv2], dtype=float)
        idx = rng_r30.integers(0, len(forks_dv2), size=(B, len(forks_dv2)))
        bt_f = lrs[idx].mean(axis=1)
        lo_f, hi_f = np.percentile(bt_f, [2.5, 97.5])
        r30_rows.append({
            "k": k,
            "N": 1 << k,
            "r30": float(math.exp(lrs.mean())),
            "ci_fork_lo": float(math.exp(lo_f)),
            "ci_fork_hi": float(math.exp(hi_f)),
            "n_forks": len(forks_dv2),
            "label": "[MT]",
        })
    df_r30 = pd.DataFrame(r30_rows)
    df_r30.to_csv(tables_dir / "p2_doubling_r30.csv", index=False)

    print("H11:")
    print(df_h11[["k_from", "k_to", "cutoff", "ln_R_v2", "ln_R_v1", "abs_diff", "threshold_3se", "pass"]].to_string(index=False))
    print("\nH12:")
    print(df_h12[["predictor", "k_from", "k_to", "cutoff", "ln_R_v2", "ln_R_hat", "abs_diff", "threshold_3se", "pass"]].to_string(index=False))
    print("\nH13 (pooled [MT] và max |Delta(k)| [ĐK]):")
    print(df_h13[df_h13["row_type"] == "pooled_all_k"][["pair", "delta_mean", "abs_delta_mean", "pass"]].to_string(index=False))
    print(f"  H13 per-k: {int(df_h13_k['pass'].sum())}/{len(df_h13_k)} ô đạt |Delta(k)| <= 0.01 (max = {df_h13_k['abs_delta_mean'].max():.6f})")

    # ── 4.4 D3: Kiểu khóa (H14, H15, H16 + [KP])
    print("\n" + "-" * 96)
    print("4.4 D3 KIỂU KHÓA (H14, H15, H16, 20% [KP], Integer D3 vs S1 [KP])")
    print("-" * 96)
    d3_r_frames, d3_best_frames = [], []
    d3_tensors = {}
    rng_d3_2 = np.random.default_rng(seeds["d3_r_by_cutoff_two"])
    rng_d3_1 = np.random.default_rng(seeds["d3_r_by_cutoff_one"])

    for key in D3_KEYS:
        obs_k, dfA_k = compute_paired_A(raw_d3[key])
        for scl in THREE_SCALE_LABELS:
            subA = dfA_k[dfA_k["scale_label"] == scl]
            subObs = obs_k[obs_k["scale_label"] == scl]
            A, forks, Ns, cutoffs = build_A_tensor(subA)
            assert len(cutoffs) == 37, f"D3/{key} {scl} có {len(cutoffs)} cutoff, kỳ vọng 37"
            d3_tensors[(key, scl)] = (A, forks, Ns, cutoffs)

            point_lr = A.mean(axis=(0, 1))
            point_r = np.exp(point_lr)
            bt2 = boot_two_tier(A, B, rng_d3_2)
            lo2, hi2 = np.percentile(bt2, [2.5, 97.5], axis=0)
            bt1 = boot_one_tier(A, B, rng_d3_1)
            lo1, hi1 = np.percentile(bt1, [2.5, 97.5], axis=0)
            obs_cnt = subObs.groupby("cutoff")["lr"].size().to_dict()

            for j, c in enumerate(cutoffs):
                d3_r_frames.append({
                    "key": key,
                    "scale": scl,
                    "cutoff": c,
                    "r": float(point_r[j]),
                    "ci2_lo": float(math.exp(lo2[j])),
                    "ci2_hi": float(math.exp(hi2[j])),
                    "ci1_lo": float(math.exp(lo1[j])),
                    "ci1_hi": float(math.exp(hi1[j])),
                    "n_N": len(Ns),
                    "n_forks": len(forks),
                    "n_obs": int(obs_cnt[c]),
                    "label": "[ĐK]",
                })

            best_idx = int(np.argmin(point_r))
            c_st = cutoffs[best_idx]
            r_st = float(point_r[best_idx])
            near_l = [cutoffs[j] for j in range(len(cutoffs)) if point_r[j] <= (1.0 + NEAR_TOL) * r_st]
            d3_best_frames.append({
                "key": key,
                "scale": scl,
                "c_star": c_st,
                "r_star": r_st,
                "ci2_lo": float(math.exp(lo2[best_idx])),
                "ci2_hi": float(math.exp(hi2[best_idx])),
                "ci1_lo": float(math.exp(lo1[best_idx])),
                "ci1_hi": float(math.exp(hi1[best_idx])),
                "near_optimal_2pct": compress_range(near_l),
                "label": "[ĐK]",
            })

    df_d3_r = pd.DataFrame(d3_r_frames)
    df_d3_best = pd.DataFrame(d3_best_frames)
    df_d3_r.to_csv(tables_dir / "p2_d3_r_by_cutoff.csv", index=False)
    df_d3_best.to_csv(tables_dir / "p2_d3_best.csv", index=False)
    d3_bmap = df_d3_best.set_index(["key", "scale"])

    # H14: int[] vs Integer[]
    rng_h14 = np.random.default_rng(seeds["d3_H14_diff"])
    h14_rows = []
    for scl in THREE_SCALE_LABELS:
        A_i, _, Ns_i, cuts_i = d3_tensors[("int", scl)]
        A_I, _, Ns_I, cuts_I = d3_tensors[("integer", scl)]
        assert Ns_i == Ns_I
        c_i = int(d3_bmap.loc[("int", scl), "c_star"])
        c_I = int(d3_bmap.loc[("integer", scl), "c_star"])
        r_i = float(d3_bmap.loc[("int", scl), "r_star"])
        r_I = float(d3_bmap.loc[("integer", scl), "r_star"])
        diff_b = boot_d3_diff_pair(A_i[:, :, cuts_i.index(c_i)], A_I[:, :, cuts_I.index(c_I)], B, rng_h14)
        lo_d, hi_d = np.percentile(diff_b, [2.5, 97.5])
        cond_ci = bool(hi_d < 0.0)
        cond_c = bool(c_i >= c_I)
        h14_rows.append({
            "scale": scl,
            "c_star_int": c_i,
            "r_int": r_i,
            "c_star_integer": c_I,
            "r_integer": r_I,
            "diff_r_int_minus_integer": r_i - r_I,
            "ci2_diff_lo": float(lo_d),
            "ci2_diff_hi": float(hi_d),
            "cond_ci_hi_lt_0": cond_ci,
            "cond_cstar_ge": cond_c,
            "pass": bool(cond_ci and cond_c),
            "label": "[ĐK]",
        })
    df_h14 = pd.DataFrame(h14_rows)
    df_h14.to_csv(tables_dir / "p2_H14.csv", index=False)

    # H15: độ co lại lợi ích 2^12 -> 2^19 của int[] < 0.5 * Integer[]
    rng_h15 = np.random.default_rng(seeds["d3_H15_shrink"])
    r_int_12 = float(d3_bmap.loc[("int", "2^12"), "r_star"])
    r_int_19 = float(d3_bmap.loc[("int", "2^19"), "r_star"])
    r_intg_12 = float(d3_bmap.loc[("integer", "2^12"), "r_star"])
    r_intg_19 = float(d3_bmap.loc[("integer", "2^19"), "r_star"])
    d_int = r_int_19 - r_int_12
    d_intg = r_intg_19 - r_intg_12

    A_i12, _, _, cuts_i12 = d3_tensors[("int", "2^12")]
    A_i19, _, _, cuts_i19 = d3_tensors[("int", "2^19")]
    A_I12, _, _, cuts_I12 = d3_tensors[("integer", "2^12")]
    A_I19, _, _, cuts_I19 = d3_tensors[("integer", "2^19")]
    diff_half_b, ratio_b = boot_d3_h15(
        A_i12[:, :, cuts_i12.index(int(d3_bmap.loc[("int", "2^12"), "c_star"]))],
        A_i19[:, :, cuts_i19.index(int(d3_bmap.loc[("int", "2^19"), "c_star"]))],
        A_I12[:, :, cuts_I12.index(int(d3_bmap.loc[("integer", "2^12"), "c_star"]))],
        A_I19[:, :, cuts_I19.index(int(d3_bmap.loc[("integer", "2^19"), "c_star"]))],
        B, rng_h15,
    )
    dh_lo, dh_hi = np.percentile(diff_half_b, [2.5, 97.5])
    rt_lo, rt_hi = np.nanpercentile(ratio_b, [2.5, 97.5])
    df_h15 = pd.DataFrame([{
        "r_int_2e12": r_int_12,
        "r_int_2e19": r_int_19,
        "delta_r_int": d_int,
        "r_integer_2e12": r_intg_12,
        "r_integer_2e19": r_intg_19,
        "delta_r_integer": d_intg,
        "half_delta_r_integer": 0.5 * d_intg,
        "diff_vs_half": d_int - 0.5 * d_intg,
        "ci2_diff_vs_half_lo": float(dh_lo),
        "ci2_diff_vs_half_hi": float(dh_hi),
        "ratio_int_over_integer": d_int / d_intg if d_intg != 0 else float("nan"),
        "ci2_ratio_lo": float(rt_lo),
        "ci2_ratio_hi": float(rt_hi),
        "pass": bool(d_int < 0.5 * d_intg),
        "label": "[ĐK]",
    }])
    df_h15.to_csv(tables_dir / "p2_H15.csv", index=False)

    # H16: |r_Double(c*) - r_Integer(c*)| <= 0.02 ở cả 3 thang
    rng_h16 = np.random.default_rng(seeds["d3_H16_diff"])
    h16_rows = []
    for scl in THREE_SCALE_LABELS:
        A_d, _, Ns_d, cuts_d = d3_tensors[("double", scl)]
        A_I, _, Ns_I, cuts_I = d3_tensors[("integer", scl)]
        assert Ns_d == Ns_I
        c_d = int(d3_bmap.loc[("double", scl), "c_star"])
        c_I = int(d3_bmap.loc[("integer", scl), "c_star"])
        r_d = float(d3_bmap.loc[("double", scl), "r_star"])
        r_I = float(d3_bmap.loc[("integer", scl), "r_star"])
        diff_b = boot_d3_diff_pair(A_d[:, :, cuts_d.index(c_d)], A_I[:, :, cuts_I.index(c_I)], B, rng_h16)
        lo_d, hi_d = np.percentile(diff_b, [2.5, 97.5])
        abs_d = abs(r_d - r_I)
        h16_rows.append({
            "scale": scl,
            "c_star_double": c_d,
            "r_double": r_d,
            "c_star_integer": c_I,
            "r_integer": r_I,
            "diff_r": r_d - r_I,
            "abs_diff": abs_d,
            "ci2_diff_lo": float(lo_d),
            "ci2_diff_hi": float(hi_d),
            "threshold": 0.02,
            "pass": bool(abs_d <= 0.02),
            "label": "[ĐK]",
        })
    df_h16 = pd.DataFrame(h16_rows)
    df_h16.to_csv(tables_dir / "p2_H16.csv", index=False)

    # [KP] p2_d3_20pct.csv
    d3_20_rows = []
    for scl in THREE_SCALE_LABELS:
        row = d3_bmap.loc[("int", scl)]
        r_i = float(row["r_star"])
        lo_i = float(row["ci2_lo"])
        hi_i = float(row["ci2_hi"])
        d3_20_rows.append({
            "scale": scl,
            "c_star_int": int(row["c_star"]),
            "r_int": r_i,
            "ci2_lo": lo_i,
            "ci2_hi": hi_i,
            "speedup_point": 1.0 / r_i,
            "pct_reduction_point": (1.0 - r_i) * 100.0,
            "le_0833_point": bool(r_i <= 0.833),
            "le_0833_ci_hi": bool(hi_i <= 0.833),
            "le_080_point": bool(r_i <= 0.80),
            "le_080_ci_hi": bool(hi_i <= 0.80),
            "label": "[KP]",
        })
    df_d3_20 = pd.DataFrame(d3_20_rows)
    df_d3_20.to_csv(tables_dir / "p2_d3_20pct.csv", index=False)

    # [KP] p2_d3_integer_vs_s1.csv
    s1_bmap = df_best_r5[df_best_r5["distribution"] == "random"].set_index("scale")
    s1_r30 = df_r_r5[(df_r_r5["distribution"] == "random") & (df_r_r5["cutoff"] == 30)].set_index("scale")["r"]
    d3_r30 = df_d3_r[(df_d3_r["key"] == "integer") & (df_d3_r["cutoff"] == 30)].set_index("scale")["r"]
    d3_vs_s1_rows = []
    for scl in THREE_SCALE_LABELS:
        r_st_d3 = float(d3_bmap.loc[("integer", scl), "r_star"])
        r_st_s1 = float(s1_bmap.loc[scl, "r_star"])
        r30_d = float(d3_r30.loc[scl])
        r30_s = float(s1_r30.loc[scl])
        d3_vs_s1_rows.append({
            "scale": scl,
            "c_star_d3_integer": int(d3_bmap.loc[("integer", scl), "c_star"]),
            "r_star_d3_integer": r_st_d3,
            "c_star_s1_random": int(s1_bmap.loc[scl, "c_star"]),
            "r_star_s1_random": r_st_s1,
            "diff_r_star_d3_minus_s1": r_st_d3 - r_st_s1,
            "r30_d3_integer": r30_d,
            "r30_s1_random": r30_s,
            "diff_r30_d3_minus_s1": r30_d - r30_s,
            "label": "[KP]",
        })
    df_d3_vs_s1 = pd.DataFrame(d3_vs_s1_rows)
    df_d3_vs_s1.to_csv(tables_dir / "p2_d3_integer_vs_s1.csv", index=False)

    print(df_d3_best[["key", "scale", "c_star", "r_star", "ci2_lo", "ci2_hi", "near_optimal_2pct"]].to_string(index=False))
    print("\nH14:")
    print(df_h14[["scale", "c_star_int", "r_int", "c_star_integer", "r_integer", "diff_r_int_minus_integer", "ci2_diff_lo", "ci2_diff_hi", "pass"]].to_string(index=False))
    print("\nH15:")
    print(df_h15[["delta_r_int", "delta_r_integer", "half_delta_r_integer", "ratio_int_over_integer", "ci2_ratio_lo", "ci2_ratio_hi", "pass"]].to_string(index=False))
    print("\nH16:")
    print(df_h16[["scale", "r_double", "r_integer", "abs_diff", "ci2_diff_lo", "ci2_diff_hi", "pass"]].to_string(index=False))

    # ── 4.5 JMH (H17)
    print("\n" + "-" * 96)
    print("4.5 JMH KIỂM CHỨNG CHÉO (H17): p2_jmh")
    print("-" * 96)
    df_jmh, h17_pass = compute_jmh_h17(jmh_path, obs_s1, raw_s1)
    df_jmh.to_csv(tables_dir / "p2_jmh.csv", index=False)
    print(df_jmh[["N", "cutoff", "jmh_score_us", "jmh_score_err_999_us", "r_jmh", "r_run5", "abs_diff", "pass_diff_le_002", "order_30_10_7_1_ok"]].to_string(index=False))

    # ── 4.6 Độ nhạy bỏ S1 fork 4 [KP]
    print("\n" + "-" * 96)
    print("4.6 PHÂN TÍCH ĐỘ NHẠY BỎ S1 FORK 4 [KP]: p2_sensitivity_drop_f4")
    print("-" * 96)
    eval_5f = evaluate_s1_hypotheses(df_r_r5, df_best_r5, df_h2, df_m2_sum, h17_pass, df_jmh, gd1_r_path)

    raw_s1_4f = raw_s1[raw_s1["fork"].isin([1, 2, 3, 5])].copy()
    obs_s1_4f, dfA_s1_4f = compute_paired_A(raw_s1_4f)
    df_r_s1_4f, df_best_s1_4f, tensors_s1_4f = summarize_group_r(
        dfA_s1_4f, obs_s1_4f, B,
        seed_two=seeds["sens_f4_r_two"],
        seed_one=seeds["sens_f4_r_one"],
        label="[KP]",
    )
    df_h2_4f = compute_h2_t7_t10(tensors_s1_4f, S1_SCALE_LABELS, B, seeds["sens_f4_h2_two"], seeds["sens_f4_h2_one"])
    _, df_m2_sum_4f = compute_m2_validation(raw_s1_4f, df_r_s1_4f, df_best_s1_4f, pred_m2_path, coef_m2_path)
    df_jmh_4f, h17_pass_4f = compute_jmh_h17(jmh_path, obs_s1_4f, raw_s1_4f)
    eval_4f = evaluate_s1_hypotheses(df_r_s1_4f, df_best_s1_4f, df_h2_4f, df_m2_sum_4f, h17_pass_4f, df_jmh_4f, gd1_r_path)

    # Bảng so sánh theo thang + vị trí fork 4 so với [min, max] của 4 fork còn lại
    b5 = df_best_r5[df_best_r5["distribution"] == "random"].set_index("scale")
    b4 = df_best_s1_4f[df_best_s1_4f["distribution"] == "random"].set_index("scale")
    sens_scale_rows = []
    for scl in S1_SCALE_LABELS:
        c5 = int(b5.loc[scl, "c_star"])
        # Lấy r(c*_5fork) của từng fork từ p2_fork_level
        f_sub = df_fork_lvl[(df_fork_lvl["distribution"] == "random") & (df_fork_lvl["scale"] == scl) & (df_fork_lvl["cutoff"] == c5)]
        r_f4 = float(f_sub[f_sub["fork"] == 4]["r"].iloc[0])
        other4 = f_sub[f_sub["fork"] != 4]["r"].to_numpy(dtype=float)
        o_min, o_max = float(other4.min()), float(other4.max())
        sens_scale_rows.append({
            "scale": scl,
            "c_star_5forks": c5,
            "r_star_5forks": float(b5.loc[scl, "r_star"]),
            "ci2_5f_lo": float(b5.loc[scl, "ci2_lo"]),
            "ci2_5f_hi": float(b5.loc[scl, "ci2_hi"]),
            "c_star_4forks": int(b4.loc[scl, "c_star"]),
            "r_star_4forks": float(b4.loc[scl, "r_star"]),
            "ci2_4f_lo": float(b4.loc[scl, "ci2_lo"]),
            "ci2_4f_hi": float(b4.loc[scl, "ci2_hi"]),
            "r_fork4_at_cstar5": r_f4,
            "r_other4_min": o_min,
            "r_other4_max": o_max,
            "fork4_within_other4_range": bool(o_min <= r_f4 <= o_max),
            "label": "[KP]",
        })
    df_sens_scales = pd.DataFrame(sens_scale_rows)
    df_sens_scales.to_csv(tables_dir / "p2_sensitivity_drop_f4_scales.csv", index=False)

    def _fmt_verdict(ok: bool) -> str:
        return "ĐẠT" if ok else "KHÔNG ĐẠT"

    def _summarize_s1_h(ev: dict, hid: str) -> str:
        if hid == "H1":
            return "; ".join(f"{s}:c*={ev['H1']['sub'][s]['c_star']}" for s in S1_SCALE_LABELS)
        if hid == "H2":
            d = ev["H2"]["df"]
            return f"min_ci2_lo={d['ci2_lo'].min():.4f}, max_p_holm={d['p_holm'].max():.4g}"
        if hid == "H3":
            return "; ".join(f"{s}:|d|={ev['H3']['sub'][s]['abs_diff']:.4f}" for s in THREE_SCALE_LABELS)
        if hid == "H4":
            return f"ci_12<16:{ev['H4']['ci_12_16']}, ci_16<19:{ev['H4']['ci_16_19']}, max_dec={ev['H4']['max_decrease']:.4f}"
        if hid == "H5":
            min_r = min(ev["H5"]["sub"][s]["r_star"] for s in S1_SCALE_LABELS)
            return f"min r(c*)={min_r:.4f}"
        if hid == "H10":
            d = ev["H10"]["df"].set_index("scale")
            return f"RMSE 2^14={d.loc['2^14','rmse_interp']:.4f}, 2^18={d.loc['2^18','rmse_interp']:.4f}"
        if hid == "H10b":
            d = ev["H10b"]["df"].set_index("scale")
            return f"RMSE 2^14={d.loc['2^14','rmse_calib']:.4f}, 2^18={d.loc['2^18','rmse_calib']:.4f}"
        if hid == "H17":
            d = ev["H17"]["df"]
            d9 = d[d["cutoff"] != 1]
            return f"max|d|={d9['abs_diff'].max():.4f}, order_all={bool(d['order_30_10_7_1_ok'].all())}"
        return ""

    sens_h_rows = []
    for hid in ["H1", "H2", "H3", "H4", "H5", "H10", "H10b", "H17"]:
        v5 = _fmt_verdict(eval_5f[hid]["pass"])
        v4 = _fmt_verdict(eval_4f[hid]["pass"])
        sens_h_rows.append({
            "hypothesis": hid,
            "verdict_5forks": v5,
            "verdict_4forks": v4,
            "verdict_changed": bool(v5 != v4),
            "metrics_5forks": _summarize_s1_h(eval_5f, hid),
            "metrics_4forks": _summarize_s1_h(eval_4f, hid),
            "note": "Kết luận chính dùng đủ 5 fork (§0 hợp đồng)",
            "label": "[KP]",
        })
    df_sens = pd.DataFrame(sens_h_rows)
    df_sens.to_csv(tables_dir / "p2_sensitivity_drop_f4.csv", index=False)

    print(df_sens[["hypothesis", "verdict_5forks", "verdict_4forks", "verdict_changed", "metrics_5forks", "metrics_4forks"]].to_string(index=False))
    print("\nFork 4 so với khoảng [min, max] của 4 fork còn lại {1,2,3,5}:")
    print(df_sens_scales[["scale", "c_star_5forks", "r_star_5forks", "c_star_4forks", "r_star_4forks", "r_fork4_at_cstar5", "r_other4_min", "r_other4_max", "fork4_within_other4_range"]].to_string(index=False))

    # ── 4.8 Bảng phán quyết tổng h_verdicts.csv (18 hàng tổng: H1–H17, H10b)
    print("\n" + "-" * 96)
    print("4.8 BẢNG PHÁN QUYẾT TỔNG (h_verdicts.csv) — 18 GIẢ THUYẾT [ĐK]")
    print("-" * 96)
    v_rows = []

    def add_v(hid, subcase, qty, val, thresh, met, overall, src):
        v_rows.append({
            "id": hid,
            "subcase": subcase,
            "quantity": qty,
            "value": val,
            "threshold": thresh,
            "condition_met": bool(met),
            "verdict_overall": overall,
            "source_table": src,
            "label": "[ĐK]",
        })

    # H1
    for scl in S1_SCALE_LABELS:
        info = eval_5f["H1"]["sub"][scl]
        add_v("H1", scl, "c*, near_opt", f"c*={info['c_star']}; near={info['near_opt']}",
              "c* in [17,48] & {24..32} subset near", info["met"], "", "p2_best.csv")
    add_v("H1", "OVERALL", "5/5 scales pass",
          f"{sum(v['met'] for v in eval_5f['H1']['sub'].values())}/5",
          "5/5", eval_5f["H1"]["pass"], _fmt_verdict(eval_5f["H1"]["pass"]), "p2_best.csv")

    # H2
    for row in df_h2.itertuples(index=False):
        add_v("H2", row.scale, "T7/T10, ci2_lo, p_holm",
              f"{row.ratio_T7_T10:.4f} [{row.ci2_lo:.4f}, {row.ci2_hi:.4f}], p_holm={row.p_holm:.4g}",
              "ci2_lo > 1.0 & p_holm < 0.05", row.pass_scale, "", "p2_t7_t10.csv")
    add_v("H2", "OVERALL", "5/5 scales pass",
          f"{int(df_h2['pass_scale'].sum())}/5",
          "5/5", eval_5f["H2"]["pass"], _fmt_verdict(eval_5f["H2"]["pass"]), "p2_t7_t10.csv")

    # H3
    for scl in THREE_SCALE_LABELS:
        info = eval_5f["H3"]["sub"][scl]
        add_v("H3", scl, "|r_Run5(c*) - r_GD1(c*)|",
              f"|{info['r_p2']:.4f} - {info['r_gd1']:.4f}| = {info['abs_diff']:.4f}",
              "<= 0.015", info["met"], "", "p2_best.csv")
    add_v("H3", "OVERALL", "3/3 scales pass",
          f"{sum(v['met'] for v in eval_5f['H3']['sub'].values())}/3",
          "3/3", eval_5f["H3"]["pass"], _fmt_verdict(eval_5f["H3"]["pass"]), "p2_best.csv")

    # H4
    bm = eval_5f["H4"]["best_map"]
    add_v("H4", "CI_2^12_vs_2^16", "ci2_hi(2^12) < ci2_lo(2^16)",
          f"{bm.loc['2^12','ci2_hi']:.4f} vs {bm.loc['2^16','ci2_lo']:.4f}",
          "ci2_hi < ci2_lo", eval_5f["H4"]["ci_12_16"], "", "p2_best.csv")
    add_v("H4", "CI_2^16_vs_2^19", "ci2_hi(2^16) < ci2_lo(2^19)",
          f"{bm.loc['2^16','ci2_hi']:.4f} vs {bm.loc['2^19','ci2_lo']:.4f}",
          "ci2_hi < ci2_lo", eval_5f["H4"]["ci_16_19"], "", "p2_best.csv")
    for st in eval_5f["H4"]["steps"]:
        add_v("H4", f"step_{st['pair']}", "delta r(c*)",
              f"{st['delta']:+.4f} (dec={st['decrease']:.4f})",
              "decrease <= 0.005", st["met"], "", "p2_best.csv")
    add_v("H4", "OVERALL", "(i) non-overlap CI & (ii) max dec <= 0.005",
          f"ci_ok={eval_5f['H4']['ci_12_16'] and eval_5f['H4']['ci_16_19']}, max_dec={eval_5f['H4']['max_decrease']:.4f}",
          "both true", eval_5f["H4"]["pass"], _fmt_verdict(eval_5f["H4"]["pass"]), "p2_best.csv")

    # H5
    for scl in S1_SCALE_LABELS:
        info = eval_5f["H5"]["sub"][scl]
        add_v("H5", scl, "r(c*) [ci2_lo]",
              f"{info['r_star']:.4f} [ci2_lo={info['ci2_lo']:.4f}]",
              "> 0.833", info["met"], "", "p2_best.csv")
    add_v("H5", "OVERALL", "5/5 scales > 0.833",
          f"min={min(v['r_star'] for v in eval_5f['H5']['sub'].values()):.4f}",
          "> 0.833", eval_5f["H5"]["pass"], _fmt_verdict(eval_5f["H5"]["pass"]), "p2_best.csv")

    # H6 (reversed), H7 (few_distinct), H8 (sorted), H9 (nearly_sorted)
    b_s2 = df_best_r5[df_best_r5["distribution"] != "random"].set_index(["distribution", "scale"])

    # H6
    h6_oks = []
    for scl in THREE_SCALE_LABELS:
        c_st = int(b_s2.loc[("reversed", scl), "c_star"])
        ok = 6 <= c_st <= 16
        h6_oks.append(ok)
        add_v("H6", scl, "c* (reversed)", f"{c_st}", "in [6, 16]", ok, "", "p2_best.csv")
    add_v("H6", "OVERALL", "3/3 scales pass", f"{sum(h6_oks)}/3", "3/3", all(h6_oks), _fmt_verdict(all(h6_oks)), "p2_best.csv")

    # H7
    h7_oks = []
    for scl in THREE_SCALE_LABELS:
        c_st = int(b_s2.loc[("few_distinct", scl), "c_star"])
        ok = 17 <= c_st <= 48
        h7_oks.append(ok)
        add_v("H7", scl, "c* (few_distinct)", f"{c_st}", "in [17, 48]", ok, "", "p2_best.csv")
    add_v("H7", "OVERALL", "3/3 scales pass", f"{sum(h7_oks)}/3", "3/3", all(h7_oks), _fmt_verdict(all(h7_oks)), "p2_best.csv")

    # H8 (sorted): số Δ_i > 0 bằng 0 hoặc (đúng 1 và <= 0.01), VÀ c* == 4096
    h8_oks = []
    for scl in THREE_SCALE_LABELS:
        sub_s = df_r_r5[(df_r_r5["distribution"] == "sorted") & (df_r_r5["scale"] == scl)].sort_values("cutoff")
        rs = sub_s["r"].to_numpy(dtype=float)
        deltas = np.diff(rs)
        pos = deltas[deltas > 0.0]
        n_pos = int(len(pos))
        max_pos = float(pos.max()) if n_pos > 0 else 0.0
        c_st = int(b_s2.loc[("sorted", scl), "c_star"])
        mono_ok = (n_pos == 0) or (n_pos == 1 and max_pos <= 0.01)
        ok = bool(mono_ok and (c_st == 4096))
        h8_oks.append(ok)
        add_v("H8", scl, "c*, n_inc, max_inc",
              f"c*={c_st}, n_inc={n_pos}, max_inc={max_pos:.4f}",
              "c*=4096 & (n_inc==0 or (n_inc==1 & max_inc<=0.01))", ok, "", "p2_r_by_cutoff.csv")
    add_v("H8", "OVERALL", "3/3 scales pass", f"{sum(h8_oks)}/3", "3/3", all(h8_oks), _fmt_verdict(all(h8_oks)), "p2_r_by_cutoff.csv")

    # H9 (nearly_sorted)
    h9_allowed = {128, 192, 256, 384, 512, 768, 1024}
    h9_oks = []
    for scl in THREE_SCALE_LABELS:
        c_st = int(b_s2.loc[("nearly_sorted", scl), "c_star"])
        ok = c_st in h9_allowed
        h9_oks.append(ok)
        add_v("H9", scl, "c* (nearly_sorted)", f"{c_st}", "in {128..1024}", ok, "", "p2_best.csv")
    add_v("H9", "OVERALL", "3/3 scales pass", f"{sum(h9_oks)}/3", "3/3", all(h9_oks), _fmt_verdict(all(h9_oks)), "p2_best.csv")

    # H10 & H10b
    for row in df_m2_sum.itertuples(index=False):
        add_v("H10", row.scale, "RMSE_interp, c*_M2 in near_opt",
              f"RMSE={row.rmse_interp:.4f}, c*_M2={row.c_star_M2} in [{row.near_optimal_2pct_meas}]={row.c_star_M2_in_near_opt}",
              "RMSE <= 0.012 & in near_opt", row.pass_H10, "", "p2_m2_summary.csv")
    add_v("H10", "OVERALL", "2/2 scales pass",
          f"{int(df_m2_sum['pass_H10'].sum())}/2", "2/2",
          eval_5f["H10"]["pass"], _fmt_verdict(eval_5f["H10"]["pass"]), "p2_m2_summary.csv")

    for row in df_m2_sum.itertuples(index=False):
        add_v("H10b", row.scale, "RMSE_calib (alpha_calib)",
              f"RMSE={row.rmse_calib:.4f} (alpha={row.alpha_calib:.4f})",
              "RMSE <= 0.012", row.pass_H10b, "", "p2_m2_summary.csv")
    add_v("H10b", "OVERALL", "2/2 scales pass",
          f"{int(df_m2_sum['pass_H10b'].sum())}/2", "2/2",
          eval_5f["H10b"]["pass"], _fmt_verdict(eval_5f["H10b"]["pass"]), "p2_m2_summary.csv")

    # H11
    for _, row in df_h11.iterrows():
        add_v("H11", f"k={int(row['k_from'])}_c={int(row['cutoff'])}", "|lnR_v2 - lnR_v1|",
              f"{row['abs_diff']:.4f} (3SE={row['threshold_3se']:.4f})",
              "<= 3*sqrt(SE1^2+SE2^2)", bool(row["pass"]), "", "p2_H11.csv")
    h11_pass = bool(df_h11["pass"].all())
    add_v("H11", "OVERALL", "6/6 cells pass", f"{int(df_h11['pass'].sum())}/6", "6/6",
          h11_pass, _fmt_verdict(h11_pass), "p2_H11.csv")

    # H12
    p_tiep_sub = df_h12[df_h12["predictor"] == "P_tiep"]
    p_bh_sub = df_h12[df_h12["predictor"] == "P_baohoa"]
    pass_tiep = bool(p_tiep_sub["pass"].all())
    pass_bh = bool(p_bh_sub["pass"].all())
    for _, row in df_h12.iterrows():
        add_v("H12", f"{row['predictor']}_k={int(row['k_from'])}_c={int(row['cutoff'])}",
              "|lnR_v2 - lnR_hat|", f"{row['abs_diff']:.4f} (3SE={row['threshold_3se']:.4f})",
              "<= 3*SE_k", bool(row["pass"]), "", "p2_H12.csv")
    add_v("H12", "P_tiep_summary", "4/4 cells pass", f"{int(p_tiep_sub['pass'].sum())}/4", "4/4",
          pass_tiep, "", "p2_H12.csv")
    add_v("H12", "P_baohoa_summary", "4/4 cells pass", f"{int(p_bh_sub['pass'].sum())}/4", "4/4",
          pass_bh, "", "p2_H12.csv")
    if t11_fixes:
        h12_verdict = (
            f"XEM TỪNG DỰ ĐOÁN (P-tiếp {'ĐẠT' if pass_tiep else 'KHÔNG ĐẠT'}; "
            f"P-bão hòa {'ĐẠT' if pass_bh else 'KHÔNG ĐẠT'})"
        )
    elif pass_tiep and not pass_bh:
        h12_verdict = "ĐẠT (P-tiếp ĐẠT; P-bão hòa KHÔNG ĐẠT)"
    elif pass_bh and not pass_tiep:
        h12_verdict = "ĐẠT (P-bão hòa ĐẠT; P-tiếp KHÔNG ĐẠT)"
    elif pass_tiep and pass_bh:
        h12_verdict = "ĐẠT (cả hai ĐẠT)"
    else:
        h12_verdict = "KHÔNG ĐẠT (cả hai KHÔNG ĐẠT)"
    add_v("H12", "OVERALL", "P-tiếp vs P-bão hòa",
          f"P_tiep={int(p_tiep_sub['pass'].sum())}/4, P_baohoa={int(p_bh_sub['pass'].sum())}/4",
          "4/4 cells <= 3*SE_k", bool(pass_tiep or pass_bh), h12_verdict, "p2_H12.csv")

    # H13 (45 ô per-k)
    for pair_name, grp in df_h13_k.groupby("pair", sort=True):
        n_ok = int(grp["pass"].sum())
        add_v("H13", f"pair_{pair_name}", "max |Delta(k)| over k=10..24",
              f"{n_ok}/{len(grp)} pass, max={grp['abs_delta_mean'].max():.5f}",
              "<= 0.01 ở mọi k", bool(n_ok == len(grp)), "", "p2_H13.csv")
    h13_pass = bool(df_h13_k["pass"].all())
    add_v("H13", "OVERALL", "45/45 cells pass",
          f"{int(df_h13_k['pass'].sum())}/45 (max={df_h13_k['abs_delta_mean'].max():.5f})",
          "45/45 <= 0.01", h13_pass, _fmt_verdict(h13_pass), "p2_H13.csv")

    # H14
    for _, row in df_h14.iterrows():
        add_v("H14", row["scale"], "r_int - r_Integer (CI_hi), c*",
              f"diff={row['diff_r_int_minus_integer']:+.4f} (ci_hi={row['ci2_diff_hi']:+.4f}); c*={int(row['c_star_int'])} vs {int(row['c_star_integer'])}",
              "ci_hi < 0 & c*_int >= c*_Integer", bool(row["pass"]), "", "p2_H14.csv")
    h14_pass = bool(df_h14["pass"].all())
    add_v("H14", "OVERALL", "3/3 scales pass", f"{int(df_h14['pass'].sum())}/3", "3/3",
          h14_pass, _fmt_verdict(h14_pass), "p2_H14.csv")

    # H15
    r15 = df_h15.iloc[0]
    h15_pass = bool(r15["pass"])
    add_v("H15", "2^12_to_2^19", "Delta_r_int vs 0.5*Delta_r_Integer",
          f"{r15['delta_r_int']:.4f} vs {r15['half_delta_r_integer']:.4f} (ratio={r15['ratio_int_over_integer']:.3f})",
          "< 0.5 * Delta_r_Integer", h15_pass, "", "p2_H15.csv")
    add_v("H15", "OVERALL", "Delta_r_int < 0.5*Delta_r_Integer",
          f"{r15['delta_r_int']:.4f} vs {r15['half_delta_r_integer']:.4f}",
          "< 0.5 * Delta_r_Integer", h15_pass, _fmt_verdict(h15_pass), "p2_H15.csv")

    # H16
    for _, row in df_h16.iterrows():
        add_v("H16", row["scale"], "|r_Double(c*) - r_Integer(c*)|",
              f"{row['abs_diff']:.4f} (CI=[{row['ci2_diff_lo']:+.4f},{row['ci2_diff_hi']:+.4f}])",
              "<= 0.02", bool(row["pass"]), "", "p2_H16.csv")
    h16_pass = bool(df_h16["pass"].all())
    add_v("H16", "OVERALL", "3/3 scales pass", f"{int(df_h16['pass'].sum())}/3", "3/3",
          h16_pass, _fmt_verdict(h16_pass), "p2_H16.csv")

    # H17
    for _, row in df_jmh[df_jmh["cutoff"] != 1].iterrows():
        add_v("H17", f"N={int(row['N'])}_c={int(row['cutoff'])}", "|r_JMH - r_Run5|",
              f"|{row['r_jmh']:.4f} - {row['r_run5']:.4f}| = {row['abs_diff']:.4f}",
              "<= 0.02", bool(row["pass_diff_le_002"]), "", "p2_jmh.csv")
    for n in JMH_NS:
        ord_ok = bool(df_jmh[df_jmh["N"] == n]["order_30_10_7_1_ok"].iloc[0])
        add_v("H17", f"order_N={n}", "Score(30)<Score(10)<Score(7)<Score(1)",
              str(ord_ok), "True", ord_ok, "", "p2_jmh.csv")
    add_v("H17", "OVERALL", "9/9 diff <= 0.02 & 3/3 order ok",
          f"diff={int(df_jmh[df_jmh['cutoff']!=1]['pass_diff_le_002'].sum())}/9, order={sum(bool(df_jmh[df_jmh['N']==n]['order_30_10_7_1_ok'].iloc[0]) for n in JMH_NS)}/3",
          "9/9 & 3/3", h17_pass, _fmt_verdict(h17_pass), "p2_jmh.csv")

    df_verdicts = pd.DataFrame(v_rows)
    df_verdicts.to_csv(tables_dir / "h_verdicts.csv", index=False)

    overall_df = df_verdicts[df_verdicts["subcase"] == "OVERALL"]
    assert len(overall_df) == 18, f"Kỳ vọng 18 hàng OVERALL, thực tế {len(overall_df)}"
    print(overall_df[["id", "quantity", "value", "threshold", "verdict_overall", "source_table"]].to_string(index=False))

    print("\n" + "=" * 96)
    print(f"HOÀN TẤT PHÂN TÍCH T10! Đã xuất toàn bộ bảng vào: {tables_dir}")
    print("=" * 96)
    return 0


def parse_args():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--self-check", action="store_true",
                    help="Chạy 6 kiểm tra tự kiểm trên dữ liệu GIAI ĐOẠN 1 (không đọc dữ liệu giai đoạn 2)")
    ap.add_argument("--out", type=Path, default=Path("results_phase2/analysis"),
                    help="Thư mục đầu ra cho phân tích giai đoạn 2 (mặc định: results_phase2/analysis)")
    ap.add_argument("--B", type=int, default=DEFAULT_B,
                    help=f"Số lần lặp bootstrap (mặc định: {DEFAULT_B})")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help=f"Seed bootstrap gốc (mặc định: {DEFAULT_SEED})")
    ap.add_argument("--t11-fixes", action="store_true",
                    help="Áp dụng sửa nhỏ từ R10 (T11 §4): H12 verdict 'XEM TỪNG DỰ ĐOÁN', thêm cột [KP] se_k và z_k vào p2_H13.csv")
    return ap.parse_args()


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    if args.self_check:
        sys.exit(run_self_check(B=args.B))
    sys.exit(run_phase2_analysis(args.out, B=args.B, base_seed=args.seed, t11_fixes=args.t11_fixes))


if __name__ == "__main__":
    main()
