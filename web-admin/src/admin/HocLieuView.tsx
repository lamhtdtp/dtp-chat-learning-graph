import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError, hocLieuDs, hocLieuMaKeTiep, hocLieuSua, hocLieuThem, hocLieuVideoNoiBo, hocLieuXoa,
  hocLieuYcd, tokenStore,
} from "../api";
import type {
  HocLieu, HocLieuNhap, LoaiHocLieu, MucYcdHocLieu, VideoNoiBo,
} from "../types";

const LOAI: Record<LoaiHocLieu, string> = {
  VIDEO: "Video", SGK: "SGK", SBT: "SBT", BTTC: "Bài tập thực chiến",
};
const MUC_DICH = { on_lai: "Ôn lại", cung_co: "Củng cố" } as const;
const TRONG: HocLieuNhap = {
  ma: "", loai: "VIDEO", nhan: "", url: "", muc_dich: "on_lai", ycd: "", qid: "", option_key: "",
};
const laNoiBo = (u: string) => u.startsWith("/video/files/");
const ngayGio = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(+d) ? iso : `${d.toLocaleDateString("vi-VN")} ${d.toLocaleTimeString("vi-VN",
    { hour: "2-digit", minute: "2-digit" })}`;
};

/** Kho học liệu có mã (US-27): video / SGK / SBT / BTTC gắn vào MỘT yêu cầu cần đạt, tuỳ chọn
 *  thu hẹp theo câu và phương án. Học sinh thấy học liệu ở khối "Đề xuất" sau khi nộp bài. */
