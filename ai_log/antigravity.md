# Nhật ký làm việc với Antigravity (ghi lại thủ công)

Antigravity (Google, dùng các mô hình Gemini và Claude Sonnet) được dùng làm tác tử lập trình: viết bộ đo, chương trình sinh dữ liệu, script phân tích, bảng và hình theo yêu cầu. Antigravity không có chức năng xuất hội thoại, nên tệp này là bản sinh viên chép lại từ khung chat của công cụ, **không phải bản xuất tự động**; giờ cụ thể không được lưu nên chỉ ghi ngày. Mã nguồn và lịch sử commit trong repo là nguồn đối chiếu chính xác cho những gì đã được tạo ra.

- **Thư mục làm việc:** `d:\DSA\cutoff-experiment`
- **Hai bên:** sinh viên, Antigravity

---

## Phiên 1: Sinh dữ liệu, kiểm thử đúng đắn, bộ đếm và harness đo thời gian

### 2026-10-27 — Yêu cầu của sinh viên
Tôi đã tự viết xong src/MergeCutoff.java rồi. Giờ bạn viết giúp tôi bộ sinh dữ liệu test nhiều phân bố với bộ kiểm thử tự động để check kỹ thuật toán trước khi đo với

### 2026-10-27 — Kết quả Antigravity báo lại (tóm tắt)
Đã đọc `src/MergeCutoff.java` (giữ nguyên không chỉnh sửa) và tạo hai lớp trong `src/`:

1. **`src/DataGenerator.java`**:
   - Sinh 5 phân bố (`DISTRIBUTIONS`): `random`, `sorted`, `reversed`, `nearly_sorted` (đổi chỗ ngẫu nhiên $\lfloor N/100 \rfloor$ cặp), và `few_distinct` (10 giá trị phân biệt `OFFSET + 1000*k`), tất cả giá trị $\ge$ `OFFSET = 1_000_000` để nằm ngoài `IntegerCache`.
   - `scaleNs(int s)` tạo 24 giá trị $N_j = \text{round}(S \cdot 2^{j/24})$ cho `RANDOM_SCALES = {2^12, 2^16, 2^19}` và `OTHER_SCALE = 2^16` (tổng 168 bộ dữ liệu trong `plan()`).
   - Dùng `seedFor(dist, n)` kết hợp `mix64(long z)` (SplitMix64) cho `java.util.Random`, ghi file nhị phân int32 little-endian vào `data/<dist>/N<7 chữ số>.bin` kèm `data/manifest.csv` chứa mã băm `sha256` và `data.zip` qua `zipDir()`. Hỗ trợ `--verify` qua `verify()` để kiểm tra lại toàn bộ file trên đĩa.

2. **`src/CorrectnessTest.java`** (chạy với `-ea` trong JVM riêng):
   - Gồm các hàm `testAssertionsEnabled()`, `testGenerator()`, `testGrid()`, `testStability()` cùng các bộ đối chứng độc lập `simulate()` và `inversions()`.
   - Kiểm tra `isSorted()`, tính hoán vị so với `Arrays.sort`, tính ổn định qua `Item(key, idx)`, ngoại lệ `cutoff < 1`, và kiểm tra chéo các cận đếm lý thuyết.

Bạn có thể biên dịch và chạy kiểm tra bằng:
```powershell
javac -encoding UTF-8 -d build src\*.java
java -ea -cp build CorrectnessTest
java -cp build DataGenerator
java -cp build DataGenerator --verify
```

---

### 2026-10-27 — Yêu cầu của sinh viên
CorrectnessTest đã pass rồi, DataGenerator --verify cũng ok. Giờ làm giúp tôi bản đếm phép toán (compares, accesses, exchanges, merged_len) với harness đo thời gian Benchmark.java và script chạy tự động luôn.

### 2026-10-27 — Kết quả Antigravity báo lại (tóm tắt)
Đã tạo xong bộ đếm, harness đo và script điều phối:

1. **`src/MergeCutoffCounted.java`** & **`src/CountRunner.java`**:
   - Sao chép logic của `MergeCutoff.java`, bỏ `assert` và gắn bộ đếm theo quy ước Sedgewick (`reset()`, `getCompares()`, `getAccesses()`, `getExchanges()`, `getMergedLen()`, `lessCounted()`).
   - `CountRunner` đọc cùng `manifest.csv` qua `Benchmark.readManifest()`, chạy tất cả các lưới `cutoff` và ghi `counts.csv`, đồng thời kiểm tra bất biến `A == 4*S + 2*C + 4*E` trên từng dòng.

