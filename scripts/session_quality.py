#!/usr/bin/env python3
"""
scripts/session_quality.py — Đánh giá chất lượng 5 phiên đo giai đoạn 2 theo §0 hợp đồng T09.

Định nghĩa cửa sổ đo và chỉ số (ghi rõ theo yêu cầu T10 §4.7):
  1. Cửa sổ đo (measurement window):
     - Các phiên có env_fork*.txt (S1, S2, DV2, D3):
       + Cửa sổ từng fork: mọi mẫu typeperf (chu kỳ 1 giây) thỏa start_time < utc <= end_time
         đọc từ env_fork*.txt (cùng quy ước với scripts/diag_bench_align.py; mẫu typeperf ở thời
         điểm t phản ánh giây (t-1, t]).
       + Cửa sổ toàn phiên: hợp các cửa sổ fork của phiên đó.
     - Phiên JMH (không có env_fork*.txt):
       + Cửa sổ toàn phiên: từ mẫu đầu tiên đến mẫu cuối cùng có độ bận nhân 5
         (pin_util = util_10 + util_11) >= 50.0% (cắt phần rảnh trước khi JMH chạy và sau khi dừng).
  2. "Ngoài LP 10/11":
     - Tại mỗi mẫu 1 giây, chọn busy_lp = LP có % Processor Utility lớn nhất trong 16 LP (0..15).
     - Một mẫu được tính là "ngoài LP 10/11" nếu busy_lp không thuộc {10, 11} (nhân vật lý 5,
       mặt nạ /affinity C00). Tỉ lệ (%) = 100 * (# mẫu busy_lp not in {10, 11}) / n_samples.
  3. "Xung < 110%":
     - active_pin_perf = % Processor Performance của LP bận hơn trong cặp SMT nhân 5
       (LP 10 nếu util_10 >= util_11, ngược lại LP 11), tránh kéo trung bình xuống bởi LP anh em rảnh.
     - Một mẫu được tính là "xung thấp" nếu active_pin_perf < 110.0 (%).
     - Theo §0 hợp đồng: > 5% → đánh dấu (flagged_gt5pct = True); > 20% → loại và chạy lại.
  4. Thời gian thực (duration_s, duration_min):
     - Với fork có env: (end_time - start_time).total_seconds().
     - Với phiên có nhiều fork: tổng thời gian thực các fork (và kèm span đầu-cuối trong log).
     - Với JMH: (t_last - t_first).total_seconds() trong cửa sổ hoạt động.

Cách chạy (từ thư mục gốc dự án):
    python scripts/session_quality.py --self-check
    python scripts/session_quality.py --out results_phase2/analysis/tables
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from scripts.diag_bench_align import add_pinned, parse_env, read_typeperf

PIN_LPS = [10, 11]
LOW_CLOCK_THRESH = 110.0
FLAG_PCT_THRESH = 5.0

# Số đối chiếu Quy tắc A (T10 §4.7, dung sai ±0.3 điểm %)
REF_PHASE2 = {
    ("S1", "ALL"): {"pct_low_clock_lt110": 13.02, "pct_outside_lp10_11": 0.08},
    ("S1", "fork4"): {"pct_low_clock_lt110": 52.87},
    ("DV2", "ALL"): {"pct_low_clock_lt110": 0.00, "pct_outside_lp10_11": 0.11},
    ("S2", "ALL"): {"pct_low_clock_lt110": 0.00, "pct_outside_lp10_11": 0.27},
    ("JMH", "ALL"): {"pct_low_clock_lt110": 0.00, "pct_outside_lp10_11": 0.18},
    ("D3", "ALL"): {"pct_low_clock_lt110": 0.00, "pct_outside_lp10_11": 0.05},
}

# Số đối chiếu Quy tắc A giai đoạn 2b (T12 §3.4 & CONTEXT.md, dung sai ±0.3 điểm %)
REF_PHASE2B = {
    ("S6_run1", "ALL"): {"pct_low_clock_lt110": 54.27, "pct_outside_lp10_11": 0.27},
    ("S6_run2", "ALL"): {"pct_low_clock_lt110": 77.27, "pct_outside_lp10_11": 3.12},
    ("S6_run3", "ALL"): {"pct_low_clock_lt110": 0.03, "pct_outside_lp10_11": 2.75},
    ("S7", "ALL"): {"pct_low_clock_lt110": 0.00, "pct_outside_lp10_11": 0.00},
}
REJECT_PCT_THRESH = 20.0


def load_session_typeperf(session_dir: Path) -> pd.DataFrame:
    """Đọc và ghép mọi tệp typeperf*.csv trong thư mục phiên."""
    files = sorted(session_dir.glob("typeperf*.csv"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy typeperf*.csv trong {session_dir}")
    dfs = [read_typeperf(p) for p in files]
    lps = dfs[0].attrs["lps"]
    tp = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["utc"]).sort_values("utc").reset_index(drop=True)
    tp.attrs["lps"] = lps
    add_pinned(tp, PIN_LPS)
    # Xung của LP đang chạy (bận hơn) trong cặp SMT LP 10/11 (tránh kéo tụt bởi LP anh em rảnh)
    tp["active_pin_perf"] = np.where(tp["util_10"] >= tp["util_11"], tp["perf_10"], tp["perf_11"])
    return tp


def summarize_window(session: str, fork_label: str, w: pd.DataFrame, duration_s: float) -> dict:
    """Tính các chỉ số chất lượng phiên trên tập mẫu typeperf w."""
    n = len(w)
    if n == 0:
        return {
            "session": session,
            "fork": fork_label,
            "n_samples": 0,
            "n_outside_lp10_11": 0,
            "pct_outside_lp10_11": float("nan"),
            "n_low_clock_lt110": 0,
            "pct_low_clock_lt110": float("nan"),
            "perf_median": float("nan"),
            "perf_min": float("nan"),
            "duration_s": duration_s,
            "duration_min": duration_s / 60.0,
            "flagged_gt5pct": False,
            "label": "[MT]",
        }
    n_out = int((~w["busy_in_pin"]).sum())
    n_low = int((w["active_pin_perf"] < LOW_CLOCK_THRESH).sum())
    pct_out = 100.0 * n_out / n
    pct_low = 100.0 * n_low / n
    return {
        "session": session,
        "fork": fork_label,
        "n_samples": n,
        "n_outside_lp10_11": n_out,
        "pct_outside_lp10_11": pct_out,
        "n_low_clock_lt110": n_low,
        "pct_low_clock_lt110": pct_low,
        "perf_median": float(w["active_pin_perf"].median()),
        "perf_min": float(w["active_pin_perf"].min()),
        "duration_s": float(duration_s),
        "duration_min": float(duration_s / 60.0),
        "flagged_gt5pct": bool((pct_out > FLAG_PCT_THRESH) or (pct_low > FLAG_PCT_THRESH)),
        "label": "[MT]",
    }


def analyze_env_session(session: str, session_dir: Path, env_specs: list[tuple[str, Path]]) -> list[dict]:
    """Phân tích một phiên có danh sách (fork_label, env_path)."""
    tp = load_session_typeperf(session_dir)
    rows = []
    mask_all = np.zeros(len(tp), dtype=bool)
    total_dur_s = 0.0

    for fork_label, env_path in env_specs:
        e = parse_env(env_path)
        t0, t1 = e["start"], e["end"]
        if t1 is None:
            raise ValueError(f"Thiếu end_time trong {env_path}")
        dur_s = (t1 - t0).total_seconds()
        total_dur_s += dur_s
        m = (tp["utc"] > t0) & (tp["utc"] <= t1)
        mask_all |= m.to_numpy()
        rows.append(summarize_window(session, fork_label, tp[m], dur_s))

    rows.append(summarize_window(session, "ALL", tp[mask_all], total_dur_s))
    return rows


def analyze_jmh_session(session_dir: Path, active_util_thresh: float = 50.0,
                        session_name: str = "JMH") -> list[dict]:
    """Phân tích phiên JMH (không có env_fork*.txt): cửa sổ [first, last] có pin_util >= active_util_thresh."""
    tp = load_session_typeperf(session_dir)
    active_idx = tp.index[tp["pin_util"] >= active_util_thresh]
    if len(active_idx) == 0:
        return [summarize_window(session_name, "ALL", tp.iloc[0:0], 0.0)]
    i0, i1 = int(active_idx[0]), int(active_idx[-1])
    w = tp.iloc[i0:i1 + 1]
    dur_s = (w["utc"].iloc[-1] - w["utc"].iloc[0]).total_seconds() + 1.0
    return [summarize_window(session_name, "ALL", w, dur_s)]


def run_self_check() -> int:
    """Tự kiểm trên dữ liệu giai đoạn 1 (results_run3/, KHÔNG chạm dữ liệu giai đoạn 2)."""
    print("=" * 80)
    print("SELF-CHECK session_quality.py TRÊN DỮ LIỆU GIAI ĐOẠN 1 (results_run3/)")
    print("=" * 80)
    run3_dir = PROJECT_ROOT / "results_run3"
    envs = sorted(run3_dir.glob("env_fork*.txt"))
    specs = []
    for p in envs:
        m = re.search(r"env_fork(\d+)", p.name)
        specs.append((f"fork{m.group(1)}", p))
    rows = analyze_env_session("run3_gd1", run3_dir, specs)
    df = pd.DataFrame(rows)
    print(df[["session", "fork", "n_samples", "pct_outside_lp10_11", "pct_low_clock_lt110",
              "perf_median", "perf_min", "duration_min", "flagged_gt5pct"]].to_string(index=False))
    assert len(df) == 4, f"Kỳ vọng 4 hàng (3 fork + ALL), thực tế {len(df)}"
    assert (df["n_samples"] > 1000).all(), "Số mẫu typeperf bất thường"
    print("PASS: session_quality.py hoạt động đúng trên results_run3/ (giai đoạn 1).")
    return 0


def run_phase2(out_dir: Path) -> pd.DataFrame:
    """Chạy kiểm tra chất lượng cho đủ 5 phiên giai đoạn 2."""
    all_rows: list[dict] = []

    # 1. S1: results_run5_s1
    s1_dir = PROJECT_ROOT / "results_run5_s1"
    s1_specs = [(f"fork{f}", s1_dir / f"env_fork{f}.txt") for f in range(1, 6)]
    all_rows.extend(analyze_env_session("S1", s1_dir, s1_specs))

    # 2. S2: results_run5_s2
    s2_dir = PROJECT_ROOT / "results_run5_s2"
    s2_specs = [(f"fork{f}", s2_dir / f"env_fork{f}.txt") for f in range(1, 6)]
    all_rows.extend(analyze_env_session("S2", s2_dir, s2_specs))

    # 3. DV2: results_doubling_v2
    dv2_dir = PROJECT_ROOT / "results_doubling_v2"
    dv2_specs = [(f"fork{f}", dv2_dir / f"env_fork{f}.txt") for f in range(1, 6)]
    all_rows.extend(analyze_env_session("DV2", dv2_dir, dv2_specs))

    # 4. D3: results_d3/{integer,double,int}/env_fork{1..3}.txt
    d3_dir = PROJECT_ROOT / "results_d3"
    d3_specs = []
    for key in ["integer", "double", "int"]:
        for f in range(1, 4):
            d3_specs.append((f"{key}_fork{f}", d3_dir / key / f"env_fork{f}.txt"))
    all_rows.extend(analyze_env_session("D3", d3_dir, d3_specs))

    # 5. JMH: results_jmh
    jmh_dir = PROJECT_ROOT / "results_jmh"
    all_rows.extend(analyze_jmh_session(jmh_dir))

    df = pd.DataFrame(all_rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "p2_session_quality.csv"
    df.to_csv(out_path, index=False)

    print("=" * 90)
    print("CHẤT LƯỢNG 5 PHIÊN ĐO GIAI ĐOẠN 2 [MT]")
    print("=" * 90)
    print(df[["session", "fork", "n_samples", "pct_outside_lp10_11", "pct_low_clock_lt110",
              "perf_median", "perf_min", "duration_min", "flagged_gt5pct"]].to_string(index=False))

    # Đối chiếu Quy tắc A (dung sai ±0.3 điểm %)
    print("\nĐỐI CHIẾU QUY TẮC A (T10 §4.7, dung sai ±0.3 điểm %):")
    print(f"{'Phiên/Fork':<14s} {'Chỉ số':<22s} {'Tính được':>10s} {'Tham chiếu':>10s} {'Chênh':>10s} {'Trạng thái':>10s}")
    all_ok = True
    for (sess, fk), ref_map in REF_PHASE2.items():
        sub = df[(df["session"] == sess) & (df["fork"] == fk)]
        assert len(sub) == 1, f"Không tìm thấy ({sess}, {fk})"
        row = sub.iloc[0]
        for col, ref_val in ref_map.items():
            calc_val = float(row[col])
            diff = abs(calc_val - ref_val)
            ok = diff <= 0.30
            if not ok:
                all_ok = False
            print(f"{sess + '/' + fk:<14s} {col:<22s} {calc_val:10.2f} {ref_val:10.2f} {diff:10.2f} {'OK' if ok else 'WARN':>10s}")

    # Kiểm mọi phiên/fork khác S1 fork4 đều 0% xung thấp
    others = df[~((df["session"] == "S1") & (df["fork"].isin(["fork4", "ALL"])))]
    max_other_low = float(others["pct_low_clock_lt110"].max())
    print(f"Max % xung < 110% ngoài S1/fork4: {max_other_low:.4f}% (tham chiếu: 0.00%)")
    if not all_ok:
        print("CẢNH BÁO: Có chỉ số lệch quá ±0.3 điểm % so với tham chiếu — kiểm tra lại định nghĩa cửa sổ!")
    print(f"Đã ghi: {out_path}")
    return df


def run_phase2b(out_dir: Path | None = None) -> pd.DataFrame:
    """Chạy kiểm tra chất lượng cho giai đoạn 2b: S6 (lần 1, 2, 3) và S7 (6 fork + ALL). KHÔNG đọc Score hay r."""
    all_rows: list[dict] = []

    # S6 lần 1, 2 (bị loại) và lần 3 (hợp lệ) — chỉ đọc typeperf*.csv
    all_rows.extend(analyze_jmh_session(PROJECT_ROOT / "results_jmh_v2_rejected_lowclock", session_name="S6_run1"))
    all_rows.extend(analyze_jmh_session(PROJECT_ROOT / "results_jmh_v2_rejected_lowclock_2", session_name="S6_run2"))
    all_rows.extend(analyze_jmh_session(PROJECT_ROOT / "results_jmh_v2", session_name="S6_run3"))

    # S7: results_int_ext (6 fork)
    s7_dir = PROJECT_ROOT / "results_int_ext"
    s7_specs = [(f"fork{f}", s7_dir / f"env_fork{f}.txt") for f in range(1, 7)]
    all_rows.extend(analyze_env_session("S7", s7_dir, s7_specs))

    df = pd.DataFrame(all_rows)
    df["status"] = np.where(
        (df["pct_outside_lp10_11"] > REJECT_PCT_THRESH) | (df["pct_low_clock_lt110"] > REJECT_PCT_THRESH),
        "LOẠI",
        "HỢP LỆ",
    )

    print("=" * 98)
    print("CHẤT LƯỢNG CÁC PHIÊN GIAI ĐOẠN 2b (S6 lần 1-3, S7) [MT]")
    print("=" * 98)
    print(df[["session", "fork", "n_samples", "pct_outside_lp10_11", "pct_low_clock_lt110",
              "perf_median", "perf_min", "duration_min", "flagged_gt5pct", "status"]].to_string(index=False))

    print("\nĐỐI CHIẾU QUY TẮC A GIAI ĐOẠN 2b (T12 §3.4, dung sai ±0.3 điểm %):")
    print(f"{'Phiên/Fork':<14s} {'Chỉ số':<22s} {'Tính được':>10s} {'Tham chiếu':>10s} {'Chênh':>10s} {'Trạng thái':>10s}")
    all_ok = True
    for (sess, fk), ref_map in REF_PHASE2B.items():
        sub = df[(df["session"] == sess) & (df["fork"] == fk)]
        assert len(sub) == 1, f"Không tìm thấy ({sess}, {fk})"
        row = sub.iloc[0]
        for col, ref_val in ref_map.items():
            calc_val = float(row[col])
            diff = abs(calc_val - ref_val)
            ok = diff <= 0.30
            if not ok:
                all_ok = False
            print(f"{sess + '/' + fk:<14s} {col:<22s} {calc_val:10.2f} {ref_val:10.2f} {diff:10.2f} {'OK' if ok else 'FAIL':>10s}")
    assert all_ok, "DỪNG: Có chỉ số chất lượng phiên 2b lệch quá ±0.3 điểm % so với tham chiếu!"

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "p2b_session_quality.csv"
        df.to_csv(out_path, index=False)
        print(f"Đã ghi: {out_path}")
    return df


def parse_args():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--self-check", action="store_true",
                    help="Chạy tự kiểm trên dữ liệu giai đoạn 1 (results_run3/)")
    ap.add_argument("--phase2b", action="store_true",
                    help="Chạy kiểm tra chất lượng giai đoạn 2b (S6 lần 1-3, S7) -> p2b_session_quality.csv")
    ap.add_argument("--out", type=Path, default=Path("results_phase2/analysis/tables"),
                    help="Thư mục xuất CSV (mặc định: results_phase2/analysis/tables)")
    return ap.parse_args()


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    if args.self_check:
        sys.exit(run_self_check())
    if args.phase2b:
        run_phase2b(args.out)
        return
    run_phase2(args.out)


if __name__ == "__main__":
    main()
