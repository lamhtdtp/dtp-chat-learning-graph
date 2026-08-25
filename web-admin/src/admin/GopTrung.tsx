import { useEffect, useState } from "react";
import { ApiError, cmsDanhMucTrung, cmsGopDonVi } from "../api";
import type { DmBan, DmNghi, DmNhom, DmTrung } from "../types";

const TT: Record<string, string> = { published: "Đã xuất bản", review: "Chờ duyệt", draft: "Nháp" };

function Ban({ b, giu }: { b: DmBan; giu?: boolean }) {
  return (
    <div className={"gt-ban" + (giu ? " giu" : "")}>
      <span className="gt-vt">{giu ? "GIỮ" : "BỎ"}</span>
      <div className="gt-tt">
        <b>{b.don_vi_kien_thuc}</b>
        <span className="gt-phu">
          {b.mach_noi_dung || "(chưa có mạch)"}
          {b.hoc_ky ? ` · ${b.hoc_ky.toUpperCase()}` : " · chưa có học kỳ"}
          {b.tu_ma_tran && " · do nạp ma trận tạo"}
        </span>
      </div>
      <span className={"gt-nd" + (b.co_noi_dung ? " co" : "")}>
        {b.co_noi_dung ? `📄 ${TT[b.trang_thai ?? ""] ?? "có bài"}` : "trống"}
      </span>
    </div>
  );
}

/** Dọn đơn vị kiến thức trùng trong danh mục (REQ §2.3).
 *
 *  Vì sao cần: nạp ma trận từng so tên bằng chuỗi tuyệt đối nên tên lệch một
 *  khoảng trắng là tạo thêm một đơn vị mới — học sinh bấm vào bản rỗng và thấy
 *  "đang được biên soạn" trong khi bài đã soạn nằm ở bản kia. Loader đã sửa để
 *  không đẻ thêm; đây là chỗ dọn phần đã lỡ tạo.
 *
 *  HAI MỨC, cố ý không trộn: bản trùng y hệt tên thì gộp hàng loạt được, còn bản
 *  chỉ GẦN giống phải xác nhận từng cái — trong dữ liệu thật "Hình có tâm đối
 *  xứng" và "Hình có trục đối xứng" giống nhau 0.878 mà là hai bài khác nhau. */
