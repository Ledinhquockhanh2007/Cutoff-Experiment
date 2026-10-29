# Tóm tắt kết quả thí nghiệm CUTOFF

- Kết quả: `results` — chế độ **full**, 3 fork, 81720 lần đo, 504 cặp (fork, bộ dữ liệu).
- Môi trường: Windows 11 amd64, Microsoft JDK 25.0.4.1, 16 luồng; cờ JVM: `[-Xms2g, -Xmx2g, -XX:+UseSerialGC, -XX:+AlwaysPreTouch]`.
- counts.csv: `results\counts.csv`; bootstrap B = 10000, seed = 20261027.

## 1. Độ đầy đủ và GC

- Bộ dữ liệu theo kế hoạch: 504; đủ ô (trial × CUTOFF): 504; thiếu/thừa: 0.
- Lần đo có gc_during_run = true: **0** / 81720 (loại khỏi phân tích chính). Trial mất baseline c = 1 do loại GC: 0.
- Phụ lục (giữ cả lần đo có GC): r lệch tối đa 0.00% so với bản chính (`tables/r_by_cutoff_with_gc.csv`).
- Lô K theo bộ dữ liệu: 1, 2, 3, 4, 5.

## 2. RQ1 — CUTOFF tốt nhất (r = T(c)/T(1), TB nhân trên các N, CI 95% bootstrap theo cụm N)

| phân bố | thang | số N | c tốt nhất | c tốt nhất (median) | r [CI 95%] | thời gian giảm | gần tối ưu (≤ 2%) | argmin bootstrap (top 3) |
|---|---|---|---|---|---|---|---|---|
| ngẫu nhiên | 2^12 | 24 | 32 | 30 | 0.818 [0.810, 0.826] | 18.2% | 21 22 23 24 25 26 27 28 29 30 31 32 40 48 | 32: 47%; 30: 20%; 40: 13% |
| ngẫu nhiên | 2^16 | 24 | 29 | 31 | 0.873 [0.867, 0.879] | 12.7% | 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 | 29: 39%; 40: 23%; 31: 17% |
| ngẫu nhiên | 2^19 | 24 | 24 | 48 | 0.912 [0.900, 0.924] | 8.8% | 11 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 64 | 24: 36%; 48: 20%; 22: 13% |
| đã sắp | 2^16 | 24 | 64 | 64 | 0.653 [0.647, 0.659] | 34.7% | 64 | 64: 100%; 48: 0%; 4: 0% |
| đảo ngược | 2^16 | 24 | 10 | 8 | 0.885 [0.875, 0.897] | 11.5% | 6 8 10 12 | 10: 55%; 8: 40%; 6: 5% |
| gần sắp (~1%) | 2^16 | 24 | 64 | 64 | 0.703 [0.693, 0.713] | 29.7% | 48 64 | 64: 98%; 48: 2%; 4: 0% |
| ít giá trị (10) | 2^16 | 24 | 32 | 32 | 0.813 [0.805, 0.821] | 18.7% | 24 32 48 | 32: 92%; 24: 7%; 48: 0% |

- Gộp 3 thang random (trọng số bằng nhau): c tốt nhất = **40**, r = 0.869 [0.865, 0.873], gần tối ưu: 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 64; tần suất bootstrap là tốt nhất: 40: 51%; 30: 17%; 32: 16%; 48: 4%.

## 3. RQ3 — CUTOFF 7, 10 và tốt nhất so với baseline (random)