2. **`src/Benchmark.java`**:
   - Lưới CUTOFF: `FULL_GRID` (35 giá trị: `1..32, 40, 48, 64`) cho `random`; `SPARSE_GRID` (13 giá trị) cho 4 phân bố còn lại.
   - `measure(Integer[] base, int cutoff, int k)`: gọi `System.gc()` ngoài vùng đo, `clone()` sẵn `k` mảng, đo `System.nanoTime()` cho `k` lần `MergeCutoff.sort()`, kiểm tra `isSorted()`, ghi cờ `gc_during_run` từ `gcCount()`, và trả về `Math.round((t1 - t0) / (double) k)` (tức `time_ns` đã là thời gian của **một** lần sắp).
   - `runDataset()` chạy 3 vòng warm-up theo bộ dữ liệu (`DATASET_WARMUP_ROUNDS = 3`), tự tính cỡ lô `kFor()` hướng tới `TARGET_BATCH_NS = 2_000_000L` (2 ms), xáo thứ tự CUTOFF bằng `shuffled()` với `trialSeed()`. Hỗ trợ `--pilot`, `--fork`, `--resume` (qua `resumeScan()`).

3. **`scripts/run_all.bat`**:
   - Chạy tuần tự: `javac` -> `CorrectnessTest -ea` -> `DataGenerator --verify` -> `CountRunner` -> `Benchmark --fork 1..3`.

---

## Phiên 2: Phân tích giai đoạn 1, chẩn đoán `batch_k` và đo lại thang $2^{12}$ (Run 4)

### 2026-10-29 — Yêu cầu của sinh viên
Tôi chạy xong 3 lượt rồi. Bạn viết script phân tích tổng thể xem cutoff tốt nhất là bao nhiêu và có nhanh hơn 20% như bài giảng không.

### 2026-10-29 — Kết quả Antigravity báo lại (tóm tắt)
Đã viết `scripts/analyze.py` và `scripts/descriptive.py` để phân tích dữ liệu thô (`raw_fork1..3.csv`) và `counts.csv`:

- Trong `scripts/analyze.py`: hàm `load()`, `point_by_cutoff()`, `cluster_boot_means()`, `paired_test()` và `holm()` tính tỉ số ghép cặp `r = T(c)/T(1)` theo từng `(fork, distribution, N, trial)`, bootstrap theo cụm $N$ ($B = 10\,000$, `seed = 20261027`) và kiểm định Wilcoxon có hiệu chỉnh Holm.
- Trong `scripts/descriptive.py`: `load_raw()`, `make_design_table()`, `make_variance_components()`, `make_pairing_gain()`, `make_precision_vs_R()` thực hiện phân rã phương sai trong-JVM vs giữa-JVM và đánh giá hiệu quả ghép cặp.
- **Lưu ý quy ước quan trọng:** Trong `load_raw()`, `time_ns` đã được `Benchmark.measure()` chia sẵn cho `batch_k`, nên chỉ quy đổi `df["t_ms"] = df["time_ns"] / 1e6` (đã thêm assert kiểm tra `median(N=2^16, k=1) = 8.5515 ms` trên `results_run3`).

---

### 2026-10-29 — Yêu cầu của sinh viên
Từ từ, sao kết quả thang 2^12 của run 3 thấy hơi gắt hơn hai thang kia nhiều vậy. Có khi nào chạy batch_k > 1 lặp lại trên cùng mảng làm cache nóng lên và kéo thời gian giảm ảo không? Viết tool kiểm tra thử xem.

### 2026-10-29 — Kết quả Antigravity báo lại (tóm tắt)
Đã bổ sung công cụ chẩn đoán độc lập:

1. **`src/KDiag.java`** & **`scripts/run_kdiag.bat`**:
   - Dùng `readTargetDatasets()`, `getPairsForN()` và `measure(base, cutoff, k)` để đo trực tiếp các giá trị $K \in \{1, 2, 4, 8\}$ tại 6 mức $N$ của thang $2^{12}$ (`J_SCALE_12 = {0, 5, 10, 15, 20, 23}`) và $K \in \{1, 2\}$ tại 2 mức $N$ của thang $2^{16}$ trên `CUTOFFS = {1, 7, 10, 30}` (20 trial).
