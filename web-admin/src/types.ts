export type Role = "hoc_sinh" | "giao_vien" | "admin";

export interface AdminUser {
  id: number;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  daily_limit_override: number | null;
  created_at: string;
  hoan_thanh: number;   // số đơn vị đã Đạt
  dang_hoc: number;     // số đơn vị Đang học
}

export interface AuthResult {
  token: string;
  role: Role;
  name: string;
}

// ── CMS chuyên gia biên soạn giáo trình (P4) ──
export interface CmsCompleteness {
  done: number;
  total: number;
  parts: { khai_niem: boolean; minh_hoa: boolean; vi_du: boolean; quiz: boolean };
}
export interface CmsUnit {
  topic_id: number;
  ten: string;
  trang_thai: string;                 // draft | review | published | chua_bien_soan
  completeness: CmsCompleteness;
  nguon?: string | null;
  ai?: boolean;
}
export interface CmsGroup {
  mach: string;
  dv: CmsUnit[];
}
export interface CmsMedia {
  type: string;                       // image | video
  url?: string;
  caption?: string;
  source?: string;                    // ai | expert
}
export interface CmsViDu { de: string; giai: string }
export interface CmsQuiz { q: string; o: string[]; a: number; lv: string; giai?: string }
export interface CmsDay {
  muc_tieu?: string;
  thoi_luong?: string;
  luu_y?: string;
  goi_y?: Record<string, string>;
}
export interface CmsYeuCau { yeu_cau: string; muc_do: string }
export interface CmsTopic {
  topic_id: number;
  mach: string;
  dv: string;
  yeu_cau_can_dat: CmsYeuCau[];
  khai_niem: string;
  minh_hoa: CmsMedia[];
  vi_du: CmsViDu[];
  quiz: CmsQuiz[];
  day: CmsDay | null;
  nguon: string | null;
  trang_thai: string;
  completeness: CmsCompleteness;
}
