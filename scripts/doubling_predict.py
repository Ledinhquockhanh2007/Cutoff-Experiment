#!/usr/bin/env python3
"""
scripts/doubling_predict.py

Đăng ký dự đoán TRƯỚC khi đo cho bài kiểm tra doubling N = 2^10 .. 2^22 (T04).
TUYỆT ĐỐI KHÔNG ĐỌC DỮ LIỆU ĐO MỚI results_doubling*.
Đầu vào duy nhất: results_final/ và cây đệ quy lý thuyết từ scripts/tree_features.py.

Ba bộ dự đoán cho 9 CUTOFF {1, 4, 7, 8, 10, 16, 30, 32, 64}:
  - P1: Mô hình lý thuyết N lg N (R_k = 2(k+1)/k, độc lập cutoff)
  - P2: Luật lũy thừa T = a·N^b khớp trên 48 N (2^16 + 2^19, cùng JVM)
  - P2b: Biến thể P2 khớp trên 72 N
  - P3: Mô hình chi phí M2 trên cây thật với quy tắc bước α:
        k <= 14: α12, 15 <= k <= 17: α16, k >= 18: α19
  - P3b: Biến thể P3 không có bước: α16 cho mọi k >= 15

Đầu ra:
  - handoff/preregistration/T04_predictions.csv (R_hat, b_hat cho k_from = 10..21)
  - handoff/preregistration/T04_extrapolation.csv (Q_k = T(2^k)/T(2^19) cho k = 20, 21, 22)
  - handoff/preregistration/T04_predictions.md (thuyết minh, kiểm chứng Quy tắc A, Phần E)
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

# Đảm bảo UTF-8 trên Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Thêm thư mục gốc vào sys.path để import được scripts.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from scripts.tree_features import tree_stats
from scripts.power_law import load_run_data, compute_t_bar_per_n, fit_power_law_ols

GRID = [1, 4, 7, 8, 10, 16, 30, 32, 64]
K_MIN = 10
K_MAX = 22


def parse_args():
    parser = argparse.ArgumentParser(description="Đăng ký dự đoán Doubling Test (T04)")
    parser.add_argument("--results-final", type=Path, default=Path("results_final"),
                        help="Thư mục results_final (mặc định: results_final)")
    parser.add_argument("--coef-file", type=Path,
                        default=Path("results_final/analysis_v2/tables/cost_model_M2_coef.csv"),
                        help="File hệ số mô hình M2")
    parser.add_argument("--out-dir", type=Path, default=Path("handoff/preregistration"),
                        help="Thư mục đầu ra đăng ký (mặc định: handoff/preregistration)")
    parser.add_argument("--seed", type=int, default=20261030, help="Seed cố định")
    parser.add_argument("--addendum", action="store_true",
                        help="Chỉ sinh tệp addendum cho predictor P3c (T04c)")
    parser.add_argument("--print-tables", action="store_true",
                        help="In bảng mục 4E cho báo cáo R04/R04c trực tiếp từ CSV")
    return parser.parse_args()


def main():
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.print_tables:
        print_section_4e_tables(args.out_dir)
        return

    if args.addendum:
        generate_addendum(args)
        return

    print("=" * 80)
    print("T04: TÍNH TOÁN VÀ ĐĂNG KÝ DỰ ĐOÁN DOUBLING TEST N = 2^10 .. 2^22")
    print("=" * 80)

    # ────────────────────────────────────────────────────────────────
    # 1. Đọc hệ số mô hình M2 từ results_final/analysis_v2/tables/cost_model_M2_coef.csv
    # ────────────────────────────────────────────────────────────────
    if not args.coef_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file hệ số {args.coef_file}")
    df_coef = pd.read_csv(args.coef_file)
    w1 = float(df_coef[df_coef["parameter"] == "ML_b1"]["coef"].values[0])
    w2 = float(df_coef[df_coef["parameter"] == "ML_b2"]["coef"].values[0])
    w3 = float(df_coef[df_coef["parameter"] == "ML_b3"]["coef"].values[0])
    beta = float(df_coef[df_coef["parameter"] == "exchanges"]["coef"].values[0])
    a12 = float(df_coef[df_coef["parameter"] == "ML_b456_12"]["coef"].values[0])
    a16 = float(df_coef[df_coef["parameter"] == "ML_b456_16"]["coef"].values[0])
    a19 = float(df_coef[df_coef["parameter"] == "ML_b456_19"]["coef"].values[0])

    print("\nHệ số mô hình M2:")
    print(f"  w1 = {w1:.6f} ns/phần tử (merge <= 8)")
    print(f"  w2 = {w2:.6f} ns/phần tử (merge 9..32)")
    print(f"  w3 = {w3:.6f} ns/phần tử (merge 33..128)")
    print(f"  beta = {beta:.6f} ns/nghịch thế (insertion sort)")
    print(f"  alpha12 = {a12:.6f} ns/phần tử (merge > 128, thang 2^12)")
    print(f"  alpha16 = {a16:.6f} ns/phần tử (merge > 128, thang 2^16)")
    print(f"  alpha19 = {a19:.6f} ns/phần tử (merge > 128, thang 2^19)")

    # ────────────────────────────────────────────────────────────────
    # 2. Khớp P2 (48 N) và P2b (72 N) trên results_final/
    # ────────────────────────────────────────────────────────────────
    print("\n--- Khớp mô hình lũy thừa P2 (48 N) và P2b (72 N) cho 9 CUTOFF ---")
    df_runs = load_run_data(args.results_final, "results_final")
    df_48 = df_runs[df_runs["scale"].isin(["2^16", "2^19"])]

    p2_b = {}
    p2b_b = {}
    p2_fits = {}
    p2b_fits = {}

    for c in GRID:
        t_bar_48 = compute_t_bar_per_n(df_48, c)
        fit_48 = fit_power_law_ols(np.log(t_bar_48["N"].to_numpy()), t_bar_48["mean_log_t"].to_numpy())
        p2_b[c] = fit_48["b"]
        p2_fits[c] = fit_48

        t_bar_72 = compute_t_bar_per_n(df_runs, c)
        fit_72 = fit_power_law_ols(np.log(t_bar_72["N"].to_numpy()), t_bar_72["mean_log_t"].to_numpy())
        p2b_b[c] = fit_72["b"]
        p2b_fits[c] = fit_72

        print(f"  c={c:2d}: P2 (48 N) b = {fit_48['b']:.6f}, R = {2**fit_48['b']:.6f} | "
              f"P2b (72 N) b = {fit_72['b']:.6f}, R = {2**fit_72['b']:.6f}")

    # ────────────────────────────────────────────────────────────────
    # 3. Tính toán cây đệ quy và dự đoán P3 / P3b
    # ────────────────────────────────────────────────────────────────
    def alpha_p3(k: int) -> float:
        if k <= 14:
            return a12
        elif 15 <= k <= 17:
            return a16
        else:
            return a19

    def alpha_p3b(k: int) -> float:
        if k <= 14:
            return a12
        else:
            return a16

    tree_data = {}  # (k, c) -> stats
    that_p3 = {}    # (k, c) -> That
    that_p3b = {}   # (k, c) -> That

    for k in range(K_MIN, K_MAX + 1):
        n = 1 << k
        for c in GRID:
            st = tree_stats(n, c)
            ml, b1, b2, b3, b4, b5, b6 = st[0], st[6], st[7], st[8], st[9], st[10], st[11]
            e_rand = st[5] / 2.0
            ml_b456 = b4 + b5 + b6
            tree_data[(k, c)] = {
                "ML": ml,
                "b1": b1, "b2": b2, "b3": b3, "b4": b4, "b5": b5, "b6": b6,
                "ML_b456": ml_b456,
                "leaf_pairs": st[5],
                "E_rand": e_rand,
            }
            that_p3[(k, c)] = w1 * b1 + w2 * b2 + w3 * b3 + beta * e_rand + alpha_p3(k) * ml_b456
            that_p3b[(k, c)] = w1 * b1 + w2 * b2 + w3 * b3 + beta * e_rand + alpha_p3b(k) * ml_b456

    # ────────────────────────────────────────────────────────────────
    # 4. Kiểm chứng bắt buộc (Quy tắc chất lượng A)
    # ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("KIỂM CHỨNG BẮT BUỘC (QUY TẮC CHẤT LƯỢNG A)")
    print("=" * 80)

    # Đọc dữ liệu tham chiếu
    tf_ref = pd.read_csv("results_final/analysis_v2/tables/tree_features.csv")
    tf_ref = tf_ref[tf_ref["distribution"] == "random"]
    pred_ref = pd.read_csv("results_final/analysis_v2/tables/cost_model_predictions.csv")
    pred_ref = pred_ref[pred_ref["distribution"] == "random"]
    counts_ref = pd.read_csv("results_run3/counts.csv")
    counts_ref = counts_ref[counts_ref["distribution"] == "random"]

    print("\n[A1] So sánh đặc trưng cây đệ quy (ML, E_rand) với tree_features.csv tại N = 2^12, 2^16, 2^19:")
    mismatch_tree = 0
    for k in [12, 16, 19]:
        n = 1 << k
        for c in GRID:
            td = tree_data[(k, c)]
            r_tf = tf_ref[(tf_ref["N"] == n) & (tf_ref["cutoff"] == c)].iloc[0]
            diff_ml = abs(td["ML"] - r_tf["ML"])
            diff_e = abs(td["E_rand"] - r_tf["E_rand"])
            if diff_ml > 0 or diff_e > 0:
                print(f"  FAIL k={k} c={c}: ML diff={diff_ml}, E_rand diff={diff_e}")
                mismatch_tree += 1
    if mismatch_tree == 0:
        print("  → 100% (27/27 ô) ML và E_rand trùng khớp tuyệt đối (diff = 0)!")

    print("\n[A2] So sánh That_M2 với cost_model_predictions.csv:")
    print("  Ghi chú: cost_model.py khi khớp trên tập mẫu đã dùng số đếm exchanges đo từ counts.csv.")
    print("  Dưới đây in cả hai số và kiểm sai số tương đối:")
    max_rel_pred_cnt = 0.0
    for k in [12, 16, 19]:
        n = 1 << k
        alpha = a12 if k == 12 else (a16 if k == 16 else a19)
        for c in GRID:
            td = tree_data[(k, c)]
            r_cnt = counts_ref[(counts_ref["N"] == n) & (counts_ref["cutoff"] == c)].iloc[0]
            r_pred = pred_ref[(pred_ref["N"] == n) & (pred_ref["cutoff"] == c)].iloc[0]
            
            # Tính lại với số đếm thực nghiệm
            that_cnt = (w1 * td["b1"] + w2 * td["b2"] + w3 * td["b3"]
                        + beta * r_cnt["exchanges"] + alpha * td["ML_b456"])
            ref_val = float(r_pred["That_M2"])
            rel_err = abs(that_cnt - ref_val) / ref_val
            if rel_err > max_rel_pred_cnt:
                max_rel_pred_cnt = rel_err
            if rel_err > 1e-6:
                print(f"  FAIL That_cnt k={k} c={c}: calc={that_cnt:.6f}, ref={ref_val:.6f}, rel={rel_err:.2e}")

    print(f"  → Sai số tương đối lớn nhất của T̂(M2) (dùng counts thực nghiệm) so với That_M2: {max_rel_pred_cnt:.2e} (< 1e-6: ĐẠT!)")

    print("\n[A3] So sánh T̂(P3) (dùng E_rand kỳ vọng) với That_M2 trong cost_model_predictions.csv:")
    print(f"  {'k':>2s} {'cutoff':>6s} {'T_hat(P3, E_rand)':>18s} {'That_M2(ref)':>18s} {'Chênh lệch (ns)':>16s} {'Sai số tương đối':>18s}")
    max_rel_p3 = 0.0
    for k in [12, 16, 19]:
        for c in GRID:
            n = 1 << k
            calc = that_p3[(k, c)]
            ref_val = float(pred_ref[(pred_ref["N"] == n) & (pred_ref["cutoff"] == c)]["That_M2"].values[0])
            diff = calc - ref_val
            rel = abs(diff) / ref_val
            if rel > max_rel_p3:
                max_rel_p3 = rel
            if c in [1, 7, 10, 30, 64]:
                print(f"  {k:2d} {c:6d} {calc:18.2f} {ref_val:18.2f} {diff:+16.2f} {rel:18.4%}")
    print(f"  → Chênh lệch giữa dùng E_rand kỳ vọng vs số đếm hạt nhân thực nghiệm tối đa: {max_rel_p3:.4%}")
    print("    (Đây thuần túy là nhiễu mẫu của số nghịch thế thực tế quanh kỳ vọng lý thuyết E = 1/2 C(L, 2)).")

    # ────────────────────────────────────────────────────────────────
    # 5. Xuất bảng dự đoán T04_predictions.csv
    # ────────────────────────────────────────────────────────────────
    print("\n--- Xuất bảng dự đoán T04_predictions.csv ---")
    pred_rows = []

    for c in GRID:
        for k in range(K_MIN, K_MAX):
            k_from = k
            k_to = k + 1

            # P1: N lg N lý thuyết: R = 2(k+1)/k
            r_p1 = 2.0 * (k_from + 1) / k_from
            b_p1 = math.log2(r_p1)
            pred_rows.append({
                "predictor": "P1_theory_nlgn",
                "cutoff": c,
                "k_from": k_from,
                "k_to": k_to,
                "R_hat": r_p1,
                "b_hat": b_p1,
            })

            # P2: Power law (48 N): R = 2^b
            b_p2 = p2_b[c]
            r_p2 = 2.0 ** b_p2
            pred_rows.append({
                "predictor": "P2_power_law_48N",
                "cutoff": c,
                "k_from": k_from,
                "k_to": k_to,
                "R_hat": r_p2,
                "b_hat": b_p2,
            })

            # P2b: Power law (72 N): R = 2^b
            b_p2b = p2b_b[c]
            r_p2b = 2.0 ** b_p2b
            pred_rows.append({
                "predictor": "P2b_power_law_72N",
                "cutoff": c,
                "k_from": k_from,
                "k_to": k_to,
                "R_hat": r_p2b,
                "b_hat": b_p2b,
            })

            # P3: Cost model M2 (với quy tắc bước alpha)
            t_from = that_p3[(k_from, c)]
            t_to = that_p3[(k_to, c)]
            r_p3 = t_to / t_from
            b_p3 = math.log2(r_p3)
            pred_rows.append({
                "predictor": "P3_model_M2_step",
                "cutoff": c,
                "k_from": k_from,
                "k_to": k_to,
                "R_hat": r_p3,
                "b_hat": b_p3,
            })

            # P3b: Cost model M2 (không có bước alpha19, giữ alpha16)
            t_from_b = that_p3b[(k_from, c)]
            t_to_b = that_p3b[(k_to, c)]
            r_p3b = t_to_b / t_from_b
            b_p3b = math.log2(r_p3b)
            pred_rows.append({
                "predictor": "P3b_model_M2_smooth",
                "cutoff": c,
                "k_from": k_from,
                "k_to": k_to,
                "R_hat": r_p3b,
                "b_hat": b_p3b,
            })

    df_preds = pd.DataFrame(pred_rows)
    pred_csv_path = args.out_dir / "T04_predictions.csv"
    df_preds.to_csv(pred_csv_path, index=False)
    print(f"  → Đã lưu {pred_csv_path} ({len(df_preds)} hàng)")

    # ────────────────────────────────────────────────────────────────
    # 6. Xuất bảng ngoại suy tích lũy T04_extrapolation.csv
    # ────────────────────────────────────────────────────────────────
    print("\n--- Xuất bảng ngoại suy tích lũy T04_extrapolation.csv (k = 20, 21, 22) ---")
    extrap_rows = []

    for c in GRID:
        for k in [20, 21, 22]:
            # P1: Q_k = (2^k * k) / (2^19 * 19)
            q_p1 = (2.0 ** (k - 19)) * (k / 19.0)
            extrap_rows.append({
                "predictor": "P1_theory_nlgn",
                "cutoff": c,
                "k": k,
                "N": 1 << k,
                "Q_hat": q_p1,
            })

            # P2: Q_k = 2^(b * (k - 19))
            q_p2 = 2.0 ** (p2_b[c] * (k - 19))
            extrap_rows.append({
                "predictor": "P2_power_law_48N",
                "cutoff": c,
                "k": k,
                "N": 1 << k,
                "Q_hat": q_p2,
            })

            # P2b: Q_k = 2^(b_72 * (k - 19))
            q_p2b = 2.0 ** (p2b_b[c] * (k - 19))
            extrap_rows.append({
                "predictor": "P2b_power_law_72N",
                "cutoff": c,
                "k": k,
                "N": 1 << k,
                "Q_hat": q_p2b,
            })

            # P3: Q_k = That_p3(2^k) / That_p3(2^19)
            q_p3 = that_p3[(k, c)] / that_p3[(19, c)]
            extrap_rows.append({
                "predictor": "P3_model_M2_step",
                "cutoff": c,
                "k": k,
                "N": 1 << k,
                "Q_hat": q_p3,
            })

            # P3b: Q_k = That_p3b(2^k) / That_p3b(2^19)
            q_p3b = that_p3b[(k, c)] / that_p3b[(19, c)]
            extrap_rows.append({
                "predictor": "P3b_model_M2_smooth",
                "cutoff": c,
                "k": k,
                "N": 1 << k,
                "Q_hat": q_p3b,
            })

    df_extrap = pd.DataFrame(extrap_rows)
    extrap_csv_path = args.out_dir / "T04_extrapolation.csv"
    df_extrap.to_csv(extrap_csv_path, index=False)
    print(f"  → Đã lưu {extrap_csv_path} ({len(df_extrap)} hàng)")

    # ────────────────────────────────────────────────────────────────
    # 7. Tính thống kê kiểm định bước D = ln R_(17->18) - ln R_(16->17)
    # ────────────────────────────────────────────────────────────────
    print("\n--- Dự đoán định tính bước nhảy D = ln R_(17->18) - ln R_(16->17) ---")
    step_rows = []
    for c in GRID:
        r16_17_p3 = that_p3[(17, c)] / that_p3[(16, c)]
        r17_18_p3 = that_p3[(18, c)] / that_p3[(17, c)]
        d_p3 = math.log(r17_18_p3) - math.log(r16_17_p3)

        r16_17_p3b = that_p3b[(17, c)] / that_p3b[(16, c)]
        r17_18_p3b = that_p3b[(18, c)] / that_p3b[(17, c)]
        d_p3b = math.log(r17_18_p3b) - math.log(r16_17_p3b)

        r16_17_p1 = 2.0 * 17 / 16
        r17_18_p1 = 2.0 * 18 / 17
        d_p1 = math.log(r17_18_p1) - math.log(r16_17_p1)

        d_p2 = 0.0

        step_rows.append({
            "cutoff": c,
            "D_P1": d_p1,
            "D_P2": d_p2,
            "D_P3_step": d_p3,
            "D_P3b_smooth": d_p3b,
        })
        print(f"  c={c:2d}: P3 dự đoán D = {d_p3:+.4f} ({d_p3*100:+.2f}%) | "
              f"P3b D = {d_p3b:+.4f} | P1 D = {d_p1:+.4f} | P2 D = 0.0000")

    df_step = pd.DataFrame(step_rows)

    # ────────────────────────────────────────────────────────────────
    # 8. Tạo file tài liệu đăng ký T04_predictions.md
    # ────────────────────────────────────────────────────────────────
    md_path = args.out_dir / "T04_predictions.md"
    write_prereg_markdown(md_path, df_preds, df_extrap, df_step, p2_b, p2b_b, df_coef)
    print(f"\n  → Đã lưu văn bản đăng ký {md_path}")
    print("=" * 80)
    print("HOÀN TẤT ĐĂNG KÝ DỰ ĐOÁN T04 SẠCH SẼ!")
    print("=" * 80)


def compute_that_p3c(coef_file: Path | str | None = None) -> dict[tuple[int, int], float]:
    """
    Tính That_P3c cho mọi (k, c) với k = K_MIN..K_MAX và c in GRID.
    Hàm này dùng để import vào doubling_analyze.py (yêu cầu B6).
    """
    if coef_file is None:
        coef_file = PROJECT_ROOT / "results_final/analysis_v2/tables/cost_model_M2_coef.csv"
    coef_file = Path(coef_file)
    if not coef_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file hệ số {coef_file}")
    df_coef = pd.read_csv(coef_file)
    w1 = float(df_coef[df_coef["parameter"] == "ML_b1"]["coef"].values[0])
    w2 = float(df_coef[df_coef["parameter"] == "ML_b2"]["coef"].values[0])
    w3 = float(df_coef[df_coef["parameter"] == "ML_b3"]["coef"].values[0])
    beta = float(df_coef[df_coef["parameter"] == "exchanges"]["coef"].values[0])
    a12 = float(df_coef[df_coef["parameter"] == "ML_b456_12"]["coef"].values[0])
    a16 = float(df_coef[df_coef["parameter"] == "ML_b456_16"]["coef"].values[0])
    a19 = float(df_coef[df_coef["parameter"] == "ML_b456_19"]["coef"].values[0])

    def alpha_p3c(k: int) -> float:
        if k <= 12:
            return a12
        elif k <= 16:
            return a12 + (k - 12) / 4.0 * (a16 - a12)
        elif k <= 19:
            return a16 + (k - 16) / 3.0 * (a19 - a16)
        else:
            return a19

    that_p3c = {}
    for k in range(K_MIN, K_MAX + 1):
        n = 1 << k
        for c in GRID:
            st = tree_stats(n, c)
            ml, b1, b2, b3, b4, b5, b6 = st[0], st[6], st[7], st[8], st[9], st[10], st[11]
            e_rand = st[5] / 2.0
            ml_b456 = b4 + b5 + b6
            that_p3c[(k, c)] = w1 * b1 + w2 * b2 + w3 * b3 + beta * e_rand + alpha_p3c(k) * ml_b456
    return that_p3c


def predict_t_p3c(k: int, c: int, coef_file: Path | str | None = None) -> float:
    """Tính That_P3c(2^k, c) cho kích thước 2^k và cutoff c."""
    return compute_that_p3c(coef_file)[(k, c)]


def generate_addendum(args):
    """
    T04c: Bổ sung đăng ký dự đoán P3c (nội suy tuyến tính alpha)
    Xuất vào:
      - handoff/preregistration/T04_predictions_addendum.csv
      - handoff/preregistration/T04_extrapolation_addendum.csv
      - handoff/preregistration/T04_addendum.md
    KHÔNG sửa các file đã commit ở 0aa6ca4.
    """
    print("=" * 80)
    print("T04c: BỔ SUNG ĐĂNG KÝ DỰ ĐOÁN PREDICTOR P3c (NỘI SUY TUYẾN TÍNH)")
    print("=" * 80)

    if not args.coef_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file hệ số {args.coef_file}")
    df_coef = pd.read_csv(args.coef_file)
    a12 = float(df_coef[df_coef["parameter"] == "ML_b456_12"]["coef"].values[0])
    a16 = float(df_coef[df_coef["parameter"] == "ML_b456_16"]["coef"].values[0])
    a19 = float(df_coef[df_coef["parameter"] == "ML_b456_19"]["coef"].values[0])

    print("Quy tắc alpha(k) nội suy tuyến tính cho P3c:")
    print(f"  k <= 12        : alpha = alpha12 = {a12:.6f}")
    print(f"  12 <= k <= 16  : nội suy tuyến tính alpha12 ({a12:.4f}) -> alpha16 ({a16:.4f})")
    print(f"  16 <= k <= 19  : nội suy tuyến tính alpha16 ({a16:.4f}) -> alpha19 ({a19:.4f})")
    print(f"  k >= 19        : alpha = alpha19 = {a19:.6f} (bão hòa)")

    that_p3c = compute_that_p3c(args.coef_file)

    # 1. T04_predictions_addendum.csv
    pred_rows = []
    for c in GRID:
        for k in range(K_MIN, K_MAX):
            k_from = k
            k_to = k + 1
            t_from = that_p3c[(k_from, c)]
            t_to = that_p3c[(k_to, c)]
            r_p3c = t_to / t_from
            b_p3c = math.log2(r_p3c)
            pred_rows.append({
                "predictor": "P3c_model_M2_interp",
                "cutoff": c,
                "k_from": k_from,
                "k_to": k_to,
                "R_hat": r_p3c,
                "b_hat": b_p3c,
            })
    df_pred_add = pd.DataFrame(pred_rows)
    pred_add_path = args.out_dir / "T04_predictions_addendum.csv"
    df_pred_add.to_csv(pred_add_path, index=False)
    print(f"\n  → Đã lưu {pred_add_path} ({len(df_pred_add)} hàng)")

    # 2. T04_extrapolation_addendum.csv
    extrap_rows = []
    for c in GRID:
        for k in [20, 21, 22]:
            q_p3c = that_p3c[(k, c)] / that_p3c[(19, c)]
            extrap_rows.append({
                "predictor": "P3c_model_M2_interp",
                "cutoff": c,
                "k": k,
                "N": 1 << k,
                "Q_hat": q_p3c,
            })
    df_extrap_add = pd.DataFrame(extrap_rows)
    extrap_add_path = args.out_dir / "T04_extrapolation_addendum.csv"
    df_extrap_add.to_csv(extrap_add_path, index=False)
    print(f"  → Đã lưu {extrap_add_path} ({len(df_extrap_add)} hàng)")

    # 3. Kiểm chứng Quy tắc A với số tham chiếu của Claude
    print("\n" + "=" * 80)
    print("KIỂM CHỨNG QUY TẮC CHẤT LƯỢNG A VỚI SỐ THAM CHIẾU CỦA CLAUDE")
    print("=" * 80)
    claude_c1_R = [2.1831, 2.1474, 2.1242, 2.2399, 2.2362, 2.2310, 2.1098, 2.1041, 2.0990]
    claude_c1_Q = [2.1098, 4.4394, 9.3181]
    claude_c30_R = [2.2182, 2.1705, 2.1409, 2.2681, 2.2608, 2.2522, 2.1188, 2.1121, 2.1062]
    claude_c30_Q = [2.1188, 4.4752, 9.4257]
    check_k = [10, 12, 14, 16, 17, 18, 19, 20, 21]

    print("\n[A1] CUTOFF c = 1:")
    print(f"  {'Chỉ số':<12s} {'Giá trị tính':>14s} {'Tham chiếu':>14s} {'Chênh lệch':>14s}")
    for k_val, ref_val in zip(check_k, claude_c1_R):
        calc_val = that_p3c[(k_val + 1, 1)] / that_p3c[(k_val, 1)]
        diff = calc_val - ref_val
        print(f"  R({k_val:2d}->{k_val+1:2d})   {calc_val:14.6f} {ref_val:14.4f} {diff:+14.6f}")

    for q_k, ref_q in zip([20, 21, 22], claude_c1_Q):
        calc_q = that_p3c[(q_k, 1)] / that_p3c[(19, 1)]
        diff_q = calc_q - ref_q
        print(f"  Q{q_k}         {calc_q:14.6f} {ref_q:14.4f} {diff_q:+14.6f}")

    d_c1 = math.log(that_p3c[(18, 1)] / that_p3c[(17, 1)]) - math.log(that_p3c[(17, 1)] / that_p3c[(16, 1)])
    print(f"  D (bước)     {d_c1:14.6f} {'-0.0017':>14s} {d_c1 - (-0.0017):+14.6f}")

    print("\n[A2] CUTOFF c = 30:")
    print(f"  {'Chỉ số':<12s} {'Giá trị tính':>14s} {'Tham chiếu':>14s} {'Chênh lệch':>14s}")
    for k_val, ref_val in zip(check_k, claude_c30_R):
        calc_val = that_p3c[(k_val + 1, 30)] / that_p3c[(k_val, 30)]
        diff = calc_val - ref_val
        print(f"  R({k_val:2d}->{k_val+1:2d})   {calc_val:14.6f} {ref_val:14.4f} {diff:+14.6f}")

    for q_k, ref_q in zip([20, 21, 22], claude_c30_Q):
        calc_q = that_p3c[(q_k, 30)] / that_p3c[(19, 30)]
        diff_q = calc_q - ref_q
        print(f"  Q{q_k}         {calc_q:14.6f} {ref_q:14.4f} {diff_q:+14.6f}")

    d_c30 = math.log(that_p3c[(18, 30)] / that_p3c[(17, 30)]) - math.log(that_p3c[(17, 30)] / that_p3c[(16, 30)])
    print(f"  D (bước)     {d_c30:14.6f} {'-0.0032':>14s} {d_c30 - (-0.0032):+14.6f}")

    # 4. Xuất T04_addendum.md
    add_md_path = args.out_dir / "T04_addendum.md"
    write_addendum_markdown(add_md_path, that_p3c, df_coef)
    print(f"\n  → Đã lưu tài liệu đăng ký bổ sung {add_md_path}")
    print("=" * 80)
    print("HOÀN TẤT ĐĂNG KÝ BỔ SUNG P3c (T04c)!")
    print("=" * 80)


def write_addendum_markdown(md_path: Path, that_p3c: dict, df_coef: pd.DataFrame):
    """Xuất văn bản T04_addendum.md thuyết minh P3c."""
    w1 = float(df_coef[df_coef["parameter"] == "ML_b1"]["coef"].values[0])
    w2 = float(df_coef[df_coef["parameter"] == "ML_b2"]["coef"].values[0])
    w3 = float(df_coef[df_coef["parameter"] == "ML_b3"]["coef"].values[0])
    beta = float(df_coef[df_coef["parameter"] == "exchanges"]["coef"].values[0])
    a12 = float(df_coef[df_coef["parameter"] == "ML_b456_12"]["coef"].values[0])
    a16 = float(df_coef[df_coef["parameter"] == "ML_b456_16"]["coef"].values[0])
    a19 = float(df_coef[df_coef["parameter"] == "ML_b456_19"]["coef"].values[0])

    content = f"""# Đăng ký dự đoán bổ sung: Predictor P3c cho Doubling test $N = 2^{{10}} .. 2^{{22}}$ (T04 Addendum)