2. **`scripts/k_diag_analyze.py`** & **`scripts/k_natural_experiment.py`**:
   - Phân tích 6,720 phép đo trong `results_kdiag/` và xác nhận có sai lệch hệ thống do lô $K$: tại $c = 1$, $K = 8$ nhanh hơn $K = 1$ từ $-18.3\%$ ($N = 4096$) đến $-2.4\%$ ($N = 7959$), trong khi thang $2^{16}$ không có hiệu ứng này. Do đó, số liệu $2^{12}$ của run 3 ($K = 3..8$) bị lệch thời gian tuyệt đối và làm phồng mức giảm của `cutoff = 30`.

Ngoài ra, cũng đã có `src/WarmupProbe.java` và `scripts/diag_bench_align.py` (`read_typeperf()`, `add_pinned()`, `cross_fork()`) để đối chiếu dấu thời gian với `typeperf` khi điều tra dao động xung CPU ở run 1 và run 2.

---

### 2026-10-29 — Yêu cầu của sinh viên
Vậy ta chạy lại riêng thang 2^12 random với K = 1 cố định rồi gộp với hai thang sạch kia của Run 3 nhé. Bạn chuẩn bị script chạy Run 4 và gộp thành results_final luôn đi.

### 2026-10-29 — Kết quả Antigravity báo lại (tóm tắt)
Đã cập nhật `src/Benchmark.java` thêm `--fixed-k` và `--only-scale`, đồng thời tạo `scripts/run_run4.bat` (chạy `--only-scale 2^12 --fixed-k 1`, ghim nhân 5 `/affinity C00`) và `scripts/merge_run4.py` để hợp nhất dữ liệu thành `results_final/`.

Sau khi bạn chạy xong Run 4 (25,200 hàng, `K = 1`, `0` hàng `gc_during_run`) và chạy lại `scripts/analyze.py` + `scripts/descriptive.py` trên `results_final/`, các kết quả chính ghi nhận trong `results_final/analysis/tables/` gồm:
- `rq1_best_cutoff.csv` (ngẫu nhiên):
  - $2^{12}$: $c^* = 40$, $r = 0.8484$ (CI 95%: `[0.8404, 0.8557]`), vùng gần tối ưu 2% trải rộng `17..64`.
  - $2^{16}$: $c^* = 31$, $r = 0.8879$ (CI 95%: `[0.8855, 0.8903]`), vùng gần tối ưu `13..48`.
  - $2^{19}$: $c^* = 27$, $r = 0.9181$ (CI 95%: `[0.9160, 0.9202]`), vùng gần tối ưu `11..64`.
- `rq3_speedup.csv`: mức giảm thời gian lớn nhất chỉ đạt `15.16%` ($2^{12}$), `11.21%` ($2^{16}$) và `8.19%` ($2^{19}$); không có CI nào chạm ngưỡng `r = 0.80` hay `0.833` của bài giảng.
- `rq3_paired_tests.csv`: $T_7/T_{10}$ bằng `1.0180` ($2^{12}$, `p_holm = 0.00219`), `1.0120` ($2^{16}$, `p_holm = 6.04e-5`), `1.0103` ($2^{19}$, `p_holm = 0.00219`).
- `variance_components_summary.csv` & `pairing_gain_summary.csv`: `sd_within_median_pct = 1.36%`, `sd_between_median_pct = 4.16%`, ghép cặp theo JVM giảm `87.94%` phương sai tổng (`red_total_median_pct`).

---

## Phiên 3: Quy luật lũy thừa, mô hình chi phí cây đệ quy và Doubling Test

### 2026-10-30 — Yêu cầu của sinh viên
Giờ làm tiếp phần phân tích quy luật lũy thừa T = aN^b với xây mô hình chi phí dựa trên cây đệ quy và counts.csv xem giải thích được đường r(c) không

### 2026-10-30 — Kết quả Antigravity báo lại (tóm tắt)
Đã hoàn thiện chuỗi script phân tích quy luật lũy thừa và mô hình chi phí:

1. **`scripts/power_law.py`**:
   - Các hàm `load_run_data()`, `fit_power_law_ols()`, `compare_two_runs()`, `compute_fork_scale_interaction()`, `compute_algorithmic_exponents()`, `compute_cache_step_analysis()`.
   - Kết quả trong `results_final/analysis_v2/tables/power_law_fits.csv`: trên 48 $N$ sạch ($2^{16} + 2^{19}$, cùng JVM), tại $c = 1$ thu được $b = 1.1625$, $a = 24.41\text{ ns}$; tại $c = 30$ thu được $b = 1.1790$, $a = 17.96\text{ ns}$. (Script `scripts/cache_step_vs_smooth.py` với `compare_step_vs_smooth()` cũng cho thấy trong $2^{19}$ mô hình trơn theo $\ln N$ phù hợp hơn giả thuyết bước nhảy tại $N = 699\,051$).

