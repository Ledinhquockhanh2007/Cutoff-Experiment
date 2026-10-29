# Tóm tắt kết quả thí nghiệm CUTOFF

- Kết quả: `results` — chế độ **full**, 3 fork, 81720 lần đo, 504 cặp (fork, bộ dữ liệu).
- Môi trường: Windows 11 amd64, Microsoft JDK 25.0.4.1, 16 luồng; cờ JVM: `[-Xms2g, -Xmx2g, -XX:+UseSerialGC, -XX:+AlwaysPreTouch]`.
- counts.csv: `results\counts.csv`; bootstrap B = 10000, seed = 20261027.

## 1. Độ đầy đủ và GC

- Bộ dữ liệu theo kế hoạch: 504; đủ ô (trial × CUTOFF): 504; thiếu/thừa: 0.
- Lần đo có gc_during_run = true: **0** / 81720 (loại khỏi phân tích chính). Trial mất baseline c = 1 do loại GC: 0.
- Phụ lục (giữ cả lần đo có GC): r lệch tối đa 0.00% so với bản chính (`tables/r_by_cutoff_with_gc.csv`).
- Lô K theo bộ dữ liệu: 1, 2, 3, 4.

## 2. RQ1 — CUTOFF tốt nhất (r = T(c)/T(1), TB nhân trên các N, CI 95% bootstrap theo cụm N)

| phân bố | thang | số N | c tốt nhất | c tốt nhất (median) | r [CI 95%] | thời gian giảm | gần tối ưu (≤ 2%) | argmin bootstrap (top 3) |
|---|---|---|---|---|---|---|---|---|
| ngẫu nhiên | 2^12 | 24 | 31 | 31 | 0.821 [0.815, 0.826] | 17.9% | 22 23 24 25 26 27 28 29 30 31 32 40 48 | 31: 48%; 32: 39%; 29: 9% |
| ngẫu nhiên | 2^16 | 24 | 32 | 32 | 0.880 [0.878, 0.882] | 12.0% | 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 | 32: 74%; 30: 26%; 31: 0% |
| ngẫu nhiên | 2^19 | 24 | 48 | 40 | 0.921 [0.916, 0.925] | 7.9% | 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 64 | 48: 53%; 40: 21%; 24: 9% |
| đã sắp | 2^16 | 24 | 64 | 64 | 0.664 [0.656, 0.672] | 33.6% | 64 | 64: 100%; 48: 0%; 4: 0% |
| đảo ngược | 2^16 | 24 | 10 | 10 | 0.890 [0.884, 0.897] | 11.0% | 6 8 10 12 | 10: 67%; 8: 31%; 6: 2% |
| gần sắp (~1%) | 2^16 | 24 | 64 | 64 | 0.701 [0.694, 0.707] | 29.9% | 64 | 64: 100%; 2: 0%; 4: 0% |
| ít giá trị (10) | 2^16 | 24 | 32 | 32 | 0.816 [0.812, 0.821] | 18.4% | 24 32 48 | 32: 100%; 24: 0%; 48: 0% |

- Gộp 3 thang random (trọng số bằng nhau): c tốt nhất = **31**, r = 0.874 [0.872, 0.877], gần tối ưu: 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48; tần suất bootstrap là tốt nhất: 31: 46%; 32: 38%; 30: 8%; 29: 7%.

## 3. RQ3 — CUTOFF 7, 10 và tốt nhất so với baseline (random)

