from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class AIImportWizardRequest(BaseModel):
    term_start: date | None = None
    term_end: date | None = None
    first_week_parity: Literal["odd", "even"] | None = None


class AIImportDraftUpdateRequest(BaseModel):
    wizard: AIImportWizardRequest = Field(default_factory=AIImportWizardRequest)
    payload: dict[str, Any]
