#!/usr/bin/env python3
"""
diag_bench_align.py — ghép typeperf (mỗi giây) với một hoặc nhiều lần chạy Benchmark (env_fork*.txt [+ console]).

    # một JVM (E6, T2):
    python scripts/diag_bench_align.py --env diag/E6/bench/env_fork1.txt --typeperf diag/E6/typeperf.csv
           [--console diag/E6/console.txt] [--ref results/env_fork1.txt] [--ref-level 0.932] [--out diag/E6]
    # cả lượt (run 3, ghim nhân 5 = LP 10/11, một typeperf cho cả 3 fork):
    python scripts/diag_bench_align.py --env results_run3/env_fork1.txt results_run3/env_fork2.txt
           results_run3/env_fork3.txt --typeperf results_run3/typeperf.csv --lps 10,11 --out results_run3/diag

Giai đoạn:
  - warm-up JVM: dựng lại thời điểm từng vòng từ round_totals_ms + chi phí phụ mỗi lần đo (System.gc, clone),
    chi phí phụ giải từ tổng thời gian warm-up ("time=" trong env). Neo: start_time trong env.
  - từng bộ dữ liệu: [kết thúc bộ trước, kết thúc bộ này]; mốc kết thúc lấy từ "elapsed" trong console
    (chính xác tới 1 s) nếu có, nếu không thì cộng dồn load + warmup + measure trong env (làm tròn 0.1 s).
  - cửa sổ của JVM kết thúc ở end_time trong env (nếu có).
Với mỗi giai đoạn, từ typeperf: LP bận nhất, nhân (LP//2), % Processor Performance của LP đó, độ bận của LP anh
em SMT và của các LP khác, số lần đổi LP / đổi nhân; với --lps: xung và độ bận của chính các LP được ghim.
Thời gian của bộ dữ liệu:
  - --ref (một JVM): so với cùng bộ ở lượt tham chiếu (cùng thứ tự bộ dữ liệu).
  - nhiều --env: so CHÉO giữa các fork của cùng lượt: rel = (warmup + measure) / trung bình nhân trên các fork,
    chỉ với bộ có thời gian ≥ --min-seconds ở mọi fork (K = 1, nên thời gian tỉ lệ với T cộng chi phí phụ cố định).
Thời gian typeperf (giờ địa phương + bias ở header) và start_time/end_time (có offset) đều đổi về UTC.
"""
import argparse
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

FAST_NS_PER_NLGN = 9.35         # WarmupProbe E0_2, N = 65536, mức nhanh
SMT_PAIR = lambda lp: lp ^ 1    # LP 2k và 2k+1 cùng một nhân (xác nhận bằng Coreinfo -c)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK2, NEUTRAL, GRID_C = "#52514e", "#8d8c86", "#e2e1dc"


def scale_label(n):
    return "2^19" if n >= 2 ** 18 else ("2^16" if n >= 2 ** 14 else "2^12")