| thang |  | c | r [CI] | thời gian giảm [CI] | tăng tốc | r = 0.80 trong CI? | r = 0.833 trong CI? |
|---|---|---|---|---|---|---|---|
| 2^12 | c = 7 | 7 | 0.899 [0.895, 0.903] | 10.1% [9.7%, 10.5%] | 1.112× | không | không |
| 2^12 | c = 10 | 10 | 0.882 [0.875, 0.889] | 11.8% [11.1%, 12.5%] | 1.133× | không | không |
| 2^12 | tốt nhất | 31 | 0.821 [0.815, 0.826] | 17.9% [17.4%, 18.5%] | 1.218× | không | không |
| 2^16 | c = 7 | 7 | 0.928 [0.926, 0.931] | 7.2% [6.9%, 7.4%] | 1.077× | không | không |
| 2^16 | c = 10 | 10 | 0.918 [0.915, 0.921] | 8.2% [7.9%, 8.5%] | 1.089× | không | không |
| 2^16 | tốt nhất | 32 | 0.880 [0.878, 0.882] | 12.0% [11.8%, 12.2%] | 1.136× | không | không |
| 2^19 | c = 7 | 7 | 0.952 [0.948, 0.956] | 4.8% [4.4%, 5.2%] | 1.051× | không | không |
| 2^19 | c = 10 | 10 | 0.944 [0.940, 0.948] | 5.6% [5.2%, 6.0%] | 1.059× | không | không |
| 2^19 | tốt nhất | 48 | 0.921 [0.916, 0.925] | 7.9% [7.5%, 8.4%] | 1.086× | không | không |

Bài giảng (Phần 1, mục cải tiến Mergesort): thêm cutoff "có thể nhanh hơn khoảng 20%". Hai cách đọc: thời gian giảm 20% (r = 0.80) hoặc nhanh hơn 1.2 lần (r ≈ 0.833).

So sánh ghép cặp: log(T_a/T_b) trung bình trong từng N trước (tránh giả lặp), Wilcoxon signed-rank trên các N, Holm cho cả họ kiểm định. *holdout* = c tốt nhất chọn trên trial lẻ, đánh giá trên trial chẵn (tránh lời nguyền người thắng).

| thang | loại | a | b | T_a/T_b [CI] | a nhanh hơn ở | p (Wilcoxon) | p (Holm) |
|---|---|---|---|---|---|---|---|
| 2^12 | in-sample | 7 | 10 | 1.0189 [1.0104, 1.0272] | 6/24 N | 0.000963 | 0.00193 |
| 2^12 | in-sample | 31 | 7 | 0.9130 [0.9063, 0.9201] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | in-sample | 31 | 10 | 0.9302 [0.9239, 0.9366] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 31 | 7 | 0.9134 [0.9052, 0.9221] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 31 | 10 | 0.9292 [0.9217, 0.9364] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 31 | 1 | 0.8223 [0.8160, 0.8292] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | in-sample | 7 | 10 | 1.0113 [1.0066, 1.0162] | 4/24 N | 0.000175 | 0.000526 |
| 2^16 | in-sample | 32 | 7 | 0.9477 [0.9449, 0.9506] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | in-sample | 32 | 10 | 0.9585 [0.9553, 0.9617] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 32 | 7 | 0.9499 [0.9466, 0.9532] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 32 | 10 | 0.9572 [0.9536, 0.9610] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 32 | 1 | 0.8782 [0.8752, 0.8813] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | in-sample | 7 | 10 | 1.0085 [1.0023, 1.0148] | 7/24 N | 0.0269 | 0.0269 |
| 2^19 | in-sample | 48 | 7 | 0.9670 [0.9623, 0.9718] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | in-sample | 48 | 10 | 0.9752 [0.9715, 0.9791] | 23/24 N | 2.38e-07 | 2.15e-06 |
| 2^19 | holdout | 40 | 7 | 0.9692 [0.9616, 0.9767] | 23/24 N | 5.96e-07 | 2.98e-06 |
| 2^19 | holdout | 40 | 10 | 0.9778 [0.9705, 0.9857] | 20/24 N | 3.02e-05 | 0.000121 |
| 2^19 | holdout | 40 | 1 | 0.9263 [0.9215, 0.9318] | 24/24 N | 1.19e-07 | 2.15e-06 |

## 4. Lớp tương đương và độ dài lá

