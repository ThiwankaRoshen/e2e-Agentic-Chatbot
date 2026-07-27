# ---- Stage 1: build ----
FROM node:22-alpine AS build

WORKDIR /app

# Dependency layer — cached unless package*.json changes
COPY package.json package-lock.json ./
RUN npm ci

# Source layer
COPY . .

RUN npm run build
# Vite outputs to /app/dist by default

# ---- Stage 2: serve ----
FROM nginx:alpine AS serve

# Replace default nginx config with an SPA-friendly one (client-side routing support)
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]