export function HocLieuView({ toast, onLogout }: { toast: (m: string) => void; onLogout: () => void }) {
  const [ds, setDs] = useState<HocLieu[] | null>(null);
  const [ycds, setYcds] = useState<MucYcdHocLieu[]>([]);
  const [videos, setVideos] = useState<VideoNoiBo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [locYcd, setLocYcd] = useState("");
  const [locLoai, setLocLoai] = useState("");
  const [q, setQ] = useState("");
  // null = đóng; {id: null} = thêm mới; {id: n} = sửa.
  const [form, setForm] = useState<{ id: number | null; ma: string } | null>(null);
  const [xoa, setXoa] = useState<HocLieu | null>(null);

  const xu401 = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); onLogout(); return true; }
    return false;
  };
  const tai = () => hocLieuDs({ ycd: locYcd, loai: locLoai, q: q.trim() })
    .then((r) => { setDs(r.hoc_lieu); setErr(null); })
    .catch((e) => { if (!xu401(e)) setErr(e instanceof ApiError ? e.message : "Không kết nối được máy chủ"); });

  useEffect(() => {
    hocLieuYcd().then((r) => setYcds(r.ycd)).catch(xu401);
    hocLieuVideoNoiBo().then((r) => setVideos(r.video)).catch(xu401);
  }, []); // eslint-disable-line
  // Gõ tìm kiếm thì chờ một nhịp, khỏi gọi máy chủ mỗi phím.
  useEffect(() => {
    const t = window.setTimeout(() => { void tai(); }, q ? 250 : 0);
    return () => window.clearTimeout(t);
  }, [locYcd, locLoai, q]); // eslint-disable-line

  const dongXoa = async () => {
    if (!xoa) return;
    try { await hocLieuXoa(xoa.id); toast(`Đã xoá ${xoa.ma}`); setXoa(null); void tai(); }
    catch (e) { if (!xu401(e)) { setXoa(null); setErr(e instanceof ApiError ? e.message : "Không xoá được"); } }
  };

  return (
    <>
      <div className="page-head">
        <div><h1>Kho học liệu</h1>
          <div className="ps">Video, trang SGK, SBT, bài tập thực chiến gắn vào yêu cầu cần đạt. Học sinh làm sai chỗ nào
            thì thấy đúng học liệu của chỗ đó ở khối "Đề xuất" sau khi nộp bài.</div></div>
        <div className="sp" />
        <button className="btn btn-primary" type="button" onClick={() => setForm({ id: null, ma: "" })}>+ Thêm học liệu</button>
      </div>

      <div className="panel hl-loc">
        <label>Yêu cầu cần đạt
          <select value={locYcd} onChange={(e) => setLocYcd(e.target.value)} aria-label="Lọc theo yêu cầu cần đạt">
            <option value="">Tất cả</option>
            {ycds.map((y) => <option key={y.ycd_key} value={y.ycd}>{y.ycd.length > 90 ? y.ycd.slice(0, 90) + "…" : y.ycd}</option>)}
          </select>
        </label>
        <label>Loại
          <select value={locLoai} onChange={(e) => setLocLoai(e.target.value)} aria-label="Lọc theo loại">
            <option value="">Tất cả</option>
            {(Object.keys(LOAI) as LoaiHocLieu[]).map((l) => <option key={l} value={l}>{LOAI[l]}</option>)}
          </select>
        </label>
        <label>Tìm mã / nhãn
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="VD-TO06-001 hoặc từ trong nhãn" />
        </label>
      </div>

      {err && <div className="warn-box" role="alert" style={{ marginBottom: 14 }}>⚠️ {err}</div>}
      <div className="panel">
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead><tr>
              <th>Mã</th><th>Loại</th><th>Nhãn</th><th>Phạm vi gắn</th><th>Mục đích</th><th>Tạo / sửa</th><th />
            </tr></thead>
            <tbody>
              {ds?.map((h) => (
                <tr key={h.id}>
                  <td><span className="dg-ma-nho hl-ma">{h.ma}</span></td>
                  <td>{LOAI[h.loai]}</td>
                  <td>
                    <div className="u-name">{h.nhan}</div>
                    <div className="u-mach hl-url" title={h.url}>{laNoiBo(h.url) ? "🎬 Video nội bộ" : h.url}</div>
                  </td>
                  <td>
                    <div className="u-name" style={{ fontWeight: 600 }}>{h.pham_vi}</div>
                    <div className="u-mach" title={h.ycd}>{h.ycd}</div>
                  </td>
                  <td><span className={"pill " + (h.muc_dich === "on_lai" ? "p-duyet" : "p-xong")}>{MUC_DICH[h.muc_dich]}</span></td>
                  <td>
                    <div className="u-mach">Tạo: {h.nguoi_tao || "—"} · {ngayGio(h.tao_luc)}</div>
                    {h.sua_luc && <div className="u-mach">Sửa: {h.nguoi_sua || "—"} · {ngayGio(h.sua_luc)}</div>}
                  </td>
                  <td><div className="row-act">
                    <button className="act txt" type="button" onClick={() => setForm({ id: h.id, ma: h.ma })}>✏️ Sửa</button>
                    <button className="act txt hl-xoa" type="button" onClick={() => setXoa(h)}>🗑 Xoá</button>
                  </div></td>
                </tr>
              ))}
              {ds && ds.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--ink-3)", padding: 28 }}>
                  {locYcd || locLoai || q ? "Không có học liệu nào khớp bộ lọc." : 'Chưa có học liệu nào. Bấm "Thêm học liệu".'}</td></tr>
              )}
              {!ds && !err && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--ink-3)", padding: 28 }}>Đang tải…</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {form && (
        <FormHocLieu id={form.id} ycds={ycds} videos={videos} cu={ds?.find((x) => x.id === form.id) ?? null}
          onDong={() => setForm(null)} xu401={xu401}
          onXong={(ma, moi) => { setForm(null); toast(moi ? `Đã thêm ${ma}` : `Đã lưu ${ma}`); void tai(); }} />
      )}

      {xoa && (
        <>
          <div className="scrim" onClick={() => setXoa(null)} />
          <div className="dg-modal" role="alertdialog" aria-label="Xoá học liệu">
            <h3>Xoá học liệu {xoa.ma}?</h3>
            <p>Học sinh không còn thấy học liệu này ở bất kỳ kết quả nào, kể cả bài đã nộp từ trước.
              <b> Mã {xoa.ma} không dùng lại được</b> sau khi xoá.</p>
            <div className="dg-act">
              <button className="btn btn-primary" type="button" onClick={() => void dongXoa()}>Xoá</button>
              <button className="btn btn-ghost" type="button" onClick={() => setXoa(null)}>Không xoá</button>
            </div>
          </div>
        </>
      )}
    </>
  );
}

/** Biểu mẫu thêm / sửa. Lỗi (mã trùng, đường dẫn sai…) chỉ hiện thông báo — MỌI ô giữ nguyên để
 *  sửa tiếp, không bắt nhập lại từ đầu. Mã không sửa được sau khi tạo. */
