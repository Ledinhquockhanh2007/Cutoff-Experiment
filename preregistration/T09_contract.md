# Hợp đồng đăng ký trước, giai đoạn 2 (T09): thí nghiệm xác nhận

> Viết bởi Claude (điều phối) ngày 17/11/2026, TRƯỚC khi có bất kỳ phép đo nào của giai đoạn 2. Có hiệu lực khi được commit với tiền tố `T09-PREREG:` cùng các tệp dự đoán số (mục 9). Sau commit đó: không đổi giả thuyết, ngưỡng, quy tắc quyết định hay cách tính. Mọi phân tích ngoài hợp đồng được gắn nhãn [KP] (khám phá).
>
> Mục đích: biến các điểm yếu khắc phục được của giai đoạn 1 thành kết quả đã kiểm định: (a) chọn ghim nhân và lượt chính sau khi xem dữ liệu; (b) CI không tính biến thiên giữa JVM; (c) phân bố khác chỉ ở 2^16; (d) lưới CUTOFF dừng ở 64; (e) ngưỡng doubling ≈ 1 SE; (f) mô hình chi phí chỉ là khám phá; (g) "vì sao không đạt 20%" và "vì sao lợi ích giảm theo N" chỉ là giả thuyết; (h) bộ đo tự viết chưa được đối chiếu.

## 0. Quy ước chung (áp cho mọi phiên)

- Máy, JDK, cờ JVM như giai đoạn 1: `-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch` (Doubling v2 dùng `-Xms4g -Xmx4g` vì 2^24, ghi rõ trong env), Microsoft JDK 25.0.4.1, ghim nhân vật lý 5 bằng `start "bench" /affinity C00 /wait` TỪ ĐẦU mọi phiên, K = 1, loại lần đo có GC, cắm sạc, cùng gói nguồn như run 3/Run 4 (Balanced, PROCTHROTTLEMIN AC = 80%, nguồn `results_final/env/`), đóng ứng dụng khác, tắt các dịch vụ mạng nền (Tailscale, Cloudflare WARP, Radmin VPN), tạm dừng Windows Update. Danh sách kiểm này được in ra đầu mỗi tệp .bat và người dùng xác nhận bằng một phím trước khi đo.
- `typeperf` ghi xung và độ bận theo LP suốt mỗi phiên (như run 3), để kiểm rằng phép đo nằm trên nhân 5 ở mức xung cao. Phiên nào có > 5% mẫu luồng đo không nằm trên LP 10/11 hoặc xung < 110% → phiên đó bị đánh dấu và báo cáo (không tự ý loại; quyết định loại phải theo quy tắc này: loại nếu > 20% mẫu, chạy lại phiên đó).
- Dữ liệu MỚI cho Run 5: seed = 10^7·distId + N + 5·10^8 (khác mọi seed cũ); sorted/reversed không phụ thuộc seed. Các N theo công thức thang cũ N_j = round(S·2^(j/24)), j = 0..23.
- r(N, c) = T(c)/T(1) ghép cặp trong cùng (fork, bộ dữ liệu, trial); trung bình nhân trong từng N rồi trên các N (như giai đoạn 1). c* = argmin của r gộp theo thang; "gần tối ưu" = r ≤ 1.02·r(c*).
- **CI chính của giai đoạn 2 là bootstrap hai tầng**: lấy lại fork (có hoàn lại), rồi lấy lại N trong thang (có hoàn lại), B = 10 000, seed 20261117. CI một tầng theo N được báo cáo thêm để so với giai đoạn 1.
- Mọi kiểm định đều báo cáo cả khi đạt lẫn không đạt. Không đo lại, không đổi cách tính để "cứu" một giả thuyết. Một phiên chỉ được chạy lại theo quy tắc typeperf ở trên hoặc khi có lỗi kỹ thuật được ghi lại (crash, mất điện), và phải chạy lại TOÀN BỘ phiên đó.

## 1. Run 5: lặp lại thí nghiệm chính ở dạng xác nhận (dữ liệu chính của báo cáo)

