import { useEffect, useRef, useState } from "react";
import type { MyStats, Role } from "../types";

const VAI_TRO: Record<Role, string> = {
  hoc_sinh: "Học sinh",
  giao_vien: "Giáo viên",
  chuyen_gia: "Chuyên gia biên soạn",
  admin: "Quản trị",
};

/** Chữ cái đại diện: lấy TÊN (từ cuối) chứ không lấy họ — "Hồ Thanh Lâm" -> "L".
 *  Người Việt xưng bằng tên, lấy họ thì cả lớp cùng một chữ "N". */
function chuDaiDien(ten: string): string {
  // Không dùng Array.at() — lib TS của dự án dưới ES2022.
  const tu = ten.trim().split(/\s+/).filter(Boolean);
  return (tu.length ? tu[tu.length - 1][0] : "?").toUpperCase();
}

/** Hồ sơ người đang đăng nhập, ở góc phải thanh trên.
 *
 *  Trước đây tên học sinh chỉ nằm trong `title` của nút đăng xuất — không ai
 *  thấy. Gộp luôn đổi giao diện + đăng xuất vào đây để thanh trên bớt nút rời. */
export function ProfileMenu({ name, email, role, stats, themeIcon, themeLabel, onCycleTheme, onLogout,
                              onHoSo, dangOHoSo }: {
  name: string;
  /** Từ /auth/me mà App đã gọi sẵn lúc khôi phục phiên — KHÔNG gọi lại ở đây. */
  email: string;
  role: Role;
  /** Số liệu học tập (đã tải sẵn cho Hero) — dùng lại, không gọi thêm API. */
  stats: MyStats | null;
  themeIcon: string;
  themeLabel: string;
  onCycleTheme: () => void;
  onLogout: () => void;
  /** Mở Hồ sơ học tập (REQ §3.2). */
  onHoSo?: () => void;
  /** Đang ở trang Hồ sơ -> tô sáng mục đang mở. */
  dangOHoSo?: boolean;
}) {
  const [mo, setMo] = useState(false);
  const boc = useRef<HTMLDivElement>(null);

  // Bấm ra ngoài / bấm Esc thì đóng.
  useEffect(() => {
    if (!mo) return;
    const ngoai = (e: PointerEvent) => {
      if (!boc.current?.contains(e.target as Node)) setMo(false);
    };
    const phim = (e: KeyboardEvent) => { if (e.key === "Escape") setMo(false); };
    document.addEventListener("pointerdown", ngoai);
    document.addEventListener("keydown", phim);
    return () => {
      document.removeEventListener("pointerdown", ngoai);
      document.removeEventListener("keydown", phim);
    };
  }, [mo]);

  return (
    <div className="hs-boc" ref={boc}>
      <button className={"hs-nut" + (mo ? " mo" : "")} type="button" onClick={() => setMo((v) => !v)}
        aria-haspopup="menu" aria-expanded={mo}>
        <span className="hs-ava" aria-hidden>{chuDaiDien(name)}</span>
        <span className="hs-ten">{name}</span>
        <svg className="hs-mui" width="13" height="13" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2.4" aria-hidden><path d="M6 9l6 6 6-6" /></svg>
      </button>

      {mo && (
        <div className="hs-menu" role="menu">
          <div className="hs-dau">
            <span className="hs-ava lon" aria-hidden>{chuDaiDien(name)}</span>
            <div className="hs-tt">
              <b>{name}</b>
              <span className="hs-vt">{VAI_TRO[role]}</span>
              <span className="hs-mail" title={email}>{email}</span>
            </div>
          </div>

          {/* Điểm XP đã bỏ khỏi giao diện học sinh: nó là điểm thưởng, không nói
              được em học tới đâu. Thay bằng % yêu cầu cần đạt — thước đo của
              chương trình. Backend vẫn cộng XP (streak dùng chung service). */}
          <div className="hs-so">
            <div><b className="num">{stats?.ycd_phan_tram ?? 0}%</b><span>Yêu cầu cần đạt</span></div>
            <div><b className="num">{stats?.streak ?? 0} 🔥</b><span>Chuỗi ngày</span></div>
            <div><b className="num">{stats?.dat ?? 0}/{stats?.tong ?? 0}</b><span>Đơn vị đạt</span></div>
          </div>

          {/* Thứ tự §3.2: Hồ sơ -> Giao diện -> Đăng xuất. Đóng menu khi chọn. */}
          {onHoSo && (
            <button className={"hs-dong" + (dangOHoSo ? " dang" : "")} type="button" role="menuitem"
              onClick={() => { setMo(false); onHoSo(); }}>
              <span className="ic" aria-hidden>📈</span>
              Hồ sơ học tập của em
            </button>
          )}
          <button className="hs-dong" type="button" role="menuitem" onClick={onCycleTheme}>
            <span className="ic" aria-hidden>{themeIcon}</span>
            Giao diện<span className="hs-phu">{themeLabel}</span>
          </button>
          <button className="hs-dong nguy" type="button" role="menuitem"
            onClick={() => { setMo(false); onLogout(); }}>
            <span className="ic" aria-hidden>⎋</span>
            Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
}
