export type Role = "hoc_sinh" | "giao_vien";

export interface Citation {
  nguon: string;
  page_no: number;
  chuong_so: number | null;
  bai_so: number | null;
}

export interface ChatResponse {
  reply: string;
  intent: string | null;
  citations: Citation[];
  session_id: string;
}

export interface ChatMessage {
  who: "user" | "bot";
  text: string;
  citations?: Citation[];
  pending?: boolean;
  error?: boolean;
}
