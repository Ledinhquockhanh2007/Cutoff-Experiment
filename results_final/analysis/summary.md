# Tóm tắt kết quả thí nghiệm CUTOFF

- Kết quả: `results_final` — chế độ **full**, 3 fork, 81720 lần đo, 504 cặp (fork, bộ dữ liệu).
- Môi trường: Windows 11 amd64, Microsoft JDK 25.0.4.1, 16 luồng; cờ JVM: `[-Xms2g, -Xmx2g, -XX:+UseSerialGC, -XX:+AlwaysPreTouch]`.
- counts.csv: `results_final\counts.csv`; bootstrap B = 10000, seed = 20261027.

## 1. Độ đầy đủ và GC

- Bộ dữ liệu theo kế hoạch: 504; đủ ô (trial × CUTOFF): 504; thiếu/thừa: 0.
- Lần đo có gc_during_run = true: **0** / 81720 (loại khỏi phân tích chính). Trial mất baseline c = 1 do loại GC: 0.
- Phụ lục (giữ cả lần đo có GC): r lệch tối đa 0.00% so với bản chính (`tables/r_by_cutoff_with_gc.csv`).
- Lô K theo bộ dữ liệu: 1.

## 2. RQ1 — CUTOFF tốt nhất (r = T(c)/T(1), TB nhân trên các N, CI 95% bootstrap theo cụm N)

| phân bố | thang | số N | c tốt nhất | c tốt nhất (median) | r [CI 95%] | thời gian giảm | gần tối ưu (≤ 2%) | argmin bootstrap (top 3) |
|---|---|---|---|---|---|---|---|---|
| ngẫu nhiên | 2^12 | 24 | 40 | 40 | 0.848 [0.840, 0.856] | 15.2% | 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 64 | 40: 71%; 48: 19%; 28: 6% |
| ngẫu nhiên | 2^16 | 24 | 31 | 28 | 0.888 [0.885, 0.890] | 11.2% | 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 | 31: 36%; 30: 25%; 32: 20% |
| ngẫu nhiên | 2^19 | 24 | 27 | 30 | 0.918 [0.916, 0.920] | 8.2% | 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 64 | 27: 75%; 30: 11%; 31: 9% |
| đã sắp | 2^16 | 24 | 64 | 64 | 0.647 [0.642, 0.651] | 35.3% | 64 | 64: 100%; 2: 0%; 4: 0% |
| đảo ngược | 2^16 | 24 | 8 | 8 | 0.887 [0.884, 0.890] | 11.3% | 6 8 10 12 | 8: 100%; 1: 0%; 2: 0% |
| gần sắp (~1%) | 2^16 | 24 | 64 | 64 | 0.686 [0.682, 0.689] | 31.4% | 64 | 64: 100%; 2: 0%; 4: 0% |
| ít giá trị (10) | 2^16 | 24 | 32 | 32 | 0.828 [0.825, 0.830] | 17.2% | 20 24 32 48 | 32: 100%; 24: 0%; 4: 0% |

- Gộp 3 thang random (trọng số bằng nhau): c tốt nhất = **30**, r = 0.886 [0.884, 0.888], gần tối ưu: 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 64; tần suất bootstrap là tốt nhất: 30: 47%; 40: 24%; 27: 18%; 32: 7%.

## 3. RQ3 — CUTOFF 7, 10 và tốt nhất so với baseline (random)

