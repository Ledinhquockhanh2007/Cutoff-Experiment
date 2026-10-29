#!/usr/bin/env python3
"""
merge_run4.py - Hợp nhất dữ liệu thí nghiệm Run 3 và Run 4 tạo results_final/

Quy trình:
  - Lấy toàn bộ results_run3/ NGOẠI TRỪ các hàng random của thang 2^12 (N in [4096, 7959])
    trong raw_fork*.csv và warmup_fork*.csv.
  - Thay bằng các hàng random thang 2^12 từ results_run4/ (đo lại với K = 1).
  - Giữ nguyên counts.csv từ results_run3/ (số đếm thao tác không phụ thuộc K).
  - Lấy env_fork*.txt từ results_run3/, kèm MERGE_README.txt ghi rõ nguồn gốc, sha256,
    quy ước fork và danh sách ảnh hưởng đối với các phân tích cần fork xuyên thang.

Cách dùng:
  python scripts/merge_run4.py [--run3 results_run3] [--run4 results_run4] [--out results_final]
"""

from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import sys
import pandas as pd


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def is_scale_4096_random(df: pd.DataFrame) -> pd.Series:
    """Trả về True cho các hàng distribution == 'random' và 4096 <= N < 8192."""
    return (df["distribution"] == "random") & (df["N"] >= 4096) & (df["N"] < 8192)


def generate_readme(run3_dir: Path, run4_dir: Path, out_dir: Path, stats: dict) -> str:
    lines = [
        "================================================================================",
        "MERGE_README.txt - NGUỒN GỐC VÀ QUY ƯỚC DỮ LIỆU RESULTS_FINAL",
        "================================================================================",
        "",
        "1. MỤC ĐÍCH VÀ NGUYÊN DO",
        "  Thí nghiệm KDiag (results_kdiag/) xác nhận việc đo theo lô K > 1 (TARGET_BATCH_NS = 2ms)",
        "  làm sai lệch có hệ thống thời gian một lần sắp ở thang 2^12 (N = 4096..7959) trong Run 3,",
        "  làm giảm thời gian tới 18.3% và thổi phồng mức giảm r của CUTOFF tối ưu khoảng 2.4 điểm %.",
        "  Các thang 2^16 và 2^19 có K = 1 từ thiết kế nên hoàn toàn sạch.",
        "  Run 4 đo lại toàn bộ 24 N của thang 2^12 (random) với cờ --fixed-k 1 (K = 1 cho mọi lần đo),",
        "  ghim nhân vật lý 5 (/affinity C00) giống hệt Run 3.",
        "  Thư mục results_final/ là kết quả hợp nhất chuẩn mực cho toàn bộ báo cáo chính.",
        "",
        "2. NGUỒN TỪNG PHẦN TRONG RESULTS_FINAL",
        "  - raw_fork{1,2,3}.csv:",
        f"      * Thang 2^12 random ({stats['run4_raw_rows_per_fork']} hàng/fork): lấy từ {run4_dir.name}/raw_fork*.csv (K = 1).",
        f"      * Thang 2^16, 2^19 random và 4 phân bố khác ({stats['run3_kept_raw_rows_per_fork']} hàng/fork): lấy từ {run3_dir.name}/raw_fork*.csv.",
        f"      * Tổng cộng: {stats['total_raw_rows_per_fork']} hàng/fork.",
        "  - warmup_fork{1,2,3}.csv:",
        "      * Warmup bộ dữ liệu 2^12 random: lấy từ results_run4/warmup_fork*.csv.",
        "      * Warmup JVM và các bộ dữ liệu khác: lấy từ results_run3/warmup_fork*.csv.",
        "  - counts.csv:",
        "      * Lấy nguyên văn từ results_run3/counts.csv (số đếm phép so sánh, truy cập, đổi chỗ",
        "        và độ dài merge chỉ phụ thuộc thuật toán và dữ liệu đầu vào, không phụ thuộc K hay JVM).",
        "  - env_fork{1,2,3}.txt:",
        "      * Lấy nguyên văn từ results_run3/env_fork*.txt (môi trường JVM của lượt chạy chính 75 phút).",
        "      * Run 4 chạy trên cùng máy, cùng JDK (Microsoft 25.0.4.1), cùng cờ JVM và cùng ghim nhân 5.",
        "",
        "3. QUY ƯỚC QUAN TRỌNG VỀ FORK VÀ HỆ QUẢ PHÂN TÍCH",
        "  QUY ƯỚC: 'Fork f ở 2^12 là một JVM KHÁC với fork f ở các thang khác (2^16, 2^19)'.",
        "  Hệ quả đối với các phân tích trong scripts/analyze.py:",
        "    a) Tỉ số r = T(c)/T(1) và RQ1 (rq1_best_cutoff.csv, r_by_cutoff.csv):",
        "       HOÀN TOÀN HỢP LỆ VÀ CHUẨN XÁC, vì r được ghép cặp trong cùng (fork, bộ dữ liệu, trial).",
        "       Việc 2^12 đo ở một JVM riêng không ảnh hưởng gì tới việc ghép cặp nội bộ 2^12.",
        "    b) Bảng theo từng JVM (per_jvm.csv, per_jvm_summary.csv):",
        "       Khi so sánh xuyên thang theo cùng fork f, cần nhớ rằng thời gian tuyệt đối của thang 2^12",
        "       được thu thập từ JVM Run 4, trong khi 2^16 và 2^19 từ JVM Run 3.",
        "    c) Phân tích trôi dạt (drift.csv, fig14_drift.png):",
        "       Hồi quy trôi dạt theo run_order trong fork: hàng 2^12 đến từ phiên JVM của Run 4",
        "       (trục thời gian riêng).",
        "    d) Tóm tắt môi trường (env_summary.csv):",
        "       Các thông số thời gian bắt đầu, kết thúc, tổng thời gian và RAM phản ánh JVM của Run 3.",
        "    e) Mô hình lũy thừa T = a N^b fitted trên toàn bộ 72 N:",
        "       Khớp đa thang (72 N) ghép 24 N của Run 4 với 48 N của Run 3. Do cùng ghim nhân 5 ở xung",
        "       ~129% và mức xung ổn định, mô hình gộp trên 3 fork là nhất quán.",
        "",
        "4. SHA256 CÁC TỆP NGUỒN",
    ]
    for p, h in stats["sha256_sources"].items():
        lines.append(f"  {h}  {p}")
    lines.append("")
    lines.append("================================================================================")
    return "\n".join(lines) + "\n"


