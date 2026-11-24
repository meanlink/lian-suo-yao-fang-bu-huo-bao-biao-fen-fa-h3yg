from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from ..auth import current_user, require
from . import lots

router = APIRouter(prefix='/warehouse/lots', tags=['仓库批号'])


class Receipt(BaseModel):
    sku: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    lot_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=50)]
    supplier_ref: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    expires_on: date
    temperature_band: Literal['ambient', 'chilled']
    units: int = Field(gt=0, le=1000000)


@router.get('')
def list_lots(_user=Depends(current_user)):
    return lots.list_stock()


@router.post('', status_code=201)
def receive(data: Receipt, user=Depends(require('shift_coordinator'))):
    return lots.register(data, user['sub'])
