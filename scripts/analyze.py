#!/usr/bin/env python3
"""
analyze.py - phân tích thí nghiệm CUTOFF cho mergesort.

Cách chạy (từ thư mục cutoff-experiment):
    python scripts/analyze.py --results results            # lượt đầy đủ
    python scripts/analyze.py --results results/pilot      # pilot
Tùy chọn:
    --counts <file>   counts.csv (mặc định: <results>/counts.csv, nếu không có thì <results>/../counts.csv)
    --out <dir>       thư mục đầu ra (mặc định: <results>/analysis)
    --B <int>         số mẫu bootstrap (mặc định 10000)
    --seed <int>      seed bootstrap (mặc định 20261027)
    --label <text>    nhãn lượt chính (mặc định: tên thư mục)
    --compare <dir>...         một hoặc nhiều lượt khác để so sánh (bảng compare_*.csv, fig15, mục 9 trên mọi JVM,
                               mục 11 của summary)
    --compare-label <text>...  nhãn theo đúng thứ tự --compare (mặc định: tên thư mục)
    --state-ref <label>        lượt tham chiếu cho trạng thái nhanh/chậm ở mục 10 (mặc định: lượt chính)
    --state-tol <x>            bộ dữ liệu "cùng mức tham chiếu" nếu T < x × T cùng bộ ở lượt tham chiếu (mặc định 1.25)
    --pilots <dir>... thư mục pilot cho mục 10 (mặc định: <results>/pilot và <compare>/pilot nếu có)
Ví dụ (3 lượt, run 3 là lượt chính):
    python scripts/analyze.py --results results_run3 --label "run 3 (ghim nhân 5)"
           --compare results_run2 results_run1 --compare-label "run 2" "run 1"

Đầu ra: <out>/tables/*.csv, <out>/figures/*.png (dpi 200), <out>/summary.md

Đại lượng chính: r = T(c) / T(1), ghép cặp trong cùng (fork, distribution, N, trial).
Gộp: log r trung bình theo (fork, trial) trong từng N, rồi trung bình đều trên các N của thang
(= trung bình nhân, mỗi N một trọng số). CI 95%: bootstrap theo cụm N (lấy mẫu lại N trong thang).
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm   # noqa: E402

# ----------------------------------------------------------------------------- thiết kế (đã chốt)

FULL_GRID = list(range(1, 33)) + [40, 48, 64]
SPARSE_GRID = [1, 2, 4, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64]
DISTS = ["random", "sorted", "reversed", "nearly_sorted", "few_distinct"]
DIST_VI = {"random": "ngẫu nhiên", "sorted": "đã sắp", "reversed": "đảo ngược",
           "nearly_sorted": "gần sắp (~1%)", "few_distinct": "ít giá trị (10)"}
SCALES = [2 ** 12, 2 ** 16, 2 ** 19]
NEAR_TOL = 0.02                       # "gần tối ưu": r <= 1.02 * r_tốt nhất
# bộ nhớ: working set mỗi phần tử = a (4 B tham chiếu) + aux (4 B) + Integer (16 B: header 12 B + int 4 B,
# căn 8 B) với compressed oops (mặc định khi heap < 32 GB); cache Ryzen 7 H 255: L2 1 MiB/nhân, L3 16 MiB
BYTES_PER_ELEM = 4 + 4 + 16
CACHE_LEVELS = {"L2": 1 * 2 ** 20, "L3": 16 * 2 ** 20}       # L2: mỗi nhân; L3: dùng chung
LECTURE_R = {"giảm 20% thời gian (r = 0.80)": 0.80, "nhanh hơn 1.2 lần (r = 0.833)": 1 / 1.2}


def grid_for(dist):
    return FULL_GRID if dist == "random" else SPARSE_GRID


def design_reps(dist, n, pilot):
    if pilot:
        return 2
    if dist == "random":
        return 10 if scale_of(n) <= 2 ** 16 else 5
    return 5


def scale_of(n):
    return 1 << (int(n).bit_length() - 1)


def slabel(s):
    return f"2^{int(s).bit_length() - 1}"


# ----------------------------------------------------------------------------- màu & kiểu hình (in A4)

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]   # thứ tự cố định, đã kiểm tra CVD
MARKERS = ["o", "s", "^", "D", "v"]
INK, INK2, GRID_C, NEUTRAL = "#0b0b0b", "#52514e", "#e2e1dc", "#8d8c86"
DIVERGING = LinearSegmentedColormap.from_list(
    "blue_gray_red", ["#104281", "#3987e5", "#9ec5f4", "#f0efec", "#f4b0ad", "#e34948", "#9c2222"])

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Segoe UI", "Arial"],
    "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight",
    "font.size": 9.5, "axes.titlesize": 10.5, "axes.labelsize": 10, "xtick.labelsize": 9,
    "ytick.labelsize": 9, "legend.fontsize": 8.5, "legend.frameon": False,
    "axes.edgecolor": NEUTRAL, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID_C,
    "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlecolor": INK, "lines.linewidth": 1.6, "lines.markersize": 4.5,
    "figure.facecolor": "white", "axes.facecolor": "white",
})
FIG_W = 6.6        # inch ~ bề rộng vùng chữ A4


def log2_cutoff_axis(ax, grid):
    ax.set_xscale("log", base=2)
    ticks = [c for c in [1, 2, 4, 8, 16, 32, 64] if c <= max(grid)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(t) for t in ticks])
    ax.minorticks_off()


# ----------------------------------------------------------------------------- nạp dữ liệu

def parse_env(path: Path):
    sessions, cur, in_order = [], None, False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("=== session start"):
            cur = {"kind": "resumed" if "resumed" in line else "fresh", "props": {}, "order": [],
                   "datasets": [], "jvm_warmup": {}, "end": {}}
            sessions.append(cur)
            in_order = False
            continue
        if cur is None:
            continue
        if line.startswith("dataset_order ("):
            in_order = True
            continue
        if in_order:
            m = re.match(r"\s+(\d+) (\S+) (\d+) (\d+)$", line)
            if m:
                cur["order"].append((m[2], int(m[3]), int(m[4])))
                continue
            in_order = False
        if line.startswith("jvm_warmup:"):
            body = line.split(":", 1)[1]
            m = re.search(r"round_totals_ms=\[([^\]]*)\]", body)
            cur["jvm_warmup"] = dict(kv.split("=", 1) for kv in re.sub(r"round_totals_ms=\[[^\]]*\]", "", body).split())
            cur["jvm_warmup"]["round_totals_ms"] = [float(x) for x in m[1].split()] if m else []
        elif line.startswith("dataset "):
            tok = line.split()
            rec = {"distribution": tok[1]}
            for kv in tok[2:]:
                k, v = kv.split("=", 1)
                rec[k] = v.rstrip("s") if k in ("load", "warmup", "measure") else v
            cur["datasets"].append(rec)
        elif line.startswith("end_time="):
            cur["end"] = dict(kv.split("=", 1) for kv in line.split())
        elif line.startswith("FATAL"):
            cur["props"]["FATAL"] = line
        elif "=" in line and not line.startswith(" "):
            k, v = line.split("=", 1)
            cur["props"][k] = v
    return sessions


def load(results: Path, counts_path: Path | None):
    raws = sorted(results.glob("raw_fork*.csv"))
    if not raws:
        sys.exit(f"không tìm thấy raw_fork*.csv trong {results}")
    raw = pd.concat([pd.read_csv(p) for p in raws], ignore_index=True)
    warm_files = sorted(results.glob("warmup_fork*.csv"))
    warm = pd.concat([pd.read_csv(p).assign(_file_order=np.arange(len(pd.read_csv(p)))) for p in warm_files],
                     ignore_index=True) if warm_files else pd.DataFrame()
    env = {}
    for p in sorted(results.glob("env_fork*.txt")):
        env[int(re.search(r"env_fork(\d+)", p.name)[1])] = parse_env(p)
    if counts_path is None:
        for cand in (results / "counts.csv", results.parent / "counts.csv"):
            if cand.exists():
                counts_path = cand
                break
    counts = pd.read_csv(counts_path) if counts_path and Path(counts_path).exists() else pd.DataFrame()
    raw["gc_during_run"] = raw["gc_during_run"].astype(str).str.lower().eq("true")
    raw["scale"] = raw["N"].map(scale_of)
    raw["logt"] = np.log(raw["time_ns"].astype(float))
    return raw, warm, env, counts, counts_path


# ----------------------------------------------------------------------------- bootstrap & tiện ích

def cluster_boot_means(M: np.ndarray, B: int, rng, chunk=1000):
    """M: (nN x k) giá trị theo N. Trả về (B x k) trung bình của các mẫu lấy lại N."""
    nN = M.shape[0]
    out = np.empty((B, M.shape[1]))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for s in range(0, B, chunk):
            b = min(chunk, B - s)
            idx = rng.integers(0, nN, size=(b, nN))
            out[s:s + b] = np.nanmean(M[idx], axis=1)
    return out


def holm(pvals):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adj[i] = running
    return adj


def fmt_pct(x, d=1):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{d}f}%"


def fmt_r(x, d=3):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{d}f}"


@lru_cache(maxsize=None)
def mean_leaf_length(n, c):
    @lru_cache(maxsize=None)
    def leaves(m):
        return 1 if m <= c else leaves((m + 1) // 2) + leaves(m // 2)
    return n / leaves(n)


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.values) + " |")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- phân tích lõi

class Core:
    """r = T(c)/T(1) và các tổng hợp, cho một tập dòng raw (đã lọc hoặc chưa lọc GC)."""

    def __init__(self, df: pd.DataFrame, B: int, seed: int):
        self.df = df
        key = ["fork", "distribution", "N", "trial"]
        base = df[df.cutoff == 1][key + ["logt"]].rename(columns={"logt": "logt1"})
        groups = df[key].drop_duplicates()
        self.trials_without_baseline = len(groups) - len(base.drop_duplicates(key))
        obs = df.merge(base, on=key, how="inner")
        obs["lr"] = obs["logt"] - obs["logt1"]
        obs["tnorm"] = obs["time_ns"] / (obs["N"] * np.log2(obs["N"]))
        self.obs = obs
        self.perN = (obs.groupby(["distribution", "scale", "N", "cutoff"])
                        .agg(mlr=("lr", "mean"), n=("lr", "size"), mlogtn=("tnorm", lambda s: np.log(s).mean()))
                        .reset_index())
        self.rng = np.random.default_rng(seed)
        self.B = B
        self.boot = {}
        rows = []
        for (d, s), g in self.perN.groupby(["distribution", "scale"]):
            M = g.pivot(index="N", columns="cutoff", values="mlr")
            cut = list(M.columns)
            Mv = M.to_numpy()
            bt = cluster_boot_means(Mv, B, self.rng)
            self.boot[(d, s)] = (cut, bt, list(M.index))
            point = np.nanmean(Mv, axis=0)
            lo, hi = np.nanpercentile(bt, [2.5, 97.5], axis=0)
            tn = g.pivot(index="N", columns="cutoff", values="mlogtn").to_numpy()
            obs_g = obs[(obs.distribution == d) & (obs.scale == s)]
            med_obs = obs_g.groupby("cutoff")["lr"].median()
            for j, c in enumerate(cut):
                rows.append({"distribution": d, "scale": s, "cutoff": c,
                             "r_gm": math.exp(point[j]), "ci_lo": math.exp(lo[j]), "ci_hi": math.exp(hi[j]),
                             "r_median_obs": math.exp(med_obs.get(c, np.nan)),
                             "r_median_perN": math.exp(np.nanmedian(Mv[:, j])),
                             "T_per_NlgN_ns": math.exp(np.nanmean(tn[:, j])),
                             "n_N": int(np.sum(~np.isnan(Mv[:, j]))),
                             "n_obs": int(g[g.cutoff == c]["n"].sum())})
        self.agg = pd.DataFrame(rows)

    def best(self, d, s):
        a = self.agg[(self.agg.distribution == d) & (self.agg.scale == s)]
        return int(a.loc[a.r_gm.idxmin(), "cutoff"])

    def argmin_freq(self, d, s):
        cut, bt, _ = self.boot[(d, s)]
        am = np.nanargmin(np.where(np.isnan(bt), np.inf, bt), axis=1)
        cnt = np.bincount(am, minlength=len(cut)) / len(am)
        return pd.Series(cnt, index=cut)


def point_by_cutoff(obs_sub: pd.DataFrame):
    pn = obs_sub.groupby(["N", "cutoff"])["lr"].mean().unstack("cutoff")
    return np.exp(pn.mean(axis=0)), pn


def paired_test(df: pd.DataFrame, a: int, b: int, rng, B: int):
    """log(T_a/T_b) ghép cặp theo (fork, trial, N), trung bình trong từng N trước, rồi Wilcoxon + bootstrap."""
    sub = df[df.cutoff.isin([a, b])]
    piv = sub.pivot_table(index=["fork", "trial", "N"], columns="cutoff", values="logt")
    if a not in piv or b not in piv:
        return None
    dlt = (piv[a] - piv[b]).dropna()
    dN = dlt.groupby(level="N").mean().to_numpy()
    if len(dN) == 0:
        return None
    bt = cluster_boot_means(dN.reshape(-1, 1), B, rng)[:, 0]
    lo, hi = np.percentile(bt, [2.5, 97.5])
    try:
        p = stats.wilcoxon(dN).pvalue if np.any(dN != 0) else 1.0
    except ValueError:
        p = float("nan")
    return {"n_N": len(dN), "ratio": math.exp(dN.mean()), "ci_lo": math.exp(lo), "ci_hi": math.exp(hi),
            "median_ratio": math.exp(np.median(dN)), "n_N_a_faster": int(np.sum(dN < 0)), "p_wilcoxon": p}


# ----------------------------------------------------------------------------- hình

def save(fig, figdir: Path, name: str, saved: list):
    p = figdir / f"{name}.png"
    fig.savefig(p)
    plt.close(fig)
    saved.append(p.name)


def fig_r_vs_cutoff(core: Core, figdir, saved):
    fig, ax = plt.subplots(figsize=(FIG_W, 3.6))
    for i, s in enumerate(SCALES):
        a = core.agg[(core.agg.distribution == "random") & (core.agg.scale == s)].sort_values("cutoff")
        if a.empty:
            continue
        ax.fill_between(a.cutoff, a.ci_lo, a.ci_hi, color=SERIES[i], alpha=0.15, linewidth=0)
        ax.plot(a.cutoff, a.r_gm, color=SERIES[i], marker=MARKERS[i], markersize=3.5,
                label=f"thang {slabel(s)} ({a.n_N.max()} N)")
        b = a.loc[a.r_gm.idxmin()]
        ax.plot([b.cutoff], [b.r_gm], marker=MARKERS[i], markersize=8, color=SERIES[i],
                markeredgecolor="white", markeredgewidth=1.2, linestyle="none", zorder=5)
    for (lab, v), ls, va in zip(LECTURE_R.items(), ["--", ":"], ["top", "bottom"]):
        ax.axhline(v, color=NEUTRAL, linestyle=ls, linewidth=1)
        ax.text(1.02, v, " bài giảng: " + lab, color=INK2, fontsize=7.5, va=va, ha="left")
    ax.axhline(1, color=INK2, linewidth=0.8)
    log2_cutoff_axis(ax, FULL_GRID)
    ax.set_xlabel("CUTOFF c (thang log₂)")
    ax.set_ylabel("r = T(c) / T(1)")
    ax.set_title("Tỉ số thời gian theo CUTOFF, dữ liệu ngẫu nhiên (TB nhân trên các N, CI 95%)")
    ax.legend(loc="upper center", ncol=3)
    save(fig, figdir, "fig01_r_vs_cutoff_random", saved)


def fig_argmin(core: Core, figdir, saved):
    fig, axes = plt.subplots(1, 3, figsize=(FIG_W, 2.6), sharey=True)
    for i, (ax, s) in enumerate(zip(axes, SCALES)):
        if ("random", s) not in core.boot:
            ax.set_visible(False)
            continue
        f = core.argmin_freq("random", s)
        f = f[f > 0]
        ax.bar([str(c) for c in f.index], f.values, color=SERIES[i], width=0.7)
        ax.set_title(f"thang {slabel(s)}")
        ax.set_xlabel("CUTOFF tốt nhất")
        ax.grid(axis="x", visible=False)
        ax.tick_params(axis="x", labelrotation=90 if len(f) > 6 else 0)
    axes[0].set_ylabel("tần suất (bootstrap)")
    fig.suptitle("Phân bố bootstrap của CUTOFF tốt nhất (random)", y=1.07, fontsize=10.5)
    save(fig, figdir, "fig02_argmin_bootstrap", saved)


def fig_speedup(sp: pd.DataFrame, figdir, saved):
    if sp.empty:
        return
    fig, ax = plt.subplots(figsize=(FIG_W, 2.9))
    labels = sp["label"].unique().tolist()
    xs = {s: k for k, s in enumerate([s for s in SCALES if s in set(sp.scale)])}
    width = 0.22
    for i, lab in enumerate(labels):
        g = sp[sp.label == lab]
        x = np.array([xs[s] for s in g.scale]) + (i - (len(labels) - 1) / 2) * width
        y = 1 - g.r_gm.to_numpy()
        lo, hi = 1 - g.ci_hi.to_numpy(), 1 - g.ci_lo.to_numpy()
        ax.errorbar(x, y * 100, yerr=[(y - lo) * 100, (hi - y) * 100], fmt=MARKERS[i], color=SERIES[i],
                    capsize=3, label=lab, markersize=6)
    ax.axhline(20, color=NEUTRAL, linestyle="--", linewidth=1)
    ax.text(len(xs) - 0.5, 20, "20% (bài giảng)", color=INK2, fontsize=7.5, va="bottom", ha="right")
    ax.set_xticks(list(xs.values()))
    ax.set_xticklabels([f"thang {slabel(s)}" for s in xs])
    ax.set_ylabel("thời gian giảm so với c = 1 (%)")
    ax.set_title("Mức giảm thời gian tại CUTOFF 7, 10 và tốt nhất (CI 95%)")
    ax.legend(ncol=3, loc="lower center")
    save(fig, figdir, "fig03_speedup_7_10_best", saved)


def fig_paired(dfm: pd.DataFrame, best_by_scale: dict, figdir, saved):
    comps = [(7, 10, "7 so với 10"), ("best", 7, "tốt nhất so với 7"), ("best", 10, "tốt nhất so với 10")]
    fig, axes = plt.subplots(1, 3, figsize=(FIG_W, 2.8), sharey=True)
    for ax, (a, b, lab) in zip(axes, comps):
        for i, s in enumerate(SCALES):
            sub = dfm[(dfm.distribution == "random") & (dfm.scale == s)]
            if sub.empty:
                continue
            aa = best_by_scale[s] if a == "best" else a
            piv = sub[sub.cutoff.isin([aa, b])].pivot_table(index=["fork", "trial", "N"], columns="cutoff",
                                                           values="logt")
            if aa == b or aa not in piv or b not in piv:
                continue
            dN = (piv[aa] - piv[b]).groupby(level="N").mean()
            jitter = np.random.default_rng(i).uniform(-0.12, 0.12, len(dN))
            ax.plot(i + jitter, (np.exp(dN) - 1) * 100, linestyle="none", marker=MARKERS[i], color=SERIES[i],
                    alpha=0.75, markersize=4)
            ax.plot([i - 0.25, i + 0.25], [(math.exp(dN.mean()) - 1) * 100] * 2, color=INK, linewidth=1.6)
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.set_xticks(range(3))
        ax.set_xticklabels([slabel(s) for s in SCALES])
        ax.set_title(lab, fontsize=9.5)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("T_a / T_b − 1 (%) theo từng N")
    fig.suptitle("So sánh ghép cặp (mỗi điểm = một N; vạch = trung bình nhân)", y=1.07, fontsize=10.5)
    save(fig, figdir, "fig04_paired_differences", saved)


def fig_equivalence(core: Core, counts: pd.DataFrame, figdir, saved, eq_rows: list):
    fig, axes = plt.subplots(1, 3, figsize=(FIG_W, 2.9), sharey=True)
    for i, (ax, s) in enumerate(zip(axes, SCALES)):
        pn = core.perN[(core.perN.distribution == "random") & (core.perN.N == s)].sort_values("cutoff")
        mean_line = core.agg[(core.agg.distribution == "random") & (core.agg.scale == s)].sort_values("cutoff")
        if pn.empty:
            ax.set_visible(False)
            continue
        cs = counts[(counts.distribution == "random") & (counts.N == s)].set_index("cutoff")["merged_len"] \
            if not counts.empty else pd.Series(dtype=float)
        # các lớp: cutoff liên tiếp có cùng S (merged_len) cho cùng cây đệ quy
        cl, prev, cid = [], None, -1
        for c in pn.cutoff:
            sv = cs.get(c, np.nan)
            if prev is None or sv != prev:
                cid += 1
            cl.append(cid)
            prev = sv
        pn = pn.assign(cls=cl, r=np.exp(pn.mlr))
        for k, g in pn.groupby("cls"):
            lo, hi = g.cutoff.min(), g.cutoff.max()
            if k % 2 == 0:
                ax.axvspan(lo / 1.06, hi * 1.06, color="#f0efec", linewidth=0, zorder=0)
            eq_rows.append({"scale": s, "N": s, "class": k, "cutoff_from": int(lo), "cutoff_to": int(hi),
                            "leaf_length": mean_leaf_length(s, int(lo)), "merged_len_S": cs.get(lo, np.nan),
                            "r_min": g.r.min(), "r_max": g.r.max(), "spread": g.r.max() / g.r.min() - 1,
                            "sd_log_r": float(np.std(g.mlr, ddof=1)) if len(g) > 1 else np.nan,
                            "n_cutoffs": len(g)})
        ax.plot(pn.cutoff, pn.r, linestyle="none", marker=MARKERS[i], color=SERIES[i], markersize=3.5,
                label=f"N = {slabel(s)}: r từng CUTOFF")
        for k, g in pn.groupby("cls"):
            ax.plot([g.cutoff.min() / 1.04, g.cutoff.max() * 1.04], [math.exp(g.mlr.mean())] * 2, color=INK,
                    linewidth=1.8, solid_capstyle="butt", label="TB nhân trong lớp" if k == 0 else None)
        ax.plot(mean_line.cutoff, mean_line.r_gm, color=INK2, linewidth=1.1, linestyle="--", label="TB trên các N")
        log2_cutoff_axis(ax, FULL_GRID)
        ax.set_title(f"N = {slabel(s)} = {s}", fontsize=9.5)
        ax.set_xlabel("CUTOFF c")
    axes[0].set_ylabel("r = T(c)/T(1)")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, [x.split(":")[1].strip() if ":" in x else x for x in l], loc="lower center", ncol=3,
               bbox_to_anchor=(0.5, -0.16), fontsize=8)
    fig.suptitle("Lớp tương đương ở N = 2^k: mỗi dải (xám/trắng) = các CUTOFF cho cùng cây đệ quy (cùng S)",
                 y=1.07, fontsize=10.5)
    save(fig, figdir, "fig05_equivalence_classes", saved)


def fig_leaf(core: Core, figdir, saved, leaf_rows: list):
    pn = core.perN[core.perN.distribution == "random"].copy()
    pn["leaf"] = [mean_leaf_length(int(n), int(c)) for n, c in zip(pn.N, pn.cutoff)]
    pn["r"] = np.exp(pn.mlr)
    fig, ax = plt.subplots(figsize=(FIG_W, 3.3))
    for i, s in enumerate(SCALES):
        g = pn[pn.scale == s]
        if g.empty:
            continue
        ax.plot(g.leaf, g.r, linestyle="none", marker=MARKERS[i], color=SERIES[i], alpha=0.45, markersize=3,
                label=f"thang {slabel(s)}")
    bins = 2.0 ** np.arange(0, 6.75, 0.25)
    pn["bin"] = pd.cut(pn.leaf, bins, include_lowest=True)
    b = pn.groupby("bin", observed=True).agg(leaf=("leaf", lambda x: math.exp(np.log(x).mean())),
                                             r=("mlr", lambda x: math.exp(x.mean())), n=("mlr", "size"))
    ax.plot(b.leaf, b.r, color=INK, linewidth=1.6, label="TB nhân theo khoảng")
    leaf_rows.extend(b.reset_index().assign(bin=lambda x: x["bin"].astype(str)).to_dict("records"))
    ax.axhline(1, color=INK2, linewidth=0.8)
    ax.set_xscale("log", base=2)
    ax.set_xticks([1, 2, 4, 8, 16, 32, 64])
    ax.set_xticklabels(["1", "2", "4", "8", "16", "32", "64"])
    ax.minorticks_off()
    ax.set_xlabel("độ dài lá trung bình của cây đệ quy (N / số lá)")
    ax.set_ylabel("r = T(c)/T(1)")
    ax.set_title("r theo độ dài lá thực tế (random, mỗi điểm = một cặp (N, c))")
    ax.legend(ncol=4, loc="upper center")
    save(fig, figdir, "fig06_r_vs_leaf_length", saved)


def fig_heatmap(core: Core, figdir, saved):
    pn = core.perN[core.perN.distribution == "random"]
    if pn.empty:
        return
    M = pn.pivot(index="N", columns="cutoff", values="mlr").reindex(columns=FULL_GRID)
    L2 = M.to_numpy() / math.log(2)
    vmax = np.nanmax(np.abs(L2))
    fig, ax = plt.subplots(figsize=(FIG_W, max(2.8, 0.06 * len(M) + 1.6)))
    im = ax.imshow(L2, aspect="auto", cmap=DIVERGING, interpolation="nearest",
                   norm=TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax))
    am = np.nanargmin(np.where(np.isnan(L2), np.inf, L2), axis=1)
    ax.plot(am, np.arange(len(M)), linestyle="none", marker="o", markersize=2.2, color=INK)
    ns = M.index.to_numpy()
    sc = np.array([scale_of(n) for n in ns])
    for k in range(1, len(ns)):
        if sc[k] != sc[k - 1]:
            ax.axhline(k - 0.5, color="white", linewidth=2)
    yt = [k for k in range(len(ns)) if k == 0 or sc[k] != sc[k - 1]]
    ax.set_yticks(yt)
    ax.set_yticklabels([str(ns[k]) for k in yt])
    xt = [FULL_GRID.index(c) for c in [1, 4, 8, 12, 16, 20, 24, 28, 32, 64]]
    ax.set_xticks(xt)
    ax.set_xticklabels([str(FULL_GRID[k]) for k in xt])
    ax.grid(False)
    ax.set_xlabel("CUTOFF c (trục phân loại; giữa 32 và 64 là 40, 48)")
    ax.set_ylabel("N (tăng dần; vạch trắng tách thang)")
    ax.set_title("r = T(c)/T(1) theo N × CUTOFF (random); chấm đen = CUTOFF tốt nhất của từng N")
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    ticks = [t for t in [-0.5, -0.4, -0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.4, 0.6, 0.8] if abs(t) <= vmax]
    cb.set_ticks(ticks)
    cb.set_ticklabels([f"{2 ** t:.2f}" for t in ticks])
    cb.set_label("r (thang log)")
    cb.outline.set_visible(False)
    save(fig, figdir, "fig07_heatmap_random", saved)


def fig_distributions(core: Core, figdir, saved):
    s = 2 ** 16
    fig, ax = plt.subplots(figsize=(FIG_W, 3.4))
    any_ = False
    for i, d in enumerate(DISTS):
        a = core.agg[(core.agg.distribution == d) & (core.agg.scale == s)].sort_values("cutoff")
        if a.empty:
            continue
        any_ = True
        b = a.loc[a.r_gm.idxmin()]
        ax.plot(a.cutoff, a.r_gm, color=SERIES[i], marker=MARKERS[i], markersize=3.5,
                label=f"{DIST_VI[d]}: tốt nhất c = {int(b.cutoff)}")
        ax.plot([b.cutoff], [b.r_gm], marker=MARKERS[i], markersize=8.5, color=SERIES[i],
                markeredgecolor="white", markeredgewidth=1.2, linestyle="none", zorder=5)
    if not any_:
        plt.close(fig)
        return
    ax.axhline(1, color=INK2, linewidth=0.8)
    log2_cutoff_axis(ax, FULL_GRID)
    ax.set_xlabel("CUTOFF c (thang log₂)")
    ax.set_ylabel("r = T(c)/T(1)")
    ax.set_title("r theo CUTOFF cho 5 phân bố, thang 2^16 (marker lớn = tốt nhất)")
    ax.legend(loc="best", ncol=1)
    save(fig, figdir, "fig08_distributions_2e16", saved)


def fig_counts(cn: pd.DataFrame, core: Core, figdir, saved):
    if cn.empty:
        return
    fig, axes = plt.subplots(2, 3, figsize=(FIG_W, 4.6), sharex=True)
    for j, s in enumerate(SCALES):
        g = cn[cn.scale == s].sort_values("cutoff")
        t = core.agg[(core.agg.distribution == "random") & (core.agg.scale == s)].sort_values("cutoff")
        ax = axes[0, j]
        if g.empty:
            ax.set_visible(False)
            axes[1, j].set_visible(False)
            continue
        for k, (col, lab) in enumerate([("C_ratio", "so sánh C"), ("A_ratio", "truy cập A"),
                                        ("S_ratio", "S (tổng merge)")]):
            ax.plot(g.cutoff, g[col], color=SERIES[k], marker=MARKERS[k], markersize=2.5, label=lab)
        ax.plot(t.cutoff, t.r_gm, color=SERIES[3], marker=MARKERS[3], markersize=2.5, label="thời gian T")
        ax.axhline(1, color=INK2, linewidth=0.8)
        ax.set_title(f"thang {slabel(s)}", fontsize=9.5)
        ax2 = axes[1, j]
        for k, (col, lab) in enumerate([("C_nlgn", "C/(N lgN)"), ("A_nlgn", "A/(N lgN)"), ("E_nlgn", "E/(N lgN)")]):
            ax2.plot(g.cutoff, g[col], color=SERIES[k], marker=MARKERS[k], markersize=2.5, label=lab)
        log2_cutoff_axis(ax2, FULL_GRID)
        ax2.set_xlabel("CUTOFF c")
    axes[0, 0].set_ylabel("tỉ số so với c = 1")
    axes[1, 0].set_ylabel("số đếm / (N lgN)")
    axes[0, 0].legend(fontsize=7, loc="upper left")
    axes[1, 0].legend(fontsize=7, loc="center left")
    fig.suptitle("Số đếm (MergeCutoffCounted) và thời gian theo CUTOFF, random", y=1.01, fontsize=10.5)
    save(fig, figdir, "fig09_counts_vs_time", saved)


def fig_model(tn: pd.DataFrame, fits: dict, val: dict, best_c: int, figdir, saved):
    if tn.empty:
        return
    fig, ax = plt.subplots(figsize=(FIG_W, 3.4))
    for i, c in enumerate([1, best_c]):
        g = tn[tn.cutoff == c]
        ax.plot(g.N, g.T_ms, linestyle="none", marker=MARKERS[i], color=SERIES[i], markersize=4,
                label=f"c = {c}: đo")
        f = fits.get(c)
        if f:
            xs = np.geomspace(g.N.min(), g.N.max(), 50)
            ax.plot(xs, f["a_ns"] * xs ** f["b"] / 1e6, color=SERIES[i], linewidth=1.2,
                    label=f"c = {c}: T ≈ {f['a_ns']:.3g}·N^{f['b']:.3f} ns (R² = {f['r2']:.4f})")
        v = val.get(c)
        if v:
            xs = np.geomspace(2 ** 19, g.N.max(), 20)
            ax.plot(xs, v["a_ns"] * xs ** v["b"] / 1e6, color=SERIES[i], linestyle=":", linewidth=1.6)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("N (thang log₂)")
    ax.set_ylabel("T (ms, thang log)")
    ax.set_title("Mô hình T = a·N^b (random); chấm chấm = dự đoán thang 2^19 từ 2^12 và 2^16")
    ax.legend(fontsize=7.5, loc="upper left")
    save(fig, figdir, "fig10_runtime_model", saved)


def fig_warmup(jw: pd.DataFrame, figdir, saved):
    if jw.empty:
        return
    fig, ax = plt.subplots(figsize=(FIG_W, 2.8))
    for i, ((f, sess), g) in enumerate(jw.groupby(["fork", "session"])):
        ax.plot(g["round"], g.total_ms, color=SERIES[(f - 1) % 3], marker=MARKERS[(f - 1) % 3],
                linestyle="-" if sess == 0 else "--", label=f"fork {f}" + ("" if sess == 0 else f", phiên {sess + 1}"))
    ax.set_xlabel("vòng warm-up JVM")
    ax.set_ylabel("tổng thời gian một vòng (ms)")
    ax.set_title("Warm-up JVM: N = 2^16, 35 CUTOFF mỗi vòng")
    ax.legend(ncol=3)
    save(fig, figdir, "fig11_jvm_warmup", saved)


def fig_drift(dq: pd.DataFrame, figdir, saved):
    if dq.empty:
        return
    forks = sorted(dq.fork.unique())
    fig, axes = plt.subplots(len(forks), 1, figsize=(FIG_W, 1.9 * len(forks) + 0.6), sharex=True, squeeze=False)
    for ax, f in zip(axes[:, 0], forks):
        g = dq[dq.fork == f].sort_values("run_order")
        ax.plot(g.run_order, (np.exp(g.lq) - 1) * 100, linestyle="none", marker=".", markersize=1.5,
                color=SERIES[(f - 1) % 3], alpha=0.35)
        w = max(25, len(g) // 40)
        ax.plot(g.run_order, (np.exp(g.lq.rolling(w, center=True, min_periods=w // 2).median()) - 1) * 100,
                color=INK, linewidth=1.4)
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.set_ylabel(f"fork {f}: lệch (%)")
        lim = np.nanpercentile(np.abs((np.exp(g.lq) - 1) * 100), 99)
        ax.set_ylim(-lim * 1.1, lim * 1.1)
    axes[-1, 0].set_xlabel("run_order (thứ tự đo trong fork)")
    fig.suptitle("Trôi theo thời gian: T so với TB nhân của cùng (phân bố, N, c); đường đen = trung vị trượt",
                 y=1.01, fontsize=10)
    save(fig, figdir, "fig12_drift", saved)


def fig_forks(fk: pd.DataFrame, figdir, saved):
    if fk.empty or fk.fork.nunique() < 1:
        return
    fig, axes = plt.subplots(1, 3, figsize=(FIG_W, 2.7), sharey=True)
    for ax, s in zip(axes, SCALES):
        g = fk[fk.scale == s]
        for i, lab in enumerate(g.label.unique()):
            h = g[g.label == lab]
            x = h.fork + (i - 1) * 0.18
            y = (1 - h.r_gm) * 100
            ax.errorbar(x, y, yerr=[y - (1 - h.ci_hi) * 100, (1 - h.ci_lo) * 100 - y], fmt=MARKERS[i],
                        color=SERIES[i], capsize=2.5, markersize=5, label=lab)
        ax.set_title(f"thang {slabel(s)}", fontsize=9.5)
        ax.set_xticks(sorted(fk.fork.unique()))
        ax.set_xlabel("fork")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("thời gian giảm (%)")
    axes[0].legend(fontsize=7, loc="lower left")
    fig.suptitle("Mức giảm thời gian theo từng fork (CI 95% bootstrap theo N)", y=1.07, fontsize=10.5)
    save(fig, figdir, "fig13_forks", saved)


def fig_cache(df: pd.DataFrame, cutoffs, B: int, rng, figdir, saved):
    """T/(N lgN) theo N (random), CI bootstrap theo các lần đo (fork, trial) của từng N."""
    d = df[(df.distribution == "random") & df.cutoff.isin(cutoffs)].copy()
    d["ltn"] = np.log(d.time_ns / (d.N * np.log2(d.N)))
    rows = []
    for (n, c), g in d.groupby(["N", "cutoff"]):
        v = g.ltn.to_numpy()
        bt = v[rng.integers(0, len(v), size=(B, len(v)))].mean(axis=1)
        lo, hi = np.percentile(bt, [2.5, 97.5])
        rows.append({"N": n, "cutoff": c, "scale": slabel(scale_of(n)), "n_obs": len(v),
                     "T_per_NlgN_ns": math.exp(v.mean()), "ci_lo": math.exp(lo), "ci_hi": math.exp(hi),
                     "working_set_MiB": n * BYTES_PER_ELEM / 2 ** 20})
    tab = pd.DataFrame(rows)
    if tab.empty:
        return tab
    fig, ax = plt.subplots(figsize=(FIG_W, 3.4))
    for i, c in enumerate(cutoffs):
        g = tab[tab.cutoff == c].sort_values("N")
        ax.errorbar(g.N, g.T_per_NlgN_ns, yerr=[g.T_per_NlgN_ns - g.ci_lo, g.ci_hi - g.T_per_NlgN_ns],
                    fmt=MARKERS[i], color=SERIES[i], markersize=4, capsize=2, elinewidth=1,
                    label=f"c = {c}" + (" (baseline)" if c == 1 else " (tốt nhất gộp)"))
    ymin, ymax = ax.get_ylim()
    top = ymax + 0.25 * (ymax - ymin)                      # dải trống phía trên dữ liệu để đặt nhãn
    ax.set_ylim(ymin, top)
    for (lab, size), ls, ha in zip(CACHE_LEVELS.items(), ["--", ":"], ["left", "right"]):
        n_star = size / BYTES_PER_ELEM
        ax.axvline(n_star, color=NEUTRAL, linestyle=ls, linewidth=1.2)
        x = n_star * (1.05 if ha == "left" else 1 / 1.05)
        ax.text(x, top - 0.02 * (top - ymin), f"{lab} {size // 2 ** 20} MB\nN ≈ {n_star:.0f}",
                color=INK2, fontsize=7.5, va="top", ha=ha)
    ax.set_xscale("log", base=2)
    ax.set_xlabel("N (thang log₂)")
    ax.set_ylabel("T / (N lgN) (ns)")
    ax.set_title("Chi phí mỗi phần tử mỗi tầng theo N (random); vạch dọc: working set 24N byte = dung lượng cache")
    ax.legend(loc="upper left", ncol=1)
    save(fig, figdir, "fig14_cache_levels", saved)
    return tab


# ----------------------------------------------------------------------------- bổ sung: nhiều JVM, so sánh run, JIT

L1D_BYTES = 32 * 2 ** 10          # L1D mỗi nhân (Zen 4: 512 KB L1 = 8 × (32 KB lệnh + 32 KB dữ liệu)) — chỉ dùng trong văn bản
STATE_TOL = 1.25                  # bộ dữ liệu "cùng mức tham chiếu" nếu T < 1.25 × T cùng bộ ở lượt tham chiếu.
                                  # Hai mức đã đo (E6): xung 128.1% vs 79.3% → tỉ lệ 1.62; trung điểm trên log = 1.27.
                                  # Không dùng ngưỡng tuyệt đối T/(N lgN): trong MỘT JVM ở MỘT trạng thái, T/(N lgN) theo
                                  # bộ dữ liệu đã chênh 3.3–3.7× (phân bố, N) > 1.62×, nên phải so cùng bộ dữ liệu.
JUMP_TOL = 0.10                   # bước nhảy warm-up: vòng tổng > 1.10 × trung vị các vòng trước (bỏ vòng 1)
                                  # VÀ trung vị từ vòng đó tới hết cũng > 1.10 × (bỏ điểm lẻ một vòng)
FAST_NS_PER_NLGN = 9.35           # WarmupProbe E0_2 (N = 65536, 900/900 vòng ở mức nhanh) → 343 ms mỗi vòng 35 lần sắp


def best_table(core: Core):
    """RQ1 cho một Core: c tốt nhất, tập gần tối ưu, tần suất argmin bootstrap."""
    rows, freq_rows = [], []
    for (d, s) in sorted(core.boot, key=lambda k: (DISTS.index(k[0]), k[1])):
        a = core.agg[(core.agg.distribution == d) & (core.agg.scale == s)].set_index("cutoff")
        b = int(a.r_gm.idxmin())
        near = [int(c) for c in a.index if a.r_gm[c] <= a.r_gm[b] * (1 + NEAR_TOL)]
        fr = core.argmin_freq(d, s)
        for c, v in fr.items():
            freq_rows.append({"distribution": d, "scale": slabel(s), "cutoff": c, "freq_best": v})
        top = fr.sort_values(ascending=False)
        rows.append({"distribution": d, "scale": slabel(s), "n_N": int(a.n_N.max()), "best_cutoff": b,
                     "best_by_median": int(a.r_median_obs.idxmin()),
                     "r_best": a.r_gm[b], "ci_lo": a.ci_lo[b], "ci_hi": a.ci_hi[b],
                     "near_optimal_2pct": " ".join(map(str, near)),
                     "near_range": f"{min(near)}–{max(near)}",
                     "boot_freq_best": fr.get(b, 0.0),
                     "boot_top3": "; ".join(f"{c}: {v:.0%}" for c, v in top.head(3).items()),
                     "boot_freq_in_near_set": float(fr[[c for c in near if c in fr.index]].sum())})
    return pd.DataFrame(rows), freq_rows


def pooled_best(core: Core):
    keys = [("random", s) for s in SCALES if ("random", s) in core.boot]
    if not keys:
        return None
    cuts = core.boot[keys[0]][0]
    if not all(core.boot[k][0] == cuts for k in keys):
        return None
    pt = np.mean([np.log(core.agg[(core.agg.distribution == "random") & (core.agg.scale == k[1])]
                         .set_index("cutoff").r_gm.reindex(cuts)) for k in keys], axis=0)
    return int(cuts[int(np.argmin(pt))])


def per_n_log_r(df: pd.DataFrame) -> pd.Series:
    """log r trung bình theo (fork, trial) trong từng (distribution, N, cutoff); không bootstrap."""
    key = ["fork", "distribution", "N", "trial"]
    base = df[df.cutoff == 1][key + ["time_ns"]].rename(columns={"time_ns": "t1"})
    o = df.merge(base, on=key)
    o["lr"] = np.log(o.time_ns / o.t1)
    return o.groupby(["distribution", "N", "cutoff"]).lr.mean()


def ram_free(env: dict, fork):
    s = env.get(fork, [])
    v = s[0]["props"].get("physical_memory_free_at_start") if s else None
    return float(v) / 1e9 if v not in (None, "None") else float("nan")       # GB thập phân


def make_units(run_label: str, raw_main: pd.DataFrame, env: dict):
    units = []
    for f in sorted(raw_main.fork.unique()):
        units.append({"jvm": f"{run_label} f{f}", "run": run_label, "fork": int(f),
                      "df": raw_main[raw_main.fork == f], "env": env.get(f, []), "ram_gb": ram_free(env, f)})
    return units


def per_jvm_table(units, cb: int):
    """r tại c = 7, 10, cb và T7/T10 cho TỪNG JVM (TB nhân trên các N của thang)."""
    rows = []
    for u in units:
        lr_ = per_n_log_r(u["df"][u["df"].distribution == "random"]).reset_index()
        lr_["scale"] = lr_.N.map(scale_of)
        for s, g in lr_.groupby("scale"):
            pn = g.pivot(index="N", columns="cutoff", values="lr")
            rec = {"jvm": u["jvm"], "run": u["run"], "fork": u["fork"], "scale": s, "ram_free_gb": u["ram_gb"],
                   "n_N": len(pn)}
            for c in (7, 10, cb):
                rec[f"r_{c}"] = math.exp(pn[c].mean()) if c in pn else float("nan")
            rec["T7_T10"] = math.exp((pn[7] - pn[10]).mean()) if 7 in pn and 10 in pn else float("nan")
            rec["n_N_10_faster"] = int(((pn[7] - pn[10]) > 0).sum()) if 7 in pn and 10 in pn else 0
            rows.append(rec)
    return pd.DataFrame(rows)


def jvm_t_summary(pj: pd.DataFrame, cb: int):
    """mean, min–max, khoảng t 95% (trên log) với n = số JVM."""
    rows = []
    for s, g in pj.groupby("scale"):
        for col, lab in [("r_7", "r(7)"), ("r_10", "r(10)"), (f"r_{cb}", f"r({cb})"), ("T7_T10", "T7/T10")]:
            v = np.log(g[col].dropna().to_numpy())
            n = len(v)
            if n == 0:
                continue
            m = v.mean()
            half = stats.t.ppf(0.975, n - 1) * v.std(ddof=1) / math.sqrt(n) if n > 1 else float("nan")
            rows.append({"scale": s, "metric": lab, "n_jvm": n, "mean": math.exp(m), "min": math.exp(v.min()),
                         "max": math.exp(v.max()), "t_lo": math.exp(m - half), "t_hi": math.exp(m + half),
                         "sd_log": v.std(ddof=1) if n > 1 else float("nan"),
                         "n_jvm_10_faster": int((g.T7_T10 > 1).sum()) if col == "T7_T10" else None})
    return pd.DataFrame(rows)


def fig_per_jvm(pj: pd.DataFrame, js: pd.DataFrame, cb: int, figdir, saved):
    if pj.empty:
        return
    runs = list(dict.fromkeys(pj.run))
    nr = len(runs)
    off = lambda ri: (ri - (nr - 1) / 2) * (0.56 / max(nr, 2))           # lệch ngang theo lượt
    fig, axes = plt.subplots(2, 3, figsize=(FIG_W, 4.8), sharey="row")
    metrics = [("r_7", "r(7)", "c = 7"), ("r_10", "r(10)", "c = 10"), (f"r_{cb}", f"r({cb})", f"c = {cb}")]
    for j, s in enumerate(SCALES):
        g = pj[pj.scale == s]
        if g.empty:
            axes[0, j].set_visible(False)
            axes[1, j].set_visible(False)
            continue
        ax = axes[0, j]
        for k, (col, lab, xl) in enumerate(metrics):
            for _, r_ in g.iterrows():
                ri = runs.index(r_.run)
                ax.plot(k + off(ri) + (r_.fork - 2) * 0.05, (1 - r_[col]) * 100, linestyle="none",
                        marker=MARKERS[(r_.fork - 1) % 5], color=SERIES[ri % 5], markersize=4.5, alpha=0.85)
            row = js[(js.scale == s) & (js.metric == lab)]
            if len(row):
                row = row.iloc[0]
                ax.errorbar([k + 0.42], [(1 - row["mean"]) * 100],
                            yerr=[[(row.t_hi - row["mean"]) * 100], [(row["mean"] - row.t_lo) * 100]],
                            fmt="_", color=INK, capsize=3, markersize=10, linewidth=1.4)
        ax.set_xticks(range(3))
        ax.set_xticklabels([m[2] for m in metrics], fontsize=8)
        ax.set_title(f"thang {slabel(s)}", fontsize=9.5)
        ax.grid(axis="x", visible=False)
        ax2 = axes[1, j]
        for _, r_ in g.iterrows():
            ri = runs.index(r_.run)
            ax2.plot(off(ri) * 1.8 + (r_.fork - 2) * 0.08, (r_.T7_T10 - 1) * 100, linestyle="none",
                     marker=MARKERS[(r_.fork - 1) % 5], color=SERIES[ri % 5], markersize=5, alpha=0.85)
        row = js[(js.scale == s) & (js.metric == "T7/T10")]
        if len(row):
            row = row.iloc[0]
            ax2.errorbar([0.8], [(row["mean"] - 1) * 100],
                         yerr=[[(row["mean"] - row.t_lo) * 100], [(row.t_hi - row["mean"]) * 100]],
                         fmt="_", color=INK, capsize=3, markersize=10, linewidth=1.4)
        ax2.axhline(0, color=INK2, linewidth=0.8)
        ax2.set_xlim(-0.75, 1.05)
        ax2.set_xticks([])
        ax2.grid(axis="x", visible=False)
    axes[0, 0].set_ylabel("thời gian giảm\nso với c = 1 (%)")
    axes[1, 0].set_ylabel("T7/T10 − 1 (%)\n(> 0: 10 nhanh hơn 7)")
    handles = [plt.Line2D([], [], color=SERIES[i % 5], marker="o", linestyle="none", label=r) for i, r in enumerate(runs)]
    handles += [plt.Line2D([], [], color=INK2, marker=MARKERS[f - 1], linestyle="none", label=f"fork {f}")
                for f in sorted(pj.fork.unique())]
    handles += [plt.Line2D([], [], color=INK, marker="_", markersize=10, linestyle="none", label="TB ± khoảng t 95%")]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), bbox_to_anchor=(0.5, -0.06), fontsize=7.5)
    fig.suptitle("Biến thiên giữa các JVM (mỗi điểm = một JVM, TB nhân trên 24 N)", y=1.02, fontsize=10.5)
    save(fig, figdir, "fig16_per_jvm", saved)


def multi_compare(runs: list, rng, B: int):
    """So sánh nhiều lượt chạy; runs[0] = lượt chính. Mỗi phần tử: label, core, rq1, df, env, pooled.
    Trả về: r theo cutoff (dạng dài), c tốt nhất/speedup theo lượt, cặp lượt, giao tập gần tối ưu, RAM."""
    labels = [r["label"] for r in runs]
    cols = ["distribution", "scale", "cutoff", "r_gm", "ci_lo", "ci_hi", "T_per_NlgN_ns"]
    long = pd.concat([r["core"].agg[cols].assign(run=r["label"]) for r in runs], ignore_index=True)
    base = runs[0]["core"].agg.set_index(["distribution", "scale", "cutoff"]).r_gm.rename("r_main")
    long = long.join(base, on=["distribution", "scale", "cutoff"])
    long["diff_vs_main_pct"] = (long.r_gm / long.r_main - 1) * 100
    keys = set(runs[0]["core"].boot)
    for r in runs[1:]:
        keys &= set(r["core"].boot)
    keys = sorted(keys, key=lambda k: (DISTS.index(k[0]), k[1]))

    best_rows, pair_rows, inter_rows, near = [], [], [], {}
    for d, s in keys:
        for r in runs:
            q = r["rq1"][(r["rq1"].distribution == d) & (r["rq1"].scale == slabel(s))].iloc[0]
            near[(r["label"], d, s)] = set(map(int, q.near_optimal_2pct.split()))
            rec = {"run": r["label"], "distribution": d, "scale": slabel(s), "best_cutoff": int(q.best_cutoff),
                   "r_best": q.r_best, "near_range": q.near_range, "near_optimal_2pct": q.near_optimal_2pct}
            if d == "random":
                ag = r["core"].agg[(r["core"].agg.distribution == d) & (r["core"].agg.scale == s)].set_index("cutoff")
                for c, name in [(7, "7"), (10, "10"), (int(q.best_cutoff), "best")]:
                    rec[f"red_{name}"] = 1 - ag.r_gm[c]
                    rec[f"red_{name}_ci"] = f"[{fmt_pct(1 - ag.ci_hi[c])}, {fmt_pct(1 - ag.ci_lo[c])}]"
                res = paired_test(r["df"][(r["df"].distribution == "random") & (r["df"].scale == s)], 7, 10, rng, B)
                rec["T7_T10"] = res["ratio"] if res else float("nan")
                rec["p_7v10"] = res["p_wilcoxon"] if res else float("nan")
                rec["n_N"] = res["n_N"] if res else None
                rec["n_N_10_faster"] = res["n_N"] - res["n_N_a_faster"] if res else None     # a = 7 → 10 nhanh hơn
                rec["TnlgN_c1_ns"] = float(ag.T_per_NlgN_ns[1])
            best_rows.append(rec)
        inter = set.intersection(*[near[(lab, d, s)] for lab in labels])
        bests = [rr["best_cutoff"] for rr in best_rows[-len(runs):]]
        inter_rows.append({"distribution": d, "scale": slabel(s), "near_intersection_all": " ".join(map(str, sorted(inter))),
                           "best_cutoffs": " / ".join(map(str, bests)),
                           "every_best_in_intersection": all(b_ in inter for b_ in bests)})
        for i in range(len(runs)):
            for j in range(i + 1, len(runs)):
                a_ = long[(long.run == labels[i]) & (long.distribution == d) & (long.scale == s)].set_index("cutoff").r_gm
                b_ = long[(long.run == labels[j]) & (long.distribution == d) & (long.scale == s)].set_index("cutoff").r_gm
                m = pd.concat([a_.rename("a"), b_.rename("b")], axis=1, join="inner")
                m1 = m[m.index > 1]
                dd = (m.b / m.a - 1) * 100
                pair_rows.append({"distribution": d, "scale": slabel(s), "run_a": labels[i], "run_b": labels[j],
                                  "n_cutoffs": len(m),
                                  "pearson_r": float(np.corrcoef(m1.a, m1.b)[0, 1]) if len(m1) > 2 else float("nan"),
                                  "max_abs_diff_pct": float(dd.abs().max()), "mean_diff_pct": float(dd.mean()),
                                  "near_intersection": " ".join(map(str, sorted(near[(labels[i], d, s)] & near[(labels[j], d, s)])))})
    best = pd.DataFrame(best_rows)
    if "TnlgN_c1_ns" in best:
        t0 = best[best.run == labels[0]].set_index(["distribution", "scale"]).TnlgN_c1_ns
        best["TnlgN_c1_vs_main"] = [x / t0.get((d, s), np.nan) for x, d, s in zip(best.TnlgN_c1_ns, best.distribution, best.scale)]
    inter_all = None                                   # random: giao trên mọi thang và mọi lượt
    for d, s in keys:
        if d == "random":
            sset = set.intersection(*[near[(lab, d, s)] for lab in labels])
            inter_all = sset if inter_all is None else inter_all & sset
    ram = pd.DataFrame([{"run": r["label"], "fork": f, "ram_free_gb": ram_free(r["env"], f)} for r in runs for f in sorted(r["env"])])
    return {"long": long, "best": best, "pairs": pd.DataFrame(pair_rows), "inter": pd.DataFrame(inter_rows),
            "inter_all": sorted(inter_all or []), "ram": ram, "labels": labels}


def fig_run_comparison(mc: dict, figdir, saved):
    long, pairs, labels = mc["long"], mc["pairs"], mc["labels"]
    fig, axes = plt.subplots(2, 3, figsize=(FIG_W, 5.4))
    for j, s in enumerate(SCALES):
        ax, ax2 = axes[0, j], axes[1, j]
        sub = long[(long.distribution == "random") & (long.scale == s)]
        if sub.empty:
            ax.set_visible(False)
            ax2.set_visible(False)
            continue
        g0 = sub[sub.run == labels[0]].set_index("cutoff").sort_index()
        ax.fill_between(g0.index, g0.ci_lo, g0.ci_hi, color=SERIES[0], alpha=0.15, linewidth=0)
        for i, lab in enumerate(labels):
            g = sub[sub.run == lab].sort_values("cutoff")
            ax.plot(g.cutoff, g.r_gm, color=SERIES[i % 5], marker=MARKERS[i % 5], markersize=2.6, linewidth=1.2,
                    label=lab + (" (chính, CI 95%)" if i == 0 else ""))
        ax.axhline(1, color=INK2, linewidth=0.8)
        log2_cutoff_axis(ax, FULL_GRID)
        ax.set_title(f"thang {slabel(s)}", fontsize=9.5)
        ax.set_xlabel("CUTOFF c", fontsize=8.5)
        lo, hi = sub.r_gm.min() - 0.01, sub.r_gm.max() + 0.01
        ax2.plot([lo, hi], [lo, hi], color=INK2, linewidth=0.8, linestyle="--")
        txt = []
        for i, lab in enumerate(labels[1:], start=1):
            gi = sub[sub.run == lab].set_index("cutoff").r_gm
            ax2.plot(g0.r_gm.reindex(gi.index), gi, linestyle="none", marker=MARKERS[i % 5], color=SERIES[i % 5],
                     markersize=3.2, alpha=0.8)
            pr = pairs[(pairs.distribution == "random") & (pairs.scale == slabel(s)) & (pairs.run_a == labels[0])
                       & (pairs.run_b == lab)]
            if len(pr):
                txt.append(f"{lab}: {pr.pearson_r.iloc[0]:.3f} / {pr.max_abs_diff_pct.iloc[0]:.1f}%")
        ax2.text(0.03, 0.97, "Pearson / chênh max\n" + "\n".join(txt), transform=ax2.transAxes, va="top",
                 fontsize=6.5, color=INK2)
        ax2.set_xlim(lo, hi)
        ax2.set_ylim(lo, hi)
        ax2.set_xlabel(f"r ({labels[0]})", fontsize=8.5)
    axes[0, 0].set_ylabel("r = T(c)/T(1)")
    axes[1, 0].set_ylabel("r (lượt so sánh)")
    h, l_ = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l_, loc="lower center", ncol=len(labels), fontsize=7.5, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle(f"So sánh {len(labels)} lượt chạy (random); dưới: r của từng lượt so với lượt chính, đường chéo y = x",
                 y=1.01, fontsize=10.5)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, figdir, "fig15_run_comparison", saved)


def warmup_jump(totals):
    """vòng nhảy (1-index) và tỉ lệ; bỏ vòng 1 (lạnh). Chỉ tính là nhảy nếu mức mới DUY TRÌ: trung vị từ vòng đó
    tới hết cũng > (1 + JUMP_TOL) × trung vị các vòng trước (một vòng lẻ cao, như run 3 f1 vòng 7, không tính)."""
    t = list(totals)
    for r in range(3, len(t) + 1):
        base = float(np.median(t[1:r - 1]))
        after = float(np.median(t[r - 1:]))
        if t[r - 1] > (1 + JUMP_TOL) * base and after > (1 + JUMP_TOL) * base:
            return r, after / base
    return None, float("nan")


def parse_estimate(pdir: Path):
    p = pdir / "estimate.txt"
    if not p.exists():
        return None
    m = re.search(r"3 forks \(Benchmark\)\s*:\s*(\d+):(\d+):(\d+)", p.read_text(encoding="utf-8"))
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) if m else None


def hms_to_s(x):
    if not x:
        return None
    h, m_, s = map(int, x.split(":"))
    return h * 3600 + m_ * 60 + s


def jit_analysis(main_units, pilot_units, ref_df_for_r: pd.Series, state_ref_units, state_tol=STATE_TOL):
    """Bước nhảy warm-up, trạng thái theo bộ dữ liệu so với lượt tham chiếu, pilot vs lượt chính, r ở hai trạng thái.
    Trạng thái: rel = exp(TB log T của JVM trên bộ đó − TB các JVM tham chiếu trên CÙNG bộ (TB nhân));
    'nhanh' (= cùng mức tham chiếu) nếu rel < state_tol."""
    wrows = []
    fast_round_ms = FAST_NS_PER_NLGN * 65536 * 16 * 35 / 1e6
    for u in main_units + pilot_units:
        for k, s_ in enumerate(u["env"]):
            tot = s_["jvm_warmup"].get("round_totals_ms", [])
            if not tot:
                continue
            jr, ratio = warmup_jump(tot)
            wrows.append({"jvm": u["jvm"], "session": k + 1, "ram_free_gb": u["ram_gb"], "rounds": len(tot),
                          "round_totals_ms": " ".join(f"{x:.1f}" for x in tot), "jump_round": jr,
                          "jump_ratio": ratio, "last_round_ms": tot[-1],
                          "min_round_ms": min(tot[1:]) if len(tot) > 1 else tot[0],
                          "last3_vs_fast": float(np.median(tot[-3:])) / fast_round_ms})
    wtab = pd.DataFrame(wrows)

    def ds_level(u):
        d = u["df"].assign(lgt=np.log(u["df"].time_ns))
        return d.groupby(["distribution", "N"]).agg(mlt=("lgt", "mean"), o=("run_order", "min")).reset_index()
    levels = {u["jvm"]: ds_level(u) for u in main_units + pilot_units}
    for u in state_ref_units:
        levels.setdefault(u["jvm"], ds_level(u))
    ref = pd.concat([levels[u["jvm"]] for u in state_ref_units]).groupby(["distribution", "N"]).mlt.mean().rename("ref")
    srows = []
    for u in main_units + pilot_units:
        lv = levels[u["jvm"]].join(ref, on=["distribution", "N"]).sort_values("o").reset_index(drop=True)
        lv["rel"] = np.exp(lv.mlt - lv.ref)
        lv["idx"] = np.arange(1, len(lv) + 1)
        lv["progress"] = lv.idx / len(lv)
        lv["has_ref"] = lv.ref.notna()
        lv["fast"] = lv.rel < state_tol
        lv["jvm"] = u["jvm"]
        lv["kind"] = u.get("kind", "chính")
        lv["group"] = np.where(lv.distribution == "random", "random " + lv.N.map(lambda n: slabel(scale_of(n))),
                               lv.distribution + " " + lv.N.map(lambda n: slabel(scale_of(n))))
        srows.append(lv)
    state = pd.concat(srows, ignore_index=True) if srows else pd.DataFrame()

    st_sum = []
    for j, g in state[state.has_ref].groupby("jvm", sort=False):
        f = g.fast.to_numpy()
        runs_, cur = [], 0                       # độ dài các chuỗi bộ "nhanh" liên tiếp
        for x in f:
            cur = cur + 1 if x else 0
            runs_.append(cur)
        longest = max(runs_) if runs_ else 0
        # chuyển trạng thái = bộ chậm đầu tiên ngay sau một chuỗi >= 3 bộ nhanh
        switch = next((int(g.idx.iloc[i]) for i in range(1, len(f)) if runs_[i - 1] >= 3 and not f[i]), None)
        slow_groups = g[~g.fast].group.value_counts()
        st_sum.append({"jvm": j, "kind": g.kind.iloc[0], "datasets": len(g), "fast_datasets": int(f.sum()),
                       "below_datasets": int((g.rel < 1 / state_tol).sum()),
                       "longest_fast_run": longest, "first_slow_after_fast": switch,
                       "rel_median": float(g.rel.median()),
                       "rel_p05": float(g.rel.quantile(0.05)), "rel_p95": float(g.rel.quantile(0.95)),
                       "rel_fast_median": float(g[g.fast].rel.median()) if f.any() else float("nan"),
                       "rel_slow_median": float(g[~g.fast].rel.median()) if (~f).any() else float("nan"),
                       "slow_by_group": "; ".join(f"{k}: {v}" for k, v in slow_groups.items()),
                       "rel_by_scale_random": "; ".join(
                           f"{k}: {math.exp(np.log(h.rel).mean()):.3f}" for k, h in g[g.distribution == "random"].groupby("group"))})
    st_sum = pd.DataFrame(st_sum)

    # r ở trạng thái nhanh vs chậm: pilot (theo bộ dữ liệu) so với lượt chính tại cùng (phân bố, N)
    rrows = []
    for u in pilot_units:
        lv = state[(state.jvm == u["jvm"]) & state.has_ref]
        for flag, name in [(True, "nhanh"), (False, "chậm")]:
            keys = set(map(tuple, lv[lv.fast == flag][["distribution", "N"]].to_numpy()))
            if not keys:
                continue
            sub = u["df"][[ (d, n) in keys for d, n in zip(u["df"].distribution, u["df"].N)]]
            pr = per_n_log_r(sub)
            j = pd.concat([pr.rename("x"), ref_df_for_r.rename("m")], axis=1, join="inner").reset_index()
            j = j[j.cutoff > 1]
            for d, g in j.groupby("distribution"):
                dd = g.x - g.m
                rrows.append({"pilot": u["jvm"], "state": name, "distribution": d, "n_N": g.N.nunique(),
                              "n_pairs": len(g), "mean_diff_log_r_pct": dd.mean() * 100,
                              "sd_diff_pct": dd.std(ddof=1) * 100 if len(g) > 1 else float("nan"),
                              "pearson": float(np.corrcoef(g.x, g.m)[0, 1]) if len(g) > 2 else float("nan")})
    rtab = pd.DataFrame(rrows)

    # T/(N lgN) ở c = 1 (random) theo thang trong từng trạng thái của pilot
    trows = []
    for u in pilot_units:
        lv = state[(state.jvm == u["jvm"]) & state.has_ref]
        d = u["df"][(u["df"].distribution == "random") & (u["df"].cutoff == 1)].copy()
        d = d.merge(lv[["distribution", "N", "fast"]], on=["distribution", "N"])
        d["ltn"] = np.log(d.time_ns / (d.N * np.log2(d.N)))
        d["scale"] = d.N.map(scale_of)
        for (fast, s), g in d.groupby(["fast", "scale"]):
            trows.append({"pilot": u["jvm"], "state": "nhanh" if fast else "chậm", "scale": slabel(s),
                          "n_N": g.N.nunique(), "T_per_NlgN_ns": math.exp(g.groupby("N").ltn.mean().mean())})
    ttab = pd.DataFrame(trows)
    return wtab, state, st_sum, rtab, ttab


def fig_jit(wtab: pd.DataFrame, state: pd.DataFrame, run_of: dict, ref_label: str, state_tol: float, figdir, saved):
    """Màu theo nhóm (mỗi run một màu, mỗi pilot một màu) để không vượt quá bảng màu phân loại."""
    if wtab.empty and state.empty:
        return
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(FIG_W, 3.1), gridspec_kw={"width_ratios": [1, 1.4], "wspace": 0.35})
    groups = list(dict.fromkeys(run_of.get(j, j) for j in list(wtab.jvm) + list(state.jvm)))[:5]
    col = {g: SERIES[k] for k, g in enumerate(groups)}
    seen = set()
    for _, r_ in wtab.iterrows():
        grp = run_of.get(r_.jvm, r_.jvm)
        if grp not in col:
            continue
        t = [float(x) for x in r_.round_totals_ms.split()]
        pil = grp.startswith("pilot")
        ax.plot(range(1, len(t) + 1), t, color=col[grp], marker=".", linewidth=2.2 if pil else 1.0,
                linestyle="-" if pil else "--", label=None if grp in seen else grp)
        seen.add(grp)
    ax.axhline(FAST_NS_PER_NLGN * 65536 * 16 * 35 / 1e6, color=NEUTRAL, linewidth=1, linestyle=":")
    ax.set_xlabel("vòng warm-up JVM")
    ax.set_ylabel("tổng một vòng (ms)")
    ax.set_title("Warm-up JVM (chấm: mức nhanh E0_2)", fontsize=9.5)
    st = state[state.has_ref] if "has_ref" in state else state
    for j, g in st.groupby("jvm", sort=False):
        grp = run_of.get(j, j)
        if grp not in col:
            continue
        pil = g.kind.iloc[0] == "pilot"
        ax2.plot(g.progress, g.rel, color=col[grp], linewidth=2.2 if pil else 0.8, alpha=1 if pil else 0.55,
                 marker="o" if pil else None, markersize=3, linestyle="-" if pil else "--")
    ax2.axhline(1, color=INK2, linewidth=0.8)
    ax2.axhline(state_tol, color=NEUTRAL, linewidth=1, linestyle=":")
    ax2.text(0.01, state_tol, f" ngưỡng {state_tol}", color=INK2, fontsize=7.5, va="bottom")
    ax2.set_xlabel("tiến độ (bộ dữ liệu thứ i / tổng)")
    ax2.set_ylabel(f"T / cùng bộ ở {ref_label}")
    ax2.set_title("Mức thời gian theo bộ dữ liệu", fontsize=9.5)
    fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=4, fontsize=7.5, bbox_to_anchor=(0.5, -0.12))
    fig.suptitle("Hai mức hiệu năng (liền = pilot, đứt = các fork của từng lượt)", y=1.03, fontsize=10.5)
    save(fig, figdir, "fig17_jit_state", saved)


def tree_coverage(counts: pd.DataFrame):
    """Từ S (merged_len): cây của c khác c−1 khi S(c) < S(c−1). Đếm số N mỗi thang, với 24 N và tập con 8 N (j chia hết cho 3)."""
    if counts.empty:
        return pd.DataFrame()
    c = counts[(counts.distribution == "random") & (counts.cutoff <= 32)].copy()
    rows = []
    for s in SCALES:
        ns = sorted(n for n in c.N.unique() if scale_of(n) == s)
        sub8 = set(ns[::3])
        piv = c[c.N.isin(ns)].pivot(index="N", columns="cutoff", values="merged_len")
        for k in range(2, 33):
            if k not in piv or k - 1 not in piv:
                continue
            ch = piv[k] < piv[k - 1]
            rows.append({"scale": slabel(s), "cutoff": k, "n_N_24": int(ch.sum()),
                         "n_N_8subset": int(ch[ch.index.isin(sub8)].sum()),
                         "n_N_power_of_2": int(ch.get(s, False))})
    return pd.DataFrame(rows)


def levels_over(n, cap):
    """Số tầng đệ quy (từ trên xuống) có đoạn con với working set 24·len > cap."""
    return max(0.0, math.log2(n * BYTES_PER_ELEM / cap))


def within_scale_slopes(df: pd.DataFrame, cutoffs):
    rows = []
    d = df[(df.distribution == "random") & df.cutoff.isin(cutoffs)]
    for (c, s), g in d.assign(scale=d.N.map(scale_of)).groupby(["cutoff", "scale"]):
        t = g.groupby("N").time_ns.apply(lambda x: math.exp(np.log(x).mean())).reset_index()
        t["tn"] = t.time_ns / (t.N * np.log2(t.N))
        lr_ = stats.linregress(np.log2(t.N), np.log(t.tn))
        rows.append({"cutoff": c, "scale": slabel(s), "n_N": len(t), "pct_per_doubling": (math.exp(lr_.slope) - 1) * 100,
                     "p": lr_.pvalue, "tn_min": t.tn.min(), "tn_max": t.tn.max(),
                     "levels_over_L1D": f"{levels_over(t.N.min(), L1D_BYTES):.1f}–{levels_over(t.N.max(), L1D_BYTES):.1f}",
                     "levels_over_L2": f"{levels_over(t.N.min(), CACHE_LEVELS['L2']):.1f}–{levels_over(t.N.max(), CACHE_LEVELS['L2']):.1f}",
                     "levels_over_L3": f"{levels_over(t.N.min(), CACHE_LEVELS['L3']):.1f}–{levels_over(t.N.max(), CACHE_LEVELS['L3']):.1f}",
                     "lgN": f"{math.log2(t.N.min()):.1f}–{math.log2(t.N.max()):.1f}"})
    return pd.DataFrame(rows)


def hms(sec):
    s = int(round(sec))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default="results")
    ap.add_argument("--counts", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--B", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20261027)
    ap.add_argument("--label", default=None, help="nhãn của lượt chính (mặc định: tên thư mục)")
    ap.add_argument("--compare", nargs="*", default=[], help="thư mục kết quả của (các) lượt khác để so sánh")
    ap.add_argument("--compare-label", nargs="*", default=[], help="nhãn theo thứ tự --compare (mặc định: tên thư mục)")
    ap.add_argument("--state-ref", default=None, help="nhãn lượt tham chiếu cho mục 10 (mặc định: lượt chính)")
    ap.add_argument("--state-tol", type=float, default=STATE_TOL, help="ngưỡng 'cùng mức tham chiếu' (mặc định 1.25)")
    ap.add_argument("--pilots", nargs="*", default=None,
                    help="các thư mục pilot (mặc định: <results>/pilot và <compare>/pilot nếu có)")
    args = ap.parse_args()

    results = Path(args.results)
    out = Path(args.out) if args.out else results / "analysis"
    tdir, fdir = out / "tables", out / "figures"
    tdir.mkdir(parents=True, exist_ok=True)
    fdir.mkdir(parents=True, exist_ok=True)
    raw, warm, env, counts, counts_path = load(results, Path(args.counts) if args.counts else None)
    modes = {s[0]["props"].get("mode", "?") for s in env.values() if s}
    pilot = "pilot" in modes
    forks = sorted(raw.fork.unique())
    saved, notes = [], []

    # ---------------------------------------------------------------- 1. độ đầy đủ & GC
    comp_rows = []
    for f in forks:
        sessions = env.get(f, [])
        planned = sessions[0]["order"] if sessions else \
            [(d, n, 0) for d, n in raw[raw.fork == f][["distribution", "N"]].drop_duplicates().itertuples(index=False)]
        for d, n, _ in planned:
            g = raw[(raw.fork == f) & (raw.distribution == d) & (raw.N == n)]
            R = design_reps(d, n, pilot)
            exp_cells = {(t, c) for t in range(1, R + 1) for c in grid_for(d)}
            got = g.groupby(["trial", "cutoff"]).size()
            comp_rows.append({"fork": f, "distribution": d, "N": n, "scale": slabel(scale_of(n)),
                              "expected": len(exp_cells), "observed": len(g),
                              "missing": len(exp_cells - set(got.index)), "duplicates": int((got > 1).sum()),
                              "unexpected": len(set(got.index) - exp_cells),
                              "gc_during_run": int(g.gc_during_run.sum()),
                              "batch_k": ",".join(str(k) for k in sorted(g.batch_k.unique()))})
    comp = pd.DataFrame(comp_rows)
    comp.to_csv(tdir / "completeness.csv", index=False)
    n_gc = int(raw.gc_during_run.sum())
    gc_tab = raw.groupby(["fork", "distribution", "scale"]).gc_during_run.agg(["sum", "size"]).reset_index()
    gc_tab["scale"] = gc_tab["scale"].map(slabel)
    gc_tab.rename(columns={"sum": "gc_flagged", "size": "measurements"}).to_csv(tdir / "gc_summary.csv", index=False)

    main_df = raw[~raw.gc_during_run].copy()
    core = Core(main_df, args.B, args.seed)
    core.agg.assign(scale=core.agg.scale.map(slabel)).to_csv(tdir / "r_by_cutoff.csv", index=False)
    core.perN.assign(r=np.exp(core.perN.mlr), scale=core.perN.scale.map(slabel)).drop(columns=["mlogtn"]) \
        .to_csv(tdir / "r_per_N.csv", index=False)
    core_gc = Core(raw.copy(), max(1000, args.B // 10), args.seed + 1)
    core_gc.agg.assign(scale=core_gc.agg.scale.map(slabel)).to_csv(tdir / "r_by_cutoff_with_gc.csv", index=False)
    mg = core.agg.merge(core_gc.agg, on=["distribution", "scale", "cutoff"], suffixes=("", "_gc"))
    max_gc_diff = float(np.nanmax(np.abs(mg.r_gm_gc / mg.r_gm - 1))) if len(mg) else float("nan")

    # ---------------------------------------------------------------- 3. RQ1
    rq1, freq_rows = [], []
    for (d, s) in sorted(core.boot, key=lambda k: (DISTS.index(k[0]), k[1])):
        a = core.agg[(core.agg.distribution == d) & (core.agg.scale == s)].set_index("cutoff")
        b = int(a.r_gm.idxmin())
        near = [int(c) for c in a.index if a.r_gm[c] <= a.r_gm[b] * (1 + NEAR_TOL)]
        fr = core.argmin_freq(d, s)
        for c, v in fr.items():
            freq_rows.append({"distribution": d, "scale": slabel(s), "cutoff": c, "freq_best": v})
        top = fr.sort_values(ascending=False)
        rq1.append({"distribution": d, "scale": slabel(s), "n_N": int(a.n_N.max()), "best_cutoff": b,
                    "best_by_median": int(a.r_median_obs.idxmin()),
                    "r_best": a.r_gm[b], "ci_lo": a.ci_lo[b], "ci_hi": a.ci_hi[b],
                    "near_optimal_2pct": " ".join(map(str, near)),
                    "near_range": f"{min(near)}–{max(near)}",
                    "boot_freq_best": fr.get(b, 0.0),
                    "boot_top3": "; ".join(f"{c}: {v:.0%}" for c, v in top.head(3).items()),
                    "boot_freq_in_near_set": float(fr[[c for c in near if c in fr.index]].sum())})
    rq1 = pd.DataFrame(rq1)
    rq1.to_csv(tdir / "rq1_best_cutoff.csv", index=False)
    pd.DataFrame(freq_rows).to_csv(tdir / "rq1_argmin_bootstrap.csv", index=False)

    # gộp 3 thang (random): bootstrap phân tầng theo thang, mỗi thang trọng số bằng nhau
    pooled = None
    keys = [("random", s) for s in SCALES if ("random", s) in core.boot]
    if keys:
        cuts = core.boot[keys[0]][0]
        if all(core.boot[k][0] == cuts for k in keys):
            bt = np.mean([core.boot[k][1] for k in keys], axis=0)
            pt = np.mean([np.log(core.agg[(core.agg.distribution == "random") & (core.agg.scale == k[1])]
                                 .set_index("cutoff").r_gm.reindex(cuts)) for k in keys], axis=0)
            am = np.argmin(bt, axis=1)
            fr = np.bincount(am, minlength=len(cuts)) / len(am)
            bi = int(np.argmin(pt))
            lo, hi = np.percentile(bt[:, bi], [2.5, 97.5])
            near = [cuts[j] for j in range(len(cuts)) if pt[j] <= pt[bi] + math.log(1 + NEAR_TOL)]
            pooled = {"best": int(cuts[bi]), "r": math.exp(pt[bi]), "lo": math.exp(lo), "hi": math.exp(hi),
                      "near": near, "freq": dict(zip(cuts, fr)), "scales": [slabel(k[1]) for k in keys]}
            pd.DataFrame({"cutoff": cuts, "r_gm_pooled": np.exp(pt),
                          "ci_lo": np.exp(np.percentile(bt, 2.5, axis=0)),
                          "ci_hi": np.exp(np.percentile(bt, 97.5, axis=0)), "freq_best": fr}) \
                .to_csv(tdir / "rq1_pooled_random.csv", index=False)

    # ---------------------------------------------------------------- 4. RQ3
    best_by_scale = {s: core.best("random", s) for s in SCALES if ("random", s) in core.boot}
    sp_rows = []
    for s, bc in best_by_scale.items():
        a = core.agg[(core.agg.distribution == "random") & (core.agg.scale == s)].set_index("cutoff")
        for lab, c in [("c = 7", 7), ("c = 10", 10), (f"tốt nhất", bc)]:
            if c not in a.index:
                continue
            sp_rows.append({"scale": s, "label": lab, "cutoff": c, "r_gm": a.r_gm[c], "ci_lo": a.ci_lo[c],
                            "ci_hi": a.ci_hi[c], "time_reduction": 1 - a.r_gm[c],
                            "red_lo": 1 - a.ci_hi[c], "red_hi": 1 - a.ci_lo[c], "speedup_x": 1 / a.r_gm[c],
                            **{f"lecture_{k}_in_CI": bool(a.ci_lo[c] <= v <= a.ci_hi[c]) for k, v in
                               {"r0.80": 0.80, "r0.833": 1 / 1.2}.items()}})
    sp = pd.DataFrame(sp_rows)
    sp.assign(scale=sp.scale.map(slabel) if len(sp) else []).to_csv(tdir / "rq3_speedup.csv", index=False)

    test_rows = []
    trng = np.random.default_rng(args.seed + 7)
    for s, bc in best_by_scale.items():
        sub = main_df[(main_df.distribution == "random") & (main_df.scale == s)]
        trials = sorted(sub.trial.unique())
        odd = [t for t in trials if t % 2 == 1]
        even = [t for t in trials if t % 2 == 0]
        obs_odd = core.obs[(core.obs.distribution == "random") & (core.obs.scale == s) & core.obs.trial.isin(odd)]
        bc_hold = int(point_by_cutoff(obs_odd)[0].idxmin()) if len(obs_odd) else None
        for a_, b_, kind, data, best_used in [
            (7, 10, "in-sample", sub, None),
            (bc, 7, "in-sample", sub, bc), (bc, 10, "in-sample", sub, bc),
            (bc_hold, 7, "holdout", sub[sub.trial.isin(even)], bc_hold),
            (bc_hold, 10, "holdout", sub[sub.trial.isin(even)], bc_hold),
            (bc_hold, 1, "holdout", sub[sub.trial.isin(even)], bc_hold)]:
            if a_ is None or a_ == b_ or data.empty:
                test_rows.append({"scale": slabel(s), "kind": kind, "a": a_, "b": b_,
                                  "note": "a = b (bỏ qua)" if a_ == b_ else "không đủ dữ liệu"})
                continue
            res = paired_test(data, a_, b_, trng, args.B)
            if res:
                test_rows.append({"scale": slabel(s), "kind": kind, "a": a_, "b": b_,
                                  "best_selected_on": "trial lẻ" if kind == "holdout" else "toàn bộ", **res,
                                  "note": ""})
    tests = pd.DataFrame(test_rows)
    if "p_wilcoxon" in tests:
        m = tests.p_wilcoxon.notna()
        tests.loc[m, "p_holm"] = holm(tests.loc[m, "p_wilcoxon"].to_numpy())
    tests.to_csv(tdir / "rq3_paired_tests.csv", index=False)

    # ---------------------------------------------------------------- 5. lớp tương đương
    eq_rows, leaf_rows = [], []
    fig_r_vs_cutoff(core, fdir, saved)
    fig_argmin(core, fdir, saved)
    fig_speedup(sp, fdir, saved)
    fig_paired(main_df, best_by_scale, fdir, saved)
    fig_equivalence(core, counts, fdir, saved, eq_rows)
    eq = pd.DataFrame(eq_rows)
    if len(eq):
        eq.assign(scale=eq.scale.map(slabel)).to_csv(tdir / "equivalence_classes_2k.csv", index=False)
    fig_leaf(core, fdir, saved, leaf_rows)
    pd.DataFrame(leaf_rows).to_csv(tdir / "r_by_leaf_length.csv", index=False)
    trees = []
    if not counts.empty:
        for (d, n), g in counts.groupby(["distribution", "N"]):
            trees.append({"distribution": d, "N": n, "scale": slabel(scale_of(n)),
                          "grid_size": len(g), "distinct_trees": g.merged_len.nunique()})
    trees = pd.DataFrame(trees)
    trees.to_csv(tdir / "distinct_trees_per_N.csv", index=False)

    # ---------------------------------------------------------------- 6. RQ2
    fig_heatmap(core, fdir, saved)
    fig_distributions(core, fdir, saved)

    # ---------------------------------------------------------------- 7. số đếm
    cn = pd.DataFrame()
    if not counts.empty:
        Ns = set(core.perN[core.perN.distribution == "random"].N)
        c = counts[(counts.distribution == "random") & counts.N.isin(Ns)].copy()
        nl = c.N * np.log2(c.N)
        c["C_nlgn"], c["A_nlgn"], c["E_nlgn"], c["S_nlgn"] = c.compares / nl, c.accesses / nl, c.exchanges / nl, c.merged_len / nl
        b1 = c[c.cutoff == 1].set_index("N")
        for col, src in [("C_ratio", "compares"), ("A_ratio", "accesses"), ("S_ratio", "merged_len")]:
            c[col] = c[src] / c.N.map(b1[src])
        c["scale"] = c.N.map(scale_of)
        cn = c.groupby(["scale", "cutoff"])[["C_nlgn", "A_nlgn", "E_nlgn", "S_nlgn", "C_ratio", "A_ratio",
                                              "S_ratio"]].mean().reset_index()
        cn.assign(scale=cn.scale.map(slabel)).to_csv(tdir / "counts_normalized.csv", index=False)
        call = counts.copy()
        nl = call.N * np.log2(call.N)
        call.assign(C_nlgn=call.compares / nl, A_nlgn=call.accesses / nl, E_nlgn=call.exchanges / nl,
                    S_nlgn=call.merged_len / nl).to_csv(tdir / "counts_all_normalized.csv", index=False)
    fig_counts(cn, core, fdir, saved)

    # ---------------------------------------------------------------- 8. mô hình thời gian
    rnd = main_df[main_df.distribution == "random"]
    tn = rnd.groupby(["N", "cutoff"]).logt.mean().reset_index()
    tn["T_ms"] = np.exp(tn.logt) / 1e6
    best_model = pooled["best"] if pooled else (list(best_by_scale.values())[0] if best_by_scale else 1)
    fits, vals, model_rows, val_rows = {}, {}, [], []
    for c in sorted({1, best_model}):
        g = tn[tn.cutoff == c]
        if len(g) < 3:
            continue
        lr_ = stats.linregress(np.log(g.N), g.logt)
        fits[c] = {"b": lr_.slope, "a_ns": math.exp(lr_.intercept), "r2": lr_.rvalue ** 2}
        k_nlgn = math.exp(np.mean(g.logt - np.log(g.N * np.log2(g.N))))
        model_rows.append({"cutoff": c, "n_N": len(g), "b": lr_.slope, "b_stderr": lr_.stderr,
                           "a_ns": math.exp(lr_.intercept), "R2": lr_.rvalue ** 2,
                           "k_ns_per_NlgN": k_nlgn})
        tr = g[g.N < 2 ** 19]
        te = g[g.N >= 2 ** 19]
        if len(tr) >= 3 and len(te) >= 1:
            lt = stats.linregress(np.log(tr.N), tr.logt)
            vals[c] = {"b": lt.slope, "a_ns": math.exp(lt.intercept)}
            pred = lt.intercept + lt.slope * np.log(te.N)
            k_tr = np.mean(tr.logt - np.log(tr.N * np.log2(tr.N)))
            pred2 = k_tr + np.log(te.N * np.log2(te.N))
            for n, o, p1, p2 in zip(te.N, te.logt, pred, pred2):
                val_rows.append({"cutoff": c, "N": n, "T_obs_ms": math.exp(o) / 1e6,
                                 "T_pred_powerlaw_ms": math.exp(p1) / 1e6, "rel_err_powerlaw": math.exp(p1 - o) - 1,
                                 "T_pred_NlgN_ms": math.exp(p2) / 1e6, "rel_err_NlgN": math.exp(p2 - o) - 1})
            model_rows[-1].update({"train_b": lt.slope, "train_a_ns": math.exp(lt.intercept)})
    model = pd.DataFrame(model_rows)
    model.to_csv(tdir / "runtime_model.csv", index=False)
    val = pd.DataFrame(val_rows)
    val.to_csv(tdir / "runtime_validation_2e19.csv", index=False)
    fig_model(tn, fits, vals, best_model, fdir, saved)
    cache_tab = fig_cache(main_df, sorted({1, best_model}), args.B, np.random.default_rng(args.seed + 13), fdir, saved)
    cache_tab.to_csv(tdir / "cache_levels.csv", index=False)

    # ---------------------------------------------------------------- 9. chẩn đoán
    jw_rows = []
    if not warm.empty:
        for f, g in warm[warm.distribution == "jvm_warmup"].groupby("fork"):
            g = g.sort_values("_file_order")
            it = g.warmup_iter.to_numpy()
            sess = np.concatenate([[0], np.cumsum(np.diff(it) < 0)])
            g = g.assign(session=sess)
            for (se, r), h in g.groupby(["session", "warmup_iter"]):
                jw_rows.append({"fork": f, "session": int(se), "round": int(r), "total_ms": h.time_ns.sum() / 1e6,
                                "n": len(h)})
    jw = pd.DataFrame(jw_rows)
    jw.to_csv(tdir / "warmup_jvm_rounds.csv", index=False)
    fig_warmup(jw, fdir, saved)

    dw = pd.DataFrame()
    if not warm.empty:
        w = warm[warm.distribution != "jvm_warmup"]
        med = main_df.groupby(["fork", "distribution", "N", "cutoff"]).time_ns.median().rename("t_meas")
        w = w.join(med, on=["fork", "distribution", "N", "cutoff"])
        w["ratio"] = w.time_ns / w.t_meas
        dw = w.groupby(["distribution", "warmup_iter"]).ratio.median().unstack("warmup_iter")
        dw.to_csv(tdir / "warmup_dataset_vs_measured.csv")

    # trôi: hồi quy fixed-effects; trừ trung bình nhóm (phân bố, N, c) ở CẢ log T và run_order
    g = main_df.copy()
    grp = g.groupby(["distribution", "N", "cutoff"])
    g["lq"] = g.logt - grp.logt.transform("mean")
    g["xo"] = g.run_order - grp.run_order.transform("mean")
    drift_rows = []
    for f, h in list(g.groupby("fork")) + [("pooled", g)]:
        if h.xo.std() == 0:
            continue
        lr_ = stats.linregress(h.xo, h.lq)
        rho = stats.spearmanr(h.xo, h.lq)
        drift_rows.append({"fork": f, "n": len(h), "slope_pct_per_1000_runs": (math.exp(lr_.slope * 1000) - 1) * 100,
                           "p_slope": lr_.pvalue, "spearman_rho": rho[0], "p_spearman": rho[1]})
    drift = pd.DataFrame(drift_rows)
    drift.to_csv(tdir / "drift.csv", index=False)
    fig_drift(g[["fork", "run_order", "lq"]], fdir, saved)

    fk_rows = []
    frng = np.random.default_rng(args.seed + 11)
    for f in forks:
        of = core.obs[(core.obs.fork == f) & (core.obs.distribution == "random")]
        for s, bc in best_by_scale.items():
            pn = of[of.scale == s].groupby(["N", "cutoff"]).lr.mean().unstack("cutoff")
            if pn.empty:
                continue
            for lab, c in [("c = 7", 7), ("c = 10", 10), ("tốt nhất", bc)]:
                if c not in pn:
                    continue
                v = pn[c].dropna().to_numpy()
                bt = cluster_boot_means(v.reshape(-1, 1), max(1000, args.B // 5), frng)[:, 0]
                fk_rows.append({"fork": f, "scale": s, "label": lab, "cutoff": c, "r_gm": math.exp(v.mean()),
                                "ci_lo": math.exp(np.percentile(bt, 2.5)), "ci_hi": math.exp(np.percentile(bt, 97.5)),
                                "n_N": len(v)})
    fk = pd.DataFrame(fk_rows)
    fk.assign(scale=fk.scale.map(slabel) if len(fk) else []).to_csv(tdir / "forks_speedup.csv", index=False)
    fig_forks(fk, fdir, saved)

    # env
    env_rows = []
    for f, sessions in env.items():
        for k, s_ in enumerate(sessions):
            p = s_["props"]
            env_rows.append({"fork": f, "session": k + 1, "kind": s_["kind"], "mode": p.get("mode"),
                             "java.version": p.get("java.version"), "java.vendor": p.get("java.vendor"),
                             "os": f"{p.get('os.name')} {p.get('os.version')} {p.get('os.arch')}",
                             "cpus": p.get("availableProcessors"), "maxMemory": p.get("maxMemory"),
                             "phys_total": p.get("physical_memory_total"),
                             "phys_free_start": p.get("physical_memory_free_at_start"),
                             "jvm_args": p.get("jvm_input_arguments"),
                             "jvm_warmup_rounds": s_["jvm_warmup"].get("rounds"),
                             "jvm_warmup_converged": s_["jvm_warmup"].get("converged"),
                             "start": p.get("start_time"), "end": s_["end"].get("end_time"),
                             "elapsed": s_["end"].get("elapsed"), "sink": s_["end"].get("sink")})
    envdf = pd.DataFrame(env_rows)
    envdf.to_csv(tdir / "env_summary.csv", index=False)

    # ---------------------------------------------------------------- 10. bổ sung: run so sánh, JVM, JIT, cache
    lab_p = args.label or results.name
    units_p = make_units(lab_p, main_df, env)
    for u in units_p:
        u["kind"] = "chính"
    if len(args.compare_label) not in (0, len(args.compare)):
        sys.exit("--compare-label phải có đúng số nhãn như --compare")
    runs = [{"label": lab_p, "dir": results, "core": core, "rq1": rq1, "df": main_df, "env": env,
             "pooled": pooled["best"] if pooled else None, "n": len(raw), "n_gc": n_gc}]
    units_c = []
    for k, cdir in enumerate(map(Path, args.compare)):
        lab_c = args.compare_label[k] if args.compare_label else cdir.name
        raw_c, _, env_c, _, _ = load(cdir, None)
        main_c = raw_c[~raw_c.gc_during_run].copy()
        core_c = Core(main_c, args.B, args.seed)
        rq1_c, _ = best_table(core_c)
        runs.append({"label": lab_c, "dir": cdir, "core": core_c, "rq1": rq1_c, "df": main_c, "env": env_c,
                     "pooled": pooled_best(core_c), "n": len(raw_c), "n_gc": int(raw_c.gc_during_run.sum())})
        uc = make_units(lab_c, main_c, env_c)
        for u in uc:
            u["kind"] = "chính"
        units_c += uc
    mc = None
    if len(runs) > 1:
        mc = multi_compare(runs, np.random.default_rng(args.seed + 17), args.B)
        mc["long"].assign(scale=mc["long"].scale.map(slabel)).to_csv(tdir / "compare_r_by_cutoff.csv", index=False)
        mc["best"].to_csv(tdir / "compare_best.csv", index=False)
        mc["pairs"].to_csv(tdir / "compare_pairs.csv", index=False)
        mc["inter"].to_csv(tdir / "compare_near_intersection.csv", index=False)
        mc["ram"].to_csv(tdir / "compare_ram_free.csv", index=False)
        pd.concat([r["rq1"].assign(run=r["label"]) for r in runs]).to_csv(tdir / "compare_rq1_best_cutoff.csv", index=False)
        fig_run_comparison(mc, fdir, saved)

    cb = pooled["best"] if pooled else (best_by_scale.get(2 ** 16) or 1)
    pj = per_jvm_table(units_p + units_c, cb)
    pj.assign(scale=pj.scale.map(slabel)).to_csv(tdir / "per_jvm.csv", index=False)
    js = jvm_t_summary(pj, cb)
    js.assign(scale=js.scale.map(slabel)).to_csv(tdir / "per_jvm_summary.csv", index=False)
    fig_per_jvm(pj, js, cb, fdir, saved)

    pilot_dirs = [Path(p) for p in (args.pilots or [])]
    if args.pilots is None:
        pilot_dirs = [d for d in [results / "pilot"] + [Path(c) / "pilot" for c in args.compare]
                      if (d / "raw_fork1.csv").exists()]
    pilot_units, estimates = [], []
    for k, pdir in enumerate(pilot_dirs):
        if pdir.resolve() == results.resolve():
            continue
        raw_pl, _, env_pl, _, _ = load(pdir, None)
        start = (env_pl.get(1) or [{"props": {}}])[0]["props"].get("start_time", "")
        lab = f"pilot {start[:16].replace('T', ' ')}" if start else f"pilot {k + 1}"
        u = make_units(lab, raw_pl[~raw_pl.gc_during_run], env_pl)[0]
        u["jvm"], u["kind"] = lab, "pilot"
        pilot_units.append(u)
        estimates.append({"pilot": lab, "dir": str(pdir), "estimate_3forks_s": parse_estimate(pdir)})
    actual = []
    for r in runs:
        secs = [hms_to_s(s_["end"].get("elapsed")) for f in sorted(r["env"]) for s_ in r["env"][f]]
        actual.append({"run": r["label"], "elapsed_3forks_s": sum(x for x in secs if x) if all(secs) else None})
    state_ref = args.state_ref or lab_p
    ref_units = [u for u in units_p + units_c if u["run"] == state_ref]
    if not ref_units:
        sys.exit(f"--state-ref '{state_ref}' không khớp nhãn lượt nào: {[r['label'] for r in runs]}")
    ref_lr = per_n_log_r(main_df)
    wtab, jstate, jsum, jr_tab, jt_tab = jit_analysis(units_p + units_c, pilot_units, ref_lr, ref_units, args.state_tol)
    for name, t in [("jit_warmup_rounds", wtab), ("jit_dataset_state", jstate), ("jit_state_summary", jsum),
                    ("jit_r_fast_vs_slow", jr_tab), ("jit_TnlgN_by_state", jt_tab)]:
        t.to_csv(tdir / f"{name}.csv", index=False)
    pd.DataFrame(estimates).to_csv(tdir / "pilot_estimates.csv", index=False)
    pd.DataFrame(actual).to_csv(tdir / "run_elapsed.csv", index=False)
    run_of = {u["jvm"]: u["run"] if u.get("kind") != "pilot" else u["jvm"] for u in units_p + units_c + pilot_units}
    fig_jit(wtab, jstate, run_of, state_ref, args.state_tol, fdir, saved)

    slopes = within_scale_slopes(main_df, sorted({1, best_model}))
    slopes.to_csv(tdir / "cache_within_scale.csv", index=False)
    cov = tree_coverage(counts)
    cov.to_csv(tdir / "tree_coverage.csv", index=False)

    # ---------------------------------------------------------------- 11. summary.md
    write_summary(out, locals())
    print(f"[analyze] {len(raw)} measurements, {len(forks)} fork(s), mode={','.join(sorted(modes))}")
    print(f"[analyze] tables -> {tdir}  ({len(list(tdir.glob('*.csv')))} files)")
    print(f"[analyze] figures -> {fdir}  ({len(saved)} files)")
    print(f"[analyze] summary -> {out / 'summary.md'}")


def write_summary(out: Path, v: dict):
    core, comp, rq1, sp, tests = v["core"], v["comp"], v["rq1"], v["sp"], v["tests"]
    pilot, forks, raw, env = v["pilot"], v["forks"], v["raw"], v["env"]
    L = []
    L.append("# Tóm tắt kết quả thí nghiệm CUTOFF\n")
    first = next(iter(env.values()))[0]["props"] if env else {}
    L.append(f"- Kết quả: `{v['results']}` — chế độ **{', '.join(sorted(v['modes']))}**, {len(forks)} fork, "
             f"{len(raw)} lần đo, {raw.groupby(['fork', 'distribution', 'N']).ngroups} cặp (fork, bộ dữ liệu).")
    if first:
        L.append(f"- Môi trường: {first.get('os.name')} {first.get('os.arch')}, {first.get('java.vendor')} JDK "
                 f"{first.get('java.version')}, {first.get('availableProcessors')} luồng; cờ JVM: "
                 f"`{first.get('jvm_input_arguments')}`.")
    L.append(f"- counts.csv: `{v['counts_path']}`; bootstrap B = {v['args'].B}, seed = {v['args'].seed}.")
    if pilot or len(forks) < 3:
        L.append("\n> **CẢNH BÁO — DỮ LIỆU PILOT / THIẾU FORK.** R = 2, "
                 f"{len(forks)} fork, chỉ 2–3 N mỗi (phân bố, thang). Các CI bootstrap theo cụm N, p-value Wilcoxon, "
                 "phân bố argmin, tập gần tối ưu, so sánh giữa các fork và trôi giữa các bộ dữ liệu **không có ý nghĩa "
                 "thống kê** ở đây; chỉ dùng để kiểm tra pipeline. Xem mục cuối.\n")

    L.append("\n## 1. Độ đầy đủ và GC\n")
    incomplete = comp[(comp.missing > 0) | (comp.duplicates > 0) | (comp.unexpected > 0)]
    L.append(f"- Bộ dữ liệu theo kế hoạch: {len(comp)}; đủ ô (trial × CUTOFF): {len(comp) - len(incomplete)}; "
             f"thiếu/thừa: {len(incomplete)}.")
    L.append(f"- Lần đo có gc_during_run = true: **{v['n_gc']}** / {len(raw)} (loại khỏi phân tích chính). "
             f"Trial mất baseline c = 1 do loại GC: {core.trials_without_baseline}.")
    L.append(f"- Phụ lục (giữ cả lần đo có GC): r lệch tối đa {fmt_pct(v['max_gc_diff'], 2)} so với bản chính "
             "(`tables/r_by_cutoff_with_gc.csv`).")
    L.append(f"- Lô K theo bộ dữ liệu: {', '.join(sorted(set(','.join(comp.batch_k).split(','))))}.")

    L.append("\n## 2. RQ1 — CUTOFF tốt nhất (r = T(c)/T(1), TB nhân trên các N, CI 95% bootstrap theo cụm N)\n")
    t = rq1.assign(r=lambda x: [f"{a:.3f} [{b:.3f}, {c:.3f}]" for a, b, c in zip(x.r_best, x.ci_lo, x.ci_hi)],
                   giam=lambda x: [fmt_pct(1 - a) for a in x.r_best],
                   dist=lambda x: x.distribution.map(DIST_VI))
    L.append(md_table(t[["dist", "scale", "n_N", "best_cutoff", "best_by_median", "r", "giam", "near_optimal_2pct",
                         "boot_top3"]]
                      .rename(columns={"dist": "phân bố", "scale": "thang", "n_N": "số N", "best_cutoff": "c tốt nhất",
                                       "best_by_median": "c tốt nhất (median)",
                                       "r": "r [CI 95%]", "giam": "thời gian giảm",
                                       "near_optimal_2pct": "gần tối ưu (≤ 2%)", "boot_top3": "argmin bootstrap (top 3)"})))
    if v["pooled"]:
        p = v["pooled"]
        L.append(f"\n- Gộp {len(p['scales'])} thang random (trọng số bằng nhau): c tốt nhất = **{p['best']}**, "
                 f"r = {p['r']:.3f} [{p['lo']:.3f}, {p['hi']:.3f}], gần tối ưu: {' '.join(map(str, p['near']))}; "
                 f"tần suất bootstrap là tốt nhất: "
                 + "; ".join(f"{c}: {f:.0%}" for c, f in sorted(p["freq"].items(), key=lambda x: -x[1])[:4]) + ".")

    L.append("\n## 3. RQ3 — CUTOFF 7, 10 và tốt nhất so với baseline (random)\n")
    if len(sp):
        t = sp.assign(scale=sp.scale.map(slabel),
                      r=[f"{a:.3f} [{b:.3f}, {c:.3f}]" for a, b, c in zip(sp.r_gm, sp.ci_lo, sp.ci_hi)],
                      giam=[f"{fmt_pct(a)} [{fmt_pct(b)}, {fmt_pct(c)}]" for a, b, c in
                            zip(sp.time_reduction, sp.red_lo, sp.red_hi)],
                      x=[f"{a:.3f}×" for a in sp.speedup_x],
                      l80=["có" if a else "không" for a in sp["lecture_r0.80_in_CI"]],
                      l83=["có" if a else "không" for a in sp["lecture_r0.833_in_CI"]])
        L.append(md_table(t[["scale", "label", "cutoff", "r", "giam", "x", "l80", "l83"]].rename(columns={
            "scale": "thang", "label": "", "cutoff": "c", "r": "r [CI]", "giam": "thời gian giảm [CI]",
            "x": "tăng tốc", "l80": "r = 0.80 trong CI?", "l83": "r = 0.833 trong CI?"})))
        L.append("\nBài giảng (Phần 1, mục cải tiến Mergesort): thêm cutoff \"có thể nhanh hơn khoảng 20%\". "
                 "Hai cách đọc: thời gian giảm 20% (r = 0.80) hoặc nhanh hơn 1.2 lần (r ≈ 0.833).")
    if len(tests) and "ratio" in tests:
        tt = tests[tests.ratio.notna()].copy()
        tt["T_a/T_b [CI]"] = [f"{a:.4f} [{b:.4f}, {c:.4f}]" for a, b, c in zip(tt.ratio, tt.ci_lo, tt.ci_hi)]
        tt["a nhanh hơn ở"] = [f"{int(k)}/{int(n)} N" for k, n in zip(tt.n_N_a_faster, tt.n_N)]
        tt["p (Wilcoxon)"] = tt.p_wilcoxon.map(lambda x: f"{x:.3g}")
        tt["p (Holm)"] = tt.p_holm.map(lambda x: f"{x:.3g}")
        tt["a"] = tt.a.astype(int)
        tt["b"] = tt.b.astype(int)
        L.append("\nSo sánh ghép cặp: log(T_a/T_b) trung bình trong từng N trước (tránh giả lặp), Wilcoxon "
                 "signed-rank trên các N, Holm cho cả họ kiểm định. *holdout* = c tốt nhất chọn trên trial lẻ, "
                 "đánh giá trên trial chẵn (tránh lời nguyền người thắng).\n")
        L.append(md_table(tt[["scale", "kind", "a", "b", "T_a/T_b [CI]", "a nhanh hơn ở", "p (Wilcoxon)", "p (Holm)"]]
                          .rename(columns={"scale": "thang", "kind": "loại"})))
        skipped = tests[tests.ratio.isna()] if "ratio" in tests else tests
        for _, r_ in skipped.iterrows():
            L.append(f"- thang {r_.scale}, {r_.kind}: a = {r_.a}, b = {r_.b} — {r_.note}")

    L.append("\n## 4. Lớp tương đương và độ dài lá\n")
    eq = v["eq"]
    if len(eq):
        for s, g in eq.groupby("scale"):
            cls = ", ".join(f"[{int(a)}–{int(b)}]" if a != b else f"[{int(a)}]" for a, b in zip(g.cutoff_from, g.cutoff_to))
            multi = g[g.n_cutoffs > 1]
            sd = math.sqrt(np.nansum((multi.n_cutoffs - 1) * multi.sd_log_r ** 2) / max(1, (multi.n_cutoffs - 1).sum())) \
                if len(multi) else float("nan")
            L.append(f"- N = {slabel(s)}: {len(g)} cây khác nhau trên lưới 35 CUTOFF: {cls}. Trong cùng một lớp "
                     f"(cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa "
                     f"{fmt_pct(multi.spread.max(), 1) if len(multi) else '–'}; SD gộp của log r = {sd:.3f} "
                     f"(≈ ±{fmt_pct(math.exp(sd) - 1, 1)} cho r của một CUTOFF ở một N).")
    trees = v["trees"]
    if len(trees):
        tr = trees[trees.distribution == "random"]
        L.append(f"- Số cây khác nhau trên lưới 35 CUTOFF (random, từ S trong counts.csv): N = 2^k: "
                 f"{', '.join(str(x) for x in tr[tr.N.isin(SCALES)].distinct_trees)}; các N khác: trung vị "
                 f"{tr[~tr.N.isin(SCALES)].distinct_trees.median():.0f} (min {tr.distinct_trees.min()}, max "
                 f"{tr.distinct_trees.max()}).")
    lr = pd.DataFrame(v["leaf_rows"])
    if len(lr):
        b = lr.loc[lr.r.idxmin()]
        L.append(f"- Theo độ dài lá trung bình (gộp mọi N random): r nhỏ nhất ≈ {b.r:.3f} ở độ dài lá ≈ {b.leaf:.1f} "
                 f"(khoảng {b['bin']}).")

    L.append("\n## 5. RQ2 — Ảnh hưởng của N và phân bố\n")
    t = rq1[rq1.distribution != "random"]
    rnd16 = rq1[(rq1.distribution == "random") & (rq1.scale == "2^16")]
    for _, r_ in pd.concat([rnd16, t]).iterrows():
        L.append(f"- {DIST_VI[r_.distribution]} (thang {r_.scale}): c tốt nhất = {r_.best_cutoff}, "
                 f"thời gian giảm {fmt_pct(1 - r_.r_best)}, gần tối ưu: {r_.near_optimal_2pct}.")
    rr = rq1[rq1.distribution == "random"]
    if len(rr) > 1:
        L.append(f"- Random theo thang: c tốt nhất " + ", ".join(f"{a} → {b}" for a, b in zip(rr.scale, rr.best_cutoff)) + ".")

    L.append("\n## 6. Số đếm (MergeCutoffCounted, random)\n")
    cn = v["cn"]
    if len(cn):
        for s, bc in v["best_by_scale"].items():
            row = cn[(cn.scale == s) & (cn.cutoff == bc)]
            if row.empty:
                continue
            row = row.iloc[0]
            tr_ = core.agg[(core.agg.distribution == "random") & (core.agg.scale == s) & (core.agg.cutoff == bc)].r_gm.iloc[0]
            L.append(f"- Thang {slabel(s)}, c = {bc}: C ×{row.C_ratio:.3f}, A ×{row.A_ratio:.3f}, S ×{row.S_ratio:.3f}, "
                     f"E/(N lgN) = {row.E_nlgn:.3f}, trong khi T ×{tr_:.3f} so với c = 1.")
        c1 = cn[cn.cutoff == 1]
        L.append(f"- c = 1: C/(N lgN) = {c1.C_nlgn.min():.3f}–{c1.C_nlgn.max():.3f}, A/(N lgN) = "
                 f"{c1.A_nlgn.min():.3f}–{c1.A_nlgn.max():.3f} (cận bài giảng: C ≤ N lgN, A ≤ 6 N lgN).")

    L.append("\n## 7. Mô hình thời gian chạy T = a·N^b (random)\n")
    model, val = v["model"], v["val"]
    for _, m in model.iterrows():
        L.append(f"- c = {int(m.cutoff)} ({int(m.n_N)} N): b = {m.b:.4f} ± {m.b_stderr:.4f}, a = {m.a_ns:.4g} ns, "
                 f"R² = {m.R2:.5f}; T/(N lgN) ≈ {m.k_ns_per_NlgN:.3f} ns.")
    if len(val):
        for c, g in val.groupby("cutoff"):
            L.append(f"- Kiểm chứng c = {c}: fit trên 2^12 + 2^16, dự đoán 2^19 → sai số tương đối (power law) "
                     f"TB {fmt_pct(g.rel_err_powerlaw.mean())}, |max| {fmt_pct(g.rel_err_powerlaw.abs().max())}; "
                     f"mô hình k·N lgN: TB {fmt_pct(g.rel_err_NlgN.mean())}, |max| {fmt_pct(g.rel_err_NlgN.abs().max())}. "
                     "(Âm = dự đoán thấp hơn đo.)")

    ct = v["cache_tab"]
    if len(ct):
        parts = []
        for c in sorted(ct.cutoff.unique()):
            a = core.agg[(core.agg.distribution == "random") & (core.agg.cutoff == c)].set_index("scale").T_per_NlgN_ns
            m = [a.get(sc, np.nan) for sc in SCALES]
            g19 = ct[(ct.cutoff == c) & (ct.N >= 2 ** 19)]
            n3 = CACHE_LEVELS["L3"] / BYTES_PER_ELEM
            lo3 = math.exp(np.log(g19[g19.N < n3].T_per_NlgN_ns).mean()) if (g19.N < n3).any() else float("nan")
            hi3 = math.exp(np.log(g19[g19.N >= n3].T_per_NlgN_ns).mean()) if (g19.N >= n3).any() else float("nan")
            parts.append(f"c = {c}: {m[0]:.2f} / {m[1]:.2f} / {m[2]:.2f} ns (2^12 / 2^16 / 2^19), tỉ số 2^16:2^12 = "
                         f"{m[1] / m[0]:.3f}, 2^19:2^16 = {m[2] / m[1]:.3f}; trong thang 2^19: N < {n3:.0f} → "
                         f"{lo3:.2f} ns, N ≥ {n3:.0f} → {hi3:.2f} ns")
        nn = np.array(sorted(ct.N.unique()), float)
        b_nlgn = stats.linregress(np.log(nn), np.log(nn * np.log2(nn))).slope
        L.append(f"- T/(N lgN) theo thang (TB nhân trên các N; working set 24N B; L2 ứng với N ≈ "
                 f"{CACHE_LEVELS['L2'] / BYTES_PER_ELEM:.0f} (L2 1 MB/nhân), L3 ứng với N ≈ "
                 f"{CACHE_LEVELS['L3'] / BYTES_PER_ELEM:.0f} (L3 16 MB)): " + "; ".join(parts)
                 + f". Mô hình k·N lgN thuần trên cùng tập N cho b = {b_nlgn:.4f}; phần b vượt quá giá trị này "
                 "tương ứng với việc T/(N lgN) tăng theo N (hình fig14); vị trí bước tăng so với ngưỡng L2/L3 là bằng chứng "
                 "gián tiếp cho hiệu ứng cache, không phải phép đo trực tiếp.")

    # ---- diễn giải cache (dữ liệu lượt này)
    sl = v["slopes"]
    if len(sl):
        L.append("\nDiễn giải bộ nhớ (phù hợp với hiệu ứng bộ nhớ, KHÔNG chứng minh là do cache):\n")
        L.append("- Kỳ vọng: khi working set 24N B vượt một mức cache, chỉ các tầng đệ quy TRÊN CÙNG (đoạn con lớn) "
                 "vượt mức đó, các tầng sâu vẫn nằm trong cache. Vì vậy T/(N lgN) nên TĂNG DẦN theo số tầng vượt, "
                 "không nhảy bậc tại vạch dọc.")
        for _, r_ in sl.iterrows():
            L.append(f"- c = {int(r_.cutoff)}, thang {r_.scale} (lgN {r_.lgN}): T/(N lgN) {r_.tn_min:.2f}–{r_.tn_max:.2f} ns, "
                     f"xu hướng trong thang {r_.pct_per_doubling:+.2f}% mỗi lần gấp đôi N (p = {r_.p:.3g}); số tầng vượt "
                     f"L1D 32 KB: {r_.levels_over_L1D}, vượt L2 1 MB: {r_.levels_over_L2}, vượt L3 16 MB: {r_.levels_over_L3}.")
        jt = v["jt_tab"]
        fast = jt[jt.state == "nhanh"] if len(jt) else jt
        if len(fast):
            for p, g in fast.groupby("pilot"):
                if g.scale.nunique() >= 2:
                    L.append(f"- Ở trạng thái nhanh ({p}, R = 2): T/(N lgN) ở c = 1 = " + ", ".join(
                        f"{r_.scale}: {r_.T_per_NlgN_ns:.2f} ns" for r_ in g.itertuples())
                        + " — tỉ số giữa các thang khác với các lượt ở xung thấp, nên độ tăng theo N phụ thuộc xung "
                        "(độ trễ bộ nhớ cố định theo ns chiếm tỉ trọng lớn hơn khi nhân chạy nhanh).")
        L.append("- Không tách được trong thiết kế này: TLB (trang 4 KB), L3 kiểu victim cache của Zen (dung lượng hiệu "
                 "dụng ≈ L2 + L3), băng thông DRAM single-channel, truy cập giá trị Integer qua tham chiếu đã bị xáo "
                 "trộn (truy cập ngẫu nhiên vào vùng 16N B), và mức xung của nhân chạy luồng đo (mục 10).")

    L.append("\n## 8. Chẩn đoán\n")
    jw = v["jw"]
    for (f, se), g in jw.groupby(["fork", "session"]) if len(jw) else []:
        last = g.total_ms.tail(3)
        L.append(f"- Warm-up JVM fork {f}, phiên {se + 1}: {len(g)} vòng, vòng 1 = {g.total_ms.iloc[0]:.1f} ms, "
                 f"3 vòng cuối = {last.min():.1f}–{last.max():.1f} ms.")
    dw = v["dw"]
    if len(dw):
        L.append("- Warm-up từng bộ (trung vị T_warmup / T_đo): " + "; ".join(
            f"{DIST_VI.get(d, d)}: " + ", ".join(f"vòng {int(k)} = {x:.3f}" for k, x in row.items())
            for d, row in dw.iterrows()) + ".")
    for _, d_ in v["drift"].iterrows():
        who = "gộp các fork" if d_.fork == "pooled" else f"fork {d_.fork}"
        L.append(f"- Trôi ({who}, hồi quy fixed-effects theo (phân bố, N, c)): {d_.slope_pct_per_1000_runs:+.2f}% "
                 f"mỗi 1000 lần đo (p = {d_.p_slope:.3g}), Spearman ρ = {d_.spearman_rho:+.3f}.")
    if len(forks) < 2:
        L.append("- Với 1 fork, mỗi (phân bố, N) chỉ đo ở một vị trí thời gian, nên trôi GIỮA các bộ dữ liệu bị "
                 "hấp thụ vào chuẩn hóa và không quan sát được; chỉ thấy trôi trong từng bộ.")
    fk = v["fk"]
    if len(fk) and fk.fork.nunique() > 1:
        rng_ = fk.groupby(["scale", "label"]).r_gm.agg(lambda x: x.max() / x.min() - 1)
        L.append("- Chênh lệch r giữa các fork (max/min − 1): " + "; ".join(
            f"{slabel(s)} {lab}: {fmt_pct(x, 2)}" for (s, lab), x in rng_.items()) + ".")

    # ---- 9. biến thiên giữa các JVM
    pj, js, cb = v["pj"], v["js"], v["cb"]
    if len(pj):
        L.append(f"\n## 9. Biến thiên giữa các JVM (đơn vị lặp = JVM; c tốt nhất gộp = {cb})\n")
        L.append("- **Lưu ý:** mọi CI bootstrap ở mục 2–3 chỉ lấy mẫu lại theo N, KHÔNG bao gồm biến thiên giữa các JVM. "
                 "Khoảng t dưới đây coi mỗi JVM là một lần lặp độc lập (n = số JVM, t với n − 1 bậc tự do, trên log). "
                 "Các fork cùng số ở các lượt dùng cùng thứ tự bộ dữ liệu (seed 1000 + fork), nên không hoàn toàn độc lập. "
                 f"Các lượt gộp: {', '.join(dict.fromkeys(pj.run))}.\n")
        t = js.assign(scale=js.scale.map(slabel),
                      v=[f"{a:.4f}" for a in js["mean"]], mm=[f"{a:.4f}–{b:.4f}" for a, b in zip(js["min"], js["max"])],
                      ci=[f"[{a:.4f}, {b:.4f}]" for a, b in zip(js.t_lo, js.t_hi)],
                      k=[("" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{int(x)}/{n}")
                         for x, n in zip(js.n_jvm_10_faster, js.n_jvm)])
        L.append(md_table(t[["scale", "metric", "n_jvm", "v", "mm", "ci", "k"]].rename(columns={
            "scale": "thang", "metric": "đại lượng", "n_jvm": "số JVM", "v": "TB nhân", "mm": "min–max",
            "ci": "khoảng t 95%", "k": "số JVM có 10 nhanh hơn 7"})))
        L.append("\nChi tiết từng JVM: `tables/per_jvm.csv`; hình `fig16_per_jvm.png`.")

    # ---- 10. hai mức hiệu năng
    wt, jsum = v["wtab"], v["jsum"]
    if len(wt):
        sref, stol = v["state_ref"], v["args"].state_tol
        L.append("\n## 10. Hai mức hiệu năng (bước nhảy; không do biên dịch lại MergeCutoff — log PrintCompilation; "
                 "cơ chế: xung của nhân chạy luồng đo — chẩn đoán E6, T2, run 3)\n")
        L.append(f"Bước nhảy warm-up: vòng đầu tiên (từ vòng 3) có tổng > {1 + JUMP_TOL:.2f} × trung vị các vòng trước "
                 f"(bỏ vòng 1) và trung vị từ vòng đó tới hết cũng vượt ngưỡng này. Mức warm-up = trung vị 3 vòng cuối / "
                 f"{FAST_NS_PER_NLGN * 65536 * 16 * 35 / 1e6:.0f} ms (mức nhanh của WarmupProbe E0_2, "
                 f"{FAST_NS_PER_NLGN} ns·N lgN). Trạng thái theo bộ dữ liệu: rel = T của JVM / T cùng bộ ở **{sref}** "
                 f"(TB nhân các fork của lượt đó, TB log T trên mọi c và trial); 'nhanh' (= cùng mức tham chiếu) nếu "
                 f"rel < {stol}. Hai mức đo được ở E6: xung 128.1% / 79.3% → tỉ lệ 1.62, trung điểm trên log 1.27. "
                 "Không dùng ngưỡng tuyệt đối theo T/(N lgN): trong một JVM ở một trạng thái, T/(N lgN) giữa các bộ dữ liệu "
                 "đã chênh 3.3–3.7× (phân bố, N). Nếu lượt tham chiếu ở mức chậm thì 'nhanh' chỉ có nghĩa 'không chậm hơn "
                 f"tham chiếu'; cột 'rel < {1 / stol:.2f}' đếm các bộ nhanh hẳn hơn tham chiếu.\n")
        t = wt.assign(ram=[f"{x:.2f}" for x in wt.ram_free_gb],
                      jr=[("–" if x is None or (isinstance(x, float) and math.isnan(x)) else str(int(x))) for x in wt.jump_round],
                      ratio=[("–" if math.isnan(x) else f"{x:.2f}×") for x in wt.jump_ratio],
                      lv=[f"{x:.2f}" for x in wt.last3_vs_fast])
        L.append(md_table(t[["jvm", "ram", "rounds", "round_totals_ms", "jr", "ratio", "lv"]].rename(columns={
            "jvm": "JVM", "ram": "RAM trống (GB)", "rounds": "số vòng", "round_totals_ms": "tổng mỗi vòng (ms)",
            "jr": "vòng nhảy", "ratio": "tỉ lệ nhảy", "lv": "mức 3 vòng cuối / nhanh"})))
        if len(jsum):
            L.append("")
            t = jsum.assign(fd=[f"{int(a)}/{int(b)}" for a, b in zip(jsum.fast_datasets, jsum.datasets)],
                            bl=[str(int(x)) for x in jsum.below_datasets],
                            med=[f"{x:.3f} [{a:.3f}, {b:.3f}]" for x, a, b in zip(jsum.rel_median, jsum.rel_p05, jsum.rel_p95)],
                            sw=[("–" if pd.isna(x) else str(int(x))) for x in jsum.first_slow_after_fast],
                            sl=[("tất cả" if f == 0 else (x or "–")) for f, x in zip(jsum.fast_datasets, jsum.slow_by_group)])
            L.append(md_table(t[["jvm", "kind", "fd", "bl", "med", "rel_by_scale_random", "sw", "sl"]].rename(columns={
                "jvm": "JVM", "kind": "loại", "fd": f"bộ nhanh (rel < {stol})", "bl": f"bộ rel < {1 / stol:.2f}",
                "med": f"rel trung vị [P5, P95]",
                "rel_by_scale_random": "rel random theo thang (TB nhân)", "sw": "bộ chậm đầu tiên sau ≥ 3 bộ nhanh",
                "sl": "bộ chậm theo nhóm"})))
        jr = v["jr_tab"]
        if len(jr):
            L.append("\nr của pilot so với lượt chính tại cùng (phân bố, N), theo trạng thái (log r_pilot − log r_chính, "
                     "c > 1; R = 2 nên nhiễu lớn):\n")
            t = jr.assign(md=[f"{x:+.2f}%" for x in jr.mean_diff_log_r_pct], sd=[f"{x:.2f}%" for x in jr.sd_diff_pct],
                          pc=[f"{x:.3f}" for x in jr.pearson], dist=jr.distribution.map(DIST_VI))
            L.append(md_table(t[["pilot", "state", "dist", "n_N", "md", "sd", "pc"]].rename(columns={
                "state": "trạng thái", "dist": "phân bố", "n_N": "số N", "md": "chênh TB", "sd": "SD", "pc": "Pearson"})))
        est, act = v["estimates"], v["actual"]
        if est or act:
            L.append("\n- Ước lượng pilot (3 fork): " + ("; ".join(
                f"{e['pilot']}: {hms(e['estimate_3forks_s']) if e['estimate_3forks_s'] else '–'}" for e in est) or "–")
                + ". Thời gian thực (tổng 3 fork): " + "; ".join(
                f"{a['run']}: {hms(a['elapsed_3forks_s']) if a['elapsed_3forks_s'] else '–'}" for a in act) + ".")
        L.append("- Hình: `fig17_jit_state.png`. Dữ liệu: `tables/jit_*.csv` (jit_dataset_state.csv: rel từng bộ).")

    # ---- 11. so sánh các lượt chạy
    mc, runs = v["mc"], v["runs"]
    if mc:
        labs = mc["labels"]
        sl_ = " / ".join(labs)
        L.append(f"\n## 11. So sánh {len(labs)} lượt chạy: {labs[0]} (chính), " + ", ".join(labs[1:]) + "\n")
        L.append("- " + "; ".join(f"{r['label']}: {r['n']} lần đo, gc_during_run = {r['n_gc']}, c tốt nhất gộp 3 thang "
                                  f"random = {r['pooled']}" for r in runs) + ".")
        L.append(f"- Thứ tự trong mọi ô có dấu '/': {sl_}.\n")
        b = mc["best"]
        inter = mc["inter"].set_index(["distribution", "scale"])
        rows = []
        for (d, s), g in b.groupby(["distribution", "scale"], sort=False):
            g = g.set_index("run").reindex(labs)
            rec = {"phân bố": DIST_VI.get(d, d), "thang": s,
                   "c tốt nhất": " / ".join(str(int(x)) for x in g.best_cutoff),
                   "gần tối ưu 2%": " / ".join(g.near_range),
                   f"giao {len(labs)} lượt": inter.loc[(d, s)].near_intersection_all or "∅"}
            if d == "random":
                rec["giảm c=7"] = " / ".join(fmt_pct(x) for x in g.red_7)
                rec["giảm c=10"] = " / ".join(fmt_pct(x) for x in g.red_10)
                rec["giảm tại c tốt nhất"] = " / ".join(fmt_pct(x) for x in g.red_best)
                rec["T7/T10 (p Wilcoxon)"] = " / ".join(f"{a:.4f} ({p_:.2g})" for a, p_ in zip(g.T7_T10, g.p_7v10))
                rec[f"T/(N lgN) c=1 so với {labs[0]}"] = " / ".join(f"{x:.3f}" for x in g.TnlgN_c1_vs_main)
            rows.append(rec)
        tb = pd.DataFrame(rows)
        rnd = tb[tb["phân bố"] == DIST_VI["random"]]
        L.append(md_table(rnd.dropna(axis=1, how="all")))
        oth = tb[tb["phân bố"] != DIST_VI["random"]]
        if len(oth):
            L.append("")
            L.append(md_table(oth[["phân bố", "thang", "c tốt nhất", "gần tối ưu 2%", f"giao {len(labs)} lượt"]]))
        pr = mc["pairs"]
        if len(pr):
            pr = pr.assign(pair=pr.run_a + " – " + pr.run_b,
                           val=[f"{a:.3f} ({m:.2f}%)" for a, m in zip(pr.pearson_r, pr.max_abs_diff_pct)])
            pt = pr.pivot_table(index=["distribution", "scale"], columns="pair", values="val", aggfunc="first",
                                sort=False).reset_index()
            pt["distribution"] = pt.distribution.map(DIST_VI)
            pt = pt[["distribution", "scale"] + list(dict.fromkeys(pr.pair))]
            L.append("\nTừng cặp lượt: Pearson r của đường r(c) (c > 1) và (chênh r tối đa trên lưới):\n")
            L.append(md_table(pt.rename(columns={"distribution": "phân bố", "scale": "thang"})))
        L.append(f"\n- Mọi c trong {' '.join(map(str, mc['inter_all']))} nằm trong vùng 2% của c tốt nhất ở cả 3 thang "
                 f"và cả {len(labs)} lượt (random)." if mc["inter_all"] else "\n- Không có c chung trong mọi tập gần tối ưu.")
        ram = mc["ram"]
        L.append("- RAM trống lúc bắt đầu từng fork (GB): " + "; ".join(
            f"{r}: " + " / ".join(f"{x:.2f}" for x in g.ram_free_gb) for r, g in ram.groupby("run", sort=False)) + ".")
        L.append("- Hình: `fig15_run_comparison.png`; bảng: `tables/compare_*.csv`.")

    # ---- độ phủ cây đệ quy
    cov = v["cov"]
    if len(cov):
        L.append("\n## Phụ: độ phủ cây đệ quy (từ S trong counts.csv)\n")
        for sc, g in cov.groupby("scale"):
            L.append(f"- Thang {sc}: số N (trên 24) có cây của c khác c − 1, c = 2..32: min {g.n_N_24.min()} "
                     f"(số c có < 2 N: {int((g.n_N_24 < 2).sum())}); với tập con 8 N (j chia hết cho 3): min "
                     f"{g.n_N_8subset.min()} (số c có < 2 N: {int((g.n_N_8subset < 2).sum())}); chỉ N = 2^k: "
                     f"{int(g.n_N_power_of_2.sum())}/31 giá trị c đổi cây.")
        L.append("- Bảng: `tables/tree_coverage.csv`.")

    if pilot or len(forks) < 3:
        L.append("\n## Cảnh báo: kết quả KHÔNG có ý nghĩa trên pilot (R = 2, 1 fork, 2–3 N mỗi nhóm)\n")
        L.append("- Mọi CI bootstrap theo cụm N: chỉ 2–3 cụm → rất ít mẫu lấy lại khác nhau; CI hẹp/rộng giả tạo.")
        L.append("- p-value Wilcoxon với n = 3 N: p nhỏ nhất có thể là 0.25 → không kiểm định nào có thể có ý nghĩa.")
        L.append("- Phân bố argmin bootstrap, tập gần tối ưu 2%, so sánh holdout (1 trial chọn, 1 trial đánh giá).")
        L.append("- So sánh giữa các fork và trôi giữa các bộ dữ liệu (cần ≥ 2 fork).")
        L.append("- Heatmap N × CUTOFF (9 hàng) và hình r theo độ dài lá: đúng cấu trúc nhưng nhiễu lớn.")
        L.append("- Mô hình T = a·N^b: chỉ 9 N, kiểm chứng trên 3 N.")
        L.append("- Có ý nghĩa ngay cả trên pilot: số đếm (tất định), cấu trúc lớp tương đương từ S, độ đầy đủ, "
                 "warm-up JVM, độ lớn sơ bộ của speedup.")

    L.append("\n## Tệp\n")
    L.append("- Bảng: " + ", ".join(sorted(p.name for p in (out / "tables").glob("*.csv"))))
    L.append("- Hình: " + ", ".join(v["saved"]))
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