- N = 2^12: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 2.8%; SD gộp của log r = 0.008 (≈ ±0.8% cho r của một CUTOFF ở một N).
- N = 2^16: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 1.9%; SD gộp của log r = 0.005 (≈ ±0.5% cho r của một CUTOFF ở một N).
- N = 2^19: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 1.2%; SD gộp của log r = 0.004 (≈ ±0.4% cho r của một CUTOFF ở một N).
- Số cây khác nhau trên lưới 35 CUTOFF (random, từ S trong counts.csv): N = 2^k: 7, 7, 7; các N khác: trung vị 10 (min 7, max 11).
- Theo độ dài lá trung bình (gộp mọi N random): r nhỏ nhất ≈ 0.869 ở độ dài lá ≈ 20.6 (khoảng (19.027, 22.627]).

## 5. RQ2 — Ảnh hưởng của N và phân bố

- ngẫu nhiên (thang 2^16): c tốt nhất = 32, thời gian giảm 12.0%, gần tối ưu: 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48.
- đã sắp (thang 2^16): c tốt nhất = 64, thời gian giảm 33.6%, gần tối ưu: 64.
- đảo ngược (thang 2^16): c tốt nhất = 10, thời gian giảm 11.0%, gần tối ưu: 6 8 10 12.
- gần sắp (~1%) (thang 2^16): c tốt nhất = 64, thời gian giảm 29.9%, gần tối ưu: 64.
- ít giá trị (10) (thang 2^16): c tốt nhất = 32, thời gian giảm 18.4%, gần tối ưu: 24 32 48.
- Random theo thang: c tốt nhất 2^12 → 31, 2^16 → 32, 2^19 → 48.

## 6. Số đếm (MergeCutoffCounted, random)

- Thang 2^12, c = 31: C ×1.261, A ×1.129, S ×0.639, E/(N lgN) = 0.433, trong khi T ×0.821 so với c = 1.
- Thang 2^16, c = 32: C ×1.202, A ×1.106, S ×0.723, E/(N lgN) = 0.340, trong khi T ×0.880 so với c = 1.
- Thang 2^19, c = 48: C ×1.302, A ×1.213, S ×0.736, E/(N lgN) = 0.438, trong khi T ×0.921 so với c = 1.
- c = 1: C/(N lgN) = 0.900–0.936, A/(N lgN) = 5.818–5.884 (cận bài giảng: C ≤ N lgN, A ≤ 6 N lgN).

## 7. Mô hình thời gian chạy T = a·N^b (random)

- c = 1 (72 N): b = 1.1439 ± 0.0019, a = 56.04 ns, R² = 0.99982; T/(N lgN) ≈ 17.658 ns.
- c = 31 (72 N): b = 1.1682 ± 0.0019, a = 37.33 ns, R² = 0.99981; T/(N lgN) ≈ 15.437 ns.
- Kiểm chứng c = 1: fit trên 2^12 + 2^16, dự đoán 2^19 → sai số tương đối (power law) TB -8.6%, |max| 11.3%; mô hình k·N lgN: TB -20.0%, |max| 21.7%. (Âm = dự đoán thấp hơn đo.)
- Kiểm chứng c = 31: fit trên 2^12 + 2^16, dự đoán 2^19 → sai số tương đối (power law) TB -7.6%, |max| 11.0%; mô hình k·N lgN: TB -26.2%, |max| 28.1%. (Âm = dự đoán thấp hơn đo.)
- T/(N lgN) theo thang (TB nhân trên các N; working set 24N B; L2 ứng với N ≈ 43691 (L2 1 MB/nhân), L3 ứng với N ≈ 699051 (L3 16 MB)): c = 1: 15.82 / 16.99 / 20.49 ns (2^12 / 2^16 / 2^19), tỉ số 2^16:2^12 = 1.074, 2^19:2^16 = 1.206; trong thang 2^19: N < 699051 → 20.57 ns, N ≥ 699051 → 20.44 ns; c = 31: 12.98 / 14.99 / 18.90 ns (2^12 / 2^16 / 2^19), tỉ số 2^16:2^12 = 1.155, 2^19:2^16 = 1.261; trong thang 2^19: N < 699051 → 19.01 ns, N ≥ 699051 → 18.83 ns. Mô hình k·N lgN thuần trên cùng tập N cho b = 1.0923; phần b vượt quá giá trị này tương ứng với việc T/(N lgN) tăng theo N (hình fig14); vị trí bước tăng so với ngưỡng L2/L3 là bằng chứng gián tiếp cho hiệu ứng cache, không phải phép đo trực tiếp.

