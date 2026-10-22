"""通用 Schema：分页参数等。"""

from fastapi import Query

from app.core.config import settings


class PageParams:
    """统一分页依赖（§57）：?page=1&page_size=20。"""

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(
            default=settings.DEFAULT_PAGE_SIZE,
            ge=1,
            le=settings.MAX_PAGE_SIZE,
            description="每页条数",
        ),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size
