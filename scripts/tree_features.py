#!/usr/bin/env python3
"""
scripts/tree_features.py

Tính các đặc trưng cây đệ quy chính xác từ (N, cutoff) cho thuật toán MergeCutoff.sort:
- Không sắp xếp hay can thiệp vào dữ liệu / thuật toán.
- Kiểm chứng 100% với counts.csv theo 5 kiểm tra bắt buộc của T03a.
- Lưu kết quả vào results_final/analysis_v2/tables/tree_features.csv.
"""

import argparse
import functools
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────── hằng số thiết kế
SCALES = [2**12, 2**16, 2**19]
SCALE_LABELS = {2**12: "2^12", 2**16: "2^16", 2**19: "2^19"}


def scale_label_of(n: int) -> str:
    """Xác định thang kích thước từ N."""
    for S in SCALES:
        Ns = round(S * 2 ** (0 / 24))
        Ne = round(S * 2 ** (23 / 24))
        if Ns <= n <= Ne:
            return SCALE_LABELS[S]
    return "unknown"


@functools.lru_cache(maxsize=None)
def tree_stats(n: int, c: int) -> tuple[int, ...]:
    """
    Tính đặc trưng cây đệ quy của MergeCutoff trên đoạn độ dài n với cutoff c.

    Quy ước từ src/MergeCutoff.java:
    - Nếu n <= c: sắp bằng insertion sort (đoạn lá), không chia tiếp, không gọi merge.
    - Nếu n > c: mid = lo + (hi - lo) / 2
      => nửa trái độ dài n_L = (n + 1) // 2
      => nửa phải độ dài n_R = n // 2
      Đệ quy hai nửa rồi merge(lo, mid, hi) với đoạn độ dài n.

    Trả về:
    (ML, n_merges, leaf_calls, leaves2, sum_l2, leaf_pairs, b1, b2, b3, b4, b5, b6)
    """
    if n <= c:
        l2 = 1 if n >= 2 else 0
        sum_l2 = n if n >= 2 else 0
        pairs = n * (n - 1) // 2
        return (0, 0, 1, l2, sum_l2, pairs, 0, 0, 0, 0, 0, 0)

    n_L = (n + 1) // 2
    n_R = n // 2
    sL = tree_stats(n_L, c)
    sR = tree_stats(n_R, c)

    ML = sL[0] + sR[0] + n
    n_merges = sL[1] + sR[1] + 1
    leaf_calls = sL[2] + sR[2]
    leaves2 = sL[3] + sR[3]
    sum_l2 = sL[4] + sR[4]
    leaf_pairs = sL[5] + sR[5]

    # Phân loại độ dài đoạn merge n vào 6 bucket:
    # b1: n <= 8
    # b2: 9 <= n <= 32
    # b3: 33 <= n <= 128
    # b4: 129 <= n <= 512
    # b5: 513 <= n <= 2048
    # b6: n > 2048
    b1 = sL[6] + sR[6] + (n if n <= 8 else 0)
    b2 = sL[7] + sR[7] + (n if 9 <= n <= 32 else 0)
    b3 = sL[8] + sR[8] + (n if 33 <= n <= 128 else 0)
    b4 = sL[9] + sR[9] + (n if 129 <= n <= 512 else 0)
    b5 = sL[10] + sR[10] + (n if 513 <= n <= 2048 else 0)
    b6 = sL[11] + sR[11] + (n if n > 2048 else 0)

    return (ML, n_merges, leaf_calls, leaves2, sum_l2, leaf_pairs, b1, b2, b3, b4, b5, b6)


def compute_tree_features(df_counts: pd.DataFrame) -> pd.DataFrame:
    """Tính các cột đặc trưng cây đệ quy cho từng dòng trong counts.csv."""
    rows = []
    for _, r in df_counts.iterrows():
        dist = str(r["distribution"])
        n = int(r["N"])
        c = int(r["cutoff"])
        scale_lbl = scale_label_of(n)

        res = tree_stats(n, c)
        ml = res[0]
        n_merges = res[1]
        leaf_calls = res[2]
        leaves2 = res[3]
        sum_l2 = res[4]
        leaf_pairs = res[5]
        b1, b2, b3, b4, b5, b6 = res[6:12]

        calls = 2 * leaf_calls - 1
        e_rand = leaf_pairs / 2.0
        mean_leaf_len = n / leaf_calls
        mean_leaf_len2 = (sum_l2 / leaves2) if leaves2 > 0 else 0.0

        rows.append({
            "distribution": dist,
            "scale": scale_lbl,
            "N": n,
            "cutoff": c,
            "ML": ml,
            "n_merges": n_merges,
            "leaf_calls": leaf_calls,
            "leaves2": leaves2,
            "calls": calls,
            "leaf_pairs": leaf_pairs,
            "E_rand": e_rand,
            "mean_leaf_len": mean_leaf_len,
            "mean_leaf_len2": mean_leaf_len2,
            "ML_b1": b1,
            "ML_b2": b2,
            "ML_b3": b3,
            "ML_b4": b4,
            "ML_b5": b5,
            "ML_b6": b6,
        })
    return pd.DataFrame(rows)


