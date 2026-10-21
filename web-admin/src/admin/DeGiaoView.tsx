import { useEffect, useMemo, useState } from "react";
import {
  ApiError, deGiaoBai, deGiaoChiTiet, deGiaoDong, deGiaoDs, deGiaoKetQua, tokenStore,
} from "../api";
import { SsoTestbankNut } from "./SsoTestbankNut";
import type {
  BaiDeGiao, CauDeGiao, DeGiaoChiTiet, DeGiaoTomTat, KetQuaCauGv, KetQuaDeGiao,
  Role,
} from "../types";

const KY: Record<string, string> = { CK1: "Cuối kỳ 1", CK2: "Cuối kỳ 2" };
const MUC: Record<string, string> = { B: "Biết", H: "Hiểu", V: "Vận dụng" };
const DANG: Record<string, string> = {
  TN1: "Một đáp án", TNN: "Nhiều đáp án", DS: "Đúng / Sai", DSN: "Điền đáp số", TL: "Tự luận",
};

const ngayGio = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(+d) ? iso : `${d.toLocaleDateString("vi-VN")} ${d.toLocaleTimeString("vi-VN",
    { hour: "2-digit", minute: "2-digit" })}`;
};
const soCauChu = (so: number, total: number) => (so < total ? `${so}/${total} câu` : `${so} câu`);

/** Đáp án đúng của từng phương án: TN1/TNN theo khoá, DS theo vị trí ("Đ,S,Đ,S"). */
function phuongAnDung(c: { dang: string; dap_an: string; phuong_an: { key: string }[] }): Set<string> {
  const ds = c.dap_an.split(",").map((x) => x.trim());
  if (c.dang === "DS") {
    return new Set(c.phuong_an.filter((_, i) => ["Đ", "D"].includes((ds[i] ?? "").toUpperCase()))
      .map((p) => p.key));
  }
  return new Set(ds.map((x) => x.toUpperCase()));
}

/** Một câu cho GIÁO VIÊN: có đáp án, lời giải, lý do. Có `chon` thì đánh dấu em chọn gì. */
function CauXem({ c, kq }: { c: CauDeGiao; kq?: KetQuaCauGv }) {
  const dung = phuongAnDung(c);
  const chon = kq ? new Set(kq.chon.split(",").map((x) => x.trim()).filter(Boolean)) : null;
  const coPhuongAn = ["TN1", "TNN", "DS"].includes(c.dang) && c.phuong_an.length > 0;
  // DS: em chọn theo vị trí ("Đ,S,..."), không theo khoá.
  const chonDs = kq && c.dang === "DS" ? kq.chon.split(",").map((x) => x.trim()) : [];
  return (
    <div className="dg-cau">
      <div className="dg-cau-h">
        <b>Câu {c.stt}</b>
        <span className={"dg-muc dg-muc-" + c.muc_do}>{MUC[c.muc_do] ?? c.muc_do}</span>
        <span className="dg-dang">{DANG[c.dang] ?? c.dang}</span>
        {kq && kq.cham_duoc && (
          <span className={"pill " + (kq.dung ? "p-xong" : "p-duyet")}>{kq.dung ? "Đúng" : "Sai"}</span>
        )}
        {kq && !kq.cham_duoc && <span className="pill p-nhap">Không chấm tự động</span>}
      </div>
      <div className="dg-ycd" title="Yêu cầu cần đạt">🎯 {c.ycd}</div>
      {c.cau_dan && <div className="dg-dan">{c.cau_dan}</div>}
      {c.du_kien_html && <div className="dg-dukien" dangerouslySetInnerHTML={{ __html: c.du_kien_html }} />}
      <div className="dg-de" dangerouslySetInnerHTML={{ __html: c.de_html }} />
      {coPhuongAn && (
        <div className="dg-pa">
          {c.phuong_an.map((p, i) => {
            const laDung = dung.has(p.key);
            const emChon = chon ? (c.dang === "DS" ? !!chonDs[i] : chon.has(p.key)) : false;
            const ld = c.ly_do[p.key];
            return (
              <div key={p.key} className={"dg-pa-o" + (laDung ? " dung" : "") + (emChon && !laDung ? " sai" : "")}>
                <span className="dg-k">{p.key}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div dangerouslySetInnerHTML={{ __html: p.html }} />
                  {c.dang === "DS" && <div className="dg-ly">Đáp án: <b>{laDung ? "Đúng" : "Sai"}</b>
                    {kq && <> · em chọn: <b>{chonDs[i] === "Đ" ? "Đúng" : chonDs[i] === "S" ? "Sai" : "bỏ trống"}</b></>}</div>}
                  {ld && <div className="dg-ly">{ld.noi_dung}</div>}
                </div>
                {laDung && <span className="dg-dau" aria-label="đáp án đúng">✓ đáp án</span>}
                {emChon && c.dang !== "DS" && <span className="dg-dau chon">em chọn</span>}
              </div>
            );
          })}
        </div>
      )}
      {!coPhuongAn && (
        <div className="dg-pa-o dung" style={{ marginTop: 8 }}>
          <span>Đáp án: <b dangerouslySetInnerHTML={{ __html: c.dap_an_html || "(không có)" }} /></span>
          {kq && kq.cham_duoc && <span className="dg-ly" style={{ marginLeft: 12 }}>
            Em điền: <b>{kq.chon || "bỏ trống"}</b></span>}
        </div>
      )}
      {c.giai_html && <div className="dg-giai"><b>Lời giải:</b> <span dangerouslySetInnerHTML={{ __html: c.giai_html }} /></div>}
    </div>
  );
}