| thang |  | c | r [CI] | thời gian giảm [CI] | tăng tốc | r = 0.80 trong CI? | r = 0.833 trong CI? |
|---|---|---|---|---|---|---|---|
| 2^12 | c = 7 | 7 | 0.887 [0.879, 0.895] | 11.3% [10.5%, 12.1%] | 1.127× | không | không |
| 2^12 | c = 10 | 10 | 0.875 [0.863, 0.886] | 12.5% [11.4%, 13.7%] | 1.143× | không | không |
| 2^12 | tốt nhất | 32 | 0.818 [0.810, 0.826] | 18.2% [17.4%, 19.0%] | 1.223× | không | không |
| 2^16 | c = 7 | 7 | 0.916 [0.911, 0.922] | 8.4% [7.8%, 8.9%] | 1.091× | không | không |
| 2^16 | c = 10 | 10 | 0.906 [0.901, 0.911] | 9.4% [8.9%, 9.9%] | 1.104× | không | không |
| 2^16 | tốt nhất | 29 | 0.873 [0.867, 0.879] | 12.7% [12.1%, 13.3%] | 1.145× | không | không |
| 2^19 | c = 7 | 7 | 0.954 [0.940, 0.967] | 4.6% [3.3%, 6.0%] | 1.049× | không | không |
| 2^19 | c = 10 | 10 | 0.935 [0.925, 0.945] | 6.5% [5.5%, 7.5%] | 1.070× | không | không |
| 2^19 | tốt nhất | 24 | 0.912 [0.900, 0.924] | 8.8% [7.6%, 10.0%] | 1.097× | không | không |

Bài giảng (Phần 1, mục cải tiến Mergesort): thêm cutoff "có thể nhanh hơn khoảng 20%". Hai cách đọc: thời gian giảm 20% (r = 0.80) hoặc nhanh hơn 1.2 lần (r ≈ 0.833).

So sánh ghép cặp: log(T_a/T_b) trung bình trong từng N trước (tránh giả lặp), Wilcoxon signed-rank trên các N, Holm cho cả họ kiểm định. *holdout* = c tốt nhất chọn trên trial lẻ, đánh giá trên trial chẵn (tránh lời nguyền người thắng).

| thang | loại | a | b | T_a/T_b [CI] | a nhanh hơn ở | p (Wilcoxon) | p (Holm) |
|---|---|---|---|---|---|---|---|
| 2^12 | in-sample | 7 | 10 | 1.0145 [1.0025, 1.0262] | 9/24 N | 0.0315 | 0.0583 |
| 2^12 | in-sample | 32 | 7 | 0.9215 [0.9119, 0.9304] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | in-sample | 32 | 10 | 0.9349 [0.9263, 0.9440] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 30 | 7 | 0.9253 [0.9185, 0.9316] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 30 | 10 | 0.9360 [0.9262, 0.9461] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 30 | 1 | 0.8251 [0.8137, 0.8355] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | in-sample | 7 | 10 | 1.0115 [1.0051, 1.0184] | 6/24 N | 0.00434 | 0.0173 |
| 2^16 | in-sample | 29 | 7 | 0.9529 [0.9476, 0.9582] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | in-sample | 29 | 10 | 0.9639 [0.9577, 0.9698] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 40 | 7 | 0.9584 [0.9479, 0.9686] | 23/24 N | 2.38e-07 | 2.38e-06 |
| 2^16 | holdout | 40 | 10 | 0.9655 [0.9562, 0.9748] | 21/24 N | 3.93e-06 | 3.15e-05 |
| 2^16 | holdout | 40 | 1 | 0.8738 [0.8646, 0.8828] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | in-sample | 7 | 10 | 1.0202 [1.0080, 1.0342] | 5/24 N | 0.00434 | 0.0173 |
| 2^19 | in-sample | 24 | 7 | 0.9558 [0.9424, 0.9702] | 22/24 N | 2.47e-05 | 0.000173 |
| 2^19 | in-sample | 24 | 10 | 0.9751 [0.9620, 0.9890] | 20/24 N | 0.00225 | 0.0112 |
| 2^19 | holdout | 24 | 7 | 0.9496 [0.9233, 0.9744] | 19/24 N | 0.000846 | 0.00508 |
| 2^19 | holdout | 24 | 10 | 0.9727 [0.9477, 0.9970] | 17/24 N | 0.0291 | 0.0583 |
| 2^19 | holdout | 24 | 1 | 0.9216 [0.9039, 0.9418] | 22/24 N | 2.98e-06 | 2.68e-05 |

## 4. Lớp tương đương và độ dài lá

