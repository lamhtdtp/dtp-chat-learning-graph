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
export interface CmsViDu {
  de: string; giai: string;
  /** Hình của RIÊNG ví dụ này (URL lưu DB). Ví dụ hình học không đọc được nếu thiếu. */
  anh?: string;
  /** Mô tả hình AI đề xuất — chỉ có ở ví dụ THẬT SỰ cần hình. Không hiện cho HS. */
  anh_prompt?: string;
  /** URL đã ký, chỉ để xem trong trình soạn (không gửi khi lưu). */
  anh_xem?: string;
}
export interface CmsQuiz { q: string; o: string[]; a: number; lv: string; giai?: string }
/** Lời nhắc chủ động của trợ lý ở một mốc trong bài (sinh sẵn, cache ở topic_content). */
export interface CmsNhac { moc: string; hoi: string; dap: string[]; dung: number; giai: string }
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
  nhac: CmsNhac[];
  day: CmsDay | null;
  nguon: string | null;
  // 4 phần nội dung mới + bố cục (REQ §1.2)
  khoi_dong?: string;
  hoat_dong?: string;
  luyen_tap?: string;
  bai_tap?: string;
  bo_cuc?: CmsPhan[];
  trang_thai: string;
  completeness: CmsCompleteness;
}

/** Kết quả Kiểm tra nhanh của 1 học sinh (GET /admin/users/{id}/result). */
export interface KetQuaLan {
  topic_id: number; ten: string; mach: string;
  diem: number; tong: number; dat: boolean; phan_tram: number; luc: string;
  /** nhanh = Kiểm tra nhanh của đơn vị · on_tap = một mảnh đề ôn tập cả mạch. */
  nguon: "nhanh" | "on_tap";
}
export interface KetQuaDonVi {
  topic_id: number; ten: string; mach: string;
  /** Thời gian học đơn vị này (phút) + số phiên + lần học gần nhất. */
  phut: number; so_phien: number; lan_cuoi: string | null;
  /** Nguồn thật của "đã học tới đâu" — CÙNG giá trị phía học sinh thấy. */
  trang_thai: "dat" | "dang" | "chua";
  so_lan: number; so_lan_on_tap: number;
  /** null = chưa làm Kiểm tra nhanh của đơn vị này lần nào. */
  tot_nhat: number | null; gan_nhat: number | null;
}
/** Cùng shape với /me/thoi-gian phía học sinh — dùng chung service nên không lệch. */
export interface ThoiGianKQ {
  hom_nay_phut: number; bay_ngay_phut: number; tong_phut: number; so_phien: number;
  muc_tieu_phut: number; dat_muc_tieu: boolean;
  bieu_do: { ngay: string; phut: number; hom_nay: boolean }[];
}
export interface KetQuaHocSinh {
  hoc_sinh: { id: number; name: string; email: string };
  thoi_gian: ThoiGianKQ;
  so_dat: number; so_dang: number;
  tong_lan: number; tong_lan_on_tap: number; so_lan_dat: number; diem_tb: number;
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

/** Trang Tổng quan chuyên gia (GET /cms/tong-quan · REQ §2.1). */
export interface CmsTongQuan {
  kpi: { tong_dv: number; du_7_phan: number; ycd: number; dang_soan: number; tong_phan: number };
  theo_mach: { mach: string; so_dv: number; da: number; phan_tram: number }[];
  viec_can_lam: { so: number; mo: string; di: string }[];
}

/** Một phần trong bố cục 7 phần (CMS §2.2). */
export interface CmsPhan { id: string; ten: string; em: string; cot: string | null; an: boolean }

/** §2.3 Cây danh mục. */
export interface DmDonVi {
  topic_id: number; ten: string; da_soan: number; tong_phan: number; ycd: number;
  tinh_trang: "du" | "dang" | "chua"; trang_thai: string;
}
export interface DmMach {
  mach: string; so_dv: number; dv: DmDonVi[];
  on_tap: { pham_vi: string; gia_tri: string; so_cau: number };
}
export interface DmHocKy {
  hoc_ky: string; mach: DmMach[];
  on_tap_ky: { pham_vi: string; gia_tri: string; so_cau: number };
}
/** §2.4 Kho SGK. */
export interface KhoSgk {
  kpi: { so_sach: number; so_trang: number; so_doan: number; pt_dan_nguon: number };
  kho_loi: boolean;
  /** Qdrant nối được nhưng chưa có collection — kho rỗng, không phải lỗi. */
  kho_trong?: boolean;
  sach: { id: number; ten: string; mon: string; khoi: string; tap: string | null; source_ref: string }[];
}
/** §2.5 Đối chiếu ma trận. */
export interface MaTran {
  tong: { khop: number; xem_lai: number; chua_gan: number; chua_do: number };
  /** Đơn vị do lần nạp ma trận TỰ TẠO — tên lấy thô từ .docx, phải rà lại. */
  tu_ma_tran: { topic_id: number; ten: string; mach: string }[];
  ti_le: Record<string, number>;
  anh_xa: { muc_do: string; ycd: string; don_vi: string; mach: string;
            ten_nguon: string | null; lech_ten: boolean;
            diem: number | null; loai: string | null }[];
  so_dong: number;
}

/** §3.5 Ôn tập chương / cuối kỳ (GET /on-tap) — CMS xem thử phạm vi. */
export interface OnTap {
  pham_vi: string; gia_tri: string; so_bai: number; chua_xong: number;
  bai: { topic_id: number; ten: string; mach: string; trang_thai: string; co_noi_dung: boolean }[];
  can_nho: { topic_id: number; ten: string; y: string }[];
  ycd: number; so_cau_de: number;
}

/** Một bản đơn vị kiến thức trong nhóm trùng tên (REQ §2.3). */
export interface DmBan {
  id: number;
  don_vi_kien_thuc: string;
  mach_noi_dung: string;
  hoc_ky: string | null;
  tu_ma_tran: boolean;
  trang_thai: string | null;
  co_noi_dung: boolean;
}
export interface DmNhom { giu: DmBan; bo: DmBan[] }
/** Cặp NGHI trùng: điểm giống + kiểu + cờ mất bài. Không bao giờ gộp hàng loạt. */
export interface DmNghi extends DmNhom {
  diem: number;
  kieu: "cat_cut" | "gan";
  canh_bao_mat_bai: boolean;
}
export interface DmDich { id: number; ten: string; mach: string; co_noi_dung: boolean }
export interface DmTrung {
  mon: string; khoi: string;
  so_ban_du: number; so_nghi: number; so_chua_co_bai: number;
  chac_chan: DmNhom[];
  nghi: DmNghi[];
  /** Đơn vị do ma trận tạo mà chưa có bài — gộp TAY vào đích tự chọn. */
  chua_co_bai: DmBan[];
  dich: DmDich[];
}

/** §2.4 Nạp sách bằng AI — soát thư mục ảnh trang trước khi nạp. */
export interface SoatSach {
  mon: string; khoi: string; tap: number;
  trang: number[];                 // số trang đã có ảnh
  thieu: number[];                 // khuyết ở GIỮA khoảng đã có
  cho_gan: { ten: string; kb: number }[];   // tệp chưa đoán được số trang
  da_ocr: number[];                // trang đã có cache OCR -> nạp lại gần như miễn phí
  goi_y_thu: number[];             // trang nên đọc thử (rải đều đầu/giữa/cuối)
  da_luu?: { ten: string; so: number | null; ghi_de?: boolean }[];
  cho_gan_moi?: { ten: string }[];
  bo_qua?: { ten: string; ly_do: string }[];
  ghi_de?: number[];
}
export interface TrangDocThu {
  so: number; md?: string; chu?: number;
  co_cong_thuc?: boolean;
  co_chuong?: boolean; co_bai?: boolean; it_chu?: boolean; loi?: string;
}
export interface DocThu {
  trang: TrangDocThu[]; so_trang: number;
  so_cong_thuc: number; so_it_chu: number; so_loi: number; so_co_bai: number;
}
export interface BookJob {
  id: number; mon: string; khoi: string; tap: number; sach: string;
  trang_thai: "cho" | "dang" | "tam_dung" | "xong" | "loi";
  buoc: "doc" | "cat_doan" | "ghi_kho";
  trang: number[]; trang_xong: number[];
  trang_loi: { so: number; ly_do: string }[];
  trang_dang: number | null;
  trang_soat: { so: number; ly_do: string; chu: number }[];
  so_trang_co_bai: number; so_doan: number;
  tong: number; da_xong: number;
  loi: string | null; tao_luc: string | null;
  canh_bao?: string;
}