Thiết kế: random ở 5 thang S ∈ {2^12, 2^14, 2^16, 2^18, 2^19} (2^14 và 2^18 là thang MỚI); sorted, reversed, nearly_sorted, few_distinct ở 3 thang {2^12, 2^16, 2^19}; 24 N mỗi thang; **5 fork**. Lưới: random 35 CUTOFF (1..32, 40, 48, 64); sorted và nearly_sorted: SPARSE ∪ {96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 4096}; reversed và few_distinct: SPARSE ∪ {96, 128} (SPARSE = {1, 2, 4, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64}). Số trial: random 10 (S ≤ 2^16) / 5 (S ≥ 2^18); phân bố khác 5. Warm-up như giai đoạn 1.

Giả thuyết (mỗi giả thuyết một quy tắc quyết định; "đạt" = thỏa ở MỌI thang được nêu):
- **H1 (vùng tối ưu, random, 5 thang):** c* ∈ [17, 48] và tập gần tối ưu chứa {24, 25, ..., 32}.
- **H2 (10 nhanh hơn 7, random, 5 thang):** T7/T10 > 1 với CI hai tầng 95% có cận dưới > 1 (Holm trên 5 thang, mức 0.05).
- **H3 (lặp lại độ lớn, random):** |r_Run5(c*) − r_GĐ1(c*)| ≤ 0.015 ở 2^12, 2^16, 2^19, với r_GĐ1 = 0.848 / 0.888 / 0.918 (results_final).
- **H4 (lợi ích giảm theo N):** r(c*) tăng nghiêm ngặt theo thang 2^12 < 2^16 < 2^19 với CI hai tầng không chồng nhau giữa các thang liền kề trong dãy này; và ở 5 thang, mọi bước tăng âm (nếu có) có độ lớn ≤ 0.005.
- **H5 ("khoảng 20%"):** r(c*) > 0.833 ở cả 5 thang, tức không đạt 1.2× (và vì thế cũng không đạt cách đọc r = 0.80).
- **H6 (reversed):** c* ∈ [6, 16] ở 3 thang. Cơ sở: lá đảo ngược có ~c²/2 nghịch thế, gấp đôi lá ngẫu nhiên, nên c* nhỏ hơn random khoảng hai lần trở lên.
- **H7 (few_distinct):** c* ∈ [17, 48] ở 3 thang (10 giá trị: số nghịch thế trong lá ≈ 0.9 lần random).
- **H8 (sorted, D4):** r(c) không tăng theo c trên toàn lưới (cho phép một bước tăng ≤ 0.01 do nhiễu) và c* là giá trị lớn nhất của lưới (4096) ở cả 3 thang. Cơ sở: insertion sort trên lá đã sắp tốn c − 1 so sánh, 0 đổi chỗ, nên tổng chi phí insertion ~N bất kể c, còn mỗi lần gấp đôi c bỏ thêm một tầng merge.
- **H9 (nearly_sorted, D4):** có cực tiểu bên trong: c* ∈ {128, 192, 256, 384, 512, 768, 1024} (không ở biên 4096) ở cả 3 thang. Suy dẫn (trước dữ liệu): N/100 lần đổi chỗ hai vị trí ngẫu nhiên đặt ≈ c/50 phần tử lạc chỗ vào mỗi lá dài c, mỗi phần tử gây ≈ c/2 nghịch thế, tức chi phí insertion thêm ≈ β·c/100 mỗi phần tử; mỗi lần gấp đôi c tiết kiệm ≈ w mỗi phần tử (một tầng merge). Cực tiểu tại c* ≈ 100·w/(β·ln 2); với β ≈ 3.3 ns và w trong khoảng 3–10 ns: c* ≈ 130–440. Khoảng đăng ký được nới thành [128, 1024].

## 2. Dự đoán của mô hình M2 ở thang mới (biến mô hình chi phí thành mô hình đã kiểm định)

