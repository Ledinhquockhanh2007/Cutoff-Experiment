# Tóm tắt kết quả thí nghiệm CUTOFF

- Kết quả: `results_run3` — chế độ **full**, 3 fork, 81720 lần đo, 504 cặp (fork, bộ dữ liệu).
- Môi trường: Windows 11 amd64, Microsoft JDK 25.0.4.1, 16 luồng; cờ JVM: `[-Xms2g, -Xmx2g, -XX:+UseSerialGC, -XX:+AlwaysPreTouch]`.
- counts.csv: `results_run3\counts.csv`; bootstrap B = 10000, seed = 20261027.

## 1. Độ đầy đủ và GC

- Bộ dữ liệu theo kế hoạch: 504; đủ ô (trial × CUTOFF): 504; thiếu/thừa: 0.
- Lần đo có gc_during_run = true: **0** / 81720 (loại khỏi phân tích chính). Trial mất baseline c = 1 do loại GC: 0.
- Phụ lục (giữ cả lần đo có GC): r lệch tối đa 0.00% so với bản chính (`tables/r_by_cutoff_with_gc.csv`).
- Lô K theo bộ dữ liệu: 1, 3, 4, 5, 6, 7, 8.

## 2. RQ1 — CUTOFF tốt nhất (r = T(c)/T(1), TB nhân trên các N, CI 95% bootstrap theo cụm N)

| phân bố | thang | số N | c tốt nhất | c tốt nhất (median) | r [CI 95%] | thời gian giảm | gần tối ưu (≤ 2%) | argmin bootstrap (top 3) |
|---|---|---|---|---|---|---|---|---|
| ngẫu nhiên | 2^12 | 24 | 29 | 30 | 0.820 [0.808, 0.831] | 18.0% | 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 | 29: 72%; 32: 17%; 30: 8% |
| ngẫu nhiên | 2^16 | 24 | 31 | 28 | 0.888 [0.885, 0.890] | 11.2% | 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 | 31: 36%; 30: 25%; 32: 20% |
| ngẫu nhiên | 2^19 | 24 | 27 | 30 | 0.918 [0.916, 0.920] | 8.2% | 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 64 | 27: 75%; 30: 11%; 31: 9% |
| đã sắp | 2^16 | 24 | 64 | 64 | 0.647 [0.642, 0.651] | 35.3% | 64 | 64: 100%; 2: 0%; 4: 0% |
| đảo ngược | 2^16 | 24 | 8 | 8 | 0.887 [0.884, 0.890] | 11.3% | 6 8 10 12 | 8: 100%; 1: 0%; 2: 0% |
| gần sắp (~1%) | 2^16 | 24 | 64 | 64 | 0.686 [0.682, 0.689] | 31.4% | 64 | 64: 100%; 2: 0%; 4: 0% |
| ít giá trị (10) | 2^16 | 24 | 32 | 32 | 0.828 [0.825, 0.830] | 17.2% | 20 24 32 48 | 32: 100%; 24: 0%; 4: 0% |

- Gộp 3 thang random (trọng số bằng nhau): c tốt nhất = **30**, r = 0.875 [0.871, 0.879], gần tối ưu: 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48; tần suất bootstrap là tốt nhất: 30: 29%; 31: 24%; 29: 23%; 32: 18%.

## 3. RQ3 — CUTOFF 7, 10 và tốt nhất so với baseline (random)

| thang |  | c | r [CI] | thời gian giảm [CI] | tăng tốc | r = 0.80 trong CI? | r = 0.833 trong CI? |
|---|---|---|---|---|---|---|---|
| 2^12 | c = 7 | 7 | 0.892 [0.890, 0.895] | 10.8% [10.5%, 11.0%] | 1.121× | không | không |
| 2^12 | c = 10 | 10 | 0.874 [0.867, 0.881] | 12.6% [11.9%, 13.3%] | 1.144× | không | không |
| 2^12 | tốt nhất | 29 | 0.820 [0.808, 0.831] | 18.0% [16.9%, 19.2%] | 1.219× | không | không |
| 2^16 | c = 7 | 7 | 0.925 [0.923, 0.927] | 7.5% [7.3%, 7.7%] | 1.081× | không | không |
| 2^16 | c = 10 | 10 | 0.914 [0.911, 0.918] | 8.6% [8.2%, 8.9%] | 1.094× | không | không |
| 2^16 | tốt nhất | 31 | 0.888 [0.885, 0.890] | 11.2% [11.0%, 11.5%] | 1.126× | không | không |
| 2^19 | c = 7 | 7 | 0.948 [0.945, 0.951] | 5.2% [4.9%, 5.5%] | 1.055× | không | không |
| 2^19 | c = 10 | 10 | 0.938 [0.935, 0.942] | 6.2% [5.8%, 6.5%] | 1.066× | không | không |
| 2^19 | tốt nhất | 27 | 0.918 [0.916, 0.920] | 8.2% [8.0%, 8.4%] | 1.089× | không | không |

Bài giảng (Phần 1, mục cải tiến Mergesort): thêm cutoff "có thể nhanh hơn khoảng 20%". Hai cách đọc: thời gian giảm 20% (r = 0.80) hoặc nhanh hơn 1.2 lần (r ≈ 0.833).

So sánh ghép cặp: log(T_a/T_b) trung bình trong từng N trước (tránh giả lặp), Wilcoxon signed-rank trên các N, Holm cho cả họ kiểm định. *holdout* = c tốt nhất chọn trên trial lẻ, đánh giá trên trial chẵn (tránh lời nguyền người thắng).

| thang | loại | a | b | T_a/T_b [CI] | a nhanh hơn ở | p (Wilcoxon) | p (Holm) |
|---|---|---|---|---|---|---|---|
| 2^12 | in-sample | 7 | 10 | 1.0209 [1.0128, 1.0297] | 3/24 N | 1.67e-06 | 5.01e-06 |
| 2^12 | in-sample | 29 | 7 | 0.9192 [0.9069, 0.9306] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | in-sample | 29 | 10 | 0.9384 [0.9312, 0.9449] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 29 | 7 | 0.9194 [0.9062, 0.9312] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 29 | 10 | 0.9397 [0.9322, 0.9470] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 29 | 1 | 0.8213 [0.8099, 0.8318] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | in-sample | 7 | 10 | 1.0120 [1.0079, 1.0162] | 2/24 N | 2.01e-05 | 4.03e-05 |
| 2^16 | in-sample | 31 | 7 | 0.9597 [0.9575, 0.9621] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | in-sample | 31 | 10 | 0.9713 [0.9685, 0.9740] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 28 | 7 | 0.9593 [0.9564, 0.9625] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 28 | 10 | 0.9721 [0.9685, 0.9757] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 28 | 1 | 0.8878 [0.8851, 0.8906] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | in-sample | 7 | 10 | 1.0103 [1.0051, 1.0160] | 6/24 N | 0.00109 | 0.00109 |
| 2^19 | in-sample | 27 | 7 | 0.9687 [0.9650, 0.9720] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | in-sample | 27 | 10 | 0.9786 [0.9756, 0.9817] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | holdout | 27 | 7 | 0.9702 [0.9667, 0.9738] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | holdout | 27 | 10 | 0.9806 [0.9769, 0.9844] | 23/24 N | 3.58e-07 | 2.15e-06 |
| 2^19 | holdout | 27 | 1 | 0.9181 [0.9156, 0.9206] | 24/24 N | 1.19e-07 | 2.15e-06 |

## 4. Lớp tương đương và độ dài lá

- N = 2^12: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 2.4%; SD gộp của log r = 0.007 (≈ ±0.7% cho r của một CUTOFF ở một N).
- N = 2^16: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 1.7%; SD gộp của log r = 0.004 (≈ ±0.4% cho r của một CUTOFF ở một N).
- N = 2^19: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 1.8%; SD gộp của log r = 0.004 (≈ ±0.4% cho r của một CUTOFF ở một N).
- Số cây khác nhau trên lưới 35 CUTOFF (random, từ S trong counts.csv): N = 2^k: 7, 7, 7; các N khác: trung vị 10 (min 7, max 11).
- Theo độ dài lá trung bình (gộp mọi N random): r nhỏ nhất ≈ 0.866 ở độ dài lá ≈ 17.5 (khoảng (16.0, 19.027]).

## 5. RQ2 — Ảnh hưởng của N và phân bố

- ngẫu nhiên (thang 2^16): c tốt nhất = 31, thời gian giảm 11.2%, gần tối ưu: 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48.
- đã sắp (thang 2^16): c tốt nhất = 64, thời gian giảm 35.3%, gần tối ưu: 64.
- đảo ngược (thang 2^16): c tốt nhất = 8, thời gian giảm 11.3%, gần tối ưu: 6 8 10 12.
- gần sắp (~1%) (thang 2^16): c tốt nhất = 64, thời gian giảm 31.4%, gần tối ưu: 64.
- ít giá trị (10) (thang 2^16): c tốt nhất = 32, thời gian giảm 17.2%, gần tối ưu: 20 24 32 48.
- Random theo thang: c tốt nhất 2^12 → 29, 2^16 → 31, 2^19 → 27.

