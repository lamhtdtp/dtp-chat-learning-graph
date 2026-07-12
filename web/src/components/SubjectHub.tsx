import { TUTOR_NAME } from "../config";
import { SUBJECTS } from "../subjects";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";
import type { Role } from "../types";

// Màn gốc điều hướng đa môn (sau đăng nhập). Chọn môn -> vào chat. Môn chưa có
// dữ liệu (unlocked=false) hiển thị "Sắp ra mắt". Giáo viên có thêm thẻ "Sinh đề".
export function SubjectHub({
  name, role, onOpenSubject, onOpenExam, onLogout,
}: {
  name: string;
  role: Role;
  onOpenSubject: (key: string) => void;
  onOpenExam?: () => void;
  onLogout: () => void;
}) {
  const open = SUBJECTS.filter((s) => s.unlocked);

  return (
    <div className="hub">
      <div className="app-bar">
        <div className="brand">
          <div className="dtp-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div className="brand-name">{TUTOR_NAME}</div>
        </div>
        <button className="pill-select" type="button">🎒 Lớp 6 ▾</button>
        <div className="spacer" />
        <ThemeToggle />
        <UserMenu name={name} role={role} onLogout={onLogout} />
      </div>

      <div className="hub-body">
        <div className="hub-greet">Chào {name || "bạn"} 👋 Hôm nay học môn gì?</div>
        <div className="hub-greet-sub">Chọn một môn để bắt đầu hỏi bài cùng gia sư AI.</div>

        {onOpenExam && (
          <button className="hub-exam-card" type="button" onClick={onOpenExam}>
            <span className="hub-exam-ic" aria-hidden>📝</span>
            <span className="hub-exam-txt">
              <span className="hub-exam-title">Sinh đề kiểm tra theo ma trận</span>
              <span className="hub-exam-sub">Dành cho giáo viên · Toán lớp 6</span>
            </span>
            <span className="hub-exam-go" aria-hidden>→</span>
          </button>
        )}

        {open.length > 0 && (
          <div className="hub-recent">
            {open.map((s) => (
              <button key={s.key} className="recent-chip" data-subject={s.key}
                onClick={() => onOpenSubject(s.key)}>
                <span aria-hidden>{s.icon}</span> Tiếp tục {s.name}
              </button>
            ))}
          </div>
        )}

        <div className="hub-section-title">Tất cả môn học</div>
        <div className="subject-grid">
          {SUBJECTS.map((s) => (
            <button
              key={s.key}
              className={"subject-card" + (s.unlocked ? "" : " locked")}
              data-subject={s.key}
              disabled={!s.unlocked}
              onClick={() => s.unlocked && onOpenSubject(s.key)}
              aria-label={s.unlocked ? `Vào môn ${s.name}` : `${s.name} — sắp ra mắt`}
            >
              {!s.unlocked && <span className="sc-badge">Sắp ra mắt</span>}
              <div className="sc-ic" aria-hidden>{s.icon}</div>
              <div className="sc-name">{s.name}</div>
              <div className="sc-sub">Lớp 6</div>
              <div className="sc-meta">{s.cats} mạch chủ đề</div>
            </button>
          ))}
          <div className="subject-card add" aria-hidden>➕ Thêm môn / sắp có</div>
        </div>
      </div>
    </div>
  );
}
