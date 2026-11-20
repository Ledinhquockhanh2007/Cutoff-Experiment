#!/usr/bin/env python3
"""
scripts/make_figures_p2.py: hình báo cáo bản 2 (T13; dữ liệu chính là giai đoạn xác nhận và chẩn đoán).

Đề bài: (đề bài nội bộ) Dàn ý: report/report_outline_final.md.
- Dùng lại set_style, COLORS, save_fig_bundle của scripts/make_figures.py (import, cùng font/cỡ/dpi, pdf.fonttype 42).
- Số liệu đọc từ results_phase2/analysis/tables (P2), results_phase2b/analysis/tables (P2B),
  preregistration (PR); đường theo fork (figA11) và typeperf (figA10) qua CHÍNH các hàm của
  scripts/analyze_t10.py và scripts/session_quality.py (import, không viết lại).
- KHÔNG có bước ngẫu nhiên (mọi CI lấy từ bảng P2/P2B, đã tính với seed ghi trong bảng/run_log),
  nên không cần seed; tham số --seed chỉ để giữ giao diện chung và không được dùng.
- Quy tắc A: sau khi ghi mỗi hình, đọc lại .data.csv, in số trên hình cạnh số trong bảng P2/P2B
  (chênh phải bằng 0, nếu khác: dừng), và ghi các dòng đó vào cuối .src.txt.

Cách chạy (từ thư mục gốc dự án):
    python scripts/make_figures_p2.py                 # mọi hình + FIGURES.md
    python scripts/make_figures_p2.py --only fig01,md # chỉ fig01 và FIGURES.md
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, FixedFormatter, NullLocator, FuncFormatter

from scripts import make_figures as mf

P2 = PROJECT_ROOT / "results_phase2" / "analysis" / "tables"
P2B = PROJECT_ROOT / "results_phase2b" / "analysis" / "tables"
PR = PROJECT_ROOT / "preregistration"
P2_REL = "results_phase2/analysis/tables"
P2B_REL = "results_phase2b/analysis/tables"
PR_REL = "preregistration"

MM = 1 / 25.4
W170 = 170 * MM
W120 = 120 * MM

SCALES5 = ["2^12", "2^14", "2^16", "2^18", "2^19"]
SCALES3 = ["2^12", "2^16", "2^19"]
CI2_TXT = ("CI hai tầng 95% (bootstrap rút fork có hoàn lại rồi rút N trong thang, B = 10 000, "
           "seed 20261117 cho P2 / 20261118 cho P2B), cột ci2_lo, ci2_hi")


# ───────────────────────────────────────────────────────────── tiện ích chung

def smath(scale: str) -> str:
    """'2^12' -> '$2^{12}$' (mathtext)."""
    return f"$2^{{{scale.split('^')[1]}}}$"


def C():
    return mf.COLORS


def scale_styles():
    c = C()
    return {
        "2^12": (c["blue"], "-", "o"),
        "2^14": (c["orange"], "--", "s"),
        "2^16": (c["bluish_green"], "-.", "^"),
        "2^18": (c["vermilion"], ":", "D"),
        "2^19": (c["reddish_purple"], (0, (5, 1.5)), "v"),
    }


def log2_axis(ax, ticks, lim=None):
    """Trục x thang log2 với nhãn là số thật."""
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FixedFormatter([str(t) for t in ticks]))
    ax.xaxis.set_minor_locator(NullLocator())
    if lim is not None:
        ax.set_xlim(*lim)


def parse_set(text: str) -> set[int]:
    """'17..32, 40, 48' -> {17, ..., 32, 40, 48}."""
    out: set[int] = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if ".." in part:
            a, b = part.split("..")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def compress(vals) -> str:
    vals = sorted(vals)
    parts, i = [], 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[j] + 1:
            j += 1
        parts.append(f"{vals[i]}..{vals[j]}" if j - i >= 2 else ", ".join(str(v) for v in vals[i:j + 1]))
        i = j + 1
    return ", ".join(parts)


def rule_a(out_dir: Path, name: str, items: list[tuple], tol: float = 0.0):
    """Quy tắc A. items: (mô tả, {cột: giá trị lọc}, cột trong .data.csv, giá trị bảng, nguồn bảng).
    Đọc lại .data.csv vừa ghi, in hai số cạnh nhau, ghi vào cuối .src.txt; dừng nếu |chênh| > tol."""
    d = pd.read_csv(out_dir / f"{name}.data.csv")
    lines = ["", "Quy tắc A (số đọc lại từ .data.csv | số trong bảng | chênh):"]
    bad = []
    for desc, flt, col, tval, tsrc in items:
        sub = d
        for k, v in flt.items():
            sub = sub[sub[k] == v]
        if len(sub) != 1:
            raise SystemExit(f"DỪNG [{name}] Quy tắc A: bộ lọc {flt} trả {len(sub)} hàng")
        fv = float(sub[col].iloc[0])
        tv = float(tval)
        diff = fv - tv
        lines.append(f"- {desc}: hình = {fv:.10g} | bảng ({tsrc}) = {tv:.10g} | chênh = {diff:.3g}")
        if abs(diff) > tol:
            bad.append(desc)
    src = out_dir / f"{name}.src.txt"
    src.write_text(src.read_text(encoding="utf-8").rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    for ln in lines[1:]:
        print("    " + ln)
    if bad:
        raise SystemExit(f"DỪNG [{name}] Quy tắc A lệch: {bad}")


def src_header(name: str, label: str, sources: list[str], errbar: str, body: str) -> str:
    return (f"Hình: {name}\nNhãn: {label}\nNguồn:\n" + "\n".join(f"- {s}" for s in sources)
            + f"\nThanh/dải sai số: {errbar}\nMô tả:\n{body.strip()}\n")


def legend_below(fig, handles, labels, ncol, y=-0.02, fontsize=7.5):
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, y), ncol=ncol,
               fontsize=fontsize, frameon=False, handlelength=2.4, columnspacing=1.4)


# ───────────────────────────────────────────────────────────── fig01

def make_fig01(out: Path):
    name = "fig01_r_vs_cutoff_run5"
    r = pd.read_csv(P2 / "p2_r_by_cutoff.csv")
    r = r[r["distribution"] == "random"]
    best = pd.read_csv(P2 / "p2_best.csv")
    best = best[best["distribution"] == "random"].set_index("scale")
    sets = {s: parse_set(best.loc[s, "near_optimal_2pct"]) for s in SCALES5}
    common = sorted(set.intersection(*sets.values()))
    grid = sorted(int(c) for c in r["cutoff"].unique())
    lo, hi = min(common), max(common)
    assert [c for c in grid if lo <= c <= hi] == common, "vùng chung không liên tục trên lưới"
    print(f"    vùng gần tối ưu chung (giao 5 thang, p2_best) = {{{compress(common)}}}")

    fig, ax = plt.subplots(figsize=(W170, 3.25))
    ax.axvspan(lo, hi, color=C()["light_grey"], alpha=0.55, lw=0, zorder=0)
    rows = []
    for s in SCALES5:
        col, ls, mk = scale_styles()[s]
        sub = r[r["scale"] == s].sort_values("cutoff")
        ax.fill_between(sub["cutoff"], sub["ci2_lo"], sub["ci2_hi"], color=col, alpha=0.16, lw=0)
        ax.plot(sub["cutoff"], sub["r"], color=col, ls=ls, marker=mk, ms=2.6, lw=1.1)
        cs, rs = int(best.loc[s, "c_star"]), float(best.loc[s, "r_star"])
        ax.plot([cs], [rs], marker="*", ms=10, mfc=col, mec="black", mew=0.6, ls="none", zorder=6)
        for row in sub.itertuples():
            rows.append({"scale": s, "cutoff": int(row.cutoff), "r": row.r, "ci2_lo": row.ci2_lo,
                         "ci2_hi": row.ci2_hi, "is_c_star": int(row.cutoff) == cs,
                         "in_common_near_opt": int(row.cutoff) in common})
    for cm in (7, 10):
        ax.axvline(cm, color=C()["grey"], lw=0.7, ls=(0, (1, 1.5)), zorder=1)
        ax.text(cm * 1.03, 1.003, f"$c = {cm}$", fontsize=7, color=C()["grey"], va="top", ha="left")
    log2_axis(ax, [1, 2, 4, 8, 16, 32, 64], lim=(0.92, 70))
    ax.set_ylim(min(r["ci2_lo"]) - 0.008, 1.006)
    ax.set_xlabel("CUTOFF $c$ (phần tử, thang log$_2$)")
    ax.set_ylabel("$r(c) = T(c)/T(1)$ (trung bình nhân 24 $N$)")
    handles = [Line2D([], [], color=scale_styles()[s][0], ls=scale_styles()[s][1], marker=scale_styles()[s][2],
                      ms=3.5, label=f"$S$ = {smath(s)}") for s in SCALES5]
    handles += [Line2D([], [], marker="*", ms=9, mfc="white", mec="black", ls="none", label="$c^*$ của từng thang"),
                Patch(color=C()["light_grey"], alpha=0.55,
                      label="Vùng gần tối ưu chung\n(giao 5 vùng đo được):\n{" + compress(common) + "}"),
                Patch(color=C()["blue"], alpha=0.16, label="Dải mờ cùng màu đường:\nCI hai tầng 95%")]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7.2, frameon=False)
    fig.tight_layout()

    src = src_header(name, "[ĐK H1]",
                     [f"{P2_REL}/p2_r_by_cutoff.csv (distribution = random; cột scale, cutoff, r, ci2_lo, ci2_hi)",
                      f"{P2_REL}/p2_best.csv (random; cột c_star, r_star, near_optimal_2pct)"],
                     CI2_TXT,
                     f"""
- Run 5 phiên S1 (results_run5_s1), Integer[], 5 fork, 5 thang, 24 N mỗi thang; r là trung bình nhân trên 24 N.
- Ngôi sao: c* (argmin r theo thang, p2_best). Đường dọc mảnh: c = 7 và c = 10.
- Dải nền xám: GIAO của 5 tập gần tối ưu đo được (r <= 1.02 r(c*), cột near_optimal_2pct) = {{{compress(common)}}}.
  Trên lưới, giữa 32 và 40, giữa 40 và 48 không có CUTOFF nào được đo; dải tô liền từ {lo} đến {hi}.
