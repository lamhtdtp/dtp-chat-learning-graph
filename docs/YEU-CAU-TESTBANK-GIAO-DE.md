# Gửi team DTP Testbank — giáo viên giao đề trên Testbank, học sinh làm trong Gia sư DTP

Người gửi: team **learning.dtpsoft.vn** (Gia sư DTP — ôn luyện Toán 6 cho học sinh).
Tài liệu này viết sau khi đọc mã nguồn `dtp-testbank` nhánh `develop` tại `433b379`, nên mọi
chỗ nhắc tới file/dòng đều là chỗ thật. Đọc kèm tài liệu số 24 của các anh
(`24-HUONG-DAN-API-CHO-LEARNING.md`) và bản yêu cầu trước của chúng tôi (`YEU-CAU-TESTBANK.md`,
repo `dtp-chat-learning-graph/docs/`).

Nguồn nghiệp vụ phía learning: US-28 (đăng nhập một lần sang Testbank) và US-29 (đề cuối kỳ hai
cách) trong repo `dtp-chat-learning-tdd/User-Stories/`.

## Bối cảnh

Chủ dự án chốt luồng demo mới ngày 21/10/2026:

```
Giáo viên đăng nhập Gia sư DTP
  → bấm "Soạn & giao đề trên Testbank" → vào thẳng web-teacher, đã đăng nhập (SSO)
  → soạn đề, lưu đề, phát lượt phát → nhận mã vào thi 6 ký tự, đọc cho lớp
Học sinh mở app Gia sư DTP → "Làm đề cuối kỳ" → "Nhập mã đề thầy cô giao"
  → làm bài NGAY TRONG app learning (máy chủ learning gọi delivery thay học sinh)
  → nộp → thấy điểm; giáo viên xem bảng kết quả trên web-teacher như mọi lượt phát khác
```

Learning **bỏ** tính năng giao đề bằng mã tự làm (US-26: learning tự cấp mã, tự chấm). Từ nay
lượt phát, mã vào thi, bài làm và kết quả đều **là của Testbank**. Learning chỉ là một "cửa làm
bài" khác cho học sinh, bên cạnh web-student.

**Learning không xin quyền gì thêm trên kho**: không lưu đề bằng tài khoản đối tác, không tạo
lượt phát, không xem bảng kết quả của giáo viên. Mọi việc của giáo viên đi bằng tài khoản giáo
viên của chính họ.

## Tóm tắt

| # | Việc | Chặn demo? | Ước lượng |
|---|---|---|---|
| **T1** | Delivery chạy trên `testbank.dtpsoft.vn`, máy chủ learning gọi được `/api/delivery/hs/*`; đưa vào tài liệu 24 | **Chặn** | nhỏ — triển khai, không code |
| **T2** | Chặn dò mã theo IP đừng khoá cả trường khi mọi học sinh đi qua máy chủ learning | **Chặn** (bản tối thiểu là đổi cấu hình) | nhỏ → vừa |
| **T3** | Nhận **phiếu đăng nhập** do learning ký → mở phiên web-teacher | **Chặn** SSO (có phương án tạm) | vừa |
| **T4** | Tài khoản giáo viên demo, cùng email với learning, phạm vi Toán 6 | **Chặn** | vận hành |
| T5 | Chi tiết bài làm **sau khi nộp** cho đối tác (đáp án, lời giải, YCCĐ từng câu) | Không chặn luồng giao đề; chặn phần "kết quả theo YCCĐ + Đề xuất" trên đề giao | nhỏ (dùng lại lớp có sẵn) |
| T6 | Định danh học sinh đối tác hiện trên bảng kết quả của giáo viên | Không | nhỏ |
| T7 | Đường học sinh **dành cho đối tác** có token (`/doi-tac/*`): một học sinh một bài, đếm sai mã theo học sinh | Không (T2 tối thiểu thay tạm) | vừa |
| T8 | Nút "Đăng nhập bằng tài khoản Gia sư DTP" trên trang đăng nhập Testbank | Không | nhỏ, sau T3 |
| T9 | Nhật ký đăng nhập qua learning | Không | nhỏ |
| T10 | Tuỳ chọn theo lượt phát: cho học sinh xem đáp án sau khi nộp / sau khi đóng | Không | nhỏ |
| T11 | Báo learning khi giáo viên chấm xong câu tự luận | Không | để sau |

