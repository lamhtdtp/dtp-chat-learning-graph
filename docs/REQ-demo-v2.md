# REQ — Gia sư DTP v2 (rút từ mockup demo)

> **Mục đích:** thay cho việc đọc `dtp-chat-learning-tdd/ui-design/mockups/gia-su-dtp-demo.html`
> (186 KB). Mọi hành vi, trạng thái và dữ liệu của mockup đó đã được mô tả ở đây.
> Chỉ mở file HTML khi cần xem *hình*, không cần đọc để lấy logic.
>
> **Quy ước ký hiệu**
> `✅` đã có trong code, dùng lại — đừng viết lại ·
> `🔶` có rồi nhưng phải mở rộng ·
> `🆕` chưa có, phải làm mới ·
> `❌` cố ý KHÔNG làm

---

## 0. Nền tảng đã có — đọc trước khi viết dòng nào

| Thứ | Đường dẫn | Ghi chú |
|---|---|---|
| CSS học sinh | `web/src/learn/learn.css` (484 dòng) | Token tím `#5B54F0`, cam `#FF9E2C`, teal `#10B5A4`, radius 18. **Không tạo hệ màu mới.** |
| CSS quản trị | `web-admin/src/admin/admin.css` (373 dòng) | Token cam `#F97316`, sidebar tối `#12172A`, `--ai:#2563EB` |
| Vỏ app học sinh | `web/src/learn/LearnApp.tsx` | `Hero`, `O` (ô số liệu + `useSoDoi`), điều hướng danh mục |
| Bài học | `web/src/learn/LessonView.tsx` | `NutHoi`, `The`, thanh "Đã hỏi" |
| Thẻ trợ lý | `web/src/learn/TroLyCard.tsx` | Props `topicId, anchor, nhan, hoiDau, chuDong, dapNhanh, an, onDong` |
| Mốc đọc | `web/src/learn/useMocDoc.ts` | Polling `getBoundingClientRect` 500ms, `NGUONG_DAY=0.35`. **Không đổi sang IntersectionObserver** (không bắn trong browser tự động hoá). |
| Menu hồ sơ | `web/src/learn/ProfileMenu.tsx` | Đã có `.hs-menu/.hs-dau/.hs-so/.hs-dong/.hs-phu` |
| Quiz | `web/src/learn/QuizView.tsx` | `nhacCauSai()`, chỉ câu sai ĐẦU TIÊN tự mở thẻ |
| Trợ lý | `app/api/tutor.py` | `/tutor/ask`, `_enforce_limit`, `_NEO_RE`, `_doan_bai`, `_ngu_canh_bai` |
| Bài học API | `app/api/lessons.py` | `/lessons/{id}`, `/quiz/submit` (chấm ở server), `/me/progress`, `/me/stats` |
| Hạn mức | `app/config.py` `chat_daily_limit=20` · Redis `chatquota:{uid}:{yyyymmdd}` TTL 26h | fail-open khi Redis lỗi |
| Bảng | `app/db/models.py` | `CurriculumTopic`, `TopicContent`, `StudentProgress`, `QuizAttempt`, `StudentStats`, `Blueprint(Cell)`, `VideoJob` |

**Bốn vai trong demo** → 4 app/khu vực: `Chuyên gia` (web-admin) · `Học sinh` (web) ·
`Giáo viên` (web, vai `giao_vien`) · `Vào từ LMS` (mô phỏng lms-fe, không thuộc phạm vi code repo này).

---

## 1. Mô hình 7 phần nội dung

### 1.1 Danh sách phần (thứ tự chuẩn)

