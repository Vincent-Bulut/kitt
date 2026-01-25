import os
import requests
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from typing import List, Optional, Any, Dict
import pandas as pd
import numpy as np
import httpx

router = APIRouter(prefix='/etfbook/analytics', tags=['ETFBOOK'])

ETFBOOK_API_BASE_URL= os.getenv("ETFBOOK_API_BASE_URL")
ETFBOOK_REF_API_TOKEN = os.getenv("ETFBOOK_REF_API_TOKEN")
ETFBOOK_PRIMARY_TIME_SERIES = os.getenv("ETFBOOK_PRIMARY_TIME_SERIES")


def capitalize_first_letter(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


class DynamicDataService:
    def __init__(self, endpoint_flows_details: str, headers: dict, isin_flow_chunk_size: int = 50):
        self.endpoint_flows_details = endpoint_flows_details
        self.headers = headers
        self.isin_flow_chunk_size = isin_flow_chunk_size

    async def get_dynamic_data(self, list_isins: List[str], b_milion: bool = False) -> pd.DataFrame:
        chunked_list = [
            list_isins[i : i + self.isin_flow_chunk_size]
            for i in range(0, len(list_isins), self.isin_flow_chunk_size)
        ]

        all_dataframes: List[pd.DataFrame] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for chunk in chunked_list:
                params = [("isins", isin) for isin in chunk]  # isins=A&isins=B&...

                try:
                    resp = await client.get(
                        self.endpoint_flows_details,
                        headers=self.headers,
                        params=params,
                    )
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    # On remonte l'erreur upstream avec un message clair
                    raise HTTPException(
                        status_code=502,
                        detail=f"Upstream error ({e.response.status_code}) on dynamic-data call",
                    )
                except httpx.RequestError:
                    raise HTTPException(status_code=502, detail="Upstream unreachable for dynamic-data")

                data = resp.json()
                df = pd.DataFrame(data)
                all_dataframes.append(df)

        if not all_dataframes:
            return pd.DataFrame()

        final_df = pd.concat(all_dataframes, ignore_index=True)

        # --- Transformations (copie de ta logique) ---
        # 1) date
        if "ratingDate" in final_df.columns:
            final_df["ratingDate"] = pd.to_datetime(final_df["ratingDate"], errors="coerce")

        # 2) rename
        final_df.rename(
            columns={
                "ratingDate": "navDate",
                "navL": "nav",
                "navU": "navUsd",
                "aumU": "aumUsd",
                "adjustedNavL": "adjustedNav",
            },
            inplace=True,
        )

        # 3) format YYYY-MM-DD
        if "navDate" in final_df.columns:
            final_df["navDate"] = (
                pd.to_datetime(final_df["navDate"], errors="coerce")
                .dt.strftime("%Y-%m-%d")
            )

        # 4) drop cols si présentes
        drop_cols = ["createdAt", "modifiedAt", "modifiedBy", "createdBy"]
        final_df.drop(columns=[c for c in drop_cols if c in final_df.columns], inplace=True)

        # 5) millions
        if b_milion:
            if "sharesOut" in final_df.columns:
                final_df["sharesOut"] = (final_df["sharesOut"] / 1e6).round(2)
            if "aumUsd" in final_df.columns:
                final_df["aumUsd"] = (final_df["aumUsd"] / 1e6).round(2)

        # 6) Capitalize columns
        final_df.columns = [capitalize_first_letter(c) for c in final_df.columns]

        return final_df

dynamic_service = DynamicDataService(
    endpoint_flows_details=f"{ETFBOOK_API_BASE_URL}{ETFBOOK_PRIMARY_TIME_SERIES}",
    headers={'AuthToken': ETFBOOK_REF_API_TOKEN, 'Content-Type': 'application/json'},
    isin_flow_chunk_size=50,
)

@router.get("/dynamic-data")
async def get_etfbook_dynamic_data(
    isins: List[str] = Query(..., description="Repeated query param: ?isins=...&isins=..."),
    b_milion: bool = Query(False, description="If true, sharesOut & aumUsd are returned in millions"),
):
    df = await dynamic_service.get_dynamic_data(isins, b_milion=b_milion)

    # JSON-friendly output
    if df.empty:
        return {"data": [], "count": 0}

    df = df.replace([np.inf, -np.inf], np.nan).astype(object)
    df = df.where(pd.notnull(df), None)

    records: List[Dict[str, Any]] = df.to_dict(orient="records")
    return {"data": records, "count": len(records)}