## 6. Số đếm (MergeCutoffCounted, random)

- Thang 2^12, c = 29: C ×1.237, A ×1.108, S ×0.646, E/(N lgN) = 0.406, trong khi T ×0.820 so với c = 1.
- Thang 2^16, c = 31: C ×1.192, A ×1.097, S ×0.726, E/(N lgN) = 0.328, trong khi T ×0.888 so với c = 1.
- Thang 2^19, c = 27: C ×1.131, A ×1.055, S ×0.778, E/(N lgN) = 0.242, trong khi T ×0.918 so với c = 1.
- c = 1: C/(N lgN) = 0.900–0.936, A/(N lgN) = 5.818–5.884 (cận bài giảng: C ≤ N lgN, A ≤ 6 N lgN).

## 7. Mô hình thời gian chạy T = a·N^b (random)

- c = 1 (72 N): b = 1.1509 ± 0.0020, a = 28.34 ns, R² = 0.99980; T/(N lgN) ≈ 9.664 ns.
- c = 30 (72 N): b = 1.1746 ± 0.0027, a = 19.04 ns, R² = 0.99962; T/(N lgN) ≈ 8.459 ns.
- Kiểm chứng c = 1: fit trên 2^12 + 2^16, dự đoán 2^19 → sai số tương đối (power law) TB -3.7%, |max| 6.8%; mô hình k·N lgN: TB -20.4%, |max| 24.3%. (Âm = dự đoán thấp hơn đo.)
- Kiểm chứng c = 30: fit trên 2^12 + 2^16, dự đoán 2^19 → sai số tương đối (power law) TB -0.9%, |max| 3.6%; mô hình k·N lgN: TB -26.0%, |max| 29.8%. (Âm = dự đoán thấp hơn đo.)
- T/(N lgN) theo thang (TB nhân trên các N; working set 24N B; L2 ứng với N ≈ 43691 (L2 1 MB/nhân), L3 ứng với N ≈ 699051 (L3 16 MB)): c = 1: 8.46 / 9.48 / 11.26 ns (2^12 / 2^16 / 2^19), tỉ số 2^16:2^12 = 1.121, 2^19:2^16 = 1.187; trong thang 2^19: N < 699051 → 11.01 ns, N ≥ 699051 → 11.43 ns; c = 30: 6.95 / 8.42 / 10.34 ns (2^12 / 2^16 / 2^19), tỉ số 2^16:2^12 = 1.211, 2^19:2^16 = 1.229; trong thang 2^19: N < 699051 → 10.10 ns, N ≥ 699051 → 10.52 ns. Mô hình k·N lgN thuần trên cùng tập N cho b = 1.0923; phần b vượt quá giá trị này tương ứng với việc T/(N lgN) tăng theo N (hình fig14); vị trí bước tăng so với ngưỡng L2/L3 là bằng chứng gián tiếp cho hiệu ứng cache, không phải phép đo trực tiếp.

Diễn giải bộ nhớ (phù hợp với hiệu ứng bộ nhớ, KHÔNG chứng minh là do cache):

