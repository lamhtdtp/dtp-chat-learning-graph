# Khối "Đề xuất" và kho học liệu có mã (US-27)

Sau khi nộp bài, học sinh thấy MỘT khối "Đề xuất" (đọc thêm · video · test thêm) ở mọi loại bài:
Bài kiểm tra nhanh, ôn tập chương, luyện thêm, đề cuối kỳ, đề giáo viên giao và chính bài "Test
thêm". Khối này thay hai bộ gợi ý cũ ("Nên đọc lại N phần" của Bài kiểm tra nhanh, "Đọc lại trước khi
làm tiếp" + "Làm bài mới" của đề cuối kỳ — xem `XEM-LAI-BAI-CUOI-KY.md`). Nút "Đọc lại phần này" /
"Xem lại bài" trên từng câu sai vẫn còn, nhưng ẩn khi bài chưa xuất bản (`bai_xuat_ban`).

Nghiệm thu: `User-Stories/EPIC-04-On-Tap/US-27-…` · hợp đồng: `docs/contracts/US-27-…` (repo tài liệu).
Không gọi LLM, không embed — kho học liệu là dữ liệu cấu trúc trong Postgres.

## Luồng

```
nộp bài ──► chấm (như cũ, điểm ghi + commit) ──► app/lessons/de_xuat.py dựng `de_xuat`
                                                    ├─ danh mục YCCĐ (ma trận Toán 6) + bài đã xuất bản
                                                    ├─ kho học liệu `hoc_lieu` (chỉ YCCĐ còn sai / chưa vững)
                                                    ├─ lịch sử 5 lần nộp gần nhất (chưa vững, YCCĐ yếu)
                                                    └─ testbank `/pool` (còn câu nào để "Test thêm")
```

* `de_xuat` KHÔNG lưu trong `ket_qua_json`: tính lại theo kho hiện tại ở MỌI lần trả về — nộp, nộp
  lần hai, `GET /exam/cuoi-ky/{id}`, `POST /de-giao/vao` (Q11: sửa / xoá học liệu thì bài cũ cũng đổi).
  Cửa sổ "5 lần nộp gần nhất" tính tới đúng lần nộp đó, nên mở lại không làm kết quả đổi theo bài làm sau.
* Dựng khối đứng SAU khi điểm đã commit và không bao giờ làm hỏng kết quả: kho học liệu chết → câu
  "Chưa tải được video và tài liệu gợi ý…"; testbank chết → "Test thêm" theo `ar_id` đã biết; lỗi bất ngờ →
  khối rỗng + log. Bài kiểm tra nhanh / ôn tập nộp được cả khi testbank chưa cấu hình.
* Trước khi nộp không đường nào trả thông tin học liệu (nhãn kiểu "Vì sao chọn B sai" lộ đáp án).

## Luật chọn học liệu (hàm thuần `tinh_de_xuat`)

| YCCĐ | Học liệu hiện |
|---|---|
| còn sai (có câu chấm tự động sai) | Ôn lại: theo phương án em chọn sai → theo câu → theo YCCĐ |
| đúng hết nhưng chưa vững (< 80% trên 5 lần nộp gần nhất, ≥ 2 câu) | Củng cố, luôn sau Ôn lại |
| không khớp danh mục YCCĐ | không gì cả, ghi `log.error` (không đoán) |

Câu tự luận không chấm tự động không bao giờ là "sai". "Phương án sai": TN1 = lựa chọn em chọn; TNN =
lựa chọn chọn thừa; DS = ý trả lời khác đáp án (ý thứ i ↔ khoá A, B, C, D). Giới hạn hiển thị: Video 3,
Đọc thêm 5 bài + 5 học liệu ("Xem thêm N" ở giao diện; API trả đủ).

## Quản trị (CMS)

Menu "Kho học liệu" (`web-admin`), API `/cms/hoc-lieu*` (chuyên gia / giáo viên / admin). Mã lưu CHỮ HOA, unique,
xoá mềm. Thêm đồng thời cùng mã: UNIQUE trong DB + bắt `IntegrityError` → 409. Gắn theo câu thì hỏi testbank
(`questions:resolve`, không xin đáp án) để kiểm câu thuộc YCCĐ và có phương án đó.

## Dữ liệu demo

```bash
uv run python -m app.seed_hoc_lieu                       # nạp app/seed_data/hoc_lieu_demo.json (bỏ qua mã đã có)
TESTBANK_*=… uv run python -m app.seed_hoc_lieu --kiem-do-phu   # độ phủ theo ngưỡng KB 11 (mặc định dùng đề demo trong file)
```

File demo CHỈ chứa video AI nội bộ có thật (`video_jobs` DONE, tệp có trong kho video). Không có link SGK / SBT /
BTTC thật thì để thiếu và `--kiem-do-phu` báo rõ — không lấp bằng link giả. Cần chuyên gia nội dung rà lại mức
phù hợp giữa video và YCCĐ / phương án trước khi dùng thật.

## Triển khai

* `./deploy.sh migrate` (bảng `hoc_lieu`, revision `d5a1c7e3f9b2`). API lên trước migrate vẫn nộp bài được
  (khối Đề xuất suy giảm), nhưng CMS kho học liệu chưa dùng được.
* Không có tiền tố API hay biến môi trường mới (`/cms` đã có trong nginx / vite).
* Nạp demo: chạy lệnh `app.seed_hoc_lieu` ở trên trong container api.
