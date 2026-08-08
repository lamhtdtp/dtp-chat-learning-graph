export type Role = "hoc_sinh" | "giao_vien" | "chuyen_gia" | "admin";

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
  url?: string | null;                // null = video AI đặt hàng, đang render
  caption?: string;
  source?: string;                    // ai | expert
  concept_key?: string;               // video AI: khoá tra job render (điền url khi DONE)
  /** URL đã ký, CHỈ để xem trong trình soạn. Không gửi lên khi lưu (server lược). */
  url_xem?: string;
}
/** Nháp AI trả về: nội dung bám SGK + minh hoạ đã sinh thật. */
export interface CmsAiDraft {
  khai_niem: string;
  vi_du: CmsViDu[];
  minh_hoa: CmsMedia[];
  trang_sgk: number[];                // số trang SGK đã dùng làm ngữ liệu
  thieu_sgk: boolean;                 // true = KHÔNG bám được SGK, phải rà kỹ
  loi_media: string[];                // lý do ảnh/video nào không sinh được
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

/** Kết quả Kiểm tra nhanh của 1 học sinh (GET /admin/users/{id}/result). */
export interface KetQuaLan {
  topic_id: number; ten: string; mach: string;
  diem: number; tong: number; dat: boolean; phan_tram: number; luc: string;
}
export interface KetQuaDonVi {
  topic_id: number; ten: string; mach: string;
  so_lan: number; tot_nhat: number; gan_nhat: number; dat: boolean;
}
export interface KetQuaHocSinh {
  hoc_sinh: { id: number; name: string; email: string };
  tong_lan: number; so_lan_dat: number; diem_tb: number;
  theo_don_vi: KetQuaDonVi[];
  lan: KetQuaLan[];
}

/** Số liệu học tập cho trang Tổng quan (GET /admin/overview). */
export interface AdminOverview {
  tong: { luot_lam: number; hoc_sinh: number; ty_le_dat: number };
  hoat_dong: { ngay: string; so_lan: number }[];
  kho_nhat: { topic_id: number; ten: string; mach: string; so_lan: number; ty_le_truot: number }[];
  toi_thieu_luot: number;
  phan_bo: { khoang: string; so_lan: number; dat: boolean }[];
  theo_mach: { mach: string; so_lan: number; ty_le_dat: number }[];
  pheu: { buoc: string; so: number }[];
  chua_hoc: { topic_id: number; ten: string; mach: string }[];
  chua_hoc_tong: number;
}
