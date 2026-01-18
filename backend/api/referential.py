import os
import requests
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from backend.api import schema, model
from sqlalchemy.dialects.postgresql import insert
import pandas as pd
from io import BytesIO
import numpy as np
from sqlalchemy import func
from typing import Any, Dict, List, Optional

from backend.api import schema
from backend.api.database import get_db

router = APIRouter(prefix='/referential', tags=['REFERENTIAL'])

ETFBOOK_REF_API_TOKEN = os.getenv("ETFBOOK_REF_API_TOKEN")
ETFBOOK_REF_API_BASE_URL = os.getenv("ETFBOOK_REF_API_BASE_URL")
ETFBOOK_API_BASE_URL = os.getenv("ETFBOOK_API_BASE_URL")

@router.get("/")
def say_hello():
    return "Hello Referential!"


@router.get("/assets")
def list_assets(db: Session = Depends(get_db)):
    """
    Retrieves the list of all assets from the database.
    """
    try:
        assets = db.query(model.Assets).all()
        return assets
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Erreur de base de données : {str(e)}")

@router.get("/etfbook/static-data")
def get_etfbook_static_data(
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, min_length=1, max_length=100),
) -> Dict[str, Any] | List[Dict[str, Any]]:
    """
    Fetch static data from ETFBook API (server-side),
    optionally filter by `q`, then paginate with limit/offset.
    """
    api_url = f"{ETFBOOK_API_BASE_URL}{ETFBOOK_REF_API_BASE_URL}"
    headers = {
        "AuthToken": ETFBOOK_REF_API_TOKEN,
        "Accept": "application/json",
    }

    try:
        r = requests.get(api_url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()

        # If ETFBook returns something other than a list, just return it
        if not isinstance(data, list):
            return data

        # Optional server-side search filter
        if q:
            needle = q.strip().lower()

            def matches(row: Dict[str, Any]) -> bool:
                # Targeted fields first (fast + relevant)
                fields = [
                    row.get("fundISIN"),
                    row.get("fundName"),
                    row.get("exchangeReutersCode"),
                    row.get("exchangeBloombergCode"),
                    row.get("fundTaxReportingFRPEA")
                ]
                hay = " ".join(str(x) for x in fields if x is not None).lower()

                # Fallback: search across the whole row (slower but robust)
                if needle in hay:
                    return True
                return needle in str(row).lower()

            data = [row for row in data if isinstance(row, dict) and matches(row)]

        total = len(data)
        page = data[offset : offset + limit]

        return {
            "count": len(page),
            "total": total,
            "limit": limit,
            "offset": offset,
            "q": q,
            "items": page,
        }

    except requests.Timeout:
        raise HTTPException(status_code=504, detail="ETFBook API timeout")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"ETFBook API error: {str(e)}")


@router.post("/upload-excel")
async def upload_referential_excel(
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
):
    filename = (file.filename or "").lower()
    if not (filename.endswith(".xlsx") or filename.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx/.xls).")

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read uploaded file: {e}")

    try:
        df = pd.read_excel(BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}")

    df.columns = [c.strip().lower() for c in df.columns]

    if "symbol" not in df.columns:
        raise HTTPException(status_code=400, detail="Missing required column: 'symbol'.")

    df["symbol"] = df["symbol"].astype(str).str.strip()
    df = df[df["symbol"].notna() & (df["symbol"] != "")].copy()

    if df.empty:
        return {"inserted_or_updated": 0, "message": "No valid rows (empty or missing symbol)."}

    allowed_cols = {
        "isin", "symbol", "name", "currency",
        "fees", "asset_class", "geo_focus",
        "asset_category_lv1", "asset_category_lv2", "asset_category_lv3", "asset_category_lv4"
    }
    present_cols = [c for c in df.columns if c in allowed_cols]
    if "symbol" not in present_cols:
        present_cols = ["symbol"] + present_cols

    # ✅ fees: cast en float
    if "fees" in df.columns:
        df["fees"] = pd.to_numeric(df["fees"], errors="coerce")

    # ✅ NaN/Inf -> None (sinon NaN part en DB et casse le JSON)
    df = df.replace([np.nan, np.inf, -np.inf], None)

    payload = df[present_cols].to_dict(orient="records")

    try:
        stmt = insert(model.Assets).values(payload)

        # ✅ ne pas écraser avec NULL quand Excel est vide
        update_cols = {
            c: func.coalesce(getattr(stmt.excluded, c), getattr(model.Assets, c))
            for c in present_cols
            if c != "symbol"
        }

        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_=update_cols,
        )

        result = db.execute(stmt)
        db.commit()

        return {"inserted_or_updated": int(result.rowcount or len(payload)), "rows_in_file": len(payload)}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
