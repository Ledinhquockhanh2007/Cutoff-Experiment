# Phụ lục hợp đồng T11 (A1–A3): sửa thiết kế TRƯỚC khi đo

> Claude viết ngày 18/11/2026 sau khi duyệt R11, khi CHƯA có phép đo nào của giai đoạn 2b (S6, S7, S8 chưa chạy). Có hiệu lực khi commit với tiền tố `T11-PREREG-ADD:`. Phụ lục thay thế các điểm tương ứng của `T11_contract.md`; mọi điểm khác giữ nguyên.

## A1. Bể `fresh` dùng CHUNG đối tượng Integer (sửa lỗi thiết kế của §1)
Lỗi: §1 viết "đối tượng Integer của bể tạo theo thứ tự chỉ số mảng", tức mỗi hoán vị có bộ đối tượng riêng. Khi đó `fresh` đổi cùng lúc HAI thứ: lịch sử nhánh VÀ dung lượng dữ liệu (N = 4096: 64 KB đối tượng → 4 MB, vượt L2 1 MiB; N = 524 288: 8 MB → 134 MB, vượt L3 16 MiB). J2/J3 sẽ không tách được học nhánh khỏi bộ đệm.
Sửa: tạo đối tượng Integer MỘT lần từ hoán vị 0 (thứ tự tệp, như T08); hoán vị i ≥ 1 là mảng THAM CHIẾU tới chính các đối tượng đó, xáo bằng Knuth shuffle với cùng seed `20261118L*1000 + i` (cùng thứ tự giá trị như bản R11). `same` giữ nguyên (đúng T08).
Còn lại (ghi trước, không sửa được mà không đổi `same`): với i ≥ 1, địa chỉ đối tượng không tăng theo chỉ số mảng như ở hoán vị 0, nên lượt đọc đầu tiên của merge không tuần tự theo địa chỉ. Đây là khác biệt phụ, nằm trong ngưỡng 3% của J3 nếu nhỏ; nếu J3 không đạt thì đây là một cách giải thích cạnh tranh, phải nêu.

## A2. Thêm yếu tố `reset` (trạng thái nguội trước mỗi lần đo)
Cơ sở (đọc mã, không phải số đo mới): `Benchmark.measure` gọi `System.gc()` rồi `clone` trước MỖI lần sắp (K = 1). Một lần GC toàn phần chạy nhiều mã khác và có thể đẩy dữ liệu sắp ra khỏi L1/L2 và làm mất lịch sử của bộ dự đoán nhánh; JMH T08 không làm vậy. Đây là giả thuyết cạnh tranh với J2 cho chênh lệch ở N = 4096.
Thiết kế: tham số `reset ∈ {none, gc}`; `gc` = gọi `System.gc()` ở đầu `@Setup(Level.Invocation)`, TRƯỚC `clone` (đúng thứ tự của `measure`). Chỉ chạy `reset = gc` với `profile = mixed`, `input ∈ {same, fresh}` (24 cấu hình × 3 fork, chạy JMH lần hai với `-p reset=gc -p profile=mixed`, tệp JSON và console riêng). Lần chạy chính (48 cấu hình) dùng `reset = none`.
- **J6 (trạng thái nguội làm chậm đáng kể ở N nhỏ):** dưới same + mixed: Score(gc, 4096, 30) ≥ 1.5·Score(none, 4096, 30).
- **J7 (JMH tái hiện trạng thái của bộ đo tự viết thì khớp):** cấu hình same + mixed + gc thỏa tiêu chí H17 (|r − r_Run5| ≤ 0.02 ở cả 9 ô, thứ tự T(30) < T(10) < T(7) < T(1) ở cả 3 N).
- [MT] bắt buộc: E_reset = ln Score(gc) − ln Score(none) theo (input, N, c), CI bootstrap theo fork; thời gian tuyệt đối của same + mixed + gc cạnh thời gian Run 5 cùng (N, c) (khác phiên, chỉ mô tả).
Diễn giải đã chốt: J2 đạt + J6 không đạt → ủng hộ học nhánh; J6 đạt + J2 không đạt → ủng hộ trạng thái nguội; cả hai đạt → cả hai cùng góp phần (không tách được tỉ trọng ngoài bảng mô tả); cả hai không đạt → chênh lệch T08 chưa giải thích được.

## A3. Chấp nhận sai khác của R11
Pha `mixed` gọi `System.gc()` một lần cuối pha thay vì trước mỗi lần sắp: chấp nhận (yếu tố cần tái hiện là hồ sơ JIT; thứ tự CUTOFF đã được chứng minh trùng 35/35 ở 2 vòng đầu).

## Thời gian
S6 thành ~1.5 giờ (48 + 24 cấu hình × 3 fork, cộng thời gian GC trong Setup).