- Kỳ vọng: khi working set 24N B vượt một mức cache, chỉ các tầng đệ quy TRÊN CÙNG (đoạn con lớn) vượt mức đó, các tầng sâu vẫn nằm trong cache. Vì vậy T/(N lgN) nên TĂNG DẦN theo số tầng vượt, không nhảy bậc tại vạch dọc.
- c = 1, thang 2^12 (lgN 12.0–13.0): T/(N lgN) 7.32–8.96 ns, xu hướng trong thang +19.96% mỗi lần gấp đôi N (p = 2.79e-10); số tầng vượt L1D 32 KB: 1.6–2.5, vượt L2 1 MB: 0.0–0.0, vượt L3 16 MB: 0.0–0.0.
- c = 1, thang 2^16 (lgN 16.0–17.0): T/(N lgN) 9.33–9.75 ns, xu hướng trong thang +2.34% mỗi lần gấp đôi N (p = 0.000227); số tầng vượt L1D 32 KB: 5.6–6.5, vượt L2 1 MB: 0.6–1.5, vượt L3 16 MB: 0.0–0.0.
- c = 1, thang 2^19 (lgN 19.0–20.0): T/(N lgN) 10.76–11.83 ns, xu hướng trong thang +7.53% mỗi lần gấp đôi N (p = 3.72e-10); số tầng vượt L1D 32 KB: 8.6–9.5, vượt L2 1 MB: 3.6–4.5, vượt L3 16 MB: 0.0–0.5.
- c = 30, thang 2^12 (lgN 12.0–13.0): T/(N lgN) 5.65–7.67 ns, xu hướng trong thang +33.03% mỗi lần gấp đôi N (p = 2.22e-11); số tầng vượt L1D 32 KB: 1.6–2.5, vượt L2 1 MB: 0.0–0.0, vượt L3 16 MB: 0.0–0.0.
- c = 30, thang 2^16 (lgN 16.0–17.0): T/(N lgN) 8.28–8.73 ns, xu hướng trong thang +4.23% mỗi lần gấp đôi N (p = 1.49e-08); số tầng vượt L1D 32 KB: 5.6–6.5, vượt L2 1 MB: 0.6–1.5, vượt L3 16 MB: 0.0–0.0.
- c = 30, thang 2^19 (lgN 19.0–20.0): T/(N lgN) 9.80–10.89 ns, xu hướng trong thang +7.97% mỗi lần gấp đôi N (p = 4.49e-10); số tầng vượt L1D 32 KB: 8.6–9.5, vượt L2 1 MB: 3.6–4.5, vượt L3 16 MB: 0.0–0.5.
- Ở trạng thái nhanh (pilot 2026-10-27 22:19, R = 2): T/(N lgN) ở c = 1 = 2^16: 10.38 ns, 2^19: 11.18 ns — tỉ số giữa các thang khác với các lượt ở xung thấp, nên độ tăng theo N phụ thuộc xung (độ trễ bộ nhớ cố định theo ns chiếm tỉ trọng lớn hơn khi nhân chạy nhanh).
- Không tách được trong thiết kế này: TLB (trang 4 KB), L3 kiểu victim cache của Zen (dung lượng hiệu dụng ≈ L2 + L3), băng thông DRAM single-channel, truy cập giá trị Integer qua tham chiếu đã bị xáo trộn (truy cập ngẫu nhiên vào vùng 16N B), và mức xung của nhân chạy luồng đo (mục 10).

## 8. Chẩn đoán

- Warm-up JVM fork 1, phiên 1: 13 vòng, vòng 1 = 497.3 ms, 3 vòng cuối = 334.9–342.7 ms.
- Warm-up JVM fork 2, phiên 1: 7 vòng, vòng 1 = 504.4 ms, 3 vòng cuối = 343.9–346.0 ms.
- Warm-up JVM fork 3, phiên 1: 8 vòng, vòng 1 = 511.0 ms, 3 vòng cuối = 320.3–323.4 ms.
- Warm-up từng bộ (trung vị T_warmup / T_đo): ít giá trị (10): vòng 1 = 1.000, vòng 2 = 0.999, vòng 3 = 1.000; gần sắp (~1%): vòng 1 = 1.000, vòng 2 = 1.000, vòng 3 = 1.000; ngẫu nhiên: vòng 1 = 1.002, vòng 2 = 1.002, vòng 3 = 1.002; đảo ngược: vòng 1 = 1.000, vòng 2 = 1.000, vòng 3 = 1.000; đã sắp: vòng 1 = 1.000, vòng 2 = 1.000, vòng 3 = 0.999.
- Trôi (fork 1, hồi quy fixed-effects theo (phân bố, N, c)): -0.02% mỗi 1000 lần đo (p = 9.6e-07), Spearman ρ = -0.096.
- Trôi (fork 2, hồi quy fixed-effects theo (phân bố, N, c)): +0.02% mỗi 1000 lần đo (p = 1.22e-11), Spearman ρ = +0.044.
- Trôi (fork 3, hồi quy fixed-effects theo (phân bố, N, c)): -0.11% mỗi 1000 lần đo (p = 1.16e-158), Spearman ρ = -0.203.
- Trôi (gộp các fork, hồi quy fixed-effects theo (phân bố, N, c)): -0.04% mỗi 1000 lần đo (p = 2.49e-44), Spearman ρ = -0.063.
- Chênh lệch r giữa các fork (max/min − 1): 2^12 c = 10: 1.00%; 2^12 c = 7: 0.71%; 2^12 tốt nhất: 0.46%; 2^16 c = 10: 1.16%; 2^16 c = 7: 0.85%; 2^16 tốt nhất: 1.44%; 2^19 c = 10: 2.16%; 2^19 c = 7: 0.93%; 2^19 tốt nhất: 2.67%.

