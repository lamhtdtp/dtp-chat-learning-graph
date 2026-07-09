"""Schema Postgres — ma trận, taxonomy, users. KHÔNG chứa nội dung SGK (đó là
Qdrant, xem app/ingestion/matrix_parser.py và specs/full-system-spec.md mục 4).
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class Book(Base):
    """Mọi dòng dữ liệu mang khóa (subject, grade, book) ngay từ đầu — thêm
    sách mới là thêm dữ liệu, không migrate schema (xem full-system-spec.md
    mục 5)."""

    __tablename__ = "books"
    __table_args__ = (UniqueConstraint("subject_id", "grade_id", "source_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"))
    semester: Mapped[str | None]
    source_ref: Mapped[str]  # VD "cung_kham_pha_tap_1" — khớp payload.sach trong Qdrant


class CurriculumTopic(Base):
    """Cầu nối SGK (Qdrant, qua topic_id trong payload) ↔ ma trận
    (blueprint_cells.topic_id) — xem full-system-spec.md mục 3."""

    __tablename__ = "curriculum_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"))
    mach_noi_dung: Mapped[str]
    don_vi_kien_thuc: Mapped[str]
    order_index: Mapped[int]


class Blueprint(Base):
    __tablename__ = "blueprints"
    __table_args__ = (UniqueConstraint("subject_id", "grade_id", "semester"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"))
    semester: Mapped[str]


class BlueprintCell(Base):
    """1 dòng = 1 "yêu cầu cần đạt" đã parse từ ma trận (xem
    app/ingestion/matrix_parser.MatrixRow). `ti_le` giữ nguyên giá trị gốc của
    NHÓM (có thể lặp lại giữa nhiều dòng cùng nhóm — xem `nhom_ti_le` ở
    MatrixRow); `so_cau` để NULL tới khi build_blueprint tính xong, không
    tính sẵn ở bước parse."""

    __tablename__ = "blueprint_cells"

    id: Mapped[int] = mapped_column(primary_key=True)
    blueprint_id: Mapped[int] = mapped_column(ForeignKey("blueprints.id"))
    muc_do: Mapped[str]
    nang_luc: Mapped[str]
    yeu_cau_can_dat: Mapped[str]
    topic_id: Mapped[int] = mapped_column(ForeignKey("curriculum_topics.id"))
    dang_thuc: Mapped[str]
    ti_le: Mapped[float]
    # Số nhóm tỉ lệ (từ MatrixRow.nhom_ti_le): nhiều cell cùng chia sẻ 1 mức
    # tỉ lệ chung. BẮT BUỘC lưu để cộng tổng tỉ lệ đúng 1 lần/nhóm — thiếu nó
    # thì không phân biệt được cell nào cùng nhóm và tổng bị nhân lên (eval
    # khớp ma trận đã bắt lỗi này: cộng ra 200% thay vì 100%).
    nhom_ti_le: Mapped[int]
    so_cau: Mapped[int | None] = mapped_column(default=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    password_hash: Mapped[str]
    name: Mapped[str]
    role: Mapped[str]  # "hoc_sinh" | "giao_vien"
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ChatSession(Base):
    """1 phiên hội thoại của 1 user. Lịch sử tin nhắn (bảng messages) lưu ở
    Postgres để dựng sidebar/xem lại — TÁCH khỏi checkpointer Redis của
    LangGraph (Redis giữ state để resume graph, không tiện query theo user)."""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(default="Cuộc trò chuyện")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_active: Mapped[datetime] = mapped_column(server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str]  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
