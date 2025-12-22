
import uvicorn
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi.middleware.cors import CORSMiddleware

from backend.api import model, schema
from backend.api.database import SessionLocal, engine, get_db

from backend.api.admin import router as admin_router

model.Base.metadata.create_all(bind=engine)

api = FastAPI()

# Ajout du middleware CORS
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Origines autorisées
    allow_credentials=True,
    allow_methods=["*"],  # Permet tous les types de requêtes HTTP (GET, POST, etc.)
    allow_headers=["*"],  # Autorise tous les en-têtes
)

api.include_router(admin_router)

@api.get("/")
def say_hello():
    return "Hello World!"

if __name__ == '__main__':
    uvicorn.run("main:api", host="0.0.0.0", port=8000, reload=True)