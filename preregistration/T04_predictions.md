# Đăng ký dự đoán trước thực nghiệm: Doubling test $N = 2^{10} .. 2^{22}$ (T04)

> **Mốc thời gian đăng ký:** Commit git riêng với tiền tố `T04-PREREG:`.
> **Cam kết thực nghiệm:** Không xem hay đọc bất kỳ dữ liệu thực nghiệm mới nào (`results_doubling*`) trước khi commit tài liệu này. Mọi phân tích sau này tuân thủ đúng Kế hoạch phân tích ở Phần E.

---

## 1. Mục tiêu và Thiết kế thí nghiệm

Thực hiện bài kiểm tra tăng gấp đôi kích thước (doubling test) theo đúng bài giảng 1.3:
- **Dữ liệu:** Phân bố `random`, $N = 2^k$ với $k = 10, 11, \dots, 22$ (13 kích thước). Seed sinh từ công thức chuẩn `seedFor("random", N)`. Ba bộ $N \in \{2^{12}, 2^{16}, 2^{19}\} trùng seed và sha256 với bộ dữ liệu chuẩn trong `data/`.
- **Lưới CUTOFF:** $\{1, 4, 7, 8, 10, 16, 30, 32, 64\}$ (9 giá trị).
  * **Cặp đối chứng cùng cây đệ quy:** Do $N = 2^k$, độ dài đoạn con ở lá là lũy thừa của 2 lớn nhất $\le c$. Vì vậy, các cặp $(4, 7)$, $(8, 10)$, $(16, 30)$ thực thi **chính xác cùng một cây đệ quy và cùng số phép toán**.
- **Harness đo:** Ghim nhân vật lý 5 (`/affinity C00`), JVM flags `-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch`, $K = 1$ cố định, 3 fork tuần tự. Số trial theo quy ước `repsFor`: $N \le 2^{16} \implies 10$ trials; $N > 2^{16} \implies 5$ trials.

---

## 2. Các mô hình dự đoán (Predictors)

Dự đoán tỉ số tăng thời gian $R_k = T(2^{k+1}) / T(2^k)$ và số mũ cục bộ $b_k = \log_2 R_k$ cho $k = 10, 11, \dots, 21$:

1. **P1 (Mô hình lý thuyết $N \lg N$):**
   $$R_k = \frac{2 \cdot (k+1)}{k}, \quad b_k = 1 + \log_2\left(\frac{k+1}{k}\right)$$
   Độc lập với CUTOFF $c$. Tỉ số $R_k$ giảm trơn từ $2.2000$ ($k=10$) về $2.0952$ ($k=21$).

2. **P2 (Quy luật lũy thừa $T = a \cdot N^b$ trên 48 N sạch cùng JVM):**
   Hồi quy OLS $\ln T = \ln a + b \ln N$ trên 48 điểm $N$ của $2^{16} + 2^{19}$ (từ `results_final/`):
   $$R = 2^b, \quad b_k = b \quad \text{(hằng số theo } k\text{)}$$
   * Hệ số $b$ cho 9 CUTOFF:
     - $c = 1$: $b = 1.162545 \implies R = 2.238519$
     - $c = 4$: $b = 1.170642 \implies R = 2.251119$
     - $c = 7$: $b = 1.173459 \implies R = 2.255519$
     - $c = 8$: $b = 1.173154 \implies R = 2.255042$
     - $c = 10$: $b = 1.175608 \implies R = 2.258880$
     - $c = 16$: $b = 1.176634 \implies R = 2.260488$
     - $c = 30$: $b = 1.179014 \implies R = 2.264220$
     - $c = 32$: $b = 1.179256 \implies R = 2.264599$
     - $c = 64$: $b = 1.176720 \implies R = 2.260622$
   * *Lưu ý quan trọng:* Do P2 được khớp trên 48 $N$ theo cấp số nhân hình học (nơi các đoạn lá của $c=7$ và $c=4$ có độ dài khác nhau), P2 cho $c=4$ và $c=7$ hai dự đoán khác nhau dù ở $N=2^k$ chúng chạy cùng một cây.

