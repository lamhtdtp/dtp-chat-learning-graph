import { TUTOR_NAME } from "../config";
import type { SessionRow } from "../types";

interface Props {
  sessions: SessionRow[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
  onNewChat: () => void;
  onLogout: () => void;
}

export function Sidebar({ sessions, activeId, onSelect, onDelete, onNewChat, onLogout }: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="avatar"><img src="/dtp-logo.png" alt="DTP" /></div>
        <span className="font-display">{TUTOR_NAME}</span>
      </div>

      <button className="new-chat" onClick={onNewChat} type="button">+ Cuộc trò chuyện mới</button>

      <div className="session-list">
        {sessions.length === 0 && <div className="session-empty">Chưa có lịch sử trò chuyện</div>}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={"session-item" + (s.id === activeId ? " active" : "")}
            onClick={() => onSelect(s.id)}
          >
            <span className="session-title">{s.title}</span>
            <button
              className="session-del"
              title="Xoá"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(s.id);
              }}
              type="button"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <button className="sidebar-logout" onClick={onLogout} type="button">Đăng xuất</button>
    </aside>
  );
}
