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
export interface TutorAnswer {
  answer: string;
  citations: TutorCitation[];
  khong_tim_thay: boolean;
  remaining: number | null;
  /** Nhãn đoạn bài học trợ lý đã dựa vào ("Ví dụ 2", "Khái niệm"…). null = chỉ có SGK. */
  nguon_bai: string | null;
  anh: AnhKem[];
}

/** Đoạn bài học đang hỏi. Khớp với `anchor` ở backend (app/api/tutor.py). */
/** Neo = đoạn học sinh đang hỏi. Phải khớp `_NEO_RE` ở app/api/tutor.py — thêm ở
 *  một bên thôi thì FE gửi lên bị 422 hoặc BE nhận neo mà FE không tạo được. */
export type Neo =
  | "khoi_dong" | "hoat_dong" | "kien_thuc" | "khai_niem" | "minh_hoa"
  | "luyen_tap" | "bai_tap"
  | `vi_du:${number}` | `quiz:${number}`;

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
    quiz: { diem: number; tong: number; dat: boolean } | null;
    dang_hoc: boolean;
  }[];
}
/** Đạt tới đâu theo yêu cầu cần đạt (GET /me/ycd). */
export interface YcdMach {
  mach: string;
  ycd: { ycd: string; muc_do: string; topic_id: number; don_vi: string;
         trang_thai: string; sai: number }[];
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