Thứ tự đề nghị: T1 + T2 (cấu hình) + T4 trước — đủ chạy demo với đăng nhập mật khẩu. Rồi T3.
Rồi T7 + T6 + T5 cùng một đợt (chung một đường đối tác).

---

## T1 — Delivery cho máy chủ learning gọi

### Hiện trạng

- `deploy/compose.dev.yml` có service `delivery`; `deploy/nginx-web.conf:53` chuyển
  `/api/delivery/` (cả `/hs` lẫn `/gv`) tới delivery. Tài liệu 24 mục 1 chỉ liệt kê identity,
  content, exam — chúng tôi không biết delivery đã chạy trên `testbank.dtpsoft.vn` chưa.
- Đường `/hs/*` không cần token (`routers/hs.py`), nên **về kỹ thuật learning gọi được ngay**
  nếu delivery đã chạy.

### Xin các anh

1. Xác nhận (hoặc triển khai) delivery trên môi trường dev, cho biết gốc địa chỉ.
2. Thêm một mục vào tài liệu 24 cho đường học sinh: `POST /hs/vao-thi`, `GET /hs/bai-lam`,
   `PUT /hs/bai-lam/tra-loi`, `POST /hs/bai-lam/nop`, mã lỗi, hình dạng câu trả lời 5 dạng —
   để hai bên cùng một văn bản khi có thay đổi.

### Learning cam kết

- Chỉ gọi máy chủ–máy chủ; **khoá bài làm không bao giờ xuống trình duyệt** học sinh learning.
- Học sinh learning không gõ họ tên: learning gửi `ho_ten` = `"<Tên tài khoản> · HS<mã số>"`,
  ví dụ `"Nguyễn Văn An · HS1024"` (2–100 ký tự, đúng ràng buộc `VaoThiIn.ten_hop_le`).
- Mỗi học sinh learning **một bài cho mỗi mã**: learning giữ khoá bài làm theo
  (học sinh, mã) và không gọi `vao-thi` lần hai cho cùng cặp đó (vì `bai_lam.vao_thi` luôn tạo
  bài mới).
- Learning tự kiểm định dạng mã trước (6 ký tự trong `[A-HJKMNP-Z2-9]`) — sai định dạng
  không bao giờ tới các anh, không ăn vào bộ đếm sai mã.

---

## T2 — Chặn dò mã đừng khoá cả trường

### Vấn đề

`routers/hs.py` đếm lần nhập sai theo `ip_may_khach` (`X-Real-IP`); `settings.py`:
`so_lan_sai_toi_da = 10`, `cua_so_sai_phut = 10`. Mọi học sinh learning đi ra từ **cùng một IP**
(máy chủ learning). 10 lần gõ sai cộng dồn của cả trường trong 10 phút → **mọi học sinh
learning** bị chặn 10 phút, kể cả em gõ đúng.

Learning đã tự chặn theo tài khoản: 5 lần sai / 10 phút / học sinh → chặn 10 phút ở phía
learning, không gửi sang các anh. Nhưng 3 em gõ sai 4 lần là đủ khoá cả trường.

### Xin các anh — hai mức

- **Tối thiểu (chặn demo):** trên môi trường dev/demo, nâng `so_lan_sai_toi_da` (đã là biến
  cấu hình) lên mức đủ cho một trường, ví dụ 200 trong 10 phút. Không cần sửa mã.
- **Đầy đủ (không chặn demo):** làm T7 — lời gọi có token đối tác thì đếm theo **học sinh đối
  tác**, không theo IP; giữ một trần tổng theo đối tác để kẻ chiếm được máy chủ learning không dò
  mã vô hạn.

Khi bị chặn, learning đọc `429` + `Retry-After` (đã có) để báo "thử lại sau N phút". Xin giữ
nguyên hai thứ đó.

---

## T3 — Đăng nhập một lần: phiếu do learning ký