type Man = { k: "ds" } | { k: "kq"; id: number };

/** Đề giao CŨ của learning (US-26, đã ngừng cấp mã mới — US-26 mục 7): danh sách + bảng kết quả một
 *  mã vẫn xem được, đóng được mã còn mở. Soạn và giao đề mới: nút sang Testbank (US-28). */
export function DeGiaoView({ role, onLogout }: { role: Role; onLogout: () => void }) {
  const [man, setMan] = useState<Man>({ k: "ds" });
  const handle401 = (e: unknown): boolean => {
    if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); onLogout(); return true; }
    return false;
  };
  if (man.k === "kq") {
    return <KetQuaMa id={man.id} onVe={() => setMan({ k: "ds" })} handle401={handle401} />;
  }
  return <DanhSach laAdmin={role === "admin"}
    onMo={(id) => setMan({ k: "kq", id })} handle401={handle401} />;
}

// ── Danh sách ──────────────────────────────────────────────────────────────
function DanhSach({ laAdmin, onMo, handle401 }: {
  laAdmin: boolean; onMo: (id: number) => void; handle401: (e: unknown) => boolean;
}) {
  const [ds, setDs] = useState<DeGiaoTomTat[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    deGiaoDs().then((r) => setDs(r.de_giao)).catch((e) => {
      if (!handle401(e)) setErr(e instanceof ApiError ? e.message : "Không kết nối được máy chủ");
    });
  }, []); // eslint-disable-line
  return (
    <>
      <div className="page-head">
        <div><h1>Đề giao</h1>
          <div className="ps">Đề giao mới tạo trên Testbank. Các đề giao cũ vẫn xem được bên dưới
            {ds ? ` (${ds.length})` : ""}.</div></div>
        <div className="sp" />
        <SsoTestbankNut />
      </div>
      {err && <div className="warn-box" style={{ marginBottom: 14 }}>⚠️ {err}</div>}
      <div className="panel">
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead><tr>
              <th>Mã</th><th>Kỳ</th><th>Số câu</th><th>Ngày tạo</th><th>Trạng thái</th>
              <th className="tnum">Đã nộp</th><th className="tnum">Đang làm</th>
              {laAdmin && <th>Người tạo</th>}<th />
            </tr></thead>
            <tbody>
              {ds?.map((d) => (
                <tr key={d.id} className="dg-hang" onClick={() => onMo(d.id)}>
                  <td><span className="dg-ma-nho">{d.ma}</span></td>
                  <td>{KY[d.exam] ?? d.exam}</td>
                  <td>{soCauChu(d.so_cau, d.total)}</td>
                  <td>{ngayGio(d.created_at)}</td>
                  <td><span className={"pill " + (d.trang_thai === "mo" ? "p-xong" : "p-nhap")}>
                    {d.trang_thai === "mo" ? "Đang mở" : "Đã đóng"}</span></td>
                  <td className="tnum">{d.so_da_nop}</td>
                  <td className="tnum">{d.so_dang_lam}</td>
                  {laAdmin && <td>{d.nguoi_tao}</td>}
                  <td><div className="row-act">
                    <button className="act txt" type="button" onClick={(e) => { e.stopPropagation(); onMo(d.id); }}>
                      📊 Kết quả</button></div></td>
                </tr>
              ))}
              {ds && ds.length === 0 && (
                <tr><td colSpan={laAdmin ? 9 : 8} style={{ textAlign: "center", color: "var(--ink-3)", padding: 28 }}>
                  Chưa có đề giao cũ nào. Thầy cô soạn và giao đề mới trên Testbank.</td></tr>
              )}
              {!ds && !err && <tr><td colSpan={laAdmin ? 9 : 8} style={{ textAlign: "center", color: "var(--ink-3)", padding: 28 }}>
                Đang tải…</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ── Bảng kết quả một mã ────────────────────────────────────────────────────
function KetQuaMa({ id, onVe, handle401 }: {
  id: number; onVe: () => void; handle401: (e: unknown) => boolean;
}) {
  const [de, setDe] = useState<DeGiaoChiTiet | null>(null);
  const [kq, setKq] = useState<KetQuaDeGiao | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [xemDe, setXemDe] = useState(false);
  const [hoi, setHoi] = useState(false);
  const [dangDong, setDangDong] = useState(false);
  const [bai, setBai] = useState<{ ten: string; d: BaiDeGiao | null; loi?: string } | null>(null);

  const tai = () => {
    Promise.all([deGiaoChiTiet(id), deGiaoKetQua(id)]).then(([d, k]) => { setDe(d); setKq(k); setErr(null); })
      .catch((e) => { if (!handle401(e)) setErr(e instanceof ApiError ? e.message : "Không kết nối được máy chủ"); });
  };
  useEffect(tai, [id]); // eslint-disable-line

  const dong = async () => {
    setDangDong(true);
    try { await deGiaoDong(id); setHoi(false); tai(); }
    catch (e) { if (!handle401(e)) { setHoi(false); setErr(e instanceof ApiError ? e.message : "Không đóng được mã"); } }
    finally { setDangDong(false); }
  };

  const moBai = (uid: number, ten: string) => {
    setBai({ ten, d: null });
    deGiaoBai(id, uid).then((d) => setBai({ ten, d }))
      .catch((e) => { if (!handle401(e)) setBai({ ten, d: null, loi: e instanceof ApiError ? e.message : "Lỗi kết nối" }); });
  };

  const cauTheoQid = useMemo(() => new Map((de?.cau ?? []).map((c) => [c.qid, c])), [de]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Kết quả mã <span className="dg-ma-nho dg-lon">{de?.ma ?? "…"}</span></h1>
          {de && <div className="ps">{KY[de.exam]} · {soCauChu(de.so_cau, de.total)} · tạo {ngayGio(de.created_at)}
            {de.dong_luc && <> · đóng {ngayGio(de.dong_luc)}</>}</div>}
        </div>
        <div className="sp" />
        {de && <span className={"pill " + (de.trang_thai === "mo" ? "p-xong" : "p-nhap")}>
          {de.trang_thai === "mo" ? "Đang mở" : "Đã đóng"}</span>}
        <button className="btn btn-ghost" type="button" onClick={() => setXemDe((v) => !v)}>
          {xemDe ? "Ẩn đề" : "Xem đề & đáp án"}</button>
        {de?.trang_thai === "mo" && (
          <button className="btn btn-ghost dg-nguy" type="button" onClick={() => setHoi(true)}>🔒 Đóng mã</button>
        )}
        <button className="btn btn-ghost" type="button" onClick={onVe}>← Danh sách</button>
      </div>
      {err && <div className="warn-box" role="alert" style={{ marginBottom: 14 }}>⚠️ {err}</div>}
      {!kq && !err && <div style={{ color: "var(--ink-3)" }}>Đang tải…</div>}

      {kq && (
        <>
          <div className="kq-tong">
            <div className="kq-o"><b className="tnum">{kq.tong.da_nop}</b><span>đã nộp</span></div>
            <div className="kq-o"><b className="tnum">{kq.tong.dat}</b><span>đạt</span></div>
            <div className="kq-o"><b className="tnum">{kq.tong.dang_lam}</b><span>đang làm</span></div>
          </div>

          <div className="panel" style={{ marginBottom: 20 }}>
            <div className="panel-h"><h3>Học sinh</h3></div>
            {kq.hoc_sinh.length === 0 ? (
              <div className="dg-trong">Chưa có học sinh nào làm đề này</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead><tr><th>Học sinh</th><th>Điểm</th><th>Kết quả</th><th>Nộp lúc</th></tr></thead>
                  <tbody>
                    {kq.hoc_sinh.map((h) => (
                      <tr key={h.user_id} className="dg-hang" onClick={() => moBai(h.user_id, h.ten)}>
                        <td className="u-name">{h.ten}</td>
                        {h.trang_thai === "da_nop" ? (
                          <>
                            <td className="tnum"><b>đúng {h.diem}/{h.tong}</b></td>
                            <td><span className={"pill " + (h.dat ? "p-xong" : "p-duyet")}>
                              {h.dat ? "Đạt" : "Chưa đạt"}</span></td>
                            <td>{ngayGio(h.nop_luc)}</td>
                          </>
                        ) : (
                          <>
                            <td className="kq-mo">—</td>
                            <td><span className="pill p-nhap">
                              {h.trang_thai === "dang_lam" ? "Đang làm" : "Chưa nộp (mã đã đóng)"}</span></td>
                            <td className="kq-mo">—</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {kq.theo_ycd.length > 0 && (
            <div className="panel" style={{ marginBottom: 20 }}>
              <div className="panel-h"><h3>Theo yêu cầu cần đạt</h3></div>
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead><tr><th>Yêu cầu cần đạt</th><th className="tnum">Em đúng hết</th><th className="tnum">Tỉ lệ đúng</th></tr></thead>
                  <tbody>
                    {kq.theo_ycd.map((y) => (
                      <tr key={y.ar_id}>
                        <td><div className="u-name" style={{ fontWeight: 500 }}>{y.ycd}</div>
                          <div className="u-mach">{y.ar_id}</div></td>
                        <td className="tnum">{y.so_hs_dung_het}/{y.so_hs_da_nop} em</td>
                        <td className="tnum"><span className={"pill " + (y.ti_le_dung >= 0.7 ? "p-xong" : "p-duyet")}>
                          {Math.round(y.ti_le_dung * 100)}%</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {xemDe && de && (
        <>
          <div className="esec-h" style={{ marginTop: 6 }}><span className="n">📝</span> Đề học sinh sẽ làm (kèm đáp án)</div>
          {de.cau.map((c) => <CauXem key={c.qid} c={c} />)}
        </>
      )}

      {hoi && (
        <>
          <div className="scrim" onClick={() => !dangDong && setHoi(false)} />
          <div className="dg-modal" role="alertdialog" aria-label="Đóng mã">
            <h3>Đóng mã {de?.ma}?</h3>
            <p>Học sinh chưa mở đề sẽ không vào được nữa, và em đang làm dở bấm nộp sẽ bị từ chối. Em đã nộp vẫn
              xem được kết quả của mình. <b>Mã đã đóng không mở lại được</b> — muốn giao tiếp thì tạo đề giao mới.</p>
            <div className="dg-act">
              <button className="btn btn-primary" type="button" disabled={dangDong} onClick={() => void dong()}>
                {dangDong ? "Đang đóng…" : "Đóng mã"}</button>
              <button className="btn btn-ghost" type="button" disabled={dangDong} onClick={() => setHoi(false)}>
                Không đóng</button>
            </div>
          </div>
        </>
      )}

      {bai && (
        <>
          <div className="scrim" onClick={() => setBai(null)} />
          <aside className="drawer dg-drawer" role="dialog" aria-label="Bài của học sinh">
            <div className="dw-h">
              <div style={{ flex: 1 }}>
                <div className="eyebrow">Bài làm theo mã {de?.ma}</div>
                <h2>{bai.ten}</h2>
              </div>
              <button className="dw-close" type="button" onClick={() => setBai(null)} aria-label="Đóng">✕</button>
            </div>
            <div className="dw-body">
              {bai.loi && <div className="warn-box">⚠️ {bai.loi}</div>}
              {!bai.d && !bai.loi && <div style={{ color: "var(--ink-3)" }}>Đang tải…</div>}
              {bai.d && !bai.d.da_nop && (
                <div className="locked"><span className="lk">⏳</span><b>{bai.d.thong_bao}</b></div>
              )}
              {bai.d && bai.d.da_nop && (
                <>
                  <div className="kq-tong">
                    <div className="kq-o"><b className="tnum">đúng {bai.d.diem}/{bai.d.tong}</b>
                      <span>{bai.d.dat_yeu_cau ? "Đạt" : "Chưa đạt"}</span></div>
                    <div className="kq-o"><b className="tnum">{bai.d.khong_cham}</b><span>câu không chấm tự động</span></div>
                    <div className="kq-o"><b className="tnum" style={{ fontSize: 14 }}>{ngayGio(bai.d.nop_luc)}</b>
                      <span>nộp lúc</span></div>
                  </div>
                  <div className="esec">
                    <div className="esec-h"><span className="n">🎯</span> Theo yêu cầu cần đạt</div>
                    {bai.d.theo_ycd.map((y) => (
                      <div className="kq-lan" key={y.ar_id}>
                        <span className={"pill " + (y.trang === "dat" ? "p-xong" : y.trang === "chua" ? "p-nhap" : "p-duyet")}>
                          {y.dung}/{y.tong}</span>
                        <div style={{ minWidth: 0, flex: 1 }}><div className="u-name" style={{ fontWeight: 500 }}>{y.ycd}</div></div>
                      </div>
                    ))}
                  </div>
                  <div className="esec-h"><span className="n">📝</span> Từng câu</div>
                  {bai.d.cau.map((k) => {
                    const c = cauTheoQid.get(k.qid);
                    return c ? <CauXem key={k.qid} c={{ ...c, ly_do: k.ly_do }} kq={k} /> : null;
                  })}
                </>
              )}
            </div>
          </aside>
        </>
      )}
    </>
  );
}
