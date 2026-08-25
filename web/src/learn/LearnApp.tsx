import { useEffect, useMemo, useState } from "react";
import {
  ApiError, getCurriculum, getLesson, getMyStats, getThoiGian, setProgress, tokenStore,
} from "../api";
import { useTheme } from "../hooks/useTheme";
import type { CurriculumGroup, Lesson, MyStats, Role } from "../types";
import { HoSoView } from "./HoSoView";
import { OnTapView } from "./OnTapView";
import { LessonView } from "./LessonView";
import { usePhanDaDoc } from "./usePhanDaDoc";
import { usePingPhien } from "./usePingPhien";
import { useSoDoi } from "./useSoDoi";
import { SlideView } from "./SlideView";
import { ProfileMenu } from "./ProfileMenu";

const R = 46;
const CIRC = 2 * Math.PI * R;

// Học kỳ 1 gồm 4 mạch này (theo danh mục mockup); còn lại là HK2. Dùng để chèn
// pill "HỌC KỲ n" trong mục lục — backend không lưu học kỳ nên suy từ tên mạch.
const HK1_MACH = new Set([
  "Số tự nhiên", "Số nguyên", "Các hình phẳng trong thực tiễn", "Tính đối xứng của hình phẳng",
]);

/** Một ô số liệu. Đổi giá trị -> đếm tăng dần + loé sáng + hiện "+n" ngay bên
 *  cạnh, để học sinh thấy công mình vừa bỏ ra được ghi nhận. */
function O({ k, so, dv, duoi, nhan, ghi }: {
  k: string; so: number; dv?: string; duoi?: string; nhan: string;
  /** Chú thích nhỏ dưới nhãn, vd "12/34 yêu cầu". */
  ghi?: string;
}) {
  const { hien, nhay, delta } = useSoDoi(so);
  return (
    <div className={"stat " + k + (nhay ? " nhay" : "")}>
      <div className="v num">
        {hien}{duoi}
        {dv && <span className="u">{dv}</span>}
        {delta > 0 && <span className="delta">+{delta}</span>}
      </div>
      <div className="l">{nhan}{ghi && <span className="g">{ghi}</span>}</div>
    </div>
  );
}

function Hero({ stats, mach }: { stats: MyStats | null; mach?: string }) {
  // Vòng tiến độ phải theo MẠCH CỦA BÀI ĐANG MỞ. Trước đây luôn lấy
  // `current_mach` = mạch chưa xong đầu tiên, nên mở bài ở mạch khác rồi quay
  // lại thì vòng vẫn đứng ở % của mạch cũ.
  const cua = mach ? stats?.mach?.find((m) => m.mach === mach) : undefined;
  const hien = cua ?? stats?.current_mach ?? null;
  const pct = hien?.phan_tram ?? stats?.overall ?? 0;
  const label = (hien?.mach ?? "Toán 6").toUpperCase();
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
        {/* Yêu cầu cần đạt thay cho điểm XP: XP là điểm thưởng, còn "đạt bao
            nhiêu % yêu cầu cần đạt" mới là thứ chương trình đo. */}
        <O k="ycd" so={stats?.ycd_phan_tram ?? 0} dv="%" nhan="Yêu cầu cần đạt"
          ghi={stats?.ycd_tong ? `${stats.ycd_dat}/${stats.ycd_tong} yêu cầu` : undefined} />
      </div>
    </section>
  );
}