### Vì sao learning cần

Giáo viên đã đăng nhập learning; bắt họ nhớ thêm mật khẩu Testbank là chỗ demo vấp. Testbank
chưa có SSO nào (`services/identity/routers/auth.py` chỉ có `/auth/login` email + mật khẩu; nút
Google trên `apps/web-teacher/src/pages/LoginPage.tsx:179` đang bị comment).

Learning **không** xin Testbank tin learning cho mọi tài khoản: chỉ tài khoản được quản trị
Testbank **bật cờ**, và **không bao giờ** tài khoản có vai quản trị.

### Luồng

```
[trình duyệt GV, tab CMS learning]
   1. bấm "Soạn & giao đề trên Testbank"
   2. ── POST (learning) xin phiếu ──► máy chủ learning ký phiếu (sống 60 giây)
   3. ◄── { url: "https://testbank.dtpsoft.vn/sso#phieu=<JWT>" }
   4. mở tab mới tới url đó
[tab mới, web-teacher]
   5. đọc phiếu từ phần sau dấu # rồi XOÁ nó khỏi thanh địa chỉ (history.replaceState)
   6. ── POST /api/identity/auth/sso/learning { "phieu": "<JWT>" } ──► identity
   7. ◄── TokenOut, y hệt /auth/login  (hoặc lỗi, xem bảng)
   8. xoá token cũ đang có trên máy (nếu có), lưu cặp token mới như sau đăng nhập, vào màn chính
```

Phiếu đi sau dấu `#` để **không** lọt vào nhật ký nginx hay header `Referer`. Nếu các anh muốn
dùng `?phieu=` thì vẫn được, nhưng xin đừng ghi query vào nhật ký truy cập ở đường `/sso`.

Đường `/sso` là một màn của web-teacher (SPA phục vụ ở `/`, `nginx-web.conf:67`), không phải
một đường của identity.

### Phiếu — định dạng đề xuất

JWT ký **RS256** bằng khoá riêng của learning. Testbank chỉ giữ **khoá công khai** của learning.

Header:

```json
{ "alg": "RS256", "typ": "JWT", "kid": "learning-2026-10" }
```

Thân:

| Claim | Giá trị | Ghi chú |
|---|---|---|
| `iss` | `"gia-su-dtp"` | cố định |
| `aud` | `"testbank-identity"` | cố định; phiếu có `aud` khác thì từ chối |
| `typ` | `"sso-ticket"` | để không ai đưa nhầm một loại token khác vào |
| `sub` | id tài khoản learning, dạng chuỗi, ví dụ `"1024"` | để nhật ký truy ngược được |
| `email` | email tài khoản learning, chữ thường, đã cắt khoảng trắng | **khoá liên kết** |
| `name` | họ tên trên learning | chỉ để hiển thị / ghi nhật ký; không ghi đè tên Testbank |
| `role` | `"giao_vien"` \| `"chuyen_gia"` \| `"admin"` | vai **phía learning**; học sinh không bao giờ được cấp phiếu |
| `iat` | thời điểm ký (giây) | |
| `exp` | `iat + 60` | |
| `jti` | UUID v4 | **dùng một lần** |

Ví dụ thân:

```json
{
  "iss": "gia-su-dtp", "aud": "testbank-identity", "typ": "sso-ticket",
  "sub": "1024", "email": "hoa@truong.edu.vn", "name": "Trần Thị Hoa", "role": "giao_vien",
  "iat": 1792564800, "exp": 1792564860, "jti": "6f1c2a8e-3d0b-4a57-9a8e-2b7e5f1d9c40"
}
```

Phiếu không chứa mật khẩu, token phiên learning hay bất kỳ dữ liệu của người khác.

### Khoá công khai của learning

- Learning công bố tại `GET https://learning.dtpsoft.vn/auth/.well-known/jwks.json`, dạng **JWK
  chuẩn** (`kty`, `kid`, `use: "sig"`, `alg: "RS256"`, `n`, `e`), **kèm thêm** trường `pem` cho
  giống lối JWKS hiện tại của các anh.