- N = 2^12: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 9.3%; SD gộp của log r = 0.020 (≈ ±2.1% cho r của một CUTOFF ở một N).
- N = 2^16: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 3.9%; SD gộp của log r = 0.011 (≈ ±1.1% cho r của một CUTOFF ở một N).
- N = 2^19: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 11.8%; SD gộp của log r = 0.024 (≈ ±2.4% cho r của một CUTOFF ở một N).
- Số cây khác nhau trên lưới 35 CUTOFF (random, từ S trong counts.csv): N = 2^k: 7, 7, 7; các N khác: trung vị 10 (min 7, max 11).
- Theo độ dài lá trung bình (gộp mọi N random): r nhỏ nhất ≈ 0.865 ở độ dài lá ≈ 17.5 (khoảng (16.0, 19.027]).

## 5. RQ2 — Ảnh hưởng của N và phân bố

- ngẫu nhiên (thang 2^16): c tốt nhất = 29, thời gian giảm 12.7%, gần tối ưu: 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48.
- đã sắp (thang 2^16): c tốt nhất = 64, thời gian giảm 34.7%, gần tối ưu: 64.
- đảo ngược (thang 2^16): c tốt nhất = 10, thời gian giảm 11.5%, gần tối ưu: 6 8 10 12.
- gần sắp (~1%) (thang 2^16): c tốt nhất = 64, thời gian giảm 29.7%, gần tối ưu: 48 64.
- ít giá trị (10) (thang 2^16): c tốt nhất = 32, thời gian giảm 18.7%, gần tối ưu: 24 32 48.
- Random theo thang: c tốt nhất 2^12 → 32, 2^16 → 29, 2^19 → 24.

## 6. Số đếm (MergeCutoffCounted, random)

- Thang 2^12, c = 32: C ×1.274, A ×1.141, S ×0.635, E/(N lgN) = 0.449, trong khi T ×0.818 so với c = 1.
- Thang 2^16, c = 29: C ×1.174, A ×1.081, S ×0.732, E/(N lgN) = 0.307, trong khi T ×0.873 so với c = 1.
- Thang 2^19, c = 24: C ×1.110, A ×1.035, S ×0.786, E/(N lgN) = 0.215, trong khi T ×0.912 so với c = 1.
- c = 1: C/(N lgN) = 0.900–0.936, A/(N lgN) = 5.818–5.884 (cận bài giảng: C ≤ N lgN, A ≤ 6 N lgN).

## 7. Mô hình thời gian chạy T = a·N^b (random)

- c = 1 (72 N): b = 1.1357 ± 0.0025, a = 63.88 ns, R² = 0.99966; T/(N lgN) ≈ 18.366 ns.
- c = 40 (72 N): b = 1.1585 ± 0.0026, a = 43 ns, R² = 0.99966; T/(N lgN) ≈ 15.955 ns.
- Kiểm chứng c = 1: fit trên 2^12 + 2^16, dự đoán 2^19 → sai số tương đối (power law) TB -1.0%, |max| 12.2%; mô hình k·N lgN: TB -15.4%, |max| 25.8%. (Âm = dự đoán thấp hơn đo.)
- Kiểm chứng c = 40: fit trên 2^12 + 2^16, dự đoán 2^19 → sai số tương đối (power law) TB -0.8%, |max| 12.2%; mô hình k·N lgN: TB -21.7%, |max| 30.6%. (Âm = dự đoán thấp hơn đo.)
- T/(N lgN) theo thang (TB nhân trên các N; working set 24N B; L2 ứng với N ≈ 43691 (L2 1 MB/nhân), L3 ứng với N ≈ 699051 (L3 16 MB)): c = 1: 16.56 / 18.21 / 20.54 ns (2^12 / 2^16 / 2^19), tỉ số 2^16:2^12 = 1.099, 2^19:2^16 = 1.128; trong thang 2^19: N < 699051 → 20.29 ns, N ≥ 699051 → 20.73 ns; c = 40: 13.57 / 15.91 / 18.81 ns (2^12 / 2^16 / 2^19), tỉ số 2^16:2^12 = 1.172, 2^19:2^16 = 1.182; trong thang 2^19: N < 699051 → 18.61 ns, N ≥ 699051 → 18.94 ns. Mô hình k·N lgN thuần trên cùng tập N cho b = 1.0923; phần b vượt quá giá trị này tương ứng với việc T/(N lgN) tăng theo N (hình fig14); vị trí bước tăng so với ngưỡng L2/L3 là bằng chứng gián tiếp cho hiệu ứng cache, không phải phép đo trực tiếp.