| # | `id` | Tên | Nguồn nội dung |
|---|---|---|---|
| 1 | `khoi_dong` | Khởi động | 🆕 chuyên gia soạn |
| 2 | `hoat_dong` | Hoạt động | 🆕 chuyên gia soạn |
| 3 | `kien_thuc` | Kiến thức trọng tâm | ✅ `TopicContent.khai_niem` |
| 4 | `minh_hoa` | Minh hoạ | ✅ `TopicContent.minh_hoa_json` |
| 5 | `vi_du` | Ví dụ | ✅ `TopicContent.vi_du_json` |
| 6 | `luyen_tap` | Luyện tập – Vận dụng | 🆕 |
| 7 | `bai_tap` | Bài tập | 🆕 |

### 1.2 Thay đổi `TopicContent` 🔶

Giữ nguyên 3 cột đang có (`khai_niem`, `minh_hoa_json`, `vi_du_json`) vì
`tutor._doan_bai`, grounding, `quiz._grounding_text` và `nhac` đang đọc chúng.
Thêm:

```python
khoi_dong:  Mapped[str] = mapped_column(Text, default="")   # HTML
hoat_dong:  Mapped[str] = mapped_column(Text, default="")
luyen_tap:  Mapped[str] = mapped_column(Text, default="")
bai_tap:    Mapped[str] = mapped_column(Text, default="")
bo_cuc_json: Mapped[str] = mapped_column(Text, default="[]")  # [{"id": "...", "an": false}]
```

`bo_cuc_json` rỗng → dùng **thứ tự chuẩn ở 1.1, không phần nào bị ẩn**. Dữ liệu cũ chạy bình thường.

### 1.3 Quy tắc hiển thị — BẮT BUỘC

- Phần có `an: true` **không xuất hiện** ở phía học sinh và **không chiếm số thứ tự**.
  Số hiện là `i+1 / (số phần đang hiện)`, luôn liền mạch `1…n`.
- Kiến thức trọng tâm luôn render trong khung màu cam (`.kttt`) + `h3.kt` để ô 💡 đổi sang cam.
- Kiểm tra nhanh nằm **cuối cùng**, sau cả phần Bài tập.

---

## 2. Vai Chuyên gia (web-admin)

Sidebar 6 mục, nhóm `NỘI DUNG` / `HỆ THỐNG`. Dùng `.sb-link`, `.sb-link.active`.

### 2.1 Tổng quan `🆕`

- 4 ô `.kpi` — markup **đúng hợp đồng**: `<div class="kpi"><div class="ic ic-total">…</div><div class="v tnum">…</div><div class="l">…</div></div>`
  (`ic-total` cam, `ic-warn` vàng, `ic-ok` xanh, `ic-ai` xanh dương). Số: tổng đơn vị · đã soạn đủ 7 phần · yêu cầu cần đạt · đang soạn dở.
- Panel **Tiến độ theo mạch**: mỗi dòng = emoji + tên mạch + số đơn vị + bar + `%`.
  `% = tổng(phần đã soạn) / (số đơn vị × 7)`. Bấm dòng → mở trang nội dung.
- Panel **Việc cần làm**: 4 dòng dạng `số + mô tả + nút đi tới`. Nguồn số liệu:
  đơn vị thiếu `khai_niem`; đơn vị `quiz_json == "[]"`; job nạp sách đang chạy; dòng ma trận điểm khớp < 0.8.

### 2.2 Chương trình & nội dung — 7 phần `🆕`

Danh sách 7 hàng `.ph-o`, mỗi hàng: tay kéo · số thứ tự · emoji · tên + mô tả ·
nhãn `Đang ẩn` (nếu ẩn) · nút `✨ AI hỗ trợ` · `↑` `↓` · `👁/🙈`.

| Hành vi | Kết quả |
|---|---|
| `↑`/`↓` | Đổi thứ tự trong `bo_cuc_json`. Nút đầu/cuối `disabled`. |
| `👁` | Bật/tắt `an`. Hàng ẩn: `opacity .62`, số thành `–`. |
| `✨ AI hỗ trợ` | Sinh gợi ý cho **đúng phần đó**, bám yêu cầu cần đạt của đơn vị. Không sinh cả bài. |
| `Xem như học sinh` | Mở app học sinh với đúng `bo_cuc_json` hiện tại |

