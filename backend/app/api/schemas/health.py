from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ComponentStatus(BaseModel):
    status: Literal["ok", "degraded"]
    detail: str


class HealthResponse(BaseModel):
    service: str
    environment: str
    version: str
    status: Literal["ok", "degraded"]
    timestamp: datetime
    database: ComponentStatus

