"""Port quiz.py: parse các dạng câu i-Test + resolve đáp án (không LLM, không DB)."""

from app.integrations.itest.quiz import (
    _expand,
    _keywords,
    _q_fill,
    _q_multi,
    _to_quiz_question,
)


def test_keywords_bo_dau_va_tu_dung():
    assert "phan" in _keywords("Phân số bằng nhau")
    assert "so" not in _keywords("số")          # < 3 ký tự -> bỏ
    assert _keywords("em muốn học") == []        # toàn từ dừng


def test_to_quiz_question_single_resolve_dap_an():
    row = {"question_type": "MC3", "answers": "4*5*6*7", "correct_answers": "5",
           "question_description": "2 + 3 = ?"}
    q = _to_quiz_question(row)
    assert q["type"] == "single"
    assert q["options"] == ["4", "5", "6", "7"]
    assert q["answer"] == 1                       # khớp nội dung "5"
    assert q["q"] == "2 + 3 = ?"


def test_to_quiz_question_khong_ro_dap_an_thi_minus1():
    row = {"question_type": "MC3", "answers": "a*b*c", "correct_answers": "",
           "question_description": "Chọn?"}
    assert _to_quiz_question(row)["answer"] == -1  # KHÔNG LLM -> -1 (hiện, không chấm)


def test_q_multi_nhieu_dap_an():
    row = {"question_type": "MR1", "answers": "x#y#z", "correct_answers": "x#z",
           "question_description": "Chọn nhiều?"}
    q = _q_multi(row)
    assert q["type"] == "multi"
    assert q["answers"] == [0, 2]


def test_q_fill_gop_1_cau_nhieu_o_va_thay_placeholder():
    # Nhiều chỗ trống -> 1 câu, nhiều ô; %s% -> [1] [2] theo thứ tự.
    row = {"question_type": "FB2", "question_text": "Sớm nhất là %s%, muộn nhất là %s%.",
           "correct_answers": "bánh xe#điện thoại"}
    qs = _q_fill(row)
    assert len(qs) == 1
    assert qs[0]["type"] == "fill" and qs[0]["blanks"] == ["bánh xe", "điện thoại"]
    assert qs[0]["q"] == "Sớm nhất là [1], muộn nhất là [2]."

    # Một chỗ trống -> [...]
    one = _q_fill({"question_type": "FB7", "question_text": "Kết quả là %s%.", "correct_answers": "8"})
    assert one[0]["blanks"] == ["8"] and one[0]["q"] == "Kết quả là [...]."


def test_expand_dinh_tuyen_theo_type():
    fb = _expand({"question_type": "FB7", "question_text": "Điền:", "correct_answers": "9"})
    assert fb[0]["type"] == "fill"
    tf = _expand({"question_type": "TF1", "answers": "Mệnh đề 1#Mệnh đề 2", "correct_answers": "T#F"})
    assert [x["type"] for x in tf] == ["single", "single"]   # TF làm phẳng về single
    assert tf[0]["answer"] == 0 and tf[1]["answer"] == 1


def test_expand_sl_nhieu_cho_trong_khong_lan_dau_thang():
    """SL: nhiều chỗ trống (ngăn '#'), mỗi chỗ chọn 1 (ngăn '*') — KHÔNG để '#'
    lẫn vào lựa chọn (bug '=#>')."""
    qs = _expand({
        "question_type": "SL1",
        "question_description": "Chọn dấu thích hợp",
        "answers": "$>$*$<$*$=$#$>$*$<$*$=$",
        "correct_answers": "$<$#$>$",
    })
    assert [q["type"] for q in qs] == ["single", "single"]
    assert all(q["options"] == ["$>$", "$<$", "$=$"] for q in qs)   # tách sạch, không '#'
    assert qs[0]["answer"] == 1 and qs[1]["answer"] == 0            # khớp đáp án từng chỗ