Hàng `kien_thuc` có style riêng (`.ph-o.nb`, viền + nền vàng, số nền cam) — nhấn mạnh đây là phần bắt buộc.

Dưới danh sách: panel soạn phần đang chọn, kèm khối **"Bám N yêu cầu cần đạt trong ma trận"**
liệt kê `blueprint_cells` của đơn vị + nhãn mức độ (`.md.nb/.th/.vd`).

### 2.3 Quản lý danh mục `🆕 (UI)`

Cây: `HỌC KỲ n` → mạch (emoji + tên + số đơn vị) → đơn vị (`.dv`: số + tên + `n/7 phần` + pill
`Đủ`/`Đang soạn`/`Chưa soạn`) → **node ôn tập**:

- `🔁 Ôn tập chương · <mạch>` — cuối mỗi mạch, thụt vào cùng cấp đơn vị
- `🏁 Ôn tập cuối học kỳ n` — cuối mỗi học kỳ, không thụt

Node ôn tập **không phải** `CurriculumTopic` mới. Chúng là *view* sinh từ mạch/học kỳ; đề lấy từ
`blueprint_cells` của toàn bộ đơn vị trong phạm vi đó.

### 2.4 Nạp sách bằng AI `✅ luồng đã có, 🆕 UI`

4 ô KPI (sách · trang · đoạn tri thức · % có dẫn nguồn) + panel **Đang nạp** hiển thị 4 bước tuần tự
với bar %: `Đọc trang & nhận dạng công thức` → `Chia đoạn theo mục bài` → `Nhúng vào kho tri thức` →
`Đối chiếu với danh mục chương trình`. + panel danh sách sách trong kho.

### 2.5 Ma trận đặc tả `✅ parser đã có, 🆕 UI đối chiếu`

- Panel tệp đã đọc + 3 số: `khớp chắc chắn` (≥0.8) · `cần xem lại` (0.5–0.8) · `chưa gán` (<0.5)
- Panel tỉ lệ theo 4 mức độ (cộng **một lần cho mỗi nhóm ô gộp**, không cộng từng dòng)
- Bảng ánh xạ: `Mức độ | Yêu cầu cần đạt | Đơn vị kiến thức | Độ khớp %`
  với `.dk.cao/.vua/.thap`. Điểm khớp `0.7×tên đơn vị + 0.3×tên mạch`, chuẩn hoá NFC.
- ❌ **Không tự tạo đơn vị kiến thức mới** từ tên trong .docx. Không khớp thì gán tay hoặc bỏ.
- Nạp tệp = **THAY** toàn bộ ma trận của cặp môn+lớp, không cộng thêm.

---

## 3. Vai Học sinh (web)

### 3.1 Bố cục

- Cột trái: **chỉ danh mục chương trình** — mạch → đơn vị (`.tp-item` với `done/current/next`) →
  `🔁 Ôn tập chương` (`.tp-on`).
- Thanh trên: crumb · `⏱ mm:ss` (đồng hồ phiên, bấm → Hồ sơ) · menu hồ sơ.
- ❌ Không đặt "Hồ sơ học tập" và "Gói của em" ở cột trái — chúng nằm trong menu hồ sơ.

### 3.2 Menu hồ sơ 🔶 (mở rộng `ProfileMenu.tsx`)

Thứ tự trong popover: tên + vai + email → `.hs-so` 3 số (XP tổng · Chuỗi ngày · Đơn vị đạt) →
`📈 Hồ sơ học tập của em` → `💳 Gói của em` + `.hs-phu` tên gói → `🌙 Giao diện` → `⎋ Đăng xuất`.
Mục đang mở được tô sáng. Đóng khi: bấm ngoài (`pointerdown`), `Esc`, hoặc chọn một mục.

### 3.3 Trợ lý theo đoạn 🔶