- Đề nghị Testbank **cấu hình cứng** khoá PEM của learning qua biến môi trường (giống
  `jwt_public_key` của delivery), JWKS chỉ để đổi khoá về sau. Như vậy identity không phụ thuộc
  learning còn sống hay không lúc kiểm phiếu.
- Khi đổi khoá: learning công bố khoá mới với `kid` mới trước ít nhất 24 giờ, rồi mới ký bằng nó.

### Identity kiểm gì, theo thứ tự

1. Chữ ký đúng khoá learning (theo `kid`), `alg` đúng `RS256` (không nhận `none`/HS*).
2. `iss`, `aud`, `typ` đúng như bảng.
3. `exp` chưa qua, `iat` không ở tương lai — cho lệch đồng hồ tối đa 10 giây.
4. `jti` chưa từng dùng → **ghi lại ngay** (giữ ít nhất tới `exp` + 10 giây). Ghi ở CSDL hoặc
   Redis, không trong bộ nhớ tiến trình — chạy nhiều bản sao vẫn đúng "một lần".
5. Tìm tài khoản Testbank theo `email` (không phân biệt hoa thường).
6. Tài khoản đang hoạt động, đã **bật cờ "cho phép đăng nhập qua Gia sư DTP"**.
7. Tài khoản có vai `TEACHER` hoặc `COORDINATOR`, và **không** có `ADMIN`, vai chuyên gia bộ môn
   hay `DOI_TAC_ON_LUYEN`.
8. Cấp cặp token **giống hệt** `POST /auth/login` (`issue_pair`), ghi nhật ký đăng nhập với nguồn
   `"gia-su-dtp"`.

Không tự tạo tài khoản; không đồng bộ vai, phạm vi, họ tên từ learning sang.

### Lỗi — hình dạng đề xuất

Theo lối `{ma, thong_diep}` delivery đang dùng, để web-teacher hiện thẳng `thong_diep`:

| HTTP | `detail.ma` | `detail.thong_diep` | Khi nào |
|---|---|---|---|
| 401 | `PHIEU_KHONG_HOP_LE` | Liên kết đăng nhập không hợp lệ | sai chữ ký, sai `iss`/`aud`/`typ`, thiếu claim, sai định dạng |
| 401 | `PHIEU_HET_HAN_HOAC_DA_DUNG` | Liên kết đăng nhập đã dùng hoặc đã hết hạn, thầy cô bấm lại từ Gia sư DTP | quá `exp`, `jti` đã dùng |
| 403 | `CHUA_LIEN_KET` | Email {email} chưa được liên kết với Testbank. Thầy cô nhờ quản trị Testbank tạo tài khoản giáo viên với email này. | không có tài khoản, hoặc có mà chưa bật cờ |
| 403 | `TAI_KHOAN_KHOA` | Tài khoản Testbank của thầy cô đã bị khoá | `is_active = false` |
| 403 | `VAI_KHONG_DUOC_SSO` | Tài khoản này phải đăng nhập Testbank bằng mật khẩu | vai không thuộc bước 7 |

`CHUA_LIEN_KET` dùng chung cho "không có tài khoản" và "chưa bật cờ": không cho người cầm phiếu
biết email nào tồn tại trên Testbank. Màn lỗi của web-teacher nên có hai nút: "Về Gia sư DTP"
và "Đăng nhập bằng mật khẩu".

### Phần learning tự làm (để các anh biết bên kia làm gì)

- Chỉ vai `giao_vien` / `chuyen_gia` / `admin` đang hoạt động xin được phiếu; học sinh bị từ chối.
- Learning ghi nhật ký mỗi lần cấp phiếu (thời điểm, `sub`, `jti`), không ghi nguyên phiếu.

---

## T4 — Tài khoản giáo viên demo

Tạo tài khoản vai `TEACHER`, phạm vi `TO / 06`, **cùng email** với tài khoản giáo viên trên
learning (danh sách gửi qua kênh riêng), bật cờ liên kết khi đã có T3. Trước khi có T3 thì đặt
mật khẩu và gửi qua kênh riêng như tài khoản dịch vụ.