def read_typeperf(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    head = df.columns[0]
    m = re.search(r"\((-?\d+)\)\s*$", head)
    bias = int(m[1]) if m else 0                         # UTC = giờ địa phương + bias (phút)
    ts = None
    for fmt in ("%m/%d/%Y %H:%M:%S.%f", "%d/%m/%Y %H:%M:%S.%f"):
        try:
            ts = pd.to_datetime(df[head].str.strip(), format=fmt)
            break
        except (ValueError, TypeError):
            pass
    if ts is None:
        raise SystemExit("không đọc được thời gian trong typeperf")
    out = pd.DataFrame({"utc": ts + pd.Timedelta(minutes=bias)})
    for col in df.columns[1:]:
        mm = re.search(r"Processor Information\((\d+),(\d+)\)\\% Processor (Performance|Utility)", col)
        if mm:
            lp = int(mm[1]) * 64 + int(mm[2])
            out[f"{'perf' if mm[3] == 'Performance' else 'util'}_{lp}"] = pd.to_numeric(df[col], errors="coerce")
    out = out.dropna(subset=[c for c in out.columns if c.startswith("util_")], how="all").reset_index(drop=True)
    lps = sorted(int(c[5:]) for c in out.columns if c.startswith("util_"))
    U = out[[f"util_{l}" for l in lps]].to_numpy()
    P = out[[f"perf_{l}" for l in lps]].to_numpy()
    b = np.nanargmax(np.nan_to_num(U, nan=-1), axis=1)
    out["busy_lp"] = [lps[i] for i in b]
    out["busy_core"] = out.busy_lp // 2
    out["busy_util"] = U[np.arange(len(U)), b]
    out["busy_perf"] = P[np.arange(len(U)), b]
    idx = {l: j for j, l in enumerate(lps)}
    out["sib_util"] = [U[k, idx[SMT_PAIR(l)]] if SMT_PAIR(l) in idx else np.nan for k, l in enumerate(out.busy_lp)]
    out["core_util"] = out.busy_util + out.sib_util          # ~100 nếu một luồng chạy liên tục trên nhân đó
    out["others_util"] = [np.mean([U[k, j] for l2, j in idx.items() if l2 // 2 != l // 2])
                          for k, l in enumerate(out.busy_lp)]
    out["all_perf"] = np.nanmean(P, axis=1)
    out.attrs["lps"] = lps
    return out


def add_pinned(tp: pd.DataFrame, pin: list[int]):
    """Đại lượng của chính các LP được ghim (không phụ thuộc LP nào bận nhất)."""
    lps = tp.attrs["lps"]
    tp["pin_util"] = tp[[f"util_{l}" for l in pin]].sum(axis=1)       # ~100 × xung/xung cơ bản nếu luôn bận
    tp["pin_perf"] = tp[[f"perf_{l}" for l in pin]].mean(axis=1)
    rest = [f"util_{l}" for l in lps if l not in pin]
    tp["rest_util_mean"] = tp[rest].mean(axis=1)
    tp["rest_util_max"] = tp[rest].max(axis=1)
    tp["busy_in_pin"] = tp.busy_lp.isin(pin)


def parse_env(path: Path):
    txt = path.read_text(encoding="utf-8")
    start = pd.Timestamp(re.search(r"start_time=([^\[\s]+)", txt)[1]).tz_convert("UTC").tz_localize(None)
    me = re.search(r"end_time=([^\[\s]+)", txt)
    end = pd.Timestamp(me[1]).tz_convert("UTC").tz_localize(None) if me else None
    fork = re.search(r"^fork=(\d+)", txt, re.M)
    w = re.search(r"jvm_warmup: .*?time=([\d.]+)s round_totals_ms=\[([^\]]*)\]", txt)
    ds = []
    for m in re.finditer(r"^dataset (\S+) N=(\d+) seed=\d+ R=(\d+) grid=(\d+) K_warmup=\d+ K=(\d+) "
                         r"load=([\d.]+)s warmup=([\d.]+)s measure=([\d.]+)s", txt, re.M):
        ds.append({"distribution": m[1], "N": int(m[2]), "R": int(m[3]), "grid": int(m[4]), "K": int(m[5]),
                   "load": float(m[6]), "warmup": float(m[7]), "measure": float(m[8])})
    return {"start": start, "end": end, "fork": int(fork[1]) if fork else None, "wtime": float(w[1]),
            "totals": [float(x) for x in w[2].split()], "ds": pd.DataFrame(ds)}


def warmup_rounds(start, wtime, totals, n_per_round=35):
    tot = np.array(totals)
    ovh = (wtime * 1000 - tot.sum()) / (n_per_round * len(tot))    # chi phí phụ mỗi lần đo (ms), giả định không đổi
    edges = np.concatenate([[0], np.cumsum(tot + n_per_round * ovh)])
    rows = []
    for i, t in enumerate(tot):
        rows.append({"phase": f"warm-up vòng {i + 1}", "kind": "jvm_warmup", "round": i + 1,
                     "t0": start + pd.Timedelta(milliseconds=edges[i]), "t1": start + pd.Timedelta(milliseconds=edges[i + 1]),
                     "sort_ms_per_sort": t / n_per_round,
                     "vs_fast": t / n_per_round / (FAST_NS_PER_NLGN * 65536 * 16 / 1e6)})
    return rows, ovh, start + pd.Timedelta(seconds=wtime)


def phase_stats(tp: pd.DataFrame, t0, t1, pinned: bool):
    w = tp[(tp.utc > t0) & (tp.utc <= t1)]                     # mẫu typeperf = trung bình của giây trước đó
    if w.empty:
        return {"n_samples": 0}
    rec = {"n_samples": len(w), "busy_lp_mode": int(w.busy_lp.mode()[0]),
           "busy_cores": " ".join(map(str, sorted(w.busy_core.unique()))),
           "busy_perf": w.busy_perf.median(), "busy_util": w.busy_util.median(), "sib_util": w.sib_util.median(),
           "core_util": w.core_util.median(), "others_util": w.others_util.median(), "all_perf": w.all_perf.median(),
           "lp_changes": int((w.busy_lp != w.busy_lp.shift()).sum() - 1),
           "core_changes": int((w.busy_core != w.busy_core.shift()).sum() - 1)}
    if pinned:
        rec.update({"pin_perf": w.pin_perf.median(), "pin_perf_min": w.pin_perf.min(), "pin_util": w.pin_util.median(),
                    "pin_util_min": w.pin_util.min(), "rest_util": w.rest_util_mean.median(),
                    "rest_util_p95": w.rest_util_mean.quantile(0.95), "share_busy_in_pin": w.busy_in_pin.mean()})
    return rec


def phases_for(tp, env: dict, console: str | None, ref: str | None, ref_level: float, pinned: bool):
    rows, ovh, t = warmup_rounds(env["start"], env["wtime"], env["totals"])
    ds = env["ds"]
    ends = None
    if console:
        el = [int(h) * 3600 + int(m) * 60 + int(s) for h, m, s in
              re.findall(r"\d+/\d+ .*?elapsed (\d+):(\d+):(\d+)", Path(console).read_text(encoding="utf-8"))]
        if len(el) >= len(ds):
            ends = [env["start"] + pd.Timedelta(seconds=x) for x in el[:len(ds)]]
    rf = parse_env(Path(ref))["ds"] if ref else None
    for i, d in ds.iterrows():
        t1 = ends[i] if ends else t + pd.Timedelta(seconds=d.load + d.warmup + d.measure)
        rec = {"phase": f"bộ {i + 1}: {d.distribution} N={d.N}", "kind": "dataset", "round": i + 1, "t0": t, "t1": t1,
               "distribution": d.distribution, "N": d.N, "scale": scale_label(d.N), "K": d.K,
               "duration_s": d.load + d.warmup + d.measure, "tm_s": d.warmup + d.measure}
        if rf is not None and i < len(rf) and rf.loc[i, "N"] == d.N and rf.loc[i, "distribution"] == d.distribution:
            r = rf.loc[i]
            rec["vs_ref"] = (d.warmup + d.measure) / (r.warmup + r.measure)
            rec["level_vs_main_median"] = rec["vs_ref"] * ref_level
        rows.append(rec)
        t = t1
    ph = pd.DataFrame(rows)
    st = pd.DataFrame([phase_stats(tp, r.t0, r.t1, pinned) for r in ph.itertuples()])
    ph = pd.concat([ph, st], axis=1)
    ph["t0_s"] = (ph.t0 - env["start"]).dt.total_seconds()
    ph["t1_s"] = (ph.t1 - env["start"]).dt.total_seconds()
    return ph, ovh


def cross_fork(ph: pd.DataFrame, min_seconds: float) -> pd.DataFrame:
    """rel = (warmup + measure) / TB nhân trên các fork, cho bộ có thời gian ≥ min_seconds ở mọi fork."""
    d = ph[ph.kind == "dataset"]
    p = d.pivot_table(index=["distribution", "N"], columns="fork", values="tm_s")
    p = p[(p.min(axis=1) >= min_seconds) & p.notna().all(axis=1)]
    gm = np.exp(np.log(p).mean(axis=1))
    rel = p.div(gm, axis=0).stack().rename("rel_cross").reset_index()
    return ph.merge(rel, on=["distribution", "N", "fork"], how="left")


def fig_timeline(tp, ph, start, path):
    """Một JVM (E6, T2): xung của nhân đang chạy + mức thời gian."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    end = ph.t1.max()
    t = tp[(tp.utc > start - pd.Timedelta(seconds=5)) & (tp.utc <= end)].copy()
    t["s"] = (t.utc - start).dt.total_seconds()
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(6.6, 4.2), sharex=True, gridspec_kw={"height_ratios": [1.2, 1]})
    colors = ["#e34948", "#2a78d6", "#1baf7a", "#eda100", "#e87ba4"]
    main_cores = t.busy_core.value_counts().index[:5].tolist()
    for k, c in enumerate(main_cores):
        g = t[t.busy_core == c]
        ax.plot(g.s, g.busy_perf, linestyle="none", marker="o", markersize=2.5, color=colors[k], label=f"nhân {c} (LP {2*c}/{2*c+1})")
    ax.set_ylabel("xung nhân đang chạy\n(% Proc. Performance)")
    ax.legend(fontsize=7.5, ncol=len(main_cores), loc="lower right", frameon=False)
    ax.grid(color=GRID_C, linewidth=0.6)
    w = ph[ph.kind == "jvm_warmup"]
    d = ph[(ph.kind == "dataset") & ph.get("level_vs_main_median", pd.Series(dtype=float)).notna() & (ph.duration_s >= 2)] \
        if "level_vs_main_median" in ph else ph.iloc[0:0]
    if len(w):
        ax2.plot((w.t0 - start).dt.total_seconds(), w.vs_fast * 0.61, "s", markersize=3, color=INK2,
                 label="vòng warm-up (quy đổi)")
    if len(d):
        ax2.plot(((d.t0 + (d.t1 - d.t0) / 2) - start).dt.total_seconds(), d.level_vs_main_median, "o", markersize=3.5,
                 color="#2a78d6", label="bộ dữ liệu ≥ 2 s")
    ax2.axhline(1, color=NEUTRAL, linewidth=0.8)
    ax2.axhline(0.61, color=NEUTRAL, linewidth=0.8, linestyle=":")
    ax2.set_ylabel("mức thời gian\n(1 = run chính)")
    ax2.set_xlabel("giây kể từ start_time của Benchmark")
    ax2.legend(fontsize=7.5, frameon=False, loc="upper right")
    ax2.grid(color=GRID_C, linewidth=0.6)
    fig.suptitle("Benchmark: xung của nhân đang chạy luồng và mức thời gian", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def fig_run(tp, ph, envs, pin, path):
    """Nhiều fork (cả lượt): xung và độ bận của nhân được ghim, thời gian tương đối giữa các fork."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t_start = min(e["start"] for e in envs)
    t_end = max(e["end"] or ph.t1.max() for e in envs)
    t = tp[(tp.utc > t_start - pd.Timedelta(seconds=30)) & (tp.utc <= t_end + pd.Timedelta(seconds=30))].copy()
    t["m"] = (t.utc - t_start).dt.total_seconds() / 60
    fig, axes = plt.subplots(3, 1, figsize=(6.6, 6.0), sharex=True, gridspec_kw={"height_ratios": [1, 0.8, 1.1]})
    ax, ax1, ax2 = axes
    yv = t.pin_perf if pin else t.busy_perf
    ax.plot(t.m, yv, linestyle="none", marker="o", markersize=1.6, color=SERIES[0],
            label=f"LP {'/'.join(map(str, pin))}" if pin else "LP bận nhất")
    ax.plot(t.m, t.all_perf, linewidth=0.7, color=NEUTRAL, label="TB 16 LP")
    ax.set_ylabel("% Processor\nPerformance")
    ax.legend(fontsize=7.5, loc="lower right", ncol=2)
    if pin:
        ax1.plot(t.m, t.pin_util, linewidth=0.8, color=SERIES[0], label=f"nhân được ghim (LP {'+'.join(map(str, pin))})")
        ax1.plot(t.m, t.rest_util_mean, linewidth=0.8, color=SERIES[1], label="TB các LP còn lại")
    else:
        ax1.plot(t.m, t.core_util, linewidth=0.8, color=SERIES[0], label="nhân bận nhất")
        ax1.plot(t.m, t.others_util, linewidth=0.8, color=SERIES[1], label="TB các nhân khác")
    ax1.set_ylabel("% Processor\nUtility")
    ax1.legend(fontsize=7.5, loc="center right")
    d = ph[(ph.kind == "dataset") & ph.get("rel_cross", pd.Series(dtype=float)).notna()] if "rel_cross" in ph else ph.iloc[0:0]
    for k, (sc, g) in enumerate(d.groupby("scale")):
        mid = ((g.t0 + (g.t1 - g.t0) / 2) - t_start).dt.total_seconds() / 60
        ax2.plot(mid, g.rel_cross, linestyle="none", marker="os^"[k % 3], markersize=3.2, color=SERIES[(k + 2) % 5],
                 label=f"random {sc}" if set(g.distribution) == {"random"} else sc)
    ax2.axhline(1, color=NEUTRAL, linewidth=0.8)
    ax2.set_ylabel("thời gian bộ / TB nhân\ncác fork (cùng bộ)")
    ax2.set_xlabel("phút kể từ start_time của fork đầu tiên")
    ax2.legend(fontsize=7.5, loc="upper right")
    for e in envs:
        for a in axes:
            a.axvline((e["start"] - t_start).total_seconds() / 60, color=INK2, linewidth=0.7, linestyle="--")
        from matplotlib.transforms import blended_transform_factory
        ax1.text((e["start"] - t_start).total_seconds() / 60, 0.5, f" fork {e['fork']}", fontsize=7.5, color=INK2,
                 va="center", transform=blended_transform_factory(ax1.transData, ax1.transAxes))
    for a in axes:
        a.grid(color=GRID_C, linewidth=0.6)
        a.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Cả lượt: xung, độ bận và thời gian tương đối giữa các fork", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", nargs="+", required=True)
    ap.add_argument("--typeperf", required=True)
    ap.add_argument("--console", nargs="*", default=None, help="console.txt theo đúng thứ tự --env")
    ap.add_argument("--ref", nargs="*", default=None, help="env_fork*.txt tham chiếu theo đúng thứ tự --env")
    ap.add_argument("--ref-level", type=float, default=0.932, help="mức của lượt tham chiếu so với trung vị JVM chính")
    ap.add_argument("--lps", default=None, help="các LP được ghim, vd 10,11 (affinity C00)")
    ap.add_argument("--low-perf", type=float, default=120.0, help="ngưỡng liệt kê mẫu xung thấp (%% Performance)")
    ap.add_argument("--min-seconds", type=float, default=2.0, help="chỉ tóm tắt/so chéo bộ dữ liệu dài hơn ngưỡng này")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    tp = read_typeperf(Path(a.typeperf))
    pin = [int(x) for x in a.lps.split(",")] if a.lps else []
    if pin:
        add_pinned(tp, pin)
    envs = [parse_env(Path(p)) for p in a.env]
    for k, e in enumerate(envs):
        e["fork"] = e["fork"] or k + 1
    phs = []
    for k, e in enumerate(envs):
        ph, ovh = phases_for(tp, e, a.console[k] if a.console and k < len(a.console) else None,
                             a.ref[k] if a.ref and k < len(a.ref) else None, a.ref_level, bool(pin))
        ph.insert(0, "fork", e["fork"])
        ph["ovh_ms"] = ovh
        phs.append(ph)
    ph = pd.concat(phs, ignore_index=True)
    if len(envs) > 1:
        ph = cross_fork(ph, a.min_seconds)

    t_start = min(e["start"] for e in envs)
    out = Path(a.out) if a.out else Path(a.env[0]).parent
    out.mkdir(parents=True, exist_ok=True)
    ph.drop(columns=["t0", "t1"]).to_csv(out / "bench_aligned.csv", index=False)
    tp.assign(t_s=(tp.utc - t_start).dt.total_seconds()).to_csv(out / "typeperf_busy.csv", index=False)
    pd.set_option("display.width", 220)

    # ---- tóm tắt theo JVM (toàn cửa sổ start..end)
    print("== theo JVM (mọi mẫu typeperf từ start_time tới end_time)")
    rows = []
    for e in envs:
        end = e["end"] or ph[ph.fork == e["fork"]].t1.max()
        w = tp[(tp.utc > e["start"]) & (tp.utc <= end)]
        rec = {"fork": e["fork"], "start_utc": e["start"].strftime("%H:%M:%S"), "minutes": (end - e["start"]).total_seconds() / 60,
               "n": len(w), "busy_cores": " ".join(f"{c}:{n}" for c, n in w.busy_core.value_counts().items())}
        v = w.pin_perf if pin else w.busy_perf
        rec.update({f"perf_p{q}": np.percentile(v, q) for q in (0, 1, 5, 50, 95, 100)})
        rec[f"n_perf<{a.low_perf:g}"] = int((v < a.low_perf).sum())
        if pin:
            rec.update({"pin_util_p1": np.percentile(w.pin_util, 1), "pin_util_med": w.pin_util.median(),
                        "share_busy_in_pin": w.busy_in_pin.mean(), "rest_util_med": w.rest_util_mean.median(),
                        "rest_util_p95": np.percentile(w.rest_util_mean, 95), "rest_util_max": w.rest_util_mean.max()})
        else:
            rec.update({"core_util_med": w.core_util.median(), "others_util_med": w.others_util.median()})
        rows.append(rec)
    jt = pd.DataFrame(rows)
    jt.to_csv(out / "jvm_typeperf_summary.csv", index=False)
    print(jt.round(2).to_string(index=False))

    # ---- mẫu bất thường
    print(f"\n== mẫu có xung < {a.low_perf:g}%" + (" hoặc nhân được ghim bận < 90% hoặc LP bận nhất ngoài nhóm ghim" if pin else ""))
    lows = []
    for e in envs:
        end = e["end"] or ph[ph.fork == e["fork"]].t1.max()
        w = tp[(tp.utc > e["start"]) & (tp.utc <= end)]
        bad = (w.pin_perf < a.low_perf) | (w.pin_util < 90) | ~w.busy_in_pin if pin else (w.busy_perf < a.low_perf)
        p = ph[ph.fork == e["fork"]]
        for _, r_ in w[bad].iterrows():
            hit = p[(p.t0 < r_.utc) & (p.t1 >= r_.utc)]
            lows.append({"fork": e["fork"], "t_s": (r_.utc - e["start"]).total_seconds(),
                         "phase": hit.phase.iloc[0] if len(hit) else "(giữa các giai đoạn)",
                         "perf": r_.pin_perf if pin else r_.busy_perf, "util": r_.pin_util if pin else r_.core_util,
                         "busy_lp": r_.busy_lp, "rest_util": r_.rest_util_mean if pin else r_.others_util})
    lw = pd.DataFrame(lows)
    lw.to_csv(out / "typeperf_low_samples.csv", index=False)
    print(lw.round(1).to_string(index=False) if len(lw) else "(không có)")

    # ---- giai đoạn
    if len(envs) == 1:
        cols = ["t0_s", "t1_s", "sort_ms_per_sort", "vs_fast", "busy_lp_mode", "busy_cores", "busy_perf", "busy_util",
                "sib_util", "core_util", "others_util", "lp_changes", "core_changes"]
        print(f"\nchi phí phụ mỗi lần đo trong warm-up (dựng lại): {ph.ovh_ms.iloc[0]:.2f} ms")
        print("\n== warm-up JVM (mỗi vòng; mẫu typeperf 1 s nên vòng ngắn có thể không có mẫu riêng)")
        w = ph[ph.kind == "jvm_warmup"]
        print(w[["phase"] + [c for c in cols if c in w]].round(2).to_string(index=False))
        print("\n== bộ dữ liệu dài hơn", a.min_seconds, "s")
        d = ph[(ph.kind == "dataset") & (ph.duration_s >= a.min_seconds)]
        dcols = ["phase", "t0_s", "t1_s", "vs_ref", "level_vs_main_median", "busy_lp_mode", "busy_cores", "busy_perf",
                 "sib_util", "core_util", "others_util", "core_changes", "pin_perf", "pin_util"]
        print(d[[c for c in dcols if c in d]].round(2).to_string(index=False))
        fig_timeline(tp, ph, envs[0]["start"], out / "bench_timeline.png")
        print("\n== tóm tắt theo nhân đang chạy luồng (mọi mẫu từ lúc JVM chạy tới hết)")
        tt = tp[(tp.utc > envs[0]["start"]) & (tp.utc <= ph.t1.max())]
        g = tt.groupby("busy_core").agg(n=("busy_perf", "size"), perf_median=("busy_perf", "median"),
                                        core_util=("core_util", "median"), others=("others_util", "median"))
        print(g.round(1).to_string())
        return

    # ---- nhiều fork: so chéo theo bộ dữ liệu
    d = ph[(ph.kind == "dataset") & ph.rel_cross.notna()].copy()
    d["grp"] = np.where(d.distribution == "random", "random " + d.scale, "khác " + d.scale)
    g = d.groupby(["grp", "fork"]).agg(n=("rel_cross", "size"), rel_gm=("rel_cross", lambda x: math.exp(np.log(x).mean())),
                                       rel_min=("rel_cross", "min"), rel_max=("rel_cross", "max"),
                                       perf_med=("pin_perf" if pin else "busy_perf", "median"),
                                       rest_util_med=("rest_util" if pin else "others_util", "median")).reset_index()
    g.to_csv(out / "cross_fork_by_group.csv", index=False)
    print(f"\n== thời gian (warmup + measure) so với TB nhân của các fork, cùng bộ dữ liệu (bộ ≥ {a.min_seconds:g} s ở mọi fork)")
    print(g.round(3).to_string(index=False))
    # theo thứ tự trong từng fork: rel của các bộ random 2^19
    big = d[d.scale == "2^19"].sort_values(["fork", "round"])
    print("\n== random 2^19 theo thứ tự trong fork (round = vị trí bộ trong fork): rel_cross")
    for f, h in big.groupby("fork"):
        print(f"  fork {f}: " + " ".join(f"{int(r)}:{x:.3f}" for r, x in zip(h["round"], h.rel_cross)))
    # tương quan với độ bận của các LP khác trong lúc chạy bộ đó
    col = "rest_util" if pin else "others_util"
    print(f"\n== tương quan (Spearman) giữa rel_cross và {col} trong từng nhóm × fork")
    from scipy import stats
    for (grp, f), h in d.groupby(["grp", "fork"]):
        if len(h) >= 6:
            rho = stats.spearmanr(h.rel_cross, h[col])
            print(f"  {grp} fork {f}: ρ = {rho[0]:+.2f} (p = {rho[1]:.2g}, n = {len(h)})")
    fig_run(tp, ph, envs, pin, out / "run_timeline.png")


if __name__ == "__main__":
    main()
