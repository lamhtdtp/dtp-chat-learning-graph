// Mô hình môn học cho UI đa môn. Màu áp qua data-subject (xem styles.css);
// mỗi môn có icon, mạch chủ đề, gợi ý câu hỏi riêng.
// LƯU Ý: backend hiện chỉ có dữ liệu môn Toán -> chỉ `toan` mở (unlocked).
// Môn khác hiển thị "Sắp ra mắt" và không cho vào chat (tránh trả lời sai môn).

export interface Subject {
  key: string;
  name: string;      // tên hiển thị (vd "Toán")
  short: string;     // tên trong "Gia sư {short}"
  icon: string;
  cats: number;      // số mạch chủ đề (hiển thị trên thẻ)
  suggestions: string[];
  unlocked: boolean;
}

export const SUBJECTS: Subject[] = [
  { key: "toan", name: "Toán", short: "Toán", icon: "📐", cats: 6, unlocked: true,
    suggestions: ["Số nguyên tố là gì?", "Ước chung lớn nhất và bội chung nhỏ nhất", "Cách viết một tập hợp?", "Ôn tập chương Số tự nhiên"] },
  { key: "van", name: "Tiếng Anh", short: "Tiếng Anh", icon: "💬", cats: 5, unlocked: false,
    suggestions: ["Present Perfect dùng khi nào?", "Từ vựng chủ đề du lịch", "Viết lại câu", "Luyện phát âm"] },
  { key: "anh", name: "Ngữ văn", short: "Ngữ văn", icon: "✒️", cats: 5, unlocked: false,
    suggestions: ["Phân tích bài Ánh trăng", "Lập dàn ý nghị luận", "Biện pháp tu từ", "Tóm tắt Làng"] },
  { key: "khtn", name: "KHTN", short: "KHTN", icon: "🔬", cats: 6, unlocked: false,
    suggestions: ["Định luật Ôm", "Cân bằng phương trình hoá học", "Cấu tạo tế bào", "Bài tập điện trở"] },
  { key: "sudia", name: "Lịch sử & Địa lí", short: "Sử & Địa", icon: "🗺️", cats: 5, unlocked: false,
    suggestions: ["Cách mạng tháng Tám", "Đặc điểm khí hậu Việt Nam", "Vẽ biểu đồ dân số", "Chiến dịch Điện Biên Phủ"] },
  { key: "tin", name: "Tin học", short: "Tin học", icon: "💻", cats: 4, unlocked: false,
    suggestions: ["Vòng lặp for là gì?", "Sắp xếp nổi bọt", "Hàm trong Python", "Tạo bảng tính"] },
  { key: "gdcd", name: "GDCD", short: "GDCD", icon: "⚖️", cats: 4, unlocked: false,
    suggestions: ["Quyền trẻ em", "Sống có trách nhiệm", "Pháp luật là gì?", "Bảo vệ môi trường"] },
];

export const SUBJECT_MAP: Record<string, Subject> = Object.fromEntries(
  SUBJECTS.map((s) => [s.key, s]),
);

export const DEFAULT_SUBJECT = "toan";