""")
    mf.save_fig_bundle(fig, out, name, pd.DataFrame(rows), src)
    rule_a(out, name, [
        ("r(c*) thang 2^12", {"scale": "2^12", "is_c_star": True}, "r", best.loc["2^12", "r_star"], "p2_best.r_star"),
        ("r(c*) thang 2^19", {"scale": "2^19", "is_c_star": True}, "r", best.loc["2^19", "r_star"], "p2_best.r_star"),
        ("ci2_lo tại c* thang 2^16", {"scale": "2^16", "is_c_star": True}, "ci2_lo", best.loc["2^16", "ci2_lo"],
         "p2_best.ci2_lo"),
    ])


# ───────────────────────────────────────────────────────────── fig02

def make_fig02(out: Path):
    name = "fig02_m2_confirmation"
    v = pd.read_csv(P2 / "p2_m2_validation.csv")
    sm = pd.read_csv(P2 / "p2_m2_summary.csv").set_index("scale")
    r = pd.read_csv(P2 / "p2_r_by_cutoff.csv")
    r = r[r["distribution"] == "random"]
    fig, axes = plt.subplots(1, 2, figsize=(W170, 3.0), sharey=True)
    rows = []
    for ax, s, tag in zip(axes, ["2^14", "2^18"], ["(a)", "(b)"]):
        vs = v[v["scale"] == s].sort_values("cutoff")
        rs = r[r["scale"] == s].set_index("cutoff").loc[vs["cutoff"]]
        assert np.array_equal(rs["r"].to_numpy(), vs["r_meas"].to_numpy()), "r_meas khác p2_r_by_cutoff"
        cs = vs["cutoff"].to_numpy()
        ax.errorbar(cs, vs["r_meas"], yerr=[vs["r_meas"] - rs["ci2_lo"].to_numpy(), rs["ci2_hi"].to_numpy() - vs["r_meas"]],
                    fmt="o", ms=2.8, color="black", ecolor=C()["grey"], elinewidth=0.8, capsize=0, zorder=4)
        ax.plot(cs, vs["r_hat_interp"], color=C()["blue"], lw=1.3, zorder=3)
        ax.plot(cs, vs["r_hat_calib"], color=C()["vermilion"], lw=1.2, ls="--", zorder=3)
        c_m2 = int(sm.loc[s, "c_star_M2"])
        c_meas = int(sm.loc[s, "c_star_meas"])
        ax.axvline(c_m2, color=C()["blue"], lw=0.8, ls=":")
        ax.axvline(c_meas, color="black", lw=0.8, ls=":")
        ytop = 1.0
        ax.text(c_m2 * 1.04, 0.995, f"$c^*$ M2\n= {c_m2}", fontsize=7, color=C()["blue"], va="top")
        ax.text(c_meas / 1.04, 0.995, f"$c^*$ đo\n= {c_meas}", fontsize=7, color="black", va="top", ha="right")
        ax.text(0.03, 0.04,
                f"{tag} $S$ = {smath(s)}\nRMSE (α nội suy) = {sm.loc[s, 'rmse_interp']:.4f}\n"
                f"RMSE (α hiệu chỉnh) = {sm.loc[s, 'rmse_calib']:.4f}",
                transform=ax.transAxes, fontsize=7.2, va="bottom", ha="left",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#cccccc", lw=0.6))
        log2_axis(ax, [1, 2, 4, 8, 16, 32, 64], lim=(0.92, 70))
        ax.set_xlabel("CUTOFF $c$ (thang log$_2$)")
        for i, row in enumerate(vs.itertuples()):
            rows.append({"scale": s, "cutoff": int(row.cutoff), "r_meas": row.r_meas,
                         "ci2_lo": float(rs["ci2_lo"].iloc[i]), "ci2_hi": float(rs["ci2_hi"].iloc[i]),
                         "r_hat_interp": row.r_hat_interp, "r_hat_calib": row.r_hat_calib})
    axes[0].set_ylabel("$r(c)$ đo và $\\hat r(c)$ dự đoán")
    axes[0].set_ylim(min(r[r["scale"].isin(["2^14", "2^18"])]["ci2_lo"]) - 0.01, 1.005)
    handles = [Line2D([], [], marker="o", ms=3.5, color="black", ls="none", label="$r$ đo (thí nghiệm chính) ± CI hai tầng 95%"),
               Line2D([], [], color=C()["blue"], lw=1.3, label="$\\hat r$ M2 hệ số đóng băng, α nội suy (dự đoán trước khi đo)"),
               Line2D([], [], color=C()["vermilion"], lw=1.2, ls="--", label="$\\hat r$ M2, α hiệu chỉnh từ hàng $c = 1$ của thang")]
    fig.tight_layout()
    legend_below(fig, handles, [h.get_label() for h in handles], ncol=1, y=0.0)

    df = pd.DataFrame(rows)
    rm = {s: math.sqrt(float(np.mean((df[df.scale == s].r_hat_interp - df[df.scale == s].r_meas) ** 2))) for s in ["2^14", "2^18"]}
    src = src_header(name, "[ĐK H10, H10b]",
                     [f"{P2_REL}/p2_m2_validation.csv (cột scale, cutoff, r_meas, r_hat_interp, r_hat_calib)",
                      f"{P2_REL}/p2_m2_summary.csv (rmse_interp, rmse_calib, c_star_M2, c_star_meas)",
                      f"{P2_REL}/p2_r_by_cutoff.csv (random, 2^14 và 2^18; ci2_lo, ci2_hi cho điểm đo)",
                      f"{PR_REL}/T09_predictions_m2.csv (dự đoán đã commit trước khi đo; p2_m2_validation chép lại)"],
                     "Thanh dọc của điểm đo: " + CI2_TXT + ". Đường M2 không có dải (dự đoán điểm).",
                     f"""
- Hai thang MỚI của giai đoạn xác nhận (2^14, 2^18). Hệ số M2 đóng băng từ giai đoạn khám phá; α nội suy theo k = lg S
  (α14 = {sm.loc['2^14', 'alpha_interp']:.6f}, α18 = {sm.loc['2^18', 'alpha_interp']:.6f}).
- Đường dọc chấm: c*_M2 (argmin r̂ nội suy) và c* đo (p2_best).
- RMSE tính trên 35 CUTOFF (kể cả c = 1, sai số 0); tính lại từ .data.csv: 2^14 = {rm['2^14']:.10g}, 2^18 = {rm['2^18']:.10g}.
""")
    mf.save_fig_bundle(fig, out, name, df, src)
    rule_a(out, name, [
        ("r̂ nội suy tại 2^14, c = 40", {"scale": "2^14", "cutoff": 40}, "r_hat_interp",
         v[(v.scale == "2^14") & (v.cutoff == 40)].r_hat_interp.iloc[0], "p2_m2_validation.r_hat_interp"),
        ("r đo tại 2^18, c = 31", {"scale": "2^18", "cutoff": 31}, "r_meas",
         sm.loc["2^18"].pipe(lambda _: r[(r.scale == "2^18") & (r.cutoff == 31)].r.iloc[0]), "p2_r_by_cutoff.r"),
    ])
    # RMSE: số tính lại từ .data.csv cạnh số trong bảng (dung sai làm tròn dấu phẩy động 1e-12)
    for s in ["2^14", "2^18"]:
        print(f"    - RMSE nội suy {s}: hình = {rm[s]:.12g} | bảng (p2_m2_summary.rmse_interp) = "
              f"{sm.loc[s, 'rmse_interp']:.12g} | chênh = {rm[s] - sm.loc[s, 'rmse_interp']:.3g}")
        assert abs(rm[s] - sm.loc[s, "rmse_interp"]) < 1e-12


# ───────────────────────────────────────────────────────────── fig04

def make_fig04(out: Path):
    name = "fig04_doubling_v2"
    R = pd.read_csv(P2 / "p2_doubling_R.csv")
    pred = pd.read_csv(PR / "T09_predictions_doubling_v2.csv")
    h11 = pd.read_csv(P2 / "p2_H11.csv")
    h12 = pd.read_csv(P2 / "p2_H12.csv")
    fig, axes = plt.subplots(1, 2, figsize=(W170, 3.1), sharey=True)
    rows = []
    for ax, c, tag in zip(axes, [1, 30], ["(a) $c = 1$", "(b) $c = 30$"]):
        sub = R[(R["cutoff"] == c) & (R["k_from"].between(10, 23))].sort_values("k_from")
        k = sub["k_from"].to_numpy()
        for i, f in enumerate(range(1, 6)):
            ax.plot(k + (i - 2) * 0.07, np.log(sub[f"R_fork{f}"]), ls="none", marker="o", ms=2.2,
                    color=C()["grey"], alpha=0.45, zorder=2)
        ax.errorbar(k, sub["ln_R_bar"], yerr=3 * sub["SE_k"], fmt="o", ms=3.8, color=C()["blue"],
                    elinewidth=1.0, capsize=2, zorder=5)
        p = pred[pred["cutoff"] == c].sort_values("k")
        v1 = p.dropna(subset=["lnR_v1"])
        ax.plot(v1["k"] + 0.28, v1["lnR_v1"], ls="none", marker="o", ms=4, mfc="none", mec=C()["vermilion"],
                mew=1.0, zorder=4)
        ax.plot(p["k"], p["lnR_P_baohoa"], color=C()["bluish_green"], ls="--", lw=1.2, zorder=3)
        for kk in (22, 23):
            pt = float(p[p["k"] == kk]["lnR_P_tiep"].iloc[0])
            ax.hlines(pt, kk - 0.38, kk + 0.38, color=C()["orange"], lw=1.6, alpha=0.85, zorder=3)
        ax.axvspan(21.5, 23.5, color=C()["yellow"], alpha=0.12, lw=0, zorder=0)
        ax.text(0.03, 0.96, tag, transform=ax.transAxes, fontsize=8, va="top")
        ax.set_xticks(range(10, 24))
        ax.set_xlim(9.5, 23.6)
        ax.set_xlabel("$k$ (bước $N = 2^k \\rightarrow 2^{k+1}$)")
        for row in sub.itertuples():
            pr_row = p[p["k"] == row.k_from].iloc[0]
            d = {"cutoff": c, "k": int(row.k_from), "ln_R_bar_v2": row.ln_R_bar, "SE_k": row.SE_k,
                 "err_3SE": 3 * row.SE_k}
            for f in range(1, 6):
                d[f"ln_R_fork{f}"] = math.log(getattr(row, f"R_fork{f}"))
            d["ln_R_v1"] = pr_row["lnR_v1"]
            d["lnR_P_baohoa"] = pr_row["lnR_P_baohoa"]
            d["lnR_P_tiep"] = pr_row["lnR_P_tiep"] if row.k_from in (22, 23) else np.nan
            rows.append(d)
    axes[0].set_ylabel("$\\ln R_k$,  $R_k = T(2^{k+1})/T(2^k)$")
    handles = [Line2D([], [], marker="o", ms=3.8, color=C()["blue"], ls="-", lw=1.0,
                      label="Chính: trung bình 5 fork $\\pm 3\\,\\mathrm{SE}_k$"),
               Line2D([], [], marker="o", ms=2.5, color=C()["grey"], alpha=0.6, ls="none", label="Chính: từng fork"),
               Line2D([], [], marker="o", ms=4, mfc="none", mec=C()["vermilion"], ls="none",
                      label="Sơ bộ (3 fork), $k$ = 10..21"),
               Line2D([], [], color=C()["bluish_green"], ls="--", lw=1.2,
                      label="P-bão hòa: $\\ln(2(k+1)/k)$ (tăng như $N \\lg N$)"),
               Line2D([], [], color=C()["orange"], lw=1.6, label="P-tiếp: $b \\ln 2$ (chỉ dự đoán ở $k$ = 22, 23)"),
               Patch(color=C()["yellow"], alpha=0.25, label="Hai bước ngoại suy ($k$ = 22, 23)")]
    fig.tight_layout()
    legend_below(fig, handles, [h.get_label() for h in handles], ncol=2, y=0.0)
    src = src_header(name, "[ĐK H11, H12]",
                     [f"{P2_REL}/p2_doubling_R.csv (cutoff 1 và 30, k_from 10..23; cột R_fork1..5, ln_R_bar, SE_k)",
                      f"{PR_REL}/T09_predictions_doubling_v2.csv (lnR_v1, lnR_P_baohoa, lnR_P_tiep; commit trước khi đo)",
                      f"{P2_REL}/p2_H11.csv, p2_H12.csv (chỉ để đối chiếu Quy tắc A)"],
                     "±3·SE_k, SE_k = SD giữa 5 fork của ln R_k / √5 (cột SE_k) = ngưỡng của H12 theo hợp đồng §3. "
                     "Điểm v1 không có thanh (SE_v1 có trong PR, không vẽ để khỏi rối).",
                     """
- R_k = T(2^{k+1})/T(2^k), T là thời gian một lần sắp (doubling v2, results_doubling_v2, 5 fork, Integer[]).
- ln_R_bar = trung bình ln R trên 5 fork; điểm xám là ln R của từng fork (lệch ngang nhẹ để thấy rõ).
- P-bão hòa vẽ trên toàn dải (đường đứt); P-tiếp chỉ vẽ ở k = 22, 23 (đoạn ngắn) vì hợp đồng chỉ đăng ký ở đó;
  b = 1.202 (c = 1), 1.213 (c = 30). H11 so v2 với v1 ở k = 19, 20, 21.
