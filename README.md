# CUTOFF tối ưu cho mergesort trên JVM

Mã nguồn, dữ liệu đo và báo cáo của nghiên cứu thực nghiệm về ngưỡng CUTOFF (độ dài đoạn con mà từ đó mergesort chuyển sang insertion sort), thực hiện cho môn Cấu trúc dữ liệu và giải thuật, Trường Đại học Công nghệ, ĐHQGHN.

Báo cáo đầy đủ: [`report/report.pdf`](report/report.pdf).

**Kết quả chính.** Trên máy AMD Ryzen 7 H 255 với JDK 25, mergesort top-down trên `Integer[]` ngẫu nhiên có CUTOFF tối ưu 30–32; mọi CUTOFF từ 17 đến 32 chậm hơn mức tối ưu không quá 2%. So với CUTOFF bằng 1, thời gian giảm 8.4–15.6%. Mức "khoảng 20%" chỉ đạt với `int[]` (giảm 22–30%) và với một số phân bố dữ liệu.

## Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| `src/` | Thuật toán (`MergeCutoff`, `MergeCutoffInt`, `MergeCutoffCounted`), bộ đo `Benchmark`, sinh dữ liệu `DataGenerator`, kiểm thử `CorrectnessTest`, công cụ đo bộ nhớ và chẩn đoán |
| `jmh/src/` | Benchmark JMH (JMH ban đầu và JMH yếu tố đầy đủ) |
| `lib/` | Thư viện Java: JMH 1.37, JOL 0.17, commons-math3, jopt-simple |
| `scripts/` | Tệp `.bat` chạy từng phiên đo; script Python phân tích, vẽ hình |
| `preregistration/` | Kế hoạch đo: dự đoán và tiêu chí bằng số, ghi trước khi có dữ liệu tương ứng |
| `data*/manifest.csv` | Seed và mã băm SHA-256 của mọi mảng dữ liệu (bản thân các mảng không lưu vì sinh lại được) |
| `results_*/`, `results/`, `diag/` | Dữ liệu thô của từng phiên đo và bảng phân tích (xem bảng dưới) |
| `results_correctness/` | Kết quả `CorrectnessTest` trên JDK 25 của máy đo |
| `report/` | Mã LaTeX của báo cáo, bảng và hình sinh tự động, PDF |

### Phiên đo và thư mục dữ liệu

| Phiên đo | Thư mục |
|---|---|
| Run 1, Run 2, Run 3, Run 4 (phép đo sơ bộ) | `results_run1/`, `results/`, `results_run3/`, `results_run4/`; bộ hợp nhất và phân tích: `results_final/` |
| Chẩn đoán hai mức hiệu năng, hiệu ứng đo theo lô | `diag/`, `results_kdiag/` |
| Doubling test sơ bộ | `results_doubling/` |
| Thí nghiệm chính (`random`, 5 thang) | `results_run5_s1/` |
| Các phân bố khác | `results_run5_s2/` |
| Doubling test chính | `results_doubling_v2/` |
| Kiểu khóa | `results_d3/` |
| JMH ban đầu | `results_jmh/` |
| JMH yếu tố đầy đủ (lần 3, hợp lệ; hai lần bị loại) | `results_jmh_v2/`, `results_jmh_v2_rejected_lowclock/`, `results_jmh_v2_rejected_lowclock_2/` |
| `int[]` mở rộng | `results_int_ext/` |
| Bảng phân tích các phép đo chính / JMH và `int[]` | `results_phase2/analysis/`, `results_phase2b/analysis/` |

Mỗi thư mục phiên đo có `raw_fork*.csv` (từng phép đo), `env_fork*.txt` (môi trường JVM) và `typeperf_*.csv` (xung nhịp, độ bận của từng bộ xử lý logic, ghi mỗi giây).

## Yêu cầu

- Windows 10/11 (các tệp `.bat` dùng `start /affinity` để ghim tiến trình), JDK 25.
- Python 3.10 trở lên: `pip install -r scripts/requirements.txt`.
- XeLaTeX nếu muốn biên dịch báo cáo.

## Tái lập

Mọi lệnh chạy từ thư mục gốc của repo.

1. **Biên dịch và sinh dữ liệu.**
   ```bat
   javac -encoding UTF-8 -cp "lib/*;src" -d build src\*.java
   java -cp build DataGenerator --run5
   java -cp build DataGenerator --doubling
   java -cp build DataGenerator --verify
   ```
   `--verify` so mã băm của các mảng vừa sinh với `manifest.csv` trong repo.
2. **Kiểm thử:** `scripts\run_correctness.bat`.
3. **Đo** (mỗi tệp kiểm tra môi trường, ghim nhân và ghi `typeperf`): `run5_s1_random.bat`, `run5_s2_other.bat`, `run_doubling_v2.bat`, `run_d3_keys.bat`, `run_jmh.bat`, `run_jmh_v2.bat`, `run_int_ext.bat` trong `scripts\`.
4. **Phân tích:** `python scripts/analyze_t10.py`, `python scripts/analyze_t12.py`, `python scripts/session_quality.py`. Mỗi script có `--self-check` để tái lập các con số đã biết trước khi chạy trên dữ liệu mới.
5. **Hình và bảng:** `python scripts/make_figures_p2.py`, `python report/make_tables.py`, `python report/make_tables_p2.py`. Mỗi hình có tệp `.data.csv` chứa đúng các điểm được vẽ và `.src.txt` ghi nguồn; script bảng đối chiếu mọi con số với bảng phân tích và dừng nếu lệch.

Thời gian tuyệt đối phụ thuộc máy; các kết luận của báo cáo dựa trên tỉ số thời gian $r = T(c)/T(1)$ đo ghép cặp trong cùng JVM.

## Kế hoạch đo và lịch sử commit

Các tệp trong `preregistration/` được commit trước dữ liệu mà chúng dự đoán. Lịch sử git của repo này được rút gọn thành các mốc (kế hoạch, dữ liệu, phân tích), giữ nguyên thời điểm commit gốc; bảng các commit mốc ở Phụ lục A của báo cáo liệt kê các mốc này.

## Sử dụng AI

Báo cáo được thực hiện với sự hỗ trợ của AI trong phạm vi cho phép; phân công cụ thể nằm ở mục "Tuyên bố sử dụng AI" của báo cáo. Nhật ký hội thoại với Claude và bản ghi làm việc với Antigravity nằm trong [`ai_log/`](ai_log/README.md).

## Tác giả

Lê Đình Quốc Khánh, Trường Đại học Công nghệ, ĐHQGHN.
