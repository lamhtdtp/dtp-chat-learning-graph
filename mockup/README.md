# Mockup giải pháp — Gia sư DTP Lớp 6

Bản dựng UI **dữ liệu giả** để chốt hướng giải pháp theo meeting note (nội dung có
cấu trúc, bài học 4 phần, tiến độ học sinh, slide giáo viên). **Chưa nối backend.**

## Cách xem / trình bày

Mở trực tiếp file `.html` bằng trình duyệt (double-click) — không cần server.

| File | Màn hình | Dùng để trình bày |
|------|----------|-------------------|
| `index.html` | **Bản tổng hợp** (bấm chuyển Học sinh/Giáo viên + Mục lục) | Demo toàn luồng |
| `bai-hoc.html` | Bài học 1 đơn vị — **4 phần cố định**. Thêm `?role=gv` để xem kèm **hướng dẫn giảng dạy** | Mục 2: cấu trúc bài học |
| `tien-do.html` | Tiến độ học sinh theo **yêu cầu cần đạt** | Mục 3: đánh giá tiến độ (HS) |
| `slide-gv.html` | **Slide giảng dạy** render từ data (← → chuyển slide) | Mục 3: tính năng GV |
| `cms.html` | **CMS chuyên gia**: (1) nhập/sửa **mục lục** theo file ma trận, (2) tải **file sách + nạp bằng AI**, (3) **sửa nội dung** 4 phần | Mục 1: nhập liệu nội dung |

> **Giáo viên** trong `index.html` có 2 tab: **📘 Bài học** (kèm khối *🎓 Hướng dẫn
> giảng dạy* — mục tiêu, thời lượng, gợi ý cách dạy từng phần, lỗi thường gặp) và
> **🖥️ Slide giảng dạy**. Cùng nội dung bài học của HS nhưng bổ sung lớp hướng dẫn dạy.

## Bám meeting note

- **① Nội dung**: mục lục **Mạch nội dung → Đơn vị kiến thức** (như file Word ma trận);
  nội dung do chuyên gia biên soạn (nhiều nguồn).
- **② Bài học**: 4 phần **đúng thứ tự** — Khái niệm (text) → Minh họa (ảnh/video) →
  Ví dụ → Bài kiểm tra nhanh; **bỏ trích dẫn số trang**.
- **③ Tính năng**: HS xem tiến độ theo *yêu cầu cần đạt*; GV render slide từ data.

## Cấu trúc

```
mockup/
  index.html          bản tổng hợp (app shell + sidebar + tabs)
  bai-hoc.html        trang lẻ: LessonView
  tien-do.html        trang lẻ: Tiến độ
  slide-gv.html       trang lẻ: Slide GV
  cms.html            CMS chuyên gia (biên soạn nội dung)
  assets/
    style.css         design token (đồng bộ app web thật)
    data.js           DATA GIẢ + helper (thay bằng API sau)
    views.js          hàm render dùng chung (LessonView, tiến độ, slide)
    cms.js            logic CMS (soạn 4 phần + preview)
  SKILL.md            hướng dẫn cho AI bảo trì/mở rộng mockup này
```

Khi chốt xong, nối backend theo mockup: bảng `TopicContent`, `GET /lessons/{topic_id}`,
tiến độ theo `blueprint_cells.yeu_cau_can_dat`, "kiểm tra nhanh" sinh theo ma trận.
