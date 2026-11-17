from io import BytesIO

import numpy as np
import pandas as pd
import requests
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.api import model
from backend.api.database import get_db
from backend.api.pea import find_new_isins, scrape_pea_etfs, to_csv

router = APIRouter(prefix='/referential', tags=['REFERENTIAL'])


@router.get("/")
def say_hello():
    return "Hello Referential!"


@router.get("/pea/download")
def download_pea_etfs():
    """
    Scrapes the PEA-eligible ETFs listed on Euronext and returns them as a CSV file.
    """
    try:
        etfs = scrape_pea_etfs()
    except (requests.RequestException, RuntimeError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"Euronext scraping failed: {e}") from e

    return Response(
        content=to_csv(etfs).encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="pea.csv"'},
    )


@router.get("/pea/new-isins")
def check_new_pea_isins(db: Session = Depends(get_db)):
    """
    Scrapes the PEA-eligible ETFs on Euronext and returns those whose ISIN is not in the assets table.
    """
    try:
        etfs = scrape_pea_etfs()
    except (requests.RequestException, RuntimeError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"Euronext scraping failed: {e}") from e

    try:
        known_isins = {
            isin.strip().upper()
            for (isin,) in db.query(model.Assets.isin).all()
            if isin
        }
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e!s}") from e

    new_etfs = find_new_isins(etfs, known_isins)

    return {
        "scraped_isins": len({etf.isin for etf in etfs}),
        "known_isins": len(known_isins),
        "new_count": len(new_etfs),
        "new_etfs": new_etfs,
    }


@router.get("/assets")
def list_assets(db: Session = Depends(get_db)):
    """
    Retrieves the list of all assets from the database.
    """
    try:
        assets = db.query(model.Assets).all()
        return assets
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e!s}") from e

@router.post("/upload-excel")
def upload_referential_excel(
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
):
    filename = (file.filename or "").lower()
    if not (filename.endswith(".xlsx") or filename.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx/.xls).")

    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read uploaded file: {e}") from e

    try:
        df = pd.read_excel(BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}") from e

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
        present_cols = ["symbol", *present_cols]

    # fees: cast to float
    if "fees" in df.columns:
        df["fees"] = pd.to_numeric(df["fees"], errors="coerce")

    # NaN/Inf -> None (otherwise NaN reaches the DB and breaks JSON)
    df = df.replace([np.nan, np.inf, -np.inf], None)

    payload = df[present_cols].to_dict(orient="records")

    try:
        stmt = insert(model.Assets).values(payload)

        # Do not overwrite existing values with NULL when the Excel cell is empty
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
        raise HTTPException(status_code=500, detail=f"Database error: {e!s}") from e
