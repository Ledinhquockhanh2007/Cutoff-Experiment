# Đăng ký dự đoán bổ sung: Predictor P3c cho Doubling test $N = 2^{10} .. 2^{22}$ (T04 Addendum)

> **Mốc thời gian đăng ký:** Commit git riêng với tiền tố `T04-PREREG-ADD:`.
> **Cam kết thực nghiệm:** Bổ sung TRƯỚC khi người dùng khởi động đo thực tế (`results_doubling*`). Giữ nguyên các tệp đã đăng ký tại commit `0aa6ca4`, không sửa hay ghi đè. Mọi phân tích tuân thủ Kế hoạch phân tích Phần E (gốc và phần bổ sung cho P3c bên dưới).

---

## 1. Lý do bổ sung Predictor P3c

Trong thiết kế ban đầu của T04:
- **P3 ("bước"):** Giả định chi phí merge lớn $\alpha(k)$ nhảy dựng đứng từ $\alpha_{16} = 8.7861$ lên $\alpha_{19} = 11.5822$ ngay tại $k = 18$ ($N = 2^{18} = 262\,144$). Giả định này dự đoán một bước nhảy bất thường $D = \ln R_{17\to 18} - \ln R_{16\to 17} = +16.5\% \dots +18.0\%$ chỉ trong một lần nhân đôi kích thước. Tuy nhiên, kết quả phân tích ngưỡng cache L3 trên thang $2^{19}$ (T02c Phần C) đã chứng minh mô hình trơn theo $\ln N$ mô tả dữ liệu tốt hơn hẳn mô hình bước nhảy. Do đó, bước nhảy dựng đứng của P3 là một giả định mang tính nhân tạo (do tập dữ liệu trước đây chỉ có 3 thang rời rạc).
- **P3b ("trơn không tăng"):** Giả định $\alpha(k) = \alpha_{16}$ giữ nguyên cho mọi $k \ge 15$. Mô hình này lại mâu thuẫn với sự thật thực nghiệm hiển nhiên rằng $\alpha_{19} > \alpha_{16}$ trên dữ liệu $2^{16} \to 2^{19}$.
- Hai mô hình P3 và P3b ban đầu chưa bao quát được **giả thuyết thực sự đáng quan tâm**: Chi phí merge lớn tăng DẦN khi dữ liệu vượt khỏi các tầng cache (từ L2, L3 ra DRAM) trong khoảng $2^{16} .. 2^{19}$ rồi BÃO HÒA khi kích thước hoàn toàn nằm ngoài cache, hay chi phí sẽ tiếp tục tăng không ngừng theo quy luật lũy thừa như P2?

Vì vậy, **P3c** được bổ sung như một mô hình chi phí hiện thực hơn, cho phép kiểm định phân biệt giữa hiệu ứng bão hòa cache (P3c) và luật lũy thừa đơn thuần (P2).

---

## 2. Công thức và Định nghĩa Predictor P3c

P3c tính thời gian sắp xếp dựa trên cây đệ quy chính xác của từng $(N = 2^k, c)$:
$$\hat{T}_{\text{P3c}}(2^k, c) = w_1 ML_{b1} + w_2 ML_{b2} + w_3 ML_{b3} + \beta E_{\text{rand}} + \alpha(k) ML_{b456}$$
với các hệ số từ `cost_model_M2_coef.csv`:
- $w_1 = 5.855101, w_2 = 10.623879, w_3 = 16.543177$ (ns/phần tử)
- $\beta = 3.272603$ (ns/nghịch thế)
- $E_{\text{rand}} = \text{leaf\_pairs} / 2.0$ (kỳ vọng số nghịch thế trên dữ liệu ngẫu nhiên)

**Quy tắc nội suy tuyến tính của $\alpha(k)$:**
- Với $k \le 12$: $\alpha(k) = \alpha_{12} = 9.076456$
- Với $12 \le k \le 16$: Nội suy tuyến tính từ $\alpha_{12} \to \alpha_{16}$:
  $$\alpha(k) = \alpha_{12} + \frac{k - 12}{16 - 12} (\alpha_{16} - \alpha_{12})$$
- Với $16 \le k \le 19$: Nội suy tuyến tính từ $\alpha_{16} \to \alpha_{19}$:
  $$\alpha(k) = \alpha_{16} + \frac{k - 16}{19 - 16} (\alpha_{19} - \alpha_{16})$$
- Với $k \ge 19$: $\alpha(k) = \alpha_{19} = 11.582234$ (bão hòa)

