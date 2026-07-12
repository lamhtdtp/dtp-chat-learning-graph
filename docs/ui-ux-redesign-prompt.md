# Prompt: Thiết kế lại UI/UX "Gia sư DTP" — đẹp hơn & đa môn học

> Dán toàn bộ phần trong khung dưới cho Claude (chế độ thiết kế / tạo artifact HTML)
> để nhận lại design system + mockup các màn hình. Có thể chỉnh phần "Ràng buộc"
> cho khớp thương hiệu thật.

---

Bạn là **Senior Product Designer** cho một nền tảng **gia sư AI cho học sinh phổ thông Việt Nam**. Hãy **thiết kế lại toàn bộ UI/UX cho đẹp, hiện đại, đáng tin hơn**, đồng thời **mở rộng từ một môn (Toán) sang NHIỀU MÔN học**. Trả về **design system + mockup các màn hình chính** dưới dạng **HTML/CSS tự chứa** (inline, không phụ thuộc CDN ngoài), hỗ trợ **sáng/tối** và **responsive (mobile-first)**.

## 1. Bối cảnh sản phẩm (giữ đúng, đừng bịa tính năng mới ngoài mục 4)
- Tên: **Gia sư DTP** — trợ lý học tập AI, giao diện **tiếng Việt**, đối tượng **học sinh lớp 6–12** và **giáo viên**.
- Cốt lõi hiện có: chat hỏi-đáp bám **Sách Giáo Khoa** (có **trích dẫn số trang**, bấm vào mở **ảnh trang sách gốc**), **giải bài từng bước**, **ôn tập theo chủ đề**, **công thức Toán render bằng KaTeX**.
- Vai trò:
  - **Học sinh**: hỏi bài, xem lời giải, xem **video AI minh hoạ** (nút "Tạo/Xem video"), **luyện trắc nghiệm i-Test** (mở quiz tương tác: chọn đáp án → nộp → chấm điểm), lịch sử hội thoại.
  - **Giáo viên**: **sinh đề kiểm tra tự động theo ma trận** (chọn học kỳ + số câu → đề có nhãn mức độ Dễ/TB/Khó + đáp án + lời giải).
