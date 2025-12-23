from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from backend.api import schema, model

from backend.api import schema
from backend.api.database import get_db

router = APIRouter(prefix='/admin', tags=['ADMIN'])

@router.post("/portfolio")
def create_portfolio(portfolio: schema.Portfolio, db: Session = Depends(get_db)):
    try:
        new_portfolio = model.Portfolio(
            name=portfolio.name,
            start_date=portfolio.start_date,
            end_date=portfolio.end_date,
            description=portfolio.description,
            manager_name=portfolio.manager_name
        )
        db.add(new_portfolio)
        db.commit()
        db.refresh(new_portfolio)
        return new_portfolio
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/portfolio/{portfolio_id}", response_model=schema.Portfolio)
def update_portfolio(
        portfolio_id: int,
        updated_portfolio: schema.Portfolio,
        db: Session = Depends(get_db)
):
    try:
        # On récupère le portfolio existant via son ID
        existing_portfolio = db.query(model.Portfolio).get(portfolio_id)
        if not existing_portfolio:
            raise HTTPException(status_code=404, detail="Portfolio introuvable.")

        # On met à jour les champs souhaités
        existing_portfolio.name = updated_portfolio.name
        existing_portfolio.start_date = updated_portfolio.start_date
        existing_portfolio.end_date = updated_portfolio.end_date
        existing_portfolio.description = updated_portfolio.description
        existing_portfolio.manager_name = updated_portfolio.manager_name

        db.commit()
        db.refresh(existing_portfolio)
        return existing_portfolio

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.delete("/portfolio/{portfolio_id}")
def delete_portfolio(
        portfolio_id: int,
        db: Session = Depends(get_db)
):
    try:
        # Récupérer l’objet existant
        existing_portfolio = db.query(model.Portfolio).get(portfolio_id)
        if not existing_portfolio:
            raise HTTPException(
                status_code=404,
                detail="Portfolio introuvable."
            )

        # Supprimer l’objet
        db.delete(existing_portfolio)
        db.commit()

        return {"message": "Portfolio supprimé avec succès"}

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) from e

@router.get("/portfolio/{portfolio_id}", response_model=schema.Portfolio)
def get_portfolio(
        portfolio_id: int,
        db: Session = Depends(get_db)
):
    try:
        portfolio = db.query(model.Portfolio).get(portfolio_id)
        if not portfolio:
            raise HTTPException(
                status_code=404,
                detail="Portfolio introuvable."
            )
        return portfolio

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) from e

@router.get("/portfolios", response_model=List[schema.PortfolioRead])
def get_all_portfolios(
        db: Session = Depends(get_db)
):
    try:
        portfolios = db.query(model.Portfolio).all()
        return portfolios
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) from e