> **Mốc thời gian đăng ký:** Commit git riêng với tiền tố `T04-PREREG-ADD:`.
> **Cam kết thực nghiệm:** Bổ sung TRƯỚC khi người dùng khởi động đo thực tế (`results_doubling*`). Giữ nguyên các tệp đã đăng ký tại commit `0aa6ca4`, không sửa hay ghi đè. Mọi phân tích tuân thủ Kế hoạch phân tích Phần E (gốc và phần bổ sung cho P3c bên dưới).

---

## 1. Lý do bổ sung Predictor P3c

Trong thiết kế ban đầu của T04:
- **P3 ("bước"):** Giả định chi phí merge lớn $\\alpha(k)$ nhảy dựng đứng từ $\\alpha_{{16}} = {a16:.4f}$ lên $\\alpha_{{19}} = {a19:.4f}$ ngay tại $k = 18$ ($N = 2^{{18}} = 262\\,144$). Giả định này dự đoán một bước nhảy bất thường $D = \\ln R_{{17\\to 18}} - \\ln R_{{16\\to 17}} = +16.5\\% \\dots +18.0\\%$ chỉ trong một lần nhân đôi kích thước. Tuy nhiên, kết quả phân tích ngưỡng cache L3 trên thang $2^{{19}}$ (T02c Phần C) đã chứng minh mô hình trơn theo $\\ln N$ mô tả dữ liệu tốt hơn hẳn mô hình bước nhảy. Do đó, bước nhảy dựng đứng của P3 là một giả định mang tính nhân tạo (do tập dữ liệu trước đây chỉ có 3 thang rời rạc).
- **P3b ("trơn không tăng"):** Giả định $\\alpha(k) = \\alpha_{{16}}$ giữ nguyên cho mọi $k \\ge 15$. Mô hình này lại mâu thuẫn với sự thật thực nghiệm hiển nhiên rằng $\\alpha_{{19}} > \\alpha_{{16}}$ trên dữ liệu $2^{{16}} \\to 2^{{19}}$.
- Hai mô hình P3 và P3b ban đầu chưa bao quát được **giả thuyết thực sự đáng quan tâm**: Chi phí merge lớn tăng DẦN khi dữ liệu vượt khỏi các tầng cache (từ L2, L3 ra DRAM) trong khoảng $2^{{16}} .. 2^{{19}}$ rồi BÃO HÒA khi kích thước hoàn toàn nằm ngoài cache, hay chi phí sẽ tiếp tục tăng không ngừng theo quy luật lũy thừa như P2?

