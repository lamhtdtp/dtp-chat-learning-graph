import { useState } from "react";
import { ApiError, ssoTestbank } from "../api";

/** "Soạn & giao đề trên Testbank" (US-28): mở Testbank ở TAB MỚI, CMS giữ nguyên.
 *
 *  Tab được mở NGAY trong lúc bấm (còn "cử chỉ người dùng") rồi mới gán địa chỉ khi máy chủ
 *  trả phiếu: gọi `window.open` sau một `await` thì trình duyệt chặn cửa sổ bật lên. Lỗi thì
 *  đóng tab trắng và nói ngay trên CMS — không để thầy cô nhìn một tab trống. */
export function SsoTestbankNut() {
  const [dang, setDang] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  const bam = async () => {
    if (dang) return;
    setDang(true); setLoi(null);
    const tab = window.open("about:blank", "_blank");
    try {
      const r = await ssoTestbank();
      if (tab) tab.location.href = r.url; else window.location.href = r.url;
    } catch (e) {
      tab?.close();
      setLoi(e instanceof ApiError ? e.message : "Chưa kết nối Testbank, thầy cô báo quản trị viên giúp nhé");
    } finally { setDang(false); }
  };

  return (
    <div className="sso-tb">
      <button className="btn btn-primary" type="button" disabled={dang} onClick={() => void bam()}>
        {dang ? "Đang mở Testbank…" : "Soạn & giao đề trên Testbank ↗"}
      </button>
      {loi && <div className="warn-box" role="alert" style={{ marginTop: 8 }}>⚠️ {loi}</div>}
    </div>
  );
}