Nếu chưa kịp thêm cờ vào màn quản trị tài khoản, một danh sách email được phép đặt bằng biến môi
trường của identity là đủ cho demo.

---

## T5 — Chi tiết bài làm sau khi nộp, cho đối tác

### Vì sao learning cần

Sau khi nộp, `hien_thi.bai_lam_hs` chỉ trả `ket_qua` (điểm + trạng thái từng câu) và `cau=None`.
Đúng cho web-student. Nhưng learning có vòng **Kết quả theo YCCĐ → Đề xuất học liệu → Test thêm
đúng phần còn yếu** (US-27). Không có YCCĐ và đáp án từng câu thì đề thầy cô giao đứng ngoài vòng
đó — học sinh chỉ thấy một con số.

### Xin các anh

Một đường đọc **chỉ sau khi bài đã nộp**, chỉ cho token đối tác, chỉ cho bài do chính đối tác ấy
tạo (đi kèm T7):

```
GET /doi-tac/bai-lam/{bai_lam_id}/chi-tiet
Authorization: Bearer <access token của tài khoản DOI_TAC_ON_LUYEN>
```

Thân trả về: **đúng lớp `BaiLamChiTiet` của đường giáo viên** (`schemas.py:150`), không thêm
không bớt — `hien_thi.bai_lam_chi_tiet` đã dựng sẵn mọi thứ learning cần:

| Trường mỗi câu (`CauKetQuaGv`) | Learning dùng để |
|---|---|
| `qid`, `phien_ban`, `ma_hien_thi` | khớp học liệu gắn theo câu / phương án (US-27) |
| `ar_id`, `yccd`, `muc_do` | kết quả theo YCCĐ, thống kê YCCĐ của học sinh |
| `de_bai`, `phuong_an`, `khoi_du_kien`, `anh` | hiện lại đề cùng kết quả (đường học sinh không còn trả câu sau khi nộp) |
| `tra_loi`, `dap_an`, `bai_giai`, `diem`, `trang_thai` | hiện đúng/sai, đáp án, lời giải |

Thêm **một** trường cấp bài (gắn với T10, mặc định `true` khi T10 chưa có):

```json
"hien_dap_an_cho_hoc_sinh": true
```

Learning chỉ cho học sinh thấy `dap_an` / `bai_giai` khi cờ này `true`. YCCĐ và học liệu đề xuất
vẫn dùng được khi cờ `false` (không lộ đáp án).

| HTTP | Khi nào |
|---|---|
| 409 `{"ma":"CHUA_NOP","thong_diep":"Bài chưa nộp"}` | bài đang làm — **không bao giờ** trả đáp án trước khi nộp |
| 404 | bài không có, hoặc không do đối tác này tạo (cùng một câu trả lời) |

---

## T6 — Định danh học sinh đối tác trên bảng giáo viên

Hai học sinh trùng tên trong lớp là chuyện thường. Learning gửi kèm `"· HS1024"` vào `ho_ten` để
giáo viên phân biệt được, nhưng đó là mẹo. Xin thêm vào `BaiLamTomTat` (và `BaiLamChiTiet`):

```json
"hoc_sinh_doi_tac": { "doi_tac": "gia-su-dtp", "ma": "1024" }   // null với bài vào từ web-student
```

để web-teacher hiện một nhãn "Gia sư DTP" và lọc / tìm được theo mã.

---

## T7 — Đường học sinh dành cho đối tác

### Vì sao

Đường `/hs/*` thiết kế cho người **ẩn danh**: danh tính là khoá bài làm, chặn dò theo IP, mỗi lần
vào là một bài mới. Learning thì **biết** học sinh là ai và gọi từ một máy chủ đã có token đối
tác. Một đường riêng cho đúng trường hợp này giải quyết gọn T2 (đếm theo học sinh), một học sinh
một bài (Testbank bảo đảm, không trông vào learning), và là chỗ gắn T5, T6.

Đặt ở tiền tố riêng `/doi-tac/*` để **không** lộ qua `nginx-web-student.conf` (chỉ mở `/hs/*`) và
không đụng gì tới web-student.

### Hợp đồng đề xuất

