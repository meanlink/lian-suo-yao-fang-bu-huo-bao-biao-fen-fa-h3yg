from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from ..auth import current_user, require
from . import recalls

router = APIRouter(prefix='/warehouse/recalls', tags=['批号召回'])
manager = require('regional_manager')


class Notice(BaseModel):
    lot_id: int = Field(gt=0)
    notice_ref: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=70)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=300)]


class Action(BaseModel):
    outlet_ref: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    isolated_units: int = Field(ge=0, le=1000000)


@router.get('')
def list_notices(_user=Depends(current_user)):
    return recalls.list_recalls()


@router.post('', status_code=201)
def open_notice(data: Notice, user=Depends(manager)):
    return recalls.open_notice(data, user['sub'])


@router.put('/{recall_id}/actions/{pick_id}')
def confirm(recall_id: int, pick_id: int, data: Action, user=Depends(require('shift_coordinator'))):
    return recalls.confirm(recall_id, pick_id, data, user['sub'])


@router.put('/{recall_id}/close')
def close(recall_id: int, user=Depends(manager)):
    return recalls.close(recall_id, user['sub'])
