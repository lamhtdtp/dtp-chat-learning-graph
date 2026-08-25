import type { Role } from "../types";

/** Vai trò được vào khu quản trị. `chuyen_gia` chỉ thấy phần Nội dung (lọc ở
 *  Dashboard); `admin` thấy tất cả. Học sinh dùng app học, không vào đây.
 *
 *  Để ở file riêng vì CẢ HAI cửa đều phải dùng đúng một danh sách: form đăng
 *  nhập từng chốt cứng `admin` trong khi AdminApp đã mở cho chuyên gia, nên
 *  chuyên gia không bao giờ lấy được phiên — đăng nhập là bị đá ra ngay. */
export const VAO_DUOC: Role[] = ["chuyen_gia", "giao_vien", "admin"];
