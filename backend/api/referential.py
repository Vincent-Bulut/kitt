
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from backend.api import schema, model
from sqlalchemy.dialects.postgresql import insert
import pandas as pd
from io import BytesIO


from backend.api import schema
from backend.api.database import get_db

router = APIRouter(prefix='/referential', tags=['REFERENTIAL'])

@router.get("/")
def say_hello():
    return "Hello Referential!"

@router.post("/upload-excel")
async def upload_referential_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # 1) Validate file type (souple, basé sur extension + content-type)
    filename = (file.filename or "").lower()
    if not (filename.endswith(".xlsx") or filename.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx/.xls).")

    # 2) Read file bytes
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read uploaded file: {e}")

    # 3) Parse Excel → DataFrame
    try:
        df = pd.read_excel(BytesIO(content))  # nécessite pandas + openpyxl (souvent déjà là)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}")

    # 4) Normalize columns
    df.columns = [c.strip().lower() for c in df.columns]

    if "symbol" not in df.columns:
        raise HTTPException(status_code=400, detail="Missing required column: 'symbol'.")

    # Optionnel: drop lignes sans symbol
    df["symbol"] = df["symbol"].astype(str).str.strip()
    df = df[df["symbol"].notna() & (df["symbol"] != "")].copy()

    if df.empty:
        return {"inserted_or_updated": 0, "message": "No valid rows (empty or missing symbol)."}

    # 5) Choisis les colonnes que tu veux merger en base
    # Exemple: symbol, name, currency
    allowed_cols = {"isin", "symbol", "name", "currency"}
    present_cols = [c for c in df.columns if c in allowed_cols]

    if "symbol" not in present_cols:
        present_cols = ["symbol"] + present_cols

    payload = df[present_cols].to_dict(orient="records")

    # 6) Upsert PostgreSQL (ON CONFLICT symbol DO UPDATE)
    # - conflict target: symbol (doit être unique/indexed)
    # - update seulement les colonnes autres que symbol
    try:
        stmt = insert(model.Assets).values(payload)

        update_cols = {c: getattr(stmt.excluded, c) for c in present_cols if c != "symbol"}

        # Si tu veux aussi toucher updated_at
        # update_cols["updated_at"] = func.now()

        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],  # ou constraint="uq_referential_symbol"
            set_=update_cols,
        )

        result = db.execute(stmt)
        db.commit()

        # result.rowcount sur upsert peut être "surprenant" selon drivers,
        # mais donne souvent un ordre de grandeur.
        return {"inserted_or_updated": int(result.rowcount or len(payload)), "rows_in_file": len(payload)}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")