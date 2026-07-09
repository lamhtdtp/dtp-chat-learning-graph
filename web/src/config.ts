// Base URL backend. Dev để rỗng -> gọi same-origin, Vite proxy sang :8000.
// Production đặt VITE_API_URL lúc build (vd https://api.example.vn).
export const API_BASE = import.meta.env.VITE_API_URL ?? "";

// Tên gia sư ảo — CHỖ DUY NHẤT để đổi persona. Đổi từ "Sóc" (mascot con vật,
// hợp trẻ nhỏ) sang tên trung tính, hợp học sinh lớp lớn (tới lớp 12) —
// tránh giọng "bé"/con vật dễ thương với đối tượng lớn tuổi hơn.
export const TUTOR_NAME = "Gia sư DTP";
export const APP_NAME = "Trợ lý học Toán";
 