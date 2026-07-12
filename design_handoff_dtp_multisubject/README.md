# Handoff: Gia sư DTP — Redesign đa môn (UI/UX + Design System)

## Overview
Thiết kế lại toàn bộ UI/UX cho **Gia sư DTP** — trợ lý học tập AI tiếng Việt cho học sinh lớp 6–12 và giáo viên — đồng thời mở rộng từ 1 môn (Toán) sang **nhiều môn** (Toán, Ngữ văn, Tiếng Anh, KHTN, Lịch sử & Địa lí, Tin học, GDCD).

Mục tiêu: đẹp – hiện đại – đáng tin; design system nhất quán chạy hoàn toàn bằng biến CSS; kiến trúc điều hướng đa môn với **theme sinh theo môn từ một biến `--subject` duy nhất**; hỗ trợ sáng/tối/auto và responsive (mobile-first).

## About the Design Files
File trong gói này (`Gia sư DTP — Design System.dc.html`) là **bản tham chiếu thiết kế viết bằng HTML/CSS/JS** — một prototype thể hiện *đúng diện mạo và hành vi mong muốn*, **không phải mã sản phẩm để copy trực tiếp**.

Nhiệm vụ là **tái dựng các thiết kế này trong codebase mục tiêu** (theo brief: **React + TypeScript + Vite, CSS thuần dùng biến CSS**) theo pattern có sẵn của dự án. Ràng buộc kỹ thuật quan trọng:
- **Tiếng Việt là ngôn ngữ chính**, có dấu đầy đủ.
- **Công thức toán render bằng KaTeX** (trong prototype chỉ mô phỏng bằng text/serif font — production phải dùng KaTeX thật).
- **Tránh CDN ngoài** (CSP chặt): **self-host** fonts và thư viện. Prototype dùng Google Fonts chỉ để xem trước — production phải tải font về `/fonts` và `@font-face` cục bộ.
- Cắm được **logo DTP** (prototype dùng chữ "D" trong ô bo góc làm placeholder).
- Đơn giản, dễ bảo trì.

> Lưu ý: file `.dc.html` là định dạng "Design Component" của môi trường prototype. Bạn **không** cần tái tạo runtime đó — chỉ đọc template + logic bên trong như một đặc tả React (state, handler, markup, style inline). Toàn bộ logic đã viết bằng JS thuần dạng class giống React component (state/setState/handlers), rất dễ port sang function component + hooks.

## Fidelity
**High-fidelity (hifi).** Màu, typography, spacing, bo góc, đổ bóng, trạng thái hover/active/focus và các luồng tương tác đều là giá trị cuối. Hãy tái dựng **pixel-perfect** bằng thư viện/pattern của codebase. Chỉ nội dung ví dụ (câu hỏi Toán, tên học sinh "Minh"…) là placeholder.

---

## Design Tokens

Tất cả token đặt trên class gốc `.dtp` (production: đặt trên `:root` hoặc container app). **Không hardcode màu** ngoài các token này.

### Brand (cố định, không đổi theo môn)
| Token | Light | Ghi chú |
|---|---|---|
| `--brand` | `#1b4fbf` | Xanh DTP |
| `--brand-strong` | `#143a8f` | Xanh đậm (gradient logo) |
| `--brand-ink` | `#ffffff` | Chữ trên nền brand |

### Surfaces & ink — Light
`--bg #f4f8ff` · `--surface #ffffff` · `--surface-2 #eef3fe` · `--surface-3 #e3ecfc` · `--border #d8e2f5` · `--border-strong #c2d1ee` · `--ink #0f1b33` · `--ink-2 #4b5876` · `--ink-3 #8593b4`

### Surfaces & ink — Dark (`data-theme="dark"` hoặc `prefers-color-scheme: dark`)
`--bg #0a1120` · `--surface #111a2e` · `--surface-2 #16223a` · `--surface-3 #1d2c48` · `--border #263654` · `--border-strong #33456a` · `--ink #eaf0ff` · `--ink-2 #a7b6d6` · `--ink-3 #6f7fa3` · `--brand #4f82ff` · `--brand-strong #6f9bff`