- Hệ số ĐÓNG BĂNG từ `results_final/analysis_v2/tables/cost_model_M2_coef.csv`: w1, w2, w3, β, α12, α16, α19.
- α cho thang mới bằng nội suy tuyến tính theo k = lg S (đúng quy tắc P3c đã đăng ký ở T04): α14 = α12 + (α16 − α12)·(2/4); α18 = α16 + (α19 − α16)·(2/3). Không dùng bất kỳ dữ liệu nào của Run 5.
- Dự đoán r̂(N, c) = T̂(c)/T̂(1) cho từng N của thang 2^14 và 2^18 và 35 CUTOFF, tính trên cây đệ quy thật (đặc trưng chính xác như T03a), rồi trung bình nhân theo N như số đo. Antigravity tính và commit vào `T09_predictions_m2.csv` TRƯỚC khi đo.
- **H10 (độ chính xác M2, xác nhận):** ở mỗi thang 2^14 và 2^18: RMSE(r̂ − r) trên 35 CUTOFF ≤ 0.012, VÀ c*_M2 thuộc tập gần tối ưu đo được.
- **H10b (phụ, cùng đăng ký):** biến thể α hiệu chỉnh từ hàng c = 1 của chính thang (giao thức LOSO cũ) cũng phải đạt RMSE ≤ 0.012. Nếu H10 không đạt nhưng H10b đạt, kết luận: M2 dự đoán được r khi biết chi phí ở c = 1, nhưng α không nội suy được.

## 3. Doubling v2 (sửa ngưỡng ≈ 1 SE, mở rộng tới 2^24)

Thiết kế: random, N = 2^k, k = 10..24, cùng 9 CUTOFF {1, 4, 7, 8, 10, 16, 30, 32, 64}; **5 fork**; trial: 10 (k ≤ 16), 5 (17 ≤ k ≤ 20), 3 (21 ≤ k ≤ 24); dữ liệu 2^10..2^22 dùng lại `data_doubling/` (cùng seed), thêm 2^23, 2^24 theo cùng công thức seed. Heap `-Xms4g -Xmx4g`.
SE_k = SD giữa 5 fork của ln R_k (fork-level) / √5. Ngưỡng của mọi phép thử dưới đây là **3·SE_k** (khác giai đoạn 1: 1.5% cố định ≈ 1 SE).
- **H11 (lặp lại doubling v1):** với k = 19, 20, 21 và c ∈ {1, 30}: |ln R̄_k(v2) − ln R̄_k(v1)| ≤ 3·√(SE_k(v1)² + SE_k(v2)²), SE_k(v1) lấy từ bảng A1z của giai đoạn 1.
- **H12 (ngoại suy tới 2^24: hai dự đoán cạnh tranh, k = 22 và 23, tức R của 2^22 → 2^23 và 2^23 → 2^24):**
  - P-tiếp: số mũ đoạn 19–22 của v1 tiếp diễn: ln R = b·ln 2 với b = 1.202 (c = 1), 1.213 (c = 30).
  - P-bão hòa: chi phí trên mỗi phần tử ngừng tăng: R = 2(k+1)/k (2.0909 ở k = 22; 2.0870 ở k = 23).
  - Một dự đoán "đạt" nếu |ln R̄_k − ln R̂_k| ≤ 3·SE_k ở cả k = 22 và 23, với cả c = 1 và c = 30. Báo cáo kết quả của cả hai (có thể cả hai không đạt; khi đó T(N) ở dải này nằm giữa hai mô hình).
- **H13 (kiểm soát cùng cây):** ở mọi k, các cặp (4, 7), (8, 10), (16, 30) có |chênh trung bình| ≤ 1% (như v1).

## 4. D3: kiểu khóa (kiểm giả thuyết "vì sao không đạt 20%" và "vì sao lợi ích giảm theo N")