2. **`scripts/tree_features.py`**:
   - Hàm `tree_stats(n, c)` mô phỏng chính xác quy ước chia `mid = lo + (hi - lo) / 2` của `MergeCutoff.java`, xuất `tree_features.csv` gồm tổng độ dài trộn `ML`, số lá `leaves2`, `leaf_pairs`, và 6 bucket độ dài merge `b1..b6` (`<=8`, `9..32`, `33..128`, `129..512`, `513..2048`, `>2048`). Hàm `run_checks()` đối chiếu khớp 100% với `counts.csv`.

3. **`scripts/cost_model.py`** & **`scripts/validate_cost_model.py`**:
   - Khớp 3 mô hình WLS (trọng số $1/T^2$) trong `fit_and_evaluate_models()`: `M0` (chi phí hằng số), `M1` (6 bucket dùng chung), `M2` (3 bucket nhỏ `ML_b1..b3` dùng chung + `exchanges` + `ML_b456` riêng theo thang).
   - Kết quả trong `cost_model_loso.csv`: `M2` đạt RMSE(r) bỏ-một-thang là `0.0087` ($2^{12}$), `0.0068` ($2^{16}$), `0.0029` ($2^{19}$), vượt trội so với `M0` (`0.0898 / 0.0657 / 0.0755`) và `M1` (`0.0854 / 0.0083 / 0.0164`).
   - Hệ số `M2` trong `cost_model_M2_coef.csv`: `ML_b1 = 5.855`, `ML_b2 = 10.624`, `ML_b3 = 16.543`, `exchanges = 3.273`, `ML_b456_12 = 9.076`, `ML_b456_16 = 8.786`, `ML_b456_19 = 11.582` (ns).
   - `validate_other_distributions()` kiểm tra ngoại suy sang 4 phân bố khác ở $2^{16}$ cho RMSE `0.037–0.069` (không dùng ngoài `random`); `compute_sensitivity()` xác nhận khoảng `24–40` bền vững khi biến thiên hệ số $\pm 20\text{–}25\%$.

---

### 2026-10-30 — Yêu cầu của sinh viên
Tôi muốn chạy thêm doubling test từ N = 2^10 đến 2^22 trên 9 giá trị cutoff để xem xu hướng tỉ lệ tăng gấp đôi R_k và kiểm tra xem chi phí merge lớn có bão hòa sau 2^19 không. Bạn chuẩn bị bộ dữ liệu, dự đoán và script phân tích nhé.

### 2026-10-30 — Kết quả Antigravity báo lại (tóm tắt)
Đã chuẩn bị hoàn chỉnh luồng Doubling Test v1:

1. **Dữ liệu & Harness**:
   - Bổ sung `planDoubling()` và cờ `--doubling` trong `src/DataGenerator.java` (sinh `data_doubling/` cho $N = 2^{10}..2^{24}$).
   - Bổ sung `--grid` trong `src/Benchmark.java` và tạo `scripts/run_doubling.bat` chạy trên lưới `{1, 4, 7, 8, 10, 16, 30, 32, 64}` (chứa 3 cặp cùng cây đệ quy `(4,7)`, `(8,10)`, `(16,30)`), `K = 1` cố định, 3 fork, ghim nhân 5.
2. **Dự đoán & Phân tích**:
   - **`scripts/doubling_predict.py`**: xuất dự đoán trước khi đo cho các predictor `P1`, `P2`, `P3`, `P3b`, `P3c` (`predict_t_p3c()`) vào `handoff/preregistration/`.
   - **`scripts/doubling_analyze.py`**: `load_doubling_data()`, `compute_geometric_means()`, `compute_r_and_rbar()` xuất toàn bộ bảng vào `results_doubling/analysis/tables/`.
   - Kết quả chính sau khi bạn đo xong (`A6_power_law_b.csv`, `B2_t_over_nlgn.csv`, `A3_step_test.csv`, `A4_saturation_test.csv`, `B3_cutoff_ratio_r.csv`):
     - $T/(N \lg N)$ ở $c = 1$ phẳng quanh `10.0–10.3 ns` từ $2^{10}..2^{16}$, sau đó tăng liên tục lên `10.46, 10.78, 11.23, 12.39, 13.50, 14.76 ns` ($k = 17..22$), không bão hòa sau $2^{19}$ và không có bước nhảy đơn ở $2^{17}\to 2^{18}$ (`P3` và `P3c` đều bị bác).
     - `P2` gần nhất nhưng vẫn thấp hơn đo ở $k \ge 19$; số mũ hồi quy $k = 16..22$ đạt `b_mean = 1.1660` ($c = 1$) và `1.1800` ($c = 30$).
     - Tỉ số $r(N, 30)$ co dần từ `0.811` ($2^{10}$) và `0.845` ($2^{12}$) lên `0.888` ($2^{16}$), `0.920` ($2^{19}$) và `0.941` ($2^{22}$).