Mỗi phần có nút `💬 Hỏi về đoạn này` (`.hoi-doan`, mờ `opacity .5`, rõ khi hover `h3`).
Bấm → chèn `.tl-card` **ngay dưới đoạn đó**, có `📍 <tên phần>` và nguồn `📖 Bài đang học · <tên phần>`.

`_NEO_RE` trong `app/api/tutor.py` phải mở rộng:

```python
_NEO_RE = re.compile(
    r"^(khoi_dong|hoat_dong|khai_niem|kien_thuc|minh_hoa|luyen_tap|bai_tap"
    r"|(vi_du|quiz):([1-9]\d?))$")
```

`_doan_bai(c, anchor)` thêm nhánh cho 4 phần mới, trả `(text, nhan)` như hiện tại.
Quy tắc cũ giữ nguyên: anchor `quiz:N` **đòi** đã có `QuizAttempt`, nếu không → 403 với câu
`"Bạn làm bài kiểm tra nhanh xong rồi hỏi mình về câu này nhé!"`.

### 3.4 Kiểm tra nhanh + chỉ về phần sai 🔶

`quiz_json` mỗi câu thêm 2 khoá:

```json
{"q":"…","o":["…"],"a":1,"lv":"de","giai":"…",
 "phan":"kien_thuc","ycd":"Tìm được ƯCLN của hai số"}
```

`app/lessons/quiz.py::_norm_quiz` giữ 2 khoá này; prompt yêu cầu model gắn `phan` theo đoạn nội dung
đã dùng và `ycd` theo yêu cầu cần đạt. `/quiz/submit` trả thêm `phan` + `ycd` trong từng
phần tử `ket_qua`.

**Sau khi nộp**, mỗi câu SAI hiện khối `.sai-nhac` (tông cam) gồm:
`📍 Câu này thuộc phần <emoji tên>` + `Yêu cầu cần đạt: …` + 2 nút
`↑ Đọc lại phần này` (cuộn + loé viền 2.2s, class `.sang`) và `💬 Hỏi trợ lý về đoạn đó`.

Cuối đề: ô tổng kết `n/N câu đúng — đạt|chưa đạt`, `+XP`, và khối `.on-lai` gom **tất cả** phần cần
đọc lại (khử trùng, giữ thứ tự trong bài) + nút `↺ Làm lại đề`.

Số liệu lấy theo code hiện có, **không lấy theo mockup**:
`_NGUONG_DAT = 0.7` · XP = `số câu đúng × _XP_PER_CORRECT(5) + _XP_QUIZ_PASS(10) nếu đạt`
(mockup hiển thị `×10` cho gọn — sai, đừng chép).

### 3.5 Ôn tập chương 🆕

Không có 7 phần. Bố cục: eyebrow `🔁 Ôn tập chương` → tên → lead "Gộp N bài của mạch này, không có bài mới"
→ danh sách bài kèm trạng thái (`✓ đã học` / `• đang học` / `chưa học`) → nếu còn bài chưa xong thì
nói thẳng *"Còn k bài chưa học xong — vẫn ôn được, nhưng đề sẽ có câu thuộc phần em chưa đọc"* →
khối `💡 Cần nhớ` → nút `📝 Làm đề ôn tập (12 câu)`.
Ôn tập cuối kỳ: 30 câu, eyebrow tím `🏁`.

### 3.6 Hồ sơ học tập 🆕

Bốn khối theo thứ tự:

1. **Thời gian học** — 4 ô: hôm nay (kèm `✓ đạt mục tiêu` nếu ≥ mục tiêu) · 7 ngày · từ đầu năm · số phiên.
2. **Biểu đồ 14 ngày** — cột phút/ngày, đường ngang nét đứt = mục tiêu 20′/ngày.
   Ngày không học: vạch xám cao **5px** (không phải 0 — 0 đọc thành "không có dữ liệu").
   Cột hôm nay tô cam.
