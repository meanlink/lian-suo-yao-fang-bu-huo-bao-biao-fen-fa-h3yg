from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import current_user, require
from . import picklists

router = APIRouter(prefix='/warehouse/picklists', tags=['仓库拣配'])
shift = require('shift_coordinator', 'regional_manager')


class NewPicklist(BaseModel):
    approval_id: int = Field(gt=0)


@router.get('')
def list_picklists(_user=Depends(current_user)):
    return picklists.list_board()


@router.post('', status_code=201)
def reserve(data: NewPicklist, user=Depends(shift)):
    return picklists.reserve(data.approval_id, user['sub'])


@router.put('/{pick_id}/pack')
def pack(pick_id: int, user=Depends(shift)):
    return picklists.pack(pick_id, user['sub'])


@router.put('/{pick_id}/cancel')
def cancel(pick_id: int, user=Depends(shift)):
    return picklists.cancel(pick_id, user['sub'])
