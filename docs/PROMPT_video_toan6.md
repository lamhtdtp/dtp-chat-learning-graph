# Đề bài cho Claude Code: Video hoạt hình Toán lớp 6 (Manim 3D + lời thoại tiếng Việt)

Bạn là Claude Code. Hãy dựng một **video giáo dục môn Toán lớp 6** bằng **Manim (Python)**, khổ **ngang 1920×1080**, có **đồ hoạ 3D** và **lời thoại tiếng Việt lồng sẵn, khớp thời gian với hình**. Xuất ra file `.mp4`.

Chủ đề mặc định: **Số nguyên tố**. (Có thể đổi chủ đề — xem mục "Đổi chủ đề" ở cuối.)

---

## 1. Mục tiêu & ràng buộc

- Ngôn ngữ: **tiếng Việt**, phù hợp học sinh 11–12 tuổi. Giải thích chậm, nhấn mạnh chỗ hay sai.
- Thời lượng: **60–90 giây**.
- Khổ **ngang 16:9, 1920×1080, 30fps**.
- Màu phân biệt: số nguyên tố = xanh lá, hợp số = cam, cảnh báo = đỏ, ước = vàng, chữ thường = trắng ngà; nền tối `#0F1420`.
- **QUAN TRỌNG — không có công cụ sinh ảnh AI:** không dùng ảnh AI tĩnh. Thay vào đó dùng **đồ hoạ 3D thật của Manim** (`ThreeDScene`, `Sphere`, `Cube`) để "dễ hình dung". Ý tưởng cốt lõi: số nguyên tố chỉ xếp được thành **một hàng thẳng (que)**, còn hợp số xếp được thành **hình chữ nhật/khối**.
- **Lời thoại:** dùng TTS **offline** `espeak-ng` giọng tiếng Việt (`-v vi`). Đây là giọng tổng hợp (hơi máy móc) — chấp nhận được, và phải để lại chỗ dễ thay bằng giọng thật sau. **Không** phụ thuộc dịch vụ online (không internet ngoài các domain được phép).
- Font tiếng Việt: **DejaVu Sans** (có sẵn, đủ dấu). Dùng `Text(...)` của Manim (Pango), **không** dùng `Tex/MathTex` (LaTeX tiếng Việt rắc rối).
- Chữ phải **vừa trong khung**: viết hàm `fit()` tự thu nhỏ nếu bề rộng vượt ngưỡng.

---

## 2. Môi trường (Ubuntu)

Cài đặt (một lần):

```bash
apt-get update -qq
apt-get install -y -qq libcairo2-dev libpango1.0-dev pkg-config python3-dev espeak-ng
pip install manim --break-system-packages
```

Kiểm tra: `python3 -c "import manim; print(manim.__version__)"` (mong đợi ≥ 0.19), và
`espeak-ng --voices | grep -i viet` phải thấy `vi`, `vi-vn-x-central`, `vi-vn-x-south`.

---

## 3. Cấu trúc file cần tạo

```
script_data.py     # SEGMENTS: danh sách câu thoại + khoảng nghỉ, theo thứ tự thời gian
gen_audio.py       # tạo WAV từng câu bằng espeak-ng, đo thời lượng -> durations.json
prime3d.py         # ThreeDScene: dựng hình, đọc durations.json để khớp thời gian từng câu
build_and_mux.py   # ghép các WAV theo timeline + ghép tiếng vào video -> .mp4 cuối
```

Luồng chạy:

```bash
python3 gen_audio.py                                   # -> durations.json + audio/*.wav
manim prime3d.py PrimeVideo3D --resolution 1920,1080 --fps 30 -o Prime3D_final
python3 build_and_mux.py                               # -> file .mp4 có lời thoại
```

---

## 4. Cơ chế khớp tiếng với hình (bắt buộc)

Nguồn sự thật duy nhất là `SEGMENTS` trong `script_data.py`. Mỗi phần tử:
- `{"kind":"speak", "id": "...", "text": "..."}` — một câu thoại, ứng với **một "beat"** hình.
- `{"kind":"gap", "seconds": 0.6}` — khoảng chuyển cảnh.

Quy trình:
1. `gen_audio.py` đọc `SEGMENTS`, với mỗi `speak` tạo `audio/{id}.wav` bằng
   `espeak-ng -v vi -s 150 -w audio/{id}.wav "text"`, đo thời lượng `d` bằng `ffprobe`,
   ghi `durations.json` với `T = d + PAD` (PAD = 0.5s nghỉ đuôi).
2. `prime3d.py` đọc `durations.json`. Mỗi beat chạy animation rồi **chờ bù** cho đủ đúng `T` giây:
   ```python
   def beat(self, sid, fn):
       T = DUR[sid]; t0 = self.renderer.time
       fn()
       rem = T - (self.renderer.time - t0)
       if rem > 0.05: self.wait(rem)
   ```
   `gap` thì phát animation chuyển cảnh (FadeOut mọi thứ) rồi chờ bù cho đủ `seconds`.
   Giữ `run_time` của các `play` trong mỗi beat **ngắn hơn** `T` để còn chỗ chờ.
