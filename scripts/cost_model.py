#!/usr/bin/env python3
"""
scripts/cost_model.py

Khớp mô hình chi phí thời gian từ số đếm trên phân bố random (T03b):
- T(N, c): trung bình nhân của time_ns (1 lần sắp) trên mọi fork và trial (gc_during_run == False).
- Đặc trưng: tree_features.csv nối với counts.csv theo (distribution, N, cutoff).
- Mục tiêu: WLS với trọng số 1/T^2, sai số chuẩn cluster theo N.
- 3 mô hình theo thứ tự cố định:
    M0: chi phí merge hằng số theo thang (T = alpha_s*ML + beta*exchanges + gamma*leaves2)
    M1: 6 bucket merge dùng chung ba thang (T = sum w_k*ML_bk + beta*exchanges)
    M2: merge nhỏ dùng chung, merge lớn riêng từng thang
        (T = w1*ML_b1 + w2*ML_b2 + w3*ML_b3 + beta*exchanges + alpha_s*ML_b456)
- Thẩm định bằng Bỏ-một-thang (Leave-One-Scale-Out - LOSO).
- Tích hợp: c*, vùng gần tối ưu 2%, và công thức đóng L*.
- Sinh các bảng và hình vào results_final/analysis_v2/.
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
import statsmodels.api as sm


# ──────────────────────────────────────────────────────────────── hằng số thiết kế & style
SCALES = [2**12, 2**16, 2**19]
SCALE_LABELS = {2**12: "2^12", 2**16: "2^16", 2**19: "2^19"}

INK, INK2, GRID_C, NEUTRAL = "#0b0b0b", "#52514e", "#e2e1dc", "#8d8c86"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]

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


def load_dataset(results_dir: Path, tree_features_path: Path, counts_path: Path) -> pd.DataFrame:
    """Nạp dữ liệu thời gian raw, đặc trưng cây và counts cho phân bố random."""
    # 1. Đọc raw_fork1, 2, 3
    frames = []
    for f in [1, 2, 3]:
        p = results_dir / f"raw_fork{f}.csv"
        if not p.exists():
            raise FileNotFoundError(f"Không tìm thấy file {p}")
        df_f = pd.read_csv(p)
        frames.append(df_f)
    raw = pd.concat(frames, ignore_index=True)
    raw = raw[(raw["distribution"] == "random") & (raw["gc_during_run"] == False)].copy()

    # T(N, c) = trung bình nhân của time_ns (đã là 1 lần sắp) trên mọi fork và trial
    raw["log_t"] = np.log(raw["time_ns"])
    t_grp = raw.groupby(["N", "cutoff"])["log_t"].mean().reset_index()
    t_grp["T"] = np.exp(t_grp["log_t"])
    t_grp.drop(columns=["log_t"], inplace=True)
    t_grp["scale"] = t_grp["N"].map(scale_label_of)

    # 2. Đọc tree_features
    if not tree_features_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file {tree_features_path}")
    tf = pd.read_csv(tree_features_path)
    tf = tf[tf["distribution"] == "random"].copy()

    # 3. Đọc counts
    if not counts_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file {counts_path}")
    cnt = pd.read_csv(counts_path)
    cnt = cnt[cnt["distribution"] == "random"][["N", "cutoff", "exchanges", "compares"]].copy()

    # Nối dữ liệu
    df = pd.merge(t_grp, tf, on=["scale", "N", "cutoff"])
    df = pd.merge(df, cnt, on=["N", "cutoff"])

    # Tính T(N, 1) và r đo cho từng (N, c)
    t1_map = df[df["cutoff"] == 1].set_index(["scale", "N"])["T"]
    df["T1_meas"] = df.set_index(["scale", "N"]).index.map(t1_map)
    df["r_meas"] = df["T"] / df["T1_meas"]

    # Biến tương tác cho M0 và M2
    df["ML_12"] = df["ML"] * (df["scale"] == "2^12")
    df["ML_16"] = df["ML"] * (df["scale"] == "2^16")
    df["ML_19"] = df["ML"] * (df["scale"] == "2^19")

    df["ML_b456"] = df["ML_b4"] + df["ML_b5"] + df["ML_b6"]
    df["ML_b456_12"] = df["ML_b456"] * (df["scale"] == "2^12")
    df["ML_b456_16"] = df["ML_b456"] * (df["scale"] == "2^16")
    df["ML_b456_19"] = df["ML_b456"] * (df["scale"] == "2^19")

    return df


def extract_coef_table(res, model_name: str) -> pd.DataFrame:
    """Trích xuất bảng hệ số, SE cluster, z, p, CI."""
    conf = res.conf_int()
    rows = []
    for param in res.params.index:
        coef = res.params[param]
        se = res.bse[param]
        z = res.tvalues[param]
        p = res.pvalues[param]
        ci_lo = conf.loc[param, 0]
        ci_hi = conf.loc[param, 1]
        rows.append({
            "model": model_name,
            "parameter": param,
            "coef": coef,
            "std_err": se,
            "z": z,
            "p_value": p,
            "ci_lower": ci_lo,
            "ci_upper": ci_hi,
        })
    return pd.DataFrame(rows)


def compute_r_curves(df: pd.DataFrame, that_col: str) -> dict[str, pd.Series]:
    """Tính đường cong r̂(c) theo từng thang bằng trung bình nhân trên N."""
    curves = {}
    for s in ["2^12", "2^16", "2^19"]:
        sub = df[df["scale"] == s].copy()
        t1_sub = sub[sub["cutoff"] == 1].set_index("N")[that_col]
        sub["r_hat"] = sub[that_col] / sub["N"].map(t1_sub)
        r_curve = sub.groupby("cutoff")["r_hat"].apply(lambda col: np.exp(np.mean(np.log(col))))
        curves[s] = r_curve
    return curves


def fit_and_evaluate_models(df: pd.DataFrame):
    """
    Khớp và đánh giá M0, M1, M2 (cả trong mẫu và thẩm định bỏ-một-thang LOSO).
    """
    y = df["T"]
    weights = 1.0 / (y ** 2)

    # ────────────────────────────────────────────────────────────────
    # M0: T = alpha_s*ML + beta*exchanges + gamma*leaves2
    # ────────────────────────────────────────────────────────────────
    cols_m0 = ["ML_12", "ML_16", "ML_19", "exchanges", "leaves2"]
    X_m0 = df[cols_m0]
    mod_m0 = sm.WLS(y, X_m0, weights=weights)
    res_m0 = mod_m0.fit(cov_type="cluster", cov_kwds={"groups": df["N"]})
    df_coef_m0 = extract_coef_table(res_m0, "M0")

    df["That_M0"] = res_m0.predict(X_m0)
    t1_m0 = df[df["cutoff"] == 1].set_index(["scale", "N"])["That_M0"]
    df["That1_M0"] = df.set_index(["scale", "N"]).index.map(t1_m0)
    df["rhat_M0"] = df["That_M0"] / df["That1_M0"]

    # ────────────────────────────────────────────────────────────────
    # M1: T = sum_{k=1..6} w_k*ML_bk + beta*exchanges
    # ────────────────────────────────────────────────────────────────
    cols_m1 = ["ML_b1", "ML_b2", "ML_b3", "ML_b4", "ML_b5", "ML_b6", "exchanges"]
    X_m1 = df[cols_m1]
    mod_m1 = sm.WLS(y, X_m1, weights=weights)
    res_m1 = mod_m1.fit(cov_type="cluster", cov_kwds={"groups": df["N"]})
    df_coef_m1 = extract_coef_table(res_m1, "M1")

    df["That_M1"] = res_m1.predict(X_m1)
    t1_m1 = df[df["cutoff"] == 1].set_index(["scale", "N"])["That_M1"]
    df["That1_M1"] = df.set_index(["scale", "N"]).index.map(t1_m1)
    df["rhat_M1"] = df["That_M1"] / df["That1_M1"]

    # ────────────────────────────────────────────────────────────────
    # M2: T = w1*ML_b1 + w2*ML_b2 + w3*ML_b3 + beta*exchanges + alpha_s*ML_b456
    # ────────────────────────────────────────────────────────────────
    cols_m2 = ["ML_b1", "ML_b2", "ML_b3", "exchanges", "ML_b456_12", "ML_b456_16", "ML_b456_19"]
    X_m2 = df[cols_m2]
    mod_m2 = sm.WLS(y, X_m2, weights=weights)
    res_m2 = mod_m2.fit(cov_type="cluster", cov_kwds={"groups": df["N"]})
    df_coef_m2 = extract_coef_table(res_m2, "M2")

    df["That_M2"] = res_m2.predict(X_m2)
    t1_m2 = df[df["cutoff"] == 1].set_index(["scale", "N"])["That_M2"]
    df["That1_M2"] = df.set_index(["scale", "N"]).index.map(t1_m2)
    df["rhat_M2"] = df["That_M2"] / df["That1_M2"]

    # ────────────────────────────────────────────────────────────────
    # Đo thực nghiệm r_meas đường cong theo thang
    # ────────────────────────────────────────────────────────────────
    r_meas_curves = {}
    for s in ["2^12", "2^16", "2^19"]:
        sub = df[df["scale"] == s]
        r_meas_curves[s] = sub.groupby("cutoff")["r_meas"].apply(lambda col: np.exp(np.mean(np.log(col))))

    # ────────────────────────────────────────────────────────────────
    # THẨM ĐỊNH BỎ-MỘT-THANG (LOSO)
    # ────────────────────────────────────────────────────────────────
    loso_rows = []

    # 1. M0 LOSO
    for holdout_scale in ["2^12", "2^16", "2^19"]:
        train_mask = df["scale"] != holdout_scale
        test_mask = df["scale"] == holdout_scale
        train_scales = [s for s in ["2^12", "2^16", "2^19"] if s != holdout_scale]

        cols_train = ["exchanges", "leaves2"] + [f"ML_{s[2:]}" for s in train_scales]
        X_train = df.loc[train_mask, cols_train]
        y_train = y[train_mask]
        w_train = weights[train_mask]

        mod_tr = sm.WLS(y_train, X_train, weights=w_train)
        res_tr = mod_tr.fit(cov_type="cluster", cov_kwds={"groups": df.loc[train_mask, "N"]})
        beta_tr = res_tr.params["exchanges"]
        gamma_tr = res_tr.params["leaves2"]

        df_te = df[test_mask].copy()
        base_te = beta_tr * df_te["exchanges"] + gamma_tr * df_te["leaves2"]
        c1_te = df_te[df_te["cutoff"] == 1]
        c1_base = base_te[df_te["cutoff"] == 1]
        alpha_calib = np.sum((c1_te["T"] - c1_base) * c1_te["ML"]) / np.sum(c1_te["ML"] ** 2)

        df_te["That_loso"] = base_te + alpha_calib * df_te["ML"]
        t1_map = df_te[df_te["cutoff"] == 1].set_index("N")["That_loso"]
        df_te["rhat_loso"] = df_te["That_loso"] / df_te["N"].map(t1_map)

        rhat_s = df_te.groupby("cutoff")["rhat_loso"].apply(lambda col: np.exp(np.mean(np.log(col))))
        r_meas_s = r_meas_curves[holdout_scale]
        rmse_r = np.sqrt(np.mean((rhat_s.loc[2:64] - r_meas_s.loc[2:64]) ** 2))

        loso_rows.append({
            "model": "M0",
            "holdout_scale": holdout_scale,
            "rmse_r": rmse_r,
            "r7_meas": r_meas_s.loc[7],
            "r7_hat": rhat_s.loc[7],
            "r10_meas": r_meas_s.loc[10],
            "r10_hat": rhat_s.loc[10],
            "r30_meas": r_meas_s.loc[30],
            "r30_hat": rhat_s.loc[30],
        })

    # 2. M1 LOSO
    for holdout_scale in ["2^12", "2^16", "2^19"]:
        train_mask = df["scale"] != holdout_scale
        test_mask = df["scale"] == holdout_scale

        X_train = df.loc[train_mask, cols_m1]
        y_train = y[train_mask]
        w_train = weights[train_mask]

        mod_tr = sm.WLS(y_train, X_train, weights=w_train)
        res_tr = mod_tr.fit(cov_type="cluster", cov_kwds={"groups": df.loc[train_mask, "N"]})

        df_te = df[test_mask].copy()
        df_te["That_loso"] = res_tr.predict(X_m1.loc[test_mask])
        t1_map = df_te[df_te["cutoff"] == 1].set_index("N")["That_loso"]
        df_te["rhat_loso"] = df_te["That_loso"] / df_te["N"].map(t1_map)

        rhat_s = df_te.groupby("cutoff")["rhat_loso"].apply(lambda col: np.exp(np.mean(np.log(col))))
        r_meas_s = r_meas_curves[holdout_scale]
        rmse_r = np.sqrt(np.mean((rhat_s.loc[2:64] - r_meas_s.loc[2:64]) ** 2))

        loso_rows.append({
            "model": "M1",
            "holdout_scale": holdout_scale,
            "rmse_r": rmse_r,
            "r7_meas": r_meas_s.loc[7],
            "r7_hat": rhat_s.loc[7],
            "r10_meas": r_meas_s.loc[10],
            "r10_hat": rhat_s.loc[10],
            "r30_meas": r_meas_s.loc[30],
            "r30_hat": rhat_s.loc[30],
        })

    # 3. M2 LOSO
    for holdout_scale in ["2^12", "2^16", "2^19"]:
        train_mask = df["scale"] != holdout_scale
        test_mask = df["scale"] == holdout_scale
        train_scales = [s for s in ["2^12", "2^16", "2^19"] if s != holdout_scale]

        cols_train = ["ML_b1", "ML_b2", "ML_b3", "exchanges"] + [f"ML_b456_{s[2:]}" for s in train_scales]
        X_train = df.loc[train_mask, cols_train]
        y_train = y[train_mask]
        w_train = weights[train_mask]

        mod_tr = sm.WLS(y_train, X_train, weights=w_train)
        res_tr = mod_tr.fit(cov_type="cluster", cov_kwds={"groups": df.loc[train_mask, "N"]})

        w1_tr = res_tr.params["ML_b1"]
        w2_tr = res_tr.params["ML_b2"]
        w3_tr = res_tr.params["ML_b3"]
        beta_tr = res_tr.params["exchanges"]

        df_te = df[test_mask].copy()
        base_te = (w1_tr * df_te["ML_b1"] +
                   w2_tr * df_te["ML_b2"] +
                   w3_tr * df_te["ML_b3"] +
                   beta_tr * df_te["exchanges"])

        c1_te = df_te[df_te["cutoff"] == 1]
        c1_base = base_te[df_te["cutoff"] == 1]
        alpha_calib = np.sum((c1_te["T"] - c1_base) * c1_te["ML_b456"]) / np.sum(c1_te["ML_b456"] ** 2)

        df_te["That_loso"] = base_te + alpha_calib * df_te["ML_b456"]
        t1_map = df_te[df_te["cutoff"] == 1].set_index("N")["That_loso"]
        df_te["rhat_loso"] = df_te["That_loso"] / df_te["N"].map(t1_map)

        rhat_s = df_te.groupby("cutoff")["rhat_loso"].apply(lambda col: np.exp(np.mean(np.log(col))))
        r_meas_s = r_meas_curves[holdout_scale]
        rmse_r = np.sqrt(np.mean((rhat_s.loc[2:64] - r_meas_s.loc[2:64]) ** 2))

        loso_rows.append({
            "model": "M2",
            "holdout_scale": holdout_scale,
            "rmse_r": rmse_r,
            "r7_meas": r_meas_s.loc[7],
            "r7_hat": rhat_s.loc[7],
            "r10_meas": r_meas_s.loc[10],
            "r10_hat": rhat_s.loc[10],
            "r30_meas": r_meas_s.loc[30],
            "r30_hat": rhat_s.loc[30],
        })

    df_loso = pd.DataFrame(loso_rows)

    return {
        "df": df,
        "res_m0": res_m0,
        "res_m1": res_m1,
        "res_m2": res_m2,
        "coef_m0": df_coef_m0,
        "coef_m1": df_coef_m1,
        "coef_m2": df_coef_m2,
        "df_loso": df_loso,
        "r_meas_curves": r_meas_curves,
    }


def compute_lstar_table(res_m0) -> pd.DataFrame:
    """Tính L* lý thuyết bằng công thức đóng và tối ưu số từ tham số M0."""
    beta = res_m0.params["exchanges"]
    gamma = res_m0.params["leaves2"]

    alphas = {
        "2^12": res_m0.params["ML_12"],
        "2^16": res_m0.params["ML_16"],
        "2^19": res_m0.params["ML_19"],
        "mean": np.mean([res_m0.params["ML_12"], res_m0.params["ML_16"], res_m0.params["ML_19"]]),
    }

    rows = []
    for scale_lbl, alpha in alphas.items():
        # Phương trình: (beta / 4) * L^2 - (alpha / ln 2) * L - gamma = 0
        A = beta / 4.0
        B = -alpha / np.log(2)
        C = -gamma
        disc = B ** 2 - 4 * A * C

        # Nghiệm cực tiểu dương của f(L)
        L_closed = (-B + np.sqrt(disc)) / (2 * A)

        # Tối ưu số trên [2, 200]
        def g(L):
            return -alpha * np.log2(L) + beta * (L - 1) / 4.0 + gamma / L

        opt = minimize_scalar(g, bounds=(2, 200), method="bounded")
        L_num = opt.x

        rows.append({
            "scale": scale_lbl,
            "alpha": alpha,
            "beta": beta,
            "gamma": gamma,
            "L_star_closed_form": L_closed,
            "L_star_numerical": L_num,
            "diff": abs(L_closed - L_num),
        })
    return pd.DataFrame(rows)


def plot_r_curves(df: pd.DataFrame, out_path: Path):
    """
    Vẽ hình fig_cost_model_r_by_cutoff: r đo kèm CI và r̂ của mô hình chọn (M2)
    cho 3 thang kích thước, c từ 1 đến 64.
    """
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.6), sharey=True)

    # Đọc CI đo từ r_by_cutoff.csv nếu có
    r_by_cutoff_file = Path("results_final/analysis/tables/r_by_cutoff.csv")
    ci_dict = {}
    if r_by_cutoff_file.exists():
        r_df = pd.read_csv(r_by_cutoff_file)
        r_rnd = r_df[r_df["distribution"] == "random"]
        for s in ["2^12", "2^16", "2^19"]:
            sub = r_rnd[r_rnd["scale"] == s].set_index("cutoff")
            ci_dict[s] = sub

    for ax, s in zip(axes, ["2^12", "2^16", "2^19"]):
        sub_df = df[df["scale"] == s]

        # r đo thực nghiệm
        r_meas = sub_df.groupby("cutoff")["r_meas"].apply(lambda col: np.exp(np.mean(np.log(col))))
        # r mô hình M2
        r_m2 = sub_df.groupby("cutoff")["rhat_M2"].apply(lambda col: np.exp(np.mean(np.log(col))))

        cutoffs = r_meas.index.values

        # Vẽ dải tin cậy 95% nếu có
        if s in ci_dict and "ci_lo" in ci_dict[s].columns:
            ci_sub = ci_dict[s].reindex(cutoffs)
            ax.fill_between(cutoffs, ci_sub["ci_lo"], ci_sub["ci_hi"], color=SERIES[0], alpha=0.18, label="95% CI (đo)")

        # Đường đo thực nghiệm
        ax.plot(cutoffs, r_meas.values, "o-", color=SERIES[0], markersize=3.5, linewidth=1.2, label="Đo thực nghiệm $r(c)$")

        # Đường mô hình M2
        ax.plot(cutoffs, r_m2.values, "--", color="#d9381e", linewidth=1.6, label="Mô hình M2 $\\hat{r}(c)$")

        ax.set_title(f"Thang {s}", fontweight="bold", pad=8)
        ax.set_xlabel("Cutoff $c$")
        ax.set_xlim(0, 66)
        ax.set_ylim(0.82, 1.02)
        ax.axhline(1.0, color=NEUTRAL, linestyle=":", linewidth=0.8)

        # Đánh dấu c* = 40 (hoặc best)
        best_c = r_m2.idxmin()
        ax.axvline(best_c, color="#d9381e", linestyle=":", linewidth=0.8, alpha=0.7)

    axes[0].set_ylabel("Tỷ số thời gian $r(c) = T(c) / T(1)$")
    axes[0].legend(loc="upper right", frameon=True, framealpha=0.9, facecolor="white")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    print(f"  Đã lưu hình: {out_path} và .pdf")


def plot_loso_comparison(df_loso: pd.DataFrame, out_path: Path):
    """
    Vẽ hình fig_cost_model_loso: RMSE(r) thẩm định bỏ-một-thang của M0, M1, M2.
    """
    fig, ax = plt.subplots(figsize=(6.5, 3.8))

    scales = ["2^12", "2^16", "2^19"]
    models = ["M0", "M1", "M2"]
    bar_width = 0.24
    x = np.arange(len(scales) + 1)  # 3 thang + Trung bình

    colors = [NEUTRAL, SERIES[1], SERIES[2]]

    for i, m in enumerate(models):
        sub = df_loso[df_loso["model"] == m].set_index("holdout_scale")
        rmses = [sub.loc[s, "rmse_r"] for s in scales]
        avg_rmse = np.mean(rmses)
        vals = rmses + [avg_rmse]
        ax.bar(x + (i - 1) * bar_width, vals, width=bar_width, color=colors[i], label=m)

        for pos, val in zip(x + (i - 1) * bar_width, vals):
            ax.text(pos, val + 0.002, f"{val:.3f}", ha="center", va="bottom", fontsize=7.5, rotation=0)

    ax.set_xticks(x)
    ax.set_xticklabels(["Bỏ 2^12", "Bỏ 2^16", "Bỏ 2^19", "Trung bình"])
    ax.set_ylabel("RMSE của $(r̂ - r)$ trên $c \\in [2, 64]$")
    ax.set_title("Thẩm định ngoại suy bỏ-một-thang (LOSO) trên 3 mô hình", fontweight="bold", pad=10)
    ax.legend(loc="upper right", frameon=True, framealpha=0.9, facecolor="white")
    ax.set_ylim(0, 0.105)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    print(f"  Đã lưu hình: {out_path} và .pdf")


def print_quality_checks(results: dict, df_lstar: pd.DataFrame):
    """In ra các kiểm tra chất lượng theo Quy tắc A (in hai số cạnh nhau)."""
    print("\n" + "=" * 80)
    print("KIỂM TRA CHẤT LƯỢNG VÀ ĐỐI CHIẾU THAM CHIẾU (QUY TẮC CHẤT LƯỢNG A)")
    print("=" * 80)

    # 1. Kiểm tra M0
    res_m0 = results["res_m0"]
    gamma_m0 = res_m0.params["leaves2"]
    gamma_ref = -17.0
    diff_gamma = gamma_m0 - gamma_ref

    df = results["df"]
    r30_12_m0 = df[(df["scale"] == "2^12") & (df["cutoff"] == 30)]["rhat_M0"].mean()
    r30_12_meas = df[(df["scale"] == "2^12") & (df["cutoff"] == 30)]["r_meas"].mean()
    r30_12_ref = 0.755
    r30_meas_ref = 0.852

    print("\n[MÔ HÌNH M0]")
    print(f"  Hệ số gamma (leaves2): tính = {gamma_m0:8.4f} ns | tham chiếu = {gamma_ref:8.4f} ns | chênh = {diff_gamma:+8.4f} ns")
    print(f"  2^12 r̂(30) M0:         tính = {r30_12_m0:8.4f}    | tham chiếu = {r30_12_ref:8.4f}    | chênh = {r30_12_m0 - r30_12_ref:+8.4f}")
    print(f"  2^12 r(30) đo:         tính = {r30_12_meas:8.4f}    | tham chiếu = {r30_meas_ref:8.4f}    | chênh = {r30_12_meas - r30_meas_ref:+8.4f}")

    # 2. Kiểm tra M1
    df_loso = results["df_loso"]
    m1_12 = df_loso[(df_loso["model"] == "M1") & (df_loso["holdout_scale"] == "2^12")].iloc[0]
    rmse_m1_12 = m1_12["rmse_r"]
    r30_m1_12 = m1_12["r30_hat"]
    print("\n[MÔ HÌNH M1]")
    print(f"  Bỏ 2^12 RMSE(r):       tính = {rmse_m1_12:8.4f}    | tham chiếu = {0.0840:8.4f}    | chênh = {rmse_m1_12 - 0.0840:+8.4f}")
    print(f"  Bỏ 2^12 r̂(30):         tính = {r30_m1_12:8.4f}    | tham chiếu = {0.7620:8.4f}    | chênh = {r30_m1_12 - 0.7620:+8.4f}")

    # 3. Kiểm tra M2
    res_m2 = results["res_m2"]
    w1 = res_m2.params["ML_b1"]
    w2 = res_m2.params["ML_b2"]
    w3 = res_m2.params["ML_b3"]
    beta = res_m2.params["exchanges"]
    a12 = res_m2.params["ML_b456_12"]
    a16 = res_m2.params["ML_b456_16"]
    a19 = res_m2.params["ML_b456_19"]

    print("\n[MÔ HÌNH M2 - HỆ SỐ TRONG MẪU]")
    print(f"  w1 (b1 <= 8):          tính = {w1:8.4f} ns | khoảng kỳ vọng = ≈ 6.0 ns      | chênh vs 6 = {w1 - 6.0:+8.4f}")
    print(f"  w2 (b2 9-32):          tính = {w2:8.4f} ns | khoảng kỳ vọng = 10 - 12 ns     | trong khoảng: {10 <= w2 <= 12}")
    print(f"  w3 (b3 33-128):        tính = {w3:8.4f} ns | khoảng kỳ vọng = 15 - 19 ns     | trong khoảng: {15 <= w3 <= 19}")
    print(f"  beta (exchanges):      tính = {beta:8.4f} ns | khoảng kỳ vọng = 3 - 4 ns       | trong khoảng: {3 <= beta <= 4}")
    print(f"  alpha_12 (b456):       tính = {a12:8.4f} ns | khoảng kỳ vọng = 8 - 12 ns      | trong khoảng: {8 <= a12 <= 12}")
    print(f"  alpha_16 (b456):       tính = {a16:8.4f} ns | khoảng kỳ vọng = 8 - 12 ns      | trong khoảng: {8 <= a16 <= 12}")
    print(f"  alpha_19 (b456):       tính = {a19:8.4f} ns | khoảng kỳ vọng = 8 - 12 ns      | trong khoảng: {8 <= a19 <= 12}")

    print("\n[MÔ HÌNH M2 - THẨM ĐỊNH LOSO]")
    m2_loso = df_loso[df_loso["model"] == "M2"].set_index("holdout_scale")
    for s, ref_rmse in [("2^12", 0.009), ("2^16", 0.007), ("2^19", 0.003)]:
        rmse_calc = m2_loso.loc[s, "rmse_r"]
        r7_hat, r7_meas = m2_loso.loc[s, "r7_hat"], m2_loso.loc[s, "r7_meas"]
        r10_hat, r10_meas = m2_loso.loc[s, "r10_hat"], m2_loso.loc[s, "r10_meas"]
        r30_hat, r30_meas = m2_loso.loc[s, "r30_hat"], m2_loso.loc[s, "r30_meas"]

        print(f"  Thang {s}:")
        print(f"    RMSE(r):             tính = {rmse_calc:8.5f} | tham chiếu = {ref_rmse:8.5f} | chênh = {rmse_calc - ref_rmse:+8.5f}")
        print(f"    r(7):  hat={r7_hat:.4f}, meas={r7_meas:.4f}, diff={abs(r7_hat - r7_meas):.4f} (<= 1%: {abs(r7_hat - r7_meas) <= 0.01})")
        print(f"    r(10): hat={r10_hat:.4f}, meas={r10_meas:.4f}, diff={abs(r10_hat - r10_meas):.4f} (<= 1%: {abs(r10_hat - r10_meas) <= 0.01})")
        print(f"    r(30): hat={r30_hat:.4f}, meas={r30_meas:.4f}, diff={abs(r30_hat - r30_meas):.4f} (<= 1%: {abs(r30_hat - r30_meas) <= 0.01})")

    # 4. Kiểm tra L*
    print("\n[KIỂM TRA L* - ĐÓNG vs TỐI ƯU SỐ]")
    for _, r in df_lstar.iterrows():
        print(f"  Thang {r['scale']:<5}: L*_đóng = {r['L_star_closed_form']:8.4f} | L*_số = {r['L_star_numerical']:8.4f} | chênh = {r['diff']:8.4f} (<= 0.1: {r['diff'] <= 0.1})")
    print("=" * 80 + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Khớp và thẩm định các mô hình chi phí thời gian từ số đếm (T03b)."
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
    print("T03b: KHỚP MÔ HÌNH CHI PHÍ THỜI GIAN VÀ THẨM ĐỊNH BỎ-MỘT-THANG")
    print("=" * 80)

    # 1. Nạp dữ liệu
    print("\n[1/5] Đang nạp và hợp nhất dữ liệu...")
    df = load_dataset(args.results, args.tree_features, args.counts)
    print(f"  Tổng số quan sát (N, c) random: {len(df)}")

    # 2. Khớp mô hình M0, M1, M2 và thẩm định LOSO
    print("\n[2/5] Đang khớp mô hình M0, M1, M2 và chạy thẩm định LOSO...")
    results = fit_and_evaluate_models(df)

    # 3. Tính bảng L*
    print("\n[3/5] Đang tính nghiệm L* cho mô hình M0...")
    df_lstar = compute_lstar_table(results["res_m0"])

    # 4. In kiểm tra chất lượng (Quy tắc A)
    print_quality_checks(results, df_lstar)

    # 5. Lưu bảng kết quả
    print("[4/5] Đang lưu các bảng CSV kết quả...")
    args.out_tables.mkdir(parents=True, exist_ok=True)

    results["coef_m0"].to_csv(args.out_tables / "cost_model_M0_coef.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_M0_coef.csv'}")

    results["coef_m1"].to_csv(args.out_tables / "cost_model_M1_coef.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_M1_coef.csv'}")

    results["coef_m2"].to_csv(args.out_tables / "cost_model_M2_coef.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_M2_coef.csv'}")

    # Bảng dự đoán từng điểm (N, c)
    pred_cols = [
        "distribution", "scale", "N", "cutoff",
        "T", "That_M0", "That_M1", "That_M2",
        "r_meas", "rhat_M0", "rhat_M1", "rhat_M2"
    ]
    df_pred = results["df"][pred_cols].rename(columns={"T": "T_meas"})
    df_pred.to_csv(args.out_tables / "cost_model_predictions.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_predictions.csv'}")

    results["df_loso"].to_csv(args.out_tables / "cost_model_loso.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_loso.csv'}")

    df_lstar.to_csv(args.out_tables / "cost_model_Lstar.csv", index=False)
    print(f"  Đã lưu: {args.out_tables / 'cost_model_Lstar.csv'}")

    # 6. Vẽ và lưu hình ảnh
    print("\n[5/5] Đang sinh các đồ thị...")
    args.out_figures.mkdir(parents=True, exist_ok=True)
    plot_r_curves(results["df"], args.out_figures / "fig_cost_model_r_by_cutoff.png")
    plot_loso_comparison(results["df_loso"], args.out_figures / "fig_cost_model_loso.png")

    print("\nHoàn thành T03b xuất sắc!")


if __name__ == "__main__":
    main()