| thang |  | c | r [CI] | thời gian giảm [CI] | tăng tốc | r = 0.80 trong CI? | r = 0.833 trong CI? |
|---|---|---|---|---|---|---|---|
| 2^12 | c = 7 | 7 | 0.908 [0.903, 0.912] | 9.2% [8.8%, 9.7%] | 1.101× | không | không |
| 2^12 | c = 10 | 10 | 0.892 [0.884, 0.900] | 10.8% [10.0%, 11.6%] | 1.121× | không | không |
| 2^12 | tốt nhất | 40 | 0.848 [0.840, 0.856] | 15.2% [14.4%, 16.0%] | 1.179× | không | không |
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
| 2^12 | in-sample | 7 | 10 | 1.0180 [1.0099, 1.0262] | 7/24 N | 0.00109 | 0.00219 |
| 2^12 | in-sample | 40 | 7 | 0.9341 [0.9270, 0.9417] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | in-sample | 40 | 10 | 0.9509 [0.9455, 0.9565] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 40 | 7 | 0.9345 [0.9273, 0.9422] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^12 | holdout | 40 | 10 | 0.9532 [0.9479, 0.9599] | 23/24 N | 2.38e-07 | 2.15e-06 |
| 2^12 | holdout | 40 | 1 | 0.8483 [0.8417, 0.8555] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | in-sample | 7 | 10 | 1.0120 [1.0079, 1.0162] | 2/24 N | 2.01e-05 | 6.04e-05 |
| 2^16 | in-sample | 31 | 7 | 0.9597 [0.9575, 0.9621] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | in-sample | 31 | 10 | 0.9713 [0.9685, 0.9740] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 28 | 7 | 0.9593 [0.9564, 0.9625] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 28 | 10 | 0.9721 [0.9685, 0.9757] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^16 | holdout | 28 | 1 | 0.8878 [0.8851, 0.8906] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | in-sample | 7 | 10 | 1.0103 [1.0051, 1.0160] | 6/24 N | 0.00109 | 0.00219 |
| 2^19 | in-sample | 27 | 7 | 0.9687 [0.9650, 0.9720] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | in-sample | 27 | 10 | 0.9786 [0.9756, 0.9817] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | holdout | 27 | 7 | 0.9702 [0.9667, 0.9738] | 24/24 N | 1.19e-07 | 2.15e-06 |
| 2^19 | holdout | 27 | 10 | 0.9806 [0.9769, 0.9844] | 23/24 N | 3.58e-07 | 2.15e-06 |
| 2^19 | holdout | 27 | 1 | 0.9181 [0.9156, 0.9206] | 24/24 N | 1.19e-07 | 2.15e-06 |

## 4. Lớp tương đương và độ dài lá

- N = 2^12: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 5.3%; SD gộp của log r = 0.009 (≈ ±0.9% cho r của một CUTOFF ở một N).
- N = 2^16: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 1.7%; SD gộp của log r = 0.004 (≈ ±0.4% cho r của một CUTOFF ở một N).
- N = 2^19: 7 cây khác nhau trên lưới 35 CUTOFF: [1], [2–3], [4–7], [8–15], [16–31], [32–48], [64]. Trong cùng một lớp (cùng cây, nên chênh lệch chỉ là nhiễu đo): r chênh tối đa 1.8%; SD gộp của log r = 0.004 (≈ ±0.4% cho r của một CUTOFF ở một N).
- Số cây khác nhau trên lưới 35 CUTOFF (random, từ S trong counts.csv): N = 2^k: 7, 7, 7; các N khác: trung vị 10 (min 7, max 11).
- Theo độ dài lá trung bình (gộp mọi N random): r nhỏ nhất ≈ 0.881 ở độ dài lá ≈ 35.1 (khoảng (32.0, 38.055]).

## 5. RQ2 — Ảnh hưởng của N và phân bố

- ngẫu nhiên (thang 2^16): c tốt nhất = 31, thời gian giảm 11.2%, gần tối ưu: 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48.
- đã sắp (thang 2^16): c tốt nhất = 64, thời gian giảm 35.3%, gần tối ưu: 64.
- đảo ngược (thang 2^16): c tốt nhất = 8, thời gian giảm 11.3%, gần tối ưu: 6 8 10 12.
- gần sắp (~1%) (thang 2^16): c tốt nhất = 64, thời gian giảm 31.4%, gần tối ưu: 64.
- ít giá trị (10) (thang 2^16): c tốt nhất = 32, thời gian giảm 17.2%, gần tối ưu: 20 24 32 48.
- Random theo thang: c tốt nhất 2^12 → 40, 2^16 → 31, 2^19 → 27.

## 6. Số đếm (MergeCutoffCounted, random)

- Thang 2^12, c = 40: C ×1.381, A ×1.238, S ×0.609, E/(N lgN) = 0.567, trong khi T ×0.848 so với c = 1.
- Thang 2^16, c = 31: C ×1.192, A ×1.097, S ×0.726, E/(N lgN) = 0.328, trong khi T ×0.888 so với c = 1.
- Thang 2^19, c = 27: C ×1.131, A ×1.055, S ×0.778, E/(N lgN) = 0.242, trong khi T ×0.918 so với c = 1.
- c = 1: C/(N lgN) = 0.900–0.936, A/(N lgN) = 5.818–5.884 (cận bài giảng: C ≤ N lgN, A ≤ 6 N lgN).