function FormHocLieu({ id, cu, ycds, videos, onDong, onXong, xu401 }: {
  id: number | null; cu: HocLieu | null; ycds: MucYcdHocLieu[]; videos: VideoNoiBo[];
  onDong: () => void; onXong: (ma: string, moi: boolean) => void; xu401: (e: unknown) => boolean;
}) {
  const [v, setV] = useState<HocLieuNhap>(cu ? {
    ma: cu.ma, loai: cu.loai, nhan: cu.nhan, url: cu.url, muc_dich: cu.muc_dich, ycd: cu.ycd,
    qid: cu.qid ?? "", option_key: cu.option_key ?? "",
  } : TRONG);
  const [nguon, setNguon] = useState<"noi_bo" | "ngoai">(cu && laNoiBo(cu.url) ? "noi_bo" : "ngoai");
  const [dang, setDang] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const daGoMa = useRef(!!cu);
  const sua = id !== null;
  const set = <K extends keyof HocLieuNhap>(k: K, x: HocLieuNhap[K]) => setV((s) => ({ ...s, [k]: x }));

  // Gợi ý mã kế tiếp theo loại — chỉ khi thêm mới và người dùng chưa tự gõ mã (được gõ đè).
  useEffect(() => {
    if (sua || daGoMa.current) return;
    let huy = false;
    hocLieuMaKeTiep(v.loai).then((r) => { if (!huy && !daGoMa.current) set("ma", r.ma); }).catch(() => { /* gợi ý phụ */ });
    return () => { huy = true; };
  }, [v.loai, sua]); // eslint-disable-line

  const coPhuongAn = !!v.option_key.trim();
  const luu = async (e: React.FormEvent) => {
    e.preventDefault();
    if (dang) return;
    setDang(true); setLoi(null);
    try {
      const r = sua ? await hocLieuSua(id!, v) : await hocLieuThem(v);
      onXong(r.ma, !sua);
    } catch (err) {
      if (xu401(err)) return;
      setLoi(err instanceof ApiError && typeof err.message === "string" ? err.message : "Không lưu được, thử lại nhé");
    } finally { setDang(false); }
  };

  const theoDonVi = useMemo(() => {
    const m = new Map<string, MucYcdHocLieu[]>();
    for (const y of ycds) m.set(y.don_vi, [...(m.get(y.don_vi) ?? []), y]);
    return [...m.entries()];
  }, [ycds]);

  return (
    <>
      <div className="scrim" onClick={() => !dang && onDong()} />
      <aside className="drawer dg-drawer" role="dialog" aria-label={sua ? "Sửa học liệu" : "Thêm học liệu"}>
        <div className="dw-h">
          <div style={{ flex: 1 }}>
            <div className="eyebrow">Kho học liệu</div>
            <h2>{sua ? `Sửa ${v.ma}` : "Thêm học liệu"}</h2>
          </div>
          <button className="dw-close" type="button" onClick={onDong} aria-label="Đóng">✕</button>
        </div>
        <form className="dw-body hl-form" noValidate onSubmit={(e) => void luu(e)}>
          {loi && <div className="warn-box" role="alert">⚠️ {loi}</div>}

          <label>Mã học liệu
            <input type="text" value={v.ma} disabled={sua} maxLength={64} autoComplete="off" spellCheck={false}
              onChange={(e) => { daGoMa.current = true; set("ma", e.target.value); }} aria-label="Mã học liệu" />
            <small>{sua ? "Mã không sửa được sau khi tạo." : "Gợi ý theo loại, được gõ đè. Không phân biệt hoa thường; mã đã dùng (kể cả đã xoá) không dùng lại."}</small>
          </label>

          <label>Loại
            <select value={v.loai} onChange={(e) => set("loai", e.target.value as LoaiHocLieu)}>
              {(Object.keys(LOAI) as LoaiHocLieu[]).map((l) => <option key={l} value={l}>{LOAI[l]}</option>)}
            </select>
          </label>

          <label>Nhãn
            <input type="text" value={v.nhan} maxLength={300} onChange={(e) => set("nhan", e.target.value)}
              placeholder='Ví dụ: "Toán 6 tập 1, trang 24, bài 3" hoặc tiêu đề video' />
            <small>Tối đa 255 ký tự. Hiện nguyên văn cho học sinh.</small>
          </label>

          <fieldset className="hl-nguon">
            <legend>Đường dẫn</legend>
            <div className="hl-radio">
              <label><input type="radio" name="nguon" checked={nguon === "ngoai"} onChange={() => { setNguon("ngoai"); if (laNoiBo(v.url)) set("url", ""); }} /> Link ngoài (http / https)</label>
              <label><input type="radio" name="nguon" checked={nguon === "noi_bo"} onChange={() => { setNguon("noi_bo"); if (!laNoiBo(v.url)) set("url", ""); }} /> Video AI nội bộ</label>
            </div>
            {nguon === "ngoai" ? (
              <input type="text" value={v.url} inputMode="url" autoComplete="off" spellCheck={false}
                onChange={(e) => set("url", e.target.value)} placeholder="https://…" aria-label="Đường dẫn" />
            ) : (
              <select value={v.url} onChange={(e) => { set("url", e.target.value); if (v.loai !== "VIDEO") set("loai", "VIDEO"); }}
                aria-label="Chọn video nội bộ">
                <option value="">— Chọn video đã dựng xong —</option>
                {videos.map((x) => <option key={x.url} value={x.url}>{x.tieu_de}</option>)}
              </select>
            )}
            <small>{nguon === "ngoai" ? "Hệ thống không mở thử link khi lưu." : "Chỉ video đã dựng xong mới chọn được."}</small>
          </fieldset>

          <fieldset className="hl-nguon">
            <legend>Mục đích</legend>
            <div className="hl-radio">
              {(Object.keys(MUC_DICH) as (keyof typeof MUC_DICH)[]).map((m) => (
                <label key={m}><input type="radio" name="muc_dich" checked={v.muc_dich === m}
                  onChange={() => set("muc_dich", m)} /> {MUC_DICH[m]}</label>
              ))}
            </div>
            <small>Ôn lại: hiện khi em làm sai YCCĐ này. Củng cố: hiện khi em đúng nhưng chưa vững. Gắn theo phương án chỉ dùng Ôn lại.</small>
          </fieldset>

          <label>Yêu cầu cần đạt (bắt buộc)
            <select value={v.ycd} onChange={(e) => set("ycd", e.target.value)} aria-label="Yêu cầu cần đạt">
              <option value="">— Chọn từ danh mục —</option>
              {/* Học liệu đã gắn YCCĐ mà ma trận nạp lại làm biến mất: vẫn hiện để không mất lựa chọn khi sửa. */}
              {v.ycd && !ycds.some((y) => y.ycd === v.ycd) && <option value={v.ycd}>{v.ycd}</option>}
              {theoDonVi.map(([dv, ds]) => (
                <optgroup key={dv} label={dv}>
                  {ds.map((y) => <option key={y.ycd_key} value={y.ycd}>{y.ycd}</option>)}
                </optgroup>
              ))}
            </select>
          </label>

          <div className="hl-hai">
            <label>Câu (tuỳ chọn)
              <input type="text" value={v.qid} autoComplete="off" spellCheck={false} placeholder="Mã câu trong kho đề, vd Q26-000004"
                onChange={(e) => { set("qid", e.target.value); if (!e.target.value.trim()) set("option_key", ""); }} />
              <small>Chỉ hiện khi em sai đúng câu này.</small>
            </label>
            <label>Phương án (tuỳ chọn)
              <input type="text" value={v.option_key} maxLength={2} autoComplete="off" disabled={!v.qid.trim()} placeholder="A, B, C…"
                onChange={(e) => set("option_key", e.target.value.toUpperCase())} />
              <small>{v.qid.trim() ? "Chỉ hiện khi em chọn đúng phương án này." : "Chọn câu trước."}</small>
            </label>
          </div>
          {coPhuongAn && v.muc_dich === "cung_co" && (
            <div className="warn-box" role="status">Học liệu gắn theo phương án chỉ dùng mục đích Ôn lại.</div>
          )}

          <div className="dg-act">
            <button className="btn btn-primary" type="submit" disabled={dang}>{dang ? "Đang lưu…" : "Lưu"}</button>
            <button className="btn btn-ghost" type="button" disabled={dang} onClick={onDong}>Huỷ</button>
          </div>
        </form>
      </aside>
    </>
  );
}
