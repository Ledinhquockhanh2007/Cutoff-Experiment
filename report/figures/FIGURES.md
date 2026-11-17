# Danh mục đồ thị báo cáo (Figures Catalogue)

## 1. Đồ thị thân bài (Main Figures)

| Tên tệp | Cỡ | Nhãn LaTeX (`\label`) | Caption gợi ý (trung tính, không nhân quả) | Phân loại | Nguồn dữ liệu |
| :--- | :---: | :--- | :--- | :---: | :--- |
| `fig01_r_vs_cutoff_random` | 120 mm | `fig:r_cutoff_random` | Tỉ số thời gian $r(N, c) = T(c)/T(1)$ theo CUTOFF cho dữ liệu ngẫu nhiên trên ba thang quy mô; dải mờ là CI 95% bootstrap. | [khám phá] | `results_final/analysis/tables/r_by_cutoff.csv` |
| `fig02_m2_fit_loso` | 170 mm | `fig:m2_fit_loso` | So khớp mô hình chi phí M2 với thực đo trên 3 thang nội suy (a) và kiểm tra ngoài mẫu LOSO trên thang $2^{19}$ kèm dải dung sai thực nghiệm $\pm 0.01$ (b). | [khám phá] | `cost_model_in_sample_errors.csv`, `validate_2e19_loso.csv` |
| `fig03_cost_decomposition` | 85 mm | `fig:cost_decomposition` | Phân rã thành phần chi phí của mô hình M2 trên thang $S = 2^{16}$: mức tiết kiệm bỏ merge đối chiếu với chi phí thêm của insertion sort và vùng gần tối ưu 2% [14, 48]. | [khám phá] | `cost_model_decomposition.csv`, `cost_model_sensitivity.csv` |
| `fig04_doubling_ln_R` | 170 mm | `fig:doubling_ln_r` | Tỉ số tăng trưởng doubling $\ln R_k$ theo $k$ cho $c=1$ và $c=30$ kèm sai số thực đo $\pm 2\cdot\mathrm{SE}$, so sánh với các dự báo mô hình P1, P2 và P3c qua các vùng nội suy và ngoại suy. | [kiểm định đã đăng ký] | `A1_pred_error_full.csv`, `B1_doubling_lecture.csv` |
| `fig05_t_over_nlgn_cache` | 120 mm | `fig:t_over_nlgn_cache` | Thời gian chuẩn hóa $T / (N \lg N)$ theo quy mô $k$, kèm các ngưỡng dung lượng bộ nhớ hoạt động tương ứng với bộ nhớ đệm L2 và L3. | [khám phá] | `B2_t_over_nlgn.csv`, `memory_cache_discussion.csv` |
| `fig06_r_diminishing_returns` | 85 mm | `fig:r_diminishing` | Tỉ số thời gian $r(N, 30)$ trên thang doubling từ 1K đến 4M (tại $N = 2^k$, $c=30$ tương đương lá dài 16, cùng cây đệ quy với mọi $c \in [16, 31]$); đường đứt nét biểu thị mức giảm 20% nêu trong bài giảng. | [khám phá] | `B3_cutoff_ratio_r.csv` |
| `fig07_memory_by_config` | 170 mm | `fig:memory_by_config` | Dung lượng bộ nhớ thực tế của mergesort: số byte/phần tử trên 3 cấu hình JVM (a) và tổng dung lượng hoạt động theo $N$ so với cache trên thang log (b). | [khám phá] | `memory_measurements.csv` |
| `fig08_other_distributions` | 170 mm | `fig:other_distributions` | Tỉ số $r(N, c)$ trên 4 phân bố không ngẫu nhiên (thang $S = 2^{16}$, trung bình nhân 24 $N$), minh họa sự không áp dụng được của mô hình M2 và khác biệt lớn của $c^*$ giữa các phân bố. | [khám phá] | `validate_other_distributions.csv` |

## 2. Đồ thị phụ lục (Appendix Figures)