3. **Lịch sử học tập** — mỗi phiên: ngày/giờ · tên bài · các nhãn `⏱ n phút`,
   `✅ Kiểm tra d/t`, `Đọc x/y phần`, `Hỏi trợ lý n câu`, `● đang học`.
4. **Đạt tới đâu theo yêu cầu cần đạt** — dùng `.pmach` + `.ycd-row` + `.badge.b-dat/b-dang/b-chua`
   sẵn có; thêm `sai n lần` và nút `Học lại ↗` (chỉ hiện khi `sai ≥ 2`) → mở bài + cuộn tới phần đó.
   Giữ đúng thứ tự trong ma trận, **không** sắp lại theo số lần sai.

### 3.7 Gói của em 🆕

Thanh trạng thái gói (`.tt-goi`) + 4 thẻ gói + 3 ô chu kỳ. Nội dung xem §6.

---

## 4. Vai Giáo viên 🆕

- Cột trái: `THCS … · Lớp đọc từ LMS` + nút `↻ Đồng bộ` + danh sách lớp
  (`6A · Toán`, `32 học sinh · chủ nhiệm`, dấu ✓ khớp sĩ số).
- Ba ô ngữ cảnh: Trường · Lớp (+ sĩ số) · Phân công (`Chủ nhiệm` / `Bộ môn <môn>`).
- Bảng tiến độ: `Học sinh | Mã HS | Đơn vị đạt | Thời gian học | Kiểm tra gần nhất | Lần cuối`.
  Em chưa vào học lần nào: hàng mờ, `— / chưa làm / chưa vào lần nào`. Dòng cuối `… còn k em nữa`.
- Câu chốt trên bảng: **`k em chưa vào học lần nào`** — đây là con số giáo viên cần nhất.
- Khối **Cả lớp yếu ở đâu**: top yêu cầu cần đạt theo số em sai, kèm `n/32 em sai ít nhất một lần`.

**Phân quyền:** giáo viên chỉ thấy lớp mình được phân công. Lấy bằng cách gọi API LMS
**bằng token của chính giáo viên đó** (§5), không dùng tài khoản dịch vụ quyền admin.

---

## 5. Tích hợp LMS (LCMS)

### 5.1 Cơ chế mở — đã xác minh trong mã lms-fe

LMS **không mở tab mới**. Route `pages/preview-resource/[source]/[resourceId].js` render
`IframeFullScreen` → học liệu bên thứ ba chạy trong **iframe toàn màn hình trong LMS**.

```
lms-fe  →  /preview-resource/ai_resource/{resourceId}
        →  <iframe src="https://learning.dtpsoft.vn/lms/mo-bai?p=base64(AES(payload))">
```

`payload` (khuôn lấy từ `ResourceService.generatePracticeTestUrl` của iTest):

```json
{ "topicId": 2031, "lmsUserId": 88214, "hoTen": "…", "vaiTro": "STUDENT",
  "branchId": 12, "classroomId": 3391, "resultId": 771902,
  "webhookUrl": "…/ai-resources/submit-result", "webhookPayload": "…",
  "exp": 1755123456 }
```

`exp` là **bắt buộc** (payload iTest hiện không có hạn cho chính cái link).
Phía DTP dùng lại tư duy đã có ở `app/api/security.py` (`_media_sig`/`verify_media`).

### 5.2 Hai đường trả điểm — chọn một, đừng làm cả hai

| | Cách | Ghi chú |
|---|---|---|
| A | `POST /ai-resources/submit-result` từ **server DTP**, kèm `secureToken` | Khuôn iTest. Chữ ký hiện chỉ ký `resultId` → **phải bàn với LMS** mở rộng ký toàn body + timestamp + nonce. |
| B | `postMessage` từ iframe → lms-fe → API LMS | Khuôn DHA/Eduhome (`hooks/useResourceResult.js`, topic `dw.getHistory`). Nhẹ hơn nhưng điểm đi qua client. |

