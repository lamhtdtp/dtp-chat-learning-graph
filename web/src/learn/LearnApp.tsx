import { useEffect, useMemo, useState } from "react";
import {
  ApiError, getCurriculum, getLesson, getMyStats, setProgress, tokenStore,
} from "../api";
import { useTheme } from "../hooks/useTheme";
import type { CurriculumGroup, Lesson, MyStats, Role } from "../types";
import { LessonView } from "./LessonView";
import { useSoDoi } from "./useSoDoi";
import { SlideView } from "./SlideView";

const R = 46;
const CIRC = 2 * Math.PI * R;

// Học kỳ 1 gồm 4 mạch này (theo danh mục mockup); còn lại là HK2. Dùng để chèn
// pill "HỌC KỲ n" trong mục lục — backend không lưu học kỳ nên suy từ tên mạch.
const HK1_MACH = new Set([
  "Số tự nhiên", "Số nguyên", "Các hình phẳng trong thực tiễn", "Tính đối xứng của hình phẳng",
]);

/** Một ô số liệu. Đổi giá trị -> đếm tăng dần + loé sáng + hiện "+n" ngay bên
 *  cạnh, để học sinh thấy công mình vừa bỏ ra được ghi nhận. */
function O({ k, so, dv, duoi, nhan }: {
  k: string; so: number; dv?: string; duoi?: string; nhan: string;
}) {
  const { hien, nhay, delta } = useSoDoi(so);
  return (
    <div className={"stat " + k + (nhay ? " nhay" : "")}>
      <div className="v num">
        {hien}{duoi}
        {dv && <span className="u">{dv}</span>}
        {delta > 0 && <span className="delta">+{delta}</span>}
      </div>
      <div className="l">{nhan}</div>
    </div>
  );
}

function Hero({ stats }: { stats: MyStats | null }) {
  const pct = stats?.current_mach?.phan_tram ?? stats?.overall ?? 0;
  const label = (stats?.current_mach?.mach ?? "Toán 6").toUpperCase();
  const lbl = label.length > 16 ? label.slice(0, 15) + "…" : label;
  return (
    <section className="progress-card" aria-label="Tiến độ học tập">
      <div className="prog-hop">
      <div className="ring">
        <svg width="106" height="106">
          <defs><linearGradient id="rg" x1="0" y1="0" x2="1" y2="1"><stop className="a" offset="0" /><stop className="b" offset="1" /></linearGradient></defs>
          <circle className="track" cx="53" cy="53" r={R} fill="none" strokeWidth="9" />
          <circle className="fill" cx="53" cy="53" r={R} fill="none" stroke="url(#rg)" strokeWidth="9"
            strokeLinecap="round" strokeDasharray={CIRC} strokeDashoffset={CIRC * (1 - pct / 100)} />
        </svg>
        <div className="pct num">{pct}%</div>
      </div>
      <div className="ring-nhan" title={label}>{lbl}</div>
      </div>
      <div className="prog-stats">
        <O k="" so={stats?.dat ?? 0} dv={`/${stats?.tong ?? 0} đơn vị`} nhan="Trong chương trình" />
        <O k="streak" so={stats?.streak ?? 0} duoi=" 🔥" nhan="Chuỗi ngày học" />
        <O k="xp" so={stats?.xp_week ?? 0} dv="XP" nhan="Điểm tuần này" />
      </div>
    </section>
  );
}

