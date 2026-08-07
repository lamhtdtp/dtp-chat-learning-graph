"""Nạp ma trận đặc tả (yêu cầu cần đạt + mức độ) và ÁNH XẠ vào catalog SẠCH.

    python -m app.seed_matrix

Khác `matrix_loader.load_matrix` (tạo curriculum_topics từ tên trong .docx —
sẽ làm bẩn lại catalog): script này KHÔNG tạo topic mới, mà khớp từng cell của
ma trận vào 21 đơn vị sạch đã có, theo (mạch + từ khoá đơn vị). Nhờ vậy quiz
(app/lessons/quiz) bám được "yêu cầu cần đạt".

Tên đơn vị trong docx bị cắt cụt / thiếu dấu cách nên khớp bằng cách đếm số từ
khoá của đơn vị SẠCH xuất hiện (dạng substring) trong tên docx, trong cùng mạch.
Cell không khớp -> BÁO ra, không âm thầm bỏ.
"""
import argparse
import asyncio
import re
import unicodedata
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Blueprint, BlueprintCell, CurriculumTopic, Grade, Subject
from app.db.session import async_session_factory
from app.ingestion.matrix_parser import parse_matrix

MON, KHOI = "Toán", "Lớp 6"
DOCX = {"hk1": "data/matrix/TOAN_6_HK1.docx", "hk2": "data/matrix/TOAN_6_HK2.docx"}
_STOP = {"các", "và", "của", "trong", "cho", "một", "với", "tập", "hợp", "the"}


def _nfc(s: str) -> str:
    # Docx có ô dùng Unicode tổ hợp (NFD) — chuẩn hoá NFC để khớp với DB (NFC).
    return unicodedata.normalize("NFC", s or "").lower()


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", _nfc(s))


def _tokens(s: str) -> list[str]:
    """Từ khoá có nghĩa (>=3 ký tự, bỏ stopword) để khớp."""
    return [w for w in re.findall(r"\w+", _nfc(s), re.UNICODE) if len(w) >= 3 and w not in _STOP]


def _score(a: str, b: str) -> float:
    """Điểm khớp ĐỐI XỨNG, chịu cắt cụt/thiếu dấu cách: số từ khoá xuất hiện
    (dạng substring) trong CẢ HAI tên, chia cho tập từ NGẮN hơn. Tên docx bị cắt
    (ít từ hơn) mà nằm trọn trong tên sạch vẫn đạt điểm cao."""
    sa, sb = set(_tokens(a)), set(_tokens(b))
    if not sa or not sb:
        return 0.0
    na, nb = _nospace(a), _nospace(b)
    common = sum(1 for t in (sa | sb) if t in na and t in nb)
    return common / min(len(sa), len(sb))


async def _get_or_create(session: AsyncSession, model, **keys):
    obj = await session.scalar(select(model).filter_by(**keys))
    if obj is None:
        obj = model(**keys)
        session.add(obj)
        await session.flush()
    return obj


async def seed(*, mon: str, khoi: str) -> None:
    async with async_session_factory() as session:
        subject = await session.scalar(select(Subject).filter_by(name=mon))
        grade = await session.scalar(select(Grade).filter_by(name=khoi))
        if subject is None or grade is None:
            print(f"✗ Chưa có môn {mon!r}/khối {khoi!r}. Chạy `python -m app.seed_curriculum` trước.")
            return

        topics = list(await session.scalars(
            select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
        ))

        def match_topic(rec) -> tuple[CurriculumTopic | None, float]:
            """Khớp toàn cục: điểm = 0.7*(đơn vị) + 0.3*(mạch). Bỏ cổng lọc mạch
            để chịu lỗi forward-fill (mạch bị điền sai) — tên đơn vị đủ phân biệt."""
            best, best_sc = None, 0.0
            for t in topics:
                sc = 0.7 * _score(rec.don_vi_kien_thuc, t.don_vi_kien_thuc) + 0.3 * _score(rec.mach_noi_dung, t.mach_noi_dung)
                if sc > best_sc:
                    best, best_sc = t, sc
            return best, best_sc

        # Xoá ma trận cũ (nếu có) cho (môn, khối) — idempotent.
        old_bps = list(await session.scalars(
            select(Blueprint).filter_by(subject_id=subject.id, grade_id=grade.id)
        ))
        for bp in old_bps:
            await session.execute(delete(BlueprintCell).where(BlueprintCell.blueprint_id == bp.id))
        for bp in old_bps:
            await session.delete(bp)
        await session.flush()

        total = matched = 0
        unmatched: list[str] = []
        for hoc_ky, path in DOCX.items():
            p = Path(path)
            if not p.exists():
                print(f"• Bỏ qua {hoc_ky}: không có {path}")
                continue
            rows = parse_matrix(p)
            bp = Blueprint(subject_id=subject.id, grade_id=grade.id, semester=hoc_ky)
            session.add(bp)
            await session.flush()
            for rec in rows:
                total += 1
                topic, sc = match_topic(rec)
                if topic is None or sc < 0.45:
                    unmatched.append(f"[{hoc_ky}] {rec.mach_noi_dung[:20]} :: {rec.don_vi_kien_thuc[:45]} (sc={sc:.2f})")
                    continue
                session.add(BlueprintCell(
                    blueprint_id=bp.id, muc_do=rec.muc_do, nang_luc=rec.nang_luc_thanh_phan,
                    yeu_cau_can_dat=rec.yeu_cau_can_dat, topic_id=topic.id,
                    dang_thuc=rec.dang_thuc, ti_le=rec.ti_le, nhom_ti_le=rec.nhom_ti_le,
                ))
                matched += 1
        await session.commit()

        # Số đơn vị sạch đã có ≥1 yêu cầu cần đạt.
        covered = len(set(
            c.topic_id for c in await session.scalars(select(BlueprintCell))
        ))
        print(f"✓ Khớp {matched}/{total} cell vào catalog sạch · {covered}/{len(topics)} đơn vị có yêu cầu cần đạt.")
        if unmatched:
            print(f"⚠️  {len(unmatched)} cell không khớp (đơn vị đó quiz sẽ dùng fallback):")
            for u in unmatched:
                print("   -", u)


def main() -> None:
    ap = argparse.ArgumentParser(description="Nạp ma trận đặc tả, map vào catalog sạch")
    ap.add_argument("--mon", default=MON)
    ap.add_argument("--khoi", default=KHOI)
    args = ap.parse_args()
    asyncio.run(seed(mon=args.mon, khoi=args.khoi))


if __name__ == "__main__":
    main()
