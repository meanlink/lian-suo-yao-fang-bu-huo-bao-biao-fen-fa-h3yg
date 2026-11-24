from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from ..auth import current_user, require
from . import counts

router = APIRouter(prefix='/warehouse/counts', tags=['仓库盘差'])


class Count(BaseModel):
    lot_id: int = Field(gt=0)
    count_ref: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    counted_units: int = Field(ge=0, le=1000000)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=300)]


class Review(BaseModel):
    decision: Literal['posted', 'rejected']
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=300)]


@router.get('')
def queue(_user=Depends(current_user)):
    return counts.count_queue()


@router.post('', status_code=201)
def submit(data: Count, user=Depends(require('inventory_clerk'))):
    return counts.submit(data, user['sub'])


@router.put('/{count_id}')
def review(count_id: int, data: Review, user=Depends(require('regional_manager'))):
    return counts.review(count_id, data, user['sub'])
