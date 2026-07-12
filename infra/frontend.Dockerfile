# Frontend: build React tĩnh rồi serve bằng nginx. VITE_API_URL nướng vào lúc
# build (URL backend mà TRÌNH DUYỆT gọi) — truyền qua --build-arg.
FROM node:20-alpine AS build

WORKDIR /web
COPY web/package.json web/package-lock.json ./
# Dùng `npm install` (không phải `npm ci`): npm có bug optional-deps (#4828) khiến
# ci đôi khi THIẾU native binary rollup theo nền tảng -> `vite build` lỗi
# "Cannot find module @rollup/rollup-linux-*". install resolve optional đúng nền
# tảng đang build (musl/glibc, arm64/x64) và không kén lock lệch nhẹ.
RUN npm install --no-audit --no-fund
COPY web/ ./

ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
