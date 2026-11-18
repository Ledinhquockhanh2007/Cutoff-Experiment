# Phiên S6 (JMH v2) lần 2 — BỊ LOẠI theo §0 hợp đồng
- Quyết định chỉ dựa trên typeperf (chưa mở Score/r).
- 19:25–20:35 ngày 18/11: xung LP bận của nhân 5 ≈ 80% gần như suốt phiên; chỉ 20:09–20:15 (ngay sau khi lượt 2 mở cửa sổ mới) ở 127%. Các LP rảnh giữ mức bình thường (≈ 72–79%), độ bận tổng ≈ 6.5% → giới hạn chỉ ở nhân đo, không có tải cạnh tranh.
- 77.27% mẫu (n = 4 139) có xung < 110% > 20% → loại, chạy lại toàn phiên. Ngoài LP 10/11: 3.12%.
- Giả thuyết (chưa kiểm): Windows Power Throttling/EcoQoS áp lên các JVM con không có cửa sổ do JMH tạo (fork), nhất là khi cửa sổ không ở tiền cảnh hoặc màn hình tắt; bộ đo tự viết (một JVM có cửa sổ) không bị ở mọi phiên.
