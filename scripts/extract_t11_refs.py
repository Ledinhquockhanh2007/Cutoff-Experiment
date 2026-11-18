#!/usr/bin/env python3
"""
scripts/extract_t11_refs.py — Trích giá trị tham chiếu từ giai đoạn 2 và xuất các tệp đăng ký trước T11:
  - handoff/preregistration/T11_reference_values.csv
  - handoff/preregistration/T11_hypotheses.csv

Tuân thủ Quy tắc A (T11_code.md §5):
  - Đọc trực tiếp từ results_phase2/analysis/tables/ (p2_jmh.csv, p2_best.csv, p2_d3_best.csv).
  - In từng giá trị tính/đọc được cạnh số tham chiếu 4 chữ số của Claude trong T11_contract.md §5.
  - Nếu chênh lệch > 5e-5 -> DỪNG (raise AssertionError).

Cách chạy (từ thư mục gốc dự án):
    python scripts/extract_t11_refs.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

import pandas as pd

TOL_RULE_A = 5e-5

# Số tham chiếu của Claude trong handoff/preregistration/T11_contract.md §5 (4 chữ số thập phân)
CLAUDE_REF_R_T08 = {
    (4096, 7): 0.6144,
    (4096, 10): 0.5885,
    (4096, 30): 0.5660,
    (65536, 7): 0.9868,
    (65536, 10): 0.9496,
    (65536, 30): 0.9727,
    (524288, 7): 0.9782,
    (524288, 10): 0.9364,
    (524288, 30): 0.9904,
}
CLAUDE_REF_R_RUN5 = {
    (4096, 7): 0.9081,
    (4096, 10): 0.8737,
    (4096, 30): 0.8421,
    (65536, 7): 0.9344,
    (65536, 10): 0.9112,
    (65536, 30): 0.8868,
    (524288, 7): 0.9585,
    (524288, 10): 0.9406,
    (524288, 30): 0.9212,
}
CLAUDE_REF_S1_R = {"2^12": 0.8443, "2^19": 0.9165}
CLAUDE_REF_DELTA_R_INTG = 0.0722
CLAUDE_REF_D3_R_INT = {"2^12": 0.7122, "2^16": 0.7719, "2^19": 0.7852}
CLAUDE_REF_D3_CSTAR_INT = {"2^12": 128, "2^16": 128, "2^19": 64}


def build_hypotheses() -> pd.DataFrame:
    """12 giả thuyết giai đoạn 2b (J1–J5, I1, I1b, I2–I4, B1, B2) đúng theo T11_contract.md."""
    rows = [
        {
            "id": "J1",
            "short_description": "JMH v2 tự lặp lại T08 (same + pure)",
            "metric": "|r(same, pure, N, c) - r_T08(N, c)|",
            "decision_rule": "Ở cấu hình same + pure: |r - r_T08| <= 0.03 ở cả 9 ô (N in {4096, 65536, 524288} x c in {7, 10, 30})",
            "threshold": "<= 0.03 (9/9 ô)",
        },
        {
            "id": "J2",
            "short_description": "Học nhánh khi lặp cùng đầu vào, N = 4096 (pure)",
            "metric": "r(fresh, c) - r(same, c); Score(fresh, 4096, 30)/Score(same, 4096, 30)",
            "decision_rule": "Dưới pure, ở N = 4096: r(fresh, c) - r(same, c) >= 0.10 với cả c in {7, 10, 30}, VÀ Score(fresh, 4096, 30) >= 1.30 * Score(same, 4096, 30)",
            "threshold": "diff_r >= 0.10 (3/3 c) & ratio_score >= 1.30",
        },
        {
            "id": "J3",
            "short_description": "Không học được ở N lớn = 524288 (pure)",
            "metric": "|ln Score(fresh, 524288, c) - ln Score(same, 524288, c)|",
            "decision_rule": "Dưới pure, ở N = 524288: |ln Score(fresh, c) - ln Score(same, c)| <= 0.03 với cả 4 c in {1, 7, 10, 30}",
            "threshold": "<= 0.03 (4/4 c)",
        },
        {
            "id": "J4",
            "short_description": "Hồ sơ JIT (fresh + mixed, N lớn)",
            "metric": "Thứ tự Score(30) < Score(10) < Score(7) < Score(1)",
            "decision_rule": "Dưới fresh + mixed, ở cả N = 65536 và N = 524288: thứ tự Score(30) < Score(10) < Score(7) < Score(1) đúng",
            "threshold": "Score(30) < Score(10) < Score(7) < Score(1) (2/2 N)",
        },
        {
            "id": "J5",
            "short_description": "JMH cấu hình như bộ đo tự viết thì khớp Run 5 (fresh + mixed)",
            "metric": "|r(fresh, mixed, N, c) - r_Run5(N, c)|, thứ tự T(c)",
            "decision_rule": "Cấu hình fresh + mixed thỏa đúng tiêu chí H17: |r - r_Run5(N, c)| <= 0.02 ở cả 9 ô VÀ thứ tự Score(30) < Score(10) < Score(7) < Score(1) ở cả 3 N",
            "threshold": "<= 0.02 (9/9 ô) & thứ tự đúng (3/3 N)",
        },
        {
            "id": "I1",
            "short_description": "Khoảng 20% với khóa nguyên thủy int[] (xác nhận [KP] D3)",
            "metric": "CI hai tầng 95% cận trên của r_int(c*)",
            "decision_rule": "Cận trên CI hai tầng 95% của r_int(c*) < 0.833 ở cả 3 thang 2^12, 2^16, 2^19 (6 fork, lưới 43 CUTOFF)",
            "threshold": "ci2_hi(r_int(c*)) < 0.833 (3/3 thang)",
        },
        {
            "id": "I1b",
            "short_description": "Phụ: int[] đạt r < 0.80 ở cả 3 thang",
            "metric": "Ước lượng điểm r_int(c*)",
            "decision_rule": "Ước lượng điểm r_int(c*) < 0.80 ở cả 3 thang 2^12, 2^16, 2^19",
            "threshold": "r_int(c*) < 0.80 (3/3 thang)",
        },
        {
            "id": "I2",
            "short_description": "Cực tiểu int[] nằm trong lưới mở rộng (không ở biên 256)",
            "metric": "c*_int (trên lưới 43 CUTOFF tới 256)",
            "decision_rule": "c*_int <= 192 ở cả 3 thang 2^12, 2^16, 2^19",
            "threshold": "c*_int <= 192 (3/3 thang)",
        },
        {
            "id": "I3",
            "short_description": "Dạng gồ của D3 int[] có lặp lại ở 6 fork không",
            "metric": "r_int(32), r_int(64), r_int(96) (ước lượng điểm, 6 fork)",
            "decision_rule": "Ở cả 2^12 và 2^16: r_int(64) > r_int(32) VÀ r_int(96) < r_int(64)",
            "threshold": "r(64) > r(32) & r(96) < r(64) (2/2 thang)",
        },
        {
            "id": "I4",
            "short_description": "Lặp lại phát hiện H15 theo chiều ngược (lợi ích int[] vẫn co đáng kể)",
            "metric": "Delta_r_int = r_int(c*, 2^19) - r_int(c*, 2^12) vs 0.5 * Delta_r_Integer(S1)",
            "decision_rule": "Delta_r_int >= 0.5 * Delta_r_Integer, với Delta_r_Integer = r(c*, 2^19) - r(c*, 2^12) của Integer[] trong Run 5 S1",
            "threshold": ">= 0.5 * Delta_r_Integer(S1)",
        },
        {
            "id": "B1",
            "short_description": "D1 (có điều kiện): dự đoán sai nhánh giảm ít nhất một nửa khi lặp đầu vào ở N = 4096",
            "metric": "M(same, 4096, c) vs 0.5 * M(fresh, 4096, c) (trung vị 3 lần, trừ nền copyonly)",
            "decision_rule": "M(same, 4096, 30) <= 0.5 * M(fresh, 4096, 30) VÀ M(same, 4096, 1) <= 0.5 * M(fresh, 4096, 1)",
            "threshold": "<= 0.5 * M(fresh) (c in {1, 30})",
        },
        {
            "id": "B2",
            "short_description": "D1 (có điều kiện): dự đoán sai nhánh gần như không đổi ở N = 524288",
            "metric": "M(same, 524288, c) vs 0.8 * M(fresh, 524288, c) (trung vị 3 lần, trừ nền copyonly)",
            "decision_rule": "M(same, 524288, c) >= 0.8 * M(fresh, 524288, c) với cả c in {1, 30}",
            "threshold": ">= 0.8 * M(fresh) (c in {1, 30})",
        },
    ]
    return pd.DataFrame(rows)


def extract_references(tables_dir: Path) -> pd.DataFrame:
    """Trích các giá trị tham chiếu từ bảng kết quả giai đoạn 2 và đối chiếu Quy tắc A."""
    df_jmh = pd.read_csv(tables_dir / "p2_jmh.csv")
    df_best = pd.read_csv(tables_dir / "p2_best.csv")
    df_d3_best = pd.read_csv(tables_dir / "p2_d3_best.csv")

    ref_rows = []
    print("=" * 96)
    print("ĐỐI CHIẾU QUY TẮC A: GIÁ TRỊ TRÍCH TỪ GIAI ĐOẠN 2 VS THAM CHIẾU CLAUDE (T11_contract.md §5)")
    print(f"{'Đại lượng':<28s} {'Đọc từ CSV':>14s} {'Tham chiếu':>12s} {'Chênh lệch':>12s} {'Nguồn':<22s} {'KQ'}")
    print("-" * 96)

    def add_and_check(key: str, group: str, n_or_scale: str, cutoff: str,
                      val: float, claude_ref: float, source_file: str, source_col: str, tol: float = TOL_RULE_A):
        diff = abs(val - claude_ref)
        ok = diff <= tol
        print(f"{key:<28s} {val:14.6f} {claude_ref:12.4f} {diff:12.2e} {source_file:<22s} {'PASS' if ok else 'FAIL'}")
        assert ok, f"DỪNG Quy tắc A: {key} đọc={val}, tham chiếu={claude_ref}, chênh={diff:.3e} > {tol}"
        ref_rows.append({
            "key": key,
            "group": group,
            "n_or_scale": n_or_scale,
            "cutoff": cutoff,
            "value": val,
            "claude_ref_4dp": claude_ref,
            "abs_diff": diff,
            "source_file": source_file,
            "source_column": source_col,
        })

    # 1. r_T08 và r_Run5 cho 9 ô từ p2_jmh.csv
    for n in [4096, 65536, 524288]:
        for c in [7, 10, 30]:
            sub = df_jmh[(df_jmh["N"] == n) & (df_jmh["cutoff"] == c)]
            assert len(sub) == 1, f"Thiếu ô JMH N={n}, c={c}"
            row = sub.iloc[0]
            add_and_check(
                f"r_T08_N{n}_c{c}", "JMH_T08", str(n), str(c),
                float(row["r_jmh"]), CLAUDE_REF_R_T08[(n, c)],
                "p2_jmh.csv", "r_jmh",
            )
            add_and_check(
                f"r_Run5_N{n}_c{c}", "Run5_S1_exactN", str(n), str(c),
                float(row["r_run5"]), CLAUDE_REF_R_RUN5[(n, c)],
                "p2_jmh.csv", "r_run5",
            )

    # 2. Integer S1 r(c*) ở 2^12 và 2^19 và Delta_r_Integer từ p2_best.csv
    b_rnd = df_best[df_best["distribution"] == "random"].set_index("scale")
    r_s1_12 = float(b_rnd.loc["2^12", "r_star"])
    r_s1_19 = float(b_rnd.loc["2^19", "r_star"])
    delta_r_intg = r_s1_19 - r_s1_12
    add_and_check("r_Integer_S1_2e12", "Run5_S1_Integer", "2^12", str(int(b_rnd.loc["2^12", "c_star"])),
                  r_s1_12, CLAUDE_REF_S1_R["2^12"], "p2_best.csv", "r_star")
    add_and_check("r_Integer_S1_2e19", "Run5_S1_Integer", "2^19", str(int(b_rnd.loc["2^19", "c_star"])),
                  r_s1_19, CLAUDE_REF_S1_R["2^19"], "p2_best.csv", "r_star")
    add_and_check("delta_r_Integer_S1", "Run5_S1_Integer", "2^12->2^19", "c*",
                  delta_r_intg, CLAUDE_REF_DELTA_R_INTG, "p2_best.csv", "r_star(2^19)-r_star(2^12)")

    # 3. D3 int[] r_int(c*) và c*_int từ p2_d3_best.csv
    d3_int = df_d3_best[df_d3_best["key"] == "int"].set_index("scale")
    for scl in ["2^12", "2^16", "2^19"]:
        r_val = float(d3_int.loc[scl, "r_star"])
        c_val = int(d3_int.loc[scl, "c_star"])
        add_and_check(f"r_int_D3_{scl.replace('^', 'e')}", "D3_int", scl, str(c_val),
                      r_val, CLAUDE_REF_D3_R_INT[scl], "p2_d3_best.csv", "r_star")
        add_and_check(f"c_star_int_D3_{scl.replace('^', 'e')}", "D3_int", scl, str(c_val),
                      float(c_val), float(CLAUDE_REF_D3_CSTAR_INT[scl]), "p2_d3_best.csv", "c_star", tol=0.0)

    print("-" * 96)
    print(f"PASS QUY TẮC A: {len(ref_rows)}/{len(ref_rows)} giá trị khớp tham chiếu Claude (chênh <= {TOL_RULE_A:.0e}).")
    return pd.DataFrame(ref_rows)


def parse_args():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--tables-dir", type=Path, default=Path("results_phase2/analysis/tables"),
                    help="Thư mục chứa các bảng CSV giai đoạn 2 (mặc định: results_phase2/analysis/tables)")
    ap.add_argument("--out-dir", type=Path, default=Path("handoff/preregistration"),
                    help="Thư mục xuất T11_reference_values.csv và T11_hypotheses.csv")
    return ap.parse_args()


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    df_refs = extract_references(args.tables_dir)
    ref_out = args.out_dir / "T11_reference_values.csv"
    df_refs.to_csv(ref_out, index=False)
    print(f"Đã ghi {len(df_refs)} dòng vào: {ref_out}")

    df_hyp = build_hypotheses()
    hyp_out = args.out_dir / "T11_hypotheses.csv"
    df_hyp.to_csv(hyp_out, index=False)
    print(f"Đã ghi {len(df_hyp)} giả thuyết (J1-J5, I1, I1b, I2-I4, B1, B2) vào: {hyp_out}")


if __name__ == "__main__":
    main()
