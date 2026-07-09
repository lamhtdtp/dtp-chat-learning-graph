// Gợi ý nhanh (hiện trên ô nhập khi trống) + danh mục chủ đề (panel phải).
export const SUGGESTIONS = [
  "Số nguyên tố là gì ạ?",
  "Cho em 3 bài tập chia hết",
  "Cách viết một tập hợp?",
];

export interface TopicGroup {
  title: string;
  emoji: string;
  items: string[];
}

// Danh mục chương trình Toán lớp 6 (Tập 1 + Tập 2).
export const TOPIC_GROUPS: TopicGroup[] = [
  { title: "Số tự nhiên", emoji: "🔢", items: ["Số nguyên tố, hợp số", "Ước và bội", "ƯCLN và BCNN", "Lũy thừa", "Dấu hiệu chia hết"] },
  { title: "Số nguyên", emoji: "➖", items: ["Số nguyên âm", "Cộng trừ số nguyên", "Nhân chia số nguyên"] },
  { title: "Phân số & Số thập phân", emoji: "➗", items: ["Phân số", "Phép tính phân số", "Số thập phân", "Tỉ số & phần trăm"] },
  { title: "Hình học trực quan", emoji: "🔺", items: ["Tam giác đều, lục giác đều", "Hình chữ nhật, hình thoi", "Chu vi & diện tích"] },
  { title: "Hình học phẳng", emoji: "📐", items: ["Điểm, đường thẳng", "Đoạn thẳng, trung điểm", "Góc"] },
  { title: "Thống kê & Xác suất", emoji: "📊", items: ["Thu thập & phân loại dữ liệu", "Biểu đồ", "Xác suất thực nghiệm"] },
];
