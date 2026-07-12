import { createPortal } from "react-dom";
import type { ReactNode } from "react";

// Đưa nội dung (modal/popup) ra thẳng <body> để overlay phủ TOÀN màn hình,
// không bị khung chat (overflow:hidden / bo góc / transform khi animate) cắt hay
// giới hạn containing-block của position:fixed.
export function Portal({ children }: { children: ReactNode }) {
  return createPortal(children, document.body);
}