Khuyến nghị: **A**, vì quiz của DTP chấm ở server; gọi webhook từ server giữ được tính chất đó.
Bắt buộc có **retry**; lỗi thì nói thật với học sinh, không im lặng.

### 5.3 Đọc tổ chức từ LMS (chỉ đọc, một chiều) 🆕

| Endpoint LMS (đã có) | Dùng để |
|---|---|
| `GET /classrooms` | Lớp + `studentAmount` + `headTeachers` |
| `GET /classroom-students?classRoomId=` | Học sinh trong lớp (chặn nếu GV không được phân công) |
| `GET /teacher-allocations?classroomId=` | Giáo viên của lớp, `kind=HEAD` = chủ nhiệm |
| `GET /classrooms/current-classroom/{userId}` | Lớp hiện tại của một học sinh |

Bảng mirror chỉ-đọc phía DTP 🆕: `lms_truong`, `lms_lop`, `lms_lop_hoc_sinh`, `lms_gv_lop`
(+ `dong_bo_luc`). **DTP không ghi gì vào LMS.** Phải xử lý học sinh chuyển lớp giữa kỳ
(LMS có `/classroom-students/transfer-class`).

### 5.4 Đối chiếu danh tính 🆕

`users` thêm `lms_user_id` (unique, nullable) + `nguon` (`web|lms`).
Khoá đối chiếu là **id LMS**, ❌ không dùng email (học sinh phổ thông hay không có email, và email
trùng giữa các trường là chuyện thật).

### 5.5 Ngữ cảnh hiển thị cho học sinh

Vào từ LMS thì bài học hiện băng: *"Em là học sinh **lớp 6A · THCS Nguyễn Du** — cô Hạnh chủ nhiệm"*.
Sau khi nộp quiz: *"✓ Đã gửi điểm về sổ điểm lớp 6A"*, và khi webhook lỗi:
*"⚠️ Chưa gửi được điểm về lớp — hệ thống sẽ tự gửi lại."*

---

## 6. Gói & hạn mức

### 6.1 Bốn gói

| Gói | Giá (minh hoạ, chưa chốt) | Hạn mức trợ lý | Khác |
|---|---|---|---|
| Miễn phí | 0đ | **5 lượt/ngày** | Đọc toàn bộ nội dung, làm kiểm tra nhanh, xem video. Không ôn tập chương/cuối kỳ. Hồ sơ 7 ngày. |
| Chuẩn | 99k/th · 399k/học kỳ · 699k/năm | **300 lượt/tháng, trần 30/ngày** | Đủ ôn tập, hồ sơ đầy đủ, làm lại đề 5 lần/bài |
| Gia đình | 149k/th · 599k/kỳ · 1.049k/năm | như Chuẩn, **mỗi em quota riêng** | tối đa 3 học sinh |
| Nhà trường | theo hợp đồng | theo hợp đồng + trần theo trường | kích hoạt bằng **key-code của LMS** |

### 6.2 Nguyên tắc — không thương lượng

- **Nội dung bài học không bao giờ bị khoá.** Chỉ phần AI tính tiền. Chi phí biên thực tế nằm ở
  **lượt hỏi trợ lý**; sinh đề / video / nhắc / nhúng SGK làm một lần rồi dùng chung.
- ❌ **Không có gói "hỏi không giới hạn".**
- Video giữ cache theo `concept_key + sgk_version` (đã unique) — dùng chung mọi học sinh.
  ❌ Không cho sinh video theo yêu cầu từng em.

### 6.3 Hạn mức trong code 🔶