export function LearnApp({ name, email, role, onLogout }: {
  name: string; email: string; role: Role; onLogout: () => void;
}) {
  const teacher = role === "giao_vien";
  const { cycle, icon, label } = useTheme();
  const [groups, setGroups] = useState<CurriculumGroup[]>([]);
  const [cur, setCur] = useState<number | null>(null);
  // "bai" | "ho_so" — Hồ sơ là một TRANG trong cột giữa, không phải popover, vì
  // nó có biểu đồ + danh sách dài.
  const [trang, setTrang] = useState<"bai" | "ho_so" | "on_tap">("bai");
  // Phạm vi ôn tập đang mở (mạch nào / học kỳ nào).
  const [onTap, setOnTap] = useState<{ pv: "mach" | "hoc_ky"; gt: string; ten: string } | null>(null);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [stats, setStats] = useState<MyStats | null>(null);
  const [slide, setSlide] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Thời gian học HÔM NAY cho chip ⏱ trên thanh trên (mockup có chip này).
  // Số thật từ /me/thoi-gian, không phải đồng hồ đếm phía client.
  const [phutHomNay, setPhutHomNay] = useState<number | null>(null);

  // Ghi thời gian học + phần đã đọc cho bài đang mở (§3.6). Danh sách phần lấy
  // từ `lesson.bo_cuc` — chính thứ đang render, nên "x/y" khớp cái HS thấy.
  const phanDaDoc = usePhanDaDoc(
    (lesson?.bo_cuc ?? []).map((p) => p.id), trang === "bai" && !!lesson);
  usePingPhien(trang === "bai" ? cur : null, phanDaDoc);

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
  const loadThoiGian = () => {
    getThoiGian(1).then((d) => setPhutHomNay(d.hom_nay_phut)).catch(() => setPhutHomNay(null));
  };
  useEffect(() => { loadCurriculum(true); loadStats(); loadThoiGian(); }, []); // eslint-disable-line
  // Học một lúc thì số phải nhích lên; ping phiên chạy mỗi 2 phút nên 60 giây là đủ.
  useEffect(() => {
    const t = window.setInterval(loadThoiGian, 60_000);
    return () => window.clearInterval(t);
  }, []);

  const openTopic = (id: number) => { setCur(id); setSlide(false); setTrang("bai"); loadLesson(id); };
  const moOnTap = (pv: "mach" | "hoc_ky", gt: string, ten: string) => {
    setOnTap({ pv, gt, ten }); setSlide(false); setTrang("on_tap");
  };
  /** Từ Hồ sơ nhảy về bài + cuộn tới đúng phần (nút "Học lại ↗"). */
  const moBaiTuHoSo = (id: number, phan?: string) => {
    openTopic(id);
    if (phan) {
      // Đợi bài render xong mới cuộn — cuộn ngay thì phần tử chưa tồn tại.
      window.setTimeout(() => document
        .getElementById(`phan-${phan}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 800);
    }
  };
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

  // Học kỳ của bài đang mở — để dòng "Lộ trình học" nói đúng kỳ, không cứng "1".
  const hkDangXem = useMemo(() => {
    const g = groups.find((x) => x.dv.some((d) => d.topic_id === cur));
    return g && !HK1_MACH.has(g.mach) ? 2 : 1;
  }, [groups, cur]);

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
        {/* Mockup có khối "Lộ trình học" tách riêng phía trên cây mạch — nó nói
            cho học sinh biết đang ở lộ trình nào, việc mà chip "HỌC KỲ" không nói. */}
        <div className="tp-lotrinh">
          <span className="em" aria-hidden>🧭</span>
          <div><b>Lộ trình học</b><span>Toán 6 · Học kỳ {hkDangXem}</span></div>
        </div>
        <div className="tp-scroll col">
          {groups.map((g, gi) => {
            const hk = HK1_MACH.has(g.mach) ? 1 : 2;
            const prevHk = gi === 0 ? 0 : (HK1_MACH.has(groups[gi - 1].mach) ? 1 : 2);
            return (
            <div key={g.mach}>
              {hk !== prevHk && <div className="tp-sem">📚 HỌC KỲ {hk}</div>}
              <div className="tp-group">
              {(() => {
                const xong = g.dv.filter((d) => d.trang_thai === "dat").length;
                return (
                  <div className="tp-group-head">
                    <div className="tp-group-title">
                      <span className="em">{g.em}</span> {g.mach.toUpperCase()}
                      <span className="tp-dem tnum">{xong}/{g.dv.length}</span>
                    </div>
                    {/* Thanh tiến độ theo MẠCH: cây danh mục dài, không có nó thì
                        học sinh không biết mạch nào gần xong. */}
                    <div className="tp-bar">
                      <i style={{ width: `${g.dv.length ? (xong / g.dv.length) * 100 : 0}%` }} />
                    </div>
                  </div>
                );
              })()}
              <div className="tp-items">
                {g.dv.map((d) => (
                  <button key={d.topic_id} type="button" className={itemClass(d)} onClick={() => openTopic(d.topic_id)}>
                    {/* Ba trạng thái phân biệt được bằng HÌNH, không chỉ bằng màu:
                        ✓ đã đạt · ◉ đang xem · ○ chưa học (mockup §sidebar). */}
                    <span className="ic" aria-hidden>
                      {d.trang_thai === "dat" ? "✓" : d.topic_id === cur ? "◉" : ""}
                    </span>
                    <span className="tx">{d.ten}</span>
                    {d.topic_id === cur
                      ? <span className="flag xem">ĐANG XEM</span>
                      : d.topic_id === nextId && <span className="flag">TIẾP</span>}
                  </button>
                ))}
              </div>
              {/* Ôn tập chương ở CUỐI mạch (mockup). Không phải bài mới — là view
                  gộp cả mạch, nên đứng ngoài danh sách đơn vị. */}
              <button className={"tp-ontap" + (trang === "on_tap" && onTap?.gt === g.mach ? " dang" : "")}
                type="button" onClick={() => moOnTap("mach", g.mach, `Ôn tập: ${g.mach}`)}>
                <span className="ic" aria-hidden>🔁</span>
                <div><b>Ôn tập chương</b><span>{g.dv.length} bài trong mạch này</span></div>
              </button>
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
          {phutHomNay !== null && (
            <div className="chip-gio" title="Thời gian học hôm nay">
              <span aria-hidden>⏱</span>
              <b className="tnum">{phutHomNay < 60 ? `${phutHomNay} phút`
                : `${Math.floor(phutHomNay / 60)} g ${String(phutHomNay % 60).padStart(2, "0")}`}</b>
            </div>
          )}
          {teacher && lesson && (
            <button className="icon-btn" type="button" title={slide ? "Xem bài học" : "Xem slide"}
              onClick={() => setSlide((s) => !s)} aria-label="Đổi bài học/slide">{slide ? "📘" : "🖥️"}</button>
          )}
          {/* Đổi giao diện + đăng xuất gộp vào đây: tên học sinh trước chỉ nằm
              trong tooltip nút ⎋ nên không ai thấy mình đang đăng nhập bằng ai. */}
          <ProfileMenu name={name} email={email} role={role} stats={stats}
            themeIcon={icon} themeLabel={label} onCycleTheme={cycle} onLogout={onLogout}
            onHoSo={() => setTrang("ho_so")} dangOHoSo={trang === "ho_so"} />
        </div>

        {/* Hero là số liệu của BÀI đang học -> ẩn ở trang Hồ sơ, nơi đã có 4 ô
            thời gian chi tiết hơn. */}
        {trang === "bai" && <Hero stats={stats} mach={lesson?.mach} />}

        {err && <div className="lesson-empty">⚠️ {err}</div>}
        {!err && (trang === "on_tap" && onTap
          ? <OnTapView phamVi={onTap.pv} giaTri={onTap.gt} ten={onTap.ten}
              onMoBai={openTopic} onDong={() => setTrang("bai")} />
          : trang === "ho_so"
          ? <HoSoView onMoBai={moBaiTuHoSo} ten={name} />
          : slide && lesson
            ? <SlideView lesson={lesson} />
            : lesson
              ? <LessonView lesson={lesson} teacher={teacher} onMarkDone={markDone}
                  onQuizGraded={onQuizGraded} />
              : <div className="lesson-empty">Đang tải bài học…</div>)}
      </main>
    </div>
  );
}