""")
    mf.save_fig_bundle(fig, out, name, pd.DataFrame(rows), src)
    h12r = h12[(h12.predictor == "P_tiep") & (h12.k_from == 22) & (h12.cutoff == 1)].iloc[0]
    h11r = h11[(h11.k_from == 19) & (h11.cutoff == 30)].iloc[0]
    rule_a(out, name, [
        ("ln R̄ v2, c = 1, k = 22", {"cutoff": 1, "k": 22}, "ln_R_bar_v2", h12r.ln_R_v2, "p2_H12.ln_R_v2"),
        ("SE_k v2, c = 1, k = 22", {"cutoff": 1, "k": 22}, "SE_k", h12r.SE_v2, "p2_H12.SE_v2"),
        ("ln R̄ v1, c = 30, k = 19", {"cutoff": 30, "k": 19}, "ln_R_v1", h11r.ln_R_v1, "p2_H11.ln_R_v1"),
        ("ln R̄ v2, c = 30, k = 19", {"cutoff": 30, "k": 19}, "ln_R_bar_v2", h11r.ln_R_v2, "p2_H11.ln_R_v2"),
    ])


# ───────────────────────────────────────────────────────────── fig05

def make_fig05(out: Path):
    name = "fig05_t_over_nlgn_v2"
    t = pd.read_csv(P2 / "p2_doubling_T_over_NlgN.csv")
    # Dữ liệu hoạt động theo mô hình bộ nhớ T05 (JVM mặc định): 24N + 32 byte
    k_l2 = math.log2((2 ** 20 - 32) / 24)
    k_l3 = math.log2((2 ** 24 - 32) / 24)
    fig, ax = plt.subplots(figsize=(W120, 3.0))
    rows = []
    for c, col, ls, mk, lab in [(1, C()["blue"], "-", "o", "$c = 1$"), (30, C()["orange"], "--", "s", "$c = 30$")]:
        sub = t[t["cutoff"] == c].sort_values("k")
        ax.plot(sub["k"], sub["T_over_NlgN_ns"], color=col, ls=ls, marker=mk, ms=3.5, label=lab)
        for row in sub.itertuples():
            rows.append({"cutoff": c, "k": int(row.k), "N": int(row.N), "T_ns": row.T_ns,
                         "T_over_NlgN_ns": row.T_over_NlgN_ns})
    for kv, txt in [(k_l2, "$24N + 32$ B\n= 1 MiB (L2)"), (k_l3, "$24N + 32$ B\n= 16 MiB (L3)")]:
        ax.axvline(kv, color=C()["grey"], lw=0.8, ls=":")
        ax.text(kv + 0.12, 0.97, txt, transform=ax.get_xaxis_transform(), fontsize=7, color=C()["grey"],
                va="top", ha="left")
    ax.set_xticks(range(10, 25))
    ax.set_xlim(9.6, 24.4)
    ax.set_xlabel("$k = \\lg N$")
    ax.set_ylabel("$T/(N \\lg N)$ (ns)")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 0.88), fontsize=7.5)
    fig.tight_layout()
    df = pd.DataFrame(rows)
    df_lines = pd.DataFrame([{"marker": "L2_1MiB", "k_line": k_l2}, {"marker": "L3_16MiB", "k_line": k_l3}])
    df = pd.concat([df, df_lines], ignore_index=True)
    src = src_header(name, "[MT]",
                     [f"{P2_REL}/p2_doubling_T_over_NlgN.csv (cột k, N, cutoff, T_ns, T_over_NlgN_ns; T là trung bình nhân qua 5 fork)"],
                     "Không có (bảng nguồn không có CI; hình mô tả).",
                     f"""
- Doubling v2 (results_doubling_v2), Integer[], k = 10..24, c = 1 và c = 30.
- Đường dọc: N tại đó dữ liệu hoạt động 24N + 32 byte (a + aux + N đối tượng Integer, JVM mặc định; mô hình T05,
  khớp từng byte với JOL) bằng 1 MiB (L2 mỗi nhân) và 16 MiB (L3), CPU theo results_doubling/cpu_info.txt.
  Tính bằng công thức: k = lg((2^20 - 32)/24) = {k_l2:.4f}; k = lg((2^24 - 32)/24) = {k_l3:.4f}.
- Hình chỉ mô tả; không gán nguyên nhân cho các bước tăng.
""")
    mf.save_fig_bundle(fig, out, name, df, src)
    rule_a(out, name, [
        ("T/(N lg N), c = 1, k = 24", {"cutoff": 1, "k": 24}, "T_over_NlgN_ns",
         t[(t.cutoff == 1) & (t.k == 24)].T_over_NlgN_ns.iloc[0], "p2_doubling_T_over_NlgN"),
        ("T/(N lg N), c = 30, k = 10", {"cutoff": 30, "k": 10}, "T_over_NlgN_ns",
         t[(t.cutoff == 30) & (t.k == 10)].T_over_NlgN_ns.iloc[0], "p2_doubling_T_over_NlgN"),
    ])


# ───────────────────────────────────────────────────────────── fig06

def make_fig06(out: Path):
    name = "fig06_r30_doubling_v2"
    t = pd.read_csv(P2 / "p2_doubling_r30.csv").sort_values("k")
    fig, ax = plt.subplots(figsize=(W120, 2.9))
    ax.errorbar(t["k"], t["r30"], yerr=[t["r30"] - t["ci_fork_lo"], t["ci_fork_hi"] - t["r30"]], fmt="o-",
                ms=3.5, color=C()["blue"], lw=1.1, elinewidth=0.9, capsize=2)
    for y, ls, txt in [(0.80, "--", "$r = 0.80$ (giảm 20%)"), (1 / 1.2, ":", "$r = 0.833$ (nhanh hơn 1.2×)")]:
        ax.axhline(y, color=C()["vermilion"], lw=0.9, ls=ls)
        ax.text(24.3, y + 0.002, txt, fontsize=7, color=C()["vermilion"], ha="right", va="bottom")
    ax.text(0.02, 0.97, "Hai cách đọc “khoảng 20%”: hai đường ngang.\nỞ $N = 2^k$, $c = 30$ cho lá dài 16.",
            transform=ax.transAxes, fontsize=7, va="top")
    ax.set_xticks(range(10, 25))
    ax.set_xlim(9.6, 24.4)
    ax.set_ylim(0.785, max(t["ci_fork_hi"]) + 0.012)
    ax.set_xlabel("$k = \\lg N$")
    ax.set_ylabel("$r(2^k, 30) = T(30)/T(1)$")
    fig.tight_layout()
    df = t[["k", "N", "r30", "ci_fork_lo", "ci_fork_hi", "n_forks"]].copy()
    src = src_header(name, "[MT]",
                     [f"{P2_REL}/p2_doubling_r30.csv (cột k, N, r30, ci_fork_lo, ci_fork_hi)"],
                     "CI 95% bootstrap chỉ rút fork (5 fork, cột ci_fork_lo/ci_fork_hi; seed ghi trong run_log của T10).",
                     """
- r(2^k, 30) = trung bình nhân qua 5 fork của T(30)/T(1), doubling v2 (results_doubling_v2), Integer[].
- Ở N = 2^k, c = 30 cho lá dài 16 (cùng cây đệ quy với mọi c trong [16, 31]).
- Hai đường ngang: hai cách đọc "khoảng 20%" (r = 0.80 và r = 1/1.2 = 0.833).
""")
    mf.save_fig_bundle(fig, out, name, df, src)
    rule_a(out, name, [
        ("r30 tại k = 10", {"k": 10}, "r30", t[t.k == 10].r30.iloc[0], "p2_doubling_r30.r30"),
        ("r30 tại k = 24", {"k": 24}, "r30", t[t.k == 24].r30.iloc[0], "p2_doubling_r30.r30"),
        ("ci_fork_hi tại k = 24", {"k": 24}, "ci_fork_hi", t[t.k == 24].ci_fork_hi.iloc[0], "p2_doubling_r30.ci_fork_hi"),
    ])


# ───────────────────────────────────────────────────────────── fig08

PRED_BANDS = {  # từ preregistration/T09_hypotheses.csv (cột decision_rule)
    "reversed": ("H6", 6, 16),
    "few_distinct": ("H7", 17, 48),
    "nearly_sorted": ("H9", 128, 1024),
    "sorted": ("H8", 4096, 4096),
}
LABEL_POS = {"sorted": (0.97, 0.96, "right"), "nearly_sorted": (0.03, 0.96, "left"),
             "reversed": (0.03, 0.96, "left"), "few_distinct": (0.30, 0.96, "left")}
DIST_VI = {"sorted": "sorted (đã sắp)", "nearly_sorted": "nearly_sorted (gần sắp)",
           "reversed": "reversed (đảo ngược)", "few_distinct": "few_distinct (10 giá trị)"}


def make_fig08(out: Path):
    name = "fig08_other_distributions"
    r = pd.read_csv(P2 / "p2_r_by_cutoff.csv")
    best = pd.read_csv(P2 / "p2_best.csv").set_index(["distribution", "scale"])
    hyp = pd.read_csv(PR / "T09_hypotheses.csv").set_index("id")
    for d, (hid, a, b) in PRED_BANDS.items():
        print(f"    {hid} ({d}): khoảng vẽ [{a}, {b}] | luật PR: {hyp.loc[hid, 'threshold']}")
    sty = {"2^12": scale_styles()["2^12"], "2^16": scale_styles()["2^16"], "2^19": scale_styles()["2^19"]}
    fig, axes = plt.subplots(2, 2, figsize=(W170, 4.7))
    rows = []
    order = ["sorted", "nearly_sorted", "reversed", "few_distinct"]
    for ax, d, tag in zip(axes.ravel(), order, ["(a)", "(b)", "(c)", "(d)"]):
        hid, a, b = PRED_BANDS[d]
        if a == b:
            ax.axvline(a, color=C()["yellow"], lw=5, alpha=0.6, zorder=0)
        else:
            ax.axvspan(a, b, color=C()["yellow"], alpha=0.25, lw=0, zorder=0)
        for s in SCALES3:
            col, ls, mk = sty[s]
            sub = r[(r["distribution"] == d) & (r["scale"] == s)].sort_values("cutoff")
            ax.fill_between(sub["cutoff"], sub["ci2_lo"], sub["ci2_hi"], color=col, alpha=0.18, lw=0)
            ax.plot(sub["cutoff"], sub["r"], color=col, ls=ls, marker=mk, ms=2.1, lw=1.0)
            cs, rs = int(best.loc[(d, s), "c_star"]), float(best.loc[(d, s), "r_star"])
            ax.plot([cs], [rs], marker="*", ms=9, mfc=col, mec="black", mew=0.6, ls="none", zorder=6)
            for row in sub.itertuples():
                rows.append({"distribution": d, "scale": s, "cutoff": int(row.cutoff), "r": row.r,
                             "ci2_lo": row.ci2_lo, "ci2_hi": row.ci2_hi, "is_c_star": int(row.cutoff) == cs,
                             "pred_lo": a, "pred_hi": b, "hypothesis": hid})
        gmax = int(r[r["distribution"] == d]["cutoff"].max())
        ticks = [1, 4, 16, 64, 256, 1024, 4096] if gmax == 4096 else [1, 2, 4, 8, 16, 32, 64, 128]
        log2_axis(ax, ticks, lim=(0.85, gmax * 1.18))
        lx, ly, lha = LABEL_POS[d]
        ax.text(lx, ly, f"{tag} {DIST_VI[d]}", transform=ax.transAxes, fontsize=7.5, va="top", ha=lha)
        if d == "reversed":
            # Ô phóng to vùng c <= 32 (cùng dữ liệu, không thêm điểm): vùng đáy bị nén vì r(128) > 2
            ins = ax.inset_axes([0.09, 0.30, 0.50, 0.52])
            ins.axvspan(a, b, color=C()["yellow"], alpha=0.25, lw=0, zorder=0)
            for s in SCALES3:
                col, ls, mk = sty[s]
                sub = r[(r["distribution"] == d) & (r["scale"] == s) & (r["cutoff"] <= 32)].sort_values("cutoff")
                ins.fill_between(sub["cutoff"], sub["ci2_lo"], sub["ci2_hi"], color=col, alpha=0.18, lw=0)
                ins.plot(sub["cutoff"], sub["r"], color=col, ls=ls, lw=0.9)
                cs, rs = int(best.loc[(d, s), "c_star"]), float(best.loc[(d, s), "r_star"])
                ins.plot([cs], [rs], marker="*", ms=7, mfc=col, mec="black", mew=0.5, ls="none", zorder=6)
            log2_axis(ins, [1, 2, 4, 8, 16, 32], lim=(0.9, 36))
            ins.tick_params(labelsize=6, length=2, pad=1)
            ins.text(0.5, 1.02, "phóng to $c \\leq 32$", transform=ins.transAxes, fontsize=6.5, ha="center", va="bottom")
        ax.set_xlabel("CUTOFF $c$ (thang log$_2$)", fontsize=8)
    axes[0, 0].set_ylabel("$r(c) = T(c)/T(1)$")
    axes[1, 0].set_ylabel("$r(c) = T(c)/T(1)$")
    # panel sorted: nhãn dải ở góc phải trên
    handles = [Line2D([], [], color=sty[s][0], ls=sty[s][1], marker=sty[s][2], ms=3.5, label=f"$S$ = {smath(s)}")
               for s in SCALES3]
    handles += [Line2D([], [], marker="*", ms=9, mfc="white", mec="black", ls="none", label="$c^*$ đo"),
                Patch(color=C()["yellow"], alpha=0.35,
                      label="Dự đoán ghi trước: (a) $c^*$ = 4096, (b) [128, 1024], (c) [6, 16], (d) [17, 48]"),
                Patch(color=C()["grey"], alpha=0.2, label="CI hai tầng 95%")]
    fig.tight_layout()
    legend_below(fig, handles[:4] + [handles[5]], [h.get_label() for h in handles[:4]] + [handles[5].get_label()], ncol=5, y=0.0)
    fig.legend([handles[4]], [handles[4].get_label()], loc="upper center", bbox_to_anchor=(0.5, -0.045),
               fontsize=7.5, frameon=False)
    src = src_header(name, "[ĐK H6, H7, H8, H9]",
                     [f"{P2_REL}/p2_r_by_cutoff.csv (sorted, nearly_sorted, reversed, few_distinct; r, ci2_lo, ci2_hi)",
                      f"{P2_REL}/p2_best.csv (c_star, r_star)",
                      f"{PR_REL}/T09_hypotheses.csv (khoảng dự đoán H6–H9, cột decision_rule/threshold)"],
                     CI2_TXT,
                     """
