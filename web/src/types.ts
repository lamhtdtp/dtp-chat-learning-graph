export type Role = "hoc_sinh" | "giao_vien";

export interface Citation {
  nguon: string;
  page_no: number;
  chuong_so: number | null;
  bai_so: number | null;
  tap: number | null;
}

export interface VideoInfo {
  job_id: number;
  status: "QUEUED" | "RENDERING" | "DONE" | "FAILED";
  video_url: string | null;
}

export interface ChatResponse {
  reply: string;
  intent: string | null;
  citations: Citation[];
  session_id: number;
  video: VideoInfo | null;
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