## 9. Biến thiên giữa các JVM (đơn vị lặp = JVM; c tốt nhất gộp = 30)

- **Lưu ý:** mọi CI bootstrap ở mục 2–3 chỉ lấy mẫu lại theo N, KHÔNG bao gồm biến thiên giữa các JVM. Khoảng t dưới đây coi mỗi JVM là một lần lặp độc lập (n = số JVM, t với n − 1 bậc tự do, trên log). Các fork cùng số ở các lượt dùng cùng thứ tự bộ dữ liệu (seed 1000 + fork), nên không hoàn toàn độc lập. Các lượt gộp: run 3 (ghim nhân 5), run 2, run 1.

| thang | đại lượng | số JVM | TB nhân | min–max | khoảng t 95% | số JVM có 10 nhanh hơn 7 |
|---|---|---|---|---|---|---|
| 2^12 | r(7) | 9 | 0.8929 | 0.8830–0.9076 | [0.8860, 0.8999] |  |
| 2^12 | r(10) | 9 | 0.8771 | 0.8680–0.8954 | [0.8705, 0.8836] |  |
| 2^12 | r(30) | 9 | 0.8214 | 0.8035–0.8355 | [0.8133, 0.8296] |  |
| 2^12 | T7/T10 | 9 | 1.0181 | 1.0126–1.0247 | [1.0148, 1.0214] | 9/9 |
| 2^16 | r(7) | 9 | 0.9233 | 0.9118–0.9359 | [0.9175, 0.9291] |  |
| 2^16 | r(10) | 9 | 0.9127 | 0.9007–0.9303 | [0.9056, 0.9197] |  |
| 2^16 | r(30) | 9 | 0.8814 | 0.8654–0.8941 | [0.8738, 0.8891] |  |
| 2^16 | T7/T10 | 9 | 1.0116 | 1.0060–1.0151 | [1.0092, 1.0141] | 9/9 |
| 2^19 | r(7) | 9 | 0.9511 | 0.9383–0.9646 | [0.9442, 0.9581] |  |
| 2^19 | r(10) | 9 | 0.9389 | 0.9282–0.9552 | [0.9324, 0.9455] |  |
| 2^19 | r(30) | 9 | 0.9208 | 0.9049–0.9467 | [0.9109, 0.9308] |  |
| 2^19 | T7/T10 | 9 | 1.0130 | 1.0037–1.0306 | [1.0059, 1.0201] | 9/9 |

Chi tiết từng JVM: `tables/per_jvm.csv`; hình `fig16_per_jvm.png`.

## 10. Hai mức hiệu năng (bước nhảy; không do biên dịch lại MergeCutoff — log PrintCompilation; cơ chế: xung của nhân chạy luồng đo — chẩn đoán E6, T2, run 3)

Bước nhảy warm-up: vòng đầu tiên (từ vòng 3) có tổng > 1.10 × trung vị các vòng trước (bỏ vòng 1) và trung vị từ vòng đó tới hết cũng vượt ngưỡng này. Mức warm-up = trung vị 3 vòng cuối / 343 ms (mức nhanh của WarmupProbe E0_2, 9.35 ns·N lgN). Trạng thái theo bộ dữ liệu: rel = T của JVM / T cùng bộ ở **run 3 (ghim nhân 5)** (TB nhân các fork của lượt đó, TB log T trên mọi c và trial); 'nhanh' (= cùng mức tham chiếu) nếu rel < 1.25. Hai mức đo được ở E6: xung 128.1% / 79.3% → tỉ lệ 1.62, trung điểm trên log 1.27. Không dùng ngưỡng tuyệt đối theo T/(N lgN): trong một JVM ở một trạng thái, T/(N lgN) giữa các bộ dữ liệu đã chênh 3.3–3.7× (phân bố, N). Nếu lượt tham chiếu ở mức chậm thì 'nhanh' chỉ có nghĩa 'không chậm hơn tham chiếu'; cột 'rel < 0.80' đếm các bộ nhanh hẳn hơn tham chiếu.