| Tên tệp | Cỡ | Nhãn LaTeX (`\label`) | Caption gợi ý (trung tính, không nhân quả) | Phân loại | Nguồn dữ liệu |
| :--- | :---: | :--- | :--- | :---: | :--- |
| `figA01_local_exponent` | 120 mm | `fig:local_exponent` | Số mũ tăng trưởng cục bộ $b$ theo thang quy mô cho $c=1$ và $c=30$ so với lý thuyết xấp xỉ cục bộ của $N \lg N$. | [khám phá] | `power_law_local_exponent.csv` |
| `figA02_power_law_runs` | 120 mm | `fig:power_law_runs` | Chênh lệch số mũ lũy thừa $\Delta b = b_{\mathrm{run}} - b_{\mathrm{run3}}$ giữa các lượt chạy độc lập (run 1, run 2 so với run 3 ghim nhân 5). | [khám phá] | `power_law_run_comparison.csv` |
| `figA03_precision_vs_R` | 120 mm | `fig:precision_vs_r` | Phân tích phương sai và độ nửa rộng khoảng tin cậy của $d(7, 10)$ theo số fork JVM và số lần lặp đo $m$. | [khám phá] | `precision_vs_R.csv` |
| `figA04_fork_stability_doubling` | 120 mm | `fig:fork_stability` | Độ ổn định giữa 3 fork JVM độc lập của $\ln R_k$ trên toàn bộ thang doubling ($c=1$); dải xám là ngưỡng hợp đồng $\pm 1.5\%$ tham chiếu. | [khám phá] | `A1_pred_error_full.csv` |
| `figA05_cost_model_sensitivity` | 120 mm | `fig:cost_model_sensitivity` | Độ nhạy của CUTOFF tối ưu $c^*$ và vùng gần tối ưu 2% theo các kịch bản biến thiên trọng số chi phí phần cứng. | [khám phá] | `cost_model_sensitivity.csv` |
| `figA06_r_vs_leaf_length` | 120 mm | `fig:r_vs_leaf_length` | Tỉ số thời gian $r$ theo độ dài lá trung bình tách riêng theo 3 thang quy mô, minh họa sự phân tách mức nền $r$ giữa các thang. | [khám phá] | `tree_features.csv`, `cost_model_predictions.csv` |

## 3. Đồ thị đã loại khỏi danh mục (Dropped Figures)

| Tên tệp đã loại | Lý do loại bỏ | Hình thay thế |
| :--- | :--- | :--- |
| `figA02_power_law_cache_step` | Đặt các thang $2^{12}, 2^{16}, 2^{19}$ đo ở các phiên khác nhau lên cùng trục dung lượng bộ nhớ làm việc. CONTEXT (T04b) đã xác định sai lệch tuyệt đối giữa các phiên đo lên tới $\pm 8\%$ và hiện tượng "dip" $2^{12} > 2^{16}$ là hiệu ứng giữa phiên (trong cùng một JVM ở doubling test không có hiện tượng dip này). Các đường nối giữa các cụm thang cũng tạo ấn tượng sai lệch về dữ liệu ở vùng không đo. | `fig05_t_over_nlgn_cache` (đo trong cùng JVM trên toàn dải doubling $2^{10}..2^{22}$) |

## 4. Bảng ánh xạ đổi tên phụ lục (T06b -> T06c)

| Tên cũ (T06b) | Tên mới (T06c) | Ghi chú thay đổi |
| :--- | :--- | :--- |
| `figA01_local_exponent` | `figA01_local_exponent` | Mở rộng ylim [1.05, 1.23], không che điểm $c=30$ tại $2^{12}$; bổ sung công thức $b_{\mathrm{theo}}$ trong .src.txt |
| `figA02_power_law_cache_step` | *(Đã loại)* | Xóa khỏi bộ hình (git rm); thay bằng `fig05` |
| `figA03_power_law_runs` | `figA02_power_law_runs` | Đánh lại số thứ tự sau khi loại bỏ `figA02` cũ |
| `figA04_precision_vs_R` | `figA03_precision_vs_R` | Đánh lại số thứ tự |
| `figA05_fork_stability_doubling` | `figA04_fork_stability_doubling` | Mở rộng ylim [-4.5%, +6.0%], đổi nhãn dải xám hợp đồng tham chiếu, cập nhật SE thật trong .src.txt |
| `figA06_cost_model_sensitivity` | `figA05_cost_model_sensitivity` | Bỏ tiêu đề trong hình, dùng mathtext cho nhãn trục y, thêm chú giải điểm và thanh |
| `figA07_r_vs_leaf_length` | `figA06_r_vs_leaf_length` | Tách thành 3 đường riêng theo từng thang quy mô, bỏ cụm từ "tính không ổn định", bỏ Run 3 |