- Run 5 phiên S2 (results_run5_s2), Integer[], 5 fork, 3 thang, 24 N mỗi thang; lưới: sorted và nearly_sorted tới 4096,
  reversed và few_distinct tới 128.
- Nền vàng: khoảng (hoặc điểm, với sorted) dự đoán ĐĂNG KÝ TRƯỚC cho c*; ngôi sao: c* đo (p2_best).
- Trục y khác nhau giữa các panel (mức r khác nhau nhiều giữa các phân bố).
- Panel (c) có ô phóng to vùng c <= 32 (cùng dữ liệu với panel, không thêm điểm) vì r(128) > 2 làm nén vùng đáy.
""")
    mf.save_fig_bundle(fig, out, name, pd.DataFrame(rows), src)
    rule_a(out, name, [
        ("r(c*) reversed 2^16", {"distribution": "reversed", "scale": "2^16", "is_c_star": True}, "r",
         best.loc[("reversed", "2^16"), "r_star"], "p2_best.r_star"),
        ("r(c*) nearly_sorted 2^19", {"distribution": "nearly_sorted", "scale": "2^19", "is_c_star": True}, "r",
         best.loc[("nearly_sorted", "2^19"), "r_star"], "p2_best.r_star"),
        ("r(c*) sorted 2^12", {"distribution": "sorted", "scale": "2^12", "is_c_star": True}, "r",
         best.loc[("sorted", "2^12"), "r_star"], "p2_best.r_star"),
    ])


# ───────────────────────────────────────────────────────────── fig09

def make_fig09(out: Path):
    name = "fig09_key_types"
    d3 = pd.read_csv(P2 / "p2_d3_r_by_cutoff.csv")
    d3b = pd.read_csv(P2 / "p2_d3_best.csv").set_index(["key", "scale"])
    s7 = pd.read_csv(P2B / "p2b_int_r_by_cutoff.csv")
    s7b = pd.read_csv(P2B / "p2b_int_best.csv").set_index("scale")
    series = [
        ("integer", "Integer[] (3 fork)", C()["blue"], "-", "o"),
        ("double", "Double[] (3 fork)", C()["orange"], "-.", "s"),
        ("int", "int[] (3 fork)", C()["bluish_green"], "-", "^"),
        ("int_S7", "int[] (mở rộng, 6 fork)", C()["vermilion"], "--", "D"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(W170, 3.0), sharey=True)
    rows = []
    for ax, s, tag in zip(axes, SCALES3, ["(a)", "(b)", "(c)"]):
        for key, lab, col, ls, mk in series:
            if key == "int_S7":
                sub = s7[s7["scale"] == s].sort_values("cutoff")
                cs, rs = int(s7b.loc[s, "c_star"]), float(s7b.loc[s, "r_star"])
            else:
                sub = d3[(d3["key"] == key) & (d3["scale"] == s)].sort_values("cutoff")
                cs, rs = int(d3b.loc[(key, s), "c_star"]), float(d3b.loc[(key, s), "r_star"])
            ax.fill_between(sub["cutoff"], sub["ci2_lo"], sub["ci2_hi"], color=col, alpha=0.14, lw=0)
            ax.plot(sub["cutoff"], sub["r"], color=col, ls=ls, lw=1.1, marker=mk, ms=1.8)
            ax.plot([cs], [rs], marker="*", ms=9, mfc=col, mec="black", mew=0.6, ls="none", zorder=6)
            for row in sub.itertuples():
                rows.append({"series": key, "scale": s, "cutoff": int(row.cutoff), "r": row.r,
                             "ci2_lo": row.ci2_lo, "ci2_hi": row.ci2_hi, "is_c_star": int(row.cutoff) == cs})
        for y, ls in [(1 / 1.2, ":"), (0.80, "--")]:
            ax.axhline(y, color=C()["grey"], lw=0.8, ls=ls)
        log2_axis(ax, [1, 4, 16, 64, 256], lim=(0.85, 300))
        ax.text(0.04, 0.04, f"{tag} $S$ = {smath(s)}", transform=ax.transAxes, fontsize=7.5)
        ax.set_xlabel("CUTOFF $c$ (thang log$_2$)")
    axes[0].set_ylabel("$r(c) = T(c)/T(1)$")
    handles = [Line2D([], [], color=col, ls=ls, marker=mk, ms=3, label=lab) for _, lab, col, ls, mk in series]
    handles += [Line2D([], [], marker="*", ms=9, mfc="white", mec="black", ls="none", label="$c^*$ của từng đường"),
                Line2D([], [], color=C()["grey"], ls=":", label="$r = 0.833$ (1.2×)"),
                Line2D([], [], color=C()["grey"], ls="--", label="$r = 0.80$ (giảm 20%)"),
                Patch(color=C()["grey"], alpha=0.2, label="CI hai tầng 95%")]
    fig.tight_layout()
    legend_below(fig, handles, [h.get_label() for h in handles], ncol=4, y=0.0)
    src = src_header(name, "[ĐK H14, H15, H16, I1, I2, I3]",
                     [f"{P2_REL}/p2_d3_r_by_cutoff.csv (key integer/double/int; r, ci2_lo, ci2_hi; lưới 37 CUTOFF tới 128)",
                      f"{P2_REL}/p2_d3_best.csv (c_star, r_star theo key)",
                      f"{P2B_REL}/p2b_int_r_by_cutoff.csv (S7 int_ext, 6 fork, lưới 43 CUTOFF tới 256)",
                      f"{P2B_REL}/p2b_int_best.csv (c_star, r_star của S7)"],
                     CI2_TXT,
                     """
