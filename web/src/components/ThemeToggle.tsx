import { useTheme } from "../hooks/useTheme";

// Nút đổi giao diện: Tự động → Sáng → Tối → Tự động.
export function ThemeToggle() {
  const { cycle, label, icon } = useTheme();
  return (
    <button className="theme-toggle" type="button" onClick={cycle}
      aria-label={`Giao diện: ${label}. Bấm để đổi.`} title={`Giao diện: ${label}`}>
      <span aria-hidden>{icon}</span> {label}
    </button>
  );
}
