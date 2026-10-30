#!/usr/bin/env python3
"""
scripts/validate_cost_model.py

Thẩm định ngoài mẫu của mô hình chi phí M2 đã chọn ở T03b (T03c & T03c2):
1. Phân bố khác (thang 2^16, sorted, reversed, nearly_sorted, few_distinct).
2. Thang 2^19 như tập thẩm định thật (khớp trên 2^12 + 2^16, dự đoán 2^19 - LOSO).
3. Tách phần giải thích của mô hình (tiết kiệm merge vs chi phí insertion) & hình cột chồng.
4. Phân tích độ nhạy (nhân beta và w1, w2 với 0.8 và 1.25).
5. Phân tích đa cộng tuyến (ma trận tương quan, số điều kiện, SE).
6. Độ lệch trong mẫu cho 3 thang tại các c chính, đánh dấu ngoài CI 95%.
7. Phân tích co mức cải thiện theo thang (scale shrinkage) & so sánh T7/T10.
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm


# ──────────────────────────────────────────────────────────────── hằng số thiết kế & style
SCALES = [2**12, 2**16, 2**19]
SCALE_LABELS = {2**12: "2^12", 2**16: "2^16", 2**19: "2^19"}

INK, INK2, GRID_C, NEUTRAL = "#0b0b0b", "#52514e", "#e2e1dc", "#8d8c86"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#8c564b"]

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


def scale_label_of(n: int) -> str:
    """Xác định thang kích thước từ N."""
    for S in SCALES:
        Ns = round(S * 2 ** (0 / 24))
        Ne = round(S * 2 ** (23 / 24))
        if Ns <= n <= Ne:
            return SCALE_LABELS[S]
    return "unknown"


def load_all_data(results_dir: Path, tree_features_path: Path, counts_path: Path):
    """Nạp dữ liệu thời gian raw, đặc trưng cây và counts cho mọi phân bố."""
    # 1. Đọc raw_fork1, 2, 3
    frames = []
    for f in [1, 2, 3]:
        p = results_dir / f"raw_fork{f}.csv"
        if not p.exists():
            raise FileNotFoundError(f"Không tìm thấy file {p}")
        df_f = pd.read_csv(p)
        frames.append(df_f)
    raw = pd.concat(frames, ignore_index=True)
    raw = raw[raw["gc_during_run"] == False].copy()

    # T(distribution, N, cutoff) = exp(mean(log(time_ns)))
    raw["log_t"] = np.log(raw["time_ns"])
    t_grp = raw.groupby(["distribution", "N", "cutoff"])["log_t"].mean().reset_index()
    t_grp["T"] = np.exp(t_grp["log_t"])
    t_grp.drop(columns=["log_t"], inplace=True)
    t_grp["scale"] = t_grp["N"].map(scale_label_of)

    # 2. Đọc tree_features
    tf = pd.read_csv(tree_features_path)

    # 3. Đọc counts
    cnt = pd.read_csv(counts_path)[["distribution", "N", "cutoff", "exchanges", "compares"]]

    # Nối
    df = pd.merge(t_grp, tf, on=["distribution", "scale", "N", "cutoff"])
    df = pd.merge(df, cnt, on=["distribution", "N", "cutoff"])

    # Tính r_meas
    t1_map = df[df["cutoff"] == 1].set_index(["distribution", "scale", "N"])["T"]
    df["T1_meas"] = df.set_index(["distribution", "scale", "N"]).index.map(t1_map)
    df["r_meas"] = df["T"] / df["T1_meas"]

    df["ML_b456"] = df["ML_b4"] + df["ML_b5"] + df["ML_b6"]
    df["ML_b456_12"] = df["ML_b456"] * (df["scale"] == "2^12")
    df["ML_b456_16"] = df["ML_b456"] * (df["scale"] == "2^16")
    df["ML_b456_19"] = df["ML_b456"] * (df["scale"] == "2^19")

    return df


def validate_other_distributions(df: pd.DataFrame, m2_coef: dict, r_by_cutoff: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """1. Dự đoán trên các phân bố khác (thang 2^16)."""
    w1 = m2_coef["ML_b1"]
    w2 = m2_coef["ML_b2"]
    w3 = m2_coef["ML_b3"]
    beta = m2_coef["exchanges"]
    a16 = m2_coef["ML_b456_16"]

    other_dists = ["sorted", "reversed", "nearly_sorted", "few_distinct"]
    df_16 = df[(df["scale"] == "2^16") & (df["distribution"].isin(other_dists))].copy()

    df_16["That_M2"] = (w1 * df_16["ML_b1"] +
                        w2 * df_16["ML_b2"] +
                        w3 * df_16["ML_b3"] +
                        beta * df_16["exchanges"] +
                        a16 * df_16["ML_b456"])

    t1_map = df_16[df_16["cutoff"] == 1].set_index(["distribution", "N"])["That_M2"]
    df_16["That1_M2"] = df_16.set_index(["distribution", "N"]).index.map(t1_map)
    df_16["rhat_M2"] = df_16["That_M2"] / df_16["That1_M2"]

    # Đường cong trung bình nhân theo cutoff
    rhat_curves = df_16.groupby(["distribution", "cutoff"])["rhat_M2"].apply(lambda s: np.exp(np.mean(np.log(s))))

    detail_rows = []
    summary_rows = []

    for dist in other_dists:
        meas_sub = r_by_cutoff[(r_by_cutoff["distribution"] == dist) & (r_by_cutoff["scale"] == "2^16")].set_index("cutoff")
        rhat_sub = rhat_curves.loc[dist]

        cutoffs = sorted(meas_sub.index.unique())
        for c in cutoffs:
            r_m = meas_sub.loc[c, "r_gm"]
            r_h = rhat_sub.loc[c]
            ci_l = meas_sub.loc[c, "ci_lo"]
            ci_h = meas_sub.loc[c, "ci_hi"]
            diff = r_h - r_m

            detail_rows.append({
                "distribution": dist,
                "scale": "2^16",
                "cutoff": c,
                "r_meas": r_m,
                "ci_lo": ci_l,
                "ci_hi": ci_h,
                "r_hat": r_h,
                "diff": diff,
                "outside_ci": (r_h < ci_l) or (r_h > ci_h)
            })

        # Summary
        c_ge2 = [c for c in cutoffs if c >= 2]
        rmse_r = np.sqrt(np.mean([(rhat_sub.loc[c] - meas_sub.loc[c, "r_gm"]) ** 2 for c in c_ge2]))
        argmin_meas = meas_sub["r_gm"].idxmin()
        argmin_hat = rhat_sub.idxmin()

        summary_rows.append({
            "distribution": dist,
            "scale": "2^16",
            "rmse_r": rmse_r,
            "argmin_meas": argmin_meas,
            "min_r_meas": meas_sub.loc[argmin_meas, "r_gm"],
            "argmin_hat": argmin_hat,
            "min_r_hat": rhat_sub.loc[argmin_hat],
            "note": "Biên lưới c=64" if argmin_meas == 64 else ""
        })

    return pd.DataFrame(detail_rows), pd.DataFrame(summary_rows)


def validate_2e19_loso(df: pd.DataFrame, r_by_cutoff: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """2. Thẩm định thật trên thang 2^19 bằng LOSO (khớp trên 2^12 + 2^16, dự đoán 2^19)."""
    df_rnd = df[df["distribution"] == "random"].copy()
    y = df_rnd["T"]
    weights = 1.0 / (y ** 2)

    train_mask = df_rnd["scale"] != "2^19"
    test_mask = df_rnd["scale"] == "2^19"

    X_train = df_rnd.loc[train_mask, ["ML_b1", "ML_b2", "ML_b3", "exchanges", "ML_b456_12", "ML_b456_16"]]
    mod_tr = sm.WLS(y[train_mask], X_train, weights=weights[train_mask])
    res_tr = mod_tr.fit(cov_type="cluster", cov_kwds={"groups": df_rnd.loc[train_mask, "N"]})

    w1 = res_tr.params["ML_b1"]
    w2 = res_tr.params["ML_b2"]
    w3 = res_tr.params["ML_b3"]
    beta = res_tr.params["exchanges"]

    df_te = df_rnd[test_mask].copy()
    base_te = w1 * df_te["ML_b1"] + w2 * df_te["ML_b2"] + w3 * df_te["ML_b3"] + beta * df_te["exchanges"]
    c1_te = df_te[df_te["cutoff"] == 1]
    c1_base = base_te[df_te["cutoff"] == 1]

    # Hiệu chỉnh alpha_19 từ c=1
    alpha_calib = np.sum((c1_te["T"] - c1_base) * c1_te["ML_b456"]) / np.sum(c1_te["ML_b456"] ** 2)
    df_te["That_loso"] = base_te + alpha_calib * df_te["ML_b456"]

    t1_map = df_te[df_te["cutoff"] == 1].set_index("N")["That_loso"]
    df_te["rhat_loso"] = df_te["That_loso"] / df_te["N"].map(t1_map)

    rhat_19 = df_te.groupby("cutoff")["rhat_loso"].apply(lambda s: np.exp(np.mean(np.log(s))))
    rmeas_19 = df_te.groupby("cutoff")["r_meas"].apply(lambda s: np.exp(np.mean(np.log(s))))

    r_ci_19 = r_by_cutoff[(r_by_cutoff["distribution"] == "random") & (r_by_cutoff["scale"] == "2^19")].set_index("cutoff")

    rows = []
    for c in rhat_19.index:
        r_m = rmeas_19.loc[c]
        r_h = rhat_19.loc[c]
        ci_l = r_ci_19.loc[c, "ci_lo"]
        ci_h = r_ci_19.loc[c, "ci_hi"]
        diff = r_h - r_m

        rows.append({
            "cutoff": c,
            "r_meas": r_m,
            "ci_lo": ci_l,
            "ci_hi": ci_h,
            "r_hat_loso": r_h,
            "diff": diff,
            "outside_ci": (r_h < ci_l) or (r_h > ci_h)
        })

    df_res = pd.DataFrame(rows)
    rmse_r = np.sqrt(np.mean(df_res.loc[df_res["cutoff"] >= 2, "diff"] ** 2))

    min_rhat = df_res["r_hat_loso"].min()
    near_opt_hat = df_res[df_res["r_hat_loso"] <= 1.02 * min_rhat]["cutoff"].tolist()
    min_rmeas = df_res["r_meas"].min()
    near_opt_meas = df_res[df_res["r_meas"] <= 1.02 * min_rmeas]["cutoff"].tolist()

    meta = {
        "alpha_calib": alpha_calib,
        "rmse_r": rmse_r,
        "argmin_meas": df_res.loc[df_res["r_meas"].idxmin(), "cutoff"],
        "min_rmeas": min_rmeas,
        "argmin_hat": df_res.loc[df_res["r_hat_loso"].idxmin(), "cutoff"],
        "min_rhat": min_rhat,
        "near_opt_hat": near_opt_hat,
        "near_opt_meas": near_opt_meas,
    }

    return df_res, meta


def compute_decomposition(df: pd.DataFrame, m2_coef: dict) -> pd.DataFrame:
    """3. Tách phần giải thích của mô hình tại scale 2^16 (tiết kiệm merge vs chi phí insertion)."""
    w1 = m2_coef["ML_b1"]
    w2 = m2_coef["ML_b2"]
    w3 = m2_coef["ML_b3"]
    beta = m2_coef["exchanges"]
    a16 = m2_coef["ML_b456_16"]

    df_16 = df[(df["distribution"] == "random") & (df["scale"] == "2^16")].copy()
    t1_df = df_16[df_16["cutoff"] == 1].set_index("N")

    rows = []
    for (n, c), sub in df_16.groupby(["N", "cutoff"]):
        row1 = t1_df.loc[n]
        row_c = sub.iloc[0]

        t1_hat = (w1 * row1["ML_b1"] + w2 * row1["ML_b2"] + w3 * row1["ML_b3"] +
                  beta * row1["exchanges"] + a16 * row1["ML_b456"])

        dml1 = row1["ML_b1"] - row_c["ML_b1"]
        dml2 = row1["ML_b2"] - row_c["ML_b2"]
        dml3 = row1["ML_b3"] - row_c["ML_b3"]
        save_merge = w1 * dml1 + w2 * dml2 + w3 * dml3
        cost_insert = beta * row_c["exchanges"]

        rows.append({
            "N": n,
            "cutoff": c,
            "ratio_save": save_merge / t1_hat,
            "ratio_insert": cost_insert / t1_hat,
            "net_reduction": (save_merge - cost_insert) / t1_hat,
            "r_hat": 1.0 - (save_merge - cost_insert) / t1_hat
        })

    res = pd.DataFrame(rows)
    mean_decomp = res.groupby("cutoff")[["ratio_save", "ratio_insert", "net_reduction", "r_hat"]].mean().reset_index()
    return mean_decomp


def compute_sensitivity(df: pd.DataFrame, m2_coef: dict) -> pd.DataFrame:
    """4. Phân tích độ nhạy khi nhân beta và w1, w2 với 0.8 và 1.25."""
    w1 = m2_coef["ML_b1"]
    w2 = m2_coef["ML_b2"]
    w3 = m2_coef["ML_b3"]
    beta = m2_coef["exchanges"]
    a16 = m2_coef["ML_b456_16"]

    df_16 = df[(df["distribution"] == "random") & (df["scale"] == "2^16")].copy()

    scenarios = {
        "baseline": (w1, w2, w3, beta, a16),
        "beta * 0.8": (w1, w2, w3, beta * 0.8, a16),
        "beta * 1.25": (w1, w2, w3, beta * 1.25, a16),
        "w12 * 0.8": (w1 * 0.8, w2 * 0.8, w3, beta, a16),
        "w12 * 1.25": (w1 * 1.25, w2 * 1.25, w3, beta, a16),
    }

    rows = []
    for name, (cw1, cw2, cw3, cbeta, ca16) in scenarios.items():
        df_temp = df_16.copy()
        df_temp["That"] = (cw1 * df_temp["ML_b1"] +
                           cw2 * df_temp["ML_b2"] +
                           cw3 * df_temp["ML_b3"] +
                           cbeta * df_temp["exchanges"] +
                           ca16 * df_temp["ML_b456"])

        t1_map = df_temp[df_temp["cutoff"] == 1].set_index("N")["That"]
        df_temp["rhat"] = df_temp["That"] / df_temp["N"].map(t1_map)

        rhat_s = df_temp.groupby("cutoff")["rhat"].apply(lambda s: np.exp(np.mean(np.log(s))))

        best_c = rhat_s.idxmin()
        min_r = rhat_s.min()
        near_opt = rhat_s[rhat_s <= 1.02 * min_r].index.tolist()
        c_star_med = df_temp.groupby("N").apply(lambda d: d.set_index("cutoff")["rhat"].idxmin()).median()

        rows.append({
            "scenario": name,
            "c_star_curve": best_c,
            "min_rhat": min_r,
            "c_star_med_N": c_star_med,
            "near_opt_min": near_opt[0],
            "near_opt_max": near_opt[-1],
            "near_opt_count": len(near_opt),
            "near_opt_range": f"[{near_opt[0]}, {near_opt[-1]}]"
        })

    return pd.DataFrame(rows)


def compute_collinearity(df: pd.DataFrame, m2_coef_df: pd.DataFrame) -> pd.DataFrame:
    """5. Báo cáo ma trận tương quan và số điều kiện của các biến M2 (lưu CSV)."""
    df_rnd = df[df["distribution"] == "random"].copy()
    cols = ["ML_b1", "ML_b2", "ML_b3", "exchanges", "ML_b456"]
    X = df_rnd[cols]
    y = df_rnd["T"]
    X_w = X.div(y, axis=0)

    corr_w = X_w.corr()
    cond_w = float(np.linalg.cond(X_w))

    df_collin = corr_w.reset_index().rename(columns={"index": "variable"})
    param_map = {"ML_b1": "ML_b1", "ML_b2": "ML_b2", "ML_b3": "ML_b3", "exchanges": "exchanges"}
    df_collin["coef"] = df_collin["variable"].map(lambda v: m2_coef_df.loc[param_map[v], "coef"] if v in param_map else np.nan)
    df_collin["std_err"] = df_collin["variable"].map(lambda v: m2_coef_df.loc[param_map[v], "std_err"] if v in param_map else np.nan)
    df_collin["rel_se_pct"] = df_collin["std_err"] / df_collin["coef"].abs() * 100.0
    df_collin["condition_number"] = cond_w

    return df_collin


def compute_in_sample_errors(df: pd.DataFrame, m2_coef: dict, r_by_cutoff: pd.DataFrame) -> pd.DataFrame:
    """6. Bảng sai số có dấu r̂ − r theo c in {7, 10, 20, 30, 40, 48, 64} cho 3 thang."""
    w1 = m2_coef["ML_b1"]
    w2 = m2_coef["ML_b2"]
    w3 = m2_coef["ML_b3"]
    beta = m2_coef["exchanges"]
    a12 = m2_coef["ML_b456_12"]
    a16 = m2_coef["ML_b456_16"]
    a19 = m2_coef["ML_b456_19"]

    df_rnd = df[df["distribution"] == "random"].copy()

    # Tính That theo từng thang
    df_rnd["That_M2"] = (w1 * df_rnd["ML_b1"] +
                         w2 * df_rnd["ML_b2"] +
                         w3 * df_rnd["ML_b3"] +
                         beta * df_rnd["exchanges"] +
                         a12 * df_rnd["ML_b456_12"] +
                         a16 * df_rnd["ML_b456_16"] +
                         a19 * df_rnd["ML_b456_19"])

    t1_map = df_rnd[df_rnd["cutoff"] == 1].set_index(["scale", "N"])["That_M2"]
    df_rnd["That1_M2"] = df_rnd.set_index(["scale", "N"]).index.map(t1_map)
    df_rnd["rhat_M2"] = df_rnd["That_M2"] / df_rnd["That1_M2"]

    r_rnd = r_by_cutoff[r_by_cutoff["distribution"] == "random"].set_index(["scale", "cutoff"])

    scales = ["2^12", "2^16", "2^19"]
    cutoffs = [7, 10, 20, 30, 40, 48, 64]

    rows = []
    for s in scales:
        sub = df_rnd[df_rnd["scale"] == s]
        rhat_s = sub.groupby("cutoff")["rhat_M2"].apply(lambda col: np.exp(np.mean(np.log(col))))
        rmeas_s = sub.groupby("cutoff")["r_meas"].apply(lambda col: np.exp(np.mean(np.log(col))))

        for c in cutoffs:
            r_meas = rmeas_s.loc[c]
            r_hat = rhat_s.loc[c]
            signed_diff = r_hat - r_meas

            ci_lo = r_rnd.loc[(s, c), "ci_lo"]
            ci_hi = r_rnd.loc[(s, c), "ci_hi"]
            outside_ci = (r_hat < ci_lo) or (r_hat > ci_hi)

            rows.append({
                "scale": s,
                "cutoff": c,
                "r_meas": r_meas,
                "ci_lo": ci_lo,
                "ci_hi": ci_hi,
                "r_hat_M2": r_hat,
                "signed_diff": signed_diff,
                "outside_ci_95": outside_ci
            })

    return pd.DataFrame(rows)


def compute_scale_shrinkage(df: pd.DataFrame, m2_coef: dict) -> pd.DataFrame:
    """7. Phân tích co mức cải thiện theo thang và kịch bản thay thế alpha_19 bằng alpha_16."""
    w1 = m2_coef["ML_b1"]
    w2 = m2_coef["ML_b2"]
    w3 = m2_coef["ML_b3"]
    beta = m2_coef["exchanges"]
    a12 = m2_coef["ML_b456_12"]
    a16 = m2_coef["ML_b456_16"]
    a19 = m2_coef["ML_b456_19"]

    df_rnd = df[df["distribution"] == "random"].copy()
    c1_df = df_rnd[df_rnd["cutoff"] == 1].copy()
    c1_df["ratio_b123"] = (c1_df["ML_b1"] + c1_df["ML_b2"] + c1_df["ML_b3"]) / c1_df["ML"]

    t1_meas = df_rnd[df_rnd["cutoff"] == 1].set_index(["scale", "N"])["T"]
    df_rnd["r_meas"] = df_rnd["T"] / df_rnd.set_index(["scale", "N"]).index.map(t1_meas)

    shrink_rows = []
    for s in ["2^12", "2^16", "2^19"]:
        sub = df_rnd[df_rnd["scale"] == s].copy()
        ratio_c1 = c1_df[c1_df["scale"] == s]["ratio_b123"].mean()

        as_val = a12 if s == "2^12" else (a16 if s == "2^16" else a19)
        sub["That_norm"] = w1 * sub["ML_b1"] + w2 * sub["ML_b2"] + w3 * sub["ML_b3"] + beta * sub["exchanges"] + as_val * sub["ML_b456"]
        t1_norm = sub[sub["cutoff"] == 1].set_index("N")["That_norm"]
        sub["rhat_norm"] = sub["That_norm"] / sub["N"].map(t1_norm)
        rhat30_norm = np.exp(np.mean(np.log(sub[sub["cutoff"] == 30]["rhat_norm"])))

        # Counterfactual: thay alpha bằng alpha_16
        sub["That_cf"] = w1 * sub["ML_b1"] + w2 * sub["ML_b2"] + w3 * sub["ML_b3"] + beta * sub["exchanges"] + a16 * sub["ML_b456"]
        t1_cf = sub[sub["cutoff"] == 1].set_index("N")["That_cf"]
        sub["rhat_cf"] = sub["That_cf"] / sub["N"].map(t1_cf)
        rhat30_cf = np.exp(np.mean(np.log(sub[sub["cutoff"] == 30]["rhat_cf"])))

        rmeas30 = np.exp(np.mean(np.log(sub[sub["cutoff"] == 30]["r_meas"])))

        shrink_rows.append({
            "scale": s,
            "ratio_b123_at_c1": ratio_c1,
            "rhat30_normal": rhat30_norm,
            "rhat30_cf_alpha16": rhat30_cf,
            "rmeas30": rmeas30
        })

    return pd.DataFrame(shrink_rows)


def compute_t7_t10_table(df: pd.DataFrame, m2_coef: dict) -> pd.DataFrame:
    """8. Bảng so sánh T7/T10 đo thực nghiệm vs mô hình M2."""
    w1 = m2_coef["ML_b1"]
    w2 = m2_coef["ML_b2"]
    w3 = m2_coef["ML_b3"]
    beta = m2_coef["exchanges"]
    a12 = m2_coef["ML_b456_12"]
    a16 = m2_coef["ML_b456_16"]
    a19 = m2_coef["ML_b456_19"]

    df_rnd = df[df["distribution"] == "random"].copy()
    t1_meas = df_rnd[df_rnd["cutoff"] == 1].set_index(["scale", "N"])["T"]
    df_rnd["r_meas"] = df_rnd["T"] / df_rnd.set_index(["scale", "N"]).index.map(t1_meas)

    t710_rows = []
    for s in ["2^12", "2^16", "2^19"]:
        sub = df_rnd[df_rnd["scale"] == s].copy()
        as_val = a12 if s == "2^12" else (a16 if s == "2^16" else a19)
        sub["That"] = w1 * sub["ML_b1"] + w2 * sub["ML_b2"] + w3 * sub["ML_b3"] + beta * sub["exchanges"] + as_val * sub["ML_b456"]
        t1_hat = sub[sub["cutoff"] == 1].set_index("N")["That"]
        sub["rhat"] = sub["That"] / sub["N"].map(t1_hat)

        rmeas_s = sub.groupby("cutoff")["r_meas"].apply(lambda c: np.exp(np.mean(np.log(c))))
        rhat_s = sub.groupby("cutoff")["rhat"].apply(lambda c: np.exp(np.mean(np.log(c))))

        t7_t10_meas = rmeas_s.loc[7] / rmeas_s.loc[10]
        t7_t10_hat = rhat_s.loc[7] / rhat_s.loc[10]

        t710_rows.append({
            "scale": s,
            "t7_t10_meas": t7_t10_meas,
            "t7_t10_hat": t7_t10_hat,
            "diff": t7_t10_hat - t7_t10_meas
        })

    return pd.DataFrame(t710_rows)


def plot_decomposition(decomp_df: pd.DataFrame, out_path: Path):
    """Vẽ hình cột chồng phân rã đóng góp của tiết kiệm merge và chi phí insertion."""
    fig, ax = plt.subplots(figsize=(7.5, 4.0))

    sub = decomp_df[decomp_df["cutoff"].isin([2, 4, 7, 10, 16, 20, 24, 30, 40, 48, 64])].copy()
    cutoffs = sub["cutoff"].values
    x = np.arange(len(cutoffs))

    save_pct = sub["ratio_save"].values * 100
    insert_pct = sub["ratio_insert"].values * 100
    net_pct = sub["net_reduction"].values * 100

    width = 0.35
    ax.bar(x - width / 2, save_pct, width=width, color=SERIES[2], label="Tiết kiệm từ merge (bỏ b1..b3)", alpha=0.9)
    ax.bar(x + width / 2, insert_pct, width=width, color=SERIES[1], label="Chi phí thêm từ insertion ($\\beta \\cdot E$)", alpha=0.9)
    ax.plot(x, net_pct, "o--", color=INK, linewidth=1.5, markersize=5, label="Mức giảm thời gian ròng $(1 - \\hat{r})$")

    ax.set_xticks(x)
    ax.set_xticklabels([str(c) for c in cutoffs])
    ax.set_xlabel("Cutoff $c$")
    ax.set_ylabel("Tỷ lệ phần trăm trên $T(c=1)$ (%)")
    ax.set_title("Phân rã cơ chế tối ưu mô hình M2 tại thang $2^{16}$ (trung bình 24 $N$)", fontweight="bold", pad=10)
    ax.legend(loc="upper left", frameon=True, framealpha=0.9, facecolor="white")
    ax.set_ylim(0, 38)

    # Đánh dấu vùng đáy phẳng 16-48
    ax.axvspan(4 - 0.4, 9 + 0.4, color=NEUTRAL, alpha=0.15, label="Vùng đáy phẳng [16, 48]")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    print(f"  Đã lưu hình: {out_path} và .pdf")


def plot_sensitivity_curves(df: pd.DataFrame, m2_coef: dict, out_path: Path):
    """Vẽ đường cong r̂(c) trong các kịch bản độ nhạy."""
    fig, ax = plt.subplots(figsize=(6.8, 3.8))

    w1 = m2_coef["ML_b1"]
    w2 = m2_coef["ML_b2"]
    w3 = m2_coef["ML_b3"]
    beta = m2_coef["exchanges"]
    a16 = m2_coef["ML_b456_16"]

    df_16 = df[(df["distribution"] == "random") & (df["scale"] == "2^16")].copy()

    scenarios = {
        "Baseline": (w1, w2, w3, beta, a16, INK, "-"),
        "$\\beta \\times 0.8$ (insertion rẻ hơn)": (w1, w2, w3, beta * 0.8, a16, SERIES[2], "--"),
        "$\\beta \\times 1.25$ (insertion đắt hơn)": (w1, w2, w3, beta * 1.25, a16, SERIES[1], "--"),
        "$w_{1,2} \\times 0.8$ (tiết kiệm merge ít)": (w1 * 0.8, w2 * 0.8, w3, beta, a16, SERIES[3], ":"),
        "$w_{1,2} \\times 1.25$ (tiết kiệm merge nhiều)": (w1 * 1.25, w2 * 1.25, w3, beta, a16, SERIES[0], ":"),
    }

    cutoffs = sorted(df_16["cutoff"].unique())

    for label, (cw1, cw2, cw3, cbeta, ca16, color, ls) in scenarios.items():
        df_temp = df_16.copy()
        df_temp["That"] = (cw1 * df_temp["ML_b1"] +
                           cw2 * df_temp["ML_b2"] +
                           cw3 * df_temp["ML_b3"] +
                           cbeta * df_temp["exchanges"] +
                           ca16 * df_temp["ML_b456"])

        t1_map = df_temp[df_temp["cutoff"] == 1].set_index("N")["That"]
        df_temp["rhat"] = df_temp["That"] / df_temp["N"].map(t1_map)
        rhat_s = df_temp.groupby("cutoff")["rhat"].apply(lambda s: np.exp(np.mean(np.log(s))))

        ax.plot(cutoffs, rhat_s.values, ls, color=color, linewidth=1.5, label=label)

    ax.axhline(1.0, color=NEUTRAL, linestyle=":", linewidth=0.8)
    ax.axvspan(24, 40, color=NEUTRAL, alpha=0.15, label="Giao các vùng tối ưu [24, 40]")
    ax.set_xlabel("Cutoff $c$")
    ax.set_ylabel("Tỷ số thời gian $\\hat{r}(c) = \\hat{T}(c) / \\hat{T}(1)$")
    ax.set_title("Phân tích độ nhạy của đường cong $\\hat{r}(c)$ trên thang $2^{16}$", fontweight="bold", pad=10)
    ax.legend(loc="upper right", frameon=True, framealpha=0.9, facecolor="white", fontsize=8)
    ax.set_xlim(0, 66)
    ax.set_ylim(0.82, 1.02)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    print(f"  Đã lưu hình: {out_path} và .pdf")


def plot_other_distributions(detail_df: pd.DataFrame, out_path: Path):
    """Vẽ so sánh r đo vs r̂ mô hình trên 4 phân bố khác."""
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 7.0), sharex=True, sharey=True)
    axes = axes.flatten()

    dists = ["sorted", "reversed", "nearly_sorted", "few_distinct"]
    titles = ["Sorted", "Reversed", "Nearly Sorted (~1%)", "Few Distinct (10 giá trị)"]

    for ax, dist, title in zip(axes, dists, titles):
        sub = detail_df[detail_df["distribution"] == dist].sort_values("cutoff")
        cutoffs = sub["cutoff"].values
        r_m = sub["r_meas"].values
        r_h = sub["r_hat"].values
        ci_l = sub["ci_lo"].values
        ci_h = sub["ci_hi"].values

        ax.fill_between(cutoffs, ci_l, ci_h, color=SERIES[0], alpha=0.18, label="95% CI (đo)")
        ax.plot(cutoffs, r_m, "o-", color=SERIES[0], markersize=4, linewidth=1.2, label="Đo thực nghiệm")
        ax.plot(cutoffs, r_h, "--s", color="#d9381e", markersize=4, linewidth=1.4, label="Mô hình M2 (từ random)")

        ax.axhline(1.0, color=NEUTRAL, linestyle=":", linewidth=0.8)
        ax.set_title(title, fontweight="bold", pad=8)
        ax.set_xlabel("Cutoff $c$")
        ax.set_ylabel("$r(c) = T(c)/T(1)$")

    axes[0].legend(loc="upper right", frameon=True, framealpha=0.9, facecolor="white")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    print(f"  Đã lưu hình: {out_path} và .pdf")


def print_rule_a_checks(summary_other: pd.DataFrame, meta_19: dict, df_errors: pd.DataFrame, df_collin: pd.DataFrame, df_shrink: pd.DataFrame, df_t710: pd.DataFrame):
    """In đầy đủ các kiểm tra chất lượng theo Quy tắc A (in hai số cạnh nhau)."""
    print("\n" + "=" * 80)
    print("KIỂM TRA CHẤT LƯỢNG VÀ ĐỐI CHIẾU THAM CHIẾU (QUY TẮC CHẤT LƯỢNG A)")
    print("=" * 80)

    # 1. Phân bố khác
    print("\n[MỤC 1: THẨM ĐỊNH NGOÀI MẪU TRÊN 4 PHÂN BỐ KHÁC (THANG 2^16)]")
    for _, r in summary_other.iterrows():
        print(f"  Phân bố {r['distribution']:<14}: RMSE(r) = {r['rmse_r']:.4f} | "
              f"argmin đo = {r['argmin_meas']:2d} (r={r['min_r_meas']:.4f}) | "
              f"argmin mô hình = {r['argmin_hat']:2d} (r={r['min_r_hat']:.4f}) {r['note']}")

    # 2. Thang 2^19 LOSO
    print("\n[MỤC 2: THẨM ĐỊNH NGOÀI MẪU TRÊN THANG 2^19 (LOSO)]")
    print(f"  RMSE(r):            tính = {meta_19['rmse_r']:.5f} | tham chiếu = 0.00300 | chênh = {meta_19['rmse_r'] - 0.00300:+.5f}")
    print(f"  argmin đo:          {meta_19['argmin_meas']} (r = {meta_19['min_rmeas']:.4f})")
    print(f"  argmin mô hình:     {meta_19['argmin_hat']} (r = {meta_19['min_rhat']:.4f})")
    print(f"  Vùng gần opt 2% đo: {meta_19['near_opt_meas']}")
    print(f"  Vùng gần opt 2% MH: {meta_19['near_opt_hat']}")

    # 3. Đa cộng tuyến
    print("\n[MỤC 5: ĐA CỘNG TUYẾN]")
    cond_val = df_collin["condition_number"].iloc[0]
    print(f"  Condition number của ma trận trọng số (X/T): {cond_val:.2f}")
    for _, r in df_collin.dropna(subset=["coef"]).iterrows():
        print(f"  {r['variable']:<10}: coef = {r['coef']:8.4f}, std_err = {r['std_err']:8.4f}, rel_se = {r['rel_se_pct']:5.2f}%")

    # 4. Độ lệch trong mẫu
    print("\n[MỤC 6: ĐỘ LỆCH TRONG MẪU VÀ ĐÁNH DẤU NGOÀI CI 95%]")
    print(df_errors.to_string(index=False, formatters={
        "r_meas": lambda x: f"{x:.4f}",
        "ci_lo": lambda x: f"{x:.4f}",
        "ci_hi": lambda x: f"{x:.4f}",
        "r_hat_M2": lambda x: f"{x:.4f}",
        "signed_diff": lambda x: f"{x:+.4f}",
    }))

    # 5. Co mức cải thiện theo thang
    print("\n[MỤC 7: CO MỨC CẢI THIỆN THEO THANG]")
    print(df_shrink.to_string(index=False, formatters={
        "ratio_b123_at_c1": lambda x: f"{x:.4f}",
        "rhat30_normal": lambda x: f"{x:.4f}",
        "rhat30_cf_alpha16": lambda x: f"{x:.4f}",
        "rmeas30": lambda x: f"{x:.4f}",
    }))

    # 6. T7 / T10
    print("\n[MỤC 8: SO SÁNH T7 / T10]")
    print(df_t710.to_string(index=False, formatters={
        "t7_t10_meas": lambda x: f"{x:.4f}",
        "t7_t10_hat": lambda x: f"{x:.4f}",
        "diff": lambda x: f"{x:+.4f}",
    }))
    print("=" * 80 + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Thẩm định ngoài mẫu của mô hình chi phí M2 (T03c & T03c2)."
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("results_final"),
        help="Thư mục dữ liệu kết quả (mặc định: results_final)",
    )
    parser.add_argument(
        "--tree-features",
        type=Path,
        default=Path("results_final/analysis_v2/tables/tree_features.csv"),
        help="Đường dẫn tree_features.csv (mặc định: results_final/analysis_v2/tables/tree_features.csv)",
    )
    parser.add_argument(
        "--counts",
        type=Path,
        default=Path("results_final/counts.csv"),
        help="Đường dẫn counts.csv (mặc định: results_final/counts.csv)",
    )
    parser.add_argument(
        "--out-tables",
        type=Path,
        default=Path("results_final/analysis_v2/tables"),
        help="Thư mục lưu bảng CSV (mặc định: results_final/analysis_v2/tables)",
    )
    parser.add_argument(
        "--out-figures",
        type=Path,
        default=Path("results_final/analysis_v2/figures"),
        help="Thư mục lưu hình ảnh (mặc định: results_final/analysis_v2/figures)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Hạt giống ngẫu nhiên (mặc định: 42)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    np.random.seed(args.seed)

    print("=" * 80)
    print("T03c & T03c2: THẨM ĐỊNH NGOÀI MẪU CỦA MÔ HÌNH CHI PHÍ M2")
    print("=" * 80)

    # 1. Nạp dữ liệu
    print("\n[1/7] Đang nạp toàn bộ dữ liệu...")
    df = load_all_data(args.results, args.tree_features, args.counts)
    r_by_cutoff = pd.read_csv(args.results / "analysis" / "tables" / "r_by_cutoff.csv")
    m2_coef_df = pd.read_csv(args.out_tables / "cost_model_M2_coef.csv").set_index("parameter")
    m2_coef = m2_coef_df["coef"].to_dict()

    # 2. Thẩm định phân bố khác
    print("\n[2/7] Đang thẩm định trên 4 phân bố khác...")
    df_other_detail, df_other_summary = validate_other_distributions(df, m2_coef, r_by_cutoff)

    # 3. Thẩm định thang 2^19 LOSO
    print("\n[3/7] Đang thẩm định trên thang 2^19 (LOSO)...")
    df_2e19_loso, meta_19 = validate_2e19_loso(df, r_by_cutoff)

    # 4. Phân rã đóng góp & Phân tích độ nhạy
    print("\n[4/7] Đang tính phân rã đóng góp và phân tích độ nhạy...")
    df_decomp = compute_decomposition(df, m2_coef)
    df_sens = compute_sensitivity(df, m2_coef)

    # 5. Đa cộng tuyến & Độ lệch trong mẫu
    print("\n[5/7] Đang kiểm tra đa cộng tuyến và độ lệch trong mẫu...")
    df_collin = compute_collinearity(df, m2_coef_df)
    df_in_sample_errors = compute_in_sample_errors(df, m2_coef, r_by_cutoff)

    # 6. Co mức cải thiện theo thang & T7/T10
    print("\n[6/7] Đang tính co mức cải thiện theo thang và so sánh T7/T10...")
    df_shrink = compute_scale_shrinkage(df, m2_coef)
    df_t710 = compute_t7_t10_table(df, m2_coef)

    # In kiểm tra chất lượng (Quy tắc A)
    print_rule_a_checks(df_other_summary, meta_19, df_in_sample_errors, df_collin, df_shrink, df_t710)

    # 7. Lưu bảng CSV
    print("[7/7] Đang lưu các bảng CSV và đồ thị...")
    args.out_tables.mkdir(parents=True, exist_ok=True)
    args.out_figures.mkdir(parents=True, exist_ok=True)

    df_other_detail.to_csv(args.out_tables / "validate_other_distributions.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'validate_other_distributions.csv'}")

    df_other_summary.to_csv(args.out_tables / "validate_other_summary.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'validate_other_summary.csv'}")

    df_2e19_loso.to_csv(args.out_tables / "validate_2e19_loso.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'validate_2e19_loso.csv'}")

    df_decomp.to_csv(args.out_tables / "cost_model_decomposition.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_decomposition.csv'}")

    df_sens.to_csv(args.out_tables / "cost_model_sensitivity.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_sensitivity.csv'}")

    df_in_sample_errors.to_csv(args.out_tables / "cost_model_in_sample_errors.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_in_sample_errors.csv'}")

    df_collin.to_csv(args.out_tables / "cost_model_collinearity.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_collinearity.csv'}")

    df_shrink.to_csv(args.out_tables / "cost_model_scale_shrinkage.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_scale_shrinkage.csv'}")

    df_t710.to_csv(args.out_tables / "cost_model_t7_t10.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_t7_t10.csv'}")

    # Vẽ và lưu hình ảnh
    plot_decomposition(df_decomp, args.out_figures / "fig_cost_model_decomp.png")
    plot_sensitivity_curves(df, m2_coef, args.out_figures / "fig_cost_model_sensitivity.png")
    plot_other_distributions(df_other_detail, args.out_figures / "fig_cost_model_other_dist.png")

    print("\nHoàn thành T03c & T03c2 thành công!")


if __name__ == "__main__":
    main()
