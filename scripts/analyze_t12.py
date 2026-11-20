#!/usr/bin/env python3
"""
scripts/analyze_t12.py — Phân tích giai đoạn 2b theo Hợp đồng T11 + Phụ lục A1–A3 (J1–J7, I1–I4, B1–B2).

Tuân thủ:
  - Hợp đồng: preregistration/T11_contract.md + T11_addendum.md (commit ff163ba, b4bc8fa)
  - Định nghĩa đã chốt: (đề bài nội bộ) §2 và T10_analysis.md §2
  - Nhãn đầu ra: [ĐK], [KP], [MT]
  - Bootstrap mặc định: B = 10 000, seed gốc = 20261118 (RNG riêng cho từng bảng, ghi trong run_log.txt)
  - KHÔNG phân tích Score/r của các thư mục results_jmh_v2_rejected_lowclock*/
  - D1 (S8) đã HỦY theo §3 hợp đồng: B1, B2 ghi "KHÔNG THỰC HIỆN"

Cách chạy (từ thư mục gốc dự án):
    python scripts/analyze_t12.py --self-check
    python scripts/analyze_t12.py --out results_phase2b/analysis
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from scripts.analyze_t10 import (
    D3_KEYS,
    THREE_SCALE_LABELS,
    TeeStream,
    boot_one_tier,
    boot_two_tier,
    build_A_tensor,
    compute_paired_A,
    load_raw_dir,
    parse_jmh_float,
    summarize_group_r,
)
from scripts.predict_t09 import compress_range
from scripts.session_quality import run_phase2, run_phase2b

# ──────────────────────────────────────────────────────────────── hằng số thiết kế
DEFAULT_B = 10_000
DEFAULT_SEED = 20261118
T10_SEED = 20261117

JMH_NS = [4096, 65536, 524288]
JMH_CUTOFFS = [1, 7, 10, 30]
JMH_NONBASE_CUTOFFS = [7, 10, 30]
INT_EXT_GRID = list(range(1, 33)) + [40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 256]
REF_S7_ROWS = 154_800  # 6 forks * 43 cutoffs * 600 measurements


# ──────────────────────────────────────────────────────────────── đọc & bootstrap JMH JSON

def load_jmh_json_files(paths: list[Path], expected_configs: int | None = None,
                        expected_forks: int = 3, expected_iters: int = 10) -> tuple[dict, float]:
    """
    Đọc danh sách tệp JMH JSON (-rf json).
    Kiểm: số cấu hình, mỗi cấu hình có đúng expected_forks x expected_iters trong primaryMetric.rawData,
    và primaryMetric.score khớp trung bình cộng toàn bộ giá trị (sai số tương đối <= 1e-9).
    Trả về (cfg_map, max_rel_diff) với khóa (input, profile, reset, n, cutoff).
    """
    cfg_map = {}
    max_rel_diff = 0.0
    for p in paths:
        entries = json.loads(p.read_text(encoding="utf-8"))
        for entry in entries:
            params = entry["params"]
            key = (
                str(params["input"]),
                str(params["profile"]),
                str(params["reset"]),
                int(params["n"]),
                int(params["cutoff"]),
            )
            assert key not in cfg_map, f"Trùng cấu hình JMH: {key}"
            pm = entry["primaryMetric"]
            raw_data = pm["rawData"]
            assert len(raw_data) == expected_forks, f"{key}: kỳ vọng {expected_forks} fork, thực tế {len(raw_data)}"
            fork_means = []
            all_vals = []
            for fi, flist in enumerate(raw_data):
                assert len(flist) == expected_iters, f"{key} fork {fi}: kỳ vọng {expected_iters} vòng, thực tế {len(flist)}"
                arr = np.asarray(flist, dtype=float)
                fork_means.append(float(arr.mean()))
                all_vals.extend(arr.tolist())
            score_calc = float(np.mean(all_vals))
            score_json = float(pm["score"])
            rel_diff = abs(score_calc - score_json) / max(abs(score_json), 1e-30)
            max_rel_diff = max(max_rel_diff, rel_diff)
            assert rel_diff <= 1e-9, f"{key}: score lệch json ({score_calc} vs {score_json}, rel={rel_diff:.2e})"
            cfg_map[key] = {
                "input": key[0],
                "profile": key[1],
                "reset": key[2],
                "N": key[3],
                "cutoff": key[4],
                "score": score_calc,
                "score_json": score_json,
                "score_error_999": float(pm.get("scoreError", float("nan"))),
                "unit": str(pm.get("scoreUnit", "")),
                "fork_means": np.asarray(fork_means, dtype=float),
                "n_forks": len(fork_means),
                "n_samples": len(all_vals),
            }
    if expected_configs is not None:
        assert len(cfg_map) == expected_configs, f"Kỳ vọng {expected_configs} cấu hình JMH, thực tế {len(cfg_map)}"
    return cfg_map, max_rel_diff


def boot_jmh_score(fork_means: np.ndarray, B: int, rng: np.random.Generator) -> np.ndarray:
    """Bootstrap JMH trên F fork (mặc định 3): rút F fork có hoàn lại, lấy trung bình."""
    F = len(fork_means)
    idx = rng.integers(0, F, size=(B, F))
    return fork_means[idx].mean(axis=1)


def compute_jmh_csv_ratios(jmh_csv_path: Path) -> pd.DataFrame:
    """Tính r_JMH(N, c) = Score(N, c) / Score(N, 1) từ tệp JMH CSV (T08, dùng cho self-check #2 và bảng đối chiếu)."""
    df_j = pd.read_csv(jmh_csv_path)
    col_score = [c for c in df_j.columns if c.strip() == "Score"][0]
    col_n = [c for c in df_j.columns if c.strip().lower().endswith("n") and "param" in c.lower()][0]
    col_c = [c for c in df_j.columns if "cutoff" in c.lower() and "param" in c.lower()][0]
    df_j = df_j.copy()
    df_j["N"] = df_j[col_n].astype(int)
    df_j["cutoff"] = df_j[col_c].astype(int)
    df_j["score_us"] = df_j[col_score].map(parse_jmh_float)
    base_map = df_j[df_j["cutoff"] == 1].set_index("N")["score_us"].to_dict()
    df_j["r_jmh"] = df_j.apply(lambda r: float(r["score_us"]) / float(base_map[int(r["N"])]), axis=1)
    return df_j[["N", "cutoff", "score_us", "r_jmh"]]


def load_t11_references(ref_path: Path) -> dict:
    """Đọc T11_reference_values.csv thành dict tra cứu theo key."""
    df = pd.read_csv(ref_path)
    return df.set_index("key")["value"].to_dict()


def fmt_verdict(ok: bool) -> str:
    return "ĐẠT" if ok else "KHÔNG ĐẠT"


# ──────────────────────────────────────────────────────────────── TỰ KIỂM (§3, TRƯỚC KHI ĐỌC SCORE/r 2b)

def run_self_check(B: int = DEFAULT_B) -> int:
    """
    Chạy 4 hạng mục tự kiểm (T12 §3) TRƯỚC khi đọc Score hay r của results_jmh_v2/ và results_int_ext/.
    Chỉ đọc: results_d3/, results_jmh/ (T08), JSON tổng hợp, và typeperf/env cho session_quality.
    """
    print("=" * 96)
    print("T12 --self-check: TỰ KIỂM 4 HẠNG MỤC (KHÔNG ĐỌC Score HAY r CỦA GIAI ĐOẠN 2b)")
    print("=" * 96)
    summary = []

    # ── Check 1: Bootstrap hai tầng + c* trên results_d3/int/ tái lập p2_d3_best.csv
    print("\n[Check 1] Bootstrap hai tầng + c* trên results_d3/int/ tái lập p2_d3_best.csv (int)")
    ref_d3_best = pd.read_csv(PROJECT_ROOT / "results_phase2/analysis/tables/p2_d3_best.csv")
    ref_int = ref_d3_best[ref_d3_best["key"] == "int"].set_index("scale")

    # (1a) Chạy trực tiếp trên results_d3/int/ với seed 20261117
    raw_d3_int = load_raw_dir(PROJECT_ROOT / "results_d3/int", "D3/int (GĐ2)", expected_rows=66_600)
    obs_int, dfA_int = compute_paired_A(raw_d3_int)
    _, df_best_int_direct, _ = summarize_group_r(
        dfA_int, obs_int, B, seed_two=T10_SEED, seed_one=T10_SEED + 1, label="[ĐK]",
    )
    b_dir = df_best_int_direct.set_index("scale")
    max_diff_r = 0.0
    max_diff_ci_direct = 0.0
    for scl in THREE_SCALE_LABELS:
        c_calc, c_ref = int(b_dir.loc[scl, "c_star"]), int(ref_int.loc[scl, "c_star"])
        r_calc, r_ref = float(b_dir.loc[scl, "r_star"]), float(ref_int.loc[scl, "r_star"])
        lo_c, hi_c = float(b_dir.loc[scl, "ci2_lo"]), float(b_dir.loc[scl, "ci2_hi"])
        lo_r, hi_r = float(ref_int.loc[scl, "ci2_lo"]), float(ref_int.loc[scl, "ci2_hi"])
        dr = abs(r_calc - r_ref)
        dci = max(abs(lo_c - lo_r), abs(hi_c - hi_r))
        max_diff_r = max(max_diff_r, dr)
        max_diff_ci_direct = max(max_diff_ci_direct, dci)
        print(f"  [direct seed=20261117] {scl}: c*={c_calc} (ref {c_ref}) | r*={r_calc:.9f} (ref {r_ref:.9f}, diff={dr:.2e}) | CI=[{lo_c:.6f},{hi_c:.6f}] vs ref [{lo_r:.6f},{hi_r:.6f}] (diff={dci:.2e})")
        assert c_calc == c_ref, f"c* không khớp ở {scl}"
    assert max_diff_r < 1e-9, f"r_star không khớp: {max_diff_r}"

    # (1b) Khớp chính xác luồng RNG của analyze_t10.py (seed = 20261117 + 7 qua integer -> double -> int)
    rng_exact = np.random.default_rng(T10_SEED + 7)
    max_diff_ci_exact = 0.0
    for key in D3_KEYS:
        raw_k = load_raw_dir(PROJECT_ROOT / "results_d3" / key, f"D3/{key} (exact-RNG)", expected_rows=66_600)
        _, dfA_k = compute_paired_A(raw_k)
        for scl in THREE_SCALE_LABELS:
            subA = dfA_k[dfA_k["scale_label"] == scl]
            A, _, _, cutoffs = build_A_tensor(subA)
            pt_r = np.exp(A.mean(axis=(0, 1)))
            bt2 = boot_two_tier(A, B, rng_exact)
            lo2, hi2 = np.percentile(bt2, [2.5, 97.5], axis=0)
            if key == "int":
                bi = int(np.argmin(pt_r))
                lo_e, hi_e = math.exp(lo2[bi]), math.exp(hi2[bi])
                lo_r, hi_r = float(ref_int.loc[scl, "ci2_lo"]), float(ref_int.loc[scl, "ci2_hi"])
                de = max(abs(lo_e - lo_r), abs(hi_e - hi_r))
                max_diff_ci_exact = max(max_diff_ci_exact, de)
                print(f"  [exact T10 RNG stream] {scl}: CI=[{lo_e:.9f},{hi_e:.9f}] vs ref [{lo_r:.9f},{hi_r:.9f}] (diff={de:.2e})")
    assert max_diff_ci_exact < 1e-9, f"CI exact stream không khớp: {max_diff_ci_exact}"
    assert max_diff_ci_direct < 0.003, f"CI direct seed 20261117 lệch bất thường: {max_diff_ci_direct}"
    summary.append(("1. D3/int c*, r*, CI2 vs p2_d3_best", "128/128/64", "128/128/64", f"r:{max_diff_r:.1e}; CI(exact):{max_diff_ci_exact:.1e}", "PASS"))

    # ── Check 2: Mã r JMH chạy trên results_jmh/jmh_results.csv tái lập p2_jmh.csv (9 ô)
    print("\n[Check 2] Mã r JMH trên results_jmh/jmh_results.csv (T08) tái lập p2_jmh.csv (9 ô)")
    df_t08_calc = compute_jmh_csv_ratios(PROJECT_ROOT / "results_jmh/jmh_results.csv")
    df_t08_ref = pd.read_csv(PROJECT_ROOT / "results_phase2/analysis/tables/p2_jmh.csv")
    m2 = pd.merge(
        df_t08_calc[df_t08_calc["cutoff"].isin(JMH_NONBASE_CUTOFFS)],
        df_t08_ref[df_t08_ref["cutoff"].isin(JMH_NONBASE_CUTOFFS)][["N", "cutoff", "r_jmh"]],
        on=["N", "cutoff"],
        suffixes=("_calc", "_ref"),
    )
    assert len(m2) == 9
    max_diff_jmh = float(np.max(np.abs(m2["r_jmh_calc"] - m2["r_jmh_ref"])))
    for row in m2.itertuples(index=False):
        print(f"  N={row.N:6d} c={row.cutoff:2d}: calc={row.r_jmh_calc:.9f} | ref={row.r_jmh_ref:.9f} | diff={abs(row.r_jmh_calc - row.r_jmh_ref):.2e}")
    assert max_diff_jmh < 1e-9, f"Check 2 FAIL: max_diff={max_diff_jmh}"
    summary.append(("2. JMH T08 r_jmh (9 ô)", "9/9 khớp", "p2_jmh.csv", f"max={max_diff_jmh:.2e}", "PASS"))

    # ── Check 3: Bộ đọc JSON trên tệp JSON TỔNG HỢP (2 cấu hình, fork hằng số -> CI rộng 0)
    print("\n[Check 3] Bộ đọc JSON trên tệp JSON tổng hợp (2 cấu hình, fork hằng số -> độ rộng CI = 0)")
    syn_dir = PROJECT_ROOT / "results_smoke"
    syn_dir.mkdir(parents=True, exist_ok=True)
    syn_path = syn_dir / "t12_selfcheck_syn.json"
    syn_payload = [
        {
            "benchmark": "bench.MergeCutoffBenchmarkV2.sort",
            "mode": "avgt",
            "params": {"input": "same", "profile": "pure", "reset": "none", "n": "4096", "cutoff": "1"},
            "primaryMetric": {
                "score": 100.0,
                "scoreError": 0.0,
                "scoreUnit": "us/op",
                "rawData": [[100.0] * 10, [100.0] * 10, [100.0] * 10],
            },
        },
        {
            "benchmark": "bench.MergeCutoffBenchmarkV2.sort",
            "mode": "avgt",
            "params": {"input": "same", "profile": "pure", "reset": "none", "n": "4096", "cutoff": "30"},
            "primaryMetric": {
                "score": 80.0,
                "scoreError": 0.0,
                "scoreUnit": "us/op",
                "rawData": [[80.0] * 10, [80.0] * 10, [80.0] * 10],
            },
        },
    ]
    syn_path.write_text(json.dumps(syn_payload), encoding="utf-8")
    syn_map, syn_rel = load_jmh_json_files([syn_path], expected_configs=2)
    s1 = syn_map[("same", "pure", "none", 4096, 1)]
    s30 = syn_map[("same", "pure", "none", 4096, 30)]
    r_syn = s30["score"] / s1["score"]
    rng_syn = np.random.default_rng(DEFAULT_SEED)
    b1 = boot_jmh_score(s1["fork_means"], B, rng_syn)
    b30 = boot_jmh_score(s30["fork_means"], B, rng_syn)
    lo_s, hi_s = np.percentile(b30 / b1, [2.5, 97.5])
    ci_w = float(hi_s - lo_s)
    print(f"  Score(1)={s1['score']:.6f} (ref 100.0), Score(30)={s30['score']:.6f} (ref 80.0), r={r_syn:.6f} (ref 0.80)")
    print(f"  Bootstrap CI(r)=[{lo_s:.12f}, {hi_s:.12f}], width={ci_w:.2e}, max_rel_diff={syn_rel:.2e}")
    assert abs(s1["score"] - 100.0) < 1e-12 and abs(s30["score"] - 80.0) < 1e-12
    assert abs(r_syn - 0.80) < 1e-12 and ci_w == 0.0
    summary.append(("3. JSON tổng hợp (Score, r, CI width=0)", f"r={r_syn:.2f}, w={ci_w:.1e}", "0.80, w=0", f"diff={abs(r_syn-0.8):.1e}", "PASS"))

    # ── Check 4: session_quality mở rộng (GĐ2 không đổi + GĐ2b khớp CONTEXT ±0.3 điểm %)
    print("\n[Check 4] session_quality mở rộng: tái lập p2_session_quality.csv và kiểm S7, S6 (lần 1, 2, 3)")
    ref_p2_sq = pd.read_csv(PROJECT_ROOT / "results_phase2/analysis/tables/p2_session_quality.csv")
    tmp_sq_dir = syn_dir / "t12_sq_check"
    df_p2_recalc = run_phase2(tmp_sq_dir)
    s1_old = float(ref_p2_sq[(ref_p2_sq["session"] == "S1") & (ref_p2_sq["fork"] == "ALL")]["pct_low_clock_lt110"].iloc[0])
    s1_new = float(df_p2_recalc[(df_p2_recalc["session"] == "S1") & (df_p2_recalc["fork"] == "ALL")]["pct_low_clock_lt110"].iloc[0])
    jmh_old = float(ref_p2_sq[(ref_p2_sq["session"] == "JMH") & (ref_p2_sq["fork"] == "ALL")]["pct_low_clock_lt110"].iloc[0])
    jmh_new = float(df_p2_recalc[(df_p2_recalc["session"] == "JMH") & (df_p2_recalc["fork"] == "ALL")]["pct_low_clock_lt110"].iloc[0])
    print(f"  GĐ2 S1 low_clock: calc={s1_new:.6f}% | ref={s1_old:.6f}% | diff={abs(s1_new - s1_old):.2e}")
    print(f"  GĐ2 JMH low_clock: calc={jmh_new:.6f}% | ref={jmh_old:.6f}% | diff={abs(jmh_new - jmh_old):.2e}")
    assert abs(s1_new - s1_old) < 1e-9 and abs(jmh_new - jmh_old) < 1e-9

    # GĐ2b typeperf + env only (run_phase2b tự assert dung sai ±0.3 điểm % với REF_PHASE2B)
    df_p2b_sq = run_phase2b(out_dir=None)
    assert len(df_p2b_sq) == 10  # S6_run1, S6_run2, S6_run3, S7 fork1..6 + ALL
    summary.append(("4. session_quality (GĐ2 + S6/S7 typeperf)", "8/8 mốc 2b OK", "CONTEXT ±0.3%", "GĐ2 diff=0.0e+00", "PASS"))

    print("\n" + "=" * 96)
    print("TỔNG KẾT --self-check (4/4 PASS):")
    print(f"{'Hạng mục':<44s} {'Tính được':<18s} {'Tham chiếu':<16s} {'Chênh':<22s} {'KQ'}")
    for item in summary:
        print(f"{item[0]:<44s} {item[1]:<18s} {item[2]:<16s} {item[3]:<22s} {item[4]}")
    print("=" * 96)
    return 0


# ──────────────────────────────────────────────────────────────── PHÂN TÍCH GIAI ĐOẠN 2b (§4)

def run_phase2b_analysis(out_dir: Path, B: int = DEFAULT_B, base_seed: int = DEFAULT_SEED) -> int:
    """Chạy toàn bộ phân tích giai đoạn 2b (J1–J7, I1–I4, B1–B2, [MT], [KP]) và ghi CSV + run_log.txt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "run_log.txt"

    orig_stdout = sys.stdout
    log_f = log_path.open("w", encoding="utf-8")
    sys.stdout = TeeStream(orig_stdout, log_f)
    try:
        return _run_phase2b_body(tables_dir, B, base_seed)
    finally:
        sys.stdout = orig_stdout
        log_f.close()


def _run_phase2b_body(tables_dir: Path, B: int, base_seed: int) -> int:
    print("=" * 98)
    print("T12: PHÂN TÍCH GIAI ĐOẠN 2b THEO HỢP ĐỒNG T11 + PHỤ LỤC A1–A3 (ff163ba, b4bc8fa)")
    print(f"Bootstrap: B = {B}, seed gốc = {base_seed}")
    print("=" * 98)

    seeds = {
        "jmh_scores_boot": base_seed,
        "jmh_r_boot": base_seed + 1,
        "jmh_J1_boot": base_seed + 2,
        "jmh_J2_boot": base_seed + 3,
        "jmh_J3_boot": base_seed + 4,
        "jmh_J4_boot": base_seed + 5,
        "jmh_J5_boot": base_seed + 6,
        "jmh_J6_boot": base_seed + 7,
        "jmh_J7_boot": base_seed + 8,
        "jmh_effects_boot": base_seed + 9,
        "int_r_by_cutoff_two": base_seed + 10,
        "int_r_by_cutoff_one": base_seed + 11,
        "int_I4_boot": base_seed + 12,
    }
    print("\nDanh sách seed bootstrap theo bảng:")
    for k, v in seeds.items():
        print(f"  {k:<24s}: {v}")

    refs = load_t11_references(PROJECT_ROOT / "preregistration/T11_reference_values.csv")

    # ── 1. Nạp JMH v2 (chỉ phiên S6 lần 3 hợp lệ) & kiểm tra toàn vẹn (§1)
    print("\n" + "-" * 98)
    print("1. NẠP DỮ LIỆU JMH V2 (results_jmh_v2/ — S6 LẦN 3 HỢP LỆ)")
    print("-" * 98)
    jmh_v2_dir = PROJECT_ROOT / "results_jmh_v2"
    cfg_map, max_rel_diff = load_jmh_json_files(
        [jmh_v2_dir / "jmh_v2.json", jmh_v2_dir / "jmh_v2_gc.json"],
        expected_configs=72, expected_forks=3, expected_iters=10,
    )
    print(f"  [Quy tắc A] JMH v2: đọc đúng {len(cfg_map)}/72 cấu hình (48 reset=none + 24 reset=gc, mixed), 3 fork x 10 vòng")
    print(f"  [Quy tắc A] Chênh lệch tương đối lớn nhất |Score_calc - Score_json|/Score_json = {max_rel_diff:.3e} (dung sai 1e-9)")

    # ── 4.1 p2b_jmh_scores.csv & p2b_jmh_r.csv [MT]
    rng_sc = np.random.default_rng(seeds["jmh_scores_boot"])
    score_rows = []
    for key in sorted(cfg_map.keys()):
        c = cfg_map[key]
        bt = boot_jmh_score(c["fork_means"], B, rng_sc)
        lo, hi = np.percentile(bt, [2.5, 97.5])
        score_rows.append({
            "input": c["input"],
            "profile": c["profile"],
            "reset": c["reset"],
            "N": c["N"],
            "cutoff": c["cutoff"],
            "score_us": c["score"],
            "fork1_mean_us": float(c["fork_means"][0]),
            "fork2_mean_us": float(c["fork_means"][1]),
            "fork3_mean_us": float(c["fork_means"][2]),
            "ci_lo": float(lo),
            "ci_hi": float(hi),
            "score_error_999_us": c["score_error_999"],
            "n_forks": c["n_forks"],
            "n_samples": c["n_samples"],
            "label": "[MT]",
        })
    df_jmh_scores = pd.DataFrame(score_rows)
    df_jmh_scores.to_csv(tables_dir / "p2b_jmh_scores.csv", index=False)

    rng_r = np.random.default_rng(seeds["jmh_r_boot"])
    r_rows = []
    conds = sorted({(k[0], k[1], k[2], k[3]) for k in cfg_map.keys()})
    for inp, prof, rst, n in conds:
        base = cfg_map[(inp, prof, rst, n, 1)]
        for cut in JMH_CUTOFFS:
            cur = cfg_map[(inp, prof, rst, n, cut)]
            r_pt = cur["score"] / base["score"]
            if cut == 1:
                lo_r, hi_r = 1.0, 1.0
            else:
                b_c = boot_jmh_score(cur["fork_means"], B, rng_r)
                b_1 = boot_jmh_score(base["fork_means"], B, rng_r)
                lo_r, hi_r = np.percentile(b_c / b_1, [2.5, 97.5])
            r_rows.append({
                "input": inp,
                "profile": prof,
                "reset": rst,
                "N": n,
                "cutoff": cut,
                "score_us": cur["score"],
                "base_score_us": base["score"],
                "r": float(r_pt),
                "ci_lo": float(lo_r),
                "ci_hi": float(hi_r),
                "label": "[MT]",
            })
    df_jmh_r = pd.DataFrame(r_rows)
    df_jmh_r.to_csv(tables_dir / "p2b_jmh_r.csv", index=False)
    r_idx = df_jmh_r.set_index(["input", "profile", "reset", "N", "cutoff"])

    # ── 4.2 Kiểm định J1–J7 [ĐK]
    print("\n" + "-" * 98)
    print("4.2 KIỂM ĐỊNH JMH V2: J1–J7 [ĐK]")
    print("-" * 98)

    # J1: same + pure + none vs r_T08 (<= 0.03 ở 9/9 ô)
    rng_j1 = np.random.default_rng(seeds["jmh_J1_boot"])
    j1_rows = []
    for n in JMH_NS:
        for cut in JMH_NONBASE_CUTOFFS:
            c_cur = cfg_map[("same", "pure", "none", n, cut)]
            c_1 = cfg_map[("same", "pure", "none", n, 1)]
            r_val = c_cur["score"] / c_1["score"]
            r_t08 = float(refs[f"r_T08_N{n}_c{cut}"])
            diff = r_val - r_t08
            abs_diff = abs(diff)
            bt_r = boot_jmh_score(c_cur["fork_means"], B, rng_j1) / boot_jmh_score(c_1["fork_means"], B, rng_j1)
            lo_r, hi_r = np.percentile(bt_r, [2.5, 97.5])
            j1_rows.append({
                "N": n, "cutoff": cut, "r_same_pure_none": r_val,
                "ci_lo": float(lo_r), "ci_hi": float(hi_r),
                "r_T08": r_t08, "diff": diff, "abs_diff": abs_diff,
                "threshold": 0.03, "condition_met": bool(abs_diff <= 0.03), "label": "[ĐK]",
            })
    df_j1 = pd.DataFrame(j1_rows)
    df_j1.to_csv(tables_dir / "p2b_J1.csv", index=False)
    j1_pass = bool(df_j1["condition_met"].all())

    # J2: pure + none, N = 4096: (a) r(fresh,c) - r(same,c) >= 0.10 (c=7,10,30); (b) Score(fresh,30)/Score(same,30) >= 1.30
    rng_j2 = np.random.default_rng(seeds["jmh_J2_boot"])
    j2_rows = []
    for cut in JMH_NONBASE_CUTOFFS:
        f_c = cfg_map[("fresh", "pure", "none", 4096, cut)]
        f_1 = cfg_map[("fresh", "pure", "none", 4096, 1)]
        s_c = cfg_map[("same", "pure", "none", 4096, cut)]
        s_1 = cfg_map[("same", "pure", "none", 4096, 1)]
        rf = f_c["score"] / f_1["score"]
        rs = s_c["score"] / s_1["score"]
        diff_r = rf - rs
        bt_rf = boot_jmh_score(f_c["fork_means"], B, rng_j2) / boot_jmh_score(f_1["fork_means"], B, rng_j2)
        bt_rs = boot_jmh_score(s_c["fork_means"], B, rng_j2) / boot_jmh_score(s_1["fork_means"], B, rng_j2)
        lo_d, hi_d = np.percentile(bt_rf - bt_rs, [2.5, 97.5])
        j2_rows.append({
            "subcase": f"diff_r_c{cut}", "N": 4096, "cutoff": cut,
            "val_fresh": rf, "val_same": rs, "metric_value": diff_r,
            "ci_lo": float(lo_d), "ci_hi": float(hi_d),
            "threshold": ">= 0.10", "condition_met": bool(diff_r >= 0.10), "label": "[ĐK]",
        })
    f30 = cfg_map[("fresh", "pure", "none", 4096, 30)]
    s30 = cfg_map[("same", "pure", "none", 4096, 30)]
    ratio_30 = f30["score"] / s30["score"]
    bt_rat = boot_jmh_score(f30["fork_means"], B, rng_j2) / boot_jmh_score(s30["fork_means"], B, rng_j2)
    lo_rat, hi_rat = np.percentile(bt_rat, [2.5, 97.5])
    j2_rows.append({
        "subcase": "ratio_Score_c30", "N": 4096, "cutoff": 30,
        "val_fresh": f30["score"], "val_same": s30["score"], "metric_value": ratio_30,
        "ci_lo": float(lo_rat), "ci_hi": float(hi_rat),
        "threshold": ">= 1.30", "condition_met": bool(ratio_30 >= 1.30), "label": "[ĐK]",
    })
    df_j2 = pd.DataFrame(j2_rows)
    df_j2.to_csv(tables_dir / "p2b_J2.csv", index=False)
    j2_pass = bool(df_j2["condition_met"].all())

    # J3: pure + none, N = 524288: |ln Score(fresh,c) - ln Score(same,c)| <= 0.03 (c=1,7,10,30)
    rng_j3 = np.random.default_rng(seeds["jmh_J3_boot"])
    j3_rows = []
    for cut in JMH_CUTOFFS:
        fc = cfg_map[("fresh", "pure", "none", 524288, cut)]
        sc = cfg_map[("same", "pure", "none", 524288, cut)]
        e_in = math.log(fc["score"]) - math.log(sc["score"])
        bt_e = np.log(boot_jmh_score(fc["fork_means"], B, rng_j3)) - np.log(boot_jmh_score(sc["fork_means"], B, rng_j3))
        lo_e, hi_e = np.percentile(bt_e, [2.5, 97.5])
        j3_rows.append({
            "N": 524288, "cutoff": cut, "score_fresh_us": fc["score"], "score_same_us": sc["score"],
            "ln_diff": e_in, "abs_ln_diff": abs(e_in),
            "ci_lo": float(lo_e), "ci_hi": float(hi_e),
            "threshold": 0.03, "condition_met": bool(abs(e_in) <= 0.03), "label": "[ĐK]",
        })
    df_j3 = pd.DataFrame(j3_rows)
    df_j3.to_csv(tables_dir / "p2b_J3.csv", index=False)
    j3_pass = bool(df_j3["condition_met"].all())

    # J4: fresh + mixed + none, N in {65536, 524288}: Score(30) < Score(10) < Score(7) < Score(1)
    rng_j4 = np.random.default_rng(seeds["jmh_J4_boot"])
    j4_rows = []
    for n in [65536, 524288]:
        sc = {c: cfg_map[("fresh", "mixed", "none", n, c)] for c in JMH_CUTOFFS}
        ok = bool(sc[30]["score"] < sc[10]["score"] < sc[7]["score"] < sc[1]["score"])
        b_s = {c: boot_jmh_score(sc[c]["fork_means"], B, rng_j4) for c in JMH_CUTOFFS}
        p_ord = float(np.mean((b_s[30] < b_s[10]) & (b_s[10] < b_s[7]) & (b_s[7] < b_s[1])))
        j4_rows.append({
            "N": n, "score_1": sc[1]["score"], "score_7": sc[7]["score"],
            "score_10": sc[10]["score"], "score_30": sc[30]["score"],
            "boot_prob_order_ok": p_ord,
            "threshold": "Score(30)<Score(10)<Score(7)<Score(1)",
            "condition_met": ok, "label": "[ĐK]",
        })
    df_j4 = pd.DataFrame(j4_rows)
    df_j4.to_csv(tables_dir / "p2b_J4.csv", index=False)
    j4_pass = bool(df_j4["condition_met"].all())

    def eval_h17_like(inp: str, prof: str, rst: str, seed_val: int) -> tuple[pd.DataFrame, bool]:
        rng = np.random.default_rng(seed_val)
        rows = []
        for n in JMH_NS:
            sc = {c: cfg_map[(inp, prof, rst, n, c)] for c in JMH_CUTOFFS}
            ord_ok = bool(sc[30]["score"] < sc[10]["score"] < sc[7]["score"] < sc[1]["score"])
            for cut in JMH_NONBASE_CUTOFFS:
                r_val = sc[cut]["score"] / sc[1]["score"]
                r_r5 = float(refs[f"r_Run5_N{n}_c{cut}"])
                diff = r_val - r_r5
                bt_r = boot_jmh_score(sc[cut]["fork_means"], B, rng) / boot_jmh_score(sc[1]["fork_means"], B, rng)
                lo_r, hi_r = np.percentile(bt_r, [2.5, 97.5])
                rows.append({
                    "subcase": f"diff_N{n}_c{cut}", "N": n, "cutoff": cut,
                    "r_jmh": r_val, "ci_lo": float(lo_r), "ci_hi": float(hi_r),
                    "r_Run5": r_r5, "diff": diff, "abs_diff": abs(diff),
                    "threshold": "<= 0.02", "condition_met": bool(abs(diff) <= 0.02), "label": "[ĐK]",
                })
            rows.append({
                "subcase": f"order_N{n}", "N": n, "cutoff": -1,
                "r_jmh": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"),
                "r_Run5": float("nan"), "diff": float("nan"), "abs_diff": float("nan"),
                "threshold": "Score(30)<Score(10)<Score(7)<Score(1)",
                "condition_met": ord_ok, "label": "[ĐK]",
            })
        df_out = pd.DataFrame(rows)
        return df_out, bool(df_out["condition_met"].all())

    # J5: fresh + mixed + none
    df_j5, j5_pass = eval_h17_like("fresh", "mixed", "none", seeds["jmh_J5_boot"])
    df_j5.to_csv(tables_dir / "p2b_J5.csv", index=False)

    # J6: same + mixed: Score(gc, 4096, 30) / Score(none, 4096, 30) >= 1.50
    rng_j6 = np.random.default_rng(seeds["jmh_J6_boot"])
    g30 = cfg_map[("same", "mixed", "gc", 4096, 30)]
    n30 = cfg_map[("same", "mixed", "none", 4096, 30)]
    rat_j6 = g30["score"] / n30["score"]
    bt_j6 = boot_jmh_score(g30["fork_means"], B, rng_j6) / boot_jmh_score(n30["fork_means"], B, rng_j6)
    lo_j6, hi_j6 = np.percentile(bt_j6, [2.5, 97.5])
    j6_pass = bool(rat_j6 >= 1.50)
    df_j6 = pd.DataFrame([{
        "N": 4096, "cutoff": 30,
        "score_gc_us": g30["score"], "score_none_us": n30["score"],
        "ratio_gc_over_none": rat_j6, "ci_lo": float(lo_j6), "ci_hi": float(hi_j6),
        "threshold": ">= 1.50", "condition_met": j6_pass, "label": "[ĐK]",
    }])
    df_j6.to_csv(tables_dir / "p2b_J6.csv", index=False)

    # J7: same + mixed + gc
    df_j7, j7_pass = eval_h17_like("same", "mixed", "gc", seeds["jmh_J7_boot"])
    df_j7.to_csv(tables_dir / "p2b_J7.csv", index=False)

    # Bảng 4 kết cục J2 x J6 (nguyên văn T11_addendum.md dòng 16)
    if j2_pass and not j6_pass:
        j2_j6_outcome = "J2 đạt + J6 không đạt → ủng hộ học nhánh"
    elif j6_pass and not j2_pass:
        j2_j6_outcome = "J6 đạt + J2 không đạt → ủng hộ trạng thái nguội"
    elif j2_pass and j6_pass:
        j2_j6_outcome = "cả hai đạt → cả hai cùng góp phần (không tách được tỉ trọng ngoài bảng mô tả)"
    else:
        j2_j6_outcome = "cả hai không đạt → chênh lệch T08 chưa giải thích được"

    print(f"  J1: {fmt_verdict(j1_pass)} ({int(df_j1['condition_met'].sum())}/9 ô <= 0.03, max={df_j1['abs_diff'].max():.4f})")
    print(f"  J2: {fmt_verdict(j2_pass)} ({int(df_j2['condition_met'].sum())}/4 điều kiện; ratio_c30={ratio_30:.4f})")
    print(f"  J3: {fmt_verdict(j3_pass)} ({int(df_j3['condition_met'].sum())}/4 ô <= 0.03, max={df_j3['abs_ln_diff'].max():.4f})")
    print(f"  J4: {fmt_verdict(j4_pass)} ({int(df_j4['condition_met'].sum())}/2 N đúng thứ tự)")
    print(f"  J5: {fmt_verdict(j5_pass)} ({int(df_j5['condition_met'].sum())}/12 điều kiện)")
    print(f"  J6: {fmt_verdict(j6_pass)} (ratio_gc/none={rat_j6:.4f}, CI=[{lo_j6:.4f}, {hi_j6:.4f}])")
    print(f"  J7: {fmt_verdict(j7_pass)} ({int(df_j7['condition_met'].sum())}/12 điều kiện)")
    print(f"  J2 x J6 (Phụ lục A2): {j2_j6_outcome}")

    # ── 4.3 p2b_jmh_effects.csv & p2b_jmh_abs_vs_run5.csv [MT]
    print("\n" + "-" * 98)
    print("4.3 HIỆU ỨNG E_in, E_prof, E_reset VÀ THỜI GIAN TUYỆT ĐỐI SO VỚI RUN 5 [MT]")
    print("-" * 98)
    rng_eff = np.random.default_rng(seeds["jmh_effects_boot"])
    eff_rows = []

    def add_effect(eff_name: str, stratum: str, k_num: tuple, k_den: tuple):
        c_a, c_b = cfg_map[k_num], cfg_map[k_den]
        val = math.log(c_a["score"]) - math.log(c_b["score"])
        bt = np.log(boot_jmh_score(c_a["fork_means"], B, rng_eff)) - np.log(boot_jmh_score(c_b["fork_means"], B, rng_eff))
        lo, hi = np.percentile(bt, [2.5, 97.5])
        eff_rows.append({
            "effect": eff_name, "stratum": stratum, "N": k_num[3], "cutoff": k_num[4],
            "score_num_us": c_a["score"], "score_den_us": c_b["score"],
            "ln_ratio": val, "ratio": math.exp(val),
            "ci_ln_lo": float(lo), "ci_ln_hi": float(hi),
            "ci_ratio_lo": float(math.exp(lo)), "ci_ratio_hi": float(math.exp(hi)),
            "label": "[MT]",
        })

    for n in JMH_NS:
        for cut in JMH_CUTOFFS:
            # E_in = ln Score(fresh) - ln Score(same)
            add_effect("E_in", "pure_none", ("fresh", "pure", "none", n, cut), ("same", "pure", "none", n, cut))
            add_effect("E_in", "mixed_none", ("fresh", "mixed", "none", n, cut), ("same", "mixed", "none", n, cut))
            add_effect("E_in", "mixed_gc", ("fresh", "mixed", "gc", n, cut), ("same", "mixed", "gc", n, cut))
            # E_prof = ln Score(mixed) - ln Score(pure) (reset=none)
            add_effect("E_prof", "same_none", ("same", "mixed", "none", n, cut), ("same", "pure", "none", n, cut))
            add_effect("E_prof", "fresh_none", ("fresh", "mixed", "none", n, cut), ("fresh", "pure", "none", n, cut))
            # E_reset = ln Score(gc) - ln Score(none) (profile=mixed)
            add_effect("E_reset", "same_mixed", ("same", "mixed", "gc", n, cut), ("same", "mixed", "none", n, cut))
            add_effect("E_reset", "fresh_mixed", ("fresh", "mixed", "gc", n, cut), ("fresh", "mixed", "none", n, cut))

    df_eff = pd.DataFrame(eff_rows)
    df_eff.to_csv(tables_dir / "p2b_jmh_effects.csv", index=False)

    print("Tóm tắt hiệu ứng tại c = 30, N = 4096 và 524288 [MT]:")
    sub_eff = df_eff[(df_eff["cutoff"] == 30) & (df_eff["N"].isin([4096, 524288]))]
    print(sub_eff[["effect", "stratum", "N", "ln_ratio", "ratio", "ci_ln_lo", "ci_ln_hi"]].to_string(index=False))

    # p2b_jmh_abs_vs_run5.csv [MT]
    df_p2_jmh = pd.read_csv(PROJECT_ROOT / "results_phase2/analysis/tables/p2_jmh.csv").set_index(["N", "cutoff"])
    df_t08_csv = compute_jmh_csv_ratios(PROJECT_ROOT / "results_jmh/jmh_results.csv").set_index(["N", "cutoff"])
    abs_rows = []
    for n in JMH_NS:
        for cut in JMH_CUTOFFS:
            run5_us = float(df_p2_jmh.loc[(n, cut), "run5_geom_time_us_kp"])
            t08_us = float(df_t08_csv.loc[(n, cut), "score_us"])
            abs_rows.append({
                "N": n, "cutoff": cut,
                "same_pure_none_us": cfg_map[("same", "pure", "none", n, cut)]["score"],
                "fresh_mixed_none_us": cfg_map[("fresh", "mixed", "none", n, cut)]["score"],
                "same_mixed_gc_us": cfg_map[("same", "mixed", "gc", n, cut)]["score"],
                "fresh_mixed_gc_us": cfg_map[("fresh", "mixed", "gc", n, cut)]["score"],
                "T08_us": t08_us,
                "run5_geom_time_us": run5_us,
                "note": "JMH là trung bình cộng, Run 5 là trung bình nhân, khác phiên -> chỉ mô tả",
                "label": "[MT]",
            })
    df_abs = pd.DataFrame(abs_rows)
    df_abs.to_csv(tables_dir / "p2b_jmh_abs_vs_run5.csv", index=False)

    # ── 4.4 p2b_session_quality.csv [MT]
    print("\n" + "-" * 98)
    print("4.4 CHẤT LƯỢNG PHIÊN GIAI ĐOẠN 2b: p2b_session_quality.csv [MT]")
    print("-" * 98)
    run_phase2b(out_dir=tables_dir)

    # ── 4.5 S7 int[] lưới mở rộng (I1, I1b, I2, I3, I4 + MT/KP)
    print("\n" + "-" * 98)
    print("4.5 S7 int[] LƯỚI MỞ RỘNG (results_int_ext/, 6 fork, 43 CUTOFF): I1–I4")
    print("-" * 98)
    raw_s7 = load_raw_dir(PROJECT_ROOT / "results_int_ext", "S7 int_ext (6 fork, 43 c)", expected_rows=REF_S7_ROWS)
    assert set(raw_s7["key"].unique()) == {"int"}, "key không phải int"
    assert sorted(raw_s7["cutoff"].unique().tolist()) == INT_EXT_GRID, "Lưới S7 không khớp INT_EXT_GRID (43 CUTOFF)"
    assert sorted(raw_s7["fork"].unique().tolist()) == [1, 2, 3, 4, 5, 6], "S7 không đủ 6 fork 1..6"

    obs_s7, dfA_s7 = compute_paired_A(raw_s7)
    df_int_r, df_int_best, tensors_s7 = summarize_group_r(
        dfA_s7, obs_s7, B,
        seed_two=seeds["int_r_by_cutoff_two"],
        seed_one=seeds["int_r_by_cutoff_one"],
        label="[ĐK]",
    )
    df_int_r_out = df_int_r.drop(columns=["distribution"]).copy()
    df_int_r_out.to_csv(tables_dir / "p2b_int_r_by_cutoff.csv", index=False)
    df_int_best_out = df_int_best.drop(columns=["distribution", "near_optimal_list"]).copy()
    df_int_best_out.to_csv(tables_dir / "p2b_int_best.csv", index=False)

    print(df_int_best_out[["scale", "c_star", "r_star", "ci2_lo", "ci2_hi", "ci1_lo", "ci1_hi", "near_optimal_2pct", "boot2_argmin_top3_kp"]].to_string(index=False))

    b_s7 = df_int_best.set_index("scale")
    r_s7_idx = df_int_r_out.set_index(["scale", "cutoff"])["r"]

    # I1 & I1b
    i1_rows = []
    for scl in THREE_SCALE_LABELS:
        row = b_s7.loc[scl]
        i1_rows.append({
            "scale": scl, "c_star": int(row["c_star"]),
            "r_star": float(row["r_star"]), "ci2_lo": float(row["ci2_lo"]), "ci2_hi": float(row["ci2_hi"]),
            "threshold_I1": "< 0.833 (ci2_hi)", "condition_met_I1": bool(float(row["ci2_hi"]) < 0.833),
            "threshold_I1b": "< 0.80 (point)", "condition_met_I1b": bool(float(row["r_star"]) < 0.80),
            "label": "[ĐK]",
        })
    df_i1 = pd.DataFrame(i1_rows)
    df_i1.to_csv(tables_dir / "p2b_I1.csv", index=False)
    i1_pass = bool(df_i1["condition_met_I1"].all())
    i1b_pass = bool(df_i1["condition_met_I1b"].all())

    # I2: c*_int <= 192 ở cả 3 thang
    i2_rows = []
    for scl in THREE_SCALE_LABELS:
        c_st = int(b_s7.loc[scl, "c_star"])
        i2_rows.append({
            "scale": scl, "c_star": c_st, "threshold": "<= 192",
            "condition_met": bool(c_st <= 192), "label": "[ĐK]",
        })
    df_i2 = pd.DataFrame(i2_rows)
    df_i2.to_csv(tables_dir / "p2b_I2.csv", index=False)
    i2_pass = bool(df_i2["condition_met"].all())

    # I3: ở 2^12 VÀ 2^16: r(64) > r(32) VÀ r(96) < r(64)
    i3_rows = []
    for scl in ["2^12", "2^16"]:
        r32 = float(r_s7_idx.loc[(scl, 32)])
        r64 = float(r_s7_idx.loc[(scl, 64)])
        r96 = float(r_s7_idx.loc[(scl, 96)])
        c1 = bool(r64 > r32)
        c2 = bool(r96 < r64)
        i3_rows.append({
            "scale": scl, "r_32": r32, "r_64": r64, "r_96": r96,
            "cond_r64_gt_r32": c1, "cond_r96_lt_r64": c2,
            "threshold": "r(64)>r(32) & r(96)<r(64)",
            "condition_met": bool(c1 and c2), "label": "[ĐK]",
        })
    df_i3 = pd.DataFrame(i3_rows)
    df_i3.to_csv(tables_dir / "p2b_I3.csv", index=False)
    i3_pass = bool(df_i3["condition_met"].all())

    # I4: delta_r_int >= 0.5 * delta_r_Integer_S1 (đọc từ T11_reference_values.csv)
    delta_intg_s1 = float(refs["delta_r_Integer_S1"])
    r_int_12 = float(b_s7.loc["2^12", "r_star"])
    r_int_19 = float(b_s7.loc["2^19", "r_star"])
    delta_r_int = r_int_19 - r_int_12
    half_delta_intg = 0.5 * delta_intg_s1
    i4_pass = bool(delta_r_int >= half_delta_intg)

    # Bootstrap hai tầng tham khảo cho delta_r_int (cùng 6 fork cho 2^12 và 2^19, N độc lập)
    rng_i4 = np.random.default_rng(seeds["int_I4_boot"])
    A12, _, _, cuts12 = tensors_s7[("random", "2^12")]
    A19, _, _, cuts19 = tensors_s7[("random", "2^19")]
    a12_c = A12[:, :, cuts12.index(int(b_s7.loc["2^12", "c_star"]))]  # (6, 24)
    a19_c = A19[:, :, cuts19.index(int(b_s7.loc["2^19", "c_star"]))]  # (6, 24)
    F_s7, nN_s7 = a12_c.shape
    bt_dint = np.empty(B, dtype=float)
    for s in range(0, B, 1000):
        b = min(1000, B - s)
        f_idx = rng_i4.integers(0, F_s7, size=(b, F_s7))
        n12_idx = rng_i4.integers(0, nN_s7, size=(b, nN_s7))
        n19_idx = rng_i4.integers(0, nN_s7, size=(b, nN_s7))
        wf = np.zeros((b, F_s7))
        np.add.at(wf, (np.arange(b)[:, None], f_idx), 1.0 / F_s7)
        wn12 = np.zeros((b, nN_s7))
        np.add.at(wn12, (np.arange(b)[:, None], n12_idx), 1.0 / nN_s7)
        wn19 = np.zeros((b, nN_s7))
        np.add.at(wn19, (np.arange(b)[:, None], n19_idx), 1.0 / nN_s7)
        r12_b = np.exp(np.einsum("bf,bn,fn->b", wf, wn12, a12_c, optimize=True))
        r19_b = np.exp(np.einsum("bf,bn,fn->b", wf, wn19, a19_c, optimize=True))
        bt_dint[s:s + b] = r19_b - r12_b
    lo_dint, hi_dint = np.percentile(bt_dint, [2.5, 97.5])

    df_i4 = pd.DataFrame([{
        "r_int_2e12": r_int_12, "r_int_2e19": r_int_19,
        "delta_r_int": delta_r_int, "ci2_delta_lo": float(lo_dint), "ci2_delta_hi": float(hi_dint),
        "delta_r_Integer_S1": delta_intg_s1, "half_delta_r_Integer_S1": half_delta_intg,
        "ratio_int_over_Integer_S1": delta_r_int / delta_intg_s1,
        "threshold": ">= 0.5 * delta_r_Integer_S1", "condition_met": i4_pass, "label": "[ĐK]",
    }])
    df_i4.to_csv(tables_dir / "p2b_I4.csv", index=False)

    # p2b_int_fork_sd.csv [MT] & p2b_int_vs_d3.csv [KP]
    raw_d3_int = load_raw_dir(PROJECT_ROOT / "results_d3/int", "D3/int (đối chiếu)", expected_rows=66_600)
    _, dfA_d3_int = compute_paired_A(raw_d3_int)
    d3_r_csv = pd.read_csv(PROJECT_ROOT / "results_phase2/analysis/tables/p2_d3_r_by_cutoff.csv")
    d3_int_r_map = d3_r_csv[d3_r_csv["key"] == "int"].set_index(["scale", "cutoff"])["r"].to_dict()

    # SD giữa các fork của r_fork(scale, c) = exp(mean_N A(f, N, c))
    s7_fork_r = dfA_s7.groupby(["scale_label", "cutoff", "fork"])["A"].mean().map(math.exp).reset_index(name="r_fork")
    s7_sd_map = s7_fork_r.groupby(["scale_label", "cutoff"])["r_fork"].std(ddof=1).to_dict()
    d3_fork_r = dfA_d3_int.groupby(["scale_label", "cutoff", "fork"])["A"].mean().map(math.exp).reset_index(name="r_fork")
    d3_sd_map = d3_fork_r.groupby(["scale_label", "cutoff"])["r_fork"].std(ddof=1).to_dict()

    d3_cuts = sorted(dfA_d3_int["cutoff"].unique().tolist())
    common_cuts = [c for c in INT_EXT_GRID if c in d3_cuts]

    sd_rows = []
    vs_rows = []
    for scl in THREE_SCALE_LABELS:
        for cut in INT_EXT_GRID:
            sd_s7 = float(s7_sd_map[(scl, cut)])
            sd_d3 = float(d3_sd_map[(scl, cut)]) if (scl, cut) in d3_sd_map else float("nan")
            sd_rows.append({
                "scale": scl, "cutoff": cut,
                "sd_6forks_S7": sd_s7, "sd_3forks_D3": sd_d3,
                "ratio_sd_S7_over_D3": (sd_s7 / sd_d3) if (not math.isnan(sd_d3) and sd_d3 > 0) else float("nan"),
                "in_common_grid": bool(cut in common_cuts),
                "label": "[MT]",
            })
            if cut in common_cuts:
                r7 = float(r_s7_idx.loc[(scl, cut)])
                rd = float(d3_int_r_map[(scl, cut)])
                vs_rows.append({
                    "scale": scl, "cutoff": cut,
                    "r_S7_6forks": r7, "r_D3_3forks": rd,
                    "diff_S7_minus_D3": r7 - rd, "abs_diff": abs(r7 - rd),
                    "label": "[KP]",
                })
    df_fork_sd = pd.DataFrame(sd_rows)
    df_fork_sd.to_csv(tables_dir / "p2b_int_fork_sd.csv", index=False)
    df_vs_d3 = pd.DataFrame(vs_rows)
    df_vs_d3.to_csv(tables_dir / "p2b_int_vs_d3.csv", index=False)

    sd_common = df_fork_sd[df_fork_sd["in_common_grid"] & (df_fork_sd["cutoff"] > 1)]
    print(f"\n  I1: {fmt_verdict(i1_pass)} | I1b: {fmt_verdict(i1b_pass)} | I2: {fmt_verdict(i2_pass)} | I3: {fmt_verdict(i3_pass)} | I4: {fmt_verdict(i4_pass)}")
    print(f"  I4: delta_r_int={delta_r_int:.4f} (CI=[{lo_dint:.4f}, {hi_dint:.4f}]) vs 0.5*delta_r_Integer_S1={half_delta_intg:.4f} (ratio={delta_r_int/delta_intg_s1:.3f})")
    print(f"  [MT] SD giữa fork (c>1 chung, 108 ô): median S7(6f)={sd_common['sd_6forks_S7'].median():.4f} vs D3(3f)={sd_common['sd_3forks_D3'].median():.4f}; mean S7={sd_common['sd_6forks_S7'].mean():.4f} vs D3={sd_common['sd_3forks_D3'].mean():.4f}")

    # ── 4.6 h2b_verdicts.csv (14 giả thuyết + J2xJ6)
    print("\n" + "-" * 98)
    print("4.6 BẢNG PHÁN QUYẾT TỔNG GIAI ĐOẠN 2b (h2b_verdicts.csv) [ĐK]")
    print("-" * 98)
    v_rows = []

    def add_v(hid, subcase, qty, val, thresh, met, overall, src):
        v_rows.append({
            "id": hid, "subcase": subcase, "quantity": qty, "value": val,
            "threshold": thresh, "condition_met": met, "verdict_overall": overall,
            "source_table": src, "label": "[ĐK]",
        })

    # J1
    for _, r in df_j1.iterrows():
        add_v("J1", f"N={int(r['N'])}_c={int(r['cutoff'])}", "|r - r_T08|",
              f"|{r['r_same_pure_none']:.4f} - {r['r_T08']:.4f}| = {r['abs_diff']:.4f}", "<= 0.03", bool(r["condition_met"]), "", "p2b_J1.csv")
    add_v("J1", "OVERALL", "9/9 cells <= 0.03", f"{int(df_j1['condition_met'].sum())}/9 (max={df_j1['abs_diff'].max():.4f})",
          "9/9", j1_pass, fmt_verdict(j1_pass), "p2b_J1.csv")

    # J2
    for _, r in df_j2.iterrows():
        add_v("J2", r["subcase"], r["subcase"], f"{r['metric_value']:.4f} (CI=[{r['ci_lo']:.4f},{r['ci_hi']:.4f}])",
              r["threshold"], bool(r["condition_met"]), "", "p2b_J2.csv")
    add_v("J2", "OVERALL", "(a) 3/3 diff>=0.10 & (b) ratio>=1.30",
          f"{int(df_j2['condition_met'].sum())}/4 (ratio_c30={ratio_30:.4f})", "4/4", j2_pass, fmt_verdict(j2_pass), "p2b_J2.csv")

    # J3
    for _, r in df_j3.iterrows():
        add_v("J3", f"c={int(r['cutoff'])}", "|ln Score(fresh) - ln Score(same)|",
              f"{r['abs_ln_diff']:.4f} (signed={r['ln_diff']:+.4f})", "<= 0.03", bool(r["condition_met"]), "", "p2b_J3.csv")
    add_v("J3", "OVERALL", "4/4 cutoffs <= 0.03", f"{int(df_j3['condition_met'].sum())}/4 (max={df_j3['abs_ln_diff'].max():.4f})",
          "4/4", j3_pass, fmt_verdict(j3_pass), "p2b_J3.csv")

    # J4
    for _, r in df_j4.iterrows():
        add_v("J4", f"N={int(r['N'])}", "Score(30)<Score(10)<Score(7)<Score(1)",
              f"{r['score_30']:.1f} / {r['score_10']:.1f} / {r['score_7']:.1f} / {r['score_1']:.1f}",
              "strictly increasing", bool(r["condition_met"]), "", "p2b_J4.csv")
    add_v("J4", "OVERALL", "2/2 N order ok", f"{int(df_j4['condition_met'].sum())}/2", "2/2", j4_pass, fmt_verdict(j4_pass), "p2b_J4.csv")

    # J5
    for _, r in df_j5.iterrows():
        val_s = f"|{r['r_jmh']:.4f}-{r['r_Run5']:.4f}|={r['abs_diff']:.4f}" if int(r["cutoff"]) > 0 else str(bool(r["condition_met"]))
        add_v("J5", r["subcase"], "H17 criterion (fresh+mixed+none)", val_s, r["threshold"], bool(r["condition_met"]), "", "p2b_J5.csv")
    d5_diff = int(df_j5[df_j5["cutoff"] > 0]["condition_met"].sum())
    d5_ord = int(df_j5[df_j5["cutoff"] < 0]["condition_met"].sum())
    add_v("J5", "OVERALL", "9/9 diff<=0.02 & 3/3 order", f"diff={d5_diff}/9, order={d5_ord}/3", "9/9 & 3/3", j5_pass, fmt_verdict(j5_pass), "p2b_J5.csv")

    # J6
    add_v("J6", "N=4096_c=30", "Score(gc)/Score(none) (same+mixed)",
          f"{rat_j6:.4f} (CI=[{lo_j6:.4f},{hi_j6:.4f}])", ">= 1.50", j6_pass, "", "p2b_J6.csv")
    add_v("J6", "OVERALL", "ratio >= 1.50", f"{rat_j6:.4f}", ">= 1.50", j6_pass, fmt_verdict(j6_pass), "p2b_J6.csv")

    # J7
    for _, r in df_j7.iterrows():
        val_s = f"|{r['r_jmh']:.4f}-{r['r_Run5']:.4f}|={r['abs_diff']:.4f}" if int(r["cutoff"]) > 0 else str(bool(r["condition_met"]))
        add_v("J7", r["subcase"], "H17 criterion (same+mixed+gc)", val_s, r["threshold"], bool(r["condition_met"]), "", "p2b_J7.csv")
    d7_diff = int(df_j7[df_j7["cutoff"] > 0]["condition_met"].sum())
    d7_ord = int(df_j7[df_j7["cutoff"] < 0]["condition_met"].sum())
    add_v("J7", "OVERALL", "9/9 diff<=0.02 & 3/3 order", f"diff={d7_diff}/9, order={d7_ord}/3", "9/9 & 3/3", j7_pass, fmt_verdict(j7_pass), "p2b_J7.csv")

    # J2xJ6
    add_v("J2xJ6", "OUTCOME", "Bảng 4 kết cục Phụ lục A2",
          f"J2={fmt_verdict(j2_pass)}, J6={fmt_verdict(j6_pass)}", "T11_addendum.md A2",
          "", j2_j6_outcome, "p2b_J2.csv; p2b_J6.csv")

    # I1 & I1b
    for _, r in df_i1.iterrows():
        add_v("I1", r["scale"], "ci2_hi(r_int(c*))", f"{r['ci2_hi']:.4f} (r*={r['r_star']:.4f})", "< 0.833", bool(r["condition_met_I1"]), "", "p2b_I1.csv")
    add_v("I1", "OVERALL", "3/3 scales ci2_hi < 0.833", f"{int(df_i1['condition_met_I1'].sum())}/3 (max_hi={df_i1['ci2_hi'].max():.4f})",
          "3/3", i1_pass, fmt_verdict(i1_pass), "p2b_I1.csv")

    for _, r in df_i1.iterrows():
        add_v("I1b", r["scale"], "r_int(c*)", f"{r['r_star']:.4f}", "< 0.80", bool(r["condition_met_I1b"]), "", "p2b_I1.csv")
    add_v("I1b", "OVERALL", "3/3 scales r* < 0.80", f"{int(df_i1['condition_met_I1b'].sum())}/3 (max_r*={df_i1['r_star'].max():.4f})",
          "3/3", i1b_pass, fmt_verdict(i1b_pass), "p2b_I1.csv")

    # I2
    for _, r in df_i2.iterrows():
        add_v("I2", r["scale"], "c*_int", f"{int(r['c_star'])}", "<= 192", bool(r["condition_met"]), "", "p2b_I2.csv")
    add_v("I2", "OVERALL", "3/3 scales c* <= 192", f"{int(df_i2['condition_met'].sum())}/3", "3/3", i2_pass, fmt_verdict(i2_pass), "p2b_I2.csv")

    # I3
    for _, r in df_i3.iterrows():
        add_v("I3", r["scale"], "r(32), r(64), r(96)", f"{r['r_32']:.4f}, {r['r_64']:.4f}, {r['r_96']:.4f}",
              "r(64)>r(32) & r(96)<r(64)", bool(r["condition_met"]), "", "p2b_I3.csv")
    add_v("I3", "OVERALL", "2/2 scales hump repeats", f"{int(df_i3['condition_met'].sum())}/2", "2/2", i3_pass, fmt_verdict(i3_pass), "p2b_I3.csv")

    # I4
    add_v("I4", "2^12_to_2^19", "delta_r_int vs 0.5*delta_r_Integer_S1",
          f"{delta_r_int:.4f} vs {half_delta_intg:.4f} (ratio={delta_r_int/delta_intg_s1:.3f})",
          ">= 0.5 * delta_r_Integer_S1", i4_pass, "", "p2b_I4.csv")
    add_v("I4", "OVERALL", "delta_r_int >= 0.5*delta_r_Integer_S1",
          f"{delta_r_int:.4f} vs {half_delta_intg:.4f}", ">= 0.5 * delta_r_Integer_S1", i4_pass, fmt_verdict(i4_pass), "p2b_I4.csv")

    # B1, B2: HỦY D1 theo §3 hợp đồng
    add_v("B1", "OVERALL", "D1 branch mispredict (N=4096)", "D1 hủy theo §3 (AMD uProf chưa cài)",
          "<= 0.5 * M(fresh)", "", "KHÔNG THỰC HIỆN", "ghi chép phiên đo")
    add_v("B2", "OVERALL", "D1 branch mispredict (N=524288)", "D1 hủy theo §3 (AMD uProf chưa cài)",
          ">= 0.8 * M(fresh)", "", "KHÔNG THỰC HIỆN", "ghi chép phiên đo")

    df_verdicts = pd.DataFrame(v_rows)
    df_verdicts.to_csv(tables_dir / "h2b_verdicts.csv", index=False)

    overall = df_verdicts[df_verdicts["subcase"].isin(["OVERALL", "OUTCOME"])]
    assert len(overall) == 15, f"Kỳ vọng 15 hàng tổng (14 H + J2xJ6), thực tế {len(overall)}"
    print(overall[["id", "quantity", "value", "threshold", "verdict_overall", "source_table"]].to_string(index=False))

    print("\n" + "=" * 98)
    print(f"HOÀN TẤT PHÂN TÍCH T12! Đã xuất toàn bộ bảng vào: {tables_dir}")
    print("=" * 98)
    return 0


def parse_args():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--self-check", action="store_true",
                    help="Chạy 4 kiểm tra tự kiểm (KHÔNG đọc Score hay r của results_jmh_v2/ và results_int_ext/)")
    ap.add_argument("--out", type=Path, default=Path("results_phase2b/analysis"),
                    help="Thư mục đầu ra cho phân tích giai đoạn 2b (mặc định: results_phase2b/analysis)")
    ap.add_argument("--B", type=int, default=DEFAULT_B,
                    help=f"Số lần lặp bootstrap (mặc định: {DEFAULT_B})")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help=f"Seed bootstrap gốc (mặc định: {DEFAULT_SEED})")
    return ap.parse_args()


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    if args.self_check:
        sys.exit(run_self_check(B=args.B))
    sys.exit(run_phase2b_analysis(args.out, B=args.B, base_seed=args.seed))


if __name__ == "__main__":
    main()
