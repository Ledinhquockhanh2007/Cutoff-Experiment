#!/usr/bin/env python3
"""
scripts/predict_t09.py

Tính toán và xuất các tệp dự đoán số cho Hợp đồng Đăng ký trước Giai đoạn 2 (T09):
- preregistration/T09_predictions_m2.csv
- preregistration/T09_predictions_doubling_v2.csv
- preregistration/T09_hypotheses.csv

Tuân thủ Quy tắc A: in số tính toán, số đối chiếu Claude và sai lệch.
"""

import argparse
import math
import sys
from pathlib import Path

# Thêm thư mục gốc vào sys.path để import được scripts.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from scripts.tree_features import tree_stats

GRID_35 = list(range(1, 33)) + [40, 48, 64]


def parse_args():
    parser = argparse.ArgumentParser(description="Tính và xuất dự đoán số đăng ký trước T09")
    parser.add_argument("--manifest-run5", type=Path, default=Path("data_run5/manifest.csv"),
                        help="Manifest của data_run5")
    parser.add_argument("--coef-file", type=Path,
                        default=Path("results_final/analysis_v2/tables/cost_model_M2_coef.csv"),
                        help="File hệ số mô hình M2 đóng băng")
    parser.add_argument("--pred-ref", type=Path,
                        default=Path("results_final/analysis_v2/tables/cost_model_predictions.csv"),
                        help="File dự đoán giai đoạn 1 để kiểm tra quy tắc A")
    parser.add_argument("--counts-file", type=Path, default=Path("results_final/counts.csv"),
                        help="File counts.csv giai đoạn 1 để kiểm tra quy tắc A")
    parser.add_argument("--a1z-file", type=Path,
                        default=Path("results_doubling/analysis/tables/A1z_noise_interpretation.csv"),
                        help="File A1z_noise_interpretation.csv của doubling v1")
    parser.add_argument("--out-dir", type=Path, default=Path("preregistration"),
                        help="Thư mục xuất file đăng ký")
    parser.add_argument("--seed", type=int, default=20261117, help="Seed cố định")
    return parser.parse_args()


def compress_range(nums):
    """Nén danh sách số thành chuỗi khoảng, ví dụ [20..32, 40]."""
    if not nums:
        return ""
    nums = sorted(list(set(nums)))
    ranges = []
    start = prev = nums[0]
    for x in nums[1:]:
        if x == prev + 1:
            prev = x
        else:
            ranges.append(f"{start}..{prev}" if start < prev else f"{start}")
            start = prev = x
    ranges.append(f"{start}..{prev}" if start < prev else f"{start}")
    return ", ".join(ranges)


