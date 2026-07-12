import type { SessionRow } from "../types";

interface Props {
  sessions: SessionRow[];
  activeId: number | null;
  userName?: string;
  className?: string;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
  onNewChat: () => void;
  onLogout: () => void;
}

// Sidebar bên trái khung chat (lịch sử hội thoại). Trên mobile trượt vào dạng
// drawer (class "open" do ChatView điều khiển).
export function ChatSidebar({
  sessions, activeId, userName, className = "", onSelect, onDelete, onNewChat, onLogout,
}: Props) {
  return (
    <aside className={"chat-side " + className}>
      <button className="new-chat" type="button" onClick={onNewChat}>＋ Cuộc trò chuyện mới</button>
      <div className="side-label">Lịch sử</div>
      <div className="side-list">
        {sessions.length === 0 && <div className="side-item" style={{ cursor: "default", opacity: .7 }}>Chưa có hội thoại</div>}
        {sessions.map((s) => (
          <div key={s.id} className={"side-item" + (s.id === activeId ? " active" : "")} onClick={() => onSelect(s.id)}>
            <span className="t">{s.title}</span>
            <button className="side-del" type="button" title="Xoá"
              onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}>✕</button>
          </div>
        ))}
      </div>
      <div className="side-foot">
        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {userName || "Học sinh"} · Lớp 6
        </span>
        <button className="side-logout" type="button" onClick={onLogout}>Đăng xuất</button>
      </div>
    </aside>
  );
}