## 8. Chẩn đoán

- Warm-up JVM fork 1, phiên 1: 10 vòng, vòng 1 = 467.1 ms, 3 vòng cuối = 583.5–587.3 ms.
- Warm-up JVM fork 2, phiên 1: 6 vòng, vòng 1 = 404.6 ms, 3 vòng cuối = 359.2–409.0 ms.
- Warm-up JVM fork 3, phiên 1: 13 vòng, vòng 1 = 366.9 ms, 3 vòng cuối = 479.9–481.6 ms.
- Warm-up từng bộ (trung vị T_warmup / T_đo): ít giá trị (10): vòng 1 = 1.000, vòng 2 = 1.000, vòng 3 = 1.000; gần sắp (~1%): vòng 1 = 0.999, vòng 2 = 1.000, vòng 3 = 1.000; ngẫu nhiên: vòng 1 = 1.001, vòng 2 = 1.001, vòng 3 = 1.001; đảo ngược: vòng 1 = 1.001, vòng 2 = 1.001, vòng 3 = 1.001; đã sắp: vòng 1 = 1.000, vòng 2 = 1.000, vòng 3 = 1.000.
- Trôi (fork 1, hồi quy fixed-effects theo (phân bố, N, c)): +0.02% mỗi 1000 lần đo (p = 9.63e-05), Spearman ρ = +0.033.
- Trôi (fork 2, hồi quy fixed-effects theo (phân bố, N, c)): +0.05% mỗi 1000 lần đo (p = 4.03e-45), Spearman ρ = +0.089.
- Trôi (fork 3, hồi quy fixed-effects theo (phân bố, N, c)): +0.09% mỗi 1000 lần đo (p = 4.59e-92), Spearman ρ = +0.105.
- Trôi (gộp các fork, hồi quy fixed-effects theo (phân bố, N, c)): +0.05% mỗi 1000 lần đo (p = 2.03e-32), Spearman ρ = +0.040.
- Chênh lệch r giữa các fork (max/min − 1): 2^12 c = 10: 3.16%; 2^12 c = 7: 2.69%; 2^12 tốt nhất: 3.58%; 2^16 c = 10: 2.50%; 2^16 c = 7: 1.79%; 2^16 tốt nhất: 2.53%; 2^19 c = 10: 2.35%; 2^19 c = 7: 1.75%; 2^19 tốt nhất: 3.69%.

## Tệp

- Bảng: cache_levels.csv, completeness.csv, counts_all_normalized.csv, counts_normalized.csv, distinct_trees_per_N.csv, drift.csv, env_summary.csv, equivalence_classes_2k.csv, forks_speedup.csv, gc_summary.csv, r_by_cutoff.csv, r_by_cutoff_with_gc.csv, r_by_leaf_length.csv, r_per_N.csv, rq1_argmin_bootstrap.csv, rq1_best_cutoff.csv, rq1_pooled_random.csv, rq3_paired_tests.csv, rq3_speedup.csv, runtime_model.csv, runtime_validation_2e19.csv, warmup_dataset_vs_measured.csv, warmup_jvm_rounds.csv
- Hình: fig01_r_vs_cutoff_random.png, fig02_argmin_bootstrap.png, fig03_speedup_7_10_best.png, fig04_paired_differences.png, fig05_equivalence_classes.png, fig06_r_vs_leaf_length.png, fig07_heatmap_random.png, fig08_distributions_2e16.png, fig09_counts_vs_time.png, fig10_runtime_model.png, fig14_cache_levels.png, fig11_jvm_warmup.png, fig12_drift.png, fig13_forks.png
