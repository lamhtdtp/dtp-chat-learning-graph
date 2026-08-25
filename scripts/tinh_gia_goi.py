"""Mô hình chi phí/giá gói. Số ĐO THẬT lấy từ docs/cost-estimate.md."""
VND = 25_400                      # VND/USD

# ── Đơn giá tham chiếu (proxy Google, cần xác nhận VNGCloud) ──
GIA = {"cheap_in": 0.10, "cheap_out": 0.40, "strong_in": 1.25, "strong_out": 10.00}

# ── Token ĐO THẬT (cost-estimate.md §1) ──
QA_IN, QA_OUT = 1_200, 500        # 1 lượt hỏi trợ lý
OCR_IN, OCR_OUT = 1_241, 348      # 1 trang SGK
EMB_TOK = 150                     # 1 chunk

def usd(inp, out, tier):
    return inp * GIA[f"{tier}_in"]/1e6 + out * GIA[f"{tier}_out"]/1e6

qa = usd(QA_IN, QA_OUT, "cheap")
print(f"1 lượt hỏi trợ lý  = ${qa:.5f} = {qa*VND:>8.2f} đ")

# Lời gọi tầng MẠNH khi soạn bài: pro-preview là model reasoning, max_tokens=16384.
# Đo thật cho 'solve' là 1.500 in / 2.500 out; soạn bài dài hơn -> ước 2k/4k.
strong = usd(2_000, 4_000, "strong")
print(f"1 lời gọi tầng mạnh= ${strong:.5f} = {strong*VND:>8.2f} đ  (ước lượng)")

# ── Chi phí MỘT LẦN cho Toán 6 (21 đơn vị) ──
DV = 21
goi_manh = DV * 6                 # ingest + quiz + 4 phần
ocr = 294*usd(OCR_IN, OCR_OUT, "cheap")
emb = 880*EMB_TOK*GIA["cheap_in"]/1e6
mot_lan = goi_manh*strong + ocr + emb
print(f"\nMỘT LẦN — Toán 6: {goi_manh} lời gọi mạnh + OCR 294 trang + 880 chunk")
print(f"  = ${mot_lan:.2f} = {mot_lan*VND:,.0f} đ".replace(",", "."))

# ── Chi phí BIÊN mỗi học sinh/tháng (chỉ chat) ──
print("\nBIÊN mỗi học sinh/tháng (chỉ tầng rẻ, cache 24h giảm thêm):")
GOI = [("Miễn phí", 0, 5*26), ("Chuẩn", 99_000, 300), ("Gia đình (3 HS)", 149_000, 900)]
for ten, gia, luot in GOI:
    for hit in (0.0, 0.30):
        c = luot*qa*VND*(1-hit)
        bien = (gia-c)/gia*100 if gia else None
        b = f"{bien:5.1f}%" if bien is not None else "  —  "
        print(f"  {ten:16} {luot:4} lượt · cache {int(hit*100):2}% -> AI {c:7,.0f} đ"
              .replace(",", ".") + f" · biên gộp {b}")

# ── Hoàn vốn ──
print("\n" + "="*66)
# Chi phí cố định/tháng: hạ tầng + nhân sự chuyên gia rà nội dung.
# KHÔNG có số thật -> quét vài mức để chọn.
CO_DINH = [3_000_000, 6_000_000, 12_000_000, 25_000_000]
# Đầu tư một lần: AI soạn nội dung + công chuyên gia rà (21 bài × 1h × 150k)
DAU_TU = mot_lan*VND + 21*1*150_000
print(f"Đầu tư MỘT LẦN cho Toán 6 = {DAU_TU:,.0f} đ".replace(",", ".")
      + f"  (AI {mot_lan*VND:,.0f} đ + công rà 21 giờ)".replace(",", "."))

bien_chuan = 99_000 - 300*qa*VND*(1-0.30)      # cache 30%
print(f"\nLãi gộp mỗi HS gói Chuẩn = {bien_chuan:,.0f} đ/tháng".replace(",", "."))
print(f"{'Cố định/tháng':>16} | {'HS hoà vốn/tháng':>17} | {'HS để hoàn vốn 6 tháng':>23}")
print("-"*66)
for cd in CO_DINH:
    hv = cd/bien_chuan
    # hoàn cả đầu tư trong 6 tháng: 6*(n*bien - cd) >= DAU_TU
    n6 = (DAU_TU/6 + cd)/bien_chuan
    print(f"{cd:>13,.0f} đ | {hv:>15.1f} | {n6:>21.1f}".replace(",", "."))

# ── Độ bền của giá 99k khi đơn giá AI đắt hơn dự tính ──
print("\n" + "="*66)
print("Nếu đơn giá VNGCloud ĐẮT HƠN proxy (99.000đ, 300 lượt, cache 30%):")
for x in (1, 5, 10, 20, 50):
    c = 300*qa*VND*0.7*x
    print(f"  ×{x:<3} -> AI {c:9,.0f} đ/HS/tháng · biên gộp {(99_000-c)/99_000*100:5.1f}%"
          .replace(",", "."))

# ── Rủi ro: nếu một luồng HS chạm tầng mạnh ──
print("\nRỦI RO — nếu có tính năng cho HS chạm tầng mạnh (pro-preview):")
c = 300*strong*VND
print(f"  300 lượt/tháng ở tầng mạnh = {c:,.0f} đ/HS -> LỖ {c-99_000:,.0f} đ".replace(",", "."))
print(f"  (đắt hơn tầng rẻ {strong/qa:.0f} lần)")