---

## Phiên 4: Đo bộ nhớ (JOL + ThreadMXBean) và Kiểm thử đột biến

### 2026-10-31 — Yêu cầu của sinh viên
Giờ viết giúp tôi code đo bộ nhớ thực tế của MergeCutoff trên Integer[] bằng JOL với ThreadMXBean qua các cấu hình JVM khác nhau, so sánh với công thức 40N + 48 trong mô hình chuẩn.

### 2026-10-31 — Kết quả Antigravity báo lại (tóm tắt)
Đã viết **`src/MemoryProbe.java`** (dùng `lib/jol-core-0.17.jar` và `com.sun.management.ThreadMXBean`) và **`scripts/run_memory.py`**:

- `MemoryProbe`:
  - `printClassLayouts()` in chi tiết `VM.current().details()` và `ClassLayout.parseClass(...)` cho `Integer`, `Integer[]`, `Comparable[]`.
  - `checkIdentity()` kiểm tra qua `IdentityHashMap` xác nhận 100% phần tử ở cả 5 phân bố ($N = 65536$) là các đối tượng `Integer` riêng biệt.
  - `measureSingle(int n, int[] rawInts)` đo lượng cấp phát thực tế bằng `getThreadAllocatedBytes()` cho mảng `a`, mảng đối tượng `Integer` và mảng `aux` trong `MergeCutoff.sort(copy, 30)`, đối chiếu với `GraphLayout.parseInstance()`.
- `run_memory.py` (`run_probe_for_config_and_size()`, `parse_layout_file()`, `generate_class_layouts_table()`):
  - Chạy trên 4 cấu hình JVM (`default`, `no_coops`, `lecture`, `compact_headers`) và 6 kích thước $N \in \{1024, 16384, 65536, 524288, 1048576, 4194304\}$.
  - Kết quả trong `results_final/analysis_v2/tables/memory_measurements.csv`: cả 24 hàng đo bằng JOL và `ThreadMXBean` đều khớp `0.0%` sai lệch với công thức:
    - `default`: $24N + 32\text{ B}$ (tại $N = 2^{20}$: `25,165,856 B` = 24 MiB).
    - `no_coops`: $32N + 32\text{ B}$ (`33,554,464 B` tại $N = 2^{20}$).
    - `lecture` (`-XX:-UseCompressedOops -XX:-UseCompressedClassPointers`): $40N + 48\text{ B}$ (`41,943,088 B` tại $N = 2^{20}$, gấp `1.67×` JVM mặc định).
    - `compact_headers` (`-XX:+UseCompactObjectHeaders`): $24N + 32\text{ B}$ với $N$ chẵn (do phần tử mảng bắt đầu ở offset 12 B, căn 8 B).

---

### 2026-11-17 — Yêu cầu của sinh viên
Tôi muốn bổ sung kiểm thử đột biến (mutation test) cho CorrectnessTest trên bản sao src/ để chứng minh bộ test bắt được lỗi thật, với chuẩn bị harness JMH và mở rộng giai đoạn 2 luôn nhé.

### 2026-11-17 — Kết quả Antigravity báo lại (tóm tắt)
Đã tạo:
1. **`scripts/mutation_test.py`** (`run_mutation()`):
   - Tạo bản sao cô lập trong `build_mut/` (tuyệt đối không chạm `src/MergeCutoff.java`), cài 4 đột biến `m1` (mất tính ổn định), `m2` (cutoff lệch 1), `m3` (insertion sort lệch 1), `m4` (tính `mid` lệch 1) và chạy `java -ea CorrectnessTest`.
   - Kết quả trên JDK 25 (`results_final/mutation_test.csv`): `baseline` PASS toàn bộ `970,425` kiểm tra (`0` lỗi); `4/4` đột biến bị bắt (`m1` FAIL nhóm `04, 05, 14`; `m2` FAIL nhóm `14`; `m3` FAIL nhóm `02, 03, 04, 05, 13, 14`; `m4` FAIL nhóm `13 (StackOverflow), 14`).