## 7. Mô hình thời gian chạy T = a·N^b (random)

- c = 1 (72 N): b = 1.1171 ± 0.0027, a = 43.56 ns, R² = 0.99960; T/(N lgN) ≈ 10.176 ns.
- c = 30 (72 N): b = 1.1329 ± 0.0027, a = 32.35 ns, R² = 0.99960; T/(N lgN) ≈ 9.014 ns.
- Kiểm chứng c = 1: fit trên 2^12 + 2^16, dự đoán 2^19 → sai số tương đối (power law) TB -14.7%, |max| 18.6%; mô hình k·N lgN: TB -14.0%, |max| 18.2%. (Âm = dự đoán thấp hơn đo.)
- Kiểm chứng c = 30: fit trên 2^12 + 2^16, dự đoán 2^19 → sai số tương đối (power law) TB -14.8%, |max| 18.6%; mô hình k·N lgN: TB -18.6%, |max| 22.7%. (Âm = dự đoán thấp hơn đo.)
- T/(N lgN) theo thang (TB nhân trên các N; working set 24N B; L2 ứng với N ≈ 43691 (L2 1 MB/nhân), L3 ứng với N ≈ 699051 (L3 16 MB)): c = 1: 9.88 / 9.48 / 11.26 ns (2^12 / 2^16 / 2^19), tỉ số 2^16:2^12 = 0.960, 2^19:2^16 = 1.187; trong thang 2^19: N < 699051 → 11.01 ns, N ≥ 699051 → 11.43 ns; c = 30: 8.41 / 8.42 / 10.34 ns (2^12 / 2^16 / 2^19), tỉ số 2^16:2^12 = 1.001, 2^19:2^16 = 1.229; trong thang 2^19: N < 699051 → 10.10 ns, N ≥ 699051 → 10.52 ns. Mô hình k·N lgN thuần trên cùng tập N cho b = 1.0923; phần b vượt quá giá trị này tương ứng với việc T/(N lgN) tăng theo N (hình fig14); vị trí bước tăng so với ngưỡng L2/L3 là bằng chứng gián tiếp cho hiệu ứng cache, không phải phép đo trực tiếp.

Diễn giải bộ nhớ (phù hợp với hiệu ứng bộ nhớ, KHÔNG chứng minh là do cache):

- Kỳ vọng: khi working set 24N B vượt một mức cache, chỉ các tầng đệ quy TRÊN CÙNG (đoạn con lớn) vượt mức đó, các tầng sâu vẫn nằm trong cache. Vì vậy T/(N lgN) nên TĂNG DẦN theo số tầng vượt, không nhảy bậc tại vạch dọc.
- c = 1, thang 2^12 (lgN 12.0–13.0): T/(N lgN) 9.77–10.33 ns, xu hướng trong thang -0.87% mỗi lần gấp đôi N (p = 0.338); số tầng vượt L1D 32 KB: 1.6–2.5, vượt L2 1 MB: 0.0–0.0, vượt L3 16 MB: 0.0–0.0.
- c = 1, thang 2^16 (lgN 16.0–17.0): T/(N lgN) 9.33–9.75 ns, xu hướng trong thang +2.34% mỗi lần gấp đôi N (p = 0.000227); số tầng vượt L1D 32 KB: 5.6–6.5, vượt L2 1 MB: 0.6–1.5, vượt L3 16 MB: 0.0–0.0.
- c = 1, thang 2^19 (lgN 19.0–20.0): T/(N lgN) 10.76–11.83 ns, xu hướng trong thang +7.53% mỗi lần gấp đôi N (p = 3.72e-10); số tầng vượt L1D 32 KB: 8.6–9.5, vượt L2 1 MB: 3.6–4.5, vượt L3 16 MB: 0.0–0.5.
- c = 30, thang 2^12 (lgN 12.0–13.0): T/(N lgN) 8.34–8.53 ns, xu hướng trong thang +2.03% mỗi lần gấp đôi N (p = 2.35e-07); số tầng vượt L1D 32 KB: 1.6–2.5, vượt L2 1 MB: 0.0–0.0, vượt L3 16 MB: 0.0–0.0.
- c = 30, thang 2^16 (lgN 16.0–17.0): T/(N lgN) 8.28–8.73 ns, xu hướng trong thang +4.23% mỗi lần gấp đôi N (p = 1.49e-08); số tầng vượt L1D 32 KB: 5.6–6.5, vượt L2 1 MB: 0.6–1.5, vượt L3 16 MB: 0.0–0.0.
- c = 30, thang 2^19 (lgN 19.0–20.0): T/(N lgN) 9.80–10.89 ns, xu hướng trong thang +7.97% mỗi lần gấp đôi N (p = 4.49e-10); số tầng vượt L1D 32 KB: 8.6–9.5, vượt L2 1 MB: 3.6–4.5, vượt L3 16 MB: 0.0–0.5.
- Không tách được trong thiết kế này: TLB (trang 4 KB), L3 kiểu victim cache của Zen (dung lượng hiệu dụng ≈ L2 + L3), băng thông DRAM single-channel, truy cập giá trị Integer qua tham chiếu đã bị xáo trộn (truy cập ngẫu nhiên vào vùng 16N B), và mức xung của nhân chạy luồng đo (mục 10).

