================================================================================
MERGE_README.txt - NGUỒN GỐC VÀ QUY ƯỚC DỮ LIỆU RESULTS_FINAL
================================================================================

1. MỤC ĐÍCH VÀ NGUYÊN DO
  Thí nghiệm KDiag (results_kdiag/) xác nhận việc đo theo lô K > 1 (TARGET_BATCH_NS = 2ms)
  làm sai lệch có hệ thống thời gian một lần sắp ở thang 2^12 (N = 4096..7959) trong Run 3,
  làm giảm thời gian tới 18.3% và thổi phồng mức giảm r của CUTOFF tối ưu khoảng 2.4 điểm %.
  Các thang 2^16 và 2^19 có K = 1 từ thiết kế nên hoàn toàn sạch.
  Run 4 đo lại toàn bộ 24 N của thang 2^12 (random) với cờ --fixed-k 1 (K = 1 cho mọi lần đo),
  ghim nhân vật lý 5 (/affinity C00) giống hệt Run 3.
  Thư mục results_final/ là kết quả hợp nhất chuẩn mực cho toàn bộ báo cáo chính.

2. NGUỒN TỪNG PHẦN TRONG RESULTS_FINAL
  - raw_fork{1,2,3}.csv:
      * Thang 2^12 random (8400 hàng/fork): lấy từ results_run4/raw_fork*.csv (K = 1).
      * Thang 2^16, 2^19 random và 4 phân bố khác (18840 hàng/fork): lấy từ results_run3/raw_fork*.csv.
      * Tổng cộng: 27240 hàng/fork.
  - warmup_fork{1,2,3}.csv:
      * Warmup bộ dữ liệu 2^12 random: lấy từ results_run4/warmup_fork*.csv.
      * Warmup JVM và các bộ dữ liệu khác: lấy từ results_run3/warmup_fork*.csv.
  - counts.csv:
      * Lấy nguyên văn từ results_run3/counts.csv (số đếm phép so sánh, truy cập, đổi chỗ
        và độ dài merge chỉ phụ thuộc thuật toán và dữ liệu đầu vào, không phụ thuộc K hay JVM).
  - env_fork{1,2,3}.txt:
      * Lấy nguyên văn từ results_run3/env_fork*.txt (môi trường JVM của lượt chạy chính 75 phút).
      * Run 4 chạy trên cùng máy, cùng JDK (Microsoft 25.0.4.1), cùng cờ JVM và cùng ghim nhân 5.

3. QUY ƯỚC QUAN TRỌNG VỀ FORK VÀ HỆ QUẢ PHÂN TÍCH
  QUY ƯỚC: 'Fork f ở 2^12 là một JVM KHÁC với fork f ở các thang khác (2^16, 2^19)'.
  Hệ quả đối với các phân tích trong scripts/analyze.py:
    a) Tỉ số r = T(c)/T(1) và RQ1 (rq1_best_cutoff.csv, r_by_cutoff.csv):
       HOÀN TOÀN HỢP LỆ VÀ CHUẨN XÁC, vì r được ghép cặp trong cùng (fork, bộ dữ liệu, trial).
       Việc 2^12 đo ở một JVM riêng không ảnh hưởng gì tới việc ghép cặp nội bộ 2^12.
    b) Bảng theo từng JVM (per_jvm.csv, per_jvm_summary.csv):
       Khi so sánh xuyên thang theo cùng fork f, cần nhớ rằng thời gian tuyệt đối của thang 2^12
       được thu thập từ JVM Run 4, trong khi 2^16 và 2^19 từ JVM Run 3.
    c) Phân tích trôi dạt (drift.csv, fig14_drift.png):
       Hồi quy trôi dạt theo run_order trong fork: hàng 2^12 đến từ phiên JVM của Run 4
       (trục thời gian riêng).
    d) Tóm tắt môi trường (env_summary.csv):
       Các thông số thời gian bắt đầu, kết thúc, tổng thời gian và RAM phản ánh JVM của Run 3.
    e) Mô hình lũy thừa T = a N^b fitted trên toàn bộ 72 N:
       Khớp đa thang (72 N) ghép 24 N của Run 4 với 48 N của Run 3. Do cùng ghim nhân 5 ở xung
       ~129% và mức xung ổn định, mô hình gộp trên 3 fork là nhất quán.

4. SHA256 CÁC TỆP NGUỒN
  e8161b9178ab8f27146dedab95f5e0b4fae3d0a53b8f82101bbb0f4d523e7f58  run3/counts.csv
  deef4964ad09ade4c384ef1448fe1aab2c91f0fa368ee0523722072e406fc9ae  run3/raw_fork1.csv
  50d9e7e28fe59bee789b557a2f0da09b2a4198a90e5e5a4c3d367a3a054b43d6  run4/raw_fork1.csv
  e955ebed3fc630ab5518c895dd8dcabddf4ceeebeac319de052fce4a212012a1  run3/warmup_fork1.csv
  9abf4371962502758ffaa4ad4357e134b7560670ce7a0580b44948cd01038404  run4/warmup_fork1.csv
  12aa86f7a2179db2db6ee5d0e43ff5126ed9b65dbdcdeaa8f16da6fd7998ea32  run3/env_fork1.txt
  36fe1694c232f4106c984d98874fbf33c2a699365d94ac4efc5702a35b79077d  run4/env_fork1.txt
  af3ffa7e0818bfd0e38fad9405a3607fa2ec2e3c24e22885ab319e65bf38b469  run3/raw_fork2.csv
  314fc7651acc1e14af0bf2f8359c24a5e62677883858ed58bbfeaf09e023bbd3  run4/raw_fork2.csv
  65ee0b00f1de987940488602a3c925508da8631e1aaf4ca110a891b172e30dfd  run3/warmup_fork2.csv
  2ada642c45b45ecc60744335abc901a7ebbd60cb1393d5a5181fb09ff62fce0f  run4/warmup_fork2.csv
  21235df7644a1478c193f3cb2ab700d843790c70fd9161cd0c8135a1bc4674b8  run3/env_fork2.txt
  3cb9e00bf52526cb865bd569abeaf3c8172c2b309bfc8ee69519febdd8c985ff  run4/env_fork2.txt
  c7154ce8db112f99f9d14d666356475105df9d42c216e9889b678793b2e73ca2  run3/raw_fork3.csv
  12813fa715dbdf4376e69f506b1398841e1b335838958ad7328f0452c6674bee  run4/raw_fork3.csv
  84a1d36afd491abcb33444b0b4de7c29dce316d957535b70715d552053506f03  run3/warmup_fork3.csv
  d6e7368e0dd64081cfac072dbe80362ae80befba08f61c395753da2de8b478a0  run4/warmup_fork3.csv
  0084cb88b89bb6661b048a2a87785c58565d8ccdc67366f8f1e4fc6b31a501c0  run3/env_fork3.txt
  700191e3559fd744ca62ca5d6e3873da9b0863d516606f950fc353913b4f9a9f  run4/env_fork3.txt

================================================================================