2. **Mở rộng harness & JMH cho Giai đoạn 2 (xác nhận)**:
   - `src/DataGenerator.java`: thêm `RUN5_RANDOM_SCALES = {2^12, 2^14, 2^16, 2^18, 2^19}`, `RUN5_OTHER_SCALES = {2^12, 2^16, 2^19}`, `seedForRun5()`, `planRun5()` sinh 408 file vào `data_run5/`.
   - `src/Benchmark.java`: mở rộng `--fork 1..6`, thêm `SORTED_NEARLY_GRID` (đến 4096), `REVERSED_FEW_GRID` (đến 128), `measureDouble()`, `measureInt()` (gọi `MergeCutoffInt.sort()` do bạn viết), cờ `--dists`, `--scales`, `--key`.
   - `src/CorrectnessTest.java`: bổ sung nhóm `15`, `16` kiểm tra `MergeCutoffInt` và lưới mở rộng (`984,204` kiểm tra PASS).
   - `jmh/src/bench/Sorter.java`, `jmh/src/MergeCutoffBridge.java`, `jmh/src/bench/MergeCutoffBenchmark.java` và các script chạy đo: `scripts/run5_s1_random.bat`, `scripts/run5_s2_other.bat`, `scripts/run_doubling_v2.bat` ($N = 2^{10}..2^{24}$), `scripts/run_d3_keys.bat` (`integer`, `double`, `int`), `scripts/run_jmh.bat`.
   - `scripts/predict_t09.py`: tính trước dự đoán cho thang $2^{14}$ (`alpha14 = 8.931288`), $2^{18}$ (`alpha18 = 10.650196`) và các mốc doubling v2 (`handoff/preregistration/T09_*.csv`).

---

## Phiên 5: Phân tích Giai đoạn 2 (xác nhận) & Giai đoạn 2b (chẩn đoán JMH và `int[]`)

### 2026-11-18 — Yêu cầu của sinh viên
5 phiên đo giai đoạn 2 chạy xong hết rồi (S1, S2, DV2, D3, JMH). Bạn viết script kiểm tra chất lượng typeperf trước rồi chạy phân tích kiểm định các giả thuyết H1–H17 giúp tôi.

### 2026-11-18 — Kết quả Antigravity báo lại (tóm tắt)
Đã viết `scripts/session_quality.py` và `scripts/analyze_t10.py` (cùng có `--self-check` kiểm tra khớp các số tham chiếu trước khi phân tích):

1. **Chất lượng phiên (`scripts/session_quality.py` -> `results_phase2/analysis/tables/p2_session_quality.csv`)**:
   - `load_session_typeperf()`, `summarize_window()`, `analyze_env_session()`, `analyze_jmh_session()`:
   - `S2`, `DV2`, `D3`, `JMH` đều có `0.0%` mẫu xung `< 110%` và $\le 0.27\%$ mẫu ngoài LP 10/11.
   - `S1` (168,000 hàng, `K = 1`, `0` GC) có `13.01%` (`1,345/10,335` mẫu) xung `< 110%`, tập trung toàn bộ ở `fork 4` (`52.85%`, trung vị xung `104.55%` so với `127.6%` bình thường). Theo tiêu chí $5\% < 13.01\% \le 20\%$, `S1` được đánh dấu và giữ nguyên, bổ sung phân tích độ nhạy bỏ `fork 4` (`p2_sensitivity_drop_f4.csv`).

