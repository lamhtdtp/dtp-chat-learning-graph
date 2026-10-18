# Runbook: deploy lên server + migrate + dựng lại data bằng AI

Bổ sung cho `DEPLOY-DEV.md` (cài server từ đầu). File này là **quy trình lặp lại
mỗi lần lên bản mới**: deploy → migrate → dọn dữ liệu → dựng lại nội dung bằng AI.

Mọi lệnh chạy ở gốc repo trên server, qua `./deploy.sh` (đã gói sẵn cặp compose
`docker-compose.app.yml` + `docker-compose.dev-server.yml`).

---

## 0. Trước khi bắt đầu — 3 điều dễ quên

| Điều | Vì sao |
|---|---|
| `VITE_API_URL` **nướng vào lúc build** frontend | Đổi domain API thì phải `build` lại `web`/`web-admin`, restart không đủ. Thêm route API mới thì KHÔNG cần gì (frontend gọi URL tuyệt đối). |
| Thêm mount ghi-được trong compose ⇒ phải `up -d` (recreate) | `restart` không áp mount mới. Bản này có 3 mount mới, xem §2. |
| Sinh ảnh/soạn bài bằng AI có **hạn mức 50 request/ngày** của VNGCloud | Vượt là 429. Xem tính toán ở §5 trước khi chạy hàng loạt. |

---

## 1. Lấy code mới

```bash
cd ~/dtp-chat-learning-graph      # hoặc đường dẫn repo trên server
git pull
```

Xem trước những gì sắp đổi (đặc biệt compose và migration):

```bash
git log --oneline -15
git diff --stat HEAD@{1} -- docker-compose.app.yml alembic/versions/
```

---

## 2. Build + chạy

```bash
./deploy.sh up            # build lại image thay đổi rồi up -d
./deploy.sh ps            # api, worker, web, web-admin, redis, qdrant phải Up
```

> **Bản này có 3 mount ghi-được mới**, nên bắt buộc `up -d` chứ không `restart`:
> - `api`: `./data/books` — màn "Nạp sách bằng AI" ghi ảnh trang chuyên gia kéo vào
> - `worker`: `./data/videos` — `seed --media` ghi ảnh minh hoạ
> - `worker`: `./data/books` — job nạp sách đọc ảnh trang
>
> Thiếu chúng thì lỗi là `OSError: [Errno 30] Read-only file system` **giữa
> request**, sau khi đã tiêu lượt gọi model. Kiểm nhanh:
> ```bash
> ./deploy.sh exec api sh -c 'touch /app/data/books/.w && rm /app/data/books/.w && echo books OK'
> ./deploy.sh exec api sh -c 'touch /app/data/videos/.w && rm /app/data/videos/.w && echo videos OK'
> ```

### 2a. nginx trên host phải proxy đủ tiền tố API

nginx trên host là **cửa duy nhất**: tiền tố nào không có trong `location` sẽ rơi
xuống SPA và nginx trả `index.html` **với status 200**. Client parse HTML thành
JSON rồi báo *"Không gọi được máy chủ"* — không có mã HTTP nào để lần.

Đã mất một lần với `/on-tap` (ôn tập chương + học kỳ). Danh sách đúng:

```nginx
location ~ ^/(admin|auth|cms|curriculum|health|lessons|me|on-tap|progress|quiz|tutor|video)(/|$) {
```

Sửa trên server:

```bash
sudo nano /etc/nginx/conf.d/chat-learning.conf     # sửa dòng location ~ ^/(...)
sudo nginx -t && sudo systemctl reload nginx
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' \
  "https://DOMAIN/on-tap?pham_vi=mach&gia_tri=x"   # phải là JSON, không phải text/html
```

`text/html` = vẫn chưa proxy. `401`/`400` + `application/json` = đã đúng đường
(chỉ là thiếu token hoặc tham số).

**Có NHIỀU khối server — phải sửa hết.** App học sinh và CMS ở hai domain khác
nhau, mỗi khối có `location` riêng; certbot còn có thể tạo thêm khối `443`. Sửa
một khối thì domain kia vẫn chết. Repo có sẵn hai mẫu:
`infra/nginx-dev-domain.conf.example` (app học) và
`infra/nginx-admin-domain.conf.example` (CMS, container `web-admin` cổng 8081).

#### Sửa rồi vẫn lỗi? Tìm khối server còn thiếu

`nginx -T` in ra cấu hình **đang có hiệu lực**, gồm mọi file và mọi khối server:

