from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from ..auth import current_user, require
from . import temperatures

router = APIRouter(prefix='/warehouse/temperatures', tags=['冷藏交接测温'])


class Measurement(BaseModel):
    instrument_ref: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    observed_c: Decimal = Field(ge=-60, le=80, max_digits=5, decimal_places=2)


@router.get('')
def list_checks(_user=Depends(current_user)):
    return temperatures.list_checks()


@router.post('/{pick_id}', status_code=201)
def record(pick_id: int, data: Measurement, user=Depends(require('shift_coordinator'))):
    return temperatures.record(pick_id, data, user['sub'])
