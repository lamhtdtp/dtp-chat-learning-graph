# Đổi tên API sang tiếng Anh — bảng tên (bản nháp chờ duyệt)

Phạm vi đã chốt (21/10/2026): **toàn bộ đường dẫn + toàn bộ tên trường JSON** của API.

## 0. Quy ước

- Đường dẫn: chữ thường, gạch ngang (`/exam/final/practice-more`). Tham số đường dẫn: snake_case (`{assignment_id}`).
- Tên trường JSON và query param: `snake_case` tiếng Anh.
- **Không đổi trong đợt này** (đề xuất — cần xác nhận):
  - **Giá trị** dạng mã (enum) trả trong JSON: `"dat"/"dang"/"chua"`, `"de"/"trung_binh"/"kho"`, `"nhanh"/"on_tap"/"luyen_them"/"cuoi_ky"/"de_giao"`, `"on_lai"/"cung_co"`, id phần bài (`kien_thuc`, `vi_du`…). Đổi giá trị là đổi cả dữ liệu trong DB và mọi chỗ so sánh — tách thành đợt sau nếu muốn.
  - **Tên bảng / tên cột DB** (`de_cuoi_ky`, `ycd_key`…): không phải API, giữ nguyên.
  - Trường lấy nguyên từ DTP Testbank (`qid`, `ar_id`, `answer_key`, `format_code`…): đã là tiếng Anh.
- Thông điệp lỗi `detail` gửi học sinh vẫn là **tiếng Việt** (đó là chữ hiển thị, không phải tên).
- Không giữ đường cũ song song: backend + 2 frontend deploy cùng lúc. Học sinh đang mở trang lúc deploy phải tải lại trang.

## 1. Đường dẫn

| Hiện tại | Đề xuất |
|---|---|
| `GET /admin/users/{user_id}/result` | `GET /admin/users/{user_id}/results` |
| `GET /cms/danh-muc` | `GET /cms/units` |
| `POST /cms/danh-muc/gop` | `POST /cms/units/merge` |
| `GET /cms/danh-muc/trung` | `GET /cms/units/duplicates` |
| `GET,POST /cms/hoc-lieu` | `GET,POST /cms/resources` |
| `GET /cms/hoc-lieu/ma-ke-tiep` | `GET /cms/resources/next-code` |
| `GET /cms/hoc-lieu/video-noi-bo` | `GET /cms/resources/internal-videos` |
| `GET /cms/hoc-lieu/ycd` | `GET /cms/resources/requirements` |
| `PATCH,DELETE /cms/hoc-lieu/{hoc_lieu_id}` | `PATCH,DELETE /cms/resources/{resource_id}` |
| `GET /cms/kho-sgk` | `GET /cms/textbooks` |
| `GET /cms/ma-tran` | `GET /cms/matrix` |
| `POST /cms/ma-tran/nap` | `POST /cms/matrix/import` |
| `POST /cms/sach/doc-thu` | `POST /cms/books/trial-read` |
| `GET /cms/sach/jobs` | `GET /cms/books/jobs` |
| `GET /cms/sach/jobs/{job_id}` | `GET /cms/books/jobs/{job_id}` |
| `POST /cms/sach/jobs/{job_id}/lenh` | `POST /cms/books/jobs/{job_id}/command` |
| `POST /cms/sach/nap` | `POST /cms/books/ingest` |
| `GET /cms/sach/soat` | `GET /cms/books/review` |
| `POST /cms/sach/tep` | `POST /cms/books/files` |
| `POST /cms/sach/tep/gan` | `POST /cms/books/files/attach` |
| `GET /cms/tong-quan` | `GET /cms/overview` |
| `POST /cms/topics/{topic_id}/anh` | `POST /cms/topics/{topic_id}/image` |
| `PUT /cms/topics/{topic_id}/bo-cuc` | `PUT /cms/topics/{topic_id}/layout` |
| `POST /cms/topics/{topic_id}/nhac/generate` | `POST /cms/topics/{topic_id}/nudges/generate` |
| `POST /cms/topics/{topic_id}/phan/{phan}/ai` | `POST /cms/topics/{topic_id}/sections/{section}/ai` |
| `POST /cms/topics/{topic_id}/vi-du/{chi_so}/anh` | `POST /cms/topics/{topic_id}/examples/{index}/image` |
| `GET /de-giao` | `GET /exam/assignments` |
| `POST /de-giao/xem-truoc` | `POST /exam/assignments/preview` |
| `GET /de-giao/{de_id}` | `GET /exam/assignments/{assignment_id}` |
| `GET /de-giao/{de_id}/ket-qua` | `GET /exam/assignments/{assignment_id}/results` |
| `GET /de-giao/{de_id}/bai/{user_id}` | `GET /exam/assignments/{assignment_id}/attempts/{user_id}` |
| `POST /de-giao/{de_id}/dong` | `POST /exam/assignments/{assignment_id}/close` |
| `POST /de-giao/{nhap_id}/cap-ma` | `POST /exam/assignments/{assignment_id}/issue-code` |
| `DELETE /de-giao/{nhap_id}` | `DELETE /exam/assignments/{assignment_id}` |
| `POST /de-giao/vao` | `POST /exam/assignments/join` |
| `POST /de-giao/nop` | `POST /exam/assignments/submit` |
| `GET,DELETE /exam/cuoi-ky` | `GET,DELETE /exam/final` |
| `POST /exam/cuoi-ky/generate` | `POST /exam/final/generate` |
| `POST /exam/cuoi-ky/submit` | `POST /exam/final/submit` |
| `POST /exam/cuoi-ky/test-them` | `POST /exam/final/practice-more` |
| `GET,DELETE /exam/cuoi-ky/{de_id}` | `GET,DELETE /exam/final/{exam_id}` |
| `POST /lessons/{topic_id}/luyen-them` | `POST /lessons/{topic_id}/practice` |
| `POST /lessons/luyen-them/submit` | `POST /lessons/practice/submit` |
| `POST /me/phien` | `POST /me/sessions` |
| `GET /me/thoi-gian` | `GET /me/study-time` |
| `GET /me/ycd` | `GET /me/requirements` |
| `GET /on-tap` | `GET /review` |
| `GET /on-tap/de` | `GET /review/exam` |
| `POST /on-tap/submit` | `POST /review/submit` |

Giữ nguyên (đã tiếng Anh): `/admin/overview`, `/admin/users*` (trừ `result`), `/auth/*`, `/cms/catalog`, `/cms/curriculum`, `/cms/limits`, `/cms/topics/{topic_id}` (+ `ai-ingest`, `quiz/generate`, `video`), `/curriculum`, `/health`, `/lessons/{topic_id}` (+ `quiz/generate`), `/me/stats`, `/progress*`, `/quiz/submit`, `/tutor/*`, `/video/*`.

**Hệ quả cho nginx trên server:** tiền tố `de-giao` biến mất (giao đề chuyển vào `/exam`, đã có sẵn) → hết lỗi 405 của `/de-giao/vao`; tiền tố `on-tap` đổi thành `review` → phải sửa danh sách tiền tố trong nginx thật của **cả hai** khối một lần nữa.

## 2. Tên trường JSON

Bảng đầy đủ (~300 khoá) ở mục 3 — soạn sau khi mục 1 và các quy ước ở mục 0 được duyệt.