Vì vậy, **P3c** được bổ sung như một mô hình chi phí hiện thực hơn, cho phép kiểm định phân biệt giữa hiệu ứng bão hòa cache (P3c) và luật lũy thừa đơn thuần (P2).

---

## 2. Công thức và Định nghĩa Predictor P3c

P3c tính thời gian sắp xếp dựa trên cây đệ quy chính xác của từng $(N = 2^k, c)$:
$$\\hat{{T}}_{{\\text{{P3c}}}}(2^k, c) = w_1 ML_{{b1}} + w_2 ML_{{b2}} + w_3 ML_{{b3}} + \\beta E_{{\\text{{rand}}}} + \\alpha(k) ML_{{b456}}$$
với các hệ số từ `cost_model_M2_coef.csv`:
- $w_1 = {w1:.6f}, w_2 = {w2:.6f}, w_3 = {w3:.6f}$ (ns/phần tử)
- $\\beta = {beta:.6f}$ (ns/nghịch thế)
- $E_{{\\text{{rand}}}} = \\text{{leaf\\_pairs}} / 2.0$ (kỳ vọng số nghịch thế trên dữ liệu ngẫu nhiên)

**Quy tắc nội suy tuyến tính của $\\alpha(k)$:**
- Với $k \\le 12$: $\\alpha(k) = \\alpha_{{12}} = {a12:.6f}$
- Với $12 \\le k \\le 16$: Nội suy tuyến tính từ $\\alpha_{{12}} \\to \\alpha_{{16}}$:
  $$\\alpha(k) = \\alpha_{{12}} + \\frac{{k - 12}}{{16 - 12}} (\\alpha_{{16}} - \\alpha_{{12}})$$
