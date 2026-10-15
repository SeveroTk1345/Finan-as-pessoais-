from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # Sem dados do usuário e sem detalhes de infraestrutura: o endpoint é público.
    return HealthResponse(status="ok")
