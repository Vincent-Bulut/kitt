# --- Étape 1 : build statique SvelteKit ---
FROM node:22-slim AS builder

WORKDIR /app/frontend

# Installe exactement les versions du package-lock.json
COPY package.json package-lock.json ./
RUN npm ci

# Copie les sources (node_modules/build exclus via .dockerignore ; .env conservé
# car PUBLIC_APP_API_URL est injecté au build)
COPY . .
RUN npm run build

# --- Étape 2 : service des fichiers statiques ---
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/build /usr/share/nginx/html

EXPOSE 80
