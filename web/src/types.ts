/** Hồ sơ người đăng nhập (GET /auth/me). */
export interface Me { id: number; email: string; name: string; role: Role }

export type Role = "hoc_sinh" | "giao_vien" | "chuyen_gia" | "admin";

// ── Giáo trình có cấu trúc (mô hình mockup) ──
export interface CurriculumUnit {
  topic_id: number;
  ten: string;
  trang_thai: "dat" | "dang" | "chua";
  co_noi_dung: boolean;
}
export interface CurriculumGroup {
  mach: string;
  em: string;
  dv: CurriculumUnit[];
}
export interface MinhHoa {
  type: string;              // video | image | sieve …
  url?: string | null;
  caption?: string;
  source?: string;           // "ai" | "expert"
}
export interface PhanBoCuc {
  id: string; ten: string; em: string; cot: string | null; an: boolean; so: number;
}
export interface LessonDay {
  muc_tieu?: string;
  thoi_luong?: string;
  luu_y?: string;
  goi_y?: Record<string, string>;
}
// Câu trắc nghiệm — góc nhìn HỌC SINH KHÔNG có 'a'/'giai' (chấm ở server).
export interface QuizQuestion {
  q: string;
  o: string[];
  lv: "de" | "trung_binh" | "kho";
}
export interface QuizResultItem {
  /** false = bài học của câu này chưa xuất bản: không hiện "Đọc lại phần này" (US-27 KB 19). */
  bai_xuat_ban?: boolean;
  dung: boolean;
  chon: number;
  dap_an: number;
  giai: string;
  /** Phần nội dung câu này kiểm tra — để chỉ HS về đúng đoạn cần đọc lại (§3.4). */
  phan?: string;
  /** Yêu cầu cần đạt tương ứng trong ma trận. */
  ycd?: string;
}
export interface QuizResult {
  diem: number;
  tong: number;
  dat_yeu_cau: boolean;
  trang_thai: "dat" | "dang";
  ket_qua: QuizResultItem[];
  /** Khối "Đề xuất" — máy chủ tính lại theo kho học liệu hiện tại mỗi lần trả về (US-27). */
  de_xuat?: DeXuat;
  /** Server vẫn luôn trả 3 khoá này (xem POST /quiz/submit) — trước đây type
   *  bỏ sót nên chỗ nào muốn hiện "+XP" đều phải ép kiểu. */
  xp?: number;
  xp_week?: number;
  streak?: number;
}
/** Lời nhắc chủ động của trợ lý ở một mốc trong bài (sinh sẵn lúc biên soạn). */
export interface Nhac {
  moc: "khai_niem";
  hoi: string;
  dap: string[];
  /** Chỉ số phương án đúng trong `dap` — để phản hồi ngay tại client. */
  dung: number;
  giai: string;
}

export interface Lesson {
  topic_id: number;
  mach: string;
  dv: string;
  khai_niem: string;
  minh_hoa: MinhHoa[];
  vi_du: { de: string; giai: string; anh?: string }[];
  quiz: QuizQuestion[];
  co_quiz: boolean;
  nhac: Nhac[];
  day: LessonDay | null;
  /** Tư liệu thô chuyên gia dán cho AI. CHỈ tác giả nhận; HS luôn nhận null. */
  nguon: string | null;
  // 4 phần nội dung mới (REQ §1.1)
  khoi_dong?: string;
  hoat_dong?: string;
  luyen_tap?: string;
  bai_tap?: string;
  /** Thứ tự + số thứ tự các phần ĐANG HIỆN. Server tính, client KHÔNG tự suy —
   *  tự suy là số lệch với bản chuyên gia đang soạn. */
  bo_cuc?: PhanBoCuc[];
  trang_thai: string;        // published | draft | chua_bien_soan
}
export interface ProgressGroup {
  mach: string;
  em: string;
  phan_tram: number;
  dv: { topic_id: number; ten: string; trang_thai: "dat" | "dang" | "chua" }[];
}
export interface ProgressMe {
  overall: number;
  dat: number;
  dang: number;
  tong: number;
  mach: ProgressGroup[];
}

export interface AuthResult {
  token: string;
  role: Role;
  name: string;
}

// Trợ lý hỏi–đáp bám SGK (POST /tutor/ask)
export interface TutorCitation { page_no: number; nguon: string }
/** Hình của chính bài đang học, đính theo câu trả lời khi câu hỏi nói về hình. */
export interface AnhKem { url: string; caption: string; tu: string }
/** Lối mở sang một bài mà câu trả lời có nhắc tới. Chỉ có ở phạm vi "ca_cuon" —
 *  khớp `MucLienQuan` ở app/api/tutor.py. */
export interface MucLienQuan { topic_id: number; ten: string }

export interface TutorAnswer {
  answer: string;
  citations: TutorCitation[];
  khong_tim_thay: boolean;
  remaining: number | null;
  /** Nhãn đoạn bài học trợ lý đã dựa vào ("Ví dụ 2", "Khái niệm"…). null = chỉ có SGK. */
  nguon_bai: string | null;
  anh: AnhKem[];
  /** Bài mà câu trả lời nhắc tới (phạm vi cả cuốn). Mặc định [] cho client cũ. */
  muc_lien_quan?: MucLienQuan[];
}

/** Đoạn bài học đang hỏi. Khớp với `anchor` ở backend (app/api/tutor.py). */
/** Neo = đoạn học sinh đang hỏi. Phải khớp `_NEO_RE` ở app/api/tutor.py — thêm ở
 *  một bên thôi thì FE gửi lên bị 422 hoặc BE nhận neo mà FE không tạo được. */
export type Neo =
  | "khoi_dong" | "hoat_dong" | "kien_thuc" | "khai_niem" | "minh_hoa"
  | "luyen_tap" | "bai_tap"
  | `vi_du:${number}` | `quiz:${number}`;

/** Phạm vi câu hỏi. Khớp `AskRequest.pham_vi` ở app/api/tutor.py.
 *  - "bai": trong đơn vị đang mở — nội dung bài là nguồn ưu tiên.
 *  - "ca_cuon": xuyên cả cuốn SGK của khối đó — bỏ nội dung bài, kèm mục lục,
 *    lấy nhiều đoạn SGK hơn và không ghép tên bài vào truy vấn. */
export type PhamVi = "bai" | "ca_cuon";

// Hero gamification (GET /me/stats)
export interface MachTienDo { mach: string; em: string; phan_tram: number }
export interface MyStats {
  overall: number;
  dat: number;
  tong: number;
  /** Mạch chưa xong đầu tiên — chỉ dùng khi chưa mở bài nào. */
  current_mach: MachTienDo | null;
  /** Tiến độ TỪNG mạch, để vòng tiến độ theo đúng bài đang mở. */
  mach: MachTienDo[];
  streak: number;
  /** % theo yêu cầu cần đạt (mỗi ô ma trận là một yêu cầu). */
  ycd_dat: number;
  ycd_tong: number;
  ycd_phan_tram: number;
  xp_week: number;
  xp_total: number;
}

/** Hồ sơ học tập — thời gian (GET /me/thoi-gian · REQ §3.6). */
export interface ThoiGianHoc {
  hom_nay_phut: number; bay_ngay_phut: number; tong_phut: number; so_phien: number;
  muc_tieu_phut: number; dat_muc_tieu: boolean;
  bieu_do: { ngay: string; phut: number; hom_nay: boolean }[];
  lich_su: {
    topic_id: number; ten: string; luc: string; phut: number; so_hoi: number;
    doc_x: number; doc_y: number;
    /** `nguon` chỉ có khi không phải Kiểm tra nhanh (vd "luyen_them"). */
    quiz: { diem: number; tong: number; dat: boolean; nguon?: string } | null;
    dang_hoc: boolean;
  }[];
}
/** Đạt tới đâu theo yêu cầu cần đạt (GET /me/ycd).
 *
 * `dung`/`tong`/`sai` đếm theo SỐ CÂU của chính yêu cầu cần đạt này (nguồn:
 * quiz_attempt_items). `truot_bai` mới là số LẦN trượt cả bài kiểm tra — hai
 * con số khác nghĩa, đừng hiển thị lẫn nhau.
 *
 * `tong === 0` nghĩa là chưa làm câu nào, KHÁC với làm rồi mà sai hết.
 * `yeu` do server quyết theo ngưỡng dùng chung — client không tự so lại. */
export interface YcdMach {
  mach: string;
  ycd: { ycd: string; muc_do: string; topic_id: number; don_vi: string;
         trang_thai: string; dung: number; tong: number; sai: number;
         yeu: boolean; truot_bai: number }[];
}

/** Trang Ôn tập chương / cuối kỳ (GET /on-tap — REQ §3.5). */
export interface OnTap {
  pham_vi: "mach" | "hoc_ky";
  gia_tri: string;
  so_bai: number; chua_xong: number; ycd: number;
  /** Số câu THẬT gom được (bài chưa có đề thì không góp câu). */
  so_cau_de: number;
  so_cau_toi_da: number;
  so_bai_co_de: number;
  bai: { topic_id: number; ten: string; mach: string;
         trang_thai: "dat" | "dang" | "chua"; co_noi_dung: boolean }[];
  can_nho: { topic_id: number; ten: string; y: string }[];
}
/** Một câu của đề ôn tập — KHÔNG kèm đáp án (server chấm). */
export interface CauOnTap { topic_id: number; idx: number; bai: string;
  q: string; o: string[]; lv: "de" | "trung_binh" | "kho" }
export interface DeOnTap { pham_vi: string; gia_tri: string; so_cau: number; cau: CauOnTap[] }

/* ── Đề cuối kỳ rút từ DTP Testbank (POST /exam/cuoi-ky/*) ──────────────────
 * HTML trong các trường `*_html` đã được server làm sạch (chỉ giữ vài thẻ định
 * dạng + <img> ảnh công thức của testbank) — render thẳng, KHÔNG qua renderMath:
 * công thức của testbank là ảnh hoặc Unicode, không phải LaTeX. */
export type DangCau = "TN1" | "TNN" | "DS" | "DSN" | "TL";

export interface CauCuoiKy {
  stt: number;
  qid: string;
  dang: DangCau;
  muc_do: "B" | "H" | "V" | string;
  ar_id: string;
  ycd: string;
  topic_id: number | null;
  don_vi: string;
  de_html: string;
  /** `nhan` chỉ có ở bài theo mã Testbank (nhãn hiển thị; `key` mới là khoá gửi đi). */
  phuong_an: { key: string; html: string; nhan?: string }[];
  du_kien_html: string;
  cau_dan: string;
  /** false = không chấm tự động (tự luận, đáp số là hình) — không tính vào điểm. */
  tu_cham: boolean;
}

export interface LyDoPhuongAn {
  noi_dung: string;
  /** "ai" = sinh tự động, "testbank" = bản chính thức có người duyệt. */
  nguon?: "ai" | "testbank" | string;
  dung: boolean;
}

/** Một học liệu trong khối Đề xuất (US-27). `url` đã ký nếu là video nội bộ. */
export interface MucHocLieu {
  ma: string;
  loai: "VIDEO" | "SGK" | "SBT" | "BTTC";
  nhan: string;
  url: string;
  /** true = video AI nội bộ: phát trong khung nổi; false = link ngoài: mở tab mới. */
  noi_bo: boolean;
  muc_dich: "on_lai" | "cung_co";
  /** "Vì em chọn B ở câu 3" · "Liên quan câu 2, 5, 8" · "Củng cố". */
  ghi_chu: string;
}
export interface MucBaiHoc {
  topic_id: number;
  ten: string;
  /** Id phần của bố cục bài ("kien_thuc", "vi_du", …). */
  phan: string;
  ghi_chu: string;
}
/** Khối "Đề xuất" — CÙNG MỘT hình dạng ở mọi loại bài làm. Nhóm rỗng là null. */
export interface DeXuat {
  loi_khen: string | null;
  thong_bao: string | null;
  doc_them: { bai_hoc: MucBaiHoc[]; hoc_lieu: MucHocLieu[]; toi_da_bai_hoc: number; toi_da_hoc_lieu: number } | null;
  video: { hoc_lieu: MucHocLieu[]; toi_da: number } | null;
  test_them: { ar_ids: string[]; ycd: string[]; so_cau: number; mo_ta: string; thieu: string[]; bo_qid: string[] } | null;
}

