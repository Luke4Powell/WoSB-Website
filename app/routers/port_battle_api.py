from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import require_user_redirect
from app.models import User
from app.port_battle.logic import (
    PortBattleProgramMissing,
    get_default_settings_json,
    get_port_names,
    run_generation,
)

router = APIRouter(prefix="/api/port-battle", tags=["port-battle"])


class TransitionRow(BaseModel):
    port: str = ""
    state: str = ""
    value: str = ""


class GenerateBody(BaseModel):
    days: int = Field(ge=1, le=31)
    windows: dict[str, str]
    ownership: dict[str, str] = Field(default_factory=dict)
    transition_rows: list[TransitionRow] = Field(default_factory=list)


@router.get("/defaults")
async def port_battle_defaults(_user: Annotated[User, Depends(require_user_redirect)]) -> dict:
    data = dict(get_default_settings_json())
    try:
        data["ports"] = get_port_names()
    except PortBattleProgramMissing:
        data["ports"] = []
    return data


@router.post("/generate")
async def port_battle_generate(
    _user: Annotated[User, Depends(require_user_redirect)],
    body: GenerateBody,
) -> dict:
    try:
        mod_data = {
            "days": body.days,
            "windows": body.windows,
            "ownership": body.ownership,
            "transition_rows": [r.model_dump() for r in body.transition_rows],
        }
        return run_generation(mod_data)
    except PortBattleProgramMissing as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