def main():
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("T09: DỰ ĐOÁN SỐ CHO HỢP ĐỒNG ĐĂNG KÝ TRƯỚC GIAI ĐOẠN 2")
    print("=" * 80)

    # ────────────────────────────────────────────────────────────────
    # 1. Đọc hệ số M2 đóng băng
    # ────────────────────────────────────────────────────────────────
    if not args.coef_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file hệ số M2: {args.coef_file}")
    df_coef = pd.read_csv(args.coef_file).set_index("parameter")["coef"].to_dict()

    w1 = df_coef["ML_b1"]
    w2 = df_coef["ML_b2"]
    w3 = df_coef["ML_b3"]
    beta = df_coef["exchanges"]
    alpha12 = df_coef["ML_b456_12"]
    alpha16 = df_coef["ML_b456_16"]
    alpha19 = df_coef["ML_b456_19"]

    print(f"Hệ số M2 đóng băng từ {args.coef_file}:")
    print(f"  w1 = {w1:.6f}, w2 = {w2:.6f}, w3 = {w3:.6f}")
    print(f"  beta = {beta:.6f}")
    print(f"  alpha_12 = {alpha12:.6f}, alpha_16 = {alpha16:.6f}, alpha_19 = {alpha19:.6f}")

    # Nội suy alpha theo k = lg S (§2 hợp đồng)
    # alpha14: k=14, bước (14-12)/(16-12) = 2/4 = 0.5
    # alpha18: k=18, bước (18-16)/(19-16) = 2/3
    alpha14 = alpha12 + (alpha16 - alpha12) * (2.0 / 4.0)
    alpha18 = alpha16 + (alpha19 - alpha16) * (2.0 / 3.0)

    print("\nĐối chiếu số alpha nội suy với giá trị tham chiếu của Claude (§2):")
    print(f"  alpha_14: tính = {alpha14:8.6f} (làm tròn: {alpha14:.3f}) | Claude ref = 8.931 | chênh = {abs(round(alpha14, 3) - 8.931):.3e}")
    print(f"  alpha_18: tính = {alpha18:8.6f} (làm tròn: {alpha18:.3f}) | Claude ref = 10.650 | chênh = {abs(round(alpha18, 3) - 10.650):.3e}")
    assert abs(round(alpha14, 3) - 8.931) <= 1e-3, "alpha_14 không khớp Claude ref"
    assert abs(round(alpha18, 3) - 10.650) <= 1e-3, "alpha_18 không khớp Claude ref"

    # ────────────────────────────────────────────────────────────────
    # 2. Kiểm tính đúng trên thang cũ 2^12, 2^16, 2^19 (Quy tắc A)
    # ────────────────────────────────────────────────────────────────
    print("\n" + "-" * 80)
    print("KIỂM TRA TÍNH ĐÚNG TRÊN THANG CŨ 2^12, 2^16, 2^19 (QUY TẮC A)")
    print("-" * 80)
    if args.pred_ref.exists() and args.counts_file.exists():
        pred_ref = pd.read_csv(args.pred_ref)
        counts_ref = pd.read_csv(args.counts_file)
        cnt_map = counts_ref[counts_ref.distribution == "random"].set_index(["N", "cutoff"])["exchanges"].to_dict()

        alpha_map = {"2^12": alpha12, "2^16": alpha16, "2^19": alpha19}
        max_diff_T = 0.0
        max_diff_r = 0.0

        for _, row in pred_ref.iterrows():
            sc = row["scale"]
            n = int(row["N"])
            c = int(row["cutoff"])
            # Tính tree stats
            ts = tree_stats(n, c)
            ml_b1, ml_b2, ml_b3 = ts[6], ts[7], ts[8]
            ml_b456 = ts[9] + ts[10] + ts[11]
            ex = cnt_map[(n, c)]
            a = alpha_map[sc]

            That = w1 * ml_b1 + w2 * ml_b2 + w3 * ml_b3 + beta * ex + a * ml_b456
            diff_T = abs(That - row["That_M2"])
            max_diff_T = max(max_diff_T, diff_T)

            # c = 1 That1
            ts1 = tree_stats(n, 1)
            That1 = w1 * ts1[6] + w2 * ts1[7] + w3 * ts1[8] + beta * cnt_map[(n, 1)] + a * (ts1[9] + ts1[10] + ts1[11])
            rhat = That / That1
            diff_r = abs(rhat - row["rhat_M2"])
            max_diff_r = max(max_diff_r, diff_r)

        print(f"  Sai khác lớn nhất That_M2 so với cost_model_predictions: {max_diff_T:.2e} (ns)")
        print(f"  Sai khác lớn nhất rhat_M2 so với cost_model_predictions: {max_diff_r:.2e}")
        assert max_diff_r < 1e-9, f"Sai khác rhat_M2 ({max_diff_r}) vượt ngưỡng 1e-9"
        print("  → PASS Quy tắc A: mã tái tạo tuyệt đối 100% kết quả M2 giai đoạn 1 (sai số < 1e-9).")
    else:
        print("  [Cảnh báo] Bỏ qua kiểm tra thang cũ vì thiếu file dữ liệu tham chiếu.")

    # ────────────────────────────────────────────────────────────────
    # 3. Tính dự đoán M2 cho thang mới 2^14 và 2^18
    # ────────────────────────────────────────────────────────────────
    print("\n" + "-" * 80)
    print("TÍNH TOÁN DỰ ĐOÁN M2 CHO THANG MỚI 2^14 VÀ 2^18 (H10)")
    print("-" * 80)
    if not args.manifest_run5.exists():
        raise FileNotFoundError(f"Không tìm thấy manifest Run 5: {args.manifest_run5}")

    man = pd.read_csv(args.manifest_run5)
    man_rnd = man[man.distribution == "random"].copy()

    # Nhóm N theo thang
    scales_new = {}
    for n in sorted(man_rnd["N"].unique()):
        # Xác định thang bằng log2
        k = int(math.floor(math.log2(n)))
        if k in (14, 18):
            sc = f"2^{k}"
            scales_new.setdefault(sc, []).append(n)

    alpha_new = {"2^14": alpha14, "2^18": alpha18}
    rows_m2 = []
    scale_summary = {}

    for sc, ns in scales_new.items():
        assert len(ns) == 24, f"Thang {sc} có {len(ns)} giá trị N, kỳ vọng 24"
        a = alpha_new[sc]

        # Lưu r_hat(N, c) cho thang này: dict cutoff -> list of r_hat
        r_by_cutoff = {c: [] for c in GRID_35}
        n_rows = []

        for n in ns:
            # Tính T1 trước
            ts1 = tree_stats(n, 1)
            b1_1, b2_1, b3_1 = ts1[6], ts1[7], ts1[8]
            b456_1 = ts1[9] + ts1[10] + ts1[11]
            e_rand_1 = ts1[5] / 2.0  # = 0 khi c=1
            T1_hat = w1 * b1_1 + w2 * b2_1 + w3 * b3_1 + beta * e_rand_1 + a * b456_1

            for c in GRID_35:
                ts = tree_stats(n, c)
                b1, b2, b3 = ts[6], ts[7], ts[8]
                b456 = ts[9] + ts[10] + ts[11]
                e_rand = ts[5] / 2.0
                T_hat = w1 * b1 + w2 * b2 + w3 * b3 + beta * e_rand + a * b456
                r_hat = T_hat / T1_hat

                r_by_cutoff[c].append(r_hat)
                n_rows.append({
                    "scale": sc,
                    "N": n,
                    "cutoff": c,
                    "r_hat_interp": r_hat,
                    "r_hat_calib": ""  # Để trống theo hợp đồng §9
                })

        # Trung bình nhân r_hat theo thang: exp(mean(log(r_hat)))
        scale_geomean_r = {}
        for c, r_list in r_by_cutoff.items():
            geo_mean = math.exp(np.mean(np.log(r_list)))
            scale_geomean_r[c] = geo_mean

        c_star_m2 = min(scale_geomean_r.keys(), key=lambda c: scale_geomean_r[c])
        r_star_m2 = scale_geomean_r[c_star_m2]
        near_opt_cutoffs = [c for c, val in scale_geomean_r.items() if val <= 1.02 * r_star_m2]
        near_opt_str = compress_range(near_opt_cutoffs)

        scale_summary[sc] = {
            "alpha": a,
            "c_star": c_star_m2,
            "r_star": r_star_m2,
            "near_optimal_2pct": near_opt_str,
            "near_optimal_list": near_opt_cutoffs,
            "r_by_c": scale_geomean_r
        }

        # Bổ sung c_star_M2_scale và near_optimal_2pct_scale vào các hàng
        for row in n_rows:
            row["c_star_M2_scale"] = c_star_m2
            row["near_optimal_2pct_scale"] = near_opt_str
            rows_m2.append(row)

    df_m2_pred = pd.DataFrame(rows_m2)
    m2_out = args.out_dir / "T09_predictions_m2.csv"
    df_m2_pred.to_csv(m2_out, index=False)
    print(f"  Đã ghi {len(df_m2_pred)} dòng dự đoán M2 vào: {m2_out}")

    print("\nTÓM TẮT DỰ ĐOÁN M2 THEO THANG MỚI:")
    print(f"{'Thang':<8s} {'alpha (nội suy)':<16s} {'c*_M2':<8s} {'r*(c*)':<10s} {'Vùng gần tối ưu (<= 2%)':<30s}")
    for sc, sinfo in scale_summary.items():
        print(f"{sc:<8s} {sinfo['alpha']:<16.6f} {sinfo['c_star']:<8d} {sinfo['r_star']:<10.4f} {sinfo['near_optimal_2pct']:<30s}")

    # ────────────────────────────────────────────────────────────────
    # 4. Dự đoán Doubling v2: preregistration/T09_predictions_doubling_v2.csv
    # ────────────────────────────────────────────────────────────────
    print("\n" + "-" * 80)
    print("DỰ ĐOÁN DOUBLING V2 (H11, H12)")
    print("-" * 80)
    # k = 10..23 (bước k -> k+1)
    # b = 1.202 (c=1), 1.213 (c=30)
    b_map = {1: 1.202, 30: 1.213}
    ln2 = math.log(2.0)

    # Đọc A1z
    a1z_data = {}
    if args.a1z_file.exists():
        df_a1z = pd.read_csv(args.a1z_file)
        df_a1z_p1 = df_a1z[(df_a1z.predictor == "P1_theory_nlgn") & (df_a1z.cutoff.isin([1, 30]))]
        for _, r in df_a1z_p1.iterrows():
            k_f = int(r["k_from"])
            c = int(r["cutoff"])
            a1z_data[(k_f, c)] = (math.log(float(r["R_bar"])), float(r["SE_k"]))

    rows_db = []
    for k in range(10, 24):
        for c in [1, 30]:
            lnR_tiep = b_map[c] * ln2
            # P-bão hòa: R = 2(k+1)/k
            lnR_baohoa = math.log(2.0 * (k + 1) / k)
            lnR_v1_val, se_v1_val = "", ""
            if (k, c) in a1z_data:
                lnR_v1_val = f"{a1z_data[(k, c)][0]:.6f}"
                se_v1_val = f"{a1z_data[(k, c)][1]:.6f}"

            rows_db.append({
                "k": k,
                "cutoff": c,
                "lnR_P_tiep": f"{lnR_tiep:.6f}",
                "lnR_P_baohoa": f"{lnR_baohoa:.6f}",
                "lnR_v1": lnR_v1_val,
                "SE_v1": se_v1_val
            })

    df_db_pred = pd.DataFrame(rows_db)
    db_out = args.out_dir / "T09_predictions_doubling_v2.csv"
    df_db_pred.to_csv(db_out, index=False)
    print(f"  Đã ghi {len(df_db_pred)} dòng dự đoán doubling v2 vào: {db_out}")
    print("\nMẫu dự đoán ngoại suy tại k = 22, 23 (H12):")
    print(df_db_pred[df_db_pred.k.isin([22, 23])].to_string(index=False))

    # ────────────────────────────────────────────────────────────────
    # 5. Danh sách giả thuyết: preregistration/T09_hypotheses.csv
    # ────────────────────────────────────────────────────────────────
    print("\n" + "-" * 80)
    print("XUẤT DANH SÁCH GIẢ THUYẾT H1 - H17 (T09_hypotheses.csv)")
    print("-" * 80)
    hypotheses = [
        {
            "id": "H1",
            "short_description": "Vùng tối ưu, random, 5 thang",
            "metric": "c*, near_optimal_2pct",
            "decision_rule": "c* thuộc [17, 48] VÀ tập gần tối ưu chứa {24, 25, ..., 32} ở CẢ 5 thang (2^12, 2^14, 2^16, 2^18, 2^19)",
            "threshold": "c* in [17, 48], {24..32} subset near_optimal_2pct"
        },
        {
            "id": "H2",
            "short_description": "10 nhanh hơn 7, random, 5 thang",
            "metric": "T7/T10, CI 95% hai tầng",
            "decision_rule": "T7/T10 > 1 với cận dưới CI hai tầng 95% > 1 (Holm trên 5 thang, mức 0.05)",
            "threshold": "CI_lower(T7/T10) > 1.0 (Holm adj p < 0.05)"
        },
        {
            "id": "H3",
            "short_description": "Lặp lại độ lớn, random",
            "metric": "|r_Run5(c*) - r_GD1(c*)|",
            "decision_rule": "|r_Run5(c*) - r_GD1(c*)| <= 0.015 ở cả 3 thang 2^12, 2^16, 2^19 (r_GD1 = 0.848, 0.888, 0.918)",
            "threshold": "<= 0.015"
        },
        {
            "id": "H4",
            "short_description": "Lợi ích giảm theo N",
            "metric": "r(c*) theo thang",
            "decision_rule": "r(c*) tăng nghiêm ngặt 2^12 < 2^16 < 2^19 với CI hai tầng không chồng nhau giữa thang liền kề; và ở 5 thang, mọi bước tăng âm <= 0.005",
            "threshold": "CI_hi(2^12) < CI_lo(2^16) < CI_lo(2^19); max decrease <= 0.005"
        },
        {
            "id": "H5",
            "short_description": "Khoảng 20%",
            "metric": "r(c*)",
            "decision_rule": "r(c*) > 0.833 ở cả 5 thang (không đạt 1.2x và không đạt r = 0.80)",
            "threshold": "> 0.833 ở cả 5 thang"
        },
        {
            "id": "H6",
            "short_description": "Reversed",
            "metric": "c* (reversed, 3 thang)",
            "decision_rule": "c* thuộc [6, 16] ở cả 3 thang 2^12, 2^16, 2^19",
            "threshold": "c* in [6, 16]"
        },
        {
            "id": "H7",
            "short_description": "Few distinct",
            "metric": "c* (few_distinct, 3 thang)",
            "decision_rule": "c* thuộc [17, 48] ở cả 3 thang 2^12, 2^16, 2^19",
            "threshold": "c* in [17, 48]"
        },
        {
            "id": "H8",
            "short_description": "Sorted (D4)",
            "metric": "r(c) monotonicity, c* (sorted, 3 thang)",
            "decision_rule": "r(c) không tăng theo c trên toàn lưới (cho phép 1 bước tăng <= 0.01 do nhiễu) và c* là biên trên (4096) ở cả 3 thang",
            "threshold": "c* = 4096; max_step_increase <= 0.01"
        },
        {
            "id": "H9",
            "short_description": "Nearly sorted (D4)",
            "metric": "c* (nearly_sorted, 3 thang)",
            "decision_rule": "Có cực tiểu bên trong: c* thuộc {128, 192, 256, 384, 512, 768, 1024} (không ở biên 4096) ở cả 3 thang",
            "threshold": "c* in {128, 192, 256, 384, 512, 768, 1024}"
        },
        {
            "id": "H10",
            "short_description": "Độ chính xác M2 (xác nhận)",
            "metric": "RMSE(r_hat - r) trên 35 cutoff, c*_M2",
            "decision_rule": "Ở mỗi thang 2^14 và 2^18: RMSE(r_hat - r) trên 35 cutoff <= 0.012 VÀ c*_M2 thuộc tập gần tối ưu 2% đo được",
            "threshold": "RMSE <= 0.012; c*_M2 in near_optimal_2pct"
        },
        {
            "id": "H10b",
            "short_description": "Độ chính xác M2 (phụ, alpha hiệu chỉnh từ hàng c=1)",
            "metric": "RMSE(r_hat_calib - r) trên 35 cutoff",
            "decision_rule": "Biến thể alpha hiệu chỉnh từ hàng c=1 của chính thang đạt RMSE <= 0.012 ở cả 2^14 và 2^18",
            "threshold": "RMSE <= 0.012"
        },
        {
            "id": "H11",
            "short_description": "Lặp lại doubling v1",
            "metric": "|ln R_bar_k(v2) - ln R_bar_k(v1)|",
            "decision_rule": "Với k in {19, 20, 21} và c in {1, 30}: |ln R_bar_k(v2) - ln R_bar_k(v1)| <= 3*sqrt(SE_k(v1)^2 + SE_k(v2)^2)",
            "threshold": "<= 3*sqrt(SE_v1^2 + SE_v2^2)"
        },
        {
            "id": "H12",
            "short_description": "Ngoại suy doubling tới 2^24 (P-tiếp vs P-bão hòa)",
            "metric": "|ln R_bar_k - ln R_hat_k|",
            "decision_rule": "Một dự đoán đạt nếu |ln R_bar_k - ln R_hat_k| <= 3*SE_k ở cả k=22 và 23, với cả c=1 và c=30",
            "threshold": "<= 3*SE_k"
        },
        {
            "id": "H13",
            "short_description": "Kiểm soát cùng cây doubling",
            "metric": "|Delta_bar| các cặp (4, 7), (8, 10), (16, 30)",
            "decision_rule": "Ở mọi k, các cặp có chênh trung bình |Delta_bar| <= 1%",
            "threshold": "<= 1% (0.01)"
        },
        {
            "id": "H14",
            "short_description": "D3: int[] có lợi thế hơn Integer[]",
            "metric": "r_int(c*), c*_int vs Integer[]",
            "decision_rule": "r_int(c*) < r_Integer(c*) ở cả 3 thang (cận trên CI của hiệu < 0) và c*_int >= c*_Integer ở cả 3 thang",
            "threshold": "CI_upper(r_int - r_Integer) < 0; c*_int >= c*_Integer"
        },
        {
            "id": "H15",
            "short_description": "Cơ chế bộ nhớ của việc lợi ích giảm theo N",
            "metric": "Độ co lại lợi ích từ 2^12 đến 2^19 của int[] vs Integer[]",
            "decision_rule": "[r_int(c*, 2^19) - r_int(c*, 2^12)] < 0.5 * [r_Integer(c*, 2^19) - r_Integer(c*, 2^12)] đo trong cùng phiên",
            "threshold": "< 0.5 * Delta_r_Integer"
        },
        {
            "id": "H16",
            "short_description": "D3: Double[] tương đương Integer[]",
            "metric": "|r_Double(c*) - r_Integer(c*)|",
            "decision_rule": "|r_Double(c*) - r_Integer(c*)| <= 0.02 ở cả 3 thang",
            "threshold": "<= 0.02"
        },
        {
            "id": "H17",
            "short_description": "T08: Kiểm chứng chéo bằng JMH",
            "metric": "|r_JMH(N, c) - r_Run5(N, c)|, thứ tự T(c)",
            "decision_rule": "|r_JMH(N, c) - r_Run5(N, c)| <= 0.02 cho mọi N in {4096, 65536, 524288} và c in {7, 10, 30}; và thứ tự T(30) < T(10) < T(7) < T(1) đúng ở cả 3 N",
            "threshold": "<= 0.02; T(30) < T(10) < T(7) < T(1)"
        }
    ]

    df_hyp = pd.DataFrame(hypotheses)
    hyp_out = args.out_dir / "T09_hypotheses.csv"
    df_hyp.to_csv(hyp_out, index=False)
    print(f"  Đã ghi {len(df_hyp)} giả thuyết (H1-H17) vào: {hyp_out}")
    print("\nHOÀN THÀNH TÍNH TOÁN DỰ ĐOÁN SỐ T09!")


if __name__ == "__main__":
    main()