| JVM | RAM trống (GB) | số vòng | tổng mỗi vòng (ms) | vòng nhảy | tỉ lệ nhảy | mức 3 vòng cuối / nhanh |
|---|---|---|---|---|---|---|
| run 3 (ghim nhân 5) f1 | 3.95 | 13 | 497.3 331.7 352.7 329.7 328.9 352.8 369.5 347.3 345.1 330.5 337.6 342.7 334.9 | – | – | 0.98 |
| run 3 (ghim nhân 5) f2 | 4.62 | 7 | 504.4 362.0 344.5 345.6 344.2 346.0 343.9 | – | – | 1.00 |
| run 3 (ghim nhân 5) f3 | 4.48 | 8 | 511.0 340.6 332.0 322.9 321.7 320.6 323.4 320.3 | – | – | 0.93 |
| run 2 f1 | 5.42 | 10 | 467.1 394.3 398.6 394.1 429.0 649.8 660.4 587.3 583.5 587.2 | 6 | 1.48× | 1.71 |
| run 2 f2 | 5.35 | 6 | 404.6 359.2 356.2 360.4 359.2 409.0 | 6 | 1.14× | 1.05 |
| run 2 f3 | 5.11 | 13 | 366.9 308.8 310.4 313.4 312.7 312.0 426.6 478.8 481.9 480.0 480.3 481.6 479.9 | 7 | 1.54× | 1.40 |
| run 1 f1 | 2.45 | 12 | 392.9 343.6 335.7 331.9 330.4 356.5 538.2 559.6 545.8 550.4 589.1 524.2 | 7 | 1.63× | 1.60 |
| run 1 f2 | 1.44 | 6 | 419.6 361.5 359.1 366.4 361.1 429.8 | 6 | 1.19× | 1.07 |
| run 1 f3 | 0.14 | 10 | 441.5 341.0 342.8 340.1 494.1 619.8 600.8 565.8 534.8 580.4 | 5 | 1.68× | 1.65 |
| pilot 2026-10-27 22:19 | 4.84 | 7 | 425.9 337.6 335.4 335.4 335.5 337.1 333.7 | – | – | 0.98 |

| JVM | loại | bộ nhanh (rel < 1.25) | bộ rel < 0.80 | rel trung vị [P5, P95] | rel random theo thang (TB nhân) | bộ chậm đầu tiên sau ≥ 3 bộ nhanh | bộ chậm theo nhóm |
|---|---|---|---|---|---|---|---|
| run 3 (ghim nhân 5) f1 | chính | 168/168 | 0 | 0.976 [0.955, 1.097] | random 2^12: 0.957; random 2^16: 0.982; random 2^19: 1.087 | – | – |
| run 3 (ghim nhân 5) f2 | chính | 168/168 | 0 | 0.970 [0.939, 0.984] | random 2^12: 0.968; random 2^16: 0.980; random 2^19: 0.947 | – | – |
| run 3 (ghim nhân 5) f3 | chính | 168/168 | 0 | 1.054 [0.966, 1.096] | random 2^12: 1.080; random 2^16: 1.039; random 2^19: 0.972 | – | – |
| run 2 f1 | chính | 0/168 | 0 | 1.726 [1.606, 1.846] | random 2^12: 1.777; random 2^16: 1.775; random 2^19: 1.821 | – | tất cả |
| run 2 f2 | chính | 0/168 | 0 | 1.959 [1.881, 2.107] | random 2^12: 2.095; random 2^16: 1.951; random 2^19: 1.951 | – | tất cả |
| run 2 f3 | chính | 0/168 | 0 | 1.720 [1.568, 1.852] | random 2^12: 1.791; random 2^16: 1.667; random 2^19: 1.715 | – | tất cả |
| run 1 f1 | chính | 0/168 | 0 | 1.707 [1.563, 1.998] | random 2^12: 1.777; random 2^16: 1.720; random 2^19: 1.693 | – | tất cả |
| run 1 f2 | chính | 0/168 | 0 | 2.012 [1.715, 2.390] | random 2^12: 2.065; random 2^16: 2.055; random 2^19: 1.924 | – | tất cả |
| run 1 f3 | chính | 0/168 | 0 | 1.957 [1.791, 2.184] | random 2^12: 2.055; random 2^16: 1.951; random 2^19: 1.868 | – | tất cả |
| pilot 2026-10-27 22:19 | pilot | 14/17 | 0 | 1.106 [0.991, 1.344] | random 2^12: 1.331; random 2^16: 1.117; random 2^19: 0.995 | 9 | random 2^12: 3 |