Thiết kế: random, 3 thang {2^12, 2^16, 2^19}, cùng N và dữ liệu MỚI của Run 5, lưới 35 CUTOFF ∪ {96, 128}; 3 fork; 3 kiểu khóa:
- `Integer[]` (đối chứng trong cùng phiên, cùng `MergeCutoff`);
- `Double[]` (cùng `MergeCutoff`, giá trị = (double) của số nguyên, đối tượng phân biệt);
- `int[]` với `MergeCutoffInt` (người dùng tự viết, chép đúng thuật toán của `MergeCutoff`, chỉ đổi kiểu; kiểm bằng CorrectnessTest mở rộng: cùng cây đệ quy, cùng số so sánh với bản Integer trên cùng dữ liệu).
Bộ nhớ dữ liệu hoạt động của `int[]` là 8N byte (a + aux), so với 24N với Integer (T05).
- **H14:** r_int(c*) < r_Integer(c*) ở cả 3 thang (cận trên CI của hiệu < 0), và c*_int ≥ c*_Integer ở cả 3 thang. Cơ sở: với khóa rẻ (không gián tiếp qua tham chiếu, không gọi `compareTo`), chi phí phụ của đệ quy và copy chiếm tỉ trọng lớn hơn.
- **H15 (cơ chế bộ nhớ của việc lợi ích giảm theo N):** độ co lại của lợi ích từ 2^12 đến 2^19 với int[] nhỏ hơn một nửa của Integer[] đo trong cùng phiên: [r_int(c*, 2^19) − r_int(c*, 2^12)] < 0.5·[r_Integer(c*, 2^19) − r_Integer(c*, 2^12)].
- **H16:** |r_Double(c*) − r_Integer(c*)| ≤ 0.02 ở cả 3 thang (cùng gián tiếp qua tham chiếu).
- Câu hỏi khám phá (KHÔNG có dự đoán): int[] có đạt "khoảng 20%" ở thang nào không.

## 5. T08: kiểm chứng chéo bộ đo bằng JMH

JMH (jmh-core, chế độ AverageTime, `@Setup(Level.Invocation)` sao chép mảng gốc, 3 fork, warm-up 5 × 1 s, đo 10 × 1 s), cùng cờ JVM, ghim nhân 5, random, N ∈ {4096, 65536, 524288} (dữ liệu Run 5: N là phần tử đầu j = 0 của mỗi thang), c ∈ {1, 7, 10, 30}.
- **H17:** |r_JMH(N, c) − r_Run5(N, c)| ≤ 0.02 cho mọi (N, c ∈ {7, 10, 30}), với r_Run5(N, c) là r của đúng N đó (không phải trung bình thang); và thứ tự T(30) < T(10) < T(7) < T(1) đúng ở cả 3 N trong JMH.

## 6. D1: bộ đếm phần cứng
Không thuộc hợp đồng này (công cụ AMD uProf chưa được kiểm trên máy); sẽ có hợp đồng riêng T11 trước khi đo. Mọi kết quả D1 trước hợp đồng đó là [KP].

## 7. Thứ tự phiên và ước lượng thời gian (Antigravity tính lại chính xác ở T09-code)
S1 Run 5 random 5 thang (~3 giờ), S2 Run 5 phân bố khác (~2–2.5 giờ), S3 Doubling v2 (~1 giờ), S4 D3 (~2 giờ), S5 JMH (~0.5 giờ). Mỗi phiên một tệp .bat riêng, chạy được `--resume`, ghi thời gian thực vào env.

## 8. Ngoài phạm vi, nói trước
Chỉ một máy (người dùng không có máy thứ hai): giữ ở mục Hạn chế. Mức tuyệt đối giữa các phiên lệch tới ±8%: chỉ so tỉ số trong cùng phiên; so sánh giữa phiên (H3, H11) dùng tỉ số.

## 9. Tệp dự đoán số phải commit cùng hợp đồng (do Antigravity tính bằng script, Claude kiểm trước khi đo)
- `T09_predictions_m2.csv`: scale, N, cutoff, r_hat_interp, (cột hiệu chỉnh để trống, điền sau khi có hàng c = 1), c*_M2 theo thang.
- `T09_predictions_doubling_v2.csv`: k, cutoff, lnR_P_tiep, lnR_P_baohoa, lnR_v1, SE_v1.
- `T09_hypotheses.csv`: id, mô tả ngắn, đại lượng, quy tắc quyết định, ngưỡng (một hàng cho mỗi H1–H17).
