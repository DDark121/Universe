from typing import TypeVar

from pydantic import BaseModel, Field

MAX_PAGE_SIZE = 500


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int


T = TypeVar("T")


class PaginatedResponse[T](BaseModel):
    items: list[T]
    meta: PaginationMeta