2. **Phân tích giả thuyết (`scripts/analyze_t10.py` -> `results_phase2/analysis/tables/h_verdicts.csv`)**:
   - Dùng `boot_two_tier()` (bootstrap hai tầng: fork $\to N$, $B = 10\,000$, `seed = 20261117`).
   - **ĐẠT:**
     - `H1–H5` (`S1` ngẫu nhiên 5 thang): $c^* = 32, 32, 31, 31, 30$; $r(c^*) = 0.8443, 0.8703, 0.8873, 0.9088, 0.9165$ (mọi CI hai tầng $> 0.833$); $T_7/T_{10}$ có ý nghĩa sau Holm ở cả 5 thang (`1.0193` đến `1.0099`).
     - `H6–H9` (`S2`): `reversed` $c^* = 8, 10, 8$; `few_distinct` $c^* = 32$ cả 3 thang; `sorted` $c^* = 4096$ cả 3 thang; `nearly_sorted` $c^* = 384, 384, 512$.
     - `H10`, `H10b` (M2 trên $2^{14}, 2^{18}$): RMSE nội suy lần lượt `0.0042` và `0.0040`, `c*_M2 = 40` nằm trong vùng gần tối ưu 2%.
     - `H11` & `H12` (`P-tiếp`): `DV2` tái lập `v1` ở $k = 19..21$ (`6/6`) và khớp `P-tiếp` ở $k = 22, 23$ (`4/4`); `P-bão hòa` bị bác (`0/4`).
     - `H14`, `H16` (`D3`): `int[]` giảm thời gian mạnh hơn `Integer[]` (`r_int(c*) = 0.7122, 0.7719, 0.7852`), còn `Double[]` chênh $\le 0.0177$ so với `Integer[]`.
   - **KHÔNG ĐẠT:**
     - `H13` (đối chứng cùng cây `DV2`): `38/45` ô đạt $\le 0.01$, có `7/45` ô vượt nhẹ (tối đa `0.0334`).
     - `H15`: độ co $\Delta r_{\text{int}} = 0.0730 > 0.5 \cdot \Delta r_{\text{Integer}} = 0.0289$.
     - `H17` (`JMH` vs `Run 5`): sai lệch `|r_JMH - r_Run5|` lên tới `0.2937` ở $N = 4096, c = 7$ và đảo thứ tự ở $N = 65536, 524288$.
   - Độ nhạy bỏ `fork 4` của `S1`: không làm thay đổi phán quyết của bất kỳ giả thuyết nào.

---

### 2026-11-18 — Yêu cầu của sinh viên
Lạ nhỉ, sao JMH ra r lệch hẳn Run 5 ở N = 4096, còn int[] lại có c* chạm biên 128 và đường r(c) cứ gồ lên ở c = 64? Tôi muốn làm thêm giai đoạn 2b: JMH thiết kế yếu tố đầy đủ (tách input same/fresh, JIT profile pure/mixed, System.gc() none/gc) và đo int[] lưới mở rộng đến 256 trên 6 fork.

### 2026-11-18 — Kết quả Antigravity báo lại (tóm tắt)
Đã cập nhật mã nguồn cho giai đoạn 2b (chẩn đoán):

1. **`jmh/src/bench/MergeCutoffBenchmarkV2.java`** & **`jmh/src/MergeCutoffBridge.java`**:
   - Thiết kế yếu tố $2 \times 2 \times 2$ (`input = {same, fresh}`, `profile = {pure, mixed}`, `reset = {none, gc}`) $\times 3\,N \times 4\,\text{cutoff}$.
   - `fresh` tạo bể hoán vị tham chiếu qua `knuthShuffleRefs()` dùng chung một bộ đối tượng `Integer` (cỡ bể `poolSizeFor(n)` tối đa 64); `mixed` gọi `sorter.mixedWarmup(11)` tái hiện pha warm-up `FULL_GRID` của `Benchmark.java`; `gc` gọi `System.gc()` ở đầu `@Setup(Level.Invocation)`.
2. **`src/Benchmark.java`** & **`src/CorrectnessTest.java`**:
   - Bổ sung `INT_EXT_GRID` (43 giá trị `1..32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 256`) và nhóm kiểm thử `17` trong `CorrectnessTest`.
3. **Script chạy & phân tích**:
   - Tạo `scripts/run_jmh_v2.bat`, `scripts/run_int_ext.bat`, `scripts/extract_t11_refs.py`, `scripts/analyze_t12.py` (`load_jmh_json_files()`, `boot_jmh_score()`, `run_phase2b_analysis()`), và mở rộng `run_phase2b()` trong `scripts/session_quality.py`.

---

### 2026-11-18 — Yêu cầu của sinh viên
Xong rồi! Hai lần chạy JMH v2 đầu bị Windows Power Throttling hạ xung ~80% nên tôi bỏ qua (results_jmh_v2_rejected_lowclock*), tắt Power Throttling cho java.exe chạy lại lần 3 thì xung phẳng ~128% rồi, với chạy xong results_int_ext 6 fork luôn. Giờ chạy phân tích 2b giúp tôi nhé.

### 2026-11-18 — Kết quả Antigravity báo lại (tóm tắt)
Đã chạy `scripts/session_quality.py` và `scripts/analyze_t12.py`, kết quả lưu trong `results_phase2b/analysis/tables/`:

1. **Chất lượng phiên (`p2b_session_quality.csv`)**:
   - Xác nhận `S6_run1` (`54.27%` xung $< 110\%$) và `S6_run2` (`77.27%`) bị loại; `S6_run3` chỉ có `0.025%` (`1/3,968` mẫu) xung `< 110%`, trung vị `128.74%` (HỢP LỆ); `S7` (`int[]` lưới mở rộng, `154,800` hàng) có `0.00%` xung $< 110\%$ và `0.00%` ngoài LP 10/11 (HỢP LỆ).
2. **Phán quyết giai đoạn 2b (`h2b_verdicts.csv`)**:
   - **Chẩn đoán JMH:** `J2` ĐẠT (chuyển `same` $\to$ `fresh` ở $N = 4096$ làm tăng `r` thêm `+0.3405 / +0.3943 / +0.3694`, Score tăng `1.9898×`), `J6` ĐẠT (bật `System.gc()` trước khi đo ở $N = 4096, c = 30$ làm Score tăng `1.7861×`). Kết cục `J2xJ6`: cả trạng thái dữ liệu (`same/fresh`) lẫn trạng thái bộ nhớ (`none/gc`) cùng góp phần tạo nên khác biệt giữa JMH và `Benchmark.java`. `J1, J3, J4, J5, J7` KHÔNG ĐẠT (dù `same+mixed+gc` cho thứ tự `30 < 10 < 7 < 1` đúng ở cả `3/3` mức $N$).
   - **Kiểm định `int[]` (`S7`):** cả 5 giả thuyết `I1, I1b, I2, I3, I4` đều ĐẠT:
     - $c^* = 128, 112, 64$ với $r_{\text{int}}(c^*) = 0.6972$ ($2^{12}$), $0.7661$ ($2^{16}$), $0.7832$ ($2^{19}$), mọi cận trên CI hai tầng đều $< 0.833$ và $r^* < 0.80$ (đạt mốc "khoảng 20%" của bài giảng).
     - Dạng gồ lặp lại ở $2^{12}$ và $2^{16}$: $r(64) > r(32)$ và $r(96) < r(64)$ (`0.7074, 0.7705, 0.7154` tại $2^{12}$; `0.7746, 0.8250, 0.7814` tại $2^{16}$).

---

## Phiên 6: Sinh đồ thị, bảng LaTeX và dựng khung báo cáo

### 2026-11-19 — Yêu cầu của sinh viên
Giờ sinh toàn bộ hình vẽ, bảng .tex và khung report/main.tex để tôi hoàn thiện báo cáo LaTeX nhé. Nhớ đừng viết văn xuôi vào chỗ người dùng tự viết, với kiểm tra lại đối chiếu số liệu từ CSV.

### 2026-11-19 — Kết quả Antigravity báo lại (tóm tắt)
Đã hoàn tất phần kỹ thuật của báo cáo trong `report/`:

1. **Hình vẽ (`scripts/make_figures.py` & `scripts/make_figures_p2.py`)**:
   - Xuất bộ hình PNG/PDF nhúng font Arial kèm file `.data.csv` (đúng các điểm vẽ) và `.src.txt` (ghi nguồn và đối chiếu số liệu 0 sai lệch) vào `report/figures/`, cùng chỉ mục `report/figures/FIGURES.md`.
2. **Bảng LaTeX (`report/make_tables.py` & `report/make_tables_p2.py`)**:
   - Sinh tự động toàn bộ bảng phần chính (`t01_correctness.tex` .. `t12_memory.tex`, `ta_*.tex`) và phụ lục (`p1/*.tex`) vào `report/tables/` trực tiếp từ CSV kết quả, `git log` và `report/_check/correctness_output.txt`, có hàm `check()` kiểm tra chéo với các số tham chiếu.
3. **Khung báo cáo (`report/gen_main.py` -> `report/main.tex`)**:
   - Dựng `report/main.tex` từ dàn ý `report/report_outline_final.md` và `FIGURES.md`, chèn sẵn `\input{tables/...}`, hình, macro và giữ nguyên các chỗ đánh dấu `\bv{...}` để bạn tự viết lời văn báo cáo.
4. **Kiểm thử lại trên Windows**:
   - Tạo `scripts/run_correctness.bat` để chạy lại `CorrectnessTest` trên đúng JDK 25.0.4.1 của máy đo (`984,204` kiểm tra PASS) và cập nhật bảng `t01_correctness.tex` qua `report/make_tables_p2.py`.