- D3 (results_d3): cùng dữ liệu Run 5 cho 3 kiểu khóa, 3 fork mỗi kiểu, cùng phiên. S7 (results_int_ext): int[], 6 fork, phiên riêng.
- Hai đường ngang xám: r = 0.833 và r = 0.80 (hai cách đọc "khoảng 20%").
- Ngôi sao: c* của từng đường (p2_d3_best, p2b_int_best). Hình chỉ trình bày số; không gán cơ chế.
""")
    mf.save_fig_bundle(fig, out, name, pd.DataFrame(rows), src)
    rule_a(out, name, [
        ("r(c*) int[] S7, 2^12", {"series": "int_S7", "scale": "2^12", "is_c_star": True}, "r",
         s7b.loc["2^12", "r_star"], "p2b_int_best.r_star"),
        ("r(c*) Integer[] D3, 2^19", {"series": "integer", "scale": "2^19", "is_c_star": True}, "r",
         d3b.loc[("integer", "2^19"), "r_star"], "p2_d3_best.r_star"),
        ("ci2_hi int[] S7 tại c*, 2^16", {"series": "int_S7", "scale": "2^16", "is_c_star": True}, "ci2_hi",
         s7b.loc["2^16", "ci2_hi"], "p2b_int_best.ci2_hi"),
    ])


# ───────────────────────────────────────────────────────────── fig10

JMH_CONFIGS = [("same", "pure", "none"), ("fresh", "pure", "none"), ("same", "mixed", "none"),
               ("fresh", "mixed", "none"), ("same", "mixed", "gc"), ("fresh", "mixed", "gc")]


def _cfg_label(cfg):
    return "\n".join(cfg)


def make_fig10(out: Path):
    name = "fig10_jmh_vs_harness"
    sc = pd.read_csv(P2B / "p2b_jmh_scores.csv")
    rr = pd.read_csv(P2B / "p2b_jmh_r.csv")
    absr = pd.read_csv(P2B / "p2b_jmh_abs_vs_run5.csv").set_index(["N", "cutoff"])
    t08 = pd.read_csv(P2 / "p2_jmh.csv").set_index(["N", "cutoff"])
    cuts = [1, 7, 10, 30]
    cut_sty = {1: (C()["black"], "o"), 7: (C()["blue"], "s"), 10: (C()["orange"], "^"), 30: (C()["bluish_green"], "D")}
    labels_ab = ["JMH\nban đầu"] + [_cfg_label(c) for c in JMH_CONFIGS] + ["Thí nghiệm\nchính"]
    fig = plt.figure(figsize=(W170, 6.3))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.0], hspace=0.62, wspace=0.22)
    axa, axb = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    axc = fig.add_subplot(gs[1, :])
    rows = []
    for ax, N, tag in [(axa, 4096, "(a) $N$ = 4096"), (axb, 524288, "(b) $N$ = 524 288")]:
        for j, c in enumerate(cuts):
            col, mk = cut_sty[c]
            dx = (j - 1.5) * 0.17
            # T08: Score Error 99.9% của JMH (không phải CI bootstrap) -> thanh chấm, điểm rỗng
            row = t08.loc[(N, c)]
            ax.errorbar([0 + dx], [row.jmh_score_us], yerr=[row.jmh_score_err_999_us], fmt=mk, ms=3.4, mfc="white",
                        mec=col, ecolor=col, elinewidth=0.8, capsize=1.5, ls="none")
            rows.append({"panel": "ab", "config": "T08", "N": N, "cutoff": c, "value_us": row.jmh_score_us,
                         "err_lo": row.jmh_score_us - row.jmh_score_err_999_us,
                         "err_hi": row.jmh_score_us + row.jmh_score_err_999_us, "err_kind": "JMH Score Error 99.9%"})
            for i, cfg in enumerate(JMH_CONFIGS, start=1):
                q = sc[(sc["input"] == cfg[0]) & (sc["profile"] == cfg[1]) & (sc["reset"] == cfg[2]) &
                       (sc["N"] == N) & (sc["cutoff"] == c)].iloc[0]
                ax.errorbar([i + dx], [q.score_us], yerr=[[q.score_us - q.ci_lo], [q.ci_hi - q.score_us]], fmt=mk,
                            ms=3.4, color=col, elinewidth=0.9, capsize=1.5, ls="none")
                rows.append({"panel": "ab", "config": "+".join(cfg), "N": N, "cutoff": c, "value_us": q.score_us,
                             "err_lo": q.ci_lo, "err_hi": q.ci_hi, "err_kind": "CI 95% bootstrap theo fork"})
            v5 = float(absr.loc[(N, c), "run5_geom_time_us"])
            ax.plot([7 + dx], [v5], marker=mk, ms=3.6, mfc=C()["light_grey"], mec=col, ls="none")
            rows.append({"panel": "ab", "config": "Run5", "N": N, "cutoff": c, "value_us": v5,
                         "err_lo": np.nan, "err_hi": np.nan, "err_kind": "không (trung bình nhân, khác phiên)"})
        ax.axvspan(6.5, 7.5, color=C()["light_grey"], alpha=0.35, lw=0, zorder=0)
        ax.axvline(0.5, color="#bbbbbb", lw=0.6)
        ax.set_xticks(range(8))
        ax.set_xticklabels(labels_ab, fontsize=6.3)
        ax.set_xlim(-0.6, 7.6)
        ax.text(0.0, 1.03, tag, transform=ax.transAxes, fontsize=8, ha="left", va="bottom")  # nhãn panel
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", " ")))
    axa.set_ylabel("Thời gian một lần sắp (µs)")
    # (c) r(N, 30)
    nsty = {4096: (C()["blue"], "o"), 65536: (C()["orange"], "s"), 524288: (C()["bluish_green"], "^")}
    for n_i, N in enumerate([4096, 65536, 524288]):
        col, mk = nsty[N]
        dx = (n_i - 1) * 0.2
        r08 = float(t08.loc[(N, 30), "r_jmh"])
        axc.plot([0 + dx], [r08], marker=mk, ms=4, mfc="white", mec=col, ls="none")
        rows.append({"panel": "c", "config": "T08", "N": N, "cutoff": 30, "value_r": r08,
                     "err_lo": np.nan, "err_hi": np.nan, "err_kind": "không có CI (T08 chỉ có Score Error)"})
        for i, cfg in enumerate(JMH_CONFIGS, start=1):
            q = rr[(rr["input"] == cfg[0]) & (rr["profile"] == cfg[1]) & (rr["reset"] == cfg[2]) &
                   (rr["N"] == N) & (rr["cutoff"] == 30)].iloc[0]
            axc.errorbar([i + dx], [q.r], yerr=[[q.r - q.ci_lo], [q.ci_hi - q.r]], fmt=mk, ms=4, color=col,
                         elinewidth=0.9, capsize=1.5, ls="none")
            rows.append({"panel": "c", "config": "+".join(cfg), "N": N, "cutoff": 30, "value_r": q.r,
                         "err_lo": q.ci_lo, "err_hi": q.ci_hi, "err_kind": "CI 95% bootstrap theo fork"})
        r5 = float(t08.loc[(N, 30), "r_run5"])
        axc.axhline(r5, color=col, lw=0.9, ls="--", zorder=1)
        rows.append({"panel": "c", "config": "Run5_line", "N": N, "cutoff": 30, "value_r": r5,
                     "err_lo": np.nan, "err_hi": np.nan, "err_kind": "đường ngang r_Run5(N, 30)"})
    axc.axvline(0.5, color="#bbbbbb", lw=0.6)
    axc.set_xticks(range(7))
    axc.set_xticklabels(labels_ab[:7], fontsize=6.8)
    axc.set_xlim(-0.6, 6.6)
    axc.set_ylabel("$r(N, 30) = T(30)/T(1)$")
    axc.text(0.0, 1.03, "(c) $r(N, 30)$", transform=axc.transAxes, fontsize=8, ha="left", va="bottom")
    h_ab = [Line2D([], [], color=cut_sty[c][0], marker=cut_sty[c][1], ls="none", ms=4, label=f"$c = {c}$") for c in cuts]
    h_ab += [Line2D([], [], color="black", marker="o", mfc="white", ls="none", ms=4,
                    label="JMH ban đầu: thanh = Score Error 99.9% của JMH"),
             Line2D([], [], color="black", marker="o", mfc=C()["light_grey"], ls="none", ms=4,
                    label="Thí nghiệm chính: trung bình nhân, không thanh")]
    fig.legend(h_ab, [h.get_label() for h in h_ab], loc="upper center", bbox_to_anchor=(0.5, 0.515), ncol=6,
               fontsize=6.8, frameon=False, columnspacing=1.0, handletextpad=0.3)
    h_c = [Line2D([], [], color=nsty[N][0], marker=nsty[N][1], ls="none", ms=4, label=f"$N$ = {N}") for N in nsty]
    h_c += [Line2D([], [], color="black", marker="o", mfc="white", ls="none", ms=4, label="JMH ban đầu (không có CI)"),
            Line2D([], [], color="black", marker="o", ls="none", ms=4, label="JMH yếu tố đầy đủ ± CI 95% bootstrap theo fork"),
            Line2D([], [], color="black", ls="--", lw=0.9, label="$r$ của thí nghiệm chính cùng $N$")]
    fig.legend(h_c, [h.get_label() for h in h_c], loc="upper center", bbox_to_anchor=(0.5, 0.035), ncol=3,
               fontsize=6.8, frameon=False, columnspacing=1.0, handletextpad=0.3)
    df = pd.DataFrame(rows)
    src = src_header(name, "[ĐK J1–J7] (và H17 cho cột T08)",
                     [f"{P2B_REL}/p2b_jmh_scores.csv (input, profile, reset, N, cutoff, score_us, ci_lo, ci_hi)",
                      f"{P2B_REL}/p2b_jmh_r.csv (r, ci_lo, ci_hi; panel c, cutoff = 30)",
                      f"{P2B_REL}/p2b_jmh_abs_vs_run5.csv (run5_geom_time_us)",
                      f"{P2_REL}/p2_jmh.csv (T08: jmh_score_us, jmh_score_err_999_us, r_jmh, r_run5)"],
                     "JMH yếu tố đầy đủ (6 cấu hình): CI 95% bootstrap theo fork (3 fork) từ bảng P2B. T08: KHÔNG có CI bootstrap; "
                     "thanh chấm rỗng là Score Error (99.9%) do JMH báo, vẽ khác kiểu. Run 5: không có thanh.",
                     """
- Cấu hình JMH yếu tố đầy đủ ghi theo thứ tự input + profile + reset (same/fresh × pure/mixed × none/gc).
- Run 5 là bộ đo tự viết (trung bình nhân trên các lần đo của đúng N đó, phiên S1), KHÁC phiên với JMH:
  chỉ để mô tả mức tuyệt đối; JMH là trung bình cộng.
- Panel (c): đường ngang đứt = r_Run5(N, 30) của đúng N đó (p2_jmh.r_run5).
""")
    mf.save_fig_bundle(fig, out, name, df, src)
    q = sc[(sc.input == "same") & (sc.profile == "pure") & (sc.reset == "none") & (sc.N == 4096) & (sc.cutoff == 30)].iloc[0]
    q2 = rr[(rr.input == "fresh") & (rr.profile == "mixed") & (rr.reset == "gc") & (rr.N == 4096) & (rr.cutoff == 30)].iloc[0]
    rule_a(out, name, [
        ("Score same+pure+none, N = 4096, c = 30", {"panel": "ab", "config": "same+pure+none", "N": 4096, "cutoff": 30},
         "value_us", q.score_us, "p2b_jmh_scores.score_us"),
        ("Score T08, N = 4096, c = 7", {"panel": "ab", "config": "T08", "N": 4096, "cutoff": 7}, "value_us",
         t08.loc[(4096, 7), "jmh_score_us"], "p2_jmh.jmh_score_us"),
        ("r fresh+mixed+gc, N = 4096, c = 30", {"panel": "c", "config": "fresh+mixed+gc", "N": 4096}, "value_r",
         q2.r, "p2b_jmh_r.r"),
        ("Run 5, N = 524288, c = 1", {"panel": "ab", "config": "Run5", "N": 524288, "cutoff": 1}, "value_us",
         absr.loc[(524288, 1), "run5_geom_time_us"], "p2b_jmh_abs_vs_run5.run5_geom_time_us"),
    ])


# ───────────────────────────────────────────────────────────── figA07

def make_figA07(out: Path):
    name = "figA07_fork4_sensitivity"
    fl = pd.read_csv(P2 / "p2_fork_level.csv")
    fl = fl[(fl["distribution"] == "random") & (fl["is_c_star"])]
    se = pd.read_csv(P2 / "p2_sensitivity_drop_f4_scales.csv").set_index("scale")
    fig, ax = plt.subplots(figsize=(W120, 3.0))
    rows = []
    for i, s in enumerate(SCALES5):
        sub = fl[fl["scale"] == s].sort_values("fork")
        c5 = int(se.loc[s, "c_star_5forks"])
        assert set(sub["cutoff"]) == {c5}
        for row in sub.itertuples():
            is4 = int(row.fork) == 4
            ax.plot([i - 0.18], [row.r], marker="o" if not is4 else "D", ms=3.6 if not is4 else 4.4,
                    color=C()["vermilion"] if is4 else C()["grey"], alpha=1.0 if is4 else 0.75, ls="none", zorder=4)
            rows.append({"scale": s, "kind": f"fork{int(row.fork)}", "cutoff": c5, "r": row.r,
                         "ci2_lo": np.nan, "ci2_hi": np.nan})
        for dx, kind, col, mk in [(0.06, "5forks", "black", "s"), (0.26, "4forks", C()["blue"], "^")]:
            rv = float(se.loc[s, f"r_star_{kind}"])
            lo, hi = float(se.loc[s, f"ci2_{kind[0]}f_lo"]), float(se.loc[s, f"ci2_{kind[0]}f_hi"])
            ax.errorbar([i + dx], [rv], yerr=[[rv - lo], [hi - rv]], fmt=mk, ms=4, color=col, capsize=2, elinewidth=0.9)
            rows.append({"scale": s, "kind": kind, "cutoff": int(se.loc[s, f"c_star_{kind}"]), "r": rv,
                         "ci2_lo": lo, "ci2_hi": hi})
    ax.set_xticks(range(5))
    ax.set_xticklabels([f"{smath(s)}\n($c^*$ = {int(se.loc[s, 'c_star_5forks'])} / {int(se.loc[s, 'c_star_4forks'])})" for s in SCALES5],
                       fontsize=7.2)
    ax.set_xlabel("Thang $S$ ($c^*$ với 5 fork / 4 fork)")
    ax.set_ylabel("$r(c^*)$")
    handles = [Line2D([], [], marker="o", color=C()["grey"], ls="none", ms=3.6, label="Fork 1, 2, 3, 5 (tại $c^*$ 5 fork)"),
               Line2D([], [], marker="D", color=C()["vermilion"], ls="none", ms=4.4, label="Fork 4 (xung thấp, thí nghiệm chính)"),
               Line2D([], [], marker="s", color="black", ls="-", ms=4, label="Ước lượng 5 fork ± CI hai tầng 95%"),
               Line2D([], [], marker="^", color=C()["blue"], ls="-", ms=4, label="Ước lượng 4 fork (bỏ fork 4) ± CI hai tầng 95%")]
    ax.legend(handles=handles, loc="upper left", fontsize=6.8)
    ax.set_ylim(min(fl["r"].min(), se["ci2_4f_lo"].min()) - 0.005, max(fl["r"].max(), se["ci2_5f_hi"].max()) + 0.035)
    fig.tight_layout()
    src = src_header(name, "[KP]",
                     [f"{P2_REL}/p2_fork_level.csv (random, is_c_star = True; cột scale, fork, cutoff, r)",
                      f"{P2_REL}/p2_sensitivity_drop_f4_scales.csv (c_star_5forks, r_star_5forks, ci2_5f_lo/hi, c_star_4forks, r_star_4forks, ci2_4f_lo/hi)"],
                     "Ước lượng 5 fork và 4 fork: CI hai tầng 95% từ bảng; điểm từng fork không có thanh.",
                     """
