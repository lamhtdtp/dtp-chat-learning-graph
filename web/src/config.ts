// Base URL backend. Dev để rỗng -> gọi same-origin, Vite proxy sang :8000.
// Production đặt VITE_API_URL lúc build (vd https://api.example.vn).
export const API_BASE = import.meta.env.VITE_API_URL ?? "";

// Tên gia sư ảo — CHỖ DUY NHẤT để đổi persona (design brief để ngỏ tên chính
// thức, "Sóc" là tên tạm thân thiện, không dùng lại "Mina" của hệ thống cũ).
export const TUTOR_NAME = "Sóc";
