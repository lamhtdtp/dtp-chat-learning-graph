# Bài theo mã Testbank — mức 1, chi tiết sau nộp, hai giai đoạn (US-30)

Mở rộng US-29. Mã: `app/api/ma_testbank.py` (router), `app/exam/bai_ma_chi_tiet.py` (chép chi tiết, thống kê,
dựng phản hồi), `app/exam/ly_do_to_de.py` (lý do từng phương án theo nội dung tờ đề),
`app/integrations/testbank/doi_tac.py` (client đường đối tác), `web/src/learn/BaiMaView.tsx`.

## Hai mức, một cờ mỗi việc

| Cờ | Tác dụng |
|---|---|
| `TESTBANK_DOI_TAC_BAT` | Bài **mới** vào thi bằng đường đối tác (`/doi-tac/*`, token tài khoản dịch vụ). Tắt: đường học sinh như US-29. |
| `TESTBANK_CHI_TIET_SAU_NOP_BAT` | Sau nộp lấy "chi tiết" (YCCĐ, đáp án khi lượt đóng). Tắt: kết quả như US-29. |

**Mức của từng bài cố định lúc tạo** (`de_cuoi_ky.muc`): bật/tắt cờ không đổi đường đi của bài đã có (bài mức 0
không đọc được qua đường đối tác và ngược lại). Đường đối tác lỗi **không** tự rơi về mức 0 — Testbank đã có
thể tạo bài, rơi xuống là ra bài thứ hai. Học sinh thấy "Chưa mở được đề, em thử lại sau ít phút nhé".

Bật cờ trên server: tài khoản dịch vụ learning phải có **đúng một** vai đối tác "Gia sư DTP" (Testbank AC40) và
Testbank đã triển khai T5/T7 (US-30 C1, C2). Thử nhanh: bật cờ, nhập một mã thật; "Chưa mở được đề" kèm log
`CANH_BAO testbank_doi_tac_vao_thi_loi status=… ma=…` là Testbank chưa sẵn sàng / sai vai.

## Giai đoạn

1. **Ngay sau nộp** (lượt còn mở): điểm, Đúng/Sai, kết quả theo YCCĐ, Đề xuất, "Xem lại bài". Không đáp án.
   Thống kê YCCĐ ghi **một lần** (`quiz_attempts.nguon="de_giao"`, dấu "đã ghi" là `de_cuoi_ky.attempt_id`);
   XP chỉ cộng lúc nộp.
2. **Khi thầy cô đóng lượt**: thêm đáp án, lời giải, lý do từng phương án. Learning chỉ biết khi **học sinh mở
   bài** (không có tác vụ nền, không hỏi định kỳ); chép bản đầy đủ (`dap_an_mo=true`) rồi không bao giờ hỏi lại.

Quyết định hiện đáp án chỉ dựa vào cờ `hien_dap_an_cho_hoc_sinh` **của chính bài đó** (Testbank trả). Learning
không lấy đáp án từ kho / `ly_do_phuong_an` / bài của lượt khác để lấp chỗ Testbank để trống.

## Khi nào hỏi Testbank về chi tiết

Nộp xong · nhận ra bài đã bị tự nộp (lưu / nộp / mở lại) · học sinh mở lại bài chưa có đáp án. Tối đa **một lần
mỗi 60 giây mỗi bài** (`kiem_luc`, giờ Postgres, dùng chung nhiều tab / replica); lỗi mạng / 5xx **không** tính
vào 60 giây (thử lại được ngay). Bài đủ đáp án, bài quá hạn (410) không hỏi nữa.

## Cảnh báo vận hành (tìm trong log)

| Dòng log | Nghĩa |
|---|---|
| `CANH_BAO testbank_chan_nhap_ma_doi_tac` | Cả đối tác bị Testbank tạm chặn nhập mã (300 lần / 10 phút). |
| `CANH_BAO testbank_doi_tac_vao_thi_loi` | Token bị từ chối / sai vai / chưa có đường / Testbank lỗi khi vào thi. |
| `CANH_BAO testbank_chua_co_duong_chi_tiet` | `GET /doi-tac/bai-lam/{id}/chi-tiet` trả 404 không mã: Testbank chưa triển khai T5. |
| `CANH_BAO testbank_khong_con_bai_lam` | Testbank trả "không tìm thấy bài làm"; learning giữ bản chép, không đổi điểm. |
| `YCCĐ testbank không khớp ma trận của mình` | Câu có YCCĐ lệch nguyên văn: không gắn bài, nêu mã YCCĐ. |

Log đường đối tác chỉ ghi đường mẫu, mã trạng thái, độ trễ. `bai_lam_id` nằm trong URL nên log INFO của
`httpx` / `httpcore` bị hạ xuống WARNING (`doi_tac.py`). Không có token, mã bài làm, đáp án trong log.

## Lý do từng phương án

Khoá theo **dấu vân nội dung câu trên tờ đề** (`ly_do_to_de.dau_van`), bảng `ly_do_to_de` — không theo mã câu +
phiên bản, vì thầy cô sửa riêng câu cho tờ đề. Đọc là đọc DB; câu chưa có thì sinh **nền** sau khi đã trả bài
(`BackgroundTasks`, phiên DB riêng, khoá cố vấn theo dấu vân: một lần cho mọi học sinh). Nội dung tờ đề trùng
nội dung kho và kho đã có lý do cho (mã câu, phiên bản) → chép, không gọi model (một lần `questions:resolve`
để so nội dung). Model chết → không đánh dấu "đã sinh", lần mở sau thử lại. Model bỏ sót phương án → thiếu thì
để thiếu.

Eval chất lượng: `python -m evals.run_ly_do_eval` (cần model chạy được, tốn quota).

## Việc khi deploy

- `./deploy.sh migrate` (migration `b3f7a1c9d2e5`: 6 cột của `de_cuoi_ky` + bảng `ly_do_to_de`).
- Không có tiền tố API mới → không sửa nginx. Không có biến môi trường mới (hai cờ đã có trong compose).