## 8. Chẩn đoán

- Warm-up JVM fork 1, phiên 1: 13 vòng, vòng 1 = 497.3 ms, 3 vòng cuối = 334.9–342.7 ms.
- Warm-up JVM fork 2, phiên 1: 7 vòng, vòng 1 = 504.4 ms, 3 vòng cuối = 343.9–346.0 ms.
- Warm-up JVM fork 3, phiên 1: 8 vòng, vòng 1 = 511.0 ms, 3 vòng cuối = 320.3–323.4 ms.
- Warm-up từng bộ (trung vị T_warmup / T_đo): ít giá trị (10): vòng 1 = 1.000, vòng 2 = 0.999, vòng 3 = 1.000; gần sắp (~1%): vòng 1 = 1.000, vòng 2 = 1.000, vòng 3 = 1.000; ngẫu nhiên: vòng 1 = 1.008, vòng 2 = 1.003, vòng 3 = 1.000; đảo ngược: vòng 1 = 1.000, vòng 2 = 1.000, vòng 3 = 1.000; đã sắp: vòng 1 = 1.000, vòng 2 = 1.000, vòng 3 = 0.999.
- Trôi (fork 1, hồi quy fixed-effects theo (phân bố, N, c)): +0.00% mỗi 1000 lần đo (p = 0.778), Spearman ρ = -0.057.
- Trôi (fork 2, hồi quy fixed-effects theo (phân bố, N, c)): +0.04% mỗi 1000 lần đo (p = 1.38e-22), Spearman ρ = +0.061.
- Trôi (fork 3, hồi quy fixed-effects theo (phân bố, N, c)): -0.07% mỗi 1000 lần đo (p = 2.17e-62), Spearman ρ = -0.078.
- Trôi (gộp các fork, hồi quy fixed-effects theo (phân bố, N, c)): +0.01% mỗi 1000 lần đo (p = 3.4e-05), Spearman ρ = +0.007.
- Chênh lệch r giữa các fork (max/min − 1): 2^12 c = 10: 1.54%; 2^12 c = 7: 1.93%; 2^12 tốt nhất: 3.48%; 2^16 c = 10: 1.16%; 2^16 c = 7: 0.85%; 2^16 tốt nhất: 1.44%; 2^19 c = 10: 2.16%; 2^19 c = 7: 0.93%; 2^19 tốt nhất: 2.67%.

## 9. Biến thiên giữa các JVM (đơn vị lặp = JVM; c tốt nhất gộp = 30)

- **Lưu ý:** mọi CI bootstrap ở mục 2–3 chỉ lấy mẫu lại theo N, KHÔNG bao gồm biến thiên giữa các JVM. Khoảng t dưới đây coi mỗi JVM là một lần lặp độc lập (n = số JVM, t với n − 1 bậc tự do, trên log). Các fork cùng số ở các lượt dùng cùng thứ tự bộ dữ liệu (seed 1000 + fork), nên không hoàn toàn độc lập. Các lượt gộp: results_final (K=1 sach), run 3 (goc).

