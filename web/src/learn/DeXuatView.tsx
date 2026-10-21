import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ApiError, testThem } from "../api";
import type { DeXuat, MucBaiHoc, MucHocLieu } from "../types";

const IC: Record<string, string> = { VIDEO: "▶️", SGK: "📘", SBT: "📗", BTTC: "🎯" };
const TEN_LOAI: Record<string, string> = { VIDEO: "Video", SGK: "SGK", SBT: "SBT", BTTC: "Bài tập thực chiến" };
const MSG_TEST_THEM = "Chưa tạo được bài mới, em thử lại sau ít phút";

/** Link ngoài chỉ nhận http/https: URL này do người biên soạn nhập nên coi như dữ liệu không
 *  tin cậy — `javascript:` trong `href` là chạy mã khi bấm. Máy chủ đã chặn lúc lưu; đây là lớp thứ hai. */
const linkAnToan = (u: string) => /^https?:\/\//i.test(u);

/** Khung phát NỔI cho video nội bộ. Đóng thì trả tiêu điểm về nút đã mở nó — trang kết quả
 *  không bị cuộn hay dựng lại, nên em về đúng chỗ cũ. */
function KhungPhat({ m, onDong }: { m: MucHocLieu; onDong: () => void }) {
  const [hong, setHong] = useState(false);
  const nutDong = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const truoc = document.activeElement as HTMLElement | null;
    nutDong.current?.focus();
    const phim = (e: KeyboardEvent) => { if (e.key === "Escape") onDong(); };
    document.addEventListener("keydown", phim);
    return () => { document.removeEventListener("keydown", phim); truoc?.focus?.(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Vào thẳng `.learn` (không phải chỗ nút nằm): tổ tiên có transform làm `position: fixed` lệch khỏi màn hình.
  const goc = document.querySelector(".learn") ?? document.body;
  return createPortal(
    <div className="dx-phu" onClick={onDong}>
      <div className="dx-khung" role="dialog" aria-modal="true" aria-label={m.nhan}
        onClick={(e) => e.stopPropagation()}>
        <div className="dx-khung-h">
          <b>{m.nhan}</b>
          <button ref={nutDong} type="button" className="dx-dong" aria-label="Đóng video" onClick={onDong}>✕</button>
        </div>
        {hong ? (
          <div className="dx-video-loi" role="alert">Video tạm thời không phát được</div>
        ) : (
          <video className="dx-video" controls autoPlay playsInline src={m.url}
            controlsList="nodownload" onContextMenu={(e) => e.preventDefault()}
            onError={() => setHong(true)} />
        )}
      </div>
    </div>,
    goc,
  );
}

/** Một học liệu: biểu tượng loại · nhãn · lý do · nút mở. Nhãn render dạng CHỮ (React tự thoát ký
 *  tự) — nhãn do người biên soạn nhập, không bao giờ qua `dangerouslySetInnerHTML`. */
function DongHocLieu({ m, onPhat }: { m: MucHocLieu; onPhat: (m: MucHocLieu) => void }) {
  const noiBo = m.noi_bo;
  return (
    <div className="dx-row" data-ma={m.ma}>
      <span className="ic" aria-hidden title={TEN_LOAI[m.loai]}>{IC[m.loai] ?? "📄"}</span>
      <span className="tx">
        <b>{m.nhan}</b>
        {m.ghi_chu && <span>{m.ghi_chu}</span>}
      </span>
      {noiBo ? (
        <button type="button" className="dx-mo" aria-label={`Phát video: ${m.nhan}`} onClick={() => onPhat(m)}>
          <span aria-hidden>▶</span> Xem
        </button>
      ) : linkAnToan(m.url) ? (
        <a className="dx-mo" href={m.url} target="_blank" rel="noopener noreferrer"
          aria-label={`Mở ${m.nhan} ở tab mới`}>
          <span aria-hidden>↗</span> Mở
        </a>
      ) : null}
    </div>
  );
}

function DongBaiHoc({ b, onMoBai }: { b: MucBaiHoc; onMoBai: (topicId: number, phan?: string) => void }) {
  return (
    <div className="dx-row">
      <span className="ic" aria-hidden>📖</span>
      <span className="tx">
        <b>{b.ten}</b>
        <span>{b.ghi_chu}</span>
      </span>
      <button type="button" className="dx-mo" aria-label={`Mở bài ${b.ten}`}
        onClick={() => onMoBai(b.topic_id, b.phan)}>
        <span aria-hidden>↗</span> Đọc
      </button>
    </div>
  );
}

/** Khối "Đề xuất" — MỘT component dùng chung cho mọi loại bài làm (US-27): Đọc thêm → Video →
 *  Test thêm. Nhóm rỗng không vẽ (không tiêu đề, không khung trống). Máy chủ trả ĐỦ danh sách,
 *  ở đây cắt theo `toi_da*` và cho mở phần còn lại bằng "Xem thêm N". */
export function DeXuatView({ dx, exam, onMoBai, onMoDe }: {
  dx: DeXuat | undefined;
  /** Kỳ của bài vừa làm — Test thêm ghi vào đúng kỳ để hiện trong lịch sử. */
  exam?: string;
  /** Mở bài học tại phần `phan`. */
  onMoBai: (topicId: number, phan?: string) => void;
  /** Mở bài làm mới vừa tạo (Test thêm). */
  onMoDe: (deId: string) => void;
}) {
  const [phat, setPhat] = useState<MucHocLieu | null>(null);
  const [moDoc, setMoDoc] = useState(false);
  const [moVideo, setMoVideo] = useState(false);
  const [dang, setDang] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  if (!dx) return null;
  const { doc_them: doc, video, test_them: tt } = dx;
  if (!dx.loi_khen && !dx.thong_bao && !doc && !video && !tt) return null;

  const taoTestThem = async () => {
    if (!tt) return;
    setDang(true); setLoi(null);
    try {
      const de = await testThem(tt.ar_ids, tt.bo_qid, exam);
      if (!de.de_id) { setLoi(de.thong_bao || MSG_TEST_THEM); return; }
      onMoDe(de.de_id);
    } catch (e) {
      setLoi(e instanceof ApiError && e.status === 503 ? e.message : MSG_TEST_THEM);
    } finally { setDang(false); }
  };

  // "Đọc thêm": các mục bài học (tối đa 5) rồi tới học liệu sách (tối đa 5); phần dư gộp một nút.
  const baiHoc = doc?.bai_hoc ?? [];
  const sach = doc?.hoc_lieu ?? [];
  const nBai = moDoc ? baiHoc.length : Math.min(baiHoc.length, doc?.toi_da_bai_hoc ?? 5);
  const nSach = moDoc ? sach.length : Math.min(sach.length, doc?.toi_da_hoc_lieu ?? 5);
  const anDoc = baiHoc.length - nBai + (sach.length - nSach);

  const vd = video?.hoc_lieu ?? [];
  const nVd = moVideo ? vd.length : Math.min(vd.length, video?.toi_da ?? 3);

  return (
    <section className="dx" aria-label="Đề xuất">
      <h3><span className="hi">💡</span> Đề xuất</h3>

      {dx.loi_khen && <div className="dx-khen" role="status">🎉 {dx.loi_khen}</div>}
      {dx.thong_bao && <div className="dx-tb" role="status">ℹ️ {dx.thong_bao}</div>}

      {doc && (baiHoc.length > 0 || sach.length > 0) && (
        <div className="dx-nhom" data-nhom="doc-them">
          <h4>📚 Đọc thêm</h4>
          <div className="dx-ds">
            {baiHoc.slice(0, nBai).map((b) => <DongBaiHoc key={b.topic_id} b={b} onMoBai={onMoBai} />)}
            {sach.slice(0, nSach).map((m) => <DongHocLieu key={m.ma} m={m} onPhat={setPhat} />)}
          </div>
          {anDoc > 0 && (
            <button type="button" className="dx-them" onClick={() => setMoDoc(true)}>
              Xem thêm {anDoc} học liệu ↓
            </button>
          )}
        </div>
      )}

      {video && vd.length > 0 && (
        <div className="dx-nhom" data-nhom="video">
          <h4>🎬 Video</h4>
          <div className="dx-ds">
            {vd.slice(0, nVd).map((m) => <DongHocLieu key={m.ma} m={m} onPhat={setPhat} />)}
          </div>
          {vd.length > nVd && (
            <button type="button" className="dx-them" onClick={() => setMoVideo(true)}>
              Xem thêm {vd.length - nVd} học liệu ↓
            </button>
          )}
        </div>
      )}

      {tt && (
        <div className="dx-nhom" data-nhom="test-them">
          <h4>🔁 Test thêm</h4>
          <p className="dx-mo-ta">{tt.mo_ta}</p>
          {tt.thieu.map((t) => <p className="dx-thieu" key={t}>{t}</p>)}
          {loi && <div className="ot-loi" role="alert">⚠️ {loi}</div>}
          <button type="button" className="btn btn-primary dx-tt" disabled={dang} onClick={() => void taoTestThem()}>
            {dang ? "Đang tạo bài…" : loi ? "Thử lại" : "Test thêm →"}
          </button>
        </div>
      )}

      {phat && <KhungPhat m={phat} onDong={() => setPhat(null)} />}
    </section>
  );
}
