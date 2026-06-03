FROM node:18-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# 非 root nginx(官方 nginx-unprivileged,默认 USER nginx uid 101,监听 8080)。
# 缩小容器以 root 运行的权限面(L-8)。
FROM nginxinc/nginx-unprivileged:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
