"""名单服务（OB-011 导入 / OB-012 全场景变量）。

导入流程（§24）：上传 → 解析 → 识别表头 → 模板映射 → 字段校验 → 行级校验 → 写入 → 生成导入结果。
幂等（§78）：同一任务下 (user_id, order_id) 已存在时该行按「重复导入」计入失败，不重复落库。
"""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFound, ParamError, StateNotAllowed
from app.models.outbound import OutboundImportBatch, OutboundList, OutboundTask
from app.models.outbound.enums import ImportBatchStatus, ListStatus, TaskStatus
from app.repositories.outbound.list_repository import OutboundListRepository
from app.repositories.outbound.task_repository import OutboundTaskRepository
from app.services.outbound.import_parser import (
    ParsedListRow,
    RowFailure,
    detect_format,
    parse_header,
    parse_rows,
    read_rows,
)
from app.services.outbound.variable_resolver import OutboundVariableResolver
from app.utils.storage import save_bytes

logger = logging.getLogger(__name__)

FAILURE_HEADERS = ("行号", "字段", "失败原因", "原始值")


class OutboundListService:
    """名单业务。事务在本层提交。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = OutboundListRepository(db)
        self.task_repo = OutboundTaskRepository(db)
        self.resolver = OutboundVariableResolver(db)

    # ---------- 导入（OB-011）----------

    def import_file(
        self,
        *,
        task_id: int,
        filename: str,
        content: bytes,
        operator_id: int | None = None,
    ) -> dict[str, Any]:
        task = self._get_task(task_id)
        # 规则 2 的配套约束：任务自动完成后不再接收新名单，
        # 否则会导入一批永远无法执行的死数据（COMPLETED 是终态，不可再流转回 RUNNING）
        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            raise StateNotAllowed(
                f"任务当前为 {task.status.value}，不允许再导入名单"
            )
        self._validate_file(filename, content)

        file_format = detect_format(filename)
        rows = read_rows(content, file_format)
        mapping = parse_header(rows)
        parsed, failures = parse_rows(rows, mapping)

        deduped, duplicate_failures = self._drop_duplicates(task_id, parsed)
        all_failures = [*failures, *duplicate_failures]

        if not parsed and not all_failures:
            raise ParamError("名单中没有有效数据行")

        total_rows = len(parsed) + len(failures)
        relative_path = save_bytes(subdir="imports", filename=filename, content=content)

        batch = self.repo.create_batch(
            tenant_id=task.tenant_id,
            task_id=task_id,
            file_name=filename,
            file_path=relative_path,
            file_size=len(content),
            total_rows=total_rows,
            success_rows=0,
            failed_rows=len(all_failures),
            status=ImportBatchStatus.IMPORTING,
            imported_by=operator_id,
            started_at=datetime.now(timezone.utc),
        )
        # 先提交批次，保证即使后续写入失败也留有审计记录
        self.db.commit()
        batch_id = batch.id

        try:
            inserted = self.repo.bulk_insert(
                [self._to_row_values(batch_id, task, row) for row in deduped]
            )
        except Exception as exc:
            self._mark_batch_failed(batch_id, exc)
            raise

        batch = self.repo.get_batch(batch_id)
        if batch is None:  # pragma: no cover - 提交后必然存在
            raise NotFound("导入批次不存在")
        batch.success_rows = inserted
        batch.failed_rows = len(all_failures)
        batch.status = self._resolve_status(inserted, len(all_failures))
        batch.failed_detail = self._dump_failures(all_failures)
        batch.finished_at = datetime.now(timezone.utc)
        self.db.commit()

        logger.info(
            "名单导入完成：task=%s batch=%s 总=%s 成功=%s 失败=%s",
            task_id,
            batch_id,
            total_rows,
            inserted,
            len(all_failures),
        )
        return {
            "batch_id": batch_id,
            "total_rows": total_rows,
            "success_rows": inserted,
            "failed_rows": len(all_failures),
            "failures": self._dump_failures(all_failures),
        }

    # ---------- 查询 ----------

    def list_lists(
        self, *, page: int, page_size: int, **filters: object
    ) -> tuple[list[OutboundList], int]:
        items = self.repo.list_paged(page=page, page_size=page_size, **filters)
        total = self.repo.count(**filters)
        return items, total

    def get_list(self, list_id: int) -> OutboundList:
        name_list = self.repo.get_by_id(list_id)
        if name_list is None:
            raise NotFound("名单不存在")
        return name_list

    def list_batches(
        self, *, page: int, page_size: int, **filters: object
    ) -> tuple[list[OutboundImportBatch], int]:
        items = self.repo.list_batches_paged(page=page, page_size=page_size, **filters)
        total = self.repo.count_batches(**filters)
        return items, total

    def get_batch(self, batch_id: int) -> OutboundImportBatch:
        batch = self.repo.get_batch(batch_id)
        if batch is None:
            raise NotFound("导入批次不存在")
        return batch

    # ---------- 全场景变量（OB-012）----------

    def resolve_variables(self, list_id: int) -> dict[str, Any]:
        name_list = self.get_list(list_id)
        task = self.task_repo.get_by_id(name_list.task_id)
        return self.resolver.resolve(name_list, task)

    # ---------- 失败明细下载（§25）----------

    def export_failures(self, batch_id: int) -> tuple[str, bytes]:
        batch = self.get_batch(batch_id)
        failures = batch.failed_detail or []

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(FAILURE_HEADERS)
        for item in failures:
            writer.writerow(
                [
                    item.get("row", ""),
                    item.get("field", ""),
                    item.get("reason", ""),
                    item.get("raw", ""),
                ]
            )
        # 加 BOM，保证 Excel 打开中文不乱码
        content = ("\ufeff" + buffer.getvalue()).encode("utf-8")
        return f"import_failures_{batch_id}.csv", content

    # ---------- 内部 ----------

    def _get_task(self, task_id: int) -> OutboundTask:
        task = self.task_repo.get_by_id(task_id)
        if task is None:
            raise NotFound("外呼任务不存在")
        return task

    @staticmethod
    def _validate_file(filename: str, content: bytes) -> None:
        if not filename:
            raise ParamError("请选择要导入的名单文件")
        if not content:
            raise ParamError("名单文件内容为空")
        limit = settings.MAX_IMPORT_FILE_SIZE_MB * 1024 * 1024
        if len(content) > limit:
            raise ParamError(f"文件大小超过限制（{settings.MAX_IMPORT_FILE_SIZE_MB} MB）")

    def _drop_duplicates(
        self, task_id: int, parsed: list[ParsedListRow]
    ) -> tuple[list[ParsedListRow], list[RowFailure]]:
        existing = self.repo.list_existing_keys(task_id)
        kept: list[ParsedListRow] = []
        duplicates: list[RowFailure] = []

        for row in parsed:
            key = (row.user_id, row.order_id)
            # 无 user_id / order_id 的行无法判重，直接放行
            if (row.user_id or row.order_id) and key in existing:
                duplicates.append(
                    RowFailure(
                        row=row.row_no,
                        field="",
                        reason="名单已存在（重复导入）",
                        raw=f"{row.user_id or ''}/{row.order_id or ''}".strip("/"),
                    )
                )
                continue
            kept.append(row)
            existing.add(key)
        return kept, duplicates

    @staticmethod
    def _to_row_values(
        batch_id: int, task: OutboundTask, row: ParsedListRow
    ) -> dict[str, Any]:
        return {
            "tenant_id": task.tenant_id,
            "task_id": task.id,
            "import_batch_id": batch_id,
            "user_id": row.user_id,
            "order_id": row.order_id,
            "recipient_name": row.recipient_name,
            "recipient_phone": row.recipient_phone,
            "phone_numbers": row.phone_numbers,
            "dynamic_fields": row.dynamic_fields,
            "status": ListStatus.PENDING,
            "priority": 0,
            "attempt_count": 0,
            "remark": "",
            "is_deleted": False,
        }

    @staticmethod
    def _resolve_status(success: int, failed: int) -> ImportBatchStatus:
        if failed == 0:
            return ImportBatchStatus.SUCCESS
        if success == 0:
            return ImportBatchStatus.FAILED
        return ImportBatchStatus.PARTIAL_FAILED

    @staticmethod
    def _dump_failures(failures: list[RowFailure]) -> list[dict[str, Any]]:
        """失败明细入库，超出上限时截断（计数仍按真实值）。"""
        limit = settings.MAX_IMPORT_FAILURE_DETAIL
        return [
            {"row": item.row, "field": item.field, "reason": item.reason, "raw": item.raw}
            for item in failures[:limit]
        ]

    def _mark_batch_failed(self, batch_id: int, exc: Exception) -> None:
        self.db.rollback()
        batch = self.repo.get_batch(batch_id)
        if batch is None:  # pragma: no cover
            return
        batch.status = ImportBatchStatus.FAILED
        batch.error_message = str(exc)[:500]
        batch.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        logger.exception("名单导入写入失败：batch=%s", batch_id)
