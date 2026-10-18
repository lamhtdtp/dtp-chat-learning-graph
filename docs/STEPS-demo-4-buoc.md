# Các bước triển khai demo 4 bước (Learning × DTP Testbank)

Kèm mockup: `../dtp-chat-learning-tdd/ui-design/mockups/demo-4-buoc.html`

Yêu cầu demo:
1. Vào xem content theo bài học
2. Sinh một đề thi cuối kỳ (12 câu) lấy từ testbank
3. Làm bài, ra kết quả — mỗi phương án đều giải thích tại sao đúng / tại sao sai
4. Từ kết quả, gợi ý tài liệu bổ sung và bài làm mới, chọn theo YCCĐ

## Trạng thái (18/10/2026)

A–D đã làm, chạy đầu-cuối với testbank local. Testbank đã trả lời bằng
`dtp-testbank/docs/24-HUONG-DAN-API-CHO-LEARNING.md` — **đọc tài liệu đó trước phần
dưới**, vì nó đính chính mấy chỗ trong bản này:

- **E1, E2 đã xong phía testbank.** Mọi lần rút đề chỉ lấy kho PUBLIC (không còn
  tham số `kho`); learning dùng tài khoản dịch vụ vai `DOI_TAC_ON_LUYEN`. B2/B4
  không còn là "cách tạm cho dev".
- Đường lấy nội dung là `POST /questions:resolve` của content (không phải
  `/pool/questions:resolve`). Trường kỳ tên `exam`.
- Kho thật có đủ dạng `TN1 TNN DS DSN TL`, không chỉ trắc nghiệm — giao diện và
  chấm bài làm cả năm dạng (`app/integrations/testbank/cham.py`, luật chép từ §7).
- Công thức phần lớn là **ảnh** `[[anh:…]]` → lý do từng phương án (C1) chỉ sinh
  được cho câu chữ thuần; đo trên đề CK1 local: 1/12 câu. Muốn phủ hết phải cho
  model đọc ảnh, hoặc chờ testbank làm R3 (`rationale` theo `option_key`).
- YCCĐ khớp nguyên văn 41/41 với ma trận Toán 6 của mình (B5).

Mã: `app/integrations/testbank/`, `app/exam/ly_do.py`, `app/api/cuoi_ky.py`,
`web/src/learn/CuoiKyView.tsx`. Cấu hình: khối `TESTBANK_*` trong `.env.example`.

---

## Điều quan trọng nhất trước khi chia việc

**Không phải chờ testbank mở API mới làm được.** Testbank chạy đủ ở máy dev:

```bash
cd ~/dev/dtp/dtp-testbank
make install && make dev-setup && make dev     # identity :8002 · content :8001 · exam :8003
make dev-pool                                  # terminal thứ 2 — đưa câu mồi lên OFFICIAL
```

Dữ liệu mồi có sẵn **Toán 6, kỳ CK1, gắn đúng YCCĐ** (`AR_ROWS` trong
`services/content/src/content_service/seed.py`). Tài khoản
`gv.toan6@truong-a.edu.vn` / `testbank2026`.

Nên: toàn bộ nhánh A–D dưới đây làm được **ngay hôm nay**. Thứ thật sự bị chặn
chỉ là **chạy thật trên production** — xem nhánh E.

Hai điều cần nhớ khi đọc tiếp:

- Testbank gắn câu hỏi theo **YCCĐ** (`question.ar_id` → `ar.yccd_text`), cùng
  một trục với `blueprint_cells.yeu_cau_can_dat` bên mình. **Không cần tầng ánh
  xạ** như bản i-Test cũ.
- Đề hiện chỉ rút từ **kho PRIVATE** (kho đề thi). Cho học sinh ôn luyện xem là
  lộ đề. Đây là chặn thật, không phải chi tiết kỹ thuật.

---

## Nhánh A — Dọn nền (làm trước, không phụ thuộc gì)

### A1. Xoá tàn dư i-Test

Code i-Test đã bị xoá ở commit `06c841f`, `app/integrations/` giờ chỉ còn
`__init__.py`, nhưng cấu hình thì vẫn nằm đó và sẽ đánh lừa người đọc sau:

- `app/config.py:35-36` — xoá `itest_database_url`, `itest_cdn_base`
- `pyproject.toml` — xoá optional-dependency group `itest` (`pymysql`)

**Kiểm chứng:** `grep -ri itest app/ pyproject.toml` không còn kết quả.

### A2. Thêm `httpx` vào dependencies

Dự án **chưa khai báo** `httpx`. Hiện `import httpx` vẫn chạy được vì
`anthropic`/`openai` kéo theo — đó là phụ thuộc ngầm, hỏng im lặng khi hai gói
kia đổi phiên bản.

- `pyproject.toml` → thêm `"httpx>=0.27"` vào `dependencies`

### A3. Lưu lựa chọn của học sinh theo khoá bền  ← chặn nhánh ④

`QuizAttempt` (`app/db/models.py:120`) **cố ý không lưu đáp án đã chọn**, lý do
ghi ngay trong docstring: đề sinh lại thì *chỉ số câu* trỏ sai đề. Lý do đó
đúng, nhưng giờ đã có khoá bền thay thế: **`ar_id`**.

Bảng mới `quiz_attempt_items`:

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `attempt_id` | FK `quiz_attempts.id` | |
| `ar_id` | `String(32)` index | **khoá bền** — `AR26-TO06-CK1-001` |
| `qid` | `String(16)` nullable | mã câu testbank, NULL nếu câu do AI sinh |
| `phan` | `String(24)` | id phần nội dung để trỏ về bài học |
| `chon` | `String(16)` | học sinh chọn gì — `"B"`, `"A,C"` |
| `dung` | `bool` | |

Không lưu chỉ số câu. Thêm migration mới (gần nhất đang là
`f6a7b8c9d0e1_add_topic_content_quiz`).

**Kiểm chứng:** nộp bài hai lần với hai đề sinh khác nhau, truy được "sai YCCĐ
nào mấy lần" mà không phụ thuộc thứ tự câu.

### A4. Thống kê điểm yếu theo YCCĐ

Hàm mới trong `app/lessons/` (hoặc nối vào `GET /lessons/me/ycd` đang có ở
`app/api/lessons.py:488`): trả về danh sách `ar_id` kèm `dung/tong` trong N lần
nộp gần nhất, sắp theo tỉ lệ sai giảm dần.

Đây là đầu vào của `ar_ids` ở bước ④.

---

## Nhánh B — Client gọi testbank (làm song song nhánh A)

Thư mục mới `app/integrations/testbank/`.

### B1. `settings.py` + `client.py`

- Ba base URL (identity / content / exam) — mỗi service một cổng, đừng gộp một
  biến rồi tự ghép path.
- `httpx.AsyncClient` dùng lại, **timeout tường minh** (connect 5s / read 20s —
  rút đề có gọi model phía họ).
- Lỗi mạng / 5xx của testbank **không được thành 500 của mình**: map sang 503
  kèm thông điệp tiếng Việt, cùng lối với cách `app/api/tutor.py` xử lý Qdrant
  chết.

### B2. `auth.py` — lấy token

`POST /auth/login` ở identity trả `access_token` (RS256). Cache token trong
Redis, refresh trước khi hết hạn.

**Lưu ý:** đây là cách làm **tạm cho môi trường dev**. Production phải dùng vai
máy-sang-máy (E2) — xem lý do ở đó.

**Hạn mức đề KHÔNG phải vấn đề.** `q.require_available` chỉ được gọi ở
`POST /exams` (lưu đề), không ở `:preview` — đúng như `quota.py` viết: *"Chỉ lần
dựng đề đầu tiên mới trừ. Xem trước, mở lại, in lại đều không trừ."* Learning chỉ
dùng `:preview` nên không tiêu hạn mức của ai. (Bản trước của tài liệu này nói
ngược lại — đã sửa.)

### B3. `exam.py` — rút đề

Gọi `POST /exams:preview`:

```json
{ "subject": "TO", "grade": "06", "exam": "CK1", "total": 12,
  "ratio": {"B": 40, "H": 30, "V": 30}, "seed": 20261016,
  "spread_ar": true, "ar_ids": null }
```

- `ar_ids` = `null` cho đề cuối kỳ đầy đủ; = danh sách YCCĐ yếu cho "bài làm
  mới" ở bước ④. **Tham số này đã có sẵn**, không phải xin thêm.
