import os
import uvicorn
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi.middleware.cors import CORSMiddleware

from backend.api import model, schema
from backend.api.database import SessionLocal, engine, get_db

from backend.api.admin import router as admin_router
from backend.api.referential import router as referential_router
from backend.api.analytics import router as analytics_router
from backend.api.etfbook_primary import router as etfbook_primary_router

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
api.include_router(referential_router)
api.include_router(analytics_router)

api.include_router(etfbook_primary_router)

@api.get("/")
def say_hello():
    return "Hello World!"

if __name__ == '__main__':
    uvicorn.run("main:api", host="0.0.0.0", port=8000, reload=True)