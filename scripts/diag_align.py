#!/usr/bin/env python3
"""
diag_align.py — ghép kết quả WarmupProbe (từng vòng) với log typeperf (mỗi giây) để chẩn đoán bước nhảy.

    python scripts/diag_align.py --probe diag/E0_1/probe.csv --typeperf diag/E0_1/typeperf.csv [--out diag/E0_1]

typeperf phải ghi hai bộ đếm cho mọi bộ xử lý logic:
    "\\Processor Information(*)\\% Processor Performance"   (xung thực / xung cơ bản × 100)
    "\\Processor Information(*)\\% Processor Utility"

Với mỗi vòng: bộ xử lý logic bận nhất (LP chạy luồng main), % Processor Performance của nó, độ bận của LP
"anh em" SMT (giả định LP 2k và 2k+1 cùng một nhân — xác nhận bằng Sysinternals Coreinfo -c), và cpu_per_sort.
Vòng "chậm" = ns_per_NlgN > 1.25 × phân vị 10% của cùng N.
In bảng so sánh vòng nhanh / chậm và ghi <out>/aligned.csv.
"""
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd


def read_typeperf(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    head = df.columns[0]
    m = re.search(r"\((-?\d+)\)\s*$", head)            # bias phút: UTC = giờ địa phương + bias
    bias_min = int(m[1]) if m else 0
    ts = None
    for fmt in ("%m/%d/%Y %H:%M:%S.%f", "%d/%m/%Y %H:%M:%S.%f"):
        try:
            ts = pd.to_datetime(df[head].str.strip(), format=fmt)
            break
        except (ValueError, TypeError):
            continue
    if ts is None:
        raise SystemExit("không đọc được cột thời gian của typeperf")
    epoch_ms = (ts - pd.Timestamp("1970-01-01")) // pd.Timedelta(milliseconds=1) + bias_min * 60_000
    rows = {"epoch_ms": epoch_ms.astype("int64")}
    for col in df.columns[1:]:
        mm = re.search(r"Processor Information\((\d+),(\d+)\)\\% Processor (Performance|Utility)", col)
        if not mm:
            continue                                       # bỏ _Total
        lp = int(mm[1]) * 64 + int(mm[2])
        rows[f"{'perf' if mm[3] == 'Performance' else 'util'}_{lp}"] = pd.to_numeric(df[col], errors="coerce")
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True)
    ap.add_argument("--typeperf", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    pr = pd.read_csv(a.probe)
    tp = read_typeperf(Path(a.typeperf))
    lps = sorted(int(c.split("_")[1]) for c in tp.columns if c.startswith("util_"))
    out_rows = []
    for _, r in pr.iterrows():
        w = tp[(tp.epoch_ms >= r.epoch_ms_start) & (tp.epoch_ms <= r.epoch_ms_end + 1000)]
        if w.empty:                                        # vòng ngắn hơn 1 s: lấy mẫu gần nhất sau đó
            w = tp[tp.epoch_ms >= r.epoch_ms_start].head(1)
        if w.empty:
            continue
        util = {lp: w[f"util_{lp}"].mean() for lp in lps}
        busy = max(util, key=util.get)
        sib = busy ^ 1
        out_rows.append({**r.to_dict(), "busy_lp": busy, "busy_util": util[busy],
                         "busy_perf": w[f"perf_{busy}"].mean(),
                         "sibling_lp": sib, "sibling_util": util.get(sib, np.nan),
                         "others_util_mean": np.mean([v for k, v in util.items() if k not in (busy, sib)])})
    al = pd.DataFrame(out_rows)
    base = al.groupby("N").ns_per_NlgN.transform(lambda s: s.quantile(0.10))
    al["slow"] = al.ns_per_NlgN > 1.25 * base
    al["lp_changed"] = al.busy_lp != al.busy_lp.shift()
    out = Path(a.out) if a.out else Path(a.probe).parent
    al.to_csv(out / "aligned.csv", index=False)

    print(f"{len(al)} vòng; chậm: {int(al.slow.sum())}; số lần đổi LP bận nhất: {int(al.lp_changed.sum()) - 1}")
    cols = ["ns_per_NlgN", "cpu_per_sort", "busy_perf", "busy_util", "sibling_util", "others_util_mean"]
    print(al.groupby(["N", "slow"])[cols].median().round(3).to_string())
    tr = al.index[al.slow != al.slow.shift()][1:]
    for i in tr:
        prev, cur = al.loc[i - 1], al.loc[i]
        print(f"chuyển {'nhanh→chậm' if cur.slow else 'chậm→nhanh'} ở vòng {int(cur['round'])} "
              f"(uptime {int(cur.uptime_ms_start)} ms): LP {int(prev.busy_lp)}→{int(cur.busy_lp)}, "
              f"perf {prev.busy_perf:.0f}→{cur.busy_perf:.0f}%, SMT anh em {prev.sibling_util:.0f}→{cur.sibling_util:.0f}%, "
              f"cpu/sort {prev.cpu_per_sort:.2f}→{cur.cpu_per_sort:.2f}")
    print("Đọc kết quả: busy_perf giảm ~1/1.6 ở vòng chậm → xung CPU (H1/H4); sibling_util tăng → SMT dùng chung (H2);")
    print("cpu_per_sort giảm hoặc LP đổi đúng lúc chuyển → luồng bị lập lịch lại/tạm dừng (H3); không đổi gì → xem log JIT (H5).")


if __name__ == "__main__":
    main()