### Feedback & mức độ
`--ok #16a34a` · `--warn #d97706` · `--err #dc2626` · `--easy #16a34a` (Dễ) · `--mid #d97706` (TB) · `--hard #dc2626` (Khó)

### Bo góc / rhythm
`--r-sm 8px` · `--r-md 12px` · `--r-lg 18px` · `--r-xl 26px` · `--r-pill 999px` · base spacing `--sp 4px`

### Đổ bóng
- `--sh-1`: `0 1px 2px rgba(16,27,51,.06), 0 1px 3px rgba(16,27,51,.05)`
- `--sh-2`: `0 4px 14px rgba(16,27,51,.08), 0 2px 6px rgba(16,27,51,.05)`
- `--sh-3`: `0 18px 48px rgba(16,27,51,.16), 0 6px 16px rgba(16,27,51,.10)`
- Dark thay bằng `rgba(0,0,0,...)` đậm hơn (xem file).

### Typography
- **Be Vietnam Pro** (400/500/600/700/800) — font nền cho toàn bộ nội dung & UI. Lý do chọn: bộ dấu tiếng Việt cân đối, đọc dài dễ, tạo cảm giác đáng tin.
- **Baloo 2** (500/600/700) — **chỉ dùng điểm nhấn**: tiêu đề, logo, con số vui, mascot chữ. Không dùng cho đoạn văn dài (chữ tròn khó đọc khi dày đặc).
- `font-feature-settings: "ss01"`, `line-height: 1.55`, `-webkit-font-smoothing: antialiased`.
- Cỡ chữ tiêu biểu: H1 hero `clamp(32px,5.4vw,52px)/1.05, -1px`; H2 section `26px/700`; body `14–15px`; caption `12–12.5px`.

---

## ⭐ Theme sinh theo môn (cơ chế cốt lõi)

Chỉ đặt **một biến `--subject`** theo môn; tất cả biến nhấn còn lại sinh tự động bằng `color-mix`. Khung bố cục, spacing, bo góc **không đổi** khi chuyển môn — chỉ màu nhấn.

```css
/* mỗi môn chỉ set 1 biến này (qua [data-subject="..."]) */
--subject: #e0457b;

--accent:        var(--subject);
--accent-strong: color-mix(in oklab, var(--subject) 78%, #000);
--accent-soft:   color-mix(in oklab, var(--subject) 12%, var(--surface));
--accent-soft-2: color-mix(in oklab, var(--subject) 20%, var(--surface));
--accent-border: color-mix(in oklab, var(--subject) 34%, var(--border));
--accent-ink:    color-mix(in oklab, var(--subject) 62%, var(--ink));   /* auto tương phản */
--accent-glow:   color-mix(in oklab, var(--subject) 30%, transparent);
--on-accent:     #ffffff;
```

Nền tối **tăng % pha** để giữ tương phản WCAG AA:
```css
[data-theme="dark"] {
  --accent-soft:   color-mix(in oklab, var(--subject) 26%, var(--surface));
  --accent-soft-2: color-mix(in oklab, var(--subject) 38%, var(--surface));
  --accent-border: color-mix(in oklab, var(--subject) 46%, var(--border));
  --accent-ink:    color-mix(in oklab, var(--subject) 42%, var(--ink));
}
```

### Bảng màu môn (giá trị `--subject`)
| key | Môn | Màu | Icon |
|---|---|---|---|
| `toan` | Toán | `#1b4fbf` | 📐 |
| `van` | Ngữ văn | `#e0457b` | ✒️ |
| `anh` | Tiếng Anh | `#7c4dff` | 💬 |
| `khtn` | KHTN | `#10a596` | 🔬 |
| `sudia` | Lịch sử & Địa lí | `#d9820a` | 🗺️ |
| `tin` | Tin học | `#0e9bc4` | 💻 |
| `gdcd` | GDCD | `#12a150` | ⚖️ |

