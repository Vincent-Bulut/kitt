# Utilisez une image Python officielle comme base
FROM python:3.12

# Définissez le dossier de travail principal à l'intérieur du conteneur

# Copiez les fichiers nécessaires pour installer les dépendances
COPY backend/requirements.txt /app/requirements.txt

WORKDIR /app

# Installez toutes les dépendances listées dans requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiez l'intégralité du code source dans le conteneur
COPY backend /app/backend/

ENV PYTHONPATH=$PYTHONPATH:/app

# Exposez le port utilisé par votre backend
EXPOSE 8000

CMD ["uvicorn", "backend.api.main:api", "--host", "0.0.0.0", "--port", "8000"]
