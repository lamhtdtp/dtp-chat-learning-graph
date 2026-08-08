export type Role = "hoc_sinh" | "giao_vien" | "admin";

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
export interface Lesson {
  topic_id: number;
  mach: string;
  dv: string;
  khai_niem: string;
  minh_hoa: MinhHoa[];
  vi_du: { de: string; giai: string }[];
  quiz: QuizQuestion[];
  co_quiz: boolean;
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
}

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
