export type Role = "hoc_sinh" | "giao_vien";

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

// Chip gợi ý bước tiếp theo dưới câu trả lời (bấm -> gửi `query`).
export interface Suggestion {
  label: string;
  query: string;
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

export interface ChatResponse {
  reply: string;
  intent: string | null;
  citations: Citation[];
  session_id: number;
  video: VideoInfo | null;
  itest: ItestOffer | null;
  suggestions: Suggestion[];
}

export interface SessionRow {
  id: number;
  title: string;
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
  tong_so_cau: number;
  chi_tieu: Record<string, number>;
  ti_le_muc_do: Record<string, number>;
  mach_noi_dung: string[];
  cau_hoi: ExamQuestion[];
  canh_bao: string | null;
}