- S1 (random, Integer[]): fork 4 có 52.87% mẫu typeperf xung < 110% (p2_session_quality). Phân tích độ nhạy bỏ fork 4 là khám phá.
- Điểm từng fork lấy tại c* của 5 fork; ước lượng 4 fork tại c* của 4 fork (khác ở 2^19: 30 so với 32).
""")
    mf.save_fig_bundle(fig, out, name, pd.DataFrame(rows), src)
    rule_a(out, name, [
        ("r fork 4 tại c* 5 fork, 2^12", {"scale": "2^12", "kind": "fork4"}, "r",
         se.loc["2^12", "r_fork4_at_cstar5"], "p2_sensitivity_drop_f4_scales.r_fork4_at_cstar5"),
        ("r fork 4 tại c* 5 fork, 2^19", {"scale": "2^19", "kind": "fork4"}, "r",
         se.loc["2^19", "r_fork4_at_cstar5"], "p2_sensitivity_drop_f4_scales.r_fork4_at_cstar5"),
        ("r 4 fork, 2^19", {"scale": "2^19", "kind": "4forks"}, "r", se.loc["2^19", "r_star_4forks"],
         "p2_sensitivity_drop_f4_scales.r_star_4forks"),
    ])


# ───────────────────────────────────────────────────────────── figA08

def make_figA08(out: Path):
    name = "figA08_ci_width"
    cw = pd.read_csv(P2 / "p2_ci_width.csv")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(W170, 2.9), gridspec_kw={"width_ratios": [1.25, 1]})
    rows = []
    rnd = cw[cw["distribution"] == "random"]
    kinds = [("c*", C()["black"], "*"), (7, C()["blue"], "s"), (10, C()["orange"], "^"), (30, C()["bluish_green"], "D")]
    for j, (kd, col, mk) in enumerate(kinds):
        xs, ys = [], []
        for i, s in enumerate(SCALES5):
            sub = rnd[rnd["scale"] == s]
            q = sub[sub["is_c_star"]] if kd == "c*" else sub[sub["cutoff"] == kd]
            if kd != "c*" and len(q) == 0:
                continue
            q = q.iloc[0]
            xs.append(i + (j - 1.5) * 0.13)
            ys.append(q.ratio_ci2_over_ci1)
            rows.append({"panel": "a", "distribution": "random", "scale": s, "point": str(kd), "cutoff": int(q.cutoff),
                         "ratio_ci2_over_ci1": q.ratio_ci2_over_ci1})
        ax1.plot(xs, ys, marker=mk, ms=5 if mk == "*" else 3.8, color=col, ls="none",
                 label="$c^*$" if kd == "c*" else f"$c = {kd}$")
    ax1.set_xticks(range(5))
    ax1.set_xticklabels([smath(s) for s in SCALES5])
    ax1.set_xlabel("Thang $S$ (random)")
    ax1.set_ylabel("Độ rộng CI hai tầng / một tầng")
    ax1.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.27), ncol=4, frameon=False)
    ax1.text(0.98, 0.04, "(a)", transform=ax1.transAxes, ha="right", fontsize=8)
    oth = cw[(cw["distribution"] != "random") & (cw["is_c_star"])]
    dists = ["sorted", "nearly_sorted", "reversed", "few_distinct"]
    for j, s in enumerate(SCALES3):
        col, _, mk = scale_styles()[s]
        xs, ys = [], []
        for i, d in enumerate(dists):
            q = oth[(oth["distribution"] == d) & (oth["scale"] == s)].iloc[0]
            xs.append(i + (j - 1) * 0.16)
            ys.append(q.ratio_ci2_over_ci1)
            rows.append({"panel": "b", "distribution": d, "scale": s, "point": "c*", "cutoff": int(q.cutoff),
                         "ratio_ci2_over_ci1": q.ratio_ci2_over_ci1})
        ax2.plot(xs, ys, marker=mk, ms=3.8, color=col, ls="none", label=f"$S$ = {smath(s)}")
    ax2.set_xticks(range(4))
    ax2.set_xticklabels(["sorted", "nearly_\nsorted", "reversed", "few_\ndistinct"], fontsize=7.2)
    ax2.set_xlabel("Phân bố khác, tại $c^*$")
    ax2.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.27), ncol=3, frameon=False)
    ax2.text(0.98, 0.04, "(b)", transform=ax2.transAxes, ha="right", fontsize=8)
    for ax in (ax1, ax2):
        ax.axhline(1.0, color=C()["grey"], lw=0.7, ls=":")
        ax.set_ylim(0, ax.get_ylim()[1] * 1.08)
    fig.tight_layout()
    src = src_header(name, "[MT]",
                     [f"{P2_REL}/p2_ci_width.csv (distribution, scale, cutoff, is_c_star, ratio_ci2_over_ci1)"],
                     "Không có (mỗi điểm là một tỉ số độ rộng).",
                     """
- Tỉ số = (ci2_hi - ci2_lo)/(ci1_hi - ci1_lo): CI hai tầng (rút fork rồi N) so với CI một tầng (chỉ rút N, cách của giai đoạn khám phá).
- (a) random 5 thang tại c*, 7, 10, 30 (ở 2^19, c* = 30 nên điểm c* và điểm c = 30 là cùng một hàng của bảng);
  (b) 4 phân bố S2 × 3 thang tại c*.
- Đường chấm: tỉ số = 1.
""")
    mf.save_fig_bundle(fig, out, name, pd.DataFrame(rows), src)
    def tv(d, s, star, c=None):
        q = cw[(cw.distribution == d) & (cw.scale == s) & (cw.is_c_star == star)]
        if c is not None:
            q = q[q.cutoff == c]
        return q.ratio_ci2_over_ci1.iloc[0]
    rule_a(out, name, [
        ("random 2^12 tại c*", {"panel": "a", "scale": "2^12", "point": "c*"}, "ratio_ci2_over_ci1",
         tv("random", "2^12", True), "p2_ci_width.ratio_ci2_over_ci1"),
        ("random 2^19 tại c = 7", {"panel": "a", "scale": "2^19", "point": "7"}, "ratio_ci2_over_ci1",
         tv("random", "2^19", False, 7), "p2_ci_width.ratio_ci2_over_ci1"),
        ("few_distinct 2^12 tại c*", {"panel": "b", "distribution": "few_distinct", "scale": "2^12"},
         "ratio_ci2_over_ci1", tv("few_distinct", "2^12", True), "p2_ci_width.ratio_ci2_over_ci1"),
    ])


# ───────────────────────────────────────────────────────────── figA09

def make_figA09(out: Path):
    name = "figA09_same_tree_h13"
    h = pd.read_csv(P2 / "p2_H13.csv")
    h = h[h["row_type"] == "per_k"]
    pairs = ["(4, 7)", "(8, 10)", "(16, 30)"]
    sty = {"(4, 7)": (C()["blue"], "o"), "(8, 10)": (C()["orange"], "s"), "(16, 30)": (C()["bluish_green"], "^")}
    fig, ax = plt.subplots(figsize=(W170, 2.9))
    ax.axhspan(-1.0, 1.0, color=C()["light_grey"], alpha=0.45, lw=0, zorder=0)
    rows = []
    for j, p in enumerate(pairs):
        sub = h[h["pair"] == p].sort_values("k")
        col, mk = sty[p]
        x = sub["k"] + (j - 1) * 0.18
        ax.errorbar(x, 100 * sub["delta_mean"], yerr=200 * sub["se_k"], fmt=mk, ms=3.5, color=col, capsize=1.5,
                    elinewidth=0.9, ls="none", label=f"cặp {p}: $\\bar\\Delta \\pm 2\\,\\mathrm{{se}}_k$")
        part = sub[["pair", "k", "N", "delta_mean", "se_k", "pass"]].copy()
        part["delta_mean_pct"] = 100 * part["delta_mean"]
        part["err_2se_pct"] = 200 * part["se_k"]
        rows.append(part)
    ax.axhline(0, color=C()["grey"], lw=0.6)
    ax.set_xticks(range(10, 25))
    ax.set_xlabel("$k = \\lg N$")
    ax.set_ylabel("$\\bar\\Delta(k)$ (%)")
    handles, labels = ax.get_legend_handles_labels()
    handles.append(Patch(color=C()["light_grey"], alpha=0.6))
    labels.append("Ngưỡng đối chứng: $|\\bar\\Delta| \\leq 1\\%$")
    ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7.2, frameon=False)
    fig.tight_layout()
    src = src_header(name, "[ĐK H13]",
                     [f"{P2_REL}/p2_H13.csv (row_type = per_k; cột pair, k, delta_mean, se_k, pass)"],
                     "±2·se_k, se_k = SD giữa 5 fork của Δ / √5 (cột se_k, [KP] thêm ở T11). Dải xám là NGƯỠNG ±1% của H13, KHÔNG phải sai số.",
                     """
