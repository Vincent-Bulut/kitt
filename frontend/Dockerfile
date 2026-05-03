# Utilisez l'image Node.js comme base
FROM node:22 AS builder

# Définir le répertoire de travail dans le conteneur
WORKDIR /app/frontend

# Copier uniquement les fichiers nécessaires pour installer les dépendances
COPY package*.json ./

# Installer les dépendances
RUN npm install

# Copier tout le reste des fichiers dans le conteneur
COPY . .

RUN npm run build

CMD ["npm", "run", "dev", "--", "--host"]

FROM nginx:latest

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/build /usr/share/nginx/html

EXPOSE 80