| thang | đại lượng | số JVM | TB nhân | min–max | khoảng t 95% | số JVM có 10 nhanh hơn 7 |
|---|---|---|---|---|---|---|
| 2^12 | r(7) | 6 | 0.9003 | 0.8882–0.9152 | [0.8891, 0.9115] |  |
| 2^12 | r(10) | 6 | 0.8831 | 0.8685–0.8979 | [0.8713, 0.8950] |  |
| 2^12 | r(30) | 6 | 0.8366 | 0.8188–0.8692 | [0.8157, 0.8580] |  |
| 2^12 | T7/T10 | 6 | 1.0194 | 1.0154–1.0227 | [1.0170, 1.0219] | 6/6 |
| 2^16 | r(7) | 6 | 0.9252 | 0.9205–0.9283 | [0.9213, 0.9291] |  |
| 2^16 | r(10) | 6 | 0.9142 | 0.9083–0.9189 | [0.9092, 0.9193] |  |
| 2^16 | r(30) | 6 | 0.8880 | 0.8805–0.8920 | [0.8819, 0.8942] |  |
| 2^16 | T7/T10 | 6 | 1.0120 | 1.0103–1.0134 | [1.0105, 1.0135] | 6/6 |
| 2^19 | r(7) | 6 | 0.9478 | 0.9441–0.9529 | [0.9435, 0.9521] |  |
| 2^19 | r(10) | 6 | 0.9381 | 0.9282–0.9483 | [0.9288, 0.9476] |  |
| 2^19 | r(30) | 6 | 0.9190 | 0.9049–0.9325 | [0.9061, 0.9320] |  |
| 2^19 | T7/T10 | 6 | 1.0103 | 1.0049–1.0171 | [1.0044, 1.0162] | 6/6 |

Chi tiết từng JVM: `tables/per_jvm.csv`; hình `fig16_per_jvm.png`.

## 10. Hai mức hiệu năng (bước nhảy; không do biên dịch lại MergeCutoff — log PrintCompilation; cơ chế: xung của nhân chạy luồng đo — chẩn đoán E6, T2, run 3)

Bước nhảy warm-up: vòng đầu tiên (từ vòng 3) có tổng > 1.10 × trung vị các vòng trước (bỏ vòng 1) và trung vị từ vòng đó tới hết cũng vượt ngưỡng này. Mức warm-up = trung vị 3 vòng cuối / 343 ms (mức nhanh của WarmupProbe E0_2, 9.35 ns·N lgN). Trạng thái theo bộ dữ liệu: rel = T của JVM / T cùng bộ ở **results_final (K=1 sach)** (TB nhân các fork của lượt đó, TB log T trên mọi c và trial); 'nhanh' (= cùng mức tham chiếu) nếu rel < 1.25. Hai mức đo được ở E6: xung 128.1% / 79.3% → tỉ lệ 1.62, trung điểm trên log 1.27. Không dùng ngưỡng tuyệt đối theo T/(N lgN): trong một JVM ở một trạng thái, T/(N lgN) giữa các bộ dữ liệu đã chênh 3.3–3.7× (phân bố, N). Nếu lượt tham chiếu ở mức chậm thì 'nhanh' chỉ có nghĩa 'không chậm hơn tham chiếu'; cột 'rel < 0.80' đếm các bộ nhanh hẳn hơn tham chiếu.

| JVM | RAM trống (GB) | số vòng | tổng mỗi vòng (ms) | vòng nhảy | tỉ lệ nhảy | mức 3 vòng cuối / nhanh |
|---|---|---|---|---|---|---|
| results_final (K=1 sach) f1 | 3.95 | 13 | 497.3 331.7 352.7 329.7 328.9 352.8 369.5 347.3 345.1 330.5 337.6 342.7 334.9 | – | – | 0.98 |
| results_final (K=1 sach) f2 | 4.62 | 7 | 504.4 362.0 344.5 345.6 344.2 346.0 343.9 | – | – | 1.00 |
| results_final (K=1 sach) f3 | 4.48 | 8 | 511.0 340.6 332.0 322.9 321.7 320.6 323.4 320.3 | – | – | 0.93 |
| run 3 (goc) f1 | 3.95 | 13 | 497.3 331.7 352.7 329.7 328.9 352.8 369.5 347.3 345.1 330.5 337.6 342.7 334.9 | – | – | 0.98 |
| run 3 (goc) f2 | 4.62 | 7 | 504.4 362.0 344.5 345.6 344.2 346.0 343.9 | – | – | 1.00 |
| run 3 (goc) f3 | 4.48 | 8 | 511.0 340.6 332.0 322.9 321.7 320.6 323.4 320.3 | – | – | 0.93 |