```bash
sudo nginx -T | grep -nE "server_name|listen |location ~ \^/\("
```

Đọc kết quả: mỗi `server_name` phải có một dòng `location ~ ^/(…)` chứa đủ tiền
tố. Khối nào thiếu → đó là domain đang lỗi. Ba chỗ hay bị bỏ sót:

| Chỗ | Dấu hiệu |
|---|---|
| Khối của domain **CMS** | app học sinh chạy, CMS báo "Không gọi được máy chủ" |
| Khối **`listen 443`** do certbot tạo | sửa xong, `curl http://` đúng mà `https://` vẫn sai |
| File khác trong `sites-enabled/` | `conf.d/` đã sửa mà vẫn không đổi |

Xác nhận từng domain (phải là `application/json`, không phải `text/html`):

```bash
for d in DOMAIN_HOC_SINH DOMAIN_CMS; do
  echo -n "$d -> "
  curl -sI "https://$d/on-tap?pham_vi=mach&gia_tri=x" | grep -i '^content-type'
done
```

`tests/infra/test_duong_dan_api.py` so **cả hai** mẫu với router thật và kiểm
chúng khớp nhau, nên thêm router mà quên sửa nginx là test đỏ.

### 2c. Tắt trợ lý AI kèm thông báo (khi provider hỏng)

Provider mất model / hết quota / đang bảo trì → đừng để học sinh gõ câu hỏi rồi
nhận lỗi. Bật cờ trong `.env`:

```bash
TRO_LY_BAO_TRI=true
# TRO_LY_BAO_TRI_NHAN=Trợ lý nâng cấp tới 20h hôm nay, em quay lại sau nhé!
./deploy.sh up -d api          # restart KHÔNG nạp lại env
```

Học sinh thấy lời nhắn ngay trong khung trợ lý; ô nhập, micro, chip gợi ý và mọi
nút "Hỏi về đoạn này" đều tắt. Chặn ở đầu `/tutor/ask` nên **không gọi LLM và
không trừ lượt hỏi** của các em.

Kiểm:

```bash
curl -s localhost:8000/tutor/limits -H "Authorization: Bearer $TOKEN"
# -> {"max_chars":500,"bao_tri":true,"bao_tri_nhan":"..."}
```

Còn nếu chỉ MỘT phần AI hỏng (vd hết model embedding) thì đừng bật cờ này: chat
vẫn trả lời được bằng nội dung bài đã soạn, chỉ mất phần tra cứu SGK. Chạy
`./deploy.sh llm-check` để biết đang thiếu cái gì.

### 2b. Dùng Redis riêng (không phải Redis trong compose)

App chỉ cần **Redis thường** — `get/set/incr/expire` cho cache LLM + hạn mức
hỏi/ngày, và làm Celery broker. Yêu cầu RediSearch đã mất từ khi bỏ checkpointer
LangGraph ở P5, nên Redis native / ElastiCache / Redis trong LAN đều dùng được.

Trong `.env` của server:

```bash
REDIS_URL=redis://192.168.1.19:6379/0
# có mật khẩu:
# REDIS_URL=redis://:MATKHAU@192.168.1.19:6379/0
# có cả user (Redis 6 ACL):
# REDIS_URL=redis://USER:MATKHAU@192.168.1.19:6379/0
# TLS:
# REDIS_URL=rediss://:MATKHAU@host:6380/0
```

Dùng **cổng thật của Redis đó (6379)**, không phải 6380 — 6380 chỉ là cổng host
map ra của service trong compose.

Rồi **đừng khởi động service `redis` bundled** nữa, tránh chạy song song hai
Redis và nhầm cái nào đang được dùng:

```bash
./deploy.sh up -d qdrant api worker web web-admin
```

Kiểm trước khi chạy tiếp — từ **trong container**, vì đó mới là chỗ thật sự kết nối:

```bash
./deploy.sh exec api python -c "import os,redis; \
u=os.environ['REDIS_URL']; print('dùng:', u); \
print('ping:', redis.from_url(u).ping())"
```

Ba điều dễ vướng với Redis LAN:

| Vướng | Dấu hiệu | Xử |
|---|---|---|
| Redis chỉ `bind 127.0.0.1` | `Error 111 Connection refused` | sửa `bind 0.0.0.0` + `protected-mode no` (hoặc bind đúng IP) rồi restart Redis |
| Có mật khẩu mà `REDIS_URL` thiếu | `NOAUTH Authentication required` | thêm `:MATKHAU@` |
| Container không ra được LAN | timeout chứ không refuse | kiểm firewall/route; `192.168.x` từ bridge network thường vẫn tới được |

