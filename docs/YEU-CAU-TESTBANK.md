# Gửi team DTP Testbank — bốn việc để nối Gia sư DTP vào kho câu hỏi

Người gửi: team **learning.dtpsoft.vn** (Gia sư DTP — ôn luyện Toán 6 cho học sinh).
Tài liệu này viết sau khi đọc mã nguồn `dtp-testbank` tại `5483cc4`, nên mọi chỗ
nhắc tới file/dòng đều là chỗ thật.

## Tóm tắt

| # | Việc | Chặn gì | Ước lượng |
|---|---|---|---|
| **R1** | Mở đường rút đề từ **kho PUBLIC** | Chặn chạy thật. Dev chạy local được | nhỏ |
| **R2** | Danh tính cho learning gọi sang | Chặn chạy thật | vừa, cần bàn |
| **R3** | Giải thích **theo từng phương án** | Không chặn — tạm dùng AI | vừa |
| **R4** | Nhận kết quả làm bài qua `tracking_code` | Không chặn | để sau |

**Learning không xin quyền ghi vào kho.** Không đụng vòng đời câu hỏi, không tạo
câu, không sửa câu, không gọi `POST /exams`. Chỉ đọc, và chỉ ở kho ôn luyện.

---

## R1 — Mở đường rút đề từ kho PUBLIC

### Hiện trạng

`services/content/src/content_service/routers/pool.py:52`:

```python
KHO_DE_THI = and_(m.Question.kho == Kho.PRIVATE.value, m.Question.parent_qid.is_(None))
```

Hằng số này chặn **cả hai** cửa mà exam-service đi qua:

* `GET /pool` (`get_pool`) — danh sách câu để rút đề;
* `POST /questions:resolve` (`resolve_questions`) — lấy nội dung câu, kèm comment
  giải thích là để người biết QID câu public không moi được nội dung qua đường in đề.

### Vì sao learning cần PUBLIC chứ không phải PRIVATE

Chính các anh đã viết trong `packages/testbank-core/src/testbank_core/enums.py`:

> `PRIVATE` — kho đề thi. […] `PUBLIC` — kho ôn luyện. […] Chiều ngược lại không
> mở: câu đã ra kho ôn luyện là câu học sinh có thể đã thấy, đưa nó trở lại kho đề
> thi là lộ đề.

Learning là sản phẩm **ôn luyện cho học sinh**. Cho học sinh làm bài trên kho
PRIVATE là đi ngược đúng nguyên tắc đó — nên chúng tôi **không** xin mở PRIVATE.

### Đề xuất

Thêm tham số `kho` cho ba chỗ, **mặc định `PRIVATE`** để không đổi hành vi hiện tại:

1. `GET /pool` — thêm query param `kho: str | None`
2. `POST /questions:resolve` — thêm field `kho` vào `ResolveIn`
3. `MatrixIn` (`services/exam/src/exam_service/schemas.py:11`) — thêm `kho`, truyền
   xuống qua `PoolFilters`; `HttpPoolClient.resolve` truyền tiếp

### ⚠️ Một cái bẫy xin lưu ý

**Đừng chỉ đổi giá trị `kho` trong `KHO_DE_THI`.** Hằng số ấy còn có
`parent_qid.is_(None)`, mà kho public thì **toàn là bản nhân bản** — nhân bản luôn
sinh ra ở PUBLIC và luôn có `parent_qid`. Giữ nguyên vế đó cho PUBLIC thì kho rút
đề **luôn rỗng**, và triệu chứng sẽ là `shortage` báo thiếu toàn bộ chứ không phải
một lỗi dễ thấy.

Đại ý:

```python
KHO_DE_THI = and_(m.Question.kho == Kho.PRIVATE.value, m.Question.parent_qid.is_(None))
KHO_ON_LUYEN = m.Question.kho == Kho.PUBLIC.value       # KHÔNG kèm parent_qid
```

Điều kiện `status_code.in_(USABLE)` thì giữ nguyên cho cả hai.

### Không được phá

* Mặc định (không truyền `kho`) phải cho ra **đúng kết quả như hôm nay**.
* Đường PUBLIC không được trả câu chưa `OFFICIAL` — `ensure_chuyen_public` đã bảo
  đảm câu vào PUBLIC đều đã chính thức, chỉ cần đừng nới `USABLE`.
* Phạm vi môn–lớp (`scope_clause`) giữ nguyên, áp như cũ.

### Test nên có

* `/pool?kho=PUBLIC` không trả câu PRIVATE nào, và ngược lại.
* `questions:resolve` với `kho=PUBLIC` **không** lấy được nội dung một QID PRIVATE
  (đây là đúng cái cửa sau mà comment hiện tại đang chặn).
* Không truyền `kho` → kết quả không đổi so với trước.
* Kho PUBLIC rút được đề thật — test này sẽ bắt đúng cái bẫy `parent_qid` ở trên.