Áp dụng qua thuộc tính: `<element data-subject="van">`. Trong React: một `<SubjectThemeProvider subject="van">` set `data-subject` (hoặc inline `style={{'--subject': color}}`) lên container; các con dùng `var(--accent…)`.

### Sáng / Tối / Auto
- Mặc định light. `@media (prefers-color-scheme: dark) .dtp:not([data-theme="light"])` → tự tối theo OS.
- Override thủ công bằng `data-theme="dark"` / `data-theme="light"`.
- Nút toggle luân phiên **auto → light → dark → auto** (icon 🌗/☀️/🌙, nhãn Auto/Sáng/Tối). Khi ở auto thì **không set** `data-theme` (để `prefers-color-scheme` tự quyết).

---

## Screens / Views

### 1. Đăng nhập · chọn vai trò
- **Layout**: 2 cột responsive (`minmax(300px,1fr)`), gap 18px. Cột trái: thẻ form đăng nhập (`--r-xl`, `--sh-2`, padding 30px, căn giữa). Cột phải: thẻ chọn vai trò + thẻ ghi chú a11y.
- **Form**: logo 52px gradient brand, tiêu đề Baloo 2 20px, 2 field (email, mật khẩu) cao 46px `--r-md`, nút "Đăng nhập" cao 48px nền `--brand`, chữ trắng.
- **Chọn vai trò**: 2 nút lớn — "🎒 Học sinh" (Hỏi bài · video · luyện i-Test) và "👩‍🏫 Giáo viên" (Sinh đề theo ma trận · ngân hàng câu hỏi). Nút chọn dùng `--accent-soft`/`--accent-border`; nút còn lại `--surface`/`--border`. Icon 44px bo `12px`.
- **Điều hướng**: Học sinh → Subject Hub; Giáo viên → màn Sinh đề.

### 2. Subject Hub (gốc điều hướng đa môn — màn sau đăng nhập)
- **App bar** (`--surface`, border-bottom): logo "D" 32px + "Gia sư DTP" (Baloo 2) + nút chọn khối "🎒 Lớp 9 ▾" + chuông 🔔 + avatar tròn 38px.
- **Body** padding 26px/22px: lời chào Baloo 2 24px ("Chào Minh 👋 Hôm nay học môn gì?"), subtitle `--ink-2`.
- **Gần đây**: hàng chip cuộn ngang (`overflow-x:auto`), mỗi chip mang `data-subject` riêng → màu theo môn.
- **Lưới môn**: `grid-template-columns: repeat(auto-fill, minmax(168px, 1fr))`, gap 14px. Mỗi **subject card**:
  - `data-subject` set màu; nền `--surface`, border `--border`, `--r-lg`, `--sh-1`.
  - Thanh màu trên cùng cao 4px = `var(--accent)` (`position:absolute; inset:0 0 auto 0`).
  - Icon 46px nền `--accent-soft` bo `13px`, emoji 24px.
  - Tên môn Baloo 2 16px; dòng phụ `--ink-3` 12px; dòng "N mạch chủ đề" `--accent-ink` 11.5px/600.
  - **Hover**: `translateY(-3px)`, `--sh-2`, `border-color:--accent-border`.
  - Ô cuối: card dashed "➕ Thêm môn / sắp có".