3. **P2b (Biến thể lũy thừa khớp trên 72 N):**
   Hồi quy OLS trên cả 72 điểm $N$ (gồm 24 $N$ thang $2^{12}$ đo ở JVM khác):
   - $c = 1: b = 1.117130, R = 2.169150$
   - $c = 4: b = 1.122515, R = 2.177262$
   - $c = 7: b = 1.125709, R = 2.182087$
   - $c = 8: b = 1.126015, R = 2.182550$
   - $c = 10: b = 1.127777, R = 2.185218$
   - $c = 16: b = 1.130647, R = 2.189569$
   - $c = 30: b = 1.132885, R = 2.192969$
   - $c = 32: b = 1.132822, R = 2.192873$
   - $c = 64: b = 1.136057, R = 2.197795$

4. **P3 (Mô hình chi phí M2 trên cây thật với quy tắc bước $\alpha$):**
   $$\hat{T}(2^k, c) = w_1 ML_{b1} + w_2 ML_{b2} + w_3 ML_{b3} + \beta E_{\text{rand}} + \alpha(k) ML_{b456}$$
   với hệ số từ `cost_model_M2_coef.csv`:
   - $w_1 = 5.855101, w_2 = 10.623879, w_3 = 16.543177$ (ns/phần tử)
   - $\beta = 3.272603$ (ns/nghịch thế)
   - $\alpha(k)$ chốt trước theo thang kích thước:
     * $k \le 14 \implies \alpha = \alpha_{12} = 9.076456$
     * $15 \le k \le 17 \implies \alpha = \alpha_{16} = 8.786120$
     * $k \ge 18 \implies \alpha = \alpha_{19} = 11.582234$
   - $\hat{R}_k = \hat{T}(2^{k+1}, c) / \hat{T}(2^k, c)$, $\hat{b}_k = \log_2 \hat{R}_k$.

5. **P3b (Biến thể M2 trơn, không có bước nhảy):**
   Giữ $\alpha = \alpha_{16} = 8.786120$ cho mọi $k \ge 15$ (giả định chi phí merge lớn không bị tăng vọt ở thang ngoài L3).

---

## 3. Hai dự đoán định tính để có thể BỊ BÁC (Falsifiable Predictions)

1. **Phép thử bước nhảy giữa $k=16..17$ và $k=17..18$:**
   Đại lượng $D = \ln R_{17\to 18} - \ln R_{16\to 17}$:
   - **P1 và P3b** dự đoán $D \approx -0.0035$ (giảm trơn theo $N \lg N$).
   - **P2 và P2b** dự đoán $D = 0.0000$ (tỉ số không đổi).
   - **P3** dự đoán một **bước nhảy dương rất lớn**:
     * $c = 1: D = +0.1646$ (+16.46%)
     * $c = 4, 7: D = +0.1731$ (+17.31%)
     * $c = 8, 10: D = +0.1757$ (+17.57%)
     * $c = 16, 30: D = +0.1798$ (+17.98%)
     * $c = 32: D = +0.1773$ (+17.73%)
     * $c = 64: D = +0.1680$ (+16.80%)
   *Tiêu chí bác P3:* Nếu thực nghiệm đo được $D$ quanh 0 hoặc âm (nằm ngoài khoảng tin cậy của 3 fork quanh giá trị P3 dự đoán), giả thuyết bước nhảy $\alpha_{19} > \alpha_{16}$ của P3 chính thức bị bác bỏ.

2. **Đối chứng cùng-cây tại $N = 2^k$:**
   Tại mọi $k = 10, \dots, 22$:
   - $\ln T(4) - \ln T(7) = 0$
   - $\ln T(8) - \ln T(10) = 0$
   - $\ln T(16) - \ln T(30) = 0$
   *Tiêu chí cảnh báo:* Nếu có bất kỳ cặp nào lệch hệ thống $> 1.0\%$, điều đó chứng tỏ có hiệu ứng thứ tự/vị trí đo hoặc nhiễu không triệt tiêu, cần nới lỏng các kết luận so sánh chi tiết.

---

## 4. Bảng dự đoán mẫu

### Bảng 1. Dự đoán tỉ số $R_k$ tại các mốc chính ($c = 1, 30$)

