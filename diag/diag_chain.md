# Chuỗi chẩn đoán hai mức hiệu năng (Run 1–2)

    | Bước | Câu hỏi | Cách làm | Kết quả chính | Kết luận | Fact |
    |---|---|---|---|---|---|
    | 0 | Có hai mức không? | warm-up JVM, mức theo bộ dữ liệu (S§10) | run 1/2 nhảy ở vòng 5–7, giữ mức chậm; pilot chuyển qua lại | có hai mức, tỉ lệ ~1.6 | F57–F61 |
    | 1 | Do JIT? | `-XX:+PrintCompilation`, pilot và JVM chính (28/10) | không có sự kiện biên dịch quanh lúc chuyển | loại JIT | F65–F68 |
    | 2 | Có tái hiện bằng công cụ riêng? | WarmupProbe + typeperf (E0_1, E0_2) | 296/300, 900/900 vòng nhanh; 4 vòng chậm khi luồng sang nhân 0 | gợi ý: nhân 0 | F71, F72 |
    | 3 | Benchmark chậm ở đâu? | Benchmark như `run_all.bat` + typeperf (E6) | chậm = nhân 0 ở 77–79%; nhanh = nhân 5/7 ở 125–128% | cơ chế trực tiếp: xung của nhân 0 | F74–F76 |
    | 4 | Nhân 0 bị giới hạn phần cứng? | ghim nhân 0 / nhân 5 (T2) | nhân 0 lên 123.6–127% khi bị ghim; gói nguồn min 80% | không; mức 79% ≈ mức sàn của gói nguồn | F81, F82 |
    | 5 | Ghim nhân 5 có giữ mức nhanh cả lượt? | run 3 + typeperf | 100% mẫu trên nhân 5, 128–129.5%; không bước nhảy | có | F77, F78, F83 |
    | 6 | §10 cũ báo "chậm" trong run 3? | ghép typeperf + so chéo fork (D3) | không có tụt xung; f1 +8% chỉ ở 2^19; f3 dao động quanh ngưỡng | ngưỡng cũ không phù hợp; đổi §10 theo run 3 | F79, F80 |
