"""Chọn câu cho "Luyện thêm từ kho đề" (US-25) — hàm thuần, không đụng DB hay mạng.

Đầu vào là phần tử `items` của `GET content /pool` của testbank. Luật chọn (cùng
luật testbank khuyến nghị cho một đề: "một câu mỗi họ, cả nhóm hoặc không câu nào"):

* chỉ lấy câu có `ar_id` thuộc YCCĐ của bài;
* mỗi `family_qid` tối đa một câu — bản gốc và bản nhân bản gần như giống hệt,
  làm cả hai là làm lặp;
* câu cùng `group_id` dùng chung một dữ kiện: lấy TRỌN nhóm hoặc không lấy, đứng
  liền nhau (dữ kiện chung chỉ hiện một lần trước câu đầu), cả nhóm tính vào giới hạn.
  Nhóm lớn hơn phần còn lại thì bỏ cả nhóm — cắt dở là đưa ra đề thiếu dữ kiện;
* trải đều YCCĐ (Q3): vòng qua từng YCCĐ lấy một câu rồi mới sang vòng hai. Bài có
  nhiều YCCĐ hơn `toi_da` thì thứ tự YCCĐ phụ thuộc `seed`, các lượt sau phủ dần;
* không ép tỉ lệ mức độ (Q4): ép là báo thiếu oan khi kho mỏng.

Thứ tự đề = thứ tự của kho (`items`), không phải thứ tự bốc: bốc ngẫu nhiên theo
vòng YCCĐ rồi đưa nguyên thứ tự đó cho học sinh thì câu số 1 của mỗi lượt là một
YCCĐ bất kỳ và danh sách câu nhảy lung tung giữa các lượt.
"""
import random
from collections import defaultdict


def chon_cau(items: list[dict], ar_ids: set[str], *, toi_da: int = 4, seed: int = 0) -> list[str]:
    """Trả `qid` theo thứ tự đề. Cùng `seed` + cùng đầu vào -> cùng kết quả."""
    rng = random.Random(seed)
    vi_tri = {x["qid"]: i for i, x in enumerate(items)}
    hop_le = sorted((x for x in items if x.get("ar_id") in ar_ids), key=lambda x: x["qid"])

    # Mỗi "đơn vị chọn" là một câu rời hoặc cả một nhóm; gom theo YCCĐ (nhóm lấy
    # YCCĐ của câu đầu — nhóm thường cùng một YCCĐ).
    don_vi: dict[str, list[list[dict]]] = defaultdict(list)
    nhom: dict[str, list[dict]] = {}
    for x in hop_le:
        g = x.get("group_id")
        if g:
            nhom.setdefault(g, []).append(x)
        else:
            don_vi[x["ar_id"]].append([x])
    for g_items in nhom.values():
        don_vi[g_items[0]["ar_id"]].append(g_items)

    thu_tu_ar = sorted(don_vi)
    rng.shuffle(thu_tu_ar)
    for ar in thu_tu_ar:
        rng.shuffle(don_vi[ar])

    con_lai, da_dung_ho, chon = toi_da, set(), []
    while con_lai > 0:
        lay_duoc = False
        for ar in thu_tu_ar:
            ds = don_vi[ar]
            while ds and con_lai > 0:
                dv = ds.pop()
                ho = {x["family_qid"] for x in dv}
                # Không vừa chỗ còn lại thì bỏ hẳn: chỗ chỉ nhỏ dần nên sau này cũng không vừa.
                if len(dv) > con_lai or ho & da_dung_ho:
                    continue
                da_dung_ho |= ho
                chon.append(sorted(dv, key=lambda x: vi_tri[x["qid"]]))
                con_lai -= len(dv)
                lay_duoc = True
                break
        if not lay_duoc:
            break
    chon.sort(key=lambda dv: vi_tri[dv[0]["qid"]])
    return [x["qid"] for dv in chon for x in dv]
