# Danh mục hình báo cáo bản 2 (T13)

Sinh bởi `python scripts/make_figures_p2.py` (hình GĐ2/2b) và `python scripts/make_figures.py --only fig03,fig07,figA01,figA02,figA03,figA04,figA05,figA06`
(hình GĐ1 giữ nguyên). Mỗi hình có `.pdf` (vector, font nhúng), `.png`, `.data.csv` (đúng các điểm vẽ), `.src.txt`
(nguồn, định nghĩa thanh sai số, nhãn, số đối chiếu Quy tắc A).

Nhãn: [ĐK] kiểm định đăng ký trước (ghi id giả thuyết), [KP] khám phá, [MT] mô tả. Viết tắt nguồn: P2 = `results_phase2/analysis/tables/`,
P2B = `results_phase2b/analysis/tables/`, PR = `handoff/preregistration/`, V2 = `results_final/analysis_v2/tables/`, DB = `results_doubling/analysis/tables/`.

## 1. Hình thân bài

| Tên tệp | Cỡ | `\label` đề xuất | Caption gợi ý (trung tính, không nhân quả) | Nhãn | Nguồn |
| --- | --- | --- | --- | --- | --- |
| `fig01_r_vs_cutoff_run5` | 170 mm | `fig:r_cutoff_run5` | Tỉ số $r(c) = T(c)/T(1)$ theo CUTOFF, dữ liệu ngẫu nhiên, Integer[], 5 thang (Run 5, 5 fork); dải mờ là CI hai tầng 95%; ngôi sao là $c^*$ của từng thang; nền xám là giao của 5 vùng gần tối ưu đo được; đường dọc mảnh tại $c = 7$ và $c = 10$. | [ĐK H1] | P2 p2_r_by_cutoff, p2_best |
| `fig02_m2_confirmation` | 170 mm | `fig:m2_confirmation` | Mô hình chi phí M2 với hệ số đóng băng từ giai đoạn 1 so với $r$ đo ở hai thang mới $2^{14}$ (a) và $2^{18}$ (b): đường liền là dự đoán với α nội suy (commit trước khi đo), đường đứt là biến thể α hiệu chỉnh từ hàng $c = 1$; điểm đo kèm CI hai tầng 95%; RMSE ghi trong từng panel. | [ĐK H10, H10b] | P2 p2_m2_validation, p2_m2_summary, p2_r_by_cutoff |
| `fig03_cost_decomposition` | 85 mm | `fig:cost_decomposition` | (Giai đoạn 1, giữ nguyên) Phân rã chi phí của mô hình M2 trên thang $S = 2^{16}$. | [KP] | V2 cost_model_decomposition, cost_model_sensitivity |
| `fig04_doubling_v2` | 170 mm | `fig:doubling_v2` | Doubling v2: $\ln R_k$ theo $k$ cho $c = 1$ (a) và $c = 30$ (b), trung bình 5 fork $\pm 3\,\mathrm{SE}_k$, điểm xám là từng fork, điểm rỗng là doubling v1; đường đứt là dự đoán P-bão hòa, đoạn ngắn ở $k$ = 22, 23 là dự đoán P-tiếp (đăng ký trước). | [ĐK H11, H12] | P2 p2_doubling_R, p2_H11, p2_H12; PR T09_predictions_doubling_v2 |
| `fig05_t_over_nlgn_v2` | 120 mm | `fig:t_over_nlgn_v2` | Thời gian chuẩn hóa $T/(N \lg N)$ theo $k$ (doubling v2, $c = 1$ và $c = 30$); đường dọc tại $N$ mà dữ liệu hoạt động $24N + 32$ byte bằng 1 MiB (L2) và 16 MiB (L3). | [MT] | P2 p2_doubling_T_over_NlgN |
| `fig06_r30_doubling_v2` | 120 mm | `fig:r30_doubling_v2` | Tỉ số $r(2^k, 30)$ theo $k$ (doubling v2) với CI 95% bootstrap theo fork; hai đường ngang là hai cách đọc “khoảng 20%” ($r = 0.80$ và $r = 0.833$). Ở $N = 2^k$, $c = 30$ cho lá dài 16. | [MT] | P2 p2_doubling_r30 |
| `fig07_memory_by_config` | 170 mm | `fig:memory_by_config` | (Giai đoạn 1, giữ nguyên) Bộ nhớ của mergesort trên các cấu hình JVM. | [MT] | V2 memory_measurements |
| `fig08_other_distributions` | 170 mm | `fig:other_distributions` | Tỉ số $r(c)$ cho bốn phân bố không ngẫu nhiên ở 3 thang (Run 5, 5 fork) với CI hai tầng 95%; nền vàng là khoảng (với sorted: điểm) dự đoán đăng ký trước cho $c^*$; ngôi sao là $c^*$ đo. | [ĐK H6–H9] | P2 p2_r_by_cutoff, p2_best; PR T09_hypotheses |
| `fig09_key_types` | 170 mm | `fig:key_types` | Tỉ số $r(c)$ theo kiểu khóa ở 3 thang: Integer[], Double[], int[] (D3, 3 fork) và int[] (S7, 6 fork), CI hai tầng 95%; đường ngang tại $r = 0.833$ và $r = 0.80$; ngôi sao là $c^*$ của từng đường. | [ĐK H14–H16, I1–I3] | P2 p2_d3_r_by_cutoff, p2_d3_best; P2B p2b_int_r_by_cutoff, p2b_int_best |
| `fig10_jmh_vs_harness` | 170 mm | `fig:jmh_vs_harness` | Thời gian một lần sắp đo bằng JMH theo cấu hình ở $N = 4096$ (a) và $N = 524\,288$ (b), kèm T08 và Run 5 (bộ đo tự viết, khác phiên); (c) $r(N, 30)$ theo cấu hình, đường đứt là $r$ của Run 5. JMH v2: CI 95% bootstrap theo fork; T08: Score Error 99.9% của JMH. | [ĐK J1–J7] | P2B p2b_jmh_scores, p2b_jmh_r, p2b_jmh_abs_vs_run5; P2 p2_jmh |

