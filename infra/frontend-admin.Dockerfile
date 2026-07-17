# web-admin: app QUẢN TRỊ React (Vite) build tĩnh rồi serve bằng nginx — CONTAINER
# RIÊNG, tách khỏi web học sinh/giáo viên (giống cách h5p-platform tách h5p-admin).
# VITE_API_URL nướng vào lúc build (URL backend mà TRÌNH DUYỆT gọi) — qua --build-arg.
FROM node:20-alpine AS build

WORKDIR /web-admin
COPY web-admin/package.json ./
# npm install (không dùng ci): tránh bug optional-deps rollup theo nền tảng.
RUN npm install --no-audit --no-fund
COPY web-admin/ ./

ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/nginx-admin.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web-admin/dist /usr/share/nginx/html
EXPOSE 80