export interface KetQuaCau {
  /** false = bài của YCCĐ này chưa xuất bản / không khớp bài nào: không hiện "Xem lại bài". */
  bai_xuat_ban?: boolean;
  stt: number;
  qid: string;
  dang: DangCau;
  ar_id: string;
  ycd: string;
  topic_id: number | null;
  don_vi: string;
  chon: string;
  dap_an: string;
  dap_an_html: string;
  cham_duoc: boolean;
  dung: boolean;
  so_y_dung: number | null;
  so_y: number | null;
  giai_html: string;
  ly_do: Record<string, LyDoPhuongAn>;
  /** Bài theo mã giai đoạn 2 (US-30): "Đang chuẩn bị giải thích từng phương án…" khi lý do chưa sinh xong. */
  ly_do_ghi_chu?: string;
  /** Bài theo mã giai đoạn 1 (US-30): máy chủ chưa gửi đáp án — chỉ biết `dung`; thẻ câu không hiện đáp án / lời giải. */
  chua_mo_dap_an?: boolean;
}

/** Lượt "Luyện thêm từ kho đề" (US-25) — POST /lessons/{id}/luyen-them. Như đề cuối kỳ
 *  nhưng của MỘT bài, tối đa 4 câu; không có đáp án / lời giải trước khi nộp. */
export interface DeLuyenThem {
  /** null = không có lượt nào (kho trống / bài chưa có YCCĐ) — `thong_bao` nói rõ vì sao. */
  de_id: string | null;
  cau: CauCuoiKy[];
  du_cau: boolean;
  thong_bao: string;
  so_cau_cham_duoc: number;
  /** false = dưới 3 câu chấm được: vẫn chấm, nhưng không tính đạt bài. */
  xet_dat: boolean;
}

export interface KetQuaLuyenThem {
  de_id: string;
  cau: (KetQuaCau & { phan: string })[];
  /** Số câu đúng / số câu CHẤM ĐƯỢC. */
  diem: number;
  tong: number;
  khong_cham: number;
  xet_dat: boolean;
  /** Chỉ true khi xét đạt và >= 70%. */
  dat_yeu_cau: boolean;
  /** Trạng thái bài SAU lượt (đã đạt thì không hạ). */
  trang_thai: "dat" | "dang" | "chua";
  xp: number;
  /** Có khi không xét đạt: "Lượt này chỉ có N câu chấm tự động (cần ít nhất 3)…". */
  ghi_chu: string;
  de_xuat?: DeXuat;
}

export interface YcdKetQua {
  ar_id: string;
  ycd: string;
  dung: number;
  tong: number;
  topic_id: number | null;
  don_vi: string;
  trang: "dat" | "dang" | "chua";
}

export interface KetQuaCuoiKy {
  de_id: string;
  /** Có khi là bài theo mã thầy cô giao (US-26). */
  ma?: string;
  diem: number;
  tong: number;
  dat_yeu_cau: boolean;
  khong_cham: number;
  cau: KetQuaCau[];
  theo_ycd: YcdKetQua[];
  de_xuat?: DeXuat;
  goi_y: {
    ar_ids: string[];
    tai_lieu: { topic_id: number; don_vi: string; phan: string; ycd: string; ar_id: string; cau: number[] }[];
    de_moi: { subject: string; grade: string; exam: string | null };
  };
}

export interface DeCuoiKy {
  de_id: string | null;
  cau: CauCuoiKy[];
  /** false = testbank rút thiếu câu — `thong_bao` nói rõ thiếu gì. */
  du_cau: boolean;
  thong_bao: string;
  ket_qua?: KetQuaCuoiKy | null;
  /** Có ở GET /exam/cuoi-ky/{de_id}: đề "làm bài mới" chỉ trong YCCĐ còn yếu. */
  on_lai?: boolean;
  /** Mã thầy cô giao — chỉ có với bài theo mã (US-26); đề tự rút thì null/không có. */
  ma?: string | null;
  exam?: string | null;
  ghi_chu?: string;
}