r của pilot so với lượt chính tại cùng (phân bố, N), theo trạng thái (log r_pilot − log r_chính, c > 1; R = 2 nên nhiễu lớn):

| pilot | trạng thái | phân bố | số N | chênh TB | SD | Pearson |
|---|---|---|---|---|---|---|
| pilot 2026-10-27 22:19 | nhanh | ít giá trị (10) | 2 | +0.54% | 2.03% | 0.882 |
| pilot 2026-10-27 22:19 | nhanh | gần sắp (~1%) | 2 | +5.16% | 1.95% | 0.987 |
| pilot 2026-10-27 22:19 | nhanh | ngẫu nhiên | 6 | +1.61% | 1.75% | 0.726 |
| pilot 2026-10-27 22:19 | nhanh | đảo ngược | 2 | -1.50% | 3.84% | 0.964 |
| pilot 2026-10-27 22:19 | nhanh | đã sắp | 2 | +2.51% | 4.79% | 0.916 |
| pilot 2026-10-27 22:19 | chậm | ngẫu nhiên | 3 | +8.27% | 8.83% | 0.095 |

- Ước lượng pilot (3 fork): pilot 2026-10-27 22:19: 1:17:48. Thời gian thực (tổng 3 fork): run 3 (ghim nhân 5): 1:15:21; run 2: 2:13:12; run 1: 2:16:48.
- Hình: `fig17_jit_state.png`. Dữ liệu: `tables/jit_*.csv` (jit_dataset_state.csv: rel từng bộ).

## 11. So sánh 3 lượt chạy: run 3 (ghim nhân 5) (chính), run 2, run 1

- run 3 (ghim nhân 5): 81720 lần đo, gc_during_run = 0, c tốt nhất gộp 3 thang random = 30; run 2: 81720 lần đo, gc_during_run = 0, c tốt nhất gộp 3 thang random = 31; run 1: 81720 lần đo, gc_during_run = 0, c tốt nhất gộp 3 thang random = 40.
- Thứ tự trong mọi ô có dấu '/': run 3 (ghim nhân 5) / run 2 / run 1.

| phân bố | thang | c tốt nhất | gần tối ưu 2% | giao 3 lượt | giảm c=7 | giảm c=10 | giảm tại c tốt nhất | T7/T10 (p Wilcoxon) | T/(N lgN) c=1 so với run 3 (ghim nhân 5) |
|---|---|---|---|---|---|---|---|---|---|
| ngẫu nhiên | 2^12 | 29 / 31 / 32 | 19–48 / 22–48 / 21–48 | 22 23 24 25 26 27 28 29 30 31 32 40 48 | 10.8% / 10.1% / 11.3% | 12.6% / 11.8% / 12.5% | 18.0% / 17.9% / 18.2% | 1.0209 (1.7e-06) / 1.0189 (0.00096) / 1.0145 (0.031) | 1.000 / 1.870 / 1.958 |
| ngẫu nhiên | 2^16 | 31 / 32 / 29 | 13–48 / 19–48 / 18–48 | 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 | 7.5% / 7.2% / 8.4% | 8.6% / 8.2% / 9.4% | 11.2% / 12.0% / 12.7% | 1.0120 (2e-05) / 1.0113 (0.00018) / 1.0115 (0.0043) | 1.000 / 1.792 / 1.921 |
| ngẫu nhiên | 2^19 | 27 / 48 / 24 | 11–64 / 12–64 / 11–64 | 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 64 | 5.2% / 4.8% / 4.6% | 6.2% / 5.6% / 6.5% | 8.2% / 7.9% / 8.8% | 1.0103 (0.0011) / 1.0085 (0.027) / 1.0202 (0.0043) | 1.000 / 1.821 / 1.825 |

| phân bố | thang | c tốt nhất | gần tối ưu 2% | giao 3 lượt |
|---|---|---|---|---|
| đã sắp | 2^16 | 64 / 64 / 64 | 64–64 / 64–64 / 64–64 | 64 |
| đảo ngược | 2^16 | 8 / 10 / 10 | 6–12 / 6–12 / 6–12 | 6 8 10 12 |
| gần sắp (~1%) | 2^16 | 64 / 64 / 64 | 64–64 / 64–64 / 48–64 | 64 |
| ít giá trị (10) | 2^16 | 32 / 32 / 32 | 20–48 / 24–48 / 24–48 | 24 32 48 |

Từng cặp lượt: Pearson r của đường r(c) (c > 1) và (chênh r tối đa trên lưới):

