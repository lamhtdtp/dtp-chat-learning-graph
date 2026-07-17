import { useCallback, useEffect, useState } from "react";

// Sáng / Tối / Auto. Auto = KHÔNG set data-theme (để prefers-color-scheme quyết).
// Toggle luân phiên auto -> light -> dark -> auto. Lưu localStorage.
export type ThemeMode = "auto" | "light" | "dark";

const KEY = "dtp_theme";
const NEXT: Record<ThemeMode, ThemeMode> = { auto: "light", light: "dark", dark: "auto" };
const LABEL: Record<ThemeMode, string> = { auto: "Tự động", light: "Sáng", dark: "Tối" };
const ICON: Record<ThemeMode, string> = { auto: "🌗", light: "☀️", dark: "🌙" };

function apply(mode: ThemeMode) {
  const root = document.documentElement;
  if (mode === "auto") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", mode);
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(() => (localStorage.getItem(KEY) as ThemeMode) || "auto");

  useEffect(() => {
    apply(mode);
    localStorage.setItem(KEY, mode);
  }, [mode]);

  const cycle = useCallback(() => setMode((m) => NEXT[m]), []);
  return { mode, cycle, label: LABEL[mode], icon: ICON[mode] };
}