| JVM | loại | bộ nhanh (rel < 1.25) | bộ rel < 0.80 | rel trung vị [P5, P95] | rel random theo thang (TB nhân) | bộ chậm đầu tiên sau ≥ 3 bộ nhanh | bộ chậm theo nhóm |
|---|---|---|---|---|---|---|---|
| results_final (K=1 sach) f1 | chính | 168/168 | 0 | 0.977 [0.963, 1.097] | random 2^12: 0.981; random 2^16: 0.982; random 2^19: 1.087 | – | – |
| results_final (K=1 sach) f2 | chính | 168/168 | 0 | 0.971 [0.939, 0.991] | random 2^12: 0.987; random 2^16: 0.980; random 2^19: 0.947 | – | – |
| results_final (K=1 sach) f3 | chính | 168/168 | 0 | 1.048 [0.966, 1.070] | random 2^12: 1.033; random 2^16: 1.039; random 2^19: 0.972 | – | – |
| run 3 (goc) f1 | chính | 168/168 | 8 | 0.975 [0.809, 1.097] | random 2^12: 0.799; random 2^16: 0.982; random 2^19: 1.087 | – | – |
| run 3 (goc) f2 | chính | 168/168 | 8 | 0.968 [0.814, 0.984] | random 2^12: 0.808; random 2^16: 0.980; random 2^19: 0.947 | – | – |
| run 3 (goc) f3 | chính | 168/168 | 0 | 1.048 [0.897, 1.070] | random 2^12: 0.902; random 2^16: 1.039; random 2^19: 0.972 | – | – |

- Ước lượng pilot (3 fork): –. Thời gian thực (tổng 3 fork): results_final (K=1 sach): 1:15:21; run 3 (goc): 1:15:21.
- Hình: `fig17_jit_state.png`. Dữ liệu: `tables/jit_*.csv` (jit_dataset_state.csv: rel từng bộ).

## 11. So sánh 2 lượt chạy: results_final (K=1 sach) (chính), run 3 (goc)

- results_final (K=1 sach): 81720 lần đo, gc_during_run = 0, c tốt nhất gộp 3 thang random = 30; run 3 (goc): 81720 lần đo, gc_during_run = 0, c tốt nhất gộp 3 thang random = 30.
- Thứ tự trong mọi ô có dấu '/': results_final (K=1 sach) / run 3 (goc).

| phân bố | thang | c tốt nhất | gần tối ưu 2% | giao 2 lượt | giảm c=7 | giảm c=10 | giảm tại c tốt nhất | T7/T10 (p Wilcoxon) | T/(N lgN) c=1 so với results_final (K=1 sach) |
|---|---|---|---|---|---|---|---|---|---|
| ngẫu nhiên | 2^12 | 40 / 29 | 17–64 / 19–48 | 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 | 9.2% / 10.8% | 10.8% / 12.6% | 15.2% / 18.0% | 1.0180 (0.0011) / 1.0209 (1.7e-06) | 1.000 / 0.857 |
| ngẫu nhiên | 2^16 | 31 / 31 | 13–48 / 13–48 | 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 | 7.5% / 7.5% | 8.6% / 8.6% | 11.2% / 11.2% | 1.0120 (2e-05) / 1.0120 (2e-05) | 1.000 / 1.000 |
| ngẫu nhiên | 2^19 | 27 / 27 | 11–64 / 11–64 | 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 64 | 5.2% / 5.2% | 6.2% / 6.2% | 8.2% / 8.2% | 1.0103 (0.0011) / 1.0103 (0.0011) | 1.000 / 1.000 |

| phân bố | thang | c tốt nhất | gần tối ưu 2% | giao 2 lượt |
|---|---|---|---|---|
| đã sắp | 2^16 | 64 / 64 | 64–64 / 64–64 | 64 |
| đảo ngược | 2^16 | 8 / 8 | 6–12 / 6–12 | 6 8 10 12 |
| gần sắp (~1%) | 2^16 | 64 / 64 | 64–64 / 64–64 | 64 |
| ít giá trị (10) | 2^16 | 32 / 32 | 20–48 / 20–48 | 20 24 32 48 |