> Nhớ là **Redis lỗi không làm app chết** — hạn mức hỏi/ngày fail-open và job
> video chỉ ghi cảnh báo. Nên phải chủ động ping như trên, đừng đợi triệu chứng.

---

## 3. Migrate

```bash
./deploy.sh migrate       # = alembic upgrade head trên RDS
```

Xác nhận:

```bash
./deploy.sh run --rm --no-deps api alembic current
```

`upgrade head` **idempotent** — chạy lại khi đã ở head thì không làm gì. Nếu bỏ
qua vài bản thì nó chạy tuần tự tất cả, không cần chỉ định từng revision.

### Hai migration của bản này

| Revision | Việc | Ảnh hưởng |
|---|---|---|
| `b7c8d9e0f1a2` | tạo bảng `book_jobs` | Bảng mới, không đụng dữ liệu cũ |
| `c8d9e0f1a2b3` | thêm `quiz_attempts.nguon` | Cột mới, `server_default='nhanh'` nên dòng cũ tự có giá trị |

**Lưu ý về `nguon`:** các lượt làm đề ôn tập ghi *trước* migration sẽ mang nhãn
`nhanh` và không phân biệt lại được. Tính năng ôn tập chưa từng deploy nên trên
server không có dòng nào như vậy — nhưng nếu đã deploy giữa hai bản thì bảng
"Kết quả học tập" trong CMS sẽ đếm chúng như bài kiểm tra nhanh.

### Rollback migration

```bash
./deploy.sh run --rm --no-deps api alembic downgrade -1
```

Cả hai migration của bản này đều `downgrade` an toàn (drop cột/bảng mới). Nhưng
downgrade `c8d9e0f1a2b3` là **mất dữ liệu**: nhãn `nguon` không dựng lại được.

---

## 4. Dọn dữ liệu sau khi deploy

### 4.1 Gộp đơn vị kiến thức trùng (bắt buộc nếu chưa làm)

Nạp ma trận các bản trước so tên bằng chuỗi tuyệt đối, nên danh mục Toán 6 bị
phình từ 21 lên 42 đơn vị. Học sinh bấm vào bản rỗng thấy "đang được biên soạn"
trong khi bài đã soạn nằm ở bản kia.

Loader đã sửa để không đẻ thêm, nhưng **phần đã lỡ tạo phải dọn tay**:

**CMS → Hệ thống → Quản lý danh mục** → banner vàng ở đầu trang.

