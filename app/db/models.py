"""Schema Postgres — ma trận, taxonomy, users. KHÔNG chứa nội dung SGK (đó là
Qdrant, xem app/ingestion/matrix_parser.py và specs/full-system-spec.md mục 4).
"""

from datetime import date, datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint, text
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
    hoc_ky: Mapped[str | None] = mapped_column(default=None)  # "hk1" | "hk2" (đa học kỳ)


class TopicContent(Base):
    """Nội dung bài học có cấu trúc cho 1 đơn vị kiến thức (mô hình giáo trình số
    theo mockup). 1 topic ↔ tối đa 1 bản nội dung. Phần "kiểm tra nhanh" KHÔNG
    lưu ở đây — sinh tự động theo ma trận (app/exam). Media/ví dụ lưu JSON (text).
    minh_hoa_json giữ cả video AI (mặc định) lẫn media chuyên gia upload (ưu tiên)."""

    __tablename__ = "topic_content"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("curriculum_topics.id"), unique=True, index=True)
    khai_niem: Mapped[str] = mapped_column(Text, default="")           # phần ① (HTML)
    minh_hoa_json: Mapped[str] = mapped_column(Text, default="[]")     # phần ② [{type,url,caption,source}]
    vi_du_json: Mapped[str] = mapped_column(Text, default="[]")        # phần ③ [{de,giai}]
    # phần ④ "Kiểm tra nhanh": trắc nghiệm sinh TỰ ĐỘNG theo ma trận (P3) rồi
    # cache tại đây — [{q, o:[…], a:<index đúng>, lv, giai}]. Không nhập tay.
    quiz_json: Mapped[str] = mapped_column(Text, default="[]")
    # Lời nhắc CHỦ ĐỘNG của trợ lý ở các mốc trong bài (vd đọc xong khái niệm thì
    # hỏi lại một câu kiểm tra hiểu) — [{moc, hoi, dap:[…], giai}]. Sinh MỘT LẦN
    # lúc biên soạn rồi cache tại đây; nếu sinh online thì mỗi lần học sinh cuộn
    # qua là một lượt LLM, đốt sạch hạn mức ngày mà em ấy chưa hỏi câu nào.
    nhac_json: Mapped[str] = mapped_column(Text, default="[]")
    day_json: Mapped[str | None] = mapped_column(Text, default=None)   # hướng dẫn giảng dạy (GV)
    # Tư liệu THÔ chuyên gia dán vào để AI bám khi soạn (trích đoạn SGK, ghi chú
    # chuyên môn). Chỉ là đầu vào biên soạn — KHÔNG hiển thị cho học sinh.
    nguon: Mapped[str | None] = mapped_column(Text, default=None)
    # Nội dung này do AI soạn nháp (chưa có người rà). Cột riêng, CỐ Ý không suy
    # từ `nguon` nữa: cách cũ dò chuỗi con "AI" trong nguon nên trích đoạn SGK
    # viết hoa có chữ "HAI" cũng bị gắn nhãn AI oan.
    ai_soan: Mapped[bool] = mapped_column(default=False)
    trang_thai: Mapped[str] = mapped_column(default="draft")           # draft | published
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class StudentProgress(Base):
    """Tiến độ học sinh theo ĐƠN VỊ kiến thức (baseline P1). Refine theo từng
    yêu cầu cần đạt (blueprint_cells) ở P3. 1 (user, topic) → 1 trạng thái."""

    __tablename__ = "student_progress"
    __table_args__ = (UniqueConstraint("user_id", "topic_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("curriculum_topics.id"), index=True)
    trang_thai: Mapped[str] = mapped_column(default="dang")            # dat | dang | chua
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class QuizAttempt(Base):
    """MỘT lần học sinh nộp bài Kiểm tra nhanh — lưu để giáo viên xem lại.

    StudentProgress chỉ giữ trạng thái cuối (dat|dang) nên mất sạch quá trình:
    làm mấy lần, tiến bộ ra sao, đơn vị nào cả lớp cùng đuối. Bảng này ghi từng
    lần, KHÔNG khử trùng — làm lại là thêm dòng mới.

    CỐ Ý không lưu đáp án học sinh chọn: quiz sinh lại theo ma trận (topic_content
    .quiz_json bị ghi đè) nên chỉ số câu lưu hôm nay sẽ trỏ sai đề vào ngày mai —
    dữ liệu trông có vẻ chi tiết nhưng suy ra kết luận sai."""

    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("curriculum_topics.id"), index=True)
    diem: Mapped[int]                                    # số câu đúng
    tong: Mapped[int]                                    # tổng số câu của đề lúc làm
    dat: Mapped[bool]                                    # có đạt ngưỡng 70% không
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class StudentStats(Base):
    """Gamification học sinh: điểm XP, chuỗi ngày học liên tục (streak), điểm
    tuần. 1 user → 1 dòng. Cập nhật khi HS làm bài (nộp quiz / đánh dấu hoàn
    thành). `last_study`/`week_start` là NGÀY (date) để tính streak & reset tuần."""

    __tablename__ = "student_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    xp_total: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    streak_days: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    last_study: Mapped[date | None] = mapped_column(default=None)   # ngày học gần nhất
    week_start: Mapped[date | None] = mapped_column(default=None)   # thứ Hai của tuần đang đếm
    week_points: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


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
    # "hoc_sinh" | "giao_vien" -> app học; "chuyen_gia" | "admin" -> CMS.
    # Cột chuỗi tự do (không ENUM) nên thêm vai trò mới KHÔNG cần migration.
    role: Mapped[str]
    # Quản trị: khoá/mở tài khoản; hạn mức chat/ngày riêng (None = dùng mặc định).
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    daily_limit_override: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class VideoJob(Base):
    """Job sinh video AI ngắn cho 1 khái niệm (Epic-09). Vòng đời
    QUEUED→RENDERING→DONE|FAILED lưu ở Postgres để API/WebSocket truy vấn.

    Cache theo khái niệm: 1 concept_key + sgk_version -> DÙNG LẠI 1 video cho mọi
    học sinh. `concept_key` unique cùng `sgk_version` để không render trùng và
    đổi sách thì làm mới (xem 04-Video-Generation-Flow §4, §5)."""

    __tablename__ = "video_jobs"
    __table_args__ = (UniqueConstraint("concept_key", "sgk_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    concept_key: Mapped[str] = mapped_column(index=True)
    sgk_version: Mapped[str]
    status: Mapped[str] = mapped_column(default="QUEUED")  # QUEUED|RENDERING|DONE|FAILED
    video_url: Mapped[str | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    title: Mapped[str | None] = mapped_column(default=None)
    duration_sec: Mapped[float | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
