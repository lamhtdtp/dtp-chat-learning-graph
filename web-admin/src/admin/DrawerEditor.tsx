import { useEffect, useRef, useState } from "react";
import {
  ApiError, cmsAiIngest, cmsGenerateQuiz, cmsGetTopic, cmsSaveTopic, cmsUploadVideo, tokenStore,
} from "../api";
import type { CmsMedia, CmsQuiz, CmsTopic, CmsViDu } from "../types";

const STATUS: [string, string][] = [["draft", "● Nháp"], ["review", "● Chờ duyệt"], ["published", "● Đã xuất bản"]];
const LV: Record<string, string> = { de: "Dễ", trung_binh: "TB", kho: "Khó" };

interface Draft {
  khai_niem: string; minh_hoa: CmsMedia[]; vi_du: CmsViDu[];
  day: { muc_tieu: string; thoi_luong: string; luu_y: string };
  nguon: string; trang_thai: string;
}
function toDraft(t: CmsTopic): Draft {
  return {
    khai_niem: t.khai_niem,
    minh_hoa: t.minh_hoa.map((m) => ({ ...m })),
    vi_du: t.vi_du.map((e) => ({ ...e })),
    day: { muc_tieu: t.day?.muc_tieu ?? "", thoi_luong: t.day?.thoi_luong ?? "", luu_y: t.day?.luu_y ?? "" },
    nguon: t.nguon ?? "",
    trang_thai: t.trang_thai === "chua_bien_soan" ? "draft" : t.trang_thai,
  };
}
function completeness(d: Draft, quiz: CmsQuiz[]): number {
  return [!!d.khai_niem.trim(), d.minh_hoa.length > 0, d.vi_du.length > 0, quiz.length > 0].filter(Boolean).length;
}

