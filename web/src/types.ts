export type Role = "hoc_sinh" | "giao_vien" | "admin";

export interface AdminUser {
  id: number;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  daily_limit_override: number | null;
  created_at: string;
  sessions: number;
  questions: number;
  today: number;
}

export interface AdminMessage {
  content: string;
  created_at: string;
  subject: string;
}

export interface DailyStat {
  date: string;   // YYYY-MM-DD
  count: number;
}

export interface Citation {
  nguon: string;
  page_no: number;
  chuong_so: number | null;
  bai_so: number | null;
  tap: number | null;
}

export interface VideoInfo {
  status: "OFFERED" | "QUEUED" | "RENDERING" | "DONE" | "FAILED";
  concept_key?: string | null;
  job_id?: number | null;
  video_url: string | null;
}

// Chip gợi ý dưới câu trả lời. action="ask" -> gửi `query`; action="practice_exam"
// -> mở đề ngắn sinh theo ma trận.
export interface Suggestion {
  label: string;
  query?: string;
  action?: "ask" | "practice_exam";
}

// Đề nghị luyện tập i-Test kèm câu trả lời — chỉ mang chủ đề; bấm nút mới tải đề.
export interface ItestOffer {
  topic: string;
}

// Bài trắc nghiệm i-Test (query trực tiếp DB i-Test, như repo dtp-chat-learning).
export interface QuizQuestion {
  type: "single" | "multi" | "fill" | "match";
  q: string;
  options?: string[];
  answer?: number | null; // single: -1 = chưa xác định (hiện, không chấm)
  answers?: number[];     // multi
  blanks?: string[];      // fill
  image?: string | null;
}

export interface QuizData {
  id: number;
  title: string;
  questions: QuizQuestion[];
}

export interface Quota {
  limit: number | null;      // null = không giới hạn
  used: number;
  remaining: number | null;
}

export interface ChatResponse {
  reply: string;
  intent: string | null;
  citations: Citation[];
  session_id: number;
  video: VideoInfo | null;
  itest: ItestOffer | null;
  suggestions: Suggestion[];
  quota: Quota | null;
}

export interface SessionRow {
  id: number;
  title: string;
  subject: string;
  last_active: string;
}

export interface MessageRow {
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
}

export interface ChatMessage {
  who: "user" | "bot";
  text: string;
  citations?: Citation[];
  pending?: boolean;
  error?: boolean;
  video?: VideoInfo;
  itest?: ItestOffer;
  chips?: Suggestion[];
}

// ── Bài học có cấu trúc (theo meeting note): mỗi Đơn vị kiến thức = 4 phần cố
// định, KHÔNG trích dẫn số trang. Dữ liệu do chuyên gia biên soạn (nhiều nguồn).
export interface LessonMedia { loai: "video" | "image"; url: string; caption?: string }
export interface LessonExample { de_bai: string; loi_giai: string }
export interface LessonQuickCheck {
  cau_hoi: string; lua_chon: string[]; dap_an: number; muc_do?: "de" | "trung_binh" | "kho";
}
export interface LessonContent {
  mach_noi_dung: string;
  don_vi_kien_thuc: string;
  khai_niem: string;            // (1) thuần text/markdown
  minh_hoa: LessonMedia[];      // (2) video hoặc hình ảnh
  vi_du: LessonExample[];       // (3) ví dụ
  kiem_tra_nhanh: LessonQuickCheck[];  // (4) bài kiểm tra nhanh
}

export interface AuthResult {
  token: string;
  role: Role;
  name: string;
}

export interface ExamQuestion {
  muc_do: "de" | "trung_binh" | "kho";
  noi_dung: string;
  dap_an: string;
  loi_giai: string;
}

export interface ExamResult {
  hoc_ky: string;
  mon?: string;
  tong_so_cau: number;
  chi_tieu: Record<string, number>;
  ti_le_muc_do: Record<string, number>;
  mach_noi_dung: string[];
  cau_hoi: ExamQuestion[];
  canh_bao: string | null;
}