## 8. Chẩn đoán

- Warm-up JVM fork 1, phiên 1: 12 vòng, vòng 1 = 392.9 ms, 3 vòng cuối = 524.2–589.1 ms.
- Warm-up JVM fork 2, phiên 1: 6 vòng, vòng 1 = 419.6 ms, 3 vòng cuối = 361.1–429.8 ms.
- Warm-up JVM fork 3, phiên 1: 10 vòng, vòng 1 = 441.5 ms, 3 vòng cuối = 534.8–580.4 ms.
- Warm-up từng bộ (trung vị T_warmup / T_đo): ít giá trị (10): vòng 1 = 0.999, vòng 2 = 0.998, vòng 3 = 1.006; gần sắp (~1%): vòng 1 = 1.001, vòng 2 = 1.003, vòng 3 = 1.002; ngẫu nhiên: vòng 1 = 1.004, vòng 2 = 1.003, vòng 3 = 1.003; đảo ngược: vòng 1 = 1.003, vòng 2 = 1.000, vòng 3 = 1.002; đã sắp: vòng 1 = 1.000, vòng 2 = 0.999, vòng 3 = 0.999.
- Trôi (fork 1, hồi quy fixed-effects theo (phân bố, N, c)): +0.12% mỗi 1000 lần đo (p = 1.56e-36), Spearman ρ = +0.116.
- Trôi (fork 2, hồi quy fixed-effects theo (phân bố, N, c)): -0.06% mỗi 1000 lần đo (p = 1.23e-08), Spearman ρ = -0.032.
- Trôi (fork 3, hồi quy fixed-effects theo (phân bố, N, c)): +0.06% mỗi 1000 lần đo (p = 7.55e-09), Spearman ρ = +0.042.
- Trôi (gộp các fork, hồi quy fixed-effects theo (phân bố, N, c)): +0.04% mỗi 1000 lần đo (p = 3.85e-09), Spearman ρ = +0.010.
- Chênh lệch r giữa các fork (max/min − 1): 2^12 c = 10: 0.87%; 2^12 c = 7: 1.38%; 2^12 tốt nhất: 3.30%; 2^16 c = 10: 1.54%; 2^16 c = 7: 1.03%; 2^16 tốt nhất: 1.76%; 2^19 c = 10: 0.43%; 2^19 c = 7: 2.81%; 2^19 tốt nhất: 0.83%.

## Tệp

- Bảng: cache_levels.csv, completeness.csv, counts_all_normalized.csv, counts_normalized.csv, distinct_trees_per_N.csv, drift.csv, env_summary.csv, equivalence_classes_2k.csv, forks_speedup.csv, gc_summary.csv, r_by_cutoff.csv, r_by_cutoff_with_gc.csv, r_by_leaf_length.csv, r_per_N.csv, rq1_argmin_bootstrap.csv, rq1_best_cutoff.csv, rq1_pooled_random.csv, rq3_paired_tests.csv, rq3_speedup.csv, runtime_model.csv, runtime_validation_2e19.csv, warmup_dataset_vs_measured.csv, warmup_jvm_rounds.csv
- Hình: fig01_r_vs_cutoff_random.png, fig02_argmin_bootstrap.png, fig03_speedup_7_10_best.png, fig04_paired_differences.png, fig05_equivalence_classes.png, fig06_r_vs_leaf_length.png, fig07_heatmap_random.png, fig08_distributions_2e16.png, fig09_counts_vs_time.png, fig10_runtime_model.png, fig14_cache_levels.png, fig11_jvm_warmup.png, fig12_drift.png, fig13_forks.png
