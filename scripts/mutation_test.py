#!/usr/bin/env python3
"""scripts/mutation_test.py: Chạy kiểm thử đột biến (mutation testing) trên bản sao src/.

Thực hiện 5 trường hợp kiểm thử:
  0. baseline: Bản gốc không đột biến (phải PASS toàn bộ 970.425 phép kiểm tra)
  1. m1: merge lấy nửa phải khi hai khóa bằng nhau (!less(aux[i], aux[j]))
  2. m2: dòng cutoff lệch 1 (hi <= lo + cutoff thay vì hi <= lo + cutoff - 1)
  3. m3: insertion sort cận vòng lặp lệch 1 (j > lo + 1 thay vì j > lo)
  4. m4: tính mid lệch 1 (mid = lo + (hi - lo + 1) / 2)

Mỗi trường hợp được tạo trong build_mut/<tên>/, áp đúng một thay thế chuỗi trên bản sao,
kiểm tra tính duy nhất (count == 1), biên dịch và chạy java -ea CorrectnessTest.
Kết quả được xuất ra CSV và tệp văn bản thô.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MUTATIONS = [
    {
        "id": "baseline",
        "description": "Bản gốc không đột biến (đối chứng)",
        "file": None,
        "old": None,
        "new": None,
    },
    {
        "id": "m1",
        "description": "merge lấy nửa phải khi hai khóa bằng nhau",
        "file": "MergeCutoff.java",
        "old": "else if (less(aux[j], aux[i])) a[k] = aux[j++];",
        "new": "else if (!less(aux[i], aux[j])) a[k] = aux[j++];",
    },
    {
        "id": "m2",
        "description": "dòng cutoff lệch 1: hi <= lo + cutoff",
        "file": "MergeCutoff.java",
        "old": "if (hi <= lo + cutoff - 1)",
        "new": "if (hi <= lo + cutoff)",
    },
    {
        "id": "m3",
        "description": "insertion sort: j > lo + 1",
        "file": "MergeCutoff.java",
        "old": "for (int j = i; j > lo; j--)",
        "new": "for (int j = i; j > lo + 1; j--)",
    },
    {
        "id": "m4",
        "description": "mid = lo + (hi - lo + 1)/2",
        "file": "MergeCutoff.java",
        "old": "int mid = lo + (hi - lo) / 2;",
        "new": "int mid = lo + (hi - lo + 1) / 2;",
    },
]


def run_mutation(m: dict, build_root: Path, src_dir: Path, lib_dir: Path) -> dict:
    mid = m["id"]
    m_dir = build_root / mid
    src_copy = m_dir / "src"
    bin_dir = m_dir / "bin"

    if m_dir.exists():
        shutil.rmtree(m_dir)
    src_copy.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    # Sao chép các tệp .java từ src/ sang build_mut/<id>/src/
    for java_file in src_dir.glob("*.java"):
        shutil.copy2(java_file, src_copy / java_file.name)

    # Áp dụng đột biến nếu có
    if m["file"] is not None:
        target_path = src_copy / m["file"]
        if not target_path.exists():
            raise FileNotFoundError(f"Target file {target_path} not found")
        content = target_path.read_text(encoding="utf-8")
        occurrences = content.count(m["old"])
        if occurrences != 1:
            raise ValueError(
                f"[{mid}] Thay thế chuỗi không duy nhất: tìm thấy {occurrences} lần chuỗi cần thay trong {m['file']}!"
            )
        content = content.replace(m["old"], m["new"], 1)
        target_path.write_text(content, encoding="utf-8")

    # Biên dịch
    sep = os.pathsep
    cp_lib = f"{lib_dir.resolve()}/*{sep}."
    java_files = [str(f.resolve()) for f in src_copy.glob("*.java")]
    compile_cmd = ["javac", "-cp", cp_lib, "-d", str(bin_dir.resolve())] + java_files

    c_res = subprocess.run(compile_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if c_res.returncode != 0:
        raise RuntimeError(f"[{mid}] Lỗi biên dịch javac:\n{c_res.stderr}\n{c_res.stdout}")

    # Chạy CorrectnessTest với -ea
    run_cp = f"{lib_dir.resolve()}/*{sep}{bin_dir.resolve()}"
    run_cmd = ["java", "-ea", "-cp", run_cp, "CorrectnessTest"]
    r_res = subprocess.run(run_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    output = r_res.stdout
    if r_res.stderr:
        output += "\nSTDERR:\n" + r_res.stderr

    # Phân tích các nhóm FAIL
    failed_groups = []
    has_so = "StackOverflowError" in output
    for line in output.splitlines():
        match = re.match(r"^(\d\d)\. (.+?)\s+(\d+)\s+(\d+)\s+(PASS|FAIL)", line.strip())
        if match:
            grp = match.group(1)
            status = match.group(5)
            if status == "FAIL":
                if grp == "13" and has_so:
                    failed_groups.append("13 (StackOverflow)")
                else:
                    failed_groups.append(grp)

    # Đọc tổng số checks và fails
    tot_match = re.search(r"TOTAL:\s*(\d+)\s*checks,\s*(\d+)\s*failed\s*->\s*(PASS|FAIL)", output)
    total_checks = int(tot_match.group(1)) if tot_match else 0
    total_fails = int(tot_match.group(2)) if tot_match else 0
    test_status = tot_match.group(3) if tot_match else "UNKNOWN"

    failed_str = ", ".join(failed_groups) if failed_groups else "—"

    return {
        "id": mid,
        "description": m["description"],
        "target_file": m["file"] or "—",
        "failed_groups": failed_str,
        "total_checks": total_checks,
        "total_failed": total_fails,
        "test_status": test_status,
        "raw_output": output,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Chạy kiểm thử đột biến (mutation testing) trên bản sao mã nguồn src/."
    )
    parser.add_argument("--src_dir", type=Path, default=Path("src"), help="Thư mục mã nguồn gốc (mặc định: src)")
    parser.add_argument("--lib_dir", type=Path, default=Path("lib"), help="Thư mục thư viện JAR (mặc định: lib)")
    parser.add_argument(
        "--build_dir", type=Path, default=Path("build_mut"), help="Thư mục làm việc cho đột biến (mặc định: build_mut)"
    )
    parser.add_argument(
        "--out_csv",
        type=Path,
        default=Path("results_final/mutation_test.csv"),
        help="Đường dẫn tệp CSV đầu ra (mặc định: results_final/mutation_test.csv)",
    )
    parser.add_argument(
        "--out_txt",
        type=Path,
        default=Path("results_final/mutation_test_output.txt"),
        help="Đường dẫn tệp văn bản thô đầu ra (mặc định: results_final/mutation_test_output.txt)",
    )
    args = parser.parse_args()

    args.build_dir.mkdir(parents=True, exist_ok=True)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.out_txt.parent.mkdir(parents=True, exist_ok=True)

    results = []
    raw_texts = []

    print("=== BẮT ĐẦU KIỂM THỬ ĐỘT BIẾN ===")
    for m in MUTATIONS:
        print(f"-> Đang chạy: {m['id']} ({m['description']})...", end=" ", flush=True)
        res = run_mutation(m, args.build_dir, args.src_dir, args.lib_dir)
        results.append(res)
        print(f"XONG. Nhóm FAIL: [{res['failed_groups']}], Tổng lỗi: {res['total_failed']}/{res['total_checks']}")

        raw_texts.append(
            f"================================================================================\n"
            f"MUTATION: {m['id']} - {m['description']}\n"
            f"Target: {m['file']}\n"
            f"Failed groups: {res['failed_groups']}\n"
            f"Status: {res['test_status']} ({res['total_failed']} failed / {res['total_checks']} checks)\n"
            f"--------------------------------------------------------------------------------\n"
            f"{res['raw_output'].strip()}\n\n"
        )

    # Ghi tệp CSV
    csv_lines = ["mutation_id,description,target_file,failed_groups,total_checks,total_failed,status"]
    for r in results:
        desc_escaped = f'"{r["description"]}"' if "," in r["description"] else r["description"]
        fg_escaped = f'"{r["failed_groups"]}"' if "," in r["failed_groups"] else r["failed_groups"]
        csv_lines.append(
            f"{r['id']},{desc_escaped},{r['target_file']},{fg_escaped},{r['total_checks']},{r['total_failed']},{r['test_status']}"
        )
    args.out_csv.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    print(f"Đã ghi CSV: {args.out_csv}")

    # Ghi tệp RAW
    args.out_txt.write_text("".join(raw_texts), encoding="utf-8")
    print(f"Đã ghi log thô: {args.out_txt}")

    # Kiểm tra tính toàn vẹn: baseline phải PASS toàn bộ 970425 phép kiểm tra
    baseline = results[0]
    if baseline["total_failed"] != 0 or baseline["test_status"] != "PASS" or baseline["total_checks"] != 970425:
        sys.exit(f"LỖI: Bản baseline không PASS toàn bộ 970.425 kiểm tra! ({baseline['total_failed']} lỗi)")

    # Kiểm tra cả 4 đột biến đều bị phát hiện (status FAIL)
    for r in results[1:]:
        if r["test_status"] != "FAIL" or r["total_failed"] == 0:
            sys.exit(f"LỖI: Đột biến {r['id']} không bị phát hiện!")

    print("=== HOÀN TẤT KIỂM THỬ ĐỘT BIẾN: TẤT CẢ ĐỘT BIẾN ĐÃ BỊ TIÊU DIỆT (KILLED) ===")


if __name__ == "__main__":
    main()
