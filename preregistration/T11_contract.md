# Hợp đồng đăng ký trước, giai đoạn 2b (T11): chẩn đoán JMH, int[] lưới mở rộng, bộ đếm phần cứng

> Viết bởi Claude (điều phối) ngày 18/11/2026, sau R10, TRƯỚC mọi phép đo của giai đoạn 2b. Có hiệu lực khi commit với tiền tố `T11-PREREG:` kèm `T11_hypotheses.csv` và `T11_reference_values.csv`. Sau commit đó không đổi giả thuyết, ngưỡng, quy tắc quyết định hay cách tính. Phân tích ngoài hợp đồng gắn nhãn [KP].
>
> Lý do (từ R10, đã được Claude tính lại độc lập): (1) H17 KHÔNG ĐẠT: JMH đo nhanh gấp ~2 lần bộ đo tự viết ở N = 4096 (c = 30: 213 µs so với 424 µs), r lệch tới 0.29, nhưng thời gian gần nhau ở N lớn; thứ tự T(30) < T(10) < T(7) < T(1) sai ở 65536 và 524288. (2) int[] (D3): đường r(c) gồ ghề, lệch mạnh giữa 3 fork, c* nằm ở biên lưới 128 ở 2^12 và 2^16; "int[] đạt 20%" mới là [KP]. (3) H15 KHÔNG ĐẠT dựa trên r_int(c*) ở một đường cong bất ổn với 3 fork.
> Những giả thuyết dưới đây là giả thuyết, không phải giải thích đã được chứng minh. Mọi kết quả, đạt hay không, đều vào báo cáo.

## 0. Quy ước chung
Giữ nguyên §0 của `T09_contract.md` (máy, JDK 25.0.4.1, cờ `-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch`, ghim nhân 5 bằng `start "bench" /affinity C00 /wait` từ đầu phiên, K = 1 cho bộ đo tự viết, cắm sạc, gói nguồn Balanced như cũ, tắt Tailscale/WARP/Radmin VPN, tạm dừng Windows Update, typeperf suốt phiên, quy tắc đánh dấu 5% / chạy lại 20%). Bootstrap: seed 20261118, B = 10 000. Định nghĩa r, c*, tập gần tối ưu, bootstrap hai tầng (rút fork rồi rút N, c* cố định) như mục 2 của `handoff/tasks/T10_analysis.md`.
Số tham chiếu từ giai đoạn 2 (không đo lại) do script trích ra `T11_reference_values.csv` từ `results_phase2/analysis/tables/` (p2_jmh.csv, p2_best.csv, p2_d3_*.csv), in cạnh số của Claude ở mục 5.

## 1. JMH v2: thiết kế giai thừa 2 × 2 (phiên S6)
Cùng lớp benchmark T08 (AverageTime, 3 fork, warm-up 5 × 1 s, đo 10 × 1 s, cùng cờ JVM qua `-jvmArgs`, ghim nhân 5), random, N ∈ {4096, 65536, 524288} (cùng tệp `data_run5/random/` như T08), c ∈ {1, 7, 10, 30}, thêm hai tham số:
- `input`: **same** = mỗi lần gọi sắp bản sao của CÙNG một mảng gốc (đúng T08). **fresh** = một bể P hoán vị khác nhau của cùng tập giá trị (hoán vị 0 = thứ tự trong tệp; hoán vị i ≥ 1 = Knuth shuffle với `new java.util.Random(20261118L * 1000 + i)`), P = min(64, 2^23 / N) (64, 64, 16); lần gọi thứ j sắp bản sao của hoán vị j mod P. Đối tượng Integer của bể tạo ở `@Setup(Level.Trial)`, theo thứ tự chỉ số mảng (giống T08).
- `profile`: **pure** = JVM chỉ từng chạy CUTOFF của cấu hình (đúng T08). **mixed** = trong `@Setup(Level.Trial)`, TRƯỚC warm-up của JMH, chạy lại đúng pha warm-up JVM của `Benchmark.java` (random N = 65 536 seed 777, mỗi vòng sắp với cả 35 CUTOFF của `FULL_GRID` theo thứ tự xáo như harness, 11 vòng cố định) để hồ sơ JIT giống bộ đo tự viết.
48 cấu hình × 3 fork. Lưu `-rf json` (có dữ liệu thô từng vòng đo của từng fork) và log console bằng `-o`. Đại lượng: Score(cond, N, c) = trung bình của 30 vòng đo; r(cond, N, c) = Score(c)/Score(1). CI của r: bootstrap trên 3 fork (rút fork có hoàn lại, lấy trung bình 10 vòng mỗi fork), B = 10 000.

Giả thuyết:
- **J1 (JMH tự lặp lại):** cấu hình same + pure: |r − r_T08| ≤ 0.03 ở cả 9 ô (N × c ∈ {7, 10, 30}). Không đạt nghĩa là chính kết quả T08 không ổn định.
- **J2 (học nhánh khi lặp cùng đầu vào, N nhỏ):** dưới pure, ở N = 4096: r(fresh, c) − r(same, c) ≥ 0.10 với cả c ∈ {7, 10, 30}, VÀ Score(fresh, 4096, 30) ≥ 1.30·Score(same, 4096, 30). Cơ sở: một lần sắp 4096 phần tử có khoảng 5·10^4 nhánh so sánh; nếu cùng hoán vị được sắp hàng nghìn lần liên tiếp, bộ dự đoán nhánh có thể nhớ phần lớn kết quả, làm thời gian JMH thấp hơn thời gian sắp một đầu vào "mới". Với c lớn, merge ít hơn nhưng insertion sort nhiều nhánh khó đoán hơn; giả thuyết dự đoán lợi ích của c bị phóng đại khi nhánh được học.
- **J3 (không học được ở N lớn):** dưới pure, ở N = 524 288: |ln Score(fresh, c) − ln Score(same, c)| ≤ 0.03 với cả 4 c.
- **J4 (hồ sơ JIT):** dưới fresh, ở N ∈ {65536, 524288}: thứ tự Score(30) < Score(10) < Score(7) < Score(1) đúng ở mixed (cả 2 N). (Không dự đoán gì cho pure.)
- **J5 (JMH cấu hình như bộ đo tự viết thì khớp):** cấu hình fresh + mixed thỏa đúng tiêu chí H17: |r − r_Run5(N, c)| ≤ 0.02 ở cả 9 ô và thứ tự T(30) < T(10) < T(7) < T(1) ở cả 3 N. r_Run5 lấy từ `p2_jmh.csv` (cột `r_run5`).
Bảng mô tả [MT] bắt buộc: hiệu ứng đầu vào E_in = ln Score(fresh) − ln Score(same) và hiệu ứng hồ sơ E_prof = ln Score(mixed) − ln Score(pure) cho mọi (N, c, mức của yếu tố kia), kèm CI bootstrap theo fork.

## 2. int[] lưới mở rộng (phiên S7)
Random, 3 thang {2^12, 2^16, 2^19}, cùng N và dữ liệu `data_run5/` như D3; chỉ `--key int` (`MergeCutoffInt`, không sửa); **6 fork**; lưới 43 CUTOFF = {1..32} ∪ {40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 256}; trial và warm-up như D3. Kết quả: `results_int_ext/`.
- **I1 ("khoảng 20%" với khóa nguyên thủy, xác nhận [KP] của D3):** cận trên CI hai tầng 95% của r_int(c*) < 0.833 ở cả 3 thang.
- **I1b (phụ):** ước lượng điểm r_int(c*) < 0.80 ở cả 3 thang (D3: 0.712 / 0.772 / 0.785).
- **I2 (cực tiểu nằm trong lưới):** c*_int ≤ 192 ở cả 3 thang.
- **I3 (dạng "gồ" của D3 có lặp lại không):** ở 2^12 và 2^16: r_int(64) > r_int(32) VÀ r_int(96) < r_int(64) (ước lượng điểm, 6 fork). Không đạt = dạng gồ ở D3 nhiều khả năng là nhiễu 3 fork.
- **I4 (lặp lại phát hiện của H15 theo chiều ngược):** Δr_int = r_int(c*, 2^19) − r_int(c*, 2^12) ≥ 0.5·Δr_Integer, với Δr_Integer = r(c*, 2^19) − r(c*, 2^12) của Integer[] trong Run 5 S1 (0.9165 − 0.8443, đọc từ `p2_best.csv`). Đạt = lợi ích của int[] cũng co lại đáng kể theo N, nhất quán với kết luận H15 rằng co lại không chỉ đến từ bộ nhớ của đối tượng Integer.
- [MT] bắt buộc: SD giữa 6 fork của r_int theo (thang, c); so với SD giữa 3 fork của D3 cùng ô.