def merge(run3_dir: Path, run4_dir: Path, out_dir: Path) -> dict:
    if not run3_dir.exists():
        sys.exit(f"Lỗi: Thư mục Run 3 không tồn tại: {run3_dir}")
    if not run4_dir.exists():
        sys.exit(f"Lỗi: Thư mục Run 4 không tồn tại: {run4_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    sha_sources: dict[str, str] = {}

    stats = {
        "run3_kept_raw_rows_per_fork": 0,
        "run4_raw_rows_per_fork": 0,
        "total_raw_rows_per_fork": 0,
        "sha256_sources": sha_sources,
    }

    # 1. counts.csv
    src_counts = run3_dir / "counts.csv"
    if src_counts.exists():
        sha_sources[f"run3/counts.csv"] = sha256_file(src_counts)
        dest_counts = out_dir / "counts.csv"
        dest_counts.write_bytes(src_counts.read_bytes())
    else:
        sys.exit(f"Lỗi: Không tìm thấy {src_counts}")

    # 2. Xử lý từng fork 1, 2, 3
    for f in (1, 2, 3):
        # raw_fork*.csv
        raw3_path = run3_dir / f"raw_fork{f}.csv"
        raw4_path = run4_dir / f"raw_fork{f}.csv"
        if not raw3_path.exists():
            sys.exit(f"Lỗi: Không tìm thấy {raw3_path}")
        if not raw4_path.exists():
            sys.exit(f"Lỗi: Không tìm thấy {raw4_path}")

        sha_sources[f"run3/raw_fork{f}.csv"] = sha256_file(raw3_path)
        sha_sources[f"run4/raw_fork{f}.csv"] = sha256_file(raw4_path)

        df3 = pd.read_csv(raw3_path)
        df4 = pd.read_csv(raw4_path)

        # Lọc bỏ 2^12 random khỏi run 3
        mask_drop3 = is_scale_4096_random(df3)
        df3_kept = df3[~mask_drop3]

        # Lấy các hàng 2^12 random từ run 4
        mask_take4 = is_scale_4096_random(df4)
        df4_taken = df4[mask_take4] if mask_take4.any() else df4

        stats["run3_kept_raw_rows_per_fork"] = len(df3_kept)
        stats["run4_raw_rows_per_fork"] = len(df4_taken)

        # Ghép lại
        df_merged = pd.concat([df3_kept, df4_taken], ignore_index=True)
        stats["total_raw_rows_per_fork"] = len(df_merged)

        out_raw_path = out_dir / f"raw_fork{f}.csv"
        df_merged.to_csv(out_raw_path, index=False)

        # warmup_fork*.csv
        warm3_path = run3_dir / f"warmup_fork{f}.csv"
        warm4_path = run4_dir / f"warmup_fork{f}.csv"
        if warm3_path.exists():
            sha_sources[f"run3/warmup_fork{f}.csv"] = sha256_file(warm3_path)
            wdf3 = pd.read_csv(warm3_path)
            wmask_drop3 = is_scale_4096_random(wdf3)
            wdf3_kept = wdf3[~wmask_drop3]

            if warm4_path.exists():
                sha_sources[f"run4/warmup_fork{f}.csv"] = sha256_file(warm4_path)
                wdf4 = pd.read_csv(warm4_path)
                wmask_take4 = is_scale_4096_random(wdf4)
                wdf4_taken = wdf4[wmask_take4]
                wdf_merged = pd.concat([wdf3_kept, wdf4_taken], ignore_index=True)
            else:
                wdf_merged = wdf3_kept

            out_warm_path = out_dir / f"warmup_fork{f}.csv"
            wdf_merged.to_csv(out_warm_path, index=False)

        # env_fork*.txt
        env3_path = run3_dir / f"env_fork{f}.txt"
        if env3_path.exists():
            sha_sources[f"run3/env_fork{f}.txt"] = sha256_file(env3_path)
            out_env_path = out_dir / f"env_fork{f}.txt"
            out_env_path.write_bytes(env3_path.read_bytes())

        env4_path = run4_dir / f"env_fork{f}.txt"
        if env4_path.exists():
            sha_sources[f"run4/env_fork{f}.txt"] = sha256_file(env4_path)

    # 3. Tạo MERGE_README.txt
    readme_content = generate_readme(run3_dir, run4_dir, out_dir, stats)
    (out_dir / "MERGE_README.txt").write_text(readme_content, encoding="utf-8")

    return stats


def main():
    ap = argparse.ArgumentParser(description="Hợp nhất kết quả Run 3 và Run 4 tạo results_final/")
    ap.add_argument("--run3", type=Path, default=Path("results_run3"), help="Thư mục Run 3 (mặc định: results_run3)")
    ap.add_argument("--run4", type=Path, default=Path("results_run4"), help="Thư mục Run 4 (mặc định: results_run4)")
    ap.add_argument("--out", type=Path, default=Path("results_final"), help="Thư mục xuất (mặc định: results_final)")
    args = ap.parse_args()

    print(f"=== Bắt đầu hợp nhất dữ liệu ===")
    print(f"  Run 3: {args.run3}")
    print(f"  Run 4: {args.run4}")
    print(f"  Đầu ra: {args.out}")

    stats = merge(args.run3, args.run4, args.out)

    print(f"=== Hợp nhất hoàn tất ===")
    print(f"  Số hàng giữ từ Run 3 mỗi fork: {stats['run3_kept_raw_rows_per_fork']}")
    print(f"  Số hàng lấy từ Run 4 mỗi fork: {stats['run4_raw_rows_per_fork']}")
    print(f"  Tổng số hàng mỗi fork:         {stats['total_raw_rows_per_fork']}")
    print(f"  Đã ghi MERGE_README.txt vào {args.out / 'MERGE_README.txt'}")


if __name__ == "__main__":
    main()