export function LearnApp({ name, role, onLogout }: { name: string; role: Role; onLogout: () => void }) {
  const teacher = role === "giao_vien";
  const { cycle, icon, label } = useTheme();
  const [groups, setGroups] = useState<CurriculumGroup[]>([]);
  const [cur, setCur] = useState<number | null>(null);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [stats, setStats] = useState<MyStats | null>(null);
  const [slide, setSlide] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handle = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); onLogout(); return; }
    setErr(e instanceof ApiError ? e.message : "Không kết nối được máy chủ");
  };

  const loadStats = () => getMyStats().then(setStats).catch(() => { /* hero phụ, bỏ qua */ });
  const loadLesson = (id: number) => { setLesson(null); getLesson(id).then(setLesson).catch(handle); };

  const loadCurriculum = (selectDefault: boolean) => {
    getCurriculum().then((g) => {
      setGroups(g);
      if (selectDefault && cur == null) {
        const first = g.flatMap((m) => m.dv).find((d) => d.co_noi_dung) ?? g[0]?.dv[0];
        if (first) { setCur(first.topic_id); loadLesson(first.topic_id); }
      }
    }).catch(handle);
  };
  useEffect(() => { loadCurriculum(true); loadStats(); }, []); // eslint-disable-line

  const openTopic = (id: number) => { setCur(id); setSlide(false); loadLesson(id); };
  const markDone = async () => {
    if (cur == null) return;
    try { await setProgress(cur, "dat"); loadCurriculum(false); loadStats(); } catch (e) { handle(e); }
  };
  const onQuizGraded = () => { loadCurriculum(false); loadStats(); };

  // Thứ tự phẳng để tính trạng thái "tiếp theo" (item ngay sau bài đang học).
  const flat = useMemo(() => groups.flatMap((g) => g.dv), [groups]);
  const nextId = useMemo(() => {
    const i = flat.findIndex((d) => d.topic_id === cur);
    for (let j = i + 1; j < flat.length; j++) if (flat[j].trang_thai !== "dat") return flat[j].topic_id;
    return null;
  }, [flat, cur]);

  const itemClass = (d: { topic_id: number; trang_thai: string }) => {
    if (d.topic_id === cur) return "tp-item current";
    if (d.trang_thai === "dat") return "tp-item done";
    if (d.topic_id === nextId) return "tp-item next";
    return "tp-item";
  };

  const crumb = lesson ? <>{lesson.mach} · <b>{lesson.dv}</b></> : <b>Chọn một bài học</b>;

  return (
    <div className="learn">
      <nav className="nav col">
        <div className="brand">
          <div className="brand-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div><b>Toán 6</b><span>Cùng khám phá</span></div>
        </div>
        <div className="tp-head">
          <div className="tp-title">Danh mục Toán lớp 6</div>
          <div className="tp-sub">Chọn một chủ đề để bắt đầu học</div>
        </div>
        <div className="tp-scroll col">
          {groups.map((g, gi) => {
            const hk = HK1_MACH.has(g.mach) ? 1 : 2;
            const prevHk = gi === 0 ? 0 : (HK1_MACH.has(groups[gi - 1].mach) ? 1 : 2);
            return (
            <div key={g.mach}>
              {hk !== prevHk && <div className="tp-sem">📚 HỌC KỲ {hk}</div>}
              <div className="tp-group">
              <div className="tp-group-title"><span className="em">{g.em}</span> {g.mach.toUpperCase()}</div>
              <div className="tp-items">
                {g.dv.map((d) => (
                  <button key={d.topic_id} type="button" className={itemClass(d)} onClick={() => openTopic(d.topic_id)}>
                    <span className="ic">{d.trang_thai === "dat" ? "✓" : ""}</span>
                    <span className="tx">{d.ten}</span>
                    {d.topic_id === nextId && d.topic_id !== cur && <span className="flag">TIẾP</span>}
                  </button>
                ))}
              </div>
              </div>
            </div>
            );
          })}
        </div>
      </nav>

      <main className="main col">
        <div className="topbar">
          <div className="crumb">{crumb}</div>
          <div className="spacer" />
          {teacher && lesson && (
            <button className="icon-btn" type="button" title={slide ? "Xem bài học" : "Xem slide"}
              onClick={() => setSlide((s) => !s)} aria-label="Đổi bài học/slide">{slide ? "📘" : "🖥️"}</button>
          )}
          <button className="icon-btn" type="button" onClick={cycle} title={`Giao diện: ${label}`} aria-label="Đổi giao diện">{icon}</button>
          <button className="icon-btn" type="button" onClick={onLogout} title={`Đăng xuất (${name})`} aria-label="Đăng xuất">⎋</button>
        </div>

        <Hero stats={stats} />

        {err && <div className="lesson-empty">⚠️ {err}</div>}
        {!err && (slide && lesson
          ? <SlideView lesson={lesson} />
          : lesson
            ? <LessonView lesson={lesson} teacher={teacher} onMarkDone={markDone}
                onQuizGraded={onQuizGraded} />
            : <div className="lesson-empty">Đang tải bài học…</div>)}
      </main>
    </div>
  );
}