```python
# app/api/tutor.py — thay chỗ lấy giới hạn, giữ fail-open khi Redis lỗi
goi        = await sub_svc.goi_dang_hieu_luc(session, user.id)   # None = miễn phí
tran_ngay  = goi.tran_ngay  if goi else (user.daily_limit_override or settings.chat_daily_limit)
tran_thang = goi.tran_thang if goi else None

# chặn THÁNG trước, rồi mới chặn NGÀY — để thông báo nói đúng cái nào hết
if tran_thang and await incr_quota(f"chatquota:m:{user.id}:{thang}", ttl=32*86400) > tran_thang:
    raise HTTPException(429, "Hết lượt hỏi của tháng này. Gia hạn hoặc nâng gói nhé!")
```

Thứ tự ưu tiên: **gói → `daily_limit_override` → mặc định**. Giữ `daily_limit_override` để vận hành
nâng tay cho từng em.

`GET /tutor/limits` 🔶 hiện chỉ trả `max_chars`; thêm `goi`, `con_lai_thang`, `con_lai_ngay`, `het_han`
để FE hiện thanh trạng thái **trước khi** học sinh hỏi.

### 6.4 Bảng mới 🆕

```
subscriptions(user_id, goi, chu_ky, bat_dau, ket_thuc, trang_thai, nguon)
              nguon: web | keycode | tang
payments(ma_giao_dich UNIQUE, user_id, so_tien, trang_thai, cong, tao_luc, …)
```

Hai kênh tiền (trường mua qua key-code LMS · phụ huynh mua trên web) đổ về **cùng** bảng
`subscriptions`, chỉ khác `nguon`.

### 6.5 Thu tiền 🆕

- ❌ **Không auto-renew ở phase 1.** Bán theo kỳ trả trước; nhắc gia hạn trước 7 ngày.
- IPN phải **idempotent** theo `ma_giao_dich`; ❌ không bao giờ tin số tiền client gửi lên;
  IPN là endpoint công khai nhưng **phải xác thực chữ ký** + giới hạn IP của cổng.
- Hoàn tiền làm tay ở phase 1.
- ❌ Không lưu bất kỳ dữ liệu thẻ nào.

---

## 7. Dữ liệu còn thiếu để làm được §3.6 và §4

| Cần | Vì sao chưa có |
|---|---|
| 🆕 `study_sessions(user_id, topic_id, mo_luc, dong_luc, so_giay)` + ping từ web khi tab đang hiện | Không bảng nào lưu thời lượng học. `duration_sec` đang có là của `VideoJob`. |
| 🆕 chi tiết sai theo yêu cầu cần đạt — khoá **`blueprint_cell_id` + mức độ** | `QuizAttempt` **cố ý** không lưu đáp án đã chọn, vì đề sinh lại thì *chỉ số câu* trỏ sai đề. Đừng lưu theo chỉ số câu. |
| 🔶 `phan` + `ycd` trên từng câu quiz | `quiz_json` hiện chỉ có `{q,o,a,lv,giai}` |

---

## 8. Tổng hợp API

| Endpoint | Trạng thái | Thay đổi |
|---|---|---|
| `POST /tutor/ask` | ✅ | mở rộng `_NEO_RE` + `_doan_bai` cho 4 phần mới |
| `GET /tutor/limits` | 🔶 | thêm `goi`, `con_lai_thang`, `con_lai_ngay`, `het_han` |
| `GET /lessons/{id}` | 🔶 | trả thêm `bo_cuc` (thứ tự + phần ẩn) và 4 phần nội dung mới |
| `POST /quiz/submit` | 🔶 | `ket_qua[]` trả thêm `phan`, `ycd` |
| `POST /lessons/{id}/quiz/generate` | 🔶 | sinh kèm `phan`, `ycd` |
| `GET /me/progress`, `/me/stats` | ✅ | — |
| `GET /me/thoi-gian` (biểu đồ 14 ngày, lịch sử phiên) | 🆕 | từ `study_sessions` |
| `POST /me/phien` (ping thời gian học) | 🆕 | |
| `GET /me/ycd` (đạt tới đâu theo yêu cầu cần đạt) | 🆕 | |
| `GET /gv/lop`, `GET /gv/lop/{id}/hoc-sinh`, `GET /gv/lop/{id}/yeu` | 🆕 | đọc mirror LMS + tiến độ DTP |
| `GET /lms/mo-bai?p=` | 🆕 | giải AES, kiểm `exp`, đối chiếu user, cấp session ngắn |
| `POST /goi/dat`, `POST /goi/ipn` | 🆕 | |
| `POST /cms/topics/{id}/phan/{phan}/ai` | 🆕 | AI hỗ trợ theo từng phần |
| `PUT /cms/topics/{id}/bo-cuc` | 🆕 | lưu thứ tự + ẩn/hiện |