export function GopTrung({ mon, khoi, onXong, toast }: {
  mon: string; khoi: string;
  onXong: () => void;                 // tải lại cây danh mục sau khi gộp
  toast: (m: string) => void;
}) {
  const [d, setD] = useState<DmTrung | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mo, setMo] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  // Cặp nghi trùng đang chờ xác nhận. Gộp là việc khó lùi (dồn ô ma trận, bỏ một
  // bài) nên không cho bấm một nhát là xong.
  const [hoi, setHoi] = useState<number | null>(null);

  const tai = () => {
    cmsDanhMucTrung(mon, khoi).then(setD)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không kiểm tra được danh mục"));
  };
  useEffect(() => { setD(null); setErr(null); setHoi(null); tai(); }, [mon, khoi]);

  const gop = async (giu: number, bo: number[]) => {
    setBusy(giu); setErr(null);
    try {
      const n = (await cmsGopDonVi(giu, bo)).da_doi;
      toast(`Đã gộp ${bo.length} bản trùng`
        + (n.o_ma_tran ? ` · dời ${n.o_ma_tran} ô ma trận` : "")
        + (n.luot_lam_bai ? ` · ${n.luot_lam_bai} lượt làm bài` : ""));
      setHoi(null); tai(); onXong();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không gộp được");
    } finally { setBusy(null); }
  };

  /** CHỈ gộp hàng loạt mức chắc chắn — mức nghi phải người xem từng cặp. */
  const gopHet = async () => {
    for (const g of d?.chac_chan ?? []) await gop(g.giu.id, g.bo.map((b) => b.id));
  };

  if (err && !d) return <div className="warn-box">⚠️ {err}</div>;
  if (!d || (!d.so_ban_du && !d.so_nghi && !d.so_chua_co_bai)) return null;

  const Nhom = ({ g }: { g: DmNhom }) => (
    <div className="gt-nhom">
      <Ban b={g.giu} giu />
      {g.bo.map((b) => <Ban b={b} key={b.id} />)}
      <button className="gt-nut" type="button" disabled={busy !== null}
        onClick={() => gop(g.giu.id, g.bo.map((b) => b.id))}>
        {busy === g.giu.id ? "Đang gộp…" : "Gộp về bản giữ"}
      </button>
    </div>
  );

  const Nghi = ({ g }: { g: DmNghi }) => {
    const dangHoi = hoi === g.giu.id;
    return (
      <div className={"gt-nhom nghi" + (dangHoi ? " hoi" : "")}>
        <div className="gt-diem">
          <span className={"gt-kieu " + g.kieu}>
            {g.kieu === "cat_cut" ? "tên bị cắt cụt" : "chỉ gần giống"}
          </span>
          <span className="tnum">giống {Math.round(g.diem * 100)}%</span>
        </div>
        <Ban b={g.giu} giu />
        {g.bo.map((b) => <Ban b={b} key={b.id} />)}
        {g.canh_bao_mat_bai && (
          <div className="gt-mat">⚠️ Cả hai bản đều đã có bài — gộp sẽ bỏ bài của bản dưới.</div>
        )}
        {dangHoi ? (
          <div className="gt-xn">
            <span>Chắc chắn đây là cùng một đơn vị?</span>
            <button className="gt-nut co" type="button" disabled={busy !== null}
              onClick={() => gop(g.giu.id, g.bo.map((b) => b.id))}>
              {busy === g.giu.id ? "Đang gộp…" : "Đúng, gộp"}
            </button>
            <button className="gt-nut" type="button" onClick={() => setHoi(null)}>Thôi</button>
          </div>
        ) : (
          <button className="gt-nut" type="button" disabled={busy !== null}
            onClick={() => setHoi(g.giu.id)}>Xem xét gộp…</button>
        )}
      </div>
    );
  };

  const Tay = ({ b }: { b: DmBan }) => {
    const [dich, setDich] = useState(0);
    return (
      <div className="gt-nhom tay">
        <Ban b={b} />
        <div className="gt-xn">
          <span>Gộp vào</span>
          <select className="gt-sel" value={dich} onChange={(e) => setDich(+e.target.value)}>
            <option value={0}>— chọn đơn vị đích —</option>
            {d!.dich.map((x) => (
              <option key={x.id} value={x.id}>
                {x.ten}{x.co_noi_dung ? " · có bài" : ""}
              </option>
            ))}
          </select>
          <button className="gt-nut" type="button" disabled={!dich || busy !== null}
            onClick={() => gop(dich, [b.id])}>
            {busy === dich ? "Đang gộp…" : "Gộp"}
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="gt-box">
      <button className="gt-h" type="button" onClick={() => setMo((v) => !v)}>
        <span className="gt-em" aria-hidden>⚠️</span>
        <div className="gt-tt">
          <b>
            {[d.so_ban_du && `${d.so_ban_du} đơn vị trùng`,
              d.so_nghi && `${d.so_nghi} cặp nghi trùng`,
              d.so_chua_co_bai && `${d.so_chua_co_bai} bản dư chưa có bài`,
            ].filter(Boolean).join(" · ") || "Danh mục cần rà lại"}
          </b>
          <span className="gt-phu">
            Học sinh bấm vào bản rỗng sẽ thấy “đang được biên soạn” dù bài đã soạn ở bản kia.
          </span>
        </div>
        <span className="gt-mui">{mo ? "▴" : "▾"}</span>
      </button>

      {mo && (
        <div className="gt-ds">
          {d.chac_chan.length > 0 && (
            <>
              <div className="gt-nhan">Trùng y hệt tên — gộp được ngay</div>
              {d.chac_chan.map((g) => <Nhom g={g} key={g.giu.id} />)}
              <button className="gt-het" type="button" disabled={busy !== null} onClick={gopHet}>
                Gộp tất cả {d.chac_chan.length} nhóm trùng y hệt
              </button>
            </>
          )}
          {d.nghi.length > 0 && (
            <>
              <div className="gt-nhan">
                Nghi trùng — bạn xác nhận từng cặp
                <span className="gt-phu"> (tên gần giống không chắc là cùng bài)</span>
              </div>
              {d.nghi.map((g) => <Nghi g={g} key={`${g.giu.id}-${g.bo[0].id}`} />)}
            </>
          )}
          {d.chua_co_bai.length > 0 && (
            <>
              <div className="gt-nhan">
                Do nạp ma trận tạo, chưa có bài
                <span className="gt-phu"> (tên khác hẳn nên không gợi ý được — chọn đích rồi gộp)</span>
              </div>
              {d.chua_co_bai.map((b) => <Tay b={b} key={b.id} />)}
            </>
          )}
          {err && <div className="gt-loi">⚠️ {err}</div>}
        </div>
      )}
    </div>
  );
}
