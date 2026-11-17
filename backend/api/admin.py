from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api import model, schema
from backend.api.database import commit_or_conflict, get_db

router = APIRouter(prefix="/admin", tags=["ADMIN"])


def _get_portfolio_or_404(db: Session, portfolio_id: int) -> model.Portfolio:
    portfolio = db.get(model.Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found.")
    return portfolio


@router.post("/portfolio", response_model=schema.PortfolioRead, status_code=201)
def create_portfolio(portfolio: schema.Portfolio, db: Session = Depends(get_db)):
    new_portfolio = model.Portfolio(**portfolio.model_dump())
    db.add(new_portfolio)
    commit_or_conflict(db)
    db.refresh(new_portfolio)
    return new_portfolio


@router.put("/portfolio/{portfolio_id}", response_model=schema.PortfolioRead)
def update_portfolio(portfolio_id: int, updated_portfolio: schema.Portfolio, db: Session = Depends(get_db)):
    portfolio = _get_portfolio_or_404(db, portfolio_id)
    for field, value in updated_portfolio.model_dump().items():
        setattr(portfolio, field, value)
    commit_or_conflict(db)
    db.refresh(portfolio)
    return portfolio


@router.delete("/portfolio/{portfolio_id}")
def delete_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = _get_portfolio_or_404(db, portfolio_id)
    db.delete(portfolio)
    commit_or_conflict(db)
    return {"message": "Portfolio deleted"}


@router.get("/portfolio/{portfolio_id}", response_model=schema.PortfolioRead)
def get_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    return _get_portfolio_or_404(db, portfolio_id)


@router.get("/portfolios", response_model=list[schema.PortfolioRead])
def get_all_portfolios(db: Session = Depends(get_db)):
    return db.query(model.Portfolio).order_by(model.Portfolio.id).all()