/** Một đề trong lịch sử (GET /exam/cuoi-ky) — chỉ tóm tắt, không nội dung câu. */
export interface DeCuoiKyTomTat {
  de_id: string;
  exam: string | null;
  /** true = đề "làm bài mới" chỉ trong các YCCĐ còn yếu. */
  on_lai: boolean;
  so_cau: number;
  luc: string;
  da_nop: boolean;
  nop_luc: string | null;
  /** null khi chưa nộp. */
  diem: number | null;
  tong: number | null;
  dat: boolean | null;
  /** "de_giao" = bài theo mã US-26 cũ; "testbank" = bài theo mã thầy cô phát trên Testbank (US-29).
   *  Cả hai có nhãn mã và KHÔNG xoá được. */
  loai: "cuoi_ky" | "de_giao" | "testbank";
  ma: string | null;
  tieu_de?: string | null;
  /** Bài theo mã Testbank mức 1 (US-30): "Chờ thầy cô đóng bài" | "Đã có đáp án" | null. */
  nhan_trang_thai?: string | null;
  xoa_duoc: boolean;
  /** Bài theo mã US-26 chưa nộp mà đề giao đã ngừng: hiện nhãn, không mở được. */
  da_ngung?: boolean;
}

/* ── Bài theo mã thầy cô phát trên Testbank (US-29) — /exam/ma/* ──────────────
 * KHÔNG có đáp án, lời giải, YCCĐ, khoá bài làm: máy chủ không có / không đưa xuống. */
export interface KetQuaCauMa {
  stt: number;
  /** DUNG | SAI | DUNG_MOT_PHAN | CHO_GIAO_VIEN_CHAM */
  trang_thai: string;
  /** Đúng | Sai | Đúng một phần | Chưa chấm — như Testbank trả. */
  nhan: string;
  diem: number | null;
  diem_toi_da: number | null;
  /** Lựa chọn em đã chọn (cùng dạng chuỗi như lúc làm). */
  chon: string;
  dang: string;
  // ── US-30: chỉ có ở bài mức 1 đã có chi tiết sau nộp (giai đoạn 1 và 2) ──
  qid?: string;
  muc_do?: string;
  ycd?: string;
  ar_id?: string;
  topic_id?: number | null;
  don_vi?: string;
  cham_duoc?: boolean;
  dung?: boolean;
  bai_xuat_ban?: boolean;
  // ── chỉ có ở giai đoạn 2 (thầy cô đã đóng bài); giai đoạn 1 KHÔNG có các khoá này ──
  dap_an?: string;
  dap_an_html?: string;
  giai_html?: string;
  so_y_dung?: number | null;
  so_y?: number | null;
  ly_do?: Record<string, LyDoPhuongAn>;
  ly_do_ghi_chu?: string;
}
export interface KetQuaMa {
  diem: number;
  tong: number;
  so_cau_cho_cham: number;
  cau: KetQuaCauMa[];
  cach_nop: "TAY" | "HET_GIO" | "DONG_LUOT_PHAT" | null;
  /** US-30: kết quả theo YCCĐ + khối Đề xuất (giai đoạn 1 và 2). */
  giai_doan?: 0 | 1 | 2;
  theo_ycd?: YcdKetQua[];
  khong_cham?: number;
  de_xuat?: DeXuat;
}
export interface BaiMa {
  de_id: string;
  ma: string;
  tieu_de: string;
  nhan: string;
  trang_thai: "DANG_LAM" | "DA_NOP";
  cau: CauCuoiKy[];
  /** Lựa chọn đã lưu, theo qid ("c1"…). */
  tra_loi: Record<string, string>;
  /** Giờ MÁY CHỦ Testbank; đồng hồ đếm ngược tính theo hiệu hai giá trị này, không theo giờ máy em. */
  han_nop_luc: string | null;
  gio_may_chu: string | null;
  thoi_gian_phut: number | null;
  ket_qua: KetQuaMa | null;
  thong_bao: string;
  /** 0 = chưa có chi tiết sau nộp (bài mức 0 / cờ tắt / chưa lấy được) · 1 = chờ thầy cô đóng bài ·
   *  2 = đã có đáp án. */
  giai_doan: 0 | 1 | 2;
  co_chi_tiet: boolean;
  /** Các dòng trạng thái hiện nguyên văn trên màn kết quả (máy chủ dựng, đúng chữ của US-30). */
  ghi_chu: string[];
}
export interface CheDoNhapMa {
  /** tich_hop: làm trong app · du_phong: mở web-student của Testbank · tat: chưa nối gì. */
  che_do: "tich_hop" | "du_phong" | "tat";
  url_du_phong: string | null;
}