- *Trùng y hệt tên* → bấm **"Gộp tất cả N nhóm"**, an toàn.
- *Nghi trùng* → xác nhận **từng cặp**. Cặp nào có cờ ⚠️ "cả hai bản đều đã có
  bài" thì đọc kỹ: trên dữ liệu thật có `Hình có tâm đối xứng` vs `Hình có trục
  đối xứng` giống nhau 88% mà là **hai bài khác nhau**.
- *Do nạp ma trận tạo, chưa có bài* → chọn đơn vị đích rồi gộp.

Gộp dồn cả ô ma trận và bài học sinh đã làm sang bản giữ trước khi xoá — không
mất dữ liệu.

### 4.2 Kiểm tra kho SGK (Qdrant)

Trang **Nạp sách bằng AI** hiển thị một trong ba trạng thái:

| Hiện | Nghĩa | Làm gì |
|---|---|---|
| số liệu bình thường | kho có dữ liệu | không cần gì |
| "Kho tri thức còn rỗng" | Qdrant chạy, chưa có collection | nạp sách, xem §5.1 |
| "Không nối được kho tri thức" | Qdrant chết/sai URL | `./deploy.sh logs qdrant` |

---

## 5. Dựng lại data bằng AI

> **Thứ tự bắt buộc:** kho SGK → ma trận → nội dung bài. Soạn bài trước khi có
> kho SGK thì AI không có ngữ liệu để bám, ra nội dung chung chung; soạn trước
> khi có ma trận thì không sinh được Kiểm tra nhanh đúng mức độ.

### 5.1 Nạp sách vào kho SGK

**Cách A — qua CMS (khuyến nghị, có tiến độ + soát chất lượng):**

CMS → **Nạp sách bằng AI** → kéo ảnh trang vào → soát dải ô trang → **Đọc thử 3
trang** → **Nạp cả tập**.

Ba chốt đáng dùng đúng mục đích:
- **Dải ô trang** chỉ ra ngay chỗ khuyết trang. Số trang lấy từ *tên tệp*, nạp
  sai thứ tự là mọi dẫn nguồn "[tr.9]" trỏ sai bài.
- **Đọc thử 3 trang** = 3 lượt gọi AI thay vì 149, để biết OCR có đọc nổi công
  thức của quyển này không. Nhìn markdown: `2³·5` thành `235` là phải đổi nguồn ảnh.
- **Nạp cả tập** chạy nền qua worker, đóng tab vẫn chạy, tạm dừng/nạp tiếp được
  (cache OCR giữ trong `data_processed` nên nạp tiếp gần như miễn phí).

Cần `worker` sống: `./deploy.sh ps` phải thấy `worker` Up. Nếu không, job nằm ở
trạng thái "chờ" và CMS báo *"chưa đẩy được vào hàng đợi"*.

**Cách B — CLI (khi ảnh đã có sẵn trên server):**

```bash
# thử vài trang trước cho chắc
./deploy.sh ingest --tap 1 --sach cung_kham_pha_tap_1 --pages 5-8
# rồi cả tập
./deploy.sh ingest --tap 1 --sach cung_kham_pha_tap_1
```

### 5.2 Nạp ma trận đặc tả

```bash
./deploy.sh seed-matrix --mon "Toán" --khoi "Lớp 6"
```

Hoặc CMS → **Ma trận đặc tả** → tải lên `.docx`/`.md` (thay toàn bộ ma trận của
môn/khối/học kỳ đó). Sau khi nạp, xem banner **"đơn vị vừa được tạo"** — tên lấy
thô từ Word nên phải rà, và nếu có bản trùng thì quay lại §4.1.

### 5.3 Soạn nội dung bài học

> ⚠️ **`seed` trần KHÔNG ra đủ 7 mục.** Luồng chính chỉ sinh **Kiến thức trọng
> tâm** + **Ví dụ** (2/7). Phải thêm cờ mới đủ:
>
> | Mục (bố cục 7 phần) | Cờ nào sinh ra |
> |---|---|
> | Khởi động | `--phan` |
> | Hoạt động | `--phan` |
> | Kiến thức trọng tâm | *(mặc định)* |
> | Minh hoạ | `--media` |
> | Ví dụ | *(mặc định)* |
> | Luyện tập – Vận dụng | `--phan` |
> | Bài tập | `--phan` |
>
> Chạy thiếu cờ thì bài học sinh mở ra **trống 5 mục**. Đo trên dữ liệu hiện tại
> (20 bài đã soạn bằng script cũ): Kiến thức 16/20, Ví dụ 16/20, còn Khởi động /
> Hoạt động / Luyện tập / Bài tập / Minh hoạ đều **1/20** — cái 1 đó là bài soạn tay.

`seed` **idempotent theo từng mảnh**, không phải theo cả bài: `--phan` bổ sung
được 4 phần thiếu trên bài **đã có** Kiến thức/Ví dụ mà **không** gọi lại tầng
mạnh cho chữ đã có, `--media` bổ sung minh hoạ chỉ bằng một lời gọi tầng rẻ.
Chạy lại nhiều lần chỉ bù phần còn thiếu.

> Đây là hành vi đã sửa ngày 26/08. Trước đó cửa lọc loại **mọi** đơn vị đã có
> bản ghi nội dung, nên `--phan` trên bộ nội dung đã soạn in ra *"sẽ soạn 0 đơn
> vị"* rồi thoát — im lặng không làm gì. Nếu server đang chạy code cũ thì
> `git pull` trước.

```bash
# Đủ 7 mục (khuyến nghị) — bổ sung bài/phần còn thiếu, không đụng cái đã có
./deploy.sh seed --mon "Toán" --khoi "Lớp 6" --phan --media

# Chỉ chữ, chưa cần ảnh
./deploy.sh seed --phan

