from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ApiMessage(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class IdResponse(BaseModel):
    id: UUID