3. `build_and_mux.py` duyệt lại `SEGMENTS` theo đúng thứ tự:
   - `speak`: lấy `audio/{id}.wav`, `apad` + `atrim=0:T` cho đúng đúng `T` giây.
   - `gap`: sinh `anullsrc` (im lặng) đúng `seconds` giây.
   Nối tất cả (`concat`) thành `narration.wav`, rồi mux: `-map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -shortest`.

Nhờ hai bên (hình & tiếng) cùng đọc một `SEGMENTS` và cùng độ dài mỗi beat, tiếng và hình tự khớp.

---

## 5. Kỹ thuật Manim 3D + chữ

- Lớp kế thừa `ThreeDScene`; đặt góc camera: `self.set_camera_orientation(phi=62*DEGREES, theta=-50*DEGREES)`.
- **Chữ luôn phẳng, dễ đọc:** thêm bằng `self.add_fixed_in_frame_mobjects(text)` rồi `self.play(FadeIn(text))`. Không để chữ nằm trong không gian 3D (sẽ bị nghiêng/méo).
- Vật thể 3D (`Sphere`, `Cube`) đặt trong không gian 3D, Manim tự đổ bóng tạo khối.
- Xoay nhẹ tạo chiều sâu: `self.begin_ambient_camera_rotation(rate=0.12)` ... `self.stop_ambient_camera_rotation()`.
- Theo dõi mobject đang hiện (chữ cố định và vật 3D) để **FadeOut sạch** ở mỗi `gap`.
- Hàm tiện ích:
  ```python
  def vtext(t, size=40, color=WHITE_T, weight=NORMAL):
      return Text(t, font="DejaVu Sans", font_size=size, color=color, weight=weight)
  def fit(m, max_w=12.5):
      if m.width > max_w: m.scale(max_w / m.width)
      return m
  ```

Bảng màu:
```python
BLUE_N="#4FC3F7"; GREEN_P="#66BB6A"; ORANGE_C="#FFB74D"
RED_W="#EF5350"; YELLOW_D="#FFD54F"; WHITE_T="#ECEFF4"; BG="#0F1420"
```

---

## 6. Kịch bản 5 cảnh (mỗi câu = một beat, id trùng với `SEGMENTS`)

**Cảnh 1 – Mở đầu (đặt vấn đề)**
- `s1_title`: hiện tiêu đề "SỐ NGUYÊN TỐ".
- `s1_candy`: 7 viên kẹo = **7 khối cầu 3D** xếp một hàng, caption "7 viên kẹo"; bật xoay camera nhẹ.
- `s1_arr`: ẩn caption; hiện 2 nhãn góc "Cách 1: 1 hàng × 7 ✔", "Cách 2: 7 hàng × 1 ✔"; `Indicate` hàng kẹo.
- `s1_why`: tắt xoay; hiện câu hỏi 'Vì sao số 7 lại "khó chia"?'.
- `gap 0.6`

**Cảnh 2 – Khái niệm**
- `s2_prime`: "Khái niệm" + "SỐ NGUYÊN TỐ" (xanh) + "số tự nhiên > 1, chỉ có ĐÚNG 2 ước: 1 và chính nó".
- `s2_comp`: "HỢP SỐ" (cam) + "có NHIỀU HƠN 2 ước".
- `s2_warn`: hộp đỏ "Lưu ý: số 1 KHÔNG phải nguyên tố, cũng KHÔNG phải hợp số".
- `gap 0.6`

**Cảnh 3 – Ví dụ (điểm nhấn 3D)**
- `s3_7`: "Ví dụ", "Số 7 → Ước: 1, 7"; **7 khối lập phương 3D thành một que** (màu xanh); kết luận "chỉ xếp thành 1 hàng → SỐ NGUYÊN TỐ ✔".
- `s3_12`: xoá que 7; **12 khối lập phương xếp 3×4 thành hình chữ nhật khối** (màu cam); "Số 12 → Ước: 1, 2, 3, 4, 6, 12", "xếp thành hình chữ nhật → HỢP SỐ".
- `s3_2`: hộp xanh "Số 2 là số CHẴN nhưng vẫn là số nguyên tố (chẵn duy nhất!)".
- `gap 0.6`

**Cảnh 4 – Luyện tập**
- `s4_q`: "Luyện tập" + "Số 15 là số nguyên tố hay hợp số?".
- `s4_a`: "Ước của 15: 1, 3, 5, 15" → "→ 4 ước → HỢP SỐ".
- `s4_warn`: đỏ "Lưu ý: số LẺ chưa chắc là nguyên tố (9 = 3×3 là hợp số!)".
- `gap 0.6`

**Cảnh 5 – Ghi nhớ**
- `s5_sum`: "Ghi nhớ" + 3 ý: ① Nguyên tố = có ĐÚNG 2 ước; ② Số 1 không tính là gì cả; ③ Số 2 là nguyên tố chẵn duy nhất.
- `s5_primes`: "Các số nguyên tố đầu tiên:" + "2 3 5 7 11 13 17 19 …".

---

## 7. Lời thoại chuẩn (đưa nguyên văn vào `SEGMENTS`)

```
s1_title  : Chào các em! Hôm nay chúng ta cùng tìm hiểu về số nguyên tố.
s1_candy  : Giả sử có bảy viên kẹo, muốn chia đều thành các hàng bằng nhau.
s1_arr    : Ta chỉ có hai cách: một hàng bảy viên, hoặc bảy hàng một viên. Không còn cách nào khác.
s1_why    : Vì sao số bảy lại khó chia như vậy?
s2_prime  : Số nguyên tố là số tự nhiên lớn hơn một, chỉ có đúng hai ước: một và chính nó.
s2_comp   : Còn hợp số thì có nhiều hơn hai ước.
s2_warn   : Chú ý: số một không phải số nguyên tố, cũng không phải hợp số.
s3_7      : Ví dụ số bảy. Ước của bảy chỉ có một và bảy. Đúng hai ước, nên bảy là số nguyên tố.
s3_12     : Số mười hai có sáu ước, nên xếp được thành hình chữ nhật. Mười hai là hợp số.
s3_2      : Dễ nhầm nè: số hai là số chẵn, nhưng vẫn là số nguyên tố chẵn duy nhất.
s4_q      : Đến lượt em: số mười lăm là số nguyên tố hay hợp số?
s4_a      : Ước của mười lăm là một, ba, năm, mười lăm. Bốn ước, vậy mười lăm là hợp số.
s4_warn   : Nhớ nhé, số lẻ chưa chắc là số nguyên tố. Chín bằng ba nhân ba, là hợp số.
s5_sum    : Tóm lại: nguyên tố có đúng hai ước, số một không tính, số hai là nguyên tố chẵn duy nhất.
s5_primes : Các số nguyên tố đầu tiên: hai, ba, năm, bảy, mười một, mười ba. Hẹn gặp lại các em!
```

Ghi chú TTS: viết số bằng **chữ** ("bảy", "mười hai") để espeak-ng đọc đúng; tránh ký hiệu (×, →, >) trong câu thoại.

---

## 8. Lệnh render & mux

```bash
# 1) Kiểm tra nhanh (thấp, nhanh) để bắt lỗi bố cục
manim -ql prime3d.py PrimeVideo3D

# 2) Bản chính
python3 gen_audio.py
manim prime3d.py PrimeVideo3D --resolution 1920,1080 --fps 30 -o Prime3D_final
python3 build_and_mux.py   # xuất /mnt/user-data/outputs/So_nguyen_to_Toan6_3D_loithoai.mp4
```

Mux (đã nằm trong `build_and_mux.py`):
```bash
ffmpeg -y -i <video>.mp4 -i narration.wav -c:v copy -c:a aac -b:a 160k \
       -map 0:v:0 -map 1:a:0 -shortest <output>.mp4
```

---

## 9. QA — kiểm tra trước khi giao

- [ ] Trích vài khung hình mỗi cảnh bằng `ffmpeg -ss <t> -i out.mp4 -frames:v 1 f.png` và **xem lại**: chữ không tràn mép, không đè lên nhau, không đè lên vật 3D.
- [ ] Chữ tiếng Việt đủ dấu (ố, ê, ầ, ữ, …).
- [ ] Vật 3D nhìn ra khối (có đổ bóng); que 7 vs hình chữ nhật 12 tương phản rõ.
- [ ] `ffprobe` xác nhận 1920×1080, 30fps, thời lượng 60–90s, có **2 luồng** (video h264 + audio aac).
- [ ] `volumedetect` cho `mean_volume` khác 0 (có tiếng); tiếng vào đúng lúc hình xuất hiện.
- [ ] Độ dài video ≈ độ dài `narration.wav` (lệch < 0.5s).

---

## 10. Đổi chủ đề / tuỳ chỉnh (không phải sửa code lõi)

- **Đổi chủ đề** (vd: số nguyên, phân số, bội–ước): chỉ cần thay `SEGMENTS` (id + text) và các hàm `b_*` dựng hình tương ứng; cơ chế beat/gap và mux giữ nguyên.
- **Đọc chậm hơn:** giảm `SPEED` trong `script_data.py` (vd 130).
- **Giọng Nam/Trung:** đổi `VOICE` thành `vi-vn-x-south` hoặc `vi-vn-x-central`.
- **Khổ dọc điện thoại:** `--resolution 1080,1920` và đặt lại `config.frame_width/height`, chỉnh vị trí chữ.
- **Giọng thật thay TTS:** thu âm từng câu theo id, đặt vào `audio/{id}.wav` (giữ tên), chạy lại `gen_audio.py` (chỉ để đo thời lượng — hoặc sửa nó bỏ bước espeak nếu đã có WAV thật), rồi `build_and_mux.py`.
- **Nhạc nền nhẹ:** thêm một input nhạc, trộn bằng `amix`/`sidechaincompress` với âm lượng thấp trong bước mux.

---

**Lưu ý cuối:** ưu tiên đúng > đẹp. Luôn render `-ql` xem trước, soi khung hình, sửa tràn/đè, rồi mới render bản chính.