export function DrawerEditor({ topicId, initMode, onClose, onSaved, toast }: {
  topicId: number; initMode: "edit" | "preview";
  onClose: () => void; onSaved: () => void; toast: (m: string) => void;
}) {
  const [topic, setTopic] = useState<CmsTopic | null>(null);
  const [d, setD] = useState<Draft | null>(null);
  const [quiz, setQuiz] = useState<CmsQuiz[]>([]);
  const [mode, setMode] = useState<"edit" | "preview">(initMode);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handle = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); location.reload(); return; }
    setErr(e instanceof ApiError ? e.message : "Lỗi kết nối");
  };
  useEffect(() => {
    cmsGetTopic(topicId).then((t) => { setTopic(t); setD(toDraft(t)); setQuiz(t.quiz); }).catch(handle);
  }, [topicId]);

  const patch = (p: Partial<Draft>) => setD((s) => (s ? { ...s, ...p } : s));

  const save = async () => {
    if (!d) return;
    setBusy("save");
    try {
      await cmsSaveTopic(topicId, {
        khai_niem: d.khai_niem, minh_hoa: d.minh_hoa, vi_du: d.vi_du,
        day: { muc_tieu: d.day.muc_tieu, thoi_luong: d.day.thoi_luong, luu_y: d.day.luu_y },
        nguon: d.nguon || null, trang_thai: d.trang_thai,
      });
      toast("Đã lưu nội dung"); onSaved(); onClose();
    } catch (e) { handle(e); } finally { setBusy(null); }
  };
  const aiIngest = async () => {
    if (!d) return;
    setBusy("ai");
    try {
      const dr = await cmsAiIngest(topicId, d.nguon);
      patch({ khai_niem: dr.khai_niem || d.khai_niem, vi_du: dr.vi_du.length ? dr.vi_du : d.vi_du });
      toast("AI đã gợi ý nội dung");
    } catch (e) { handle(e); } finally { setBusy(null); }
  };
  const genQuiz = async () => {
    setBusy("quiz");
    try { const r = await cmsGenerateQuiz(topicId); setQuiz(r.quiz); toast(`Đã sinh ${r.so_cau} câu`); }
    catch (e) { handle(e); } finally { setBusy(null); }
  };
  const upload = async (f: File) => {
    setBusy("video");
    try { const r = await cmsUploadVideo(topicId, f, "Video minh họa"); patch({ minh_hoa: r.minh_hoa }); toast("Đã tải video"); }
    catch (e) { handle(e); } finally { setBusy(null); if (fileRef.current) fileRef.current.value = ""; }
  };

  const addImg = () => d && patch({ minh_hoa: [...d.minh_hoa, { type: "image", url: "", caption: "" }] });
  const rmMedia = (i: number) => d && patch({ minh_hoa: d.minh_hoa.filter((_, j) => j !== i) });
  const setMedia = (i: number, p: Partial<CmsMedia>) => d && patch({ minh_hoa: d.minh_hoa.map((m, j) => j === i ? { ...m, ...p } : m) });
  const addVd = () => d && patch({ vi_du: [...d.vi_du, { de: "", giai: "" }] });
  const rmVd = (i: number) => d && patch({ vi_du: d.vi_du.filter((_, j) => j !== i) });
  const setVd = (i: number, p: Partial<CmsViDu>) => d && patch({ vi_du: d.vi_du.map((e, j) => j === i ? { ...e, ...p } : e) });

  const dn = d ? completeness(d, quiz) : 0;

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Trình soạn nội dung">
        <div className="dw-h">
          <div style={{ flex: 1 }}>
            <div className="eyebrow">{topic ? `${topic.mach}` : "Đang tải…"}</div>
            <h2>{topic?.dv ?? ""}</h2>
          </div>
          <button className="dw-close" type="button" onClick={onClose} aria-label="Đóng">✕</button>
        </div>

        <div className="dw-sub">
          <div className="seg">
            <button className={mode === "edit" ? "on" : ""} type="button" onClick={() => setMode("edit")}>✍️ Biên soạn</button>
            <button className={mode === "preview" ? "on" : ""} type="button" onClick={() => setMode("preview")}>👁 Xem trước</button>
          </div>
          {d && (
            <select className="stsel" value={d.trang_thai} onChange={(e) => patch({ trang_thai: e.target.value })}>
              {STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          )}
        </div>

        <div className="dw-body">
          {err && <div className="warn-box" style={{ marginBottom: 14 }}>⚠️ {err}</div>}
          {!d || !topic ? <div style={{ color: "var(--ink-3)" }}>Đang tải…</div>
            : mode === "edit" ? (
              <>
                {topic.yeu_cau_can_dat.length > 0 && (
                  <div className="esec">
                    <div className="esec-h"><span className="n">🎯</span> Yêu cầu cần đạt (ma trận)</div>
                    {topic.yeu_cau_can_dat.map((y, i) => (
                      <div key={i} style={{ fontSize: 13, color: "var(--ink-2)", padding: "3px 0" }}>
                        <span className="badge-ai" style={{ marginRight: 6 }}>{LV[y.muc_do] ?? "?"}</span>{y.yeu_cau}
                      </div>
                    ))}
                  </div>
                )}
                {/* 1 Khái niệm */}
                <div className="esec">
                  <div className="esec-h"><span className="n">1</span> Khái niệm, định nghĩa
                    <button className="ai-btn" type="button" disabled={busy === "ai"} onClick={aiIngest}>
                      ✨ {busy === "ai" ? "Đang soạn…" : "Gợi ý AI"}
                    </button>
                  </div>
                  <textarea value={d.khai_niem} placeholder="Nhập khái niệm (HTML thuần: <p>, <b>…)"
                    onChange={(e) => patch({ khai_niem: e.target.value })} />
                  <label className="lbl" style={{ marginTop: 8 }}>Tư liệu nguồn cho AI (tuỳ chọn)</label>
                  <input type="text" value={d.nguon} placeholder="Dán trích đoạn SGK…" onChange={(e) => patch({ nguon: e.target.value })} />
                </div>
                {/* 2 Minh hoạ */}
                <div className="esec">
                  <div className="esec-h"><span className="n">2</span> Minh họa</div>
                  {d.minh_hoa.map((m, i) => (
                    <div className="mini-item" key={i}>
                      <div className="mh">{m.type === "video" ? "🎬 Video" : "🖼️ Hình"} {i + 1}
                        {m.source === "expert" && <span className="badge-ai" style={{ marginLeft: 6 }}>chuyên gia</span>}
                        {m.source === "ai" && <span className="badge-ai" style={{ marginLeft: 6 }}>AI</span>}
                        <button className="rm" type="button" onClick={() => rmMedia(i)}>×</button></div>
                      <input type="text" value={m.url ?? ""} placeholder="URL/đường dẫn" onChange={(e) => setMedia(i, { url: e.target.value })} />
                      <input type="text" value={m.caption ?? ""} placeholder="Chú thích" style={{ marginTop: 7 }} onChange={(e) => setMedia(i, { caption: e.target.value })} />
                    </div>
                  ))}
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="add-b" type="button" onClick={addImg}>＋ Thêm ảnh/URL</button>
                    <button className="add-b" type="button" disabled={busy === "video"} onClick={() => fileRef.current?.click()} style={{ flex: "none", width: "auto", padding: "10px 14px" }}>
                      {busy === "video" ? "⬆️ Đang tải…" : "⬆️ Video"}
                    </button>
                    <input ref={fileRef} type="file" accept="video/mp4,video/webm,video/quicktime" style={{ display: "none" }}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} />
                  </div>
                </div>
                {/* 3 Ví dụ */}
                <div className="esec">
                  <div className="esec-h"><span className="n">3</span> Ví dụ</div>
                  {d.vi_du.map((e, i) => (
                    <div className="mini-item" key={i}>
                      <div className="mh">Ví dụ {i + 1}<button className="rm" type="button" onClick={() => rmVd(i)}>×</button></div>
                      <textarea value={e.de} placeholder="Đề bài" style={{ minHeight: 52 }} onChange={(ev) => setVd(i, { de: ev.target.value })} />
                      <textarea value={e.giai} placeholder="Lời giải" style={{ minHeight: 52, marginTop: 7 }} onChange={(ev) => setVd(i, { giai: ev.target.value })} />
                    </div>
                  ))}
                  <button className="add-b" type="button" onClick={addVd}>＋ Thêm ví dụ</button>
                </div>
                {/* 4 Kiểm tra nhanh */}
                <div className="esec">
                  <div className="esec-h"><span className="n">4</span> Bài kiểm tra nhanh</div>
                  <div className="locked"><span className="lk">🔒</span><div><b>Sinh tự động theo ma trận đặc tả.</b><br /><span style={{ fontSize: 12 }}>Bám yêu cầu cần đạt + mức độ — không nhập tay.</span></div></div>
                  {quiz.map((q, i) => (
                    <div className="quiz-mini" key={i}>
                      <div className="qc">Câu {i + 1}. {q.q} <span className="badge-ai">{LV[q.lv] ?? "?"}</span></div>
                      <ol>{q.o.map((op, oi) => <li key={oi} className={oi === q.a ? "ok" : ""}>{op}</li>)}</ol>
                    </div>
                  ))}
                  <button className="add-b" type="button" disabled={busy === "quiz"} onClick={genQuiz} style={{ marginTop: 7 }}>
                    {busy === "quiz" ? "🤖 Đang sinh…" : (quiz.length ? "🔄 Sinh lại theo ma trận" : "🤖 Sinh bài kiểm tra")}
                  </button>
                </div>
                {/* 5 Hướng dẫn dạy */}
                <div className="esec">
                  <div className="esec-h"><span className="n">🎓</span> Hướng dẫn giảng dạy</div>
                  <textarea value={d.day.muc_tieu} placeholder="Mục tiêu" style={{ minHeight: 52 }} onChange={(e) => patch({ day: { ...d.day, muc_tieu: e.target.value } })} />
                  <input type="text" value={d.day.thoi_luong} placeholder="Thời lượng (vd 1 tiết)" style={{ marginTop: 8 }} onChange={(e) => patch({ day: { ...d.day, thoi_luong: e.target.value } })} />
                  <textarea value={d.day.luu_y} placeholder="Lỗi thường gặp / lưu ý" style={{ minHeight: 52, marginTop: 8 }} onChange={(e) => patch({ day: { ...d.day, luu_y: e.target.value } })} />
                </div>
              </>
            ) : (
              <div className="pv">
                <div className="pv-crumb">{topic.mach} › đơn vị kiến thức</div>
                <div className="pv-title">{topic.dv}</div>
                <div className="pv-sec"><h4>📖 Khái niệm</h4><div className="bd" dangerouslySetInnerHTML={{ __html: d.khai_niem || "(chưa có nội dung)" }} /></div>
                <div className="pv-sec"><h4>🎬 Minh họa</h4><div className="pv-media">
                  {d.minh_hoa.length ? d.minh_hoa.map((m, i) => <div className="pv-chip" key={i}>{m.type === "video" ? "🎬 " : "🖼️ "}{m.caption || "(media)"}</div>) : <div className="pv-chip">(chưa có)</div>}
                </div></div>
                <div className="pv-sec"><h4>✏️ Ví dụ</h4><div className="bd">{d.vi_du.length ? d.vi_du.map((e, i) => `Ví dụ ${i + 1}. ${e.de}${e.giai ? "\n→ " + e.giai : ""}`).join("\n\n") : "(chưa có)"}</div></div>
                <div className="pv-sec"><h4>✅ Kiểm tra nhanh</h4><div className="bd">{quiz.length ? `${quiz.length} câu trắc nghiệm (sinh theo ma trận)` : "(chưa sinh)"}</div></div>
              </div>
            )}
        </div>

        <div className="dw-foot">
          <div className="cmini"><span>Hoàn thành</span><div className="tk"><i style={{ width: `${dn / 4 * 100}%` }} /></div><b className="tnum">{dn}/4</b></div>
          <div style={{ flex: 1 }} />
          <button className="btn btn-primary" type="button" disabled={busy === "save" || !d} onClick={save}>
            {busy === "save" ? "Đang lưu…" : "💾 Lưu"}
          </button>
        </div>
      </aside>
    </>
  );
}
