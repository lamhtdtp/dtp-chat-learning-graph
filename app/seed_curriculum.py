"""Reseed mục lục Toán 6 theo danh mục ĐÃ LÀM SẠCH của mockup
(ui-design/mockups/student-app.html) — 21 đơn vị / 10 mạch, HK1 + HK2.

    python -m app.seed_curriculum

Catalog cũ (curriculum_topics) do matrix_loader sinh từ .docx bị trùng lặp / sai
chính tả nên thay bằng danh mục sạch này. Vì BlueprintCell (ma trận),
TopicContent, StudentProgress trỏ FK vào catalog cũ, script XOÁ chúng trước
(dữ liệu dev, tái tạo được: nạp lại ma trận + `python -m app.seed_lessons`).
Idempotent: chạy lại luôn cho đúng 21 đơn vị.
"""
import asyncio

from sqlalchemy import delete, select

from app.db.models import (
    Blueprint, BlueprintCell, CurriculumTopic, Grade, StudentProgress, Subject, TopicContent,
)
from app.db.session import async_session_factory

MON, KHOI = "Toán", "Lớp 6"

# Học kỳ 1 gồm 4 mạch đầu (theo mockup); các mạch còn lại thuộc HK2.
HK1_MACH = {"Số tự nhiên", "Số nguyên", "Các hình phẳng trong thực tiễn", "Tính đối xứng của hình phẳng"}


def _hoc_ky(mach: str) -> str:
    return "hk1" if mach in HK1_MACH else "hk2"

# (mạch, emoji, [đơn vị kiến thức]) — thứ tự = order_index. Khớp GROUPS trong mockup.
GROUPS: list[tuple[str, str, list[str]]] = [
    ("Số tự nhiên", "🔢", [
        "Số tự nhiên và tập hợp các số tự nhiên. Thứ tự trong tập hợp các số tự nhiên",
        "Các phép tính với số tự nhiên. Luỹ thừa với số mũ tự nhiên",
        "Tính chia hết. Số nguyên tố. Ước chung và bội chung",
    ]),
    ("Số nguyên", "➖", [
        "Số nguyên âm và tập hợp các số nguyên. Thứ tự trong tập hợp các số nguyên",
        "Các phép tính với số nguyên. Tính chia hết trong tập hợp các số nguyên",
    ]),
    ("Các hình phẳng trong thực tiễn", "🔺", [
        "Tam giác đều, hình vuông, lục giác đều",
        "Hình chữ nhật, hình thoi, hình bình hành, hình thang cân",
    ]),
    ("Tính đối xứng của hình phẳng", "🔷", [
        "Hình có trục đối xứng",
        "Hình có tâm đối xứng",
        "Vai trò của đối xứng trong thế giới tự nhiên",
    ]),
    ("Phân số", "➗", [
        "Phân số. Tính chất cơ bản của phân số. So sánh phân số",
        "Các phép tính với phân số",
    ]),
    ("Số thập phân", "💯", [
        "Số thập phân và các phép tính với số thập phân. Tỉ số và tỉ số phần trăm",
    ]),
    ("Các hình hình học cơ bản", "📐", [
        "Điểm, đường thẳng, tia",
        "Đoạn thẳng. Độ dài đoạn thẳng",
        "Góc. Các góc đặc biệt. Số đo góc",
    ]),
    ("Thu thập và tổ chức dữ liệu", "📊", [
        "Thu thập, phân loại, biểu diễn dữ liệu theo các tiêu chí cho trước",
        "Mô tả và biểu diễn dữ liệu trên các bảng, biểu đồ",
    ]),
    ("Phân tích và xử lí dữ liệu", "📈", [
        "Giải quyết vấn đề đơn giản từ số liệu và biểu đồ thống kê đã có",
    ]),
    ("Một số yếu tố xác suất", "🎲", [
        "Làm quen với một số mô hình xác suất đơn giản",
        "Mô tả xác suất (thực nghiệm) khả năng xảy ra của một sự kiện",
    ]),
]


async def _get_or_create(session, model, **keys):
    obj = await session.scalar(select(model).filter_by(**keys))
    if obj is None:
        obj = model(**keys)
        session.add(obj)
        await session.flush()
    return obj


async def reseed() -> None:
    async with async_session_factory() as session:
        subject = await _get_or_create(session, Subject, name=MON)
        grade = await _get_or_create(session, Grade, name=KHOI)

        old_ids = list(await session.scalars(
            select(CurriculumTopic.id).filter_by(subject_id=subject.id, grade_id=grade.id)
        ))
        if old_ids:
            # Xoá dependents (FK) trước — không có ON DELETE CASCADE.
            await session.execute(delete(StudentProgress).where(StudentProgress.topic_id.in_(old_ids)))
            await session.execute(delete(TopicContent).where(TopicContent.topic_id.in_(old_ids)))
            await session.execute(delete(BlueprintCell).where(BlueprintCell.topic_id.in_(old_ids)))
            await session.execute(
                delete(Blueprint).where(Blueprint.subject_id == subject.id, Blueprint.grade_id == grade.id)
            )
            await session.execute(delete(CurriculumTopic).where(CurriculumTopic.id.in_(old_ids)))
            await session.flush()

        idx = 0
        for mach, _emoji, units in GROUPS:
            for dv in units:
                session.add(CurriculumTopic(
                    subject_id=subject.id, grade_id=grade.id,
                    mach_noi_dung=mach, don_vi_kien_thuc=dv, order_index=idx,
                    hoc_ky=_hoc_ky(mach),
                ))
                idx += 1
        await session.commit()
        print(f"✓ Reseed {idx} đơn vị / {len(GROUPS)} mạch cho {MON} {KHOI} (đã xoá {len(old_ids)} đơn vị cũ + ma trận/nội dung/tiến độ liên quan).")


if __name__ == "__main__":
    asyncio.run(reseed())