---

## R2 — Danh tính để learning gọi sang

### Xin đính chính một điều chúng tôi từng nói sai

Trong bản trao đổi trước, chúng tôi có nói "mỗi học sinh làm một đề sẽ ăn vào hạn
mức đề theo tháng của giáo viên". **Điều đó không đúng.** Đọc lại thì
`q.require_available` chỉ được gọi ở `POST /exams` (lưu đề) —
`routers/exams.py:170` — còn `POST /exams:preview` thì không. Đúng như docstring
của `quota.py` viết: *"Chỉ lần dựng đề đầu tiên mới trừ. Xem trước, mở lại, in lại
đều không trừ."*

Learning chỉ cần `:preview` (đề của học sinh lưu ở hệ thống chúng tôi, không cần
lưu bên các anh), nên **hạn mức không phải vấn đề**. Xin lỗi vì đã nói nhầm.

### Vấn đề thật

`services/exam/src/exam_service/pool.py` ghi rõ một tính chất mà chúng tôi **muốn
giữ**, không muốn phá:

> Mọi lần gọi đều mang token của chính người dùng. exam-service không có tài khoản
> riêng để "gọi hộ", nên không thể vô tình rút được câu mà người đó không có quyền
> thấy.

Nhưng identity hiện chỉ có 5 vai nội bộ + `TEACHER`, và học sinh của learning không
phải người dùng của testbank. Mượn một tài khoản `TEACHER` thật thì chạy được ngay,
đổi lại: mọi học sinh chung một danh tính, nhật ký không truy được ai, và phạm vi
của tài khoản ấy quyết định tất cả.

### Hai hướng, chúng tôi nghiêng về hướng A

**A. Một vai riêng cho đối tác đọc kho ôn luyện** — `LEARNING` (hoặc
`PARTNER_READONLY`), kèm phạm vi môn–lớp như mọi vai khác:

* trong `ACTION_ROLES` chỉ được `exam.pool`;
* **chỉ được `kho=PUBLIC`** — gọi với `PRIVATE` thì 403, chặn ở tầng quyền chứ
  không trông vào việc client tự giác;
* không được `POST /exams`, không đụng vòng đời, không ghi gì.

Hướng này có mất tính chất "không gọi hộ", nhưng mất ở đúng một đường và đường ấy
chỉ chạm kho ôn luyện — thứ vốn đã được chấp nhận là "học sinh có thể đã thấy".

**B. Learning gửi kèm định danh học sinh** — thêm claim kiểu `on_behalf_of` để nhật
ký truy được tới từng học sinh. Làm được thì tốt, nhưng nó là bài toán của cả hệ
thống tài khoản, không nên chặn demo.

Đề nghị: làm **A** trước, ghi sẵn chỗ cho **B**.

### Learning cam kết

* `answer_key` **không bao giờ** rời máy chủ learning — chấm ở server, client chỉ
  nhận đúng/sai sau khi nộp. (Chúng tôi vẫn cần `include_answers=True` ở đường
  server-to-server để chấm được.)
* Không gọi `POST /exams`, không gọi bất kỳ đường ghi nào.
* Không truy cập kho PRIVATE, kể cả khi token lỡ cho phép.

---

## R3 — Giải thích theo TỪNG phương án

### Hiện trạng

`question_version.explanation` là **một** lời giải cho cả câu. Các anh đã xác nhận
chưa có giải thích riêng từng phương án.

Nhưng cấu trúc "theo từng đáp án" thì **đã có sẵn**, trong
`question_resource.option_key` — và comment của chính nó mô tả đúng việc chúng tôi
đang làm:

> Gắn cho MỘT đáp án cụ thể (vòng lặp "học sinh chọn sai → đúng học liệu đúng chỗ
> sai" — xem sơ đồ sản phẩm).

Cùng với hai loại `CUNG_CO` / `ON_LAI` trong `routers/resources.py`. Nói cách khác
bản thiết kế đã tính tới vòng lặp này; chỗ còn thiếu chỉ là **chữ giải thích**.

### Vì sao cần

Yêu cầu nghiệp vụ: học sinh nộp bài xong, mỗi phương án đều nói được *vì sao đúng*
hoặc *vì sao sai* — "36 là BCNN(12;18) chứ không phải ƯCLN" chẳng hạn. Một lời giải
chung cho cả câu không trả lời được câu hỏi "vì sao **em** chọn D lại sai".

### Đề xuất

Bảng riêng, khoá `(qid, option_key)`, **theo đúng lối `QuestionOptionTag`**:

```python
class QuestionOptionRationale(Base):
    __tablename__ = "question_option_rationale"
    qid: Mapped[str] = mapped_column(ForeignKey("question.qid", ondelete="CASCADE"), primary_key=True)
    option_key: Mapped[str] = mapped_column(String(4), primary_key=True)
    rationale: Mapped[str] = mapped_column(Text)
```

Không nhét vào JSON `QuestionVersion.options` — vì đúng lý lẽ các anh đã viết cho
`QuestionOptionTag`: *"Một cột trong JSON không cho được ba thứ đó"* (duy nhất, tra
được, không vỡ khi đổi phiên bản).

Vai: dùng lại action `question.resource` đã có (EDITOR / VARIANT_EDITOR /
COORDINATOR) — cùng tính chất "sửa nội dung", không cần vai mới.

**Để learning chỉ gọi một lượt**, xin trả kèm trong `ResolvedQuestion`:

```python
option_rationales: dict[str, str] = Field(default_factory=dict)   # {"A": "...", "B": "..."}
```

### Một câu hỏi thiết kế xin các anh quyết

`QuestionResource` và `QuestionOptionTag` cố ý **không theo phiên bản**, lý do ghi
rõ: *"sửa lại diễn đạt một câu không làm nó trỏ vào trang sách khác"*. Với lời giải
từng phương án thì lập luận ấy **yếu hơn**: sửa chữ của phương án D có thể làm lời
giải "vì sao D sai" thành sai theo.

Chúng tôi nghiêng về **theo đúng tiền lệ (không versioned)** cho nhất quán và đỡ
phiền người nhập, nhưng đây là nghiệp vụ của các anh — chúng tôi chỉ nêu rủi ro.

### Nếu chưa làm kịp thì không sao

Learning sẽ tự sinh bằng AI rồi cache: đo thật khoảng **67đ cho một đề 12 câu**,
sinh một lần dùng chung mọi học sinh. Bản chính thức vẫn nên là bản có người duyệt
của các anh — chúng tôi thiết kế chỗ lưu sao cho đổi nguồn không phải sửa giao diện.

---

## R4 — Nhận kết quả làm bài (không chặn demo)

`question_option_tag.tracking_code` đã mô tả đúng việc này:

> khoá nối giữa kết quả làm bài nạp từ ngoài hệ thống và câu hỏi/học liệu trong kho

Đề xuất một đường nhận theo lô:

```
POST /ket-qua-lam-bai
[{"tracking_code": "...", "dung": false, "luc": "2026-10-17T09:12:00Z"}, ...]
```

Giá trị: kho biết **phương án nhiễu nào thật sự bẫy được học sinh** — số liệu thật
để nuôi `Psychometrics`, thay vì chỉ có `p_value` từ đợt thử nghiệm.

Việc này biến learning từ "bên tiêu thụ đề" thành "bên làm đề tốt lên", nhưng nó
không chặn gì cả — làm sau demo cũng được.

---

## Một câu hỏi chuyên môn, không phải kỹ thuật

Mỗi YCCĐ gắn **đúng một kỳ** (`ar.exam_code`, unique theo
`year/subject/grade/exam/seq`), nên `exam: "CK1"` chỉ rút trong các YCCĐ gắn nhãn
CK1. Nhưng **đề cuối kỳ 1 ở trường thường phủ cả học kỳ**, tức gồm cả YCCĐ nhãn GK1.

Với dữ liệu mồi hiện tại, Toán 6 chỉ có **3 YCCĐ** gắn CK1, nên xin 12 câu là chắc
chắn `shortage`. Chúng tôi xử lý được về mặt kỹ thuật (hiện thông báo rõ), nhưng
"đề cuối kỳ nên phủ những YCCĐ nào" là câu hỏi của tổ chuyên môn, xin các anh hỏi
giúp bên biên soạn.

---

## Chúng tôi test thế nào ở phía mình

Không cần chờ các anh mở gì: chúng tôi dựng testbank ở máy dev theo README

```bash
make install && make dev-setup && make dev     # :8002 :8001 :8003
make dev-pool
```

và viết client chạy với dữ liệu mồi. Nên **R1/R2 chỉ chặn lúc chạy thật**, không
chặn chúng tôi code.

Chúng tôi cũng đã chép quy tắc chuẩn hoá nguyên văn YCCĐ từ
`services/content/src/content_service/ar_key.py` sang phía mình, và có test đối
chiếu thẳng bản Python với biểu thức SQL của các anh trên cùng bộ mẫu (gồm NBSP,
thin space, NFD) — để hai bên không bao giờ gom khác nhau. Nếu quy tắc ấy đổi, xin
báo: đó là chỗ lệch nhau mà **không bên nào có lỗi hiện ra**.

---

## Liên hệ

Kèm theo tài liệu này có một mockup HTML chạy được, mô tả toàn bộ luồng 4 bước và
đánh dấu rõ chỗ nào đã có / chỗ nào đang xin:
`dtp-chat-learning-tdd/ui-design/mockups/demo-4-buoc.html`