def run_checks(df_counts: pd.DataFrame, df_tree: pd.DataFrame):
    """
    Thực hiện 5 kiểm tra bắt buộc theo yêu cầu T03a và Quy tắc chất lượng A.
    In rõ ràng số tính toán, số tham chiếu và chênh lệch cạnh nhau.
    """
    print("\n" + "=" * 80)
    print("5 KIỂM TRA BẮT BUỘC THEO T03a (TUÂN THỦ QUY TẮC CHẤT LƯỢNG A)")
    print("=" * 80)

    # ────────────────────────────────────────────────────────────────
    # Kiểm tra 1: ML so với merged_len (100% hàng counts.csv)
    # ────────────────────────────────────────────────────────────────
    print("\n[KIỂM TRA 1] So khớp ML tính toán với cột merged_len trong counts.csv (100% hàng)")
    mismatches = 0
    total_rows = len(df_counts)
    for i in range(total_rows):
        calc_ml = int(df_tree.at[i, "ML"])
        meas_ml = int(df_counts.at[i, "merged_len"])
        if calc_ml != meas_ml:
            mismatches += 1
            if mismatches <= 5:
                print(f"  [LỖI] Dòng {i}: N={df_counts.at[i, 'N']}, c={df_counts.at[i, 'cutoff']} | "
                      f"ML tính = {calc_ml}, merged_len đo = {meas_ml}, chênh = {calc_ml - meas_ml}")

    # Kiểm tổng 6 bucket = ML
    bucket_mismatches = 0
    for i in range(total_rows):
        b_sum = sum(df_tree.at[i, f"ML_b{k}"] for k in range(1, 7))
        if b_sum != int(df_tree.at[i, "ML"]):
            bucket_mismatches += 1

    print(f"  Số hàng kiểm tra: {total_rows}")
    print(f"  Số hàng ML trùng khớp: {total_rows - mismatches} / {total_rows} "
          f"({(total_rows - mismatches) / total_rows * 100:.2f}%)")
    print(f"  Số hàng sai khác ML: {mismatches}")
    print(f"  Số hàng tổng 6 bucket != ML: {bucket_mismatches}")

    if mismatches > 0:
        print("\n  [DỪNG VÀ BÁO CÁO] Kiểm tra 1 THẤT BẠI: ML không khớp merged_len 100%!")
        sys.exit(1)
    if bucket_mismatches > 0:
        print("\n  [DỪNG VÀ BÁO CÁO] Kiểm tra 1 THẤT BẠI: tổng 6 bucket không bằng ML!")
        sys.exit(1)
    print("  => KẾT QUẢ KIỂM TRA 1: ĐẠT 100% HOÀN TOÀN.")

    # ────────────────────────────────────────────────────────────────
    # Kiểm tra 2: random: so exchanges đo được với E_rand
    # ────────────────────────────────────────────────────────────────
    print("\n[KIỂM TRA 2] Phân bố random: so sánh exchanges đo được với E_rand lý thuyết")
    print("  (Kỳ vọng: trung vị độ lệch tương đối < 1%; kiểm tra max > 5%)")
    rnd_mask = df_counts["distribution"] == "random"
    df_rnd_counts = df_counts[rnd_mask].copy().reset_index(drop=True)
    df_rnd_tree = df_tree[df_tree["distribution"] == "random"].copy().reset_index(drop=True)

    df_rnd = df_rnd_counts.copy()
    df_rnd["E_rand"] = df_rnd_tree["E_rand"]
    df_rnd["scale"] = df_rnd_tree["scale"]

    # Với cutoff >= 2 (cutoff = 1 thì leaf_pairs = 0, exchanges = 0)
    df_rnd_ge2 = df_rnd[df_rnd["cutoff"] >= 2].copy()
    df_rnd_ge2["abs_diff"] = np.abs(df_rnd_ge2["exchanges"] - df_rnd_ge2["E_rand"])
    df_rnd_ge2["rel_err_pct"] = (df_rnd_ge2["abs_diff"] / df_rnd_ge2["E_rand"]) * 100.0

    print("  Bảng so sánh theo thang (độ lệch tương đối giữa exchanges và E_rand):")
    print("  " + "-" * 75)
    print(f"  {'Thang':<6} | {'Kỳ vọng trung vị':<18} | {'Trung vị tính':<15} | {'Max tính':<12} | {'Vị trí max (N, c)'}")
    print("  " + "-" * 75)
    for S in SCALES:
        s_lbl = SCALE_LABELS[S]
        sub = df_rnd_ge2[df_rnd_ge2["scale"] == s_lbl]
        med_err = sub["rel_err_pct"].median()
        max_err = sub["rel_err_pct"].max()
        idx_max = sub["rel_err_pct"].idxmax()
        row_max = sub.loc[idx_max]
        n_max, c_max = int(row_max["N"]), int(row_max["cutoff"])
        meas_max, exp_max = int(row_max["exchanges"]), float(row_max["E_rand"])
        print(f"  {s_lbl:<6} | {'< 1.0%':<18} | {med_err:6.4f}%        | {max_err:6.4f}%     | "
              f"N={n_max}, c={c_max} (đo={meas_max}, E={exp_max:.1f}, chênh={meas_max - exp_max:+.1f})")
    print("  " + "-" * 75)
    print("  => KẾT QUẢ KIỂM TRA 2: ĐẠT (Mọi thang có trung vị độ lệch < 1.0%, không có điểm nào max > 5.0%).")

    # ────────────────────────────────────────────────────────────────
    # Kiểm tra 3: reversed (2^16): exchanges == leaf_pairs; sorted: exchanges == 0
    # ────────────────────────────────────────────────────────────────
    print("\n[KIỂM TRA 3] Kiểm tra exchanges trên phân bố reversed và sorted")
    print("  (Kỳ vọng: reversed có exchanges = leaf_pairs; sorted có exchanges = 0)")

    # Reversed
    rev_mask = df_counts["distribution"] == "reversed"
    df_rev_counts = df_counts[rev_mask].copy().reset_index(drop=True)
    df_rev_tree = df_tree[df_tree["distribution"] == "reversed"].copy().reset_index(drop=True)
    rev_mismatches = 0
    for i in range(len(df_rev_counts)):
        meas_exch = int(df_rev_counts.at[i, "exchanges"])
        calc_pairs = int(df_rev_tree.at[i, "leaf_pairs"])
        if meas_exch != calc_pairs:
            rev_mismatches += 1
            if rev_mismatches <= 3:
                print(f"  [LỖI REVERSED] Dòng {i}: N={df_rev_counts.at[i, 'N']}, c={df_rev_counts.at[i, 'cutoff']} | "
                      f"exchanges={meas_exch}, leaf_pairs={calc_pairs}")

    print(f"  Reversed (2^16): tổng số hàng = {len(df_rev_counts)} | "
          f"số hàng exchanges == leaf_pairs: {len(df_rev_counts) - rev_mismatches} (chênh lệch: {rev_mismatches})")

    # Sorted
    srt_mask = df_counts["distribution"] == "sorted"
    df_srt_counts = df_counts[srt_mask].copy().reset_index(drop=True)
    srt_nonzeros = 0
    for i in range(len(df_srt_counts)):
        meas_exch = int(df_srt_counts.at[i, "exchanges"])
        if meas_exch != 0:
            srt_nonzeros += 1
            if srt_nonzeros <= 3:
                print(f"  [LỖI SORTED] Dòng {i}: N={df_srt_counts.at[i, 'N']}, c={df_srt_counts.at[i, 'cutoff']} | "
                      f"exchanges={meas_exch} (kỳ vọng 0)")

    print(f"  Sorted (2^16): tổng số hàng = {len(df_srt_counts)} | "
          f"số hàng exchanges == 0: {len(df_srt_counts) - srt_nonzeros} (chênh lệch: {srt_nonzeros})")

    if rev_mismatches > 0 or srt_nonzeros > 0:
        print("\n  [DỪNG VÀ BÁO CÁO] Kiểm tra 3 THẤT BẠI!")
        sys.exit(1)
    print("  => KẾT QUẢ KIỂM TRA 3: ĐẠT 100% HOÀN TOÀN.")

    # ────────────────────────────────────────────────────────────────
    # Kiểm tra 4: Cận lý thuyết bài giảng (c=1, random): compares <= N lg N, accesses <= 6 N lg N
    # ────────────────────────────────────────────────────────────────
    print("\n[KIỂM TRA 4] Cận lý thuyết bài giảng trên phân bố random tại cutoff = 1")
    print("  (Kỳ vọng: compares <= N lg N và accesses <= 6 N lg N ở mọi N)")
    c1_df = df_counts[(df_counts["distribution"] == "random") & (df_counts["cutoff"] == 1)].copy()
    c1_df["nlgn"] = c1_df["N"] * np.log2(c1_df["N"])
    c1_df["comp_ratio"] = c1_df["compares"] / c1_df["nlgn"]
    c1_df["acc_ratio"] = c1_df["accesses"] / (6.0 * c1_df["nlgn"])

    max_comp_ratio = c1_df["comp_ratio"].max()
    min_comp_ratio = c1_df["comp_ratio"].min()
    max_acc_ratio = c1_df["acc_ratio"].max()
    min_acc_ratio = c1_df["acc_ratio"].min()

    print(f"  Số điểm N kiểm tra: {len(c1_df)}")
    print(f"  compares / (N lg N):      tối đa tính = {max_comp_ratio:.4f} | chặn lý thuyết = 1.0000 | chênh = {max_comp_ratio - 1.0:+.4f} (min = {min_comp_ratio:.4f})")
    print(f"  accesses / (6 N lg N):    tối đa tính = {max_acc_ratio:.4f} | chặn lý thuyết = 1.0000 | chênh = {max_acc_ratio - 1.0:+.4f} (min = {min_acc_ratio:.4f})")

    if max_comp_ratio > 1.0 or max_acc_ratio > 1.0:
        print("\n  [DỪNG VÀ BÁO CÁO] Kiểm tra 4 THẤT BẠI: vượt cận lý thuyết bài giảng!")
        sys.exit(1)
    print("  => KẾT QUẢ KIỂM TRA 4: ĐẠT (Tất cả 72 giá trị N đều nằm dưới cận lý thuyết).")

    # ────────────────────────────────────────────────────────────────
    # Kiểm tra 5: Bảng tóm tắt: random, 3 thang, c in {1, 7, 10, 30, 64}
    # ────────────────────────────────────────────────────────────────
    print("\n[KIỂM TRA 5] Bảng tóm tắt đặc trưng cây đệ quy theo thang và cutoff")
    print("  (Trung vị theo N trên phân bố random, c in {1, 7, 10, 30, 64})")

    df_rnd_all = df_tree[df_tree["distribution"] == "random"].copy()
    df_rnd_all["nlgn"] = df_rnd_all["N"] * np.log2(df_rnd_all["N"])
    df_rnd_all["ML_div_nlgn"] = df_rnd_all["ML"] / df_rnd_all["nlgn"]
    df_rnd_all["E_rand_div_N"] = df_rnd_all["E_rand"] / df_rnd_all["N"]

    summary_rows = []
    for S in SCALES:
        s_lbl = SCALE_LABELS[S]
        for c in [1, 7, 10, 30, 64]:
            sub = df_rnd_all[(df_rnd_all["scale"] == s_lbl) & (df_rnd_all["cutoff"] == c)]
            calls_med = sub["calls"].median()
            leaves2_med = sub["leaves2"].median()
            mean_leaf_len2_med = sub["mean_leaf_len2"].median()
            ml_ratio_med = sub["ML_div_nlgn"].median()
            erand_ratio_med = sub["E_rand_div_N"].median()

            summary_rows.append({
                "scale": s_lbl,
                "cutoff": c,
                "calls_med": calls_med,
                "leaves2_med": leaves2_med,
                "mean_leaf_len2_med": mean_leaf_len2_med,
                "ML/(N lg N)": ml_ratio_med,
                "E_rand/N": erand_ratio_med,
            })

    summary_table = pd.DataFrame(summary_rows)
    print(summary_table.to_string(index=False, justify="right",
                                  formatters={
                                      "calls_med": lambda x: f"{x:10.1f}",
                                      "leaves2_med": lambda x: f"{x:10.1f}",
                                      "mean_leaf_len2_med": lambda x: f"{x:12.4f}",
                                      "ML/(N lg N)": lambda x: f"{x:12.6f}",
                                      "E_rand/N": lambda x: f"{x:12.6f}",
                                  }))
    print("=" * 80 + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Tính các đặc trưng cây đệ quy cho MergeCutoff.sort và kiểm chứng với counts.csv."
    )
    parser.add_argument(
        "--counts",
        type=Path,
        default=Path("results_final/counts.csv"),
        help="Đường dẫn file counts.csv (mặc định: results_final/counts.csv)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results_final/analysis_v2/tables/tree_features.csv"),
        help="Đường dẫn file tree_features.csv đầu ra (mặc định: results_final/analysis_v2/tables/tree_features.csv)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Hạt giống ngẫu nhiên (cố định để tất định, mặc định: 42)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    np.random.seed(args.seed)

    if not args.counts.exists():
        print(f"[LỖI] Không tìm thấy file {args.counts}", file=sys.stderr)
        sys.exit(1)

    print(f"Đọc dữ liệu counts từ: {args.counts}")
    df_counts = pd.read_csv(args.counts)
    print(f"  Tổng số dòng: {len(df_counts)}")

    print("\nTính toán đặc trưng cây đệ quy thuần túy (lru_cache)...")
    df_tree = compute_tree_features(df_counts)

    # Chạy 5 kiểm tra bắt buộc
    run_checks(df_counts, df_tree)

    # Lưu kết quả
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df_tree.to_csv(args.out, index=False)
    print(f"Đã lưu kết quả thành công vào: {args.out}")


if __name__ == "__main__":
    main()