### 3. Chat — bám SGK, đa môn (màn cốt lõi)
- **Subject switcher**: hàng tab cuộn ngang phía trên khung chat; mỗi tab `data-subject` + `data-key`. Tab active: `aria-current="true"` → nền `var(--accent)`, chữ trắng, glow. Click tab → đổi `state.subject` → **cả khung chat re-theme** (màu nhấn + icon header + gợi ý đổi; bố cục giữ nguyên).
- **Khung chat**: `display:grid; grid-template-columns: 230px 1fr;` `--r-xl`, `--sh-3`. Container mang `data-subject={currentSubject}`.
  - **Sidebar (trái, 230px)**: nút "＋ Cuộc trò chuyện mới" (nền `--accent`), nhãn "Lịch sử", danh sách hội thoại (item active nền `--accent-soft`), nhóm theo ngày ("Hôm qua"), footer user (avatar + "Minh · Lớp 9 · Kết nối tri thức").
  - **Cột hội thoại (phải)**:
    - **Header**: icon môn 34px nền `--accent-soft` + "Gia sư {Tên môn}" (Baloo 2) + "{mạch} · Lớp 9" + badge "● Bám SGK" (`--ok`).
    - **Thread** (`overflow-y:auto`, gap 16px, nền `--bg`):
      - **Bong bóng học sinh** (phải): nền `--accent`, chữ `--on-accent`, `border-radius: lg lg 6px lg`, shadow glow.
      - **Bong bóng AI** (trái): avatar "D" 32px gradient brand + bubble `--surface`/`--border` `border-radius: lg lg lg 6px`. Chứa markdown + **khối công thức** (nền `--accent-soft`, serif → thay bằng **KaTeX** ở production).
      - **Chip trích dẫn SGK**: "📖 Trang 42 · Bài 3" + icon ↗ tròn → **mở Modal ảnh SGK**. Nền `--accent-soft`, border `--accent-border`, cao 38px pill.
      - **Thẻ video AI**: thumbnail 78×54 gradient accent + tam giác play + tiêu đề + "Video AI · 1:24" → **mở Popup Video**.
      - **Thẻ i-Test**: nền `--accent-soft`, tiêu đề "✏️ i-Test: …", "5 câu · chấm điểm ngay", nút "Bắt đầu luyện tập →" → **mở Modal Quiz**.
    - **Footer**: hàng **chip gợi ý** cuộn ngang (đổi theo môn) + **ô nhập**: nền `--bg`, border 1.5px, `--r-xl`, có nút 🎤 (micro) và nút ↑ gửi (tròn 44px nền `--accent`). Placeholder "Hỏi Gia sư {Tên môn}…".
- **Gợi ý theo môn** (map trong logic, đổi khi switch tab):
  - Toán: "Định lý Viète là gì?", "Vẽ đồ thị hàm bậc hai", "Giải hệ phương trình", "Ôn tập chương 4"
  - Ngữ văn: "Phân tích bài Ánh trăng", "Lập dàn ý nghị luận", "Biện pháp tu từ", "Tóm tắt Làng"
  - Tiếng Anh: "Present Perfect dùng khi nào?", "Từ vựng chủ đề du lịch", "Viết lại câu", "Luyện phát âm"
  - KHTN: "Định luật Ôm", "Cân bằng phương trình hoá học", "Cấu tạo tế bào", "Bài tập điện trở"
  - Sử & Địa: "Cách mạng tháng Tám", "Đặc điểm khí hậu VN", "Vẽ biểu đồ dân số", "Chiến dịch Điện Biên Phủ"
  - Tin học: "Vòng lặp for là gì?", "Sắp xếp nổi bọt", "Hàm trong Python", "Tạo bảng tính"
  - GDCD: "Quyền trẻ em", "Sống có trách nhiệm", "Pháp luật là gì?", "Bảo vệ môi trường"
- **Trả lời linh hoạt theo môn** (khối trả lời tự đổi loại nội dung, cùng khung bubble):
  - Toán/KHTN = **công thức** (KaTeX).
  - Văn/Sử = **đoạn văn + chip trích nguồn** (số trang).
  - Anh = **hội thoại** (2 bong bóng đối thoại) + gạch chân điểm ngữ pháp / từ vựng.

### 4. Modal ảnh trang sách SGK
- Overlay `rgba(6,12,26,.62)` + `backdrop-filter: blur(4px)`, căn giữa. Panel `--surface`, `--r-xl`, `--sh-3`, `width: min(560px,100%)`, `max-height:88vh` scroll. Animation `dtp-pop .25s`.
- Header: "📖 SGK · Trang 42 · Bài 3" + nút ✕. Body: "ảnh trang" giả lập bằng nền kẻ dòng (`repeating-linear-gradient`) + tiêu đề bài + đoạn text + khối công thức. Footer: nguồn "Toán 9, Kết nối tri thức · trang 42" + nút ‹ › chuyển trang.
- **Production**: thay khối giả lập bằng `<img>` ảnh scan trang SGK thật, phóng to/kéo được.