- `seed` cố định → cùng đề. Dùng seed cố định khi demo để buổi trình bày lặp lại
  được; sinh ngẫu nhiên khi chạy thật.
- Trả về `quota`, `shortage`, `covered_ars`, và `items[]` chỉ có **metadata**
  (`qid`, `ar_id`, `difficulty_code`, `format_code`, `domain_code`) — **không có
  đề bài**. Nội dung lấy ở lượt gọi sau.

Phân bổ `total: 12` + `ratio 40/30/30` → **B 5 / H 4 / V 3** (đã chạy thật
`testbank_core.exam.allocate`). Dùng con số này để viết test.

**Phải xử lý `shortage`:** kho mồi chỉ có 3 YCCĐ gắn CK1, nên đòi 12 câu sẽ
thiếu. Thiếu thì **báo rõ ra màn hình**, đừng lặng lẽ trả đề ngắn hơn.

### B4. `noi_dung.py` — lấy đề bài và đáp án

`POST /pool/questions:resolve` với danh sách `qids`, trả `stem`, `options`,
`answer_key`, `explanation`, `assets`.

**Hai ràng buộc cứng:**
- `answer_key` **không bao giờ** được gửi xuống trình duyệt trước khi nộp. Chấm
  ở server, như `POST /lessons/quiz/submit` đang làm.
- Endpoint này hiện **khoá cứng vào kho PRIVATE** (`KHO_DE_THI` trong
  `routers/pool.py:52`), kèm comment giải thích là để chặn moi nội dung câu
  public qua đường in đề. Dev được ở local; production chờ E1.

### B5. Khớp YCCĐ hai bên

Testbank so khớp nguyên văn YCCĐ bằng khoá chuẩn hoá. Quy tắc nằm ở
`services/content/src/content_service/ar_key.py` — **chép đúng, đừng tự nghĩ lại**:

```python
# NFC → gộp khoảng trắng → strip → lower. KHÔNG bỏ dấu, KHÔNG cắt dấu câu.
_KHOANG_TRANG.sub(" ", unicodedata.normalize("NFC", text)).strip().lower()
```

Khớp lỏng tay ở đây là gắn câu hỏi vào YCCĐ sai mà **không có gì báo cho ai
biết**. Không khớp thì báo lỗi, đừng đoán theo độ giống.

Lưu bảng đối chiếu `ar_id` ↔ `blueprint_cells.id` để bước ④ trỏ ngược về đúng
phần nội dung bài học.

### B6. Endpoint cho frontend

- `POST /exam/cuoi-ky/generate` — body `{subject, grade, exam, total, ar_ids?}`,
  trả đề đã kèm đề bài + phương án, **không kèm đáp án**
- `POST /exam/cuoi-ky/submit` — chấm server, ghi `quiz_attempts` +
  `quiz_attempt_items` (A3), trả kết quả từng câu kèm `ar_id` / `phan` / lý do
  từng phương án

Áp quota như `app/api/tutor.py` đang làm, và chặn trước khi gọi sang testbank.

---

## Nhánh C — Giải thích từng phương án

Testbank hiện chỉ có **một** `explanation` cho cả câu
(`question_version.explanation`) — team testbank đã xác nhận chưa có giải thích
từng phương án.

### C1. Sinh bằng AI và cache (đường cho demo)

- Task mới `rationale_gen`, **tầng rẻ** (`gemini-3.1-flash-lite`) trong
  `TASK_TIER` — cùng tầng với `qa`.
- Đầu vào: `stem`, `options`, `answer_key`, `explanation` lấy từ B4. Có đáp án
  đúng và lời giải gốc rồi thì việc còn lại chỉ là diễn giải từng phương án —
  không cần tầng mạnh.
- **Sinh SẴN ngay lúc tạo đề, cache cùng chỗ với đề.** Sinh lúc nộp bài là học
  sinh ngồi chờ 48 lượt gọi model (12 câu × 4 phương án).
- Chi phí đo thật: **~67đ cho 12 câu**, một lần, mọi học sinh dùng chung.

Ràng buộc khi sinh: giữ nguyên đáp án đúng, không được "giải thích" một phương
án sai thành đúng. Phương án nào model trả về thiếu thì bỏ dòng đó, đừng vá tạm
— cùng lối với `app/lessons/quiz.py::_parse_quiz`.

