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
}
export interface QuizResult {
  diem: number;
  tong: number;
  dat_yeu_cau: boolean;
  trang_thai: "dat" | "dang";
  ket_qua: QuizResultItem[];
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
  vi_du: { de: string; giai: string }[];
  quiz: QuizQuestion[];
  co_quiz: boolean;
  nhac: Nhac[];
  day: LessonDay | null;
  /** Tư liệu thô chuyên gia dán cho AI. CHỈ tác giả nhận; HS luôn nhận null. */
  nguon: string | null;
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
export interface TutorAnswer {
  answer: string;
  citations: TutorCitation[];
  khong_tim_thay: boolean;
  remaining: number | null;
  /** Nhãn đoạn bài học trợ lý đã dựa vào ("Ví dụ 2", "Khái niệm"…). null = chỉ có SGK. */
  nguon_bai: string | null;
}

/** Đoạn bài học đang hỏi. Khớp với `anchor` ở backend (app/api/tutor.py). */
export type Neo = "khai_niem" | "minh_hoa" | `vi_du:${number}` | `quiz:${number}`;

// Hero gamification (GET /me/stats)
export interface MyStats {
  overall: number;
  dat: number;
  tong: number;
  current_mach: { mach: string; em: string; phan_tram: number } | null;
  streak: number;
  xp_week: number;
  xp_total: number;
}
