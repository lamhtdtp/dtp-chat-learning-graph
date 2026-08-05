---
name: dtp-mockup
description: Bảo trì & mở rộng bộ mockup HTML "giải pháp Gia sư DTP Lớp 6" trong folder mockup/ (mục lục Mạch→Đơn vị, bài học 4 phần, tiến độ HS, slide GV, CMS chuyên gia). Dùng khi cần thêm màn/nội dung/tính năng vào mockup, đổi mục lục theo file ma trận, hoặc chuẩn bị nối backend.
---

# Mockup giải pháp Gia sư DTP (folder `mockup/`)

Bộ **prototype HTML tĩnh, data giả, bấm được** để chốt hướng giải pháp theo meeting
note trước khi code thật. **Không** có build step, **không** framework — mở thẳng file
`.html` bằng trình duyệt (file://) là chạy.

## Khi nào dùng skill này
- Thêm/sửa màn hình hoặc thành phần trong mockup.
- Đổi mục lục cho khớp file ma trận (`data/matrix/TOAN_6_HK1.docx`).
- Thêm trường nội dung bài học / bước CMS.
- Trước khi nối backend: đối chiếu mockup ↔ schema/endpoint dự kiến.

## Bản đồ file
```
mockup/
  index.html      Bản tổng hợp: app-bar (Học sinh/Giáo viên) + Mục lục + tabs. Link 🧑‍🔬 CMS.
  bai-hoc.html    LessonView 1 đơn vị (?role=gv để kèm hướng dẫn dạy).
  tien-do.html    Tiến độ học sinh theo yêu cầu cần đạt.
  slide-gv.html   Slide giảng dạy (← → chuyển slide).
  cms.html        CMS chuyên gia: tab "Cấu trúc & Nạp sách" + tab "Biên soạn".
  assets/
    style.css     TOÀN BỘ style + design token (đồng bộ app web thật).
    data.js       DATA GIẢ + helper (CURRICULUM, PROGRESS, lesson*, sieveSVG, el, ST, initTheme).
    views.js      Render dùng chung: renderLesson/renderLessonObj, renderProgress, renderSlides, quizNode, section.
    cms.js        Logic CMS (mục lục editable, AI ingest giả lập, editor 4 phần, preview).
  README.md       Mô tả cho người xem/trình bày.
  SKILL.md        (file này) hướng dẫn cho AI bảo trì.
```

## Quy ước BẮT BUỘC giữ
- **JS thuần, scope toàn cục** (`var`, `function`), **KHÔNG ES module** (`import/export`) —
  để chạy được qua `file://` không cần server. Các trang nạp script theo thứ tự
  `data.js` → `views.js` → (`cms.js`).
- **Không thêm thư viện/CDN ngoài**; không webfont link. Font dùng system stack qua biến
  `--font-display` (Baloo 2) / `--font-body` (Be Vietnam Pro), fallback `system-ui`.
- **Design token đồng bộ app thật** (`web/src/styles.css`): brand `#1b4fbf`, nền lệch xanh,
  `color-mix(in oklab, …)` cho tint accent, semantic ok/warn/err. Theme sáng/tối qua
  `:root` + `@media (prefers-color-scheme)` + `[data-theme]` (nút `#theme` → `initTheme`).
- **Tiếng Việt** cho mọi copy. Số liệu dùng `.tnum` (tabular-nums).
- Sau khi sửa JS: `node --check assets/<file>.js` (bỏ qua log nvm; chỉ cần thấy "OK").
- Mọi trang tự chứa qua `assets/` chung — sửa 1 chỗ áp dụng mọi trang.

## Mô hình dữ liệu (data.js)
```js
CURRICULUM = [{ mach, em, dv:[{ t, st:"dat|dang|chua", prime? }] }]   // mục lục
PROGRESS   = [{ mach, ycd:[{ t, st }] }]                              // tiến độ theo yêu cầu cần đạt
lesson     = { mach, dv, khai_niem(html), minh_hoa:[{type:"image|video|sieve",url,caption}],
               vi_du:[{de,giai}], quiz:[{q,o:[...],a,lv:"de|trung_binh|kho"}], day:{muc_tieu,thoi_luong,luu_y,goi_y{}} }
```
`lessonFor(mi,di)` trả lesson mẫu; đơn vị có `prime:true` → `lessonPrime` (bài Số nguyên tố
kèm SVG sàng). Còn lại → `lessonGeneric`.

## Công thức mở rộng thường gặp
- **Thêm mạch/đơn vị vào mục lục**: sửa `CURRICULUM` (+ `PROGRESS` tương ứng) trong `data.js`.
- **Mục lục khớp file ma trận**: chạy parser lấy taxonomy rồi chuẩn hoá (khử trùng OCR):
  `.venv/bin/python -c "from app.ingestion.matrix_parser import parse_matrix; from pathlib import Path; [print(r.mach_noi_dung,'|',r.don_vi_kien_thuc) for r in parse_matrix(Path('data/matrix/TOAN_6_HK1.docx'))]"`
  → gom theo mạch, bỏ dòng lặp/nhiễu, cập nhật `CURRICULUM`.
- **Thêm phần vào bài học**: sửa `renderLessonObj` trong `views.js` (giữ thứ tự 4 phần cố định;
  KHÔNG thêm trích dẫn số trang) + style `.sec*`/`.lesson*` trong `style.css`.
- **Thêm bước/tính năng CMS**: sửa `cms.js` (`renderStruct` cho cấu trúc+AI, `renderEdit` cho
  4 phần). Preview luôn qua `renderLessonObj(root, docToLesson(...), teacher)`.
- **Thêm màn lẻ mới**: tạo `mockup/ten.html` nạp `assets/style.css`+`data.js`+`views.js`,
  render vào `#view`; thêm link ở `index.html` và dòng trong `README.md`.

## Ánh xạ khi nối backend thật (đích đến)
- Mục lục ← `curriculum_topics` (nạp từ ma trận; nên chuẩn hoá dedupe lúc `matrix_loader`).
- Bài học ← bảng mới `TopicContent(topic_id, khai_niem, minh_hoa_json, vi_du_json, kiem_tra_json, nguon, trang_thai)` qua `GET /lessons/{topic_id}`.
- "Bài kiểm tra nhanh" ← sinh tự động theo ma trận (tái dùng `app/exam/*`), KHÔNG nhập tay.
- Tiến độ ← `StudentProgress` theo `blueprint_cells.yeu_cau_can_dat`.
- CMS "Nạp sách bằng AI" ← pipeline: upload file → trích xuất (OCR/LLM) → gợi ý `TopicContent`
  cho từng đơn vị → chuyên gia rà/sửa/duyệt.
- Media ← hạ tầng URL ký HMAC sẵn có (không dùng ảnh trang SGK làm nội dung nữa).

Giữ mockup và schema đích khớp nhau: khi đổi trường trong mockup, cập nhật cả phần "Ánh xạ" ở trên.
