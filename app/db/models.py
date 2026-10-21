"""Schema Postgres — ma trận, taxonomy, users. KHÔNG chứa nội dung SGK (đó là
Qdrant, xem app/ingestion/matrix_parser.py và specs/full-system-spec.md mục 4).
"""

from datetime import date, datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, text
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
    # Đơn vị này do LẦN NẠP MA TRẬN tự tạo, không phải chuyên gia thêm vào danh
    # mục. Cần đánh dấu để §2.5 cảnh báo được: tên lấy nguyên từ .docx nên có thể
    # trùng lặp/sai chính tả so với đơn vị đã có, phải người rà lại.
    tu_ma_tran: Mapped[bool] = mapped_column(default=False)


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
    # ── 4 phần nội dung mới (REQ §1.1). Ba cột cũ (khai_niem/minh_hoa/vi_du) GIỮ
    # NGUYÊN tên vì tutor._doan_bai, grounding, quiz._grounding_text và nhac đang
    # đọc chúng — đổi tên là vỡ cả bốn chỗ.
    khoi_dong: Mapped[str] = mapped_column(Text, default="")           # phần ① (HTML)
    hoat_dong: Mapped[str] = mapped_column(Text, default="")           # phần ②
    luyen_tap: Mapped[str] = mapped_column(Text, default="")           # phần ⑥
    bai_tap: Mapped[str] = mapped_column(Text, default="")             # phần ⑦
    # Thứ tự + ẩn/hiện 7 phần: [{"id": "...", "an": false}]. RỖNG = thứ tự chuẩn,
    # không phần nào ẩn -> dữ liệu cũ mở bình thường, không cần backfill.
    bo_cuc_json: Mapped[str] = mapped_column(Text, default="[]")
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

    Bảng này giữ TỔNG KẾT một lần nộp. Chi tiết từng câu nằm ở
    `QuizAttemptItem` — xem docstring ở đó để biết vì sao mãi mới thêm được."""

    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    #: NULL CHỈ với `nguon="cuoi_ky"`: đề cuối kỳ phủ cả học kỳ, không thuộc bài
    #: nào. Mọi truy vấn `NOT IN (select topic_id …)` phải lọc NULL ra — một dòng
    #: NULL trong NOT IN làm cả điều kiện thành UNKNOWN và trả về rỗng.
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("curriculum_topics.id"), index=True)
    diem: Mapped[int]                                    # số câu đúng
    tong: Mapped[int]                                    # tổng số câu của đề lúc làm
    dat: Mapped[bool]                                    # có đạt ngưỡng 70% không
    # nhanh = Kiểm tra nhanh của chính đơn vị · on_tap = một mảnh của đề ôn tập
    # cả mạch · cuoi_ky = đề cuối kỳ rút từ DTP Testbank. KHÔNG có cột này thì
    # CMS hiện một lần nộp đề ôn tập 8 câu thành nhiều dòng "1/4" trông y như học
    # sinh đã làm bài kiểm tra của từng bài.
    nguon: Mapped[str] = mapped_column(default="nhanh", index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class QuizAttemptItem(Base):
    """Chi tiết TỪNG CÂU của một lần nộp — nền cho "gợi ý theo yêu cầu cần đạt".

    Trước đây `QuizAttempt` CỐ Ý không lưu học sinh chọn gì, và lý do ghi lại khi
    ấy vẫn đúng: quiz sinh lại theo ma trận (`topic_content.quiz_json` bị ghi đè)
    nên **chỉ số câu** lưu hôm nay sẽ trỏ sai đề vào ngày mai. Dữ liệu trông chi
    tiết nhưng suy ra kết luận sai.

    Bảng này lưu được vì đã có khoá BỀN để thay chỗ chỉ số câu:

    * `ycd_key` — nguyên văn yêu cầu cần đạt đã chuẩn hoá (`app/lessons/ycd_key.py`).
      Đây là khoá chính của mọi thống kê. KHÔNG dùng khoá ngoại tới
      `blueprint_cells.id`: nạp lại ma trận là xoá sạch cell cũ rồi chèn cell mới
      (`app/seed_matrix.py`, `app/seed_curriculum.py`), nên khoá ngoại sẽ chết
      đúng cái kiểu mà bảng này sinh ra để tránh.
    * `ar_id` — mã YCCĐ bên DTP Testbank (`AR26-TO06-CK1-001`). NULL với câu do
      mình tự sinh; câu rút từ testbank thì có. Hai hệ thống gặp nhau ở `ycd_key`,
      còn `ar_id` để đối chiếu ngược và gửi kết quả về kho.

    Không khử trùng: làm lại bài là thêm dòng mới, giống `QuizAttempt`.
    """

    __tablename__ = "quiz_attempt_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Xoá một lần nộp thì chi tiết đi theo — chi tiết không có nghĩa khi đứng rời.
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), index=True
    )
    #: Khoá bền để gom thống kê. Rỗng khi model không trả `ycd` — vẫn lưu dòng để
    #: tổng số câu khớp với `QuizAttempt.tong`, chỉ là không gom theo YCCĐ được.
    ycd_key: Mapped[str] = mapped_column(Text, default="", index=True)
    #: Nguyên văn chưa chuẩn hoá, để hiện lên màn hình cho học sinh/giáo viên đọc.
    ycd_text: Mapped[str] = mapped_column(Text, default="")
    ar_id: Mapped[str | None] = mapped_column(default=None, index=True)
    #: Mã câu bên testbank (`Q26-000006`). NULL với câu tự sinh.
    qid: Mapped[str | None] = mapped_column(default=None)
    #: Id phần nội dung trong bài học (`kien_thuc`, `minh_hoa`…) để sau khi nộp
    #: còn chỉ được học sinh về đúng đoạn cần đọc lại.
    phan: Mapped[str] = mapped_column(default="")
    muc_do: Mapped[str] = mapped_column(default="")      # de | trung_binh | kho (hoặc B|H|V)
    #: Học sinh chọn gì và đáp án đúng là gì — chuỗi nhãn ("B", "A,C"), KHÔNG
    #: phải chỉ số, vì chỉ số chỉ có nghĩa trong đúng đề đã sinh ra nó.
    chon: Mapped[str] = mapped_column(default="")
    dap_an: Mapped[str] = mapped_column(default="")
    dung: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DeGiao(Base):
    """Một đề do giáo viên giao bằng mã (US-26): rút từ testbank MỘT lần, lưu ở máy
    chủ, gắn với đúng một mã 6 ký tự.

    Có hai pha: `nhap` (bản xem trước, chưa có mã, huỷ được) rồi `mo` (đã cấp mã) và
    `dong` (giáo viên đóng, không mở lại). Học sinh vào bằng mã thì nhận MỘT bản chép
    của `cau_json` trong `de_cuoi_ky` (loai="de_giao") — đề đóng băng ở lúc cấp mã,
    kho testbank sửa câu sau đó không đổi bài đang làm.

    `cau_json` chứa CẢ ĐÁP ÁN, lời giải, lý do — chỉ đọc ở máy chủ; chỉ người tạo /
    admin xem được qua `GET /de-giao/{id}`."""

    __tablename__ = "de_giao"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: NULL khi còn nháp. Unique: một mã đã cấp (kể cả đã đóng) không bao giờ cấp lại.
    ma: Mapped[str | None] = mapped_column(unique=True, default=None)
    nguoi_tao_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exam: Mapped[str]                                    # CK1 | CK2
    total: Mapped[int]                                   # số câu giáo viên yêu cầu
    #: Số câu thật sự có (<= total khi kho thiếu) — để liệt kê khỏi phải đọc `cau_json`.
    so_cau: Mapped[int]
    tham_so_json: Mapped[str] = mapped_column(Text)
    thong_bao: Mapped[str] = mapped_column(Text, default="")
    cau_json: Mapped[str] = mapped_column(Text)
    trang_thai: Mapped[str] = mapped_column(default="nhap", server_default="nhap")  # nhap | mo | dong
    dong_luc: Mapped[datetime | None] = mapped_column(default=None)
    #: clock_timestamp (không phải now()): hai đề tạo sát nhau trong cùng một giao
    #: dịch phải có giờ khác nhau thì "mới tạo trước" mới đúng.
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())


class DeCuoiKy(Base):
    """Một đề cuối kỳ đã rút từ DTP Testbank cho MỘT học sinh, chờ nộp.

    Phải lưu phía máy chủ vì app stateless và đáp án không được xuống trình
    duyệt: lúc nộp, máy chủ chấm bằng `cau_json` ở đây — đúng bản nội dung
    (`qid`, `version`) học sinh đã thấy. Gọi lại testbank lúc nộp thì câu có thể
    đã được sửa (`version` khác) và đáp án mới chấm bài làm trên đề cũ.

    `cau_json` chứa CẢ ĐÁP ÁN — chỉ đọc ở máy chủ, không bao giờ trả nguyên ra.
    """

    __tablename__ = "de_cuoi_ky"

    #: Chuỗi ngẫu nhiên, không phải số tăng dần: id lộ ra client, số tăng dần thì
    #: đoán được đề của bạn khác (dù đã chặn theo user_id, đừng mời người ta thử).
    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    #: subject/grade/exam/total/seed/ar_ids đã gửi testbank — đủ để rút lại đúng đề.
    tham_so_json: Mapped[str] = mapped_column(Text)
    #: Thông báo của testbank khi thiếu câu ("Thiếu 2 câu mức V") — hiện cho học sinh.
    thong_bao: Mapped[str] = mapped_column(Text, default="")
    cau_json: Mapped[str] = mapped_column(Text)
    #: Kết quả chấm (đã có lý do từng phương án) — mở lại đề đã nộp thì trả cái này.
    ket_qua_json: Mapped[str | None] = mapped_column(Text, default=None)
    #: Lần nộp tương ứng trong quiz_attempts (chi tiết từng câu treo vào đó). Cần
    #: để học sinh XOÁ HẲN một đề: xoá đề phải xoá luôn lần nộp + chi tiết, không
    #: thì thống kê YCCĐ vẫn đếm bài em đã xoá. NULL khi chưa nộp.
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="SET NULL"), default=None, index=True)
    #: cuoi_ky (đề cuối kỳ) | luyen_them (US-25, tối đa 4 câu của MỘT bài). Dùng chung
    #: bảng vì cùng nhu cầu lưu bản câu + đáp án phía máy chủ; MỌI truy vấn lịch sử /
    #: xoá của đề cuối kỳ phải lọc `loai == "cuoi_ky"` kẻo liệt kê, xoá nhầm lượt luyện thêm.
    loai: Mapped[str] = mapped_column(default="cuoi_ky", server_default="cuoi_ky", index=True)
    #: Bài của lượt luyện thêm; NULL với đề cuối kỳ.
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("curriculum_topics.id", ondelete="SET NULL"), default=None, index=True)
    #: Bài theo mã (US-26, loai="de_giao"): đề giao mà bài này thuộc về. Unique cùng
    #: user_id -> mỗi em chỉ có MỘT bài cho mỗi mã, hai thiết bị mở cùng lúc cũng vậy.
    #: NULL với đề cuối kỳ tự rút (Postgres coi các NULL là khác nhau nên không vướng).
    de_giao_id: Mapped[int | None] = mapped_column(ForeignKey("de_giao.id"), default=None, index=True)
    #: Bài theo MÃ TESTBANK (US-29, loai="testbank"): mã vào thi 6 ký tự giáo viên phát trên
    #: Testbank. Unique cùng user_id -> mỗi em MỘT bài cho mỗi mã (Testbank mức 0 không bảo đảm
    #: điều đó: mỗi lần vào thi là một bài mới), nên chốt ở đây.
    ma_testbank: Mapped[str | None] = mapped_column(String(8), default=None)
    #: Khoá bài làm của Testbank — BÍ MẬT: ai cầm nó là đọc / sửa / nộp được bài của em. Chỉ ở
    #: máy chủ, KHÔNG BAO GIỜ trả ra API hay ghi log.
    khoa_bai_lam: Mapped[str | None] = mapped_column(Text, default=None)
    #: Tiêu đề lượt phát trên Testbank ("Kiểm tra cuối kỳ 1 — 6A").
    tieu_de: Mapped[str | None] = mapped_column(Text, default=None)
    #: Câu trả lời đã lưu lên Testbank lần cuối ({"c1": "B", ...}) — Testbank KHÔNG trả lại câu trả
    #: lẫn nội dung câu sau khi nộp, nên giữ bản chép để hiện "lựa chọn em đã chọn".
    tra_loi_json: Mapped[str | None] = mapped_column(Text, default=None)
    nop_luc: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("de_giao_id", "user_id", name="uq_de_cuoi_ky_de_giao_user"),
        UniqueConstraint("user_id", "ma_testbank", name="uq_de_cuoi_ky_testbank_user"),
    )


class NhatKySsoTestbank(Base):
    """Mỗi lần giáo viên bấm "Soạn & giao đề trên Testbank" (US-28 KB 13): thời điểm, tài khoản,
    mã phiếu và kết quả phía learning. KHÔNG lưu nguyên phiếu — phiếu là thứ dùng để đăng nhập."""

    __tablename__ = "nhat_ky_sso_testbank"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    #: Email tại thời điểm cấp: vận hành tra theo email (KB 13), mà email có thể đổi sau.
    email: Mapped[str] = mapped_column(String(255), index=True)
    vai: Mapped[str] = mapped_column(String(20))
    #: NULL khi không cấp phiếu (học sinh, chưa cấu hình, chế độ đăng nhập thường).
    jti: Mapped[str | None] = mapped_column(String(36), default=None)
    #: da_cap | mo_dang_nhap | tu_choi_vai | chua_cau_hinh
    ket_qua: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())


class LyDoPhuongAn(Base):
    """Vì sao một phương án đúng / sai — theo (qid, version, option_key).

    Testbank hiện chỉ có MỘT `explanation` cho cả câu. Tạm thời mình sinh bằng AI
    (`nguon="ai"`, app/exam/ly_do.py); khi testbank có cột `rationale` theo
    `option_key` thì ghi vào đây với `nguon="testbank"` và đọc ưu tiên bản đó.
    Hai nguồn chung một chỗ lưu nên đổi nguồn không phải sửa frontend.

    Khoá có `version`: câu được sửa là lý do cũ có thể sai với nội dung mới.
    Dùng chung cho mọi học sinh — sinh một lần, ai rút trúng câu đó cũng dùng.
    """

    __tablename__ = "ly_do_phuong_an"
    __table_args__ = (UniqueConstraint("qid", "version", "option_key", "nguon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    qid: Mapped[str] = mapped_column(index=True)
    version: Mapped[str]
    option_key: Mapped[str]
    noi_dung: Mapped[str] = mapped_column(Text)
    nguon: Mapped[str] = mapped_column(default="ai")     # ai | testbank
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class StudySession(Base):
    """MỘT phiên học của học sinh trên một bài (REQ §3.6/§7).

    Không bảng nào đang lưu THỜI LƯỢNG học — `VideoJob.duration_sec` là độ dài
    video, không phải thời gian em ngồi học. Bảng này lấp đúng chỗ đó.

    `so_giay` cộng dồn từ ping của client khi tab ĐANG HIỆN (§8 POST /me/phien),
    nên nó là thời gian học thật, không phải thời gian mở tab rồi đi chơi.
    """

    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("curriculum_topics.id"), index=True)
    mo_luc: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    dong_luc: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    so_giay: Mapped[int] = mapped_column(default=0)
    # Đếm ngay trong phiên để lịch sử học tập nói được "hỏi trợ lý n câu" mà không
    # phải join sang chỗ khác.
    so_hoi: Mapped[int] = mapped_column(default=0)
    # Các phần HS đã đọc trong phiên: ["khoi_dong","kien_thuc",…]. Lưu ID chứ
    # không lưu SỐ LƯỢNG: đọc lại phần cũ không được cộng thêm, và chuyên gia đổi
    # bố cục thì mẫu số ("/y phần") vẫn tính lại đúng.
    phan_doc_json: Mapped[str] = mapped_column(Text, default="[]")


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
    # Tên đơn vị/mạch NGUYÊN VĂN trong .docx + điểm khớp lúc nạp (REQ §2.5).
    # Phải lưu tại thời điểm nạp: sau đó tên gốc không còn ở đâu, nên bảng đối
    # chiếu không thể tính lại điểm — so tên đã gán với chính nó luôn ra 100%.
    ten_nguon: Mapped[str | None] = mapped_column(default=None)
    mach_nguon: Mapped[str | None] = mapped_column(default=None)
    diem_khop: Mapped[float | None] = mapped_column(default=None)
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


class BookJob(Base):
    """Một lần NẠP SÁCH: 151 ảnh trang → OCR → cắt đoạn → Qdrant (REQ §2.4).

    Vì sao cần bảng riêng chứ không đọc log như trước: mỗi trang là một lần gọi
    vision LLM nên cả tập mất 20–30 phút. Không có bảng thì UI không trả lời được
    “đang ở trang bao nhiêu”, và đóng tab là mất dấu hoàn toàn.

    Tiến độ ghi theo TRANG, không theo phần trăm: người soạn cần biết trang nào
    đang dở để đoán còn bao lâu, và để nạp tiếp đúng chỗ. Cache OCR
    (data_processed/) làm việc nạp tiếp gần như miễn phí.
    """

    __tablename__ = "book_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    mon: Mapped[str]
    khoi: Mapped[str]
    tap: Mapped[int]
    sach: Mapped[str]                                   # mã sách -> đi vào dẫn nguồn
    # cho | dang | tam_dung | xong | loi
    trang_thai: Mapped[str] = mapped_column(default="cho", index=True)
    buoc: Mapped[str] = mapped_column(default="doc")    # doc | cat_doan | ghi_kho
    trang_ds_json: Mapped[str] = mapped_column(Text, default="[]")   # các trang phải đọc
    trang_xong_json: Mapped[str] = mapped_column(Text, default="[]")
    trang_loi_json: Mapped[str] = mapped_column(Text, default="[]")  # [{so, ly_do}]
    trang_dang: Mapped[int | None] = mapped_column(default=None)
    # Trang đáng ngờ + số liệu chất lượng, điền khi đọc xong (màn soát).
    trang_soat_json: Mapped[str] = mapped_column(Text, default="[]")  # [{so, ly_do, chu}]
    so_trang_co_bai: Mapped[int] = mapped_column(default=0)
    so_doan: Mapped[int] = mapped_column(default=0)
    loi: Mapped[str | None] = mapped_column(Text, default=None)
    nguoi_tao_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


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


class HocLieu(Base):
    """Một học liệu có mã trong kho (US-27): video / SGK / SBT / BTTC gắn vào MỘT YCCĐ,
    tuỳ chọn thu hẹp theo một câu (`qid`, mã ổn định của kho đề testbank) và theo một
    phương án của câu đó (`option_key`, chỉ khi có `qid`).

    Cùng khuôn với học liệu của testbank (loai / nhan / url / qid / option_key) cộng ba
    phần mở rộng của learning: `ma`, `muc_dich` (on_lai | cung_co) và gắn theo YCCĐ không
    cần câu — để sau này đổi nguồn chỉ là đồng bộ dữ liệu, giao diện học sinh không đổi.

    `ycd_key` là khoá nhận diện (`app/lessons/ycd_key.chuan_hoa`), KHÔNG khoá ngoại tới
    `blueprint_cells.id`: nạp lại ma trận là xoá sạch cell cũ rồi chèn cell mới.
    `ma` lưu CHỮ HOA. Xoá mềm: dòng ở lại nên mã đã dùng không bao giờ dùng lại.
    Thời gian lấy đồng hồ Postgres (`clock_timestamp`, không phải `now()` là mốc đầu
    giao dịch) để danh sách "mới sửa trước" đúng thứ tự dù hai dòng tạo sát nhau."""

    __tablename__ = "hoc_lieu"

    id: Mapped[int] = mapped_column(primary_key=True)
    ma: Mapped[str] = mapped_column(String(64))
    loai: Mapped[str] = mapped_column(String(8))                 # VIDEO | SGK | SBT | BTTC
    nhan: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024))
    muc_dich: Mapped[str] = mapped_column(String(8))             # on_lai | cung_co
    ycd_key: Mapped[str] = mapped_column(Text, index=True)
    ycd_text: Mapped[str] = mapped_column(Text)
    qid: Mapped[str | None] = mapped_column(default=None)
    option_key: Mapped[str | None] = mapped_column(String(8), default=None)
    nguoi_tao_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    tao_luc: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
    nguoi_sua_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    sua_luc: Mapped[datetime | None] = mapped_column(default=None)
    xoa_luc: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (UniqueConstraint("ma", name="uq_hoc_lieu_ma"),)


def luot_khong_xet_dat():
    """Điều kiện SQL: lượt Luyện thêm dưới 3 câu chấm được (US-25 KB17). Lượt này có
    `dat=False` nhưng KHÔNG phải trượt — mọi thống kê "trượt / số lần / điểm" phải loại ra
    bằng `~luot_khong_xet_dat()`, dùng chung một chỗ để các nơi không lệch luật nhau."""
    from sqlalchemy import and_
    return and_(QuizAttempt.nguon == "luyen_them", QuizAttempt.tong < 3)