- Thương hiệu: **logo DTP**, tông **xanh dương (#1b4fbf)** trên nền sáng (#f4f8ff), chữ trắng cho vùng nhấn; font gợi ý **Be Vietnam Pro** (thân) + **Baloo 2** (tiêu đề). Bạn được tự do làm mới palette/typography nhưng nêu rõ lý do.

## 2. Vấn đề của giao diện hiện tại (cần giải quyết)
- Trông giống chatbox cơ bản, thiếu cảm giác "sản phẩm giáo dục" chỉn chu, thiếu chiều sâu thị giác.
- Chỉ phục vụ **1 môn (Toán)** — không có cách chuyển môn, không có bản sắc riêng cho từng môn.
- Các khối chức năng (trích dẫn trang, video, quiz, sinh đề) hiển thị rời rạc, chưa thành một hệ thống nhất quán.
- Chưa tối ưu mobile, chưa có chế độ tối, trạng thái rỗng/đang tải/lỗi còn sơ sài.

## 3. Mục tiêu thiết kế
1. **Đẹp & hiện đại & đáng tin**: vui tươi vừa đủ cho học sinh nhưng nghiêm túc, đáng tin với giáo viên/phụ huynh. Tránh quá "trẻ con".
2. **Nhất quán**: một design system rõ ràng (token màu/ò chữ/khoảng cách/bo góc/đổ bóng, bộ component tái dùng).
3. **Đa môn ngay từ kiến trúc điều hướng** (mục 4).
4. **Tập trung nội dung học**: chat + tài liệu + luyện tập phải nổi bật, thao tác tối thiểu.

## 4. YÊU CẦU TRỌNG TÂM: Mở rộng ĐA MÔN
Thiết kế để hỗ trợ nhiều môn (ví dụ): **Toán, Ngữ văn, Tiếng Anh, Khoa học tự nhiên (Lý–Hoá–Sinh), Lịch sử & Địa lí, Tin học, Giáo dục công dân**. Cần:
- **Màn chọn môn (Subject Hub)**: lưới thẻ môn học, mỗi môn có **màu nhận diện + icon riêng**, hiển thị lớp đang học, tiến độ/gợi ý gần đây. Đây là điểm vào sau đăng nhập.
- **Bộ chuyển môn nhanh** luôn truy cập được trong lúc chat (thanh bên / dropdown / segmented control) — đổi môn thì **theme (màu nhấn, icon, gợi ý chủ đề, danh mục) đổi theo**, nhưng khung bố cục giữ nguyên.
- **Theming theo môn**: định nghĩa cách sinh biến thể màu từ 1 "màu môn" (ví dụ Toán = xanh dương, Văn = hồng/đỏ trầm, Anh = tím, KHTN = xanh lá, Sử–Địa = nâu/cam đất…) mà vẫn giữ khung thương hiệu DTP chung. Nêu công thức token (primary/soft/on-color…).
- **Chọn lớp/khối** (6→12) và **bộ sách** (nhiều bộ SGK) trong ngữ cảnh môn.
- Nội dung theo môn có thể khác nhau: Toán cần **công thức (KaTeX)**; Văn/Sử cần **đoạn văn dài, trích dẫn nguồn**; Anh cần **hội thoại/từ vựng/phát âm**. Thiết kế khối trả lời **linh hoạt theo loại nội dung**, không chỉ hợp Toán.
- Danh mục chủ đề bên phải phải **tổng quát hoá** (hiện đang hardcode chủ đề Toán 6): mô tả cấu trúc dữ liệu chủ đề theo (môn → khối → mạch nội dung).

## 5. Màn hình & luồng cần mockup
1. **Đăng nhập/Đăng ký** (chọn vai trò học sinh/giáo viên) — ấn tượng, có minh hoạ.
2. **Subject Hub** (chọn môn — màn chính sau đăng nhập).
3. **Màn Chat** (chính): 
   - Bong bóng hỏi-đáp; **markdown + công thức**; **chip trích dẫn "Trang N · Bài M"** bấm mở **modal ảnh trang sách**.
   - Khối **video minh hoạ** (nút Tạo/Xem → popup player) và khối **luyện i-Test** (nút → **modal quiz tương tác**: 1 câu/nhiều đáp án/điền, nộp bài, chấm ✓/✕, làm lại).
   - **Gợi ý câu hỏi** (chips) khi trống; ô nhập có **micro + nút gửi**.
   - **Sidebar lịch sử** hội thoại theo môn; bộ chuyển môn.
4. **Modal ảnh trang sách** (xem trang SGK gốc, zoom).
5. **Modal Quiz i-Test** (làm bài trắc nghiệm, trạng thái đang tải/đề/kết quả).
6. **Popup Video** (đang tạo / trình phát).
7. **Màn Giáo viên — Sinh đề**: chọn học kỳ + số câu → đề (nhãn mức độ, chỉ tiêu %, câu hỏi + đáp án/lời giải, nút tải/in).
8. **Trạng thái**: rỗng (chưa hỏi), đang tải (typing), lỗi/khi AI quá tải, "chưa có trong SGK".
9. **Responsive mobile** cho tất cả + **dark mode**.

## 6. Deliverables (trả về đúng các mục sau)
1. **Design tokens**: bảng màu (light+dark), thang chữ, spacing, radius, shadow, cách sinh theme-theo-môn từ 1 màu gốc.
2. **Component library**: nút, input, chip, thẻ, bong bóng chat, chip trích dẫn, thẻ video, thẻ quiz, badge mức độ, modal, sidebar item, subject card, empty/loading/error.
3. **Mockup HTML/CSS tự chứa** cho các màn ở mục 5 (ít nhất: Subject Hub, Chat có đủ khối, Quiz modal, Sinh đề). Dùng biến CSS + `@media (prefers-color-scheme)` + `:root[data-theme]`. Không gọi tài nguyên ngoài; nhúng icon dạng SVG inline/emoji, ảnh dạng placeholder.
4. **Nguyên tắc chuyển động** (micro-interaction: reveal câu trả lời, mở modal, chấm quiz) — tinh tế, không phô trương.
5. **Ghi chú a11y**: tương phản đạt WCAG AA, focus rõ, cỡ chạm ≥44px, hỗ trợ bàn phím, chữ tiếng Việt có dấu hiển thị tốt.

## 7. Ràng buộc kỹ thuật (để bàn giao code React được)
- Sẽ hiện thực bằng **React + TypeScript + Vite**, CSS thuần (biến CSS), không bắt buộc framework UI nặng.
- **Tiếng Việt là ngôn ngữ chính**; công thức Toán qua **KaTeX**.
- Giữ khả năng cắm **logo DTP**; nêu rõ nếu đổi palette/typography so với hiện tại và lý do.
- Ưu tiên **hiệu năng + đơn giản để bảo trì**; tránh phụ thuộc CDN ngoài (CSP chặt).

Hãy bắt đầu bằng **moodboard/ý tưởng định hướng (2–3 dòng)**, rồi tới **design tokens**, rồi **mockup từng màn**. Giải thích ngắn gọn quyết định thiết kế ở mỗi phần.