| $k_{\text{from}} \to k_{\text{to}}$ | $N_{\text{from}} \to N_{\text{to}}$ | P1 ($N\lg N$) | P2 (48N, c=1) | P2 (48N, c=30) | P3 (M2, c=1) | P3 (M2, c=30) | P3b (M2, c=30) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| 10 -> 11 | 1K -> 2K | 2.2000 | 2.2385 | 2.2642 | 2.1931 | 2.2155 | 2.2155 |
| 12 -> 13 | 4K -> 8K | 2.1667 | 2.2385 | 2.2642 | 2.1610 | 2.1818 | 2.1818 |
| 14 -> 15 | 16K -> 32K | 2.1429 | 2.2385 | 2.2642 | 2.0725 | 2.0863 | 2.0863 |
| 16 -> 17 | 65K -> 131K | 2.1250 | 2.2385 | 2.2642 | 2.1164 | 2.1301 | 2.1301 |
| 17 -> 18 | 131K -> 262K | 2.1176 | 2.2385 | 2.2642 | **2.4950** | **2.5498** | **2.1224** |
| 18 -> 19 | 262K -> 524K | 2.1111 | 2.2385 | 2.2642 | 2.1054 | 2.1162 | 2.1162 |
| 19 -> 20 | 524K -> 1M | 2.1053 | 2.2385 | 2.2642 | 2.1001 | 2.1106 | 2.1106 |
| 21 -> 22 | 2M -> 4M | 2.0952 | 2.2385 | 2.2642 | 2.0910 | 2.1006 | 2.1006 |

### Bảng 2. Dự đoán ngoại suy tích lũy $Q_k = T(2^k) / T(2^{19})$

| $k$ | $N$ | P1 ($N\lg N$) | P2 (48N, c=1) | P2 (48N, c=30) | P3 (M2, c=1) | P3 (M2, c=30) | P3b (c=30) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 20 | 1 048 576 | 2.1053 | 2.2385 | 2.2642 | 2.1001 | 2.1106 | 2.1106 |
| 21 | 2 097 152 | 4.4211 | 5.0110 | 5.1267 | 4.4001 | 4.4435 | 4.4435 |
| 22 | 4 194 304 | 9.2632 | 11.2172 | 11.6080 | 9.2007 | 9.3339 | 9.3339 |

*(Bảng chi tiết đầy đủ xem trong `T04_predictions.csv` và `T04_extrapolation.csv`).*

---

## 5. Phần E. KẾ HOẠCH PHÂN TÍCH (Chốt trước, nguyên văn)

*(Sao chép nguyên văn từ đề bài `handoff/tasks/T04_doubling_prep.md`)*

- **Đơn vị:** với mỗi (fork, N, c) lấy trung bình hình học của các trial của `time_ns` (đã là thời gian một lần sắp, K = 1). R_k theo fork = tỉ số hai ô cùng fork (cùng JVM nên mức JVM triệt tiêu); R̄_k = trung bình hình học của 3 fork.
- **Sai số dự đoán:** $e_k = \ln \hat{R}_k - \ln \bar{R}_k$. "Đạt" nếu $|e_k| \le 1.5\%$ (xấp xỉ 3 lần sai số chuẩn kỳ vọng của $\bar{R}_k$). Báo cáo bảng $e_k$ cho mọi predictor, CUTOFF và $k$; RMSE của $e_k$ trên $k = 10..21$ và riêng trên $k = 18..21$ (vùng ngoại suy); dự đoán tích lũy $Q_k$ cho $k = 20..22$ so với đo, kèm đúng 3 giá trị theo fork.
- **Phép thử bước:** $D = \ln R_{17\to 18} - \ln R_{16\to 17}$ và cùng thống kê ở 2 cặp liền kề khác; so với giá trị dự đoán của P3 và P1/P2. Bác P3 nếu $D$ đo nằm ngoài khoảng của 3 fork quanh giá trị P3 dự đoán một cách rõ rệt (định nghĩa cụ thể lúc phân tích, nhưng phải báo cả 3 giá trị theo fork).
- **Đối chứng cùng-cây:** chênh lệch $\ln T$ giữa (4,7), (8,10), (16,30) tại mỗi $N$; kỳ vọng quanh 0; nếu một cặp lệch hệ thống $> 1\%$ thì có hiệu ứng vị trí/thứ tự và mọi kết luận về chênh nhỏ giữa các CUTOFF phải nới.
- **Số mũ cuối:** hồi quy log-log $T$ theo $N$ trên $k = 16..22$ và $10..22$, CI theo fork; so với $b = 1.1625$ (48 N). Chỉ báo cáo, không "đúng/sai" nếu CI df = 2 quá rộng.
- **Không được thêm kiểm định sau khi thấy dữ liệu;** phân tích khám phá ghi riêng và gắn nhãn "khám phá".