## 2. Hình phụ lục

| Tên tệp | Cỡ | `\label` đề xuất | Caption gợi ý (trung tính, không nhân quả) | Nhãn | Nguồn |
| --- | --- | --- | --- | --- | --- |
| `figA01_local_exponent` | 120 mm | `fig:local_exponent` | (Giai đoạn 1) Số mũ cục bộ $b$ theo thang. | [KP] | RF/V2 (GĐ1) |
| `figA02_power_law_runs` | 120 mm | `fig:power_law_runs` | (Giai đoạn 1) Chênh số mũ $\Delta b$ giữa các lượt đo. | [KP] | GĐ1 |
| `figA03_precision_vs_R` | 120 mm | `fig:precision_vs_r` | (Giai đoạn 1) Độ chính xác theo số fork và số lần lặp. | [KP] | GĐ1 |
| `figA04_fork_stability_doubling` | 120 mm | `fig:fork_stability` | (Giai đoạn 1) Độ ổn định giữa 3 fork của $\ln R_k$, doubling v1; dải xám là ngưỡng ±1.5% (tham chiếu). | [MT] | DB A1_pred_error_full |
| `figA05_cost_model_sensitivity` | 120 mm | `fig:cost_model_sensitivity` | (Giai đoạn 1) Độ nhạy của $c^*$ của M2 theo hệ số. | [KP] | V2 cost_model_sensitivity |
| `figA06_r_vs_leaf_length` | 120 mm | `fig:r_vs_leaf_length` | (Giai đoạn 1) $r$ theo độ dài lá trung bình, 3 thang. | [KP] | V2 tree_features, cost_model_predictions |
| `figA07_fork4_sensitivity` | 120 mm | `fig:fork4_sensitivity` | $r(c^*)$ của từng fork ở 5 thang (fork 4 của S1 tô riêng), kèm ước lượng 5 fork và 4 fork (bỏ fork 4) với CI hai tầng 95%. | [KP] | P2 p2_fork_level, p2_sensitivity_drop_f4_scales |
| `figA08_ci_width` | 170 mm | `fig:ci_width` | Tỉ số độ rộng CI hai tầng / CI một tầng: (a) random tại $c^*$, 7, 10, 30 theo thang; (b) bốn phân bố S2 tại $c^*$. | [MT] | P2 p2_ci_width |
| `figA09_same_tree_h13` | 170 mm | `fig:same_tree_h13` | Chênh lệch trung bình $\bar\Delta(k)$ giữa hai CUTOFF cho cùng cây đệ quy, ba cặp, $\pm 2\,\mathrm{se}_k$; dải xám là ngưỡng ±1% của H13. | [ĐK H13] | P2 p2_H13 (se_k) |
| `figA10_session_clock` | 170 mm | `fig:session_clock` | Xung của nhân đo (LP bận hơn trong LP 10/11) theo thời gian: S1 (cửa sổ fork 4 được tô nền) và ba lần chạy S6; đường đứt là ngưỡng 110%. | [MT] | typeperf qua session_quality.py; P2 p2_session_quality, P2B p2b_session_quality |
| `figA11_int_fork_curves` | 170 mm | `fig:int_fork_curves` | Đường $r_f(c)$ của từng fork với int[]: S7 (6 fork) và D3 (3 fork), 3 thang. | [MT] | thô results_d3/int, results_int_ext qua analyze_t10 (load_raw_dir, compute_paired_A) |

## 3. Hình giai đoạn 1 chuyển sang `legacy_phase1/` (git mv, giữ nguyên nội dung)

| Tệp cũ (nay ở `report/figures/legacy_phase1/`) | Thay bằng |
| --- | --- |
| `fig01_r_vs_cutoff_random` | `fig01_r_vs_cutoff_run5` |
| `fig02_m2_fit_loso` | `fig02_m2_confirmation` |
| `fig04_doubling_ln_R` | `fig04_doubling_v2` |
| `fig05_t_over_nlgn_cache` | `fig05_t_over_nlgn_v2` |
| `fig06_r_diminishing_returns` | `fig06_r30_doubling_v2` |
| `fig08_other_distributions` | `fig08_other_distributions (cùng tên, nay là GĐ2, 3 thang)` |

Ghi chú: `scripts/make_figures.py` vẫn có thể sinh lại các hình GĐ1 cũ (fig01, fig02, fig04, fig05, fig06, fig08 với tên cũ)
và ghi đè tệp này nếu chạy không có `--only`; khi cần sinh lại hình GĐ1 chỉ dùng `--only` với các tên ở trên.