### 5. Modal Quiz (i-Test)
- Panel `width: min(540px,100%)`. Header: icon ✏️ + "i-Test · {chủ đề}" + "Câu 1 / 5" + ✕. Thanh tiến độ 6px (`--surface-3` nền, `--accent` fill 20%).
- Câu hỏi 16px/600. **4 lựa chọn** A–D: nút full-width, badge chữ cái 26px bo 8px viền `currentColor`, `--r-md`.
- **Trạng thái option** (đổi theo tương tác):
  - Chưa chọn: `--surface`/`--border`.
  - Đang chọn (chưa nộp): border `--accent`, nền `--accent-soft`, chữ `--accent-ink`.
  - Sau khi nộp — đáp án đúng: border/chữ `--ok`, nền `ok 12%`, dấu ✔. Đáp án đã chọn mà sai: `--err`, dấu ✘.
- **Banner kết quả** sau nộp: đúng → "🎉 Chính xác!" (nền/viền `--ok`); sai → "❌ Chưa đúng. Đáp án là B…" (`--err`).
- Nút: "Thoát" (ghost) + nút chính "Nộp bài" → sau khi nộp đổi thành "Làm lại →" (reset).

### 6. Popup Video
- Panel `width: min(680px,100%)`. Khung 16:9 gradient `--accent → --accent-strong`, nút play tròn 74px (nền trắng, tam giác `--accent`), nút ✕ góc phải, thanh tiến độ đáy 5px. Dưới: tiêu đề Baloo 2 + mô tả "Video AI minh hoạ · 1:24 · lồng tiếng Việt".
- **Production**: nhúng `<video>`/player thật; **lưu vị trí phát vào localStorage** và đọc lại khi mở.

### 7. Giáo viên — Sinh đề theo ma trận
- **Layout**: `grid-template-columns: 320px 1fr`, gap 18px. Giao diện nghiêm túc, dạng bảng.
- **Panel cấu hình (trái, sticky top 80px)**: chọn Môn (📐 Toán ▾), Khối (Lớp 9 ▾), Học kỳ (HK I ▾); **Số câu theo mức độ** — 3 hàng slider Dễ/TB/Khó với thanh màu `--easy/--mid/--hard` và số câu (5/4/2); ô "Tổng số câu = 11" (nền `--accent-soft`); nút "⚡ Sinh đề" cao 48px.
- **Preview đề (phải)**: header tiêu đề đề + meta (số câu, thời gian tạo) + nút "📄 Xuất Word" / "🖨 In / PDF". Danh sách câu: mỗi câu có **badge mức độ** (● Dễ/TB/Khó theo màu), nội dung, 4 đáp án (đáp án đúng viền `--ok` + nền `ok 10%` + ✔), và `<details>` "Xem lời giải".

### 8. Trạng thái (empty / loading / error / ngoài SGK)
- **Rỗng**: khung dashed, icon 💬, "Chưa có hội thoại / Chọn một gợi ý để bắt đầu."
- **Đang tải**: 3 chấm nảy (`@keyframes dtp-blink`) + 2 dòng skeleton shimmer (`@keyframes dtp-shimmer`, gradient `--surface-2/--surface-3`).
- **Lỗi**: viền/chữ `--err`, nền `err 8%`, "⚠️ Mất kết nối" + nút "Thử lại".
- **Ngoài SGK**: nền `--surface-2`, "📗 Chưa có trong SGK — nội dung này không có trong sách hiện chọn. Em có muốn xem giải thích tổng quát không?"

---