- Δ = ln T(c_b) - ln T(c_a) cho hai CUTOFF cho cùng cây đệ quy ở N = 2^k (doubling v2, 5 fork); trục y nhân 100 (%).
- H13 đòi |Δ̄| ≤ 1% ở MỌI k; các điểm có |Δ̄| > 1% là những ô không đạt.
""")
    df = pd.concat(rows, ignore_index=True)
    mf.save_fig_bundle(fig, out, name, df, src)
    t = h.set_index(["pair", "k"])
    rule_a(out, name, [
        ("Δ̄ (16, 30), k = 10", {"pair": "(16, 30)", "k": 10}, "delta_mean", t.loc[("(16, 30)", 10), "delta_mean"], "p2_H13.delta_mean"),
        ("se_k (4, 7), k = 24", {"pair": "(4, 7)", "k": 24}, "se_k", t.loc[("(4, 7)", 24), "se_k"], "p2_H13.se_k"),
    ])


# ───────────────────────────────────────────────────────────── figA10

def make_figA10(out: Path):
    name = "figA10_session_clock"
    from scripts.session_quality import LOW_CLOCK_THRESH, load_session_typeperf, summarize_window
    from scripts.diag_bench_align import parse_env
    q2 = pd.read_csv(P2 / "p2_session_quality.csv")
    q2b = pd.read_csv(P2B / "p2b_session_quality.csv")
    sessions = [
        ("S1", "results_run5_s1", "Thí nghiệm chính (random, 5 fork): bị đánh dấu, giữ lại"),
        ("S6_run1", "results_jmh_v2_rejected_lowclock", "JMH yếu tố đầy đủ lần 1: LOẠI"),
        ("S6_run2", "results_jmh_v2_rejected_lowclock_2", "JMH yếu tố đầy đủ lần 2: LOẠI"),
        ("S6_run3", "results_jmh_v2", "JMH yếu tố đầy đủ lần 3: HỢP LỆ"),
    ]
    fig, axes = plt.subplots(4, 1, figsize=(W170, 5.6))
    rows, checks = [], []
    for ax, (sess, d, title) in zip(axes, sessions):
        tp = load_session_typeperf(PROJECT_ROOT / d)
        t0 = tp["utc"].iloc[0]
        minutes = (tp["utc"] - t0).dt.total_seconds() / 60.0
        if sess == "S1":
            wins = []
            for f in range(1, 6):
                e = parse_env(PROJECT_ROOT / d / f"env_fork{f}.txt")
                wins.append((f, e["start"], e["end"]))
            in_win = np.zeros(len(tp), dtype=bool)
            for f, a, b in wins:
                m = ((tp["utc"] > a) & (tp["utc"] <= b)).to_numpy()
                in_win |= m
                xa, xb = (a - t0).total_seconds() / 60, (b - t0).total_seconds() / 60
                if f == 4:
                    ax.axvspan(xa, xb, color=C()["vermilion"], alpha=0.12, lw=0)
                    ax.text((xa + xb) / 2, 0.06, "cửa sổ fork 4", transform=ax.get_xaxis_transform(), ha="center",
                            fontsize=6.8, color=C()["vermilion"])
                    m4 = m
                ax.axvline(xa, color="#bbbbbb", lw=0.5)
            win = in_win
        else:
            active = tp.index[tp["pin_util"] >= 50.0]
            i0, i1 = int(active[0]), int(active[-1])
            win = np.zeros(len(tp), dtype=bool)
            win[i0:i1 + 1] = True
            ax.axvspan(minutes.iloc[i0], minutes.iloc[i1], color=C()["sky_blue"], alpha=0.10, lw=0)
        ax.plot(minutes, tp["active_pin_perf"], color=C()["blue"], lw=0.5, antialiased=False)
        ax.axhline(LOW_CLOCK_THRESH, color=C()["vermilion"], lw=0.9, ls="--")
        ax.set_ylim(60, 152)
        ax.set_xlim(0, minutes.iloc[-1])
        ax.text(0.005, 0.95, title, transform=ax.transAxes, fontsize=7.3, va="top",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
        ax.set_ylabel("Xung (%)", fontsize=8)
        part = pd.DataFrame({"session": sess, "minute": minutes.to_numpy(), "active_pin_perf": tp["active_pin_perf"].to_numpy(),
                             "in_analysis_window": win})
        if sess == "S1":
            part["in_fork4_window"] = m4
        rows.append(part)
    axes[-1].set_xlabel("Thời gian từ mẫu typeperf đầu tiên của phiên (phút)")
    handles = [Line2D([], [], color=C()["blue"], lw=0.8, label="Xung của LP bận hơn trong cặp LP 10/11 (nhân 5), % xung cơ bản"),
               Line2D([], [], color=C()["vermilion"], ls="--", label="Ngưỡng 110%"),
               Patch(color=C()["vermilion"], alpha=0.2, label="Thí nghiệm chính: cửa sổ fork 4"),
               Patch(color=C()["sky_blue"], alpha=0.25, label="JMH yếu tố đầy đủ: cửa sổ phân tích (LP 10+11 bận ≥ 50%)")]
    fig.tight_layout(h_pad=0.6)
    legend_below(fig, handles, [h.get_label() for h in handles], ncol=2, y=0.0, fontsize=7)
    df = pd.concat(rows, ignore_index=True)
    # tỉ lệ xung thấp đọc từ dữ liệu vẽ (cùng cửa sổ với session_quality)
    stats = []
    for sess, sub_filter, label in [("S1", "in_fork4_window", "S1 fork4"), ("S1", "in_analysis_window", "S1 ALL"),
                                    ("S6_run1", "in_analysis_window", "S6_run1 ALL"),
                                    ("S6_run2", "in_analysis_window", "S6_run2 ALL"),
                                    ("S6_run3", "in_analysis_window", "S6_run3 ALL")]:
        w = df[(df.session == sess) & (df[sub_filter] == True)]
        stats.append({"session": "pct_low_" + label.replace(" ", "_"), "minute": np.nan,
                      "active_pin_perf": 100.0 * float((w.active_pin_perf < LOW_CLOCK_THRESH).sum()) / len(w)})
    df = pd.concat([df, pd.DataFrame(stats)], ignore_index=True)
    src = src_header(name, "[MT]",
                     ["results_run5_s1/typeperf_*.csv và env_fork1..5.txt (cửa sổ fork)",
                      "results_jmh_v2_rejected_lowclock/typeperf_*.csv (S6 lần 1), results_jmh_v2_rejected_lowclock_2/typeperf_*.csv (S6 lần 2), "
                      "results_jmh_v2/typeperf_*.csv (S6 lần 3) — chỉ đọc typeperf",
                      "đọc qua scripts/session_quality.py: load_session_typeperf (cột active_pin_perf, pin_util); "
                      "cửa sổ fork qua scripts/diag_bench_align.parse_env",
                      f"{P2_REL}/p2_session_quality.csv, {P2B_REL}/p2b_session_quality.csv (đối chiếu Quy tắc A)"],
                     "Không có (chuỗi thời gian 1 Hz).",
                     """
- Xung = % Processor Performance của LP bận hơn trong cặp SMT LP 10/11 (nhân vật lý 5, nơi luồng đo được ghim).
- Cửa sổ phân tích giống session_quality.py: S1 là hợp các cửa sổ [start_time, end_time] của 5 fork;
  S6 (JMH, không có env) là từ mẫu đầu đến mẫu cuối có LP 10 + LP 11 bận ≥ 50%.
- Quy tắc loại đăng ký trước (hợp đồng T09 §0): đánh dấu khi > 5% mẫu xung < 110%; loại và đo lại cả phiên khi > 20%.
- Các hàng cuối của .data.csv (session = pct_low_*) là tỉ lệ % mẫu xung < 110% tính từ chính các điểm vẽ.
""")
    mf.save_fig_bundle(fig, out, name, df, src)
    r2 = q2.set_index(["session", "fork"])
    r2b = q2b.set_index(["session", "fork"])
    rule_a(out, name, [
        ("% xung < 110%, S1 fork 4", {"session": "pct_low_S1_fork4"}, "active_pin_perf",
         r2.loc[("S1", "fork4"), "pct_low_clock_lt110"], "p2_session_quality.pct_low_clock_lt110"),
        ("% xung < 110%, S1 ALL", {"session": "pct_low_S1_ALL"}, "active_pin_perf",
         r2.loc[("S1", "ALL"), "pct_low_clock_lt110"], "p2_session_quality.pct_low_clock_lt110"),
        ("% xung < 110%, S6 lần 1", {"session": "pct_low_S6_run1_ALL"}, "active_pin_perf",
         r2b.loc[("S6_run1", "ALL"), "pct_low_clock_lt110"], "p2b_session_quality.pct_low_clock_lt110"),
        ("% xung < 110%, S6 lần 2", {"session": "pct_low_S6_run2_ALL"}, "active_pin_perf",
         r2b.loc[("S6_run2", "ALL"), "pct_low_clock_lt110"], "p2b_session_quality.pct_low_clock_lt110"),
        ("% xung < 110%, S6 lần 3", {"session": "pct_low_S6_run3_ALL"}, "active_pin_perf",
         r2b.loc[("S6_run3", "ALL"), "pct_low_clock_lt110"], "p2b_session_quality.pct_low_clock_lt110"),
    ], tol=1e-9)


# ───────────────────────────────────────────────────────────── figA11

def make_figA11(out: Path):
    name = "figA11_int_fork_curves"
    from scripts.analyze_t10 import compute_paired_A, load_raw_dir
    matplotlib.rcdefaults()  # analyze_t10 -> analyze.py đổi rcParams khi import; trả về mặc định
    mf.set_style()           # rồi đặt lại đúng phong cách chung của make_figures.py
    sd = pd.read_csv(P2B / "p2b_int_fork_sd.csv").set_index(["scale", "cutoff"])
    tabs = []
    for src_dir, tag, exp_rows in [("results_d3/int", "D3", 66_600), ("results_int_ext", "S7", 154_800)]:
        raw = load_raw_dir(PROJECT_ROOT / src_dir, f"{tag}/int", expected_rows=exp_rows)
        _, dfA = compute_paired_A(raw)
        fr = dfA.groupby(["scale_label", "cutoff", "fork"])["A"].mean().map(math.exp).reset_index(name="r_fork")
        fr["session"] = tag
        tabs.append(fr)
    fr = pd.concat(tabs, ignore_index=True)
    fig, axes = plt.subplots(1, 3, figsize=(W170, 3.0), sharey=True)
    for ax, s, tg in zip(axes, SCALES3, ["(a)", "(b)", "(c)"]):
        for sess, col, ls in [("S7", C()["vermilion"], "-"), ("D3", C()["bluish_green"], "--")]:
            sub = fr[(fr["session"] == sess) & (fr["scale_label"] == s)]
            for f, g in sub.groupby("fork"):
                g = g.sort_values("cutoff")
                ax.plot(g["cutoff"], g["r_fork"], color=col, ls=ls, lw=0.8, alpha=0.85)
        log2_axis(ax, [1, 4, 16, 64, 256], lim=(0.85, 300))
        ax.text(0.04, 0.04, f"{tg} $S$ = {smath(s)}", transform=ax.transAxes, fontsize=7.5)
        ax.set_xlabel("CUTOFF $c$ (thang log$_2$)")
    axes[0].set_ylabel("$r_f(c)$ của từng fork")
    handles = [Line2D([], [], color=C()["vermilion"], lw=1, label="int[] mở rộng: 6 fork, mỗi đường một fork"),
               Line2D([], [], color=C()["bluish_green"], lw=1, ls="--", label="int[] kiểu khóa: 3 fork")]
    fig.tight_layout()
    legend_below(fig, handles, [h.get_label() for h in handles], ncol=2, y=0.0)
    df = fr.rename(columns={"scale_label": "scale"})[["session", "scale", "fork", "cutoff", "r_fork"]]
    sdrows = []
    for (s, c), g in df[df.session == "S7"].groupby(["scale", "cutoff"]):
        sdrows.append({"session": "SD_S7", "scale": s, "fork": np.nan, "cutoff": c, "r_fork": g["r_fork"].std(ddof=1)})
    for (s, c), g in df[df.session == "D3"].groupby(["scale", "cutoff"]):
        sdrows.append({"session": "SD_D3", "scale": s, "fork": np.nan, "cutoff": c, "r_fork": g["r_fork"].std(ddof=1)})
    df = pd.concat([df, pd.DataFrame(sdrows)], ignore_index=True)
    src = src_header(name, "[MT]",
                     ["results_d3/int/raw_fork1..3.csv và results_int_ext/raw_fork1..6.csv (dữ liệu thô)",
                      "qua scripts/analyze_t10.py: load_raw_dir (kiểm số hàng, K = 1, không GC) và compute_paired_A (A(f, N, c))",
                      f"{P2B_REL}/p2b_int_fork_sd.csv (đối chiếu Quy tắc A: SD giữa fork)"],
                     "Không có (mỗi đường là một fork).",
                     """
- r_f(c) = exp(trung bình trên 24 N của A(f, N, c)), A = trung bình qua trial của ln T(c) - ln T(1) ghép cặp
  (đúng định nghĩa dùng cho p2b_int_fork_sd ở analyze_t12.py).