### C2. Chuyển sang nguồn chính thức (bản thật)

Khi testbank làm xong E3, đọc `rationale` theo `option_key` từ họ và **ưu tiên
hơn** bản AI. Thiết kế chỗ lưu ngay từ C1 sao cho đổi nguồn không phải sửa
frontend.

---

## Nhánh D — Giao diện

Mockup đã chốt bố cục, lấy thẳng từ đó.

- **D1.** Màn làm đề: dùng lại `.ex-card` / `.opt` của `LessonView`, thêm
  `.b4-pa` bọc ngoài + `.opt-ly` cho lý do từng phương án.
- **D2.** Màn kết quả: chấm theo **YCCĐ** (`.pmach` + `.ycd-row` + `.badge`),
  không phải theo số câu.
- **D3.** Khối gợi ý: học liệu theo đáp án đã chọn sai + nút "làm bài mới" gọi
  lại B6 với `ar_ids`.
- **D4.** Vá lỗi tương phản của `learn.css` — `.opt.correct` đang hiện đáp án
  đúng ở mức **2.27:1** (nhạt hơn chữ thường), `.opt.wrong` 2.71:1. Gốc là bộ
  token thiếu `--teal-ink`. Bản vá đã viết sẵn trong khối đề xuất của mockup.

---

## Nhánh E — Phải xin testbank (người khác làm, song song)

| # | Xin gì | Vì sao | Chặn cái gì |
|---|---|---|---|
| **E1** | Tham số `kho: "PUBLIC"` cho `/exams:preview`, và một đường lấy nội dung tương ứng | Đề hiện chỉ rút kho đề thi thật; cho học sinh xem là lộ đề | **Chặn production.** Dev chạy local được |
| **E2** | Vai + token máy-sang-máy cho learning | Identity không có vai nào cho learning; mượn tài khoản `TEACHER` thì mọi học sinh chung một danh tính, nhật ký không truy được ai | **Chặn production** |
| **E3** | Cột `rationale` theo `option_key` | Chỗ để đã có sẵn cạnh `question_resource.option_key` | Không chặn — C1 làm tạm |
| **E4** | Nhận kết quả làm bài qua `question_option_tag.tracking_code` | Khép vòng lặp: kho biết phương án nhiễu nào thật sự bẫy được học sinh | Để sau demo |

Kèm một câu hỏi **chuyên môn**, không phải kỹ thuật, cần tổ Toán chốt:

> Mỗi YCCĐ gắn **đúng một kỳ** (`ar.exam_code`), nên `exam: "CK1"` chỉ rút trong
> các YCCĐ gắn nhãn CK1. Đề cuối kỳ 1 thật thường phủ cả học kỳ, tức là cả YCCĐ
> nhãn GK1. Không mở rộng thì 12 câu dồn vào rất ít YCCĐ và `shortage` báo thiếu
> ngay trong buổi demo.

---

## Thứ tự đề nghị

```
Ngày 1   A1 A2 (nửa buổi)  →  B1 B2 B3   ‖   A3 A4 (migration + thống kê)
Ngày 2   B4 B5             ‖   C1 (sinh + cache rationale)
Ngày 3   B6                →  D1 D2
Ngày 4   D3 D4             →  chạy thử đầu-cuối trên testbank local
         E1 E2 chạy song song từ ngày 1 — không chặn ngày 1–4
```

Hai nhánh `‖` làm song song được vì không đụng file nhau.

## Xong là xong cái gì

- [ ] Học sinh mở bài học → bấm "Làm đề cuối kỳ" → nhận đúng 12 câu từ testbank
      local, phân bổ B5/H4/V3
- [ ] Nộp bài → mỗi phương án có một dòng lý do, đáp án đúng đọc được rõ
- [ ] Kết quả chấm theo YCCĐ, không theo số câu
- [ ] Bấm "làm bài mới" → đề mới chỉ gồm các YCCĐ còn yếu
- [ ] `shortage` và lỗi testbank chết đều hiện thông điệp tiếng Việt, không phải 500
- [ ] Không có `answer_key` nào trong payload gửi xuống trình duyệt trước khi nộp