Tỉ số doubling dự đoán: $\hat{R}_k = \hat{T}_{\text{P3c}}(2^{k+1}, c) / \hat{T}_{\text{P3c}}(2^k, c)$, $\hat{b}_k = \log_2 \hat{R}_k$.  
Ngoại suy tích lũy: $Q_k = \hat{T}_{\text{P3c}}(2^k, c) / \hat{T}_{\text{P3c}}(2^{19}, c)$ cho $k \in \{20, 21, 22\}$.

---

## 3. Kiểm chứng Quy tắc chất lượng A (So khớp với số tham chiếu của Claude)

Đối chiếu cạnh nhau giá trị tính toán của P3c và số tham chiếu độc lập do Claude cung cấp:

### A. CUTOFF $c = 1$
| Chỉ số | $k$ hoặc mốc | Giá trị tính toán | Tham chiếu Claude | Chênh lệch | Đánh giá |
| :--- | :---: | :---: | :---: | :---: | :---: |
| $R(10 \to 11)$ | 10 | 2.183125 | 2.1831 | +0.000025 | Khớp đến 4 chữ số |
| $R(12 \to 13)$ | 12 | 2.147354 | 2.1474 | -0.000046 | Khớp đến 4 chữ số |
| $R(14 \to 15)$ | 14 | 2.124248 | 2.1242 | +0.000048 | Khớp đến 4 chữ số |
| $R(16 \to 17)$ | 16 | 2.239862 | 2.2399 | -0.000038 | Khớp đến 4 chữ số |
| $R(17 \to 18)$ | 17 | 2.236225 | 2.2362 | +0.000025 | Khớp đến 4 chữ số |
| $R(18 \to 19)$ | 18 | 2.230991 | 2.2310 | -0.000009 | Khớp đến 4 chữ số |
| $R(19 \to 20)$ | 19 | 2.109843 | 2.1098 | +0.000043 | Khớp đến 4 chữ số |
| $R(20 \to 21)$ | 20 | 2.104125 | 2.1041 | +0.000025 | Khớp đến 4 chữ số |
| $R(21 \to 22)$ | 21 | 2.098972 | 2.0990 | -0.000028 | Khớp đến 4 chữ số |
| $Q_{20}$ | 20 | 2.109843 | 2.1098 | +0.000043 | Khớp đến 4 chữ số |
| $Q_{21}$ | 21 | 4.439374 | 4.4394 | -0.000026 | Khớp đến 4 chữ số |
| $Q_{22}$ | 22 | 9.318121 | 9.3181 | +0.000021 | Khớp đến 4 chữ số |
| $D$ (bước) | $17\to 18$ vs $16\to 17$ | -0.001625 | -0.0017 | +0.000075 | Khớp hoàn toàn |

### B. CUTOFF $c = 30$
| Chỉ số | $k$ hoặc mốc | Giá trị tính toán | Tham chiếu Claude | Chênh lệch | Đánh giá |
| :--- | :---: | :---: | :---: | :---: | :---: |
| $R(10 \to 11)$ | 10 | 2.218153 | 2.2182 | -0.000047 | Khớp đến 4 chữ số |
| $R(12 \to 13)$ | 12 | 2.170492 | 2.1705 | -0.000008 | Khớp đến 4 chữ số |
| $R(14 \to 15)$ | 14 | 2.140937 | 2.1409 | +0.000037 | Khớp đến 4 chữ số |
| $R(16 \to 17)$ | 16 | 2.268130 | 2.2681 | +0.000030 | Khớp đến 4 chữ số |
| $R(17 \to 18)$ | 17 | 2.260774 | 2.2608 | -0.000026 | Khớp đến 4 chữ số |
| $R(18 \to 19)$ | 18 | 2.252227 | 2.2522 | +0.000027 | Khớp đến 4 chữ số |
| $R(19 \to 20)$ | 19 | 2.118811 | 2.1188 | +0.000011 | Khớp đến 4 chữ số |
| $R(20 \to 21)$ | 20 | 2.112149 | 2.1121 | +0.000049 | Khớp đến 4 chữ số |
| $R(21 \to 22)$ | 21 | 2.106194 | 2.1062 | -0.000006 | Khớp đến 4 chữ số |
| $Q_{20}$ | 20 | 2.118811 | 2.1188 | +0.000011 | Khớp đến 4 chữ số |
| $Q_{21}$ | 21 | 4.475243 | 4.4752 | +0.000043 | Khớp đến 4 chữ số |
| $Q_{22}$ | 22 | 9.425730 | 9.4257 | +0.000030 | Khớp đến 4 chữ số |
| $D$ (bước) | $17\to 18$ vs $16\to 17$ | -0.003249 | — | — | Âm và gần 0 |

---

## 4. Ba Giả thuyết Cạnh tranh và Phép kiểm định Phân biệt

Trước khi có dữ liệu đo, ba giả thuyết khoa học đưa ra các dự đoán khác biệt rõ rệt tại các vùng kiểm tra then chốt:

1. **Giả thuyết 1: Luật lũy thừa không đổi (P2)**
   - Cơ chế: Chi phí tăng theo lũy thừa $T = a N^b$ với $b \approx 1.16$ không đổi ngay cả khi ra khỏi L3 cache.
   - Dự đoán: Tại $k = 19, 20, 21$, $R_k \approx 2.24$ ($c=1$), $R_k \approx 2.26$ ($c=30$). Ngoại suy tích lũy $Q_{22} \approx 11.22$ ($c=1$), $11.61$ ($c=30$).
   - Bước $D = \ln R_{17\to 18} - \ln R_{16\to 17} = 0.0000$.

2. **Giả thuyết 2: Chi phí merge tăng dần rồi bão hòa (P3c)**
   - Cơ chế: Chi phí đơn vị của merge lớn tăng dần từ $\alpha_{16} = 8.79$ lên $\alpha_{19} = 11.58$ do suy giảm hiệu năng bộ nhớ trong khoảng $2^{16} .. 2^{19}$, nhưng sau $2^{19}$ khi dữ liệu hoàn toàn vượt quá cache thì chi phí đơn vị bão hòa ở $\alpha_{19}$. Do đó, sau $k=19$, tỉ số doubling $R_k$ quay trở lại tiệm cận mức lý thuyết $N \lg N$ ($b \to 1.07$).
   - Dự đoán: Tại $k = 19, 20, 21$, $R_k$ giảm xuống $\approx 2.10$ ($c=1$), $\approx 2.11$ ($c=30$). Ngoại suy tích lũy $Q_{22} \approx 9.32$ ($c=1$), $9.43$ ($c=30$).
   - Bước $D = \ln R_{17\to 18} - \ln R_{16\to 17} = -0.0016$ ($c=1$), trơn và hơi âm nhẹ theo quy luật $N \lg N$.

3. **Giả thuyết 3: Bước nhảy gián đoạn (P3 bước)**
   - Cơ chế: Chi phí merge lớn giữ nguyên ở $\alpha_{16}$ cho đến tận $k=17$, sau đó nhảy dựng đứng lên $\alpha_{19}$ tại $k=18$.
   - Dự đoán: Bước nhảy $D = \ln R_{17\to 18} - \ln R_{16\to 17} = +0.165 \dots +0.180$ (+16.5% đến +18.0%).

### Hai phép so sánh then chốt:
1. **Phép kiểm định bão hòa (P2 vs P3c):** So sánh $R_k$ đo được tại $k = 19, 20, 21$.
   - Nếu $R_k$ đo được nằm quanh $2.24 \dots 2.26$ $\implies$ ủng hộ P2.
   - Nếu $R_k$ đo được sụt về quanh $2.10 \dots 2.11$ $\implies$ ủng hộ P3c (bão hòa cache).
2. **Phép kiểm định hình dạng chuyển tiếp (P3 bước vs P3c/P2):** So sánh $D = \ln R_{17\to 18} - \ln R_{16\to 17}$.
   - Nếu $D$ đo được dương lớn ($+15\% \dots +18\%$) $\implies$ ủng hộ P3 bước.
   - Nếu $D$ đo được quanh 0 hoặc hơi âm nhẹ ($-0.3\% \dots 0\%$) $\implies$ bác bỏ dứt khoát P3 bước, ủng hộ chuyển tiếp trơn P3c.

---

## 5. Bổ sung Kế hoạch Phân tích (Phần E)

Kế hoạch phân tích đã chốt tại Phần E của [T04_predictions.md](file:///d:/DSA/cutoff-experiment/handoff/preregistration/T04_predictions.md) được bổ sung như sau (bổ sung, không thay thế):
- Predictor **P3c** được đưa vào đánh giá đầy đủ và bình đẳng cùng các predictor P1, P2, P2b, P3, P3b.
- Tiêu chí đạt sai số dự đoán: $|e_k| = |\ln \hat{R}_k - \ln \bar{R}_k| \le 1.5\%$ áp dụng cho P3c trên mọi $k = 10..21$ và mọi CUTOFF.
- Báo cáo RMSE của $e_k$ cho P3c trên toàn dải $k = 10..21$ và riêng vùng ngoại suy $k = 18..21$.
- Báo cáo dự đoán tích lũy $Q_k$ của P3c so với giá trị đo thực nghiệm kèm 3 giá trị theo fork tại $k = 20, 21, 22$.
- Phép thử $D = \ln R_{17\to 18} - \ln R_{16\to 17}$ sẽ so sánh giá trị thực đo với cả 3 mốc dự đoán: $D_{\text{P3}} \approx +0.17$, $D_{\text{P3c}} \approx -0.002$, và $D_{\text{P2}} = 0.000$.