- Các hàng session = SD_S7 / SD_D3 trong .data.csv: SD (ddof = 1) giữa các fork của r_f(c), tính từ chính các đường vẽ.
""")
    mf.save_fig_bundle(fig, out, name, df, src)
    rule_a(out, name, [
        ("SD 6 fork S7, 2^12, c = 64", {"session": "SD_S7", "scale": "2^12", "cutoff": 64}, "r_fork",
         sd.loc[("2^12", 64), "sd_6forks_S7"], "p2b_int_fork_sd.sd_6forks_S7"),
        ("SD 3 fork D3, 2^19, c = 30", {"session": "SD_D3", "scale": "2^19", "cutoff": 30}, "r_fork",
         sd.loc[("2^19", 30), "sd_3forks_D3"], "p2b_int_fork_sd.sd_3forks_D3"),
        ("SD 6 fork S7, 2^16, c = 128", {"session": "SD_S7", "scale": "2^16", "cutoff": 128}, "r_fork",
         sd.loc[("2^16", 128), "sd_6forks_S7"], "p2b_int_fork_sd.sd_6forks_S7"),
    ], tol=1e-12)


# ───────────────────────────────────────────────────────────── FIGURES.md

MAIN_FIGS = [
    ("fig01_r_vs_cutoff_run5", "170 mm", "fig:r_cutoff_run5",
     "Tỉ số $r(c) = T(c)/T(1)$ theo CUTOFF, dữ liệu ngẫu nhiên, Integer[], 5 thang (Run 5, 5 fork); dải mờ là CI hai tầng 95%; "
     "ngôi sao là $c^*$ của từng thang; nền xám là giao của 5 vùng gần tối ưu đo được; đường dọc mảnh tại $c = 7$ và $c = 10$.",
     "[ĐK H1]", "P2 p2_r_by_cutoff, p2_best"),
    ("fig02_m2_confirmation", "170 mm", "fig:m2_confirmation",
     "Mô hình chi phí M2 với hệ số đóng băng từ giai đoạn khám phá so với $r$ đo ở hai thang mới $2^{14}$ (a) và $2^{18}$ (b): "
     "đường liền là dự đoán với α nội suy (commit trước khi đo), đường đứt là biến thể α hiệu chỉnh từ hàng $c = 1$; "
     "điểm đo kèm CI hai tầng 95%; RMSE ghi trong từng panel.",
     "[ĐK H10, H10b]", "P2 p2_m2_validation, p2_m2_summary, p2_r_by_cutoff"),
    ("fig03_cost_decomposition", "85 mm", "fig:cost_decomposition",
     "(Giai đoạn khám phá, giữ nguyên) Phân rã chi phí của mô hình M2 trên thang $S = 2^{16}$.", "[KP]",
     "V2 cost_model_decomposition, cost_model_sensitivity"),
    ("fig04_doubling_v2", "170 mm", "fig:doubling_v2",
     "Doubling v2: $\\ln R_k$ theo $k$ cho $c = 1$ (a) và $c = 30$ (b), trung bình 5 fork $\\pm 3\\,\\mathrm{SE}_k$, "
     "điểm xám là từng fork, điểm rỗng là doubling v1; đường đứt là dự đoán P-bão hòa, đoạn ngắn ở $k$ = 22, 23 là dự đoán P-tiếp (đăng ký trước).",
     "[ĐK H11, H12]", "P2 p2_doubling_R, p2_H11, p2_H12; PR T09_predictions_doubling_v2"),
    ("fig05_t_over_nlgn_v2", "120 mm", "fig:t_over_nlgn_v2",
     "Thời gian chuẩn hóa $T/(N \\lg N)$ theo $k$ (doubling v2, $c = 1$ và $c = 30$); đường dọc tại $N$ mà dữ liệu hoạt động "
     "$24N + 32$ byte bằng 1 MiB (L2) và 16 MiB (L3).", "[MT]", "P2 p2_doubling_T_over_NlgN"),
    ("fig06_r30_doubling_v2", "120 mm", "fig:r30_doubling_v2",
     "Tỉ số $r(2^k, 30)$ theo $k$ (doubling test chính) với CI 95% bootstrap theo fork; hai đường ngang là hai cách đọc “khoảng 20%” "
     "($r = 0.80$ và $r = 0.833$). Ở $N = 2^k$, $c = 30$ cho lá dài 16.", "[MT]", "P2 p2_doubling_r30"),
    ("fig07_memory_by_config", "170 mm", "fig:memory_by_config",
     "(Giai đoạn khám phá, giữ nguyên) Bộ nhớ của mergesort trên các cấu hình JVM.", "[MT]", "V2 memory_measurements"),
    ("fig08_other_distributions", "170 mm", "fig:other_distributions",
     "Tỉ số $r(c)$ cho bốn phân bố không ngẫu nhiên ở 3 thang (Run 5, 5 fork) với CI hai tầng 95%; nền vàng là khoảng (với sorted: điểm) "
     "dự đoán đăng ký trước cho $c^*$; ngôi sao là $c^*$ đo.", "[ĐK H6–H9]", "P2 p2_r_by_cutoff, p2_best; PR T09_hypotheses"),
    ("fig09_key_types", "170 mm", "fig:key_types",
     "Tỉ số $r(c)$ theo kiểu khóa ở 3 thang: Integer[], Double[], int[] (D3, 3 fork) và int[] (S7, 6 fork), CI hai tầng 95%; "
     "đường ngang tại $r = 0.833$ và $r = 0.80$; ngôi sao là $c^*$ của từng đường.",
     "[ĐK H14–H16, I1–I3]", "P2 p2_d3_r_by_cutoff, p2_d3_best; P2B p2b_int_r_by_cutoff, p2b_int_best"),
    ("fig10_jmh_vs_harness", "170 mm", "fig:jmh_vs_harness",
     "Thời gian một lần sắp đo bằng JMH theo cấu hình ở $N = 4096$ (a) và $N = 524\\,288$ (b), kèm T08 và Run 5 (bộ đo tự viết, khác phiên); "
     "(c) $r(N, 30)$ theo cấu hình, đường đứt là $r$ của Run 5. JMH yếu tố đầy đủ: CI 95% bootstrap theo fork; T08: Score Error 99.9% của JMH.",
     "[ĐK J1–J7]", "P2B p2b_jmh_scores, p2b_jmh_r, p2b_jmh_abs_vs_run5; P2 p2_jmh"),
]
APPX_FIGS = [
    ("figA01_local_exponent", "120 mm", "fig:local_exponent", "(Giai đoạn khám phá) Số mũ cục bộ $b$ theo thang.", "[KP]", "RF/V2 (khám phá)"),
    ("figA02_power_law_runs", "120 mm", "fig:power_law_runs", "(Giai đoạn khám phá) Chênh số mũ $\\Delta b$ giữa các lượt đo.", "[KP]", "khám phá"),
    ("figA03_precision_vs_R", "120 mm", "fig:precision_vs_r", "(Giai đoạn khám phá) Độ chính xác theo số fork và số lần lặp.", "[KP]", "khám phá"),
    ("figA04_fork_stability_doubling", "120 mm", "fig:fork_stability",
     "(Giai đoạn khám phá) Độ ổn định giữa 3 fork của $\\ln R_k$, doubling v1; dải xám là ngưỡng ±1.5% (tham chiếu).", "[MT]", "DB A1_pred_error_full"),
    ("figA05_cost_model_sensitivity", "120 mm", "fig:cost_model_sensitivity", "(Giai đoạn khám phá) Độ nhạy của $c^*$ của M2 theo hệ số.", "[KP]", "V2 cost_model_sensitivity"),
    ("figA06_r_vs_leaf_length", "120 mm", "fig:r_vs_leaf_length", "(Giai đoạn khám phá) $r$ theo độ dài lá trung bình, 3 thang.", "[KP]", "V2 tree_features, cost_model_predictions"),
    ("figA07_fork4_sensitivity", "120 mm", "fig:fork4_sensitivity",
     "$r(c^*)$ của từng fork ở 5 thang (fork 4 của S1 tô riêng), kèm ước lượng 5 fork và 4 fork (bỏ fork 4) với CI hai tầng 95%.",
     "[KP]", "P2 p2_fork_level, p2_sensitivity_drop_f4_scales"),
    ("figA08_ci_width", "170 mm", "fig:ci_width",
     "Tỉ số độ rộng CI hai tầng / CI một tầng: (a) random tại $c^*$, 7, 10, 30 theo thang; (b) bốn phân bố S2 tại $c^*$.",
     "[MT]", "P2 p2_ci_width"),
    ("figA09_same_tree_h13", "170 mm", "fig:same_tree_h13",
     "Chênh lệch trung bình $\\bar\\Delta(k)$ giữa hai CUTOFF cho cùng cây đệ quy, ba cặp, $\\pm 2\\,\\mathrm{se}_k$; dải xám là ngưỡng ±1% của H13.",
     "[ĐK H13]", "P2 p2_H13 (se_k)"),
    ("figA10_session_clock", "170 mm", "fig:session_clock",
     "Xung của nhân đo (LP bận hơn trong LP 10/11) theo thời gian: S1 (cửa sổ fork 4 được tô nền) và ba lần chạy S6; đường đứt là ngưỡng 110%.",
     "[MT]", "typeperf qua session_quality.py; P2 p2_session_quality, P2B p2b_session_quality"),
    ("figA11_int_fork_curves", "170 mm", "fig:int_fork_curves",
     "Đường $r_f(c)$ của từng fork với int[]: S7 (6 fork) và D3 (3 fork), 3 thang.", "[MT]",
     "thô results_d3/int, results_int_ext qua analyze_t10 (load_raw_dir, compute_paired_A)"),
]
LEGACY = [
    ("fig01_r_vs_cutoff_random", "fig01_r_vs_cutoff_run5"),
    ("fig02_m2_fit_loso", "fig02_m2_confirmation"),
    ("fig04_doubling_ln_R", "fig04_doubling_v2"),
    ("fig05_t_over_nlgn_cache", "fig05_t_over_nlgn_v2"),
    ("fig06_r_diminishing_returns", "fig06_r30_doubling_v2"),
    ("fig08_other_distributions", "fig08_other_distributions (cùng tên, nay là xác nhận, 3 thang)"),
]


def write_figures_md(out: Path):
    def table(rows):
        lines = ["| Tên tệp | Cỡ | `\\label` đề xuất | Caption gợi ý (trung tính, không nhân quả) | Nhãn | Nguồn |",
                 "| --- | --- | --- | --- | --- | --- |"]
        for n, size, lab, cap, tag, srcs in rows:
            lines.append(f"| `{n}` | {size} | `{lab}` | {cap} | {tag} | {srcs} |")
        return "\n".join(lines)
    txt = f"""# Danh mục hình báo cáo bản 2 (T13)

Sinh bởi `python scripts/make_figures_p2.py` (hình xác nhận và chẩn đoán) và `python scripts/make_figures.py --only fig03,fig07,figA01,figA02,figA03,figA04,figA05,figA06`
(hình khám phá giữ nguyên). Mỗi hình có `.pdf` (vector, font nhúng), `.png`, `.data.csv` (đúng các điểm vẽ), `.src.txt`
(nguồn, định nghĩa thanh sai số, nhãn, số đối chiếu Quy tắc A).

Nhãn: [ĐK] kiểm định đăng ký trước (ghi id giả thuyết), [KP] khám phá, [MT] mô tả. Viết tắt nguồn: P2 = `{P2_REL}/`,
P2B = `{P2B_REL}/`, PR = `{PR_REL}/`, V2 = `results_final/analysis_v2/tables/`, DB = `results_doubling/analysis/tables/`.

## 1. Hình thân bài

{table(MAIN_FIGS)}

## 2. Hình phụ lục

{table(APPX_FIGS)}

## 3. Hình giai đoạn khám phá chuyển sang `legacy_phase1/` (git mv, giữ nguyên nội dung)

| Tệp cũ (nay ở `report/figures/legacy_phase1/`) | Thay bằng |
| --- | --- |
""" + "\n".join(f"| `{a}` | `{b}` |" for a, b in LEGACY) + """

Ghi chú: `scripts/make_figures.py` vẫn có thể sinh lại các hình khám phá cũ (fig01, fig02, fig04, fig05, fig06, fig08 với tên cũ)
và ghi đè tệp này nếu chạy không có `--only`; khi cần sinh lại hình khám phá chỉ dùng `--only` với các tên ở trên.
"""
    (out / "FIGURES.md").write_text(txt, encoding="utf-8")
    print("  [OK] FIGURES.md")


# ───────────────────────────────────────────────────────────── main

FIGS = [("fig01", make_fig01), ("fig02", make_fig02), ("fig04", make_fig04), ("fig05", make_fig05),
        ("fig06", make_fig06), ("fig08", make_fig08), ("fig09", make_fig09), ("fig10", make_fig10),
        ("figA07", make_figA07), ("figA08", make_figA08), ("figA09", make_figA09), ("figA10", make_figA10),
        ("figA11", make_figA11)]


def parse_args():
    ap = argparse.ArgumentParser(description="Sinh hình báo cáo bản 2 (T13) từ bảng P2/P2B; không đo, không ngẫu nhiên.")
    ap.add_argument("--out", default="report/figures", help="thư mục xuất (mặc định report/figures)")
    ap.add_argument("--only", default="",
                    help="chỉ sinh các hình này, phân cách bằng dấu phẩy: " + ", ".join(t for t, _ in FIGS) + ", md")
    ap.add_argument("--seed", type=int, default=0, help="không dùng (script không có bước ngẫu nhiên)")
    return ap.parse_args()


def main():
    a = parse_args()
    out = Path(a.out)
    if not out.is_absolute():
        out = PROJECT_ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    mf.set_style()
    only = {t.strip() for t in a.only.split(",") if t.strip()}
    unknown = only - {t for t, _ in FIGS} - {"md"}
    if unknown:
        raise SystemExit(f"Tên không hợp lệ trong --only: {sorted(unknown)}")
    for tag, fn in FIGS:
        if not only or tag in only:
            print(f"== {tag}")
            fn(out)
    if not only or "md" in only:
        write_figures_md(out)


if __name__ == "__main__":
    main()