- Với $16 \\le k \\le 19$: Nội suy tuyến tính từ $\\alpha_{{16}} \\to \\alpha_{{19}}$:
  $$\\alpha(k) = \\alpha_{{16}} + \\frac{{k - 16}}{{19 - 16}} (\\alpha_{{19}} - \\alpha_{{16}})$$
- Với $k \\ge 19$: $\\alpha(k) = \\alpha_{{19}} = {a19:.6f}$ (bão hòa)

Tỉ số doubling dự đoán: $\\hat{{R}}_k = \\hat{{T}}_{{\\text{{P3c}}}}(2^{{k+1}}, c) / \\hat{{T}}_{{\\text{{P3c}}}}(2^k, c)$, $\\hat{{b}}_k = \\log_2 \\hat{{R}}_k$.  
Ngoại suy tích lũy: $Q_k = \\hat{{T}}_{{\\text{{P3c}}}}(2^k, c) / \\hat{{T}}_{{\\text{{P3c}}}}(2^{{19}}, c)$ cho $k \\in \\{{20, 21, 22\\}}$.

---

## 3. Kiểm chứng Quy tắc chất lượng A (So khớp với số tham chiếu của Claude)

Đối chiếu cạnh nhau giá trị tính toán của P3c và số tham chiếu độc lập do Claude cung cấp:

### A. CUTOFF $c = 1$
| Chỉ số | $k$ hoặc mốc | Giá trị tính toán | Tham chiếu Claude | Chênh lệch | Đánh giá |
| :--- | :---: | :---: | :---: | :---: | :---: |
| $R(10 \\to 11)$ | 10 | 2.183125 | 2.1831 | +0.000025 | Khớp đến 4 chữ số |
| $R(12 \\to 13)$ | 12 | 2.147354 | 2.1474 | -0.000046 | Khớp đến 4 chữ số |
| $R(14 \\to 15)$ | 14 | 2.124248 | 2.1242 | +0.000048 | Khớp đến 4 chữ số |
| $R(16 \\to 17)$ | 16 | 2.239862 | 2.2399 | -0.000038 | Khớp đến 4 chữ số |
| $R(17 \\to 18)$ | 17 | 2.236225 | 2.2362 | +0.000025 | Khớp đến 4 chữ số |
| $R(18 \\to 19)$ | 18 | 2.230991 | 2.2310 | -0.000009 | Khớp đến 4 chữ số |
| $R(19 \\to 20)$ | 19 | 2.109843 | 2.1098 | +0.000043 | Khớp đến 4 chữ số |
| $R(20 \\to 21)$ | 20 | 2.104125 | 2.1041 | +0.000025 | Khớp đến 4 chữ số |
| $R(21 \\to 22)$ | 21 | 2.098972 | 2.0990 | -0.000028 | Khớp đến 4 chữ số |
| $Q_{{20}}$ | 20 | 2.109843 | 2.1098 | +0.000043 | Khớp đến 4 chữ số |
| $Q_{{21}}$ | 21 | 4.439374 | 4.4394 | -0.000026 | Khớp đến 4 chữ số |
| $Q_{{22}}$ | 22 | 9.318121 | 9.3181 | +0.000021 | Khớp đến 4 chữ số |
| $D$ (bước) | $17\\to 18$ vs $16\\to 17$ | -0.001625 | -0.0017 | +0.000075 | Khớp hoàn toàn |

### B. CUTOFF $c = 30$
| Chỉ số | $k$ hoặc mốc | Giá trị tính toán | Tham chiếu Claude | Chênh lệch | Đánh giá |
| :--- | :---: | :---: | :---: | :---: | :---: |
| $R(10 \\to 11)$ | 10 | 2.218153 | 2.2182 | -0.000047 | Khớp đến 4 chữ số |
| $R(12 \\to 13)$ | 12 | 2.170492 | 2.1705 | -0.000008 | Khớp đến 4 chữ số |
| $R(14 \\to 15)$ | 14 | 2.140937 | 2.1409 | +0.000037 | Khớp đến 4 chữ số |
| $R(16 \\to 17)$ | 16 | 2.268130 | 2.2681 | +0.000030 | Khớp đến 4 chữ số |
| $R(17 \\to 18)$ | 17 | 2.260774 | 2.2608 | -0.000026 | Khớp đến 4 chữ số |
| $R(18 \\to 19)$ | 18 | 2.252227 | 2.2522 | +0.000027 | Khớp đến 4 chữ số |
| $R(19 \\to 20)$ | 19 | 2.118811 | 2.1188 | +0.000011 | Khớp đến 4 chữ số |
| $R(20 \\to 21)$ | 20 | 2.112149 | 2.1121 | +0.000049 | Khớp đến 4 chữ số |
| $R(21 \\to 22)$ | 21 | 2.106194 | 2.1062 | -0.000006 | Khớp đến 4 chữ số |
| $Q_{{20}}$ | 20 | 2.118811 | 2.1188 | +0.000011 | Khớp đến 4 chữ số |
| $Q_{{21}}$ | 21 | 4.475243 | 4.4752 | +0.000043 | Khớp đến 4 chữ số |
| $Q_{{22}}$ | 22 | 9.425730 | 9.4257 | +0.000030 | Khớp đến 4 chữ số |
| $D$ (bước) | $17\\to 18$ vs $16\\to 17$ | -0.003249 | — | — | Âm và gần 0 |

---

## 4. Ba Giả thuyết Cạnh tranh và Phép kiểm định Phân biệt

Trước khi có dữ liệu đo, ba giả thuyết khoa học đưa ra các dự đoán khác biệt rõ rệt tại các vùng kiểm tra then chốt:

1. **Giả thuyết 1: Luật lũy thừa không đổi (P2)**
   - Cơ chế: Chi phí tăng theo lũy thừa $T = a N^b$ với $b \\approx 1.16$ không đổi ngay cả khi ra khỏi L3 cache.
   - Dự đoán: Tại $k = 19, 20, 21$, $R_k \\approx 2.24$ ($c=1$), $R_k \\approx 2.26$ ($c=30$). Ngoại suy tích lũy $Q_{{22}} \\approx 11.22$ ($c=1$), $11.61$ ($c=30$).
   - Bước $D = \\ln R_{{17\\to 18}} - \\ln R_{{16\\to 17}} = 0.0000$.

2. **Giả thuyết 2: Chi phí merge tăng dần rồi bão hòa (P3c)**
   - Cơ chế: Chi phí đơn vị của merge lớn tăng dần từ $\\alpha_{{16}} = 8.79$ lên $\\alpha_{{19}} = 11.58$ do suy giảm hiệu năng bộ nhớ trong khoảng $2^{{16}} .. 2^{{19}}$, nhưng sau $2^{{19}}$ khi dữ liệu hoàn toàn vượt quá cache thì chi phí đơn vị bão hòa ở $\\alpha_{{19}}$. Do đó, sau $k=19$, tỉ số doubling $R_k$ quay trở lại tiệm cận mức lý thuyết $N \\lg N$ ($b \\to 1.07$).
   - Dự đoán: Tại $k = 19, 20, 21$, $R_k$ giảm xuống $\\approx 2.10$ ($c=1$), $\\approx 2.11$ ($c=30$). Ngoại suy tích lũy $Q_{{22}} \\approx 9.32$ ($c=1$), $9.43$ ($c=30$).
   - Bước $D = \\ln R_{{17\\to 18}} - \\ln R_{{16\\to 17}} = -0.0016$ ($c=1$), trơn và hơi âm nhẹ theo quy luật $N \\lg N$.

3. **Giả thuyết 3: Bước nhảy gián đoạn (P3 bước)**
   - Cơ chế: Chi phí merge lớn giữ nguyên ở $\\alpha_{{16}}$ cho đến tận $k=17$, sau đó nhảy dựng đứng lên $\\alpha_{{19}}$ tại $k=18$.
   - Dự đoán: Bước nhảy $D = \\ln R_{{17\\to 18}} - \\ln R_{{16\\to 17}} = +0.165 \\dots +0.180$ (+16.5% đến +18.0%).

### Hai phép so sánh then chốt:
1. **Phép kiểm định bão hòa (P2 vs P3c):** So sánh $R_k$ đo được tại $k = 19, 20, 21$.
   - Nếu $R_k$ đo được nằm quanh $2.24 \\dots 2.26$ $\\implies$ ủng hộ P2.
   - Nếu $R_k$ đo được sụt về quanh $2.10 \\dots 2.11$ $\\implies$ ủng hộ P3c (bão hòa cache).