Mọi lời gọi: `Authorization: Bearer <access token DOI_TAC_ON_LUYEN>`. Vai khác → 403. Bài làm
được nhận diện bằng `bai_lam_id` (không bí mật — đã có token đối tác); đối tác chỉ chạm được bài
do mình tạo, bài khác → 404.

**Thân trả về giữ nguyên các lớp đang có** (`BaiLamHs`, `LuuOut`, `TraLoiIn`…), để learning dùng
một bộ chuyển đổi cho cả `/hs` lẫn `/doi-tac`.

#### Vào thi

```
POST /doi-tac/vao-thi
{
  "ma": "K7M3PX",
  "hoc_sinh": { "ma": "1024", "ho_ten": "Nguyễn Văn An · HS1024" }
}
```

| Kết quả | HTTP | Thân |
|---|---|---|
| Lượt phát mở, học sinh chưa có bài | 201 | `{ "bai_lam_id": "<uuid>", "vao_lai": false, "bai_lam": BaiLamHs }` |
| Học sinh đã có bài trên lượt phát này (đang làm hoặc đã nộp) — **kể cả khi lượt phát đã đóng** | 200 | `{ "bai_lam_id": "<cũ>", "vao_lai": true, "bai_lam": BaiLamHs }` |
| Mã sai, hoặc lượt phát đã đóng mà học sinh chưa có bài | 404 | `"Mã không đúng hoặc bài thi đã đóng"` (đúng thông điệp `/hs`) |
| Học sinh này sai quá nhiều | 429 + `Retry-After` | như `/hs` |

- "Một học sinh một bài": duy nhất theo (lượt phát, đối tác, `hoc_sinh.ma`), bảo đảm ở CSDL — hai
  lời gọi đồng thời cho cùng học sinh ra **cùng một** `bai_lam_id`.
- `hoc_sinh.ma`: 1–64 ký tự `[A-Za-z0-9_-]`. `ho_ten`: như `VaoThiIn` hiện có.
- Đếm sai mã theo (đối tác, `hoc_sinh.ma`): 10 lần / 10 phút → chặn 10 phút (cùng con số với IP
  hiện nay). Thêm một trần tổng theo đối tác, đề xuất 300 lần sai / 10 phút.
- Lần vào thi bị chặn không ghi thêm lần sai (giữ đúng lý lẽ trong `het_han_chan`).

#### Xem bài, lưu câu, nộp

```
GET  /doi-tac/bai-lam/{bai_lam_id}              → BaiLamHs        (như GET /hs/bai-lam, gồm tự nộp khi hết giờ)
PUT  /doi-tac/bai-lam/{bai_lam_id}/tra-loi      LuuTraLoiIn → LuuOut   (như PUT /hs/bai-lam/tra-loi: 409 DA_NOP / HET_GIO, 422 từng câu)
POST /doi-tac/bai-lam/{bai_lam_id}/nop          NopIn → BaiLamHs       (như POST /hs/bai-lam/nop: nộp lại trả đúng kết quả lần đầu)
GET  /doi-tac/bai-lam/{bai_lam_id}/chi-tiet     → BaiLamChiTiet + hien_dap_an_cho_hoc_sinh   (T5)
```

Mọi luật nghiệp vụ (`seq` chống gửi cũ tới muộn, hạn nộp + 30 giây gia hạn, đóng lượt phát thì nộp
hộ, khoá đọc kết quả 30 ngày sau khi đóng) **giữ nguyên** như `/hs` — chỉ đổi cách nhận diện bài.
Chính vì vậy đề nghị hai tiền tố gọi chung các hàm trong `bai_lam.py` / `hien_thi.py`.

---

## T8, T9, T10, T11 — không chặn

- **T8.** Trên trang đăng nhập web-teacher, nút "Đăng nhập bằng tài khoản Gia sư DTP": chuyển sang
  `https://learning.dtpsoft.vn/sso/testbank?quay_ve=<url>`; learning đăng nhập (nếu chưa) rồi đi
  tiếp luồng T3. Cùng phiếu, cùng đường nhận — làm sau T3.
