#!/usr/bin/env python3
"""Run memory probes and generate memory analysis tables for T05 / T05b.

Obey guidelines:
- Fixed seed (42)
- Has --help via argparse
- Outputs clean CSV tables to results_final/analysis_v2/tables/
- Purely measures memory (no timing benchmarks, no affinity C00)
- Parses raw layout text verbatim into memory_class_layouts.csv (no hardcoded table constants)
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 42
np.random.seed(SEED)

CONFIGS = [
    {
        "id": "default",
        "name": "Mặc định (CompressedOops + CompressedClassPointers)",
        "flags": ["-Xms2g", "-Xmx2g", "-XX:+UseSerialGC"],
        "slope": 24,
        "intercept": 32,
        "formula_note": "24N + 32 (mo hinh ly thuyet JVM mac dinh, khong phai so do)",
    },
    {
        "id": "no_coops",
        "name": "Không nén con trỏ đối tượng (-XX:-UseCompressedOops)",
        "flags": ["-Xms2g", "-Xmx2g", "-XX:+UseSerialGC", "-XX:-UseCompressedOops"],
        "slope": 32,
        "intercept": 32,
        "formula_note": "32N + 32 (mo hinh ly thuyet JVM khong nen oops, khong phai so do)",
    },
    {
        "id": "lecture",
        "name": "Giống bài giảng (-XX:-UseCompressedOops -XX:-UseCompressedClassPointers)",
        "flags": ["-Xms2g", "-Xmx2g", "-XX:+UseSerialGC", "-XX:-UseCompressedOops", "-XX:-UseCompressedClassPointers"],
        "slope": 40,
        "intercept": 48,
        "formula_note": "40N + 48 (mo hinh ly thuyet bai giang Sedgewick, khong phai so do)",
    },
    {
        "id": "compact_headers",
        "name": "Compact Headers (-XX:+UseCompactObjectHeaders)",
        "flags": ["-Xms2g", "-Xmx2g", "-XX:+UseSerialGC", "-XX:+UseCompactObjectHeaders"],
        "slope": 24,
        "intercept": 32,
        "formula_note": "24N + 32 (mo hinh mo ta cho N chan, khong phai so do)",
    },
]

SIZES = [1024, 16384, 65536, 524288, 1048576, 4194304]

L2_CACHE_BYTES = 1024 * 1024       # 1 MiB per core
L3_CACHE_BYTES = 16 * 1024 * 1024  # 16 MiB total


def parse_args():
    parser = argparse.ArgumentParser(description="Run memory probes across JVM configs and sizes for T05 / T05b.")
    parser.add_argument("--tables-dir", type=str, default="results_final/analysis_v2/tables",
                        help="Directory to save CSV tables")
    parser.add_argument("--analysis-dir", type=str, default="results_final/analysis_v2",
                        help="Directory to save raw layout text files")
    parser.add_argument("--reps", type=int, default=3, help="Repetitions for probe")
    parser.add_argument("--skip-probe", action="store_true",
                        help="Skip probe measurements if measurements CSV already exists")
    return parser.parse_args()


def run_probe_for_config_and_size(config, n, reps):
    file_path = f"data_doubling/random/N{n:07d}.bin"
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Missing data file: {file_path}")

    cmd = [
        "java",
        *config["flags"],
        "-cp", "lib/jol-core-0.17.jar;build",
        "MemoryProbe", "probe", str(n), file_path, str(reps)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # Parse line starting with RESULT:
    # RESULT:n,jolA,jolAux,jolInts,jolAAndInts,jolTotal,allocA,allocInts,allocAux,allocTotal
    result_line = None
    for line in res.stdout.splitlines():
        if line.startswith("RESULT:"):
            result_line = line.strip()
            break
    if not result_line:
        raise RuntimeError(f"No RESULT line found in output for {config['id']} N={n}:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")

    parts = [int(p) for p in result_line.split(":")[1].split(",")]
    return {
        "n": parts[0],
        "jol_a": parts[1],
        "jol_aux": parts[2],
        "jol_ints": parts[3],
        "jol_a_and_ints": parts[4],
        "jol_total": parts[5],
        "alloc_a": parts[6],
        "alloc_ints": parts[7],
        "alloc_aux": parts[8],
        "alloc_total": parts[9],
    }


def run_identity_check(data_dir="data"):
    cmd = [
        "java",
        "-Xms2g", "-Xmx2g", "-XX:+UseSerialGC",
        "-cp", "lib/jol-core-0.17.jar;build",
        "MemoryProbe", "identity", data_dir
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    lines = [line.strip() for line in res.stdout.splitlines() if line.strip() and not line.startswith("#") and not line.startswith("WARNING") and not line.startswith("[")]
    # Header: distribution,N,total_elements,distinct_identities,all_distinct
    rows = []
    header = lines[0].split(",")
    for line in lines[1:]:
        if "," in line:
            parts = line.split(",")
            rows.append({
                "distribution": parts[0],
                "N": int(parts[1]),
                "total_elements": int(parts[2]),
                "distinct_identities": int(parts[3]),
                "all_distinct": parts[4].lower() == "true",
            })
    return pd.DataFrame(rows)


def run_and_save_raw_layouts(analysis_dir):
    """Run MemoryProbe layouts for all 4 configs and save verbatim output."""
    analysis_path = Path(analysis_dir)
    analysis_path.mkdir(parents=True, exist_ok=True)
    
    saved_files = {}
    for cfg in CONFIGS:
        cfg_id = cfg["id"]
        out_file = analysis_path / f"memory_layouts_{cfg_id}.txt"
        cmd = [
            "java",
            *cfg["flags"],
            "-cp", "lib/jol-core-0.17.jar;build",
            "MemoryProbe", "layouts"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Save verbatim stdout (and stderr if any notes)
        content = res.stdout
        if res.stderr.strip():
            content = f"--- STDERR ---\n{res.stderr}\n--- STDOUT ---\n{content}"
        out_file.write_text(content, encoding="utf-8")
        saved_files[cfg_id] = out_file
        print(f"Saved verbatim layout to: {out_file}")
    return saved_files


def parse_layout_file(file_path, cfg):
    """Parse layout file strictly without hardcoded numbers."""
    text = file_path.read_text(encoding="utf-8")

    # 1. Parse ref field size & array elem size
    # Look for: "# Field sizes:            4,    1,    1,    2,    2,    4,    4,    8,    8"
    m_field = re.search(r"#\s*Field sizes:\s*(\d+)", text)
    ref_size = int(m_field.group(1)) if m_field else "n/a (không parse được)"

    m_elem = re.search(r"#\s*Array element sizes:\s*(\d+)", text)
    array_elem_size = int(m_elem.group(1)) if m_elem else "n/a (không parse được)"

    # 2. Parse ClassLayout: Integer
    # Find block between "=== ClassLayout: Integer ===" and "=== ClassLayout: Integer[] ==="
    int_block_m = re.search(r"=== ClassLayout: Integer ===(.*?)(=== ClassLayout: Integer\[\] ===|$)", text, re.DOTALL)
    if int_block_m:
        int_text = int_block_m.group(1)
        # Find offset of int Integer.value: e.g. " 12   4    int Integer.value"
        m_val = re.search(r"^\s*(\d+)\s+(\d+)\s+int Integer\.value", int_text, re.MULTILINE)
        int_header = int(m_val.group(1)) if m_val else "n/a (không parse được)"
        int_val_size = int(m_val.group(2)) if m_val else "n/a (không parse được)"

        # Padding / alignment gap: e.g. " 20   4        (object alignment gap)"
        m_pad = re.search(r"^\s*(\d+)\s+(\d+)\s+\(object alignment gap\)", int_text, re.MULTILINE)
        int_padding = int(m_pad.group(2)) if m_pad else 0

        # Instance size: e.g. "Instance size: 16 bytes"
        m_sz = re.search(r"Instance size:\s*(\d+)\s*bytes", int_text)
        int_total = int(m_sz.group(1)) if m_sz else "n/a (không parse được)"
    else:
        int_header = int_val_size = int_padding = int_total = "n/a (không parse được)"

    # 3. Parse ClassLayout: Integer[]
    # Find block between "=== ClassLayout: Integer[] ===" and "=== ClassLayout: Comparable[] ==="
    arr_block_m = re.search(r"=== ClassLayout: Integer\[\] ===(.*?)(=== ClassLayout: Comparable\[\] ===|$)", text, re.DOTALL)
    if arr_block_m:
        arr_text = arr_block_m.group(1)
        # Base offset of elements: line with "<elements>"
        # e.g. " 16   0   java.lang.Integer Integer;.<elements>"
        # or in compact: " 12   0   java.lang.Integer Integer;.<elements>"
        m_elem_off = re.search(r"^\s*(\d+)\s+\d+\s+.*<elements>", arr_text, re.MULTILINE)
        array_header_offset = int(m_elem_off.group(1)) if m_elem_off else "n/a (không parse được)"

        # Array empty instance size
        m_arr_sz = re.search(r"Instance size:\s*(\d+)\s*bytes", arr_text)
        array_empty_instance = int(m_arr_sz.group(1)) if m_arr_sz else "n/a (không parse được)"
    else:
        array_header_offset = array_empty_instance = "n/a (không parse được)"

    return {
        "config": cfg["id"],
        "jvm_flags": " ".join(cfg["flags"]),
        "ref_size_bytes": ref_size,
        "integer_header_bytes": int_header,
        "integer_value_bytes": int_val_size,
        "integer_padding_bytes": int_padding,
        "integer_total_bytes": int_total,
        "array_header_offset_bytes": array_header_offset,
        "array_elem_size_bytes": array_elem_size,
        "array_empty_instance_bytes": array_empty_instance,
        "formula_model_note": cfg["formula_note"],
    }


def generate_class_layouts_table(analysis_dir, out_dir):
    """Run probe layouts, save raw text, parse into CSV table."""
    saved_files = run_and_save_raw_layouts(analysis_dir)
    rows = []
    for cfg in CONFIGS:
        cfg_id = cfg["id"]
        parsed = parse_layout_file(saved_files[cfg_id], cfg)
        rows.append(parsed)
    
    df = pd.DataFrame(rows)
    out_csv = Path(out_dir) / "memory_class_layouts.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved parsed layouts to: {out_csv}")
    print(df.to_string(index=False))

    # Verification of compact_headers array_header_offset_bytes
    compact_row = df[df["config"] == "compact_headers"].iloc[0]
    parsed_offset = compact_row["array_header_offset_bytes"]
    expected_offset = 12
    print(f"\n[Quy tắc A kiểm tra array_header của compact_headers]")
    print(f"  Số parse được từ file: {parsed_offset} B")
    print(f"  Số Claude kỳ vọng:     {expected_offset} B")
    print(f"  Chênh lệch:            {parsed_offset - expected_offset} B")
    return df


def main():
    args = parse_args()
    out_dir = Path(args.tables_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir = Path(args.analysis_dir)

    print("=== Step 1: Running Identity Check (N=65536 across 5 distributions) ===")
    df_identity = run_identity_check("data")
    identity_csv = out_dir / "memory_identity_check.csv"
    df_identity.to_csv(identity_csv, index=False)
    print(f"Saved: {identity_csv}")
    print(df_identity.to_string(index=False))

    print("\n=== Step 2: Running and Parsing Class Layouts (T05b requirement) ===")
    df_layouts = generate_class_layouts_table(analysis_dir, out_dir)

    print("\n=== Step 3: Measuring Memory across 4 JVM Configs and 6 Sizes ===")
    meas_csv = out_dir / "memory_measurements.csv"
    if args.skip_probe and meas_csv.exists():
        print(f"Skipping probe execution, reading existing {meas_csv}...")
        df_meas = pd.read_csv(meas_csv)
    else:
        all_measurements = []
        for cfg in CONFIGS:
            print(f"\n--- Config: {cfg['id']} ({cfg['name']}) ---")
            for n in SIZES:
                print(f"  Measuring N={n}...", end=" ", flush=True)
                res = run_probe_for_config_and_size(cfg, n, args.reps)
                
                # Theoretical numbers
                lecture_bytes = 40 * n + 48
                model_bytes = cfg["slope"] * n + cfg["intercept"]

                jol_bytes = res["jol_total"]
                alloc_bytes = res["alloc_total"]

                rel_err_jol = (jol_bytes - model_bytes) / model_bytes * 100.0
                rel_err_alloc = (alloc_bytes - model_bytes) / model_bytes * 100.0

                bytes_per_elem_jol = jol_bytes / n
                bytes_per_elem_alloc = alloc_bytes / n

                row = {
                    "config": cfg["id"],
                    "jvm_flags": " ".join(cfg["flags"]),
                    "N": n,
                    "bytes_jol": jol_bytes,
                    "bytes_alloc": alloc_bytes,
                    "bytes_lecture": lecture_bytes,
                    "bytes_model": model_bytes,
                    "rel_err_jol_pct": rel_err_jol,
                    "rel_err_alloc_pct": rel_err_alloc,
                    "bytes_per_elem_jol": bytes_per_elem_jol,
                    "bytes_per_elem_alloc": bytes_per_elem_alloc,
                    "jol_a": res["jol_a"],
                    "jol_aux": res["jol_aux"],
                    "jol_ints": res["jol_ints"],
                    "jol_a_and_ints": res["jol_a_and_ints"],
                    "alloc_a": res["alloc_a"],
                    "alloc_aux": res["alloc_aux"],
                    "alloc_ints": res["alloc_ints"],
                }
                all_measurements.append(row)
                print(f"JOL={jol_bytes:,} B, Alloc={alloc_bytes:,} B, Model={model_bytes:,} B (err={rel_err_jol:.3f}%)")

        df_meas = pd.DataFrame(all_measurements)
        df_meas.to_csv(meas_csv, index=False)
        print(f"\nSaved measurements to: {meas_csv}")

    print("\n=== Step 4: OLS Regression Analysis ===")
    reg_rows = []
    for cfg in CONFIGS:
        sub = df_meas[df_meas["config"] == cfg["id"]]
        x = sub["N"].values.astype(float)
        
        # JOL regression
        y_jol = sub["bytes_jol"].values.astype(float)
        slope_jol, intercept_jol = np.polyfit(x, y_jol, 1)
        r2_jol = 1.0 - np.sum((y_jol - (slope_jol * x + intercept_jol))**2) / np.sum((y_jol - np.mean(y_jol))**2)

        # Alloc regression
        y_alloc = sub["bytes_alloc"].values.astype(float)
        slope_alloc, intercept_alloc = np.polyfit(x, y_alloc, 1)
        r2_alloc = 1.0 - np.sum((y_alloc - (slope_alloc * x + intercept_alloc))**2) / np.sum((y_alloc - np.mean(y_alloc))**2)

        reg_rows.append({
            "config": cfg["id"],
            "model_formula": f"{cfg['slope']}N + {cfg['intercept']}",
            "theoretical_slope": cfg["slope"],
            "theoretical_intercept": cfg["intercept"],
            "jol_slope": slope_jol,
            "jol_intercept": intercept_jol,
            "jol_r2": r2_jol,
            "alloc_slope": slope_alloc,
            "alloc_intercept": intercept_alloc,
            "alloc_r2": r2_alloc,
        })

    df_reg = pd.DataFrame(reg_rows)
    reg_csv = out_dir / "memory_regression.csv"
    df_reg.to_csv(reg_csv, index=False)
    print(f"Saved regression to: {reg_csv}")
    print(df_reg.to_string(index=False))

    print("\n=== Step 5: Cache Discussion Table (k=10..22) ===")
    cache_rows = []
    for k in range(10, 23):
        n = 1 << k
        # In default JVM: 24N + 32 bytes (formula)
        footprint_bytes = 24 * n + 32
        footprint_mib = footprint_bytes / (1024 * 1024)
        pointer_arrays_bytes = 2 * (16 + 4 * n)
        pointer_arrays_mib = pointer_arrays_bytes / (1024 * 1024)
        integers_bytes = 16 * n
        integers_mib = integers_bytes / (1024 * 1024)

        ratio_l2 = footprint_bytes / L2_CACHE_BYTES
        ratio_l3 = footprint_bytes / L3_CACHE_BYTES

        if footprint_bytes < L2_CACHE_BYTES:
            status = "Within L2"
        elif footprint_bytes < L3_CACHE_BYTES:
            status = "Exceeds L2, within L3"
        elif pointer_arrays_bytes < L3_CACHE_BYTES:
            status = "Total exceeds L3; pointers within L3"
        else:
            status = "Both pointers and total exceed L3"

        cache_rows.append({
            "k": k,
            "N": n,
            "footprint_bytes": footprint_bytes,
            "footprint_mib": footprint_mib,
            "pointer_arrays_mib": pointer_arrays_mib,
            "integers_mib": integers_mib,
            "ratio_l2": ratio_l2,
            "ratio_l3": ratio_l3,
            "status_vs_l3": status,
        })

    df_cache = pd.DataFrame(cache_rows)
    cache_csv = out_dir / "memory_cache_discussion.csv"
    df_cache.to_csv(cache_csv, index=False)
    print(f"Saved cache discussion to: {cache_csv}")
    print(df_cache.to_string(index=False))


if __name__ == "__main__":
    main()