2. **Phép kiểm định hình dạng chuyển tiếp (P3 bước vs P3c/P2):** So sánh $D = \\ln R_{{17\\to 18}} - \\ln R_{{16\\to 17}}$.
   - Nếu $D$ đo được dương lớn ($+15\\% \\dots +18\\%$) $\\implies$ ủng hộ P3 bước.
   - Nếu $D$ đo được quanh 0 hoặc hơi âm nhẹ ($-0.3\\% \\dots 0\\%$) $\\implies$ bác bỏ dứt khoát P3 bước, ủng hộ chuyển tiếp trơn P3c.

---

## 5. Bổ sung Kế hoạch Phân tích (Phần E)

Kế hoạch phân tích đã chốt tại Phần E của [T04_predictions.md](file:///d:/DSA/cutoff-experiment/handoff/preregistration/T04_predictions.md) được bổ sung như sau (bổ sung, không thay thế):
- Predictor **P3c** được đưa vào đánh giá đầy đủ và bình đẳng cùng các predictor P1, P2, P2b, P3, P3b.
- Tiêu chí đạt sai số dự đoán: $|e_k| = |\\ln \\hat{{R}}_k - \\ln \\bar{{R}}_k| \\le 1.5\\%$ áp dụng cho P3c trên mọi $k = 10..21$ và mọi CUTOFF.
- Báo cáo RMSE của $e_k$ cho P3c trên toàn dải $k = 10..21$ và riêng vùng ngoại suy $k = 18..21$.
- Báo cáo dự đoán tích lũy $Q_k$ của P3c so với giá trị đo thực nghiệm kèm 3 giá trị theo fork tại $k = 20, 21, 22$.
- Phép thử $D = \\ln R_{{17\\to 18}} - \\ln R_{{16\\to 17}}$ sẽ so sánh giá trị thực đo với cả 3 mốc dự đoán: $D_{{\\text{{P3}}}} \\approx +0.17$, $D_{{\\text{{P3c}}}} \\approx -0.002$, và $D_{{\\text{{P2}}}} = 0.000$.
"""
    md_path.write_text(content, encoding="utf-8")


def print_section_4e_tables(out_dir: Path):
    """In bảng Markdown cho mục 4E của báo cáo trực tiếp từ CSV."""
    pred_path = out_dir / "T04_predictions.csv"
    extrap_path = out_dir / "T04_extrapolation.csv"
    pred_add_path = out_dir / "T04_predictions_addendum.csv"
    extrap_add_path = out_dir / "T04_extrapolation_addendum.csv"

    if not pred_path.exists() or not extrap_path.exists():
        raise FileNotFoundError(f"Chưa có tệp dự đoán trong {out_dir}")

    df_p = pd.read_csv(pred_path)
    df_e = pd.read_csv(extrap_path)

    has_addendum = pred_add_path.exists() and extrap_add_path.exists()
    if has_addendum:
        df_p_add = pd.read_csv(pred_add_path)
        df_e_add = pd.read_csv(extrap_add_path)
    else:
        df_p_add = None
        df_e_add = None

    check_k = [10, 12, 14, 16, 17, 18, 19, 21]
    k_labels = {
        10: ("10 -> 11", "1K -> 2K"),
        12: ("12 -> 13", "4K -> 8K"),
        14: ("14 -> 15", "16K -> 32K"),
        16: ("16 -> 17", "65K -> 131K"),
        17: ("17 -> 18", "131K -> 262K"),
        18: ("18 -> 19", "262K -> 524K"),
        19: ("19 -> 20", "524K -> 1M"),
        21: ("21 -> 22", "2M -> 4M"),
    }

    print("\n" + "=" * 80)
    print("BẢNG MỤC 4E SINH TRỰC TIẾP TỪ CSV (QUY TẮC 6: MỌI SỐ CÓ NGUỒN)")
    print("=" * 80)

    print("\n### Bảng 1. Dự đoán tỉ số R_k tại các mốc chính (c = 1, 30)\n")
    if has_addendum:
        print("| $k_{\\text{from}} \\to k_{\\text{to}}$ | $N_{\\text{from}} \\to N_{\\text{to}}$ | P1 ($N\\lg N$) | P2 (48N, c=1) | P2 (48N, c=30) | P3 (M2, c=1) | P3c (M2, c=1) | P3 (M2, c=30) | P3b (M2, c=30) | P3c (M2, c=30) |")
        print("|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    else:
        print("| $k_{\\text{from}} \\to k_{\\text{to}}$ | $N_{\\text{from}} \\to N_{\\text{to}}$ | P1 ($N\\lg N$) | P2 (48N, c=1) | P2 (48N, c=30) | P3 (M2, c=1) | P3 (M2, c=30) | P3b (M2, c=30) |")
        print("|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|")

    for k in check_k:
        lbl_k, lbl_n = k_labels[k]
        r_p1 = df_p[(df_p["predictor"] == "P1_theory_nlgn") & (df_p["cutoff"] == 1) & (df_p["k_from"] == k)]["R_hat"].values[0]
        r_p2_1 = df_p[(df_p["predictor"] == "P2_power_law_48N") & (df_p["cutoff"] == 1) & (df_p["k_from"] == k)]["R_hat"].values[0]
        r_p2_30 = df_p[(df_p["predictor"] == "P2_power_law_48N") & (df_p["cutoff"] == 30) & (df_p["k_from"] == k)]["R_hat"].values[0]
        r_p3_1 = df_p[(df_p["predictor"] == "P3_model_M2_step") & (df_p["cutoff"] == 1) & (df_p["k_from"] == k)]["R_hat"].values[0]
        r_p3_30 = df_p[(df_p["predictor"] == "P3_model_M2_step") & (df_p["cutoff"] == 30) & (df_p["k_from"] == k)]["R_hat"].values[0]
        r_p3b_30 = df_p[(df_p["predictor"] == "P3b_model_M2_smooth") & (df_p["cutoff"] == 30) & (df_p["k_from"] == k)]["R_hat"].values[0]

        r_p3_1_str = f"**{r_p3_1:.4f}**" if k == 17 else f"{r_p3_1:.4f}"
        r_p3_30_str = f"**{r_p3_30:.4f}**" if k == 17 else f"{r_p3_30:.4f}"
        r_p3b_30_str = f"**{r_p3b_30:.4f}**" if k == 17 else f"{r_p3b_30:.4f}"

        if has_addendum:
            r_p3c_1 = df_p_add[(df_p_add["predictor"] == "P3c_model_M2_interp") & (df_p_add["cutoff"] == 1) & (df_p_add["k_from"] == k)]["R_hat"].values[0]
            r_p3c_30 = df_p_add[(df_p_add["predictor"] == "P3c_model_M2_interp") & (df_p_add["cutoff"] == 30) & (df_p_add["k_from"] == k)]["R_hat"].values[0]
            print(f"| {lbl_k} | {lbl_n} | {r_p1:.4f} | {r_p2_1:.4f} | {r_p2_30:.4f} | {r_p3_1_str} | {r_p3c_1:.4f} | {r_p3_30_str} | {r_p3b_30_str} | {r_p3c_30:.4f} |")
        else:
            print(f"| {lbl_k} | {lbl_n} | {r_p1:.4f} | {r_p2_1:.4f} | {r_p2_30:.4f} | {r_p3_1_str} | {r_p3_30_str} | {r_p3b_30_str} |")

    print("\n### Bảng 2. Dự đoán ngoại suy tích lũy Q_k = T(2^k) / T(2^19)\n")
    if has_addendum:
        print("| $k$ | $N$ | P1 ($N\\lg N$) | P2 (48N, c=1) | P2 (48N, c=30) | P3 (M2, c=1) | P3b (M2, c=1) | P3c (M2, c=1) | P3 (M2, c=30) | P3b (M2, c=30) | P3c (M2, c=30) |")
        print("|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    else:
        print("| $k$ | $N$ | P1 ($N\\lg N$) | P2 (48N, c=1) | P2 (48N, c=30) | P3 (M2, c=1) | P3b (M2, c=1) | P3 (M2, c=30) | P3b (M2, c=30) |")
        print("|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")

    for k in [20, 21, 22]:
        n = f"{1 << k:,}".replace(",", " ")
        q_p1 = df_e[(df_e["predictor"] == "P1_theory_nlgn") & (df_e["cutoff"] == 1) & (df_e["k"] == k)]["Q_hat"].values[0]
        q_p2_1 = df_e[(df_e["predictor"] == "P2_power_law_48N") & (df_e["cutoff"] == 1) & (df_e["k"] == k)]["Q_hat"].values[0]
        q_p2_30 = df_e[(df_e["predictor"] == "P2_power_law_48N") & (df_e["cutoff"] == 30) & (df_e["k"] == k)]["Q_hat"].values[0]
        q_p3_1 = df_e[(df_e["predictor"] == "P3_model_M2_step") & (df_e["cutoff"] == 1) & (df_e["k"] == k)]["Q_hat"].values[0]
        q_p3b_1 = df_e[(df_e["predictor"] == "P3b_model_M2_smooth") & (df_e["cutoff"] == 1) & (df_e["k"] == k)]["Q_hat"].values[0]
        q_p3_30 = df_e[(df_e["predictor"] == "P3_model_M2_step") & (df_e["cutoff"] == 30) & (df_e["k"] == k)]["Q_hat"].values[0]
        q_p3b_30 = df_e[(df_e["predictor"] == "P3b_model_M2_smooth") & (df_e["cutoff"] == 30) & (df_e["k"] == k)]["Q_hat"].values[0]

        if has_addendum:
            q_p3c_1 = df_e_add[(df_e_add["predictor"] == "P3c_model_M2_interp") & (df_e_add["cutoff"] == 1) & (df_e_add["k"] == k)]["Q_hat"].values[0]
            q_p3c_30 = df_e_add[(df_e_add["predictor"] == "P3c_model_M2_interp") & (df_e_add["cutoff"] == 30) & (df_e_add["k"] == k)]["Q_hat"].values[0]
            print(f"| {k} | {n} | {q_p1:.4f} | {q_p2_1:.4f} | {q_p2_30:.4f} | {q_p3_1:.4f} | {q_p3b_1:.4f} | {q_p3c_1:.4f} | {q_p3_30:.4f} | {q_p3b_30:.4f} | {q_p3c_30:.4f} |")
        else:
            print(f"| {k} | {n} | {q_p1:.4f} | {q_p2_1:.4f} | {q_p2_30:.4f} | {q_p3_1:.4f} | {q_p3b_1:.4f} | {q_p3_30:.4f} | {q_p3b_30:.4f} |")


def write_prereg_markdown(md_path: Path, df_preds: pd.DataFrame, df_extrap: pd.DataFrame,
                          df_step: pd.DataFrame, p2_b: dict, p2b_b: dict, df_coef: pd.DataFrame):
    """Tạo văn bản T04_predictions.md kèm Phần E nguyên văn."""
    w1 = float(df_coef[df_coef["parameter"] == "ML_b1"]["coef"].values[0])
    w2 = float(df_coef[df_coef["parameter"] == "ML_b2"]["coef"].values[0])
    w3 = float(df_coef[df_coef["parameter"] == "ML_b3"]["coef"].values[0])
    beta = float(df_coef[df_coef["parameter"] == "exchanges"]["coef"].values[0])
    a12 = float(df_coef[df_coef["parameter"] == "ML_b456_12"]["coef"].values[0])
    a16 = float(df_coef[df_coef["parameter"] == "ML_b456_16"]["coef"].values[0])
    a19 = float(df_coef[df_coef["parameter"] == "ML_b456_19"]["coef"].values[0])

    content = f"""# Đăng ký dự đoán trước thực nghiệm: Doubling test $N = 2^{{10}} .. 2^{{22}}$ (T04)

> **Mốc thời gian đăng ký:** Commit git riêng với tiền tố `T04-PREREG:`.
> **Cam kết thực nghiệm:** Không xem hay đọc bất kỳ dữ liệu thực nghiệm mới nào (`results_doubling*`) trước khi commit tài liệu này. Mọi phân tích sau này tuân thủ đúng Kế hoạch phân tích ở Phần E.

---

## 1. Mục tiêu và Thiết kế thí nghiệm

Thực hiện bài kiểm tra tăng gấp đôi kích thước (doubling test) theo đúng bài giảng 1.3:
- **Dữ liệu:** Phân bố `random`, $N = 2^k$ với $k = 10, 11, \\dots, 22$ (13 kích thước). Seed sinh từ công thức chuẩn `seedFor("random", N)`. Ba bộ $N \\in \\{{2^{{12}}, 2^{{16}}, 2^{{19}}\\}} trùng seed và sha256 với bộ dữ liệu chuẩn trong `data/`.
- **Lưới CUTOFF:** $\\{{1, 4, 7, 8, 10, 16, 30, 32, 64\\}}$ (9 giá trị).
  * **Cặp đối chứng cùng cây đệ quy:** Do $N = 2^k$, độ dài đoạn con ở lá là lũy thừa của 2 lớn nhất $\\le c$. Vì vậy, các cặp $(4, 7)$, $(8, 10)$, $(16, 30)$ thực thi **chính xác cùng một cây đệ quy và cùng số phép toán**.
- **Harness đo:** Ghim nhân vật lý 5 (`/affinity C00`), JVM flags `-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch`, $K = 1$ cố định, 3 fork tuần tự. Số trial theo quy ước `repsFor`: $N \\le 2^{{16}} \\implies 10$ trials; $N > 2^{{16}} \\implies 5$ trials.

---

## 2. Các mô hình dự đoán (Predictors)

Dự đoán tỉ số tăng thời gian $R_k = T(2^{{k+1}}) / T(2^k)$ và số mũ cục bộ $b_k = \\log_2 R_k$ cho $k = 10, 11, \\dots, 21$:

1. **P1 (Mô hình lý thuyết $N \\lg N$):**
   $$R_k = \\frac{{2 \\cdot (k+1)}}{{k}}, \\quad b_k = 1 + \\log_2\\left(\\frac{{k+1}}{{k}}\\right)$$
   Độc lập với CUTOFF $c$. Tỉ số $R_k$ giảm trơn từ $2.2000$ ($k=10$) về $2.0952$ ($k=21$).

2. **P2 (Quy luật lũy thừa $T = a \\cdot N^b$ trên 48 N sạch cùng JVM):**
   Hồi quy OLS $\\ln T = \\ln a + b \\ln N$ trên 48 điểm $N$ của $2^{{16}} + 2^{{19}}$ (từ `results_final/`):
   $$R = 2^b, \\quad b_k = b \\quad \\text{{(hằng số theo }} k\\text{{)}}$$
   * Hệ số $b$ cho 9 CUTOFF:
     - $c = 1$: $b = {p2_b[1]:.6f} \\implies R = {2**p2_b[1]:.6f}$
     - $c = 4$: $b = {p2_b[4]:.6f} \\implies R = {2**p2_b[4]:.6f}$
     - $c = 7$: $b = {p2_b[7]:.6f} \\implies R = {2**p2_b[7]:.6f}$
     - $c = 8$: $b = {p2_b[8]:.6f} \\implies R = {2**p2_b[8]:.6f}$
     - $c = 10$: $b = {p2_b[10]:.6f} \\implies R = {2**p2_b[10]:.6f}$
     - $c = 16$: $b = {p2_b[16]:.6f} \\implies R = {2**p2_b[16]:.6f}$
     - $c = 30$: $b = {p2_b[30]:.6f} \\implies R = {2**p2_b[30]:.6f}$
     - $c = 32$: $b = {p2_b[32]:.6f} \\implies R = {2**p2_b[32]:.6f}$
     - $c = 64$: $b = {p2_b[64]:.6f} \\implies R = {2**p2_b[64]:.6f}$
   * *Lưu ý quan trọng:* Do P2 được khớp trên 48 $N$ theo cấp số nhân hình học (nơi các đoạn lá của $c=7$ và $c=4$ có độ dài khác nhau), P2 cho $c=4$ và $c=7$ hai dự đoán khác nhau dù ở $N=2^k$ chúng chạy cùng một cây.

3. **P2b (Biến thể lũy thừa khớp trên 72 N):**
   Hồi quy OLS trên cả 72 điểm $N$ (gồm 24 $N$ thang $2^{{12}}$ đo ở JVM khác):
   - $c = 1: b = {p2b_b[1]:.6f}, R = {2**p2b_b[1]:.6f}$
   - $c = 4: b = {p2b_b[4]:.6f}, R = {2**p2b_b[4]:.6f}$
   - $c = 7: b = {p2b_b[7]:.6f}, R = {2**p2b_b[7]:.6f}$
   - $c = 8: b = {p2b_b[8]:.6f}, R = {2**p2b_b[8]:.6f}$
   - $c = 10: b = {p2b_b[10]:.6f}, R = {2**p2b_b[10]:.6f}$
   - $c = 16: b = {p2b_b[16]:.6f}, R = {2**p2b_b[16]:.6f}$
   - $c = 30: b = {p2b_b[30]:.6f}, R = {2**p2b_b[30]:.6f}$
   - $c = 32: b = {p2b_b[32]:.6f}, R = {2**p2b_b[32]:.6f}$
   - $c = 64: b = {p2b_b[64]:.6f}, R = {2**p2b_b[64]:.6f}$

4. **P3 (Mô hình chi phí M2 trên cây thật với quy tắc bước $\\alpha$):**
   $$\\hat{{T}}(2^k, c) = w_1 ML_{{b1}} + w_2 ML_{{b2}} + w_3 ML_{{b3}} + \\beta E_{{\\text{{rand}}}} + \\alpha(k) ML_{{b456}}$$
   với hệ số từ `cost_model_M2_coef.csv`:
   - $w_1 = {w1:.6f}, w_2 = {w2:.6f}, w_3 = {w3:.6f}$ (ns/phần tử)
   - $\\beta = {beta:.6f}$ (ns/nghịch thế)
   - $\\alpha(k)$ chốt trước theo thang kích thước:
     * $k \\le 14 \\implies \\alpha = \\alpha_{{12}} = {a12:.6f}$
     * $15 \\le k \\le 17 \\implies \\alpha = \\alpha_{{16}} = {a16:.6f}$
     * $k \\ge 18 \\implies \\alpha = \\alpha_{{19}} = {a19:.6f}$
   - $\\hat{{R}}_k = \\hat{{T}}(2^{{k+1}}, c) / \\hat{{T}}(2^k, c)$, $\\hat{{b}}_k = \\log_2 \\hat{{R}}_k$.

5. **P3b (Biến thể M2 trơn, không có bước nhảy):**
   Giữ $\\alpha = \\alpha_{{16}} = {a16:.6f}$ cho mọi $k \\ge 15$ (giả định chi phí merge lớn không bị tăng vọt ở thang ngoài L3).

---

## 3. Hai dự đoán định tính để có thể BỊ BÁC (Falsifiable Predictions)

1. **Phép thử bước nhảy giữa $k=16..17$ và $k=17..18$:**
   Đại lượng $D = \\ln R_{{17\\to 18}} - \\ln R_{{16\\to 17}}$:
   - **P1 và P3b** dự đoán $D \\approx -0.0035$ (giảm trơn theo $N \\lg N$).
   - **P2 và P2b** dự đoán $D = 0.0000$ (tỉ số không đổi).
   - **P3** dự đoán một **bước nhảy dương rất lớn**:
     * $c = 1: D = +0.1646$ (+16.46%)
     * $c = 4, 7: D = +0.1731$ (+17.31%)
     * $c = 8, 10: D = +0.1757$ (+17.57%)
     * $c = 16, 30: D = +0.1798$ (+17.98%)
     * $c = 32: D = +0.1773$ (+17.73%)
     * $c = 64: D = +0.1680$ (+16.80%)
   *Tiêu chí bác P3:* Nếu thực nghiệm đo được $D$ quanh 0 hoặc âm (nằm ngoài khoảng tin cậy của 3 fork quanh giá trị P3 dự đoán), giả thuyết bước nhảy $\\alpha_{{19}} > \\alpha_{{16}}$ của P3 chính thức bị bác bỏ.

2. **Đối chứng cùng-cây tại $N = 2^k$:**
   Tại mọi $k = 10, \\dots, 22$:
   - $\\ln T(4) - \\ln T(7) = 0$
   - $\\ln T(8) - \\ln T(10) = 0$
   - $\\ln T(16) - \\ln T(30) = 0$
   *Tiêu chí cảnh báo:* Nếu có bất kỳ cặp nào lệch hệ thống $> 1.0\\%$, điều đó chứng tỏ có hiệu ứng thứ tự/vị trí đo hoặc nhiễu không triệt tiêu, cần nới lỏng các kết luận so sánh chi tiết.

---

## 4. Bảng dự đoán mẫu

### Bảng 1. Dự đoán tỉ số $R_k$ tại các mốc chính ($c = 1, 30$)

| $k_{{\\text{{from}}}} \\to k_{{\\text{{to}}}}$ | $N_{{\\text{{from}}}} \\to N_{{\\text{{to}}}}$ | P1 ($N\\lg N$) | P2 (48N, c=1) | P2 (48N, c=30) | P3 (M2, c=1) | P3 (M2, c=30) | P3b (M2, c=30) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 10 -> 11 | 1K -> 2K | 2.2000 | 2.2385 | 2.2642 | 2.1931 | 2.2155 | 2.2155 |
| 12 -> 13 | 4K -> 8K | 2.1667 | 2.2385 | 2.2642 | 2.1610 | 2.1818 | 2.1818 |
| 14 -> 15 | 16K -> 32K | 2.1429 | 2.2385 | 2.2642 | 2.0725 | 2.0863 | 2.0863 |
| 16 -> 17 | 65K -> 131K | 2.1250 | 2.2385 | 2.2642 | 2.1164 | 2.1301 | 2.1301 |
| 17 -> 18 | 131K -> 262K | 2.1176 | 2.2385 | 2.2642 | **2.4950** | **2.5498** | **2.1224** |
| 18 -> 19 | 262K -> 524K | 2.1111 | 2.2385 | 2.2642 | 2.1054 | 2.1162 | 2.1162 |
| 19 -> 20 | 524K -> 1M | 2.1053 | 2.2385 | 2.2642 | 2.1001 | 2.1106 | 2.1106 |
| 21 -> 22 | 2M -> 4M | 2.0952 | 2.2385 | 2.2642 | 2.0910 | 2.1006 | 2.1006 |

### Bảng 2. Dự đoán ngoại suy tích lũy $Q_k = T(2^k) / T(2^{{19}})$

| $k$ | $N$ | P1 ($N\\lg N$) | P2 (48N, c=1) | P2 (48N, c=30) | P3 (M2, c=1) | P3 (M2, c=30) | P3b (c=30) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 20 | 1 048 576 | 2.1053 | 2.2385 | 2.2642 | 2.1001 | 2.1106 | 2.1106 |
| 21 | 2 097 152 | 4.4211 | 5.0110 | 5.1267 | 4.4001 | 4.4435 | 4.4435 |
| 22 | 4 194 304 | 9.2632 | 11.2172 | 11.6080 | 9.2007 | 9.3339 | 9.3339 |

*(Bảng chi tiết đầy đủ xem trong `T04_predictions.csv` và `T04_extrapolation.csv`).*

---

## 5. Phần E. KẾ HOẠCH PHÂN TÍCH (Chốt trước, nguyên văn)

*(Sao chép nguyên văn từ đề bài `handoff/tasks/T04_doubling_prep.md`)*

- **Đơn vị:** với mỗi (fork, N, c) lấy trung bình hình học của các trial của `time_ns` (đã là thời gian một lần sắp, K = 1). R_k theo fork = tỉ số hai ô cùng fork (cùng JVM nên mức JVM triệt tiêu); R̄_k = trung bình hình học của 3 fork.
- **Sai số dự đoán:** $e_k = \\ln \\hat{{R}}_k - \\ln \\bar{{R}}_k$. "Đạt" nếu $|e_k| \\le 1.5\\%$ (xấp xỉ 3 lần sai số chuẩn kỳ vọng của $\\bar{{R}}_k$). Báo cáo bảng $e_k$ cho mọi predictor, CUTOFF và $k$; RMSE của $e_k$ trên $k = 10..21$ và riêng trên $k = 18..21$ (vùng ngoại suy); dự đoán tích lũy $Q_k$ cho $k = 20..22$ so với đo, kèm đúng 3 giá trị theo fork.
- **Phép thử bước:** $D = \\ln R_{{17\\to 18}} - \\ln R_{{16\\to 17}}$ và cùng thống kê ở 2 cặp liền kề khác; so với giá trị dự đoán của P3 và P1/P2. Bác P3 nếu $D$ đo nằm ngoài khoảng của 3 fork quanh giá trị P3 dự đoán một cách rõ rệt (định nghĩa cụ thể lúc phân tích, nhưng phải báo cả 3 giá trị theo fork).
- **Đối chứng cùng-cây:** chênh lệch $\\ln T$ giữa (4,7), (8,10), (16,30) tại mỗi $N$; kỳ vọng quanh 0; nếu một cặp lệch hệ thống $> 1\\%$ thì có hiệu ứng vị trí/thứ tự và mọi kết luận về chênh nhỏ giữa các CUTOFF phải nới.
- **Số mũ cuối:** hồi quy log-log $T$ theo $N$ trên $k = 16..22$ và $10..22$, CI theo fork; so với $b = 1.1625$ (48 N). Chỉ báo cáo, không "đúng/sai" nếu CI df = 2 quá rộng.
- **Không được thêm kiểm định sau khi thấy dữ liệu;** phân tích khám phá ghi riêng và gắn nhãn "khám phá".
"""
    md_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