Từng cặp lượt: Pearson r của đường r(c) (c > 1) và (chênh r tối đa trên lưới):

| phân bố | thang | results_final (K=1 sach) – run 3 (goc) |
|---|---|---|
| ngẫu nhiên | 2^12 | 0.989 (4.11%) |
| ngẫu nhiên | 2^16 | 1.000 (0.00%) |
| ngẫu nhiên | 2^19 | 1.000 (0.00%) |
| đã sắp | 2^16 | 1.000 (0.00%) |
| đảo ngược | 2^16 | 1.000 (0.00%) |
| gần sắp (~1%) | 2^16 | 1.000 (0.00%) |
| ít giá trị (10) | 2^16 | 1.000 (0.00%) |

- Mọi c trong 19 20 21 22 23 24 25 26 27 28 29 30 31 32 40 48 nằm trong vùng 2% của c tốt nhất ở cả 3 thang và cả 2 lượt (random).
- RAM trống lúc bắt đầu từng fork (GB): results_final (K=1 sach): 3.95 / 4.62 / 4.48; run 3 (goc): 3.95 / 4.62 / 4.48.
- Hình: `fig15_run_comparison.png`; bảng: `tables/compare_*.csv`.

## Phụ: độ phủ cây đệ quy (từ S trong counts.csv)

- Thang 2^12: số N (trên 24) có cây của c khác c − 1, c = 2..32: min 2 (số c có < 2 N: 0); với tập con 8 N (j chia hết cho 3): min 0 (số c có < 2 N: 17); chỉ N = 2^k: 5/31 giá trị c đổi cây.
- Thang 2^16: số N (trên 24) có cây của c khác c − 1, c = 2..32: min 2 (số c có < 2 N: 0); với tập con 8 N (j chia hết cho 3): min 0 (số c có < 2 N: 17); chỉ N = 2^k: 5/31 giá trị c đổi cây.
- Thang 2^19: số N (trên 24) có cây của c khác c − 1, c = 2..32: min 2 (số c có < 2 N: 0); với tập con 8 N (j chia hết cho 3): min 0 (số c có < 2 N: 17); chỉ N = 2^k: 5/31 giá trị c đổi cây.
- Bảng: `tables/tree_coverage.csv`.

## Tệp

- Bảng: cache_levels.csv, cache_within_scale.csv, compare_best.csv, compare_near_intersection.csv, compare_pairs.csv, compare_r_by_cutoff.csv, compare_ram_free.csv, compare_rq1_best_cutoff.csv, completeness.csv, counts_all_normalized.csv, counts_normalized.csv, distinct_trees_per_N.csv, drift.csv, env_summary.csv, equivalence_classes_2k.csv, forks_speedup.csv, gc_summary.csv, jit_TnlgN_by_state.csv, jit_dataset_state.csv, jit_r_fast_vs_slow.csv, jit_state_summary.csv, jit_warmup_rounds.csv, per_jvm.csv, per_jvm_summary.csv, pilot_estimates.csv, r_by_cutoff.csv, r_by_cutoff_with_gc.csv, r_by_leaf_length.csv, r_per_N.csv, rq1_argmin_bootstrap.csv, rq1_best_cutoff.csv, rq1_pooled_random.csv, rq3_paired_tests.csv, rq3_speedup.csv, run_elapsed.csv, runtime_model.csv, runtime_validation_2e19.csv, tree_coverage.csv, warmup_dataset_vs_measured.csv, warmup_jvm_rounds.csv
- Hình: fig01_r_vs_cutoff_random.png, fig02_argmin_bootstrap.png, fig03_speedup_7_10_best.png, fig04_paired_differences.png, fig05_equivalence_classes.png, fig06_r_vs_leaf_length.png, fig07_heatmap_random.png, fig08_distributions_2e16.png, fig09_counts_vs_time.png, fig10_runtime_model.png, fig14_cache_levels.png, fig11_jvm_warmup.png, fig12_drift.png, fig13_forks.png, fig15_run_comparison.png, fig16_per_jvm.png, fig17_jit_state.png