| phân bố | thang | run 3 (ghim nhân 5) – run 2 | run 3 (ghim nhân 5) – run 1 | run 2 – run 1 |
|---|---|---|---|---|
| ngẫu nhiên | 2^12 | 0.998 (1.20%) | 0.996 (0.92%) | 0.997 (1.27%) |
| ngẫu nhiên | 2^16 | 0.986 (0.97%) | 0.980 (2.09%) | 0.991 (1.53%) |
| ngẫu nhiên | 2^19 | 0.981 (1.04%) | 0.946 (1.57%) | 0.962 (1.17%) |
| đã sắp | 2^16 | 1.000 (2.72%) | 0.999 (1.64%) | 1.000 (1.69%) |
| đảo ngược | 2^16 | 0.998 (3.43%) | 0.998 (4.82%) | 0.998 (2.31%) |
| gần sắp (~1%) | 2^16 | 0.999 (2.45%) | 0.999 (2.59%) | 0.999 (0.96%) |
| ít giá trị (10) | 2^16 | 0.987 (1.57%) | 0.987 (2.12%) | 0.998 (0.93%) |

- Mọi c trong 22 23 24 25 26 27 28 29 30 31 32 40 48 nằm trong vùng 2% của c tốt nhất ở cả 3 thang và cả 3 lượt (random).
- RAM trống lúc bắt đầu từng fork (GB): run 3 (ghim nhân 5): 3.95 / 4.62 / 4.48; run 2: 5.42 / 5.35 / 5.11; run 1: 2.45 / 1.44 / 0.14.
- Hình: `fig15_run_comparison.png`; bảng: `tables/compare_*.csv`.

## Phụ: độ phủ cây đệ quy (từ S trong counts.csv)

- Thang 2^12: số N (trên 24) có cây của c khác c − 1, c = 2..32: min 2 (số c có < 2 N: 0); với tập con 8 N (j chia hết cho 3): min 0 (số c có < 2 N: 17); chỉ N = 2^k: 5/31 giá trị c đổi cây.
- Thang 2^16: số N (trên 24) có cây của c khác c − 1, c = 2..32: min 2 (số c có < 2 N: 0); với tập con 8 N (j chia hết cho 3): min 0 (số c có < 2 N: 17); chỉ N = 2^k: 5/31 giá trị c đổi cây.
- Thang 2^19: số N (trên 24) có cây của c khác c − 1, c = 2..32: min 2 (số c có < 2 N: 0); với tập con 8 N (j chia hết cho 3): min 0 (số c có < 2 N: 17); chỉ N = 2^k: 5/31 giá trị c đổi cây.
- Bảng: `tables/tree_coverage.csv`.

## Tệp

- Bảng: cache_levels.csv, cache_within_scale.csv, compare_best.csv, compare_near_intersection.csv, compare_pairs.csv, compare_r_by_cutoff.csv, compare_ram_free.csv, compare_rq1_best_cutoff.csv, compare_summary.csv, completeness.csv, counts_all_normalized.csv, counts_normalized.csv, distinct_trees_per_N.csv, drift.csv, env_summary.csv, equivalence_classes_2k.csv, forks_speedup.csv, gc_summary.csv, jit_TnlgN_by_state.csv, jit_dataset_state.csv, jit_r_fast_vs_slow.csv, jit_state_summary.csv, jit_warmup_rounds.csv, per_jvm.csv, per_jvm_summary.csv, pilot_estimates.csv, r_by_cutoff.csv, r_by_cutoff_with_gc.csv, r_by_leaf_length.csv, r_per_N.csv, rq1_argmin_bootstrap.csv, rq1_best_cutoff.csv, rq1_pooled_random.csv, rq3_paired_tests.csv, rq3_speedup.csv, run_elapsed.csv, runtime_model.csv, runtime_validation_2e19.csv, tree_coverage.csv, warmup_dataset_vs_measured.csv, warmup_jvm_rounds.csv
- Hình: fig01_r_vs_cutoff_random.png, fig02_argmin_bootstrap.png, fig03_speedup_7_10_best.png, fig04_paired_differences.png, fig05_equivalence_classes.png, fig06_r_vs_leaf_length.png, fig07_heatmap_random.png, fig08_distributions_2e16.png, fig09_counts_vs_time.png, fig10_runtime_model.png, fig14_cache_levels.png, fig11_jvm_warmup.png, fig12_drift.png, fig13_forks.png, fig15_run_comparison.png, fig16_per_jvm.png, fig17_jit_state.png
