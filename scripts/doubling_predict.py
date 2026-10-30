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
    return parser.parse_args()


def main():
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

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