## 3. D1: bộ đếm phần cứng (phiên S8, CÓ ĐIỀU KIỆN)
Chỉ thực hiện nếu AMD uProf (CLI) cài được và đọc được bộ đếm nhánh của lõi 5 trên máy (kiểm ở T11-code bằng một lần chạy thử không xem số đo nhánh của thí nghiệm). Nếu không: D1 hủy, ghi "không thực hiện được" trong báo cáo, KHÔNG thay bằng cách đo khác. Quyết định hủy được ghi trong R11, trước khi có số liệu nào của S6–S7 được phân tích.
Thiết kế: chương trình `BranchProbe` (gọi `MergeCutoff.sort`, không sửa nó) chạy trong một JVM ghim nhân 5, cùng cờ JVM, random, N ∈ {4096, 524288}, c ∈ {1, 30}, input ∈ {same, fresh} (như §1), sau warm-up 20 s mỗi cấu hình đo R lần sắp liên tiếp (R = 20 000 với 4096; 40 với 524288); đối chứng "chỉ sao chép" (clone, không sắp) cùng số lần để trừ nền. Đại lượng: số nhánh dự đoán sai trên MỘT lần sắp sau khi trừ nền, M(input, N, c), 3 lần lặp mỗi cấu hình, lấy trung vị.
- **B1:** M(same, 4096, 30) ≤ 0.5·M(fresh, 4096, 30) và M(same, 4096, 1) ≤ 0.5·M(fresh, 4096, 1).
- **B2:** M(same, 524288, c) ≥ 0.8·M(fresh, 524288, c) với c ∈ {1, 30}.
J2 đạt cùng B1 đạt: nhất quán với giả thuyết học nhánh. J2 đạt mà B1 không: chênh lệch thời gian không đi kèm chênh lệch dự đoán nhánh; giả thuyết học nhánh không được ủng hộ.

## 4. Thứ tự phiên và thời gian dự kiến
S6 JMH v2 (~1 giờ), S7 int[] mở rộng (~1 giờ), S8 D1 (~15 phút, có điều kiện). Mỗi phiên một .bat, có danh sách kiểm tra đầu phiên, typeperf song song, ghi thời gian thực. Lưu ý đã biết trước: JMH chạy các cấu hình theo thứ tự tham số cố định (không xáo); trôi nhiệt theo thời gian có thể lẫn với yếu tố đứng sau trong thứ tự. Ghi nhận ở mục Hạn chế; typeperf dùng để mô tả.

## 5. Tệp phải commit cùng hợp đồng
- `T11_hypotheses.csv`: id (J1–J5, I1, I1b, I2–I4, B1, B2), mô tả ngắn, đại lượng, quy tắc quyết định, ngưỡng.
- `T11_reference_values.csv`: r_T08(N, c) và r_Run5(N, c) cho 9 ô (từ `p2_jmh.csv`); r(c*) Integer S1 ở 2^12 và 2^19 và Δr_Integer (từ `p2_best.csv`); r_int(c*), c*_int ở D3 (từ `p2_d3_best.csv`). Số tham chiếu của Claude để đối chiếu (quy tắc A, 4 chữ số): r_T08 = 0.6144/0.5885/0.5660 (4096), 0.9868/0.9496/0.9727 (65536), 0.9782/0.9364/0.9904 (524288); r_Run5 = 0.9081/0.8737/0.8421, 0.9344/0.9112/0.8868, 0.9585/0.9406/0.9212 (c = 7/10/30); Δr_Integer = 0.0722; D3 r_int(c*) = 0.7122/0.7719/0.7852, c*_int = 128/128/64.