## Interactions & Behavior
- **Chuyển môn**: click tab → `setSubject(key)` → container chat đổi `data-subject` → toàn bộ `var(--accent…)` cascade lại; header icon/tên + gợi ý cập nhật. Bố cục giữ nguyên.
- **Toggle theme**: auto → light → dark → auto. Ở auto không set `data-theme`.
- **Mở/đóng modal**: click chip/thẻ → set `modal`. Overlay click → đóng. **Panel bên trong PHẢI `stopPropagation`** để click nội dung (chọn đáp án, nút play, mũi tên trang) không đóng modal.
- **Quiz**: chọn đáp án → lưu `quiz.q1`; "Nộp bài" → `quizDone=true` (tô đúng/sai + banner); "Làm lại" → reset.
- **Hover**: card nâng `translateY(-1..-3px)` + tăng shadow + đổi `border-color` sang `--accent-border`. Nút chính: `brightness(1.06)` + nâng nhẹ.
- **Animation**: `dtp-fade` (fade+trượt lên 8px, .5s), `dtp-pop` (modal, .25s), `dtp-blink`, `dtp-shimmer`, `dtp-spin`. Tôn trọng `prefers-reduced-motion: reduce` (rút mọi animation về ~0ms).
- **Responsive** (`max-width: 720px`): khung chat về 1 cột, **ẩn sidebar** (chuyển sang drawer/off-canvas ở production); grid sinh đề về 1 cột, panel cấu hình bỏ sticky. Các lưới `auto-fit/auto-fill` tự co.

## State Management
Prototype dùng một component với state:
- `theme`: `'auto' | 'light' | 'dark'` — điều khiển `data-theme` (auto = không set).
- `subject`: một trong `toan|van|anh|khtn|sudia|tin|gdcd` — quyết định theme chat + gợi ý + icon/tên.
- `modal`: `null | 'book' | 'video' | 'quiz'`.
- `quiz`: `{ q1?: 'A'|'B'|'C'|'D' }` — đáp án đã chọn.
- `quizDone`: boolean — đã nộp chưa.

Port sang React: `useState` cho từng biến; một map `SUBJ[key] = {name, icon, cats, sugs}` để render header + chip gợi ý. Đáp án đúng câu mẫu = `'B'`.

Data fetching (production): danh sách môn/khối/bộ sách, lịch sử hội thoại, câu hỏi quiz, ảnh trang SGK, video AI, đề sinh ra — đều từ API. Prototype hardcode nội dung mẫu.

## Assets
- **Logo DTP**: prototype dùng chữ "D" (Baloo 2 700, trắng) trong ô gradient `--brand→--brand-strong`. Thay bằng file logo thật.
- **Icon**: dùng emoji (📐 ✒️ 💬 🔬 🗺️ 💻 ⚖️ 🎒 👩‍🏫 📖 🎬 ✏️ 🔔). Ở production nên thay bằng **bộ icon SVG** đồng bộ (emoji render khác nhau giữa OS). Icon UI nhỏ (↑ ↗ ✕ ‹ ›) là ký tự/SVG inline.
- **Ảnh trang SGK / video AI**: chưa có — cần asset thật từ hệ thống.
- **Fonts**: Be Vietnam Pro + Baloo 2 — **self-host** cho production (prototype dùng Google Fonts).

## Accessibility (WCAG AA)
- Tương phản chữ ≥ 4.5:1 ở cả sáng & tối (token tự pha lại theo nền).
- Mọi hit target ≥ 44×44px; focus ring rõ: `outline: 3px solid color-mix(in oklab, var(--accent) 55%, transparent)`.
- Không chỉ dựa vào màu để phân biệt mức độ — luôn kèm nhãn "● Dễ / TB / Khó".
- Tiếng Việt có dấu đầy đủ. Tôn trọng `prefers-reduced-motion`. Nút icon có `aria-label`.

## Files
- `Gia sư DTP — Design System.dc.html` — bản thiết kế đầy đủ (moodboard, tokens, component library, và 6+ màn: Subject Hub, Chat, Modal SGK/Quiz/Video, Sinh đề, Auth, các trạng thái). Mở trực tiếp trong trình duyệt để xem tương tác. Đọc phần `<style>` trong `<helmet>` để lấy token chính xác và phần logic class để lấy hành vi.