# SOẠN LẠI tất cả kể cả phần đã có — xem cảnh báo dưới
./deploy.sh seed --force --phan --media
```

**`--force` ghi đè chữ và XOÁ phần chuyên gia đã chỉnh tay.** Nó *giữ lại* minh
hoạ đã có và trạng thái xuất bản (hai thứ tốn công/tốn tiền nhất). Chỉ dùng khi
thật sự cần soạn lại cả bộ.

#### Soạn lại TỪ ĐẦU thì phải chia lô

`--force` làm lại **mọi** bài và `topic_content` không có cột thời gian, nên nó
không tự biết đã tới đâu. Hạn mức 50 request/ngày ÷ 9 request/bài ≈ 5 bài/ngày —
chạy `--force` nhiều ngày thì ngày nào cũng bắt đầu từ bài 1 và **không bao giờ
xong**. Dùng `--bo-qua` / `--gioi-han`:

| Ngày | Lệnh |
|---|---|
| 1 | `./deploy.sh seed --force --phan --media --gioi-han 5` |
| 2 | `./deploy.sh seed --force --phan --media --bo-qua 5 --gioi-han 5` |
| 3 | `./deploy.sh seed --force --phan --media --bo-qua 10 --gioi-han 5` |
| 4 | `./deploy.sh seed --force --phan --media --bo-qua 15 --gioi-han 6` |

Thứ tự lô theo `order_index` nên ổn định giữa các ngày.

**Không dùng `--force` thì KHÔNG cần chia lô** — lượt sau tự bỏ qua phần đã có,
cứ chạy lại cùng một lệnh mỗi ngày là tiến lên.

#### Ước lượng chi phí trước khi chạy

Mỗi đơn vị: **2 request** nền (soạn bài + quiz), **+4** với `--phan` (mỗi phần một
lần gọi riêng — bốn phần có yêu cầu rất khác nhau, nhồi vào một prompt là ra bốn
khối lai lai giống nhau), **+3** với `--media` (1 đề xuất + 2 ảnh).

Toán 6 hiện có **21 đơn vị**, hạn mức **50 request/ngày**:

| Lệnh | Request/đơn vị | Tổng 21 đơn vị | Kết luận |
|---|---|---|---|
| `seed` | 2 | **42** | vừa đủ một ngày · **chỉ 2/7 mục** |
| `seed --phan` | 6 | **126** | chia ~3 ngày · 6/7 mục |
| `seed --phan --media` | 9 | **189** | chia ~4 ngày · đủ 7/7 |

Vượt hạn mức thì gateway trả 429; script **bỏ qua rồi tiếp tục**, nên chạy lại
hôm sau bù đúng phần còn thiếu. Cách chia gọn nhất — mỗi ngày một lệnh, lệnh sau
chỉ làm phần lệnh trước chưa kịp:

```bash
# ngày 1: chữ nền (Kiến thức + Ví dụ + quiz)
./deploy.sh seed
# ngày 2–3: 4 phần còn lại
./deploy.sh seed --phan
# ngày 4: ảnh minh hoạ + đặt hàng video
./deploy.sh seed --phan --media
```

#### Theo dõi còn thiếu mục nào

```bash
./deploy.sh phan-status            # bảng đầy đủ 21 đơn vị × 7 mục
./deploy.sh phan-status --thieu    # chỉ bài chưa đủ
```

```
Toán · Lớp 6 — 21 đơn vị · đủ 7 mục: 0 · đã xuất bản: 3
     1 2 3 4 5 6 7  n/7  tt   đơn vị
  1480 · · █ · █ · ·  2/7  XB  Các phép tính với số tự nhiên. Luỹ thừa…
```

`tt`: `XB` đã xuất bản · `cd` chờ duyệt · `np` nháp · `--` chưa có bản ghi.

Chạy lại sau **mỗi** lượt seed: hạn mức 50 request/ngày làm một lượt không bao
giờ xong cả bộ, nên phải đo phần còn lại chứ không chạy mù. Hoặc xem cột
"Hoàn thành n/7 phần" ở CMS → Chương trình & nội dung.

#### Soạn xong vẫn phải XUẤT BẢN

`seed` lưu ở trạng thái `draft`. Học sinh **chỉ đọc được bản `published`**
([lessons.py:160](../app/api/lessons.py#L160)) — soạn đủ 7/7 mà còn nháp thì bài
vẫn hiện "đang được biên soạn". Hai cách:

- **Duyệt từng bài** trong CMS (khuyến nghị: nội dung AI cần người rà).
- Chạy kèm `--publish` để xuất bản luôn — chỉ nên dùng khi đã tin quy trình.

`phan-status` in sẵn cảnh báo khi có bài đủ mục mà chưa xuất bản.

### 5.4 Video ngắn

`--media` chỉ **đặt hàng** job video, không dựng. Cần worker riêng vì image có
ffmpeg/node/katex:

```bash
./deploy.sh video-up        # bật worker queue 'video'
./deploy.sh pregen-video    # hoặc dựng sẵn đồng bộ, không cần worker sống
```

#### Nếu thấy "không đẩy được job video N vào hàng đợi"

```
không đẩy được job video 49 vào hàng đợi (OperationalError):
Error 111 connecting to redis:6380. Connection refused.
```

**Sai `REDIS_URL`, không phải lỗi code.** Trong mạng compose Redis nghe cổng
**6379**; `6380` là cổng HOST map ra (`"6380:6379"`). Ghép tên service `redis` với
cổng host `6380` là không tồn tại.

Nguyên nhân hay gặp: copy `REDIS_URL` từ `.env.example` (giá trị
`redis://localhost:6380/0`, đúng cho venv trên host) sang `.env` của server rồi
đổi `localhost` → `redis` mà **để nguyên 6380**.

