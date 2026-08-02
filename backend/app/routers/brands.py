from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from ..auth import AuthUser, get_current_user
from ..models.brands import (
    Brand,
    BrandCreate,
    BrandListResponse,
    BrandUpdate,
)
from ..services import brands

router = APIRouter()


@router.get("", response_model=BrandListResponse)
async def list_brand_mappings(user: AuthUser = Depends(get_current_user)):
    items = await brands.list_brands()
    return BrandListResponse(brands=items, total=len(items))


@router.post("", response_model=Brand, status_code=201)
async def create_brand_mapping(
    body: BrandCreate, user: AuthUser = Depends(get_current_user)
):
    try:
        return await brands.create_brand(body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{brand_id}", response_model=Brand)
async def update_brand_mapping(
    brand_id: int, body: BrandUpdate, user: AuthUser = Depends(get_current_user)
):
    try:
        return await brands.update_brand(brand_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{brand_id}", status_code=204)
async def delete_brand_mapping(
    brand_id: int, user: AuthUser = Depends(get_current_user)
):
    if not await brands.delete_brand(brand_id):
        raise HTTPException(status_code=404, detail="Brand mapping not found.")
    return Response(status_code=204)

