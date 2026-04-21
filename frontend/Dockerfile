# Build stage
FROM node:20-alpine AS builder
WORKDIR /app

# Copy only frontend package files
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --legacy-peer-deps

# Copy full frontend code
COPY frontend/ .
RUN npm run build

# Serve stage — nginx
FROM nginx:alpine AS production

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx/nginx.frontend.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]