---

## 9. Quy tắc nghiệp vụ bắt buộc

1. Trợ lý trả lời theo thứ tự nguồn: **bài đang học > SGK**. `has_grounding` đúng khi có ít nhất một trong hai.
2. Qdrant lỗi → **vẫn trả lời được** bằng nội dung bài; chỉ 503 khi không có nguồn nào.
3. Semantic cache và quota **fail-open**: Redis lỗi thì cho qua, log một lần.
4. Chấm quiz **ở server**, không gửi đáp án ra client.
5. Không hiển thị nhãn số trang SGK trong câu trả lời (giữ trong `citations`).
6. `max_tokens` cho tác vụ sinh JSON ≥ 16384 — reasoning token dùng chung ngân sách, thấp hơn sẽ bị cắt giữa JSON.
7. Mọi thông báo lỗi hướng tới học sinh phải nói **việc gì đã xảy ra và làm gì tiếp**, không nuốt lỗi.

---

## 10. Checklist hoàn thành

**Nội dung 7 phần**
- [ ] Migration `TopicContent` + `bo_cuc_json`; dữ liệu cũ vẫn mở được
- [ ] Đổi thứ tự / ẩn ở admin → học sinh thấy ngay, số tự tính lại `1…n`
- [ ] Phần ẩn không xuất hiện và không chiếm số
- [ ] `_NEO_RE` nhận đủ 7 phần; hỏi ở phần mới trả lời đúng đoạn

**Kiểm tra nhanh**
- [ ] Mỗi câu sai chỉ đúng phần + yêu cầu cần đạt
- [ ] `↑ Đọc lại phần này` cuộn tới và loé viền
- [ ] Ô tổng kết gom mọi phần cần ôn, khử trùng

**Hồ sơ học tập**
- [ ] `study_sessions` + ping; số hôm nay/tuần/tổng khớp nhau
- [ ] Biểu đồ 14 ngày, ngày nghỉ vẫn thấy vạch
- [ ] `sai n lần` + `Học lại ↗` nhảy đúng phần

**Gói**
- [ ] Quota tháng + trần ngày cùng hoạt động, chặn tháng trước
- [ ] `GET /tutor/limits` đủ thông tin cho thanh trạng thái
- [ ] Hết lượt: **vẫn đọc được bài**, chỉ chặn hỏi

**LMS**
- [ ] `/lms/mo-bai` hết hạn `exp` thì từ chối
- [ ] Đối chiếu theo `lms_user_id`, không theo email
- [ ] Webhook có retry; lỗi thì báo cho học sinh
- [ ] Giáo viên chỉ thấy lớp mình được phân công

---

## 11. Việc KHÔNG làm

- ❌ Tạo hệ màu / component mới khi `learn.css` và `admin.css` đã có
- ❌ Đổi `useMocDoc` sang IntersectionObserver
- ❌ Tạo đơn vị kiến thức mới từ tên trong .docx
- ❌ Gói AI không giới hạn; sinh video theo yêu cầu từng em
- ❌ Lưu chi tiết quiz theo *chỉ số câu*
- ❌ Auto-renew, lưu dữ liệu thẻ, endpoint ghi dữ liệu không xác thực
- ❌ Khoá nội dung bài học khi hết gói