- **T9.** Nhật ký đăng nhập qua learning: thời điểm, email, `jti`, kết quả, `detail.ma` khi từ chối.
- **T10.** Cờ theo lượt phát "học sinh xem đáp án: ngay sau khi nộp / sau khi đóng / không" —
  learning tuân theo qua `hien_dap_an_cho_hoc_sinh` (T5). Web-student cũng có thể dùng.
- **T11.** Khi giáo viên chấm xong câu tự luận, learning muốn biết để cập nhật điểm của em. Chưa
  cần đường đẩy; learning đọc lại `GET /doi-tac/bai-lam/{id}` khi học sinh mở bài là đủ cho tới
  khi có nhu cầu thật.

---

## Phương án tối thiểu nếu chưa kịp

| Chưa kịp | Learning làm thế nào | Đánh đổi |
|---|---|---|
| T3 | Nút trên CMS learning chỉ mở trang đăng nhập web-teacher; giáo viên dùng mật khẩu T4 | Hai mật khẩu; demo không có "đăng nhập một lần" |
| T7 (đã có T1 + T2 tối thiểu) | Learning dùng nguyên `/hs/*`: gửi `ho_ten` có "· HS<mã>", giữ khoá bài làm ở máy chủ theo (học sinh, mã), tự bảo đảm một bài một em | Testbank không biết đó là học sinh learning; bảo đảm "một bài" chỉ ở phía learning; đếm sai mã vẫn theo IP (đã nâng ngưỡng) |
| T1 | Ô nhập mã của learning mở **web-student** ở tab mới với `?ma=` điền sẵn | Học sinh rời app, tự gõ tên, một em làm được nhiều bài, learning không có kết quả |
| T5 | Học sinh chỉ thấy điểm và Đúng/Sai từng câu; vòng "YCCĐ → Đề xuất" trình diễn bằng đề cuối kỳ tự rút | Đề thầy cô giao không có đáp án / lời giải / YCCĐ phía học sinh; giáo viên vẫn xem đủ trên web-teacher |
| T6 | Mẹo "· HS<mã>" trong họ tên | Tên dài; không lọc được theo mã |

---

## Câu hỏi cho các anh

1. Delivery đã chạy trên `testbank.dtpsoft.vn` chưa? Có định mở prod cho đối tác cùng lúc với
   identity / content / exam không?
2. Đếm sai mã theo IP: các anh chịu nâng ngưỡng trên dev cho demo không, hay muốn làm thẳng T7?
3. SSO: các anh có muốn chỉ cho vai `TEACHER` (bỏ `COORDINATOR`) không? Chúng tôi đề xuất cả hai
   vì cả hai đều được phát đề (`auth.GV_ROLES`), nhưng `ADMIN` thì không bao giờ.
4. Cờ "cho phép đăng nhập qua Gia sư DTP": thêm vào màn Tài khoản của quản trị, hay danh sách email
   bằng cấu hình là đủ trong giai đoạn này?
5. Đường nhận phiếu: `POST /api/identity/auth/sso/learning` và màn `/sso` của web-teacher như trên
   có hợp lối các anh không? Đổi tên thì báo để learning đổi theo trước demo.
6. T5 trả nguyên `BaiLamChiTiet` (gồm `dap_an`, `bai_giai`) cho tài khoản đối tác: có vướng
   nguyên tắc nào về kho không? Lượt phát chỉ lấy câu kho PUBLIC (ADR 0018) nên chúng tôi hiểu
   là không — xin xác nhận.
7. Mã vào thi của Testbank và mã cũ của learning dùng **cùng bảng ký tự**. Learning đã ngừng cấp
   mã của mình nên không còn nhập nhằng; các anh có định đổi bảng ký tự hay độ dài mã không?

---

## Liên hệ

Nghiệp vụ và kịch bản nghiệm thu đầy đủ:
`dtp-chat-learning-tdd/User-Stories/EPIC-06-Nen-Tang/US-28-sso-giao-vien-sang-testbank.md`,
`dtp-chat-learning-tdd/User-Stories/EPIC-03-Sinh-De/US-29-de-cuoi-ky-hai-cach-ma-testbank-va-tu-sinh.md`.