Sửa: **xoá hẳn dòng `REDIS_URL` trong `.env`** của server — compose đã có mặc định
`redis://redis:6379/0`. Rồi:

```bash
./deploy.sh up -d api worker           # nạp lại env
./deploy.sh exec api python -c "import redis,os;
r=redis.from_url(os.environ['REDIS_URL']);print('redis OK' if r.ping() else 'FAIL')"
./deploy.sh requeue-video               # đẩy lại job đã tạo nhưng chưa vào hàng đợi
```

**Không mất gì khác:** lỗi này chỉ cảnh báo rồi đi tiếp (cố ý — broker chết không
được phép làm vỡ cả lượt soạn bài). Chữ và **ảnh minh hoạ đã sinh xong bình
thường** vì chúng không cần Redis. Job video nằm lại trạng thái `QUEUED` nhưng
không có message nào trong hàng đợi, nên `requeue-video` là bước bắt buộc — worker
bật lại cũng không tự thấy chúng.

> ⚠️ Còn một hậu quả **âm thầm**: `REDIS_URL` sai làm **hạn mức hỏi/ngày của trợ lý
> tự tắt**. Chỗ đếm lượt fail-open khi Redis lỗi (`app/api/tutor.py:_enforce_limit`)
> — cố ý để Redis chết không chặn học sinh học, nhưng nghĩa là học sinh hỏi không
> giới hạn mà không có cảnh báo nào. Sửa `REDIS_URL` xong nên kiểm lại bằng lệnh
> ping ở trên.

### 5.5 Hình cho từng ví dụ

Ví dụ hình học (*"Trong các hình sau…"*) cần hình riêng, không nằm trong luồng
hàng loạt vì mỗi ảnh là một lần gọi model:

CMS → **Chương trình & nội dung** → Sửa bài → phần **Ví dụ**. Ví dụ nào nhắc tới
hình mà chưa có hình sẽ hiện cảnh báo vàng + nút **"✨ Vẽ bằng AI"** / **"⬆️ Tải
hình"**. Mô tả hình nên viết bằng tiếng Anh, nền phẳng kiểu SGK, ghi rõ không có
chữ trong hình (nếu đề đặt tên điểm M, N, P thì phải tả rõ từng chữ, font serif).

---

## 6. Kiểm tra sau deploy

```bash
./deploy.sh health                       # {"status":"ok"}
./deploy.sh logs api | tail -50          # không có traceback
```

Trên trình duyệt:

| Kiểm | Ở đâu | Đúng thì thấy |
|---|---|---|
| Học sinh vào được | app học, tài khoản `hoc_sinh` | mục lục + bài học |
| Vòng tiến độ theo bài | mở bài ở mạch khác | nhãn mạch **đổi theo bài đang mở** |
| Ôn tập chương | sidebar, cuối mỗi mạch | mở được, bấm "Bắt đầu ôn tập" ra đề |
| Trợ lý kèm hình | hỏi "Hình nào có trục đối xứng?" | có ảnh dưới câu trả lời |
| CMS khớp phía học sinh | CMS → Người dùng → Kết quả | "đơn vị đạt" trùng số học sinh thấy |
| Chuyên gia vào CMS | tài khoản `chuyen_gia` | vào được, chỉ thấy mục Nội dung |

Ôn tập cần bài trong mạch **đã có Kiểm tra nhanh** (đề gom từ đó). Chưa có thì
trang nói rõ "mới gom được N/12 câu vì M bài chưa có bài kiểm tra nhanh".

---

## 7. Rollback

```bash
git log --oneline -5
git checkout <commit-cũ>
./deploy.sh up
```

Migration **không** tự lùi theo code. Bản cũ chạy trên schema mới vẫn được (cột
`nguon` và bảng `book_jobs` chỉ bị bỏ qua). Chỉ `downgrade` khi thật cần, và nhớ
là mất nhãn `nguon`.
