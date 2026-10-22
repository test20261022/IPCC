"""质检对话批量导入测试：TXT / JSON / XLSX 三种格式与 ext_ref_no 幂等（QC 一期）。"""

import io
import json

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.qc import QcConversation
from app.models.qc.enums import QcImportFormat, QcImportStatus
from tests.conftest import auth_headers

PREFIX = f"{settings.API_V1_PREFIX}/qc/conversations"
IMPORT_PERMS = ("qc:conversation:import", "qc:conversation:list")


def _token(user_token) -> str:
    return user_token("qc_import_admin", *IMPORT_PERMS)


def _post_import(client: TestClient, token: str, tenant_id: int, filename: str, content: bytes):
    return client.post(
        f"{PREFIX}/import",
        headers=auth_headers(token),
        params={"tenant_id": tenant_id},
        files={"file": (filename, content, "application/octet-stream")},
    )


def _json_file() -> bytes:
    payload = [
        {
            "ext_ref_no": "REF-1",
            "started_at": "2026-01-01 10:00:00",
            "agent_name": "客服甲",
            "customer_id": "C-1",
            "messages": [
                {"role": "agent", "content": "您好"},
                {"role": "customer", "content": "你好"},
            ],
        },
        {
            "ext_ref_no": "REF-2",
            "started_at": "2026-01-01 11:00:00",
            "agent_name": "客服乙",
            "messages": [{"role": "客服", "content": "请问需要什么帮助"}],
        },
        {"agent_name": "缺少时间", "messages": []},
    ]
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _txt_file() -> bytes:
    text = (
        "2026-01-02 09:00:00\t客服甲\tC-9\t客服: 您好\t客户: 你好\n"
        "2026-01-02 09:30:00\t客服乙\tC-10\t客服: 请稍等\n"
        "字段不足的一行\n"
    )
    return text.encode("utf-8")


def _xlsx_file() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ext_ref_no", "started_at", "agent_name", "role", "content"])
    sheet.append(["REF-X1", "2026-01-03 08:00:00", "客服丙", "客服", "您好，很高兴为您服务"])
    sheet.append(["REF-X1", "2026-01-03 08:00:00", "客服丙", "客户", "帮我改一下套餐"])
    sheet.append(["REF-X2", "2026-01-03 09:00:00", "客服丁", "客服", "已为您办理"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestImportFormats:
    def test_import_json_partial_failure(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        token = _token(user_token)
        response = _post_import(client, token, tenant.id, "conversations.json", _json_file())
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["format"] == QcImportFormat.JSON.value
        assert data["total_rows"] == 3
        assert data["success_rows"] == 2
        assert data["failed_rows"] == 1
        assert data["status"] == QcImportStatus.PARTIAL_FAILED.value
        assert data["error_detail"][0]["reason"]

        total = db_session.execute(
            select(func.count()).select_from(QcConversation).where(
                QcConversation.tenant_id == tenant.id
            )
        ).scalar_one()
        assert total == 2

    def test_import_txt(self, client: TestClient, user_token, tenant, db_session: Session) -> None:
        token = _token(user_token)
        response = _post_import(client, token, tenant.id, "conversations.txt", _txt_file())
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["format"] == QcImportFormat.TXT.value
        assert data["success_rows"] == 2
        assert data["failed_rows"] == 1

        rows = db_session.execute(
            select(QcConversation).where(QcConversation.tenant_id == tenant.id)
        ).scalars().all()
        assert {row.agent_name for row in rows} == {"客服甲", "客服乙"}

    def test_import_xlsx_groups_messages(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        token = _token(user_token)
        response = _post_import(client, token, tenant.id, "conversations.xlsx", _xlsx_file())
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["format"] == QcImportFormat.XLSX.value
        # REF-X1 的两行合并为一条对话，REF-X2 独立一条
        assert data["success_rows"] == 2
        assert data["failed_rows"] == 0
        assert data["status"] == QcImportStatus.SUCCESS.value

        first = db_session.execute(
            select(QcConversation).where(
                QcConversation.tenant_id == tenant.id, QcConversation.ext_ref_no == "REF-X1"
            )
        ).scalar_one()
        assert first.msg_count == 2


class TestImportIdempotency:
    def test_duplicate_ext_ref_no_skipped(
        self, client: TestClient, user_token, tenant, db_session: Session
    ) -> None:
        token = _token(user_token)
        first = _post_import(client, token, tenant.id, "conversations.json", _json_file())
        assert first.json()["data"]["success_rows"] == 2

        second = _post_import(client, token, tenant.id, "conversations.json", _json_file())
        assert second.status_code == 200, second.text
        data = second.json()["data"]
        # REF-1 / REF-2 已存在 → 计入失败明细，成功 0
        assert data["success_rows"] == 0
        assert data["failed_rows"] == 3
        assert data["status"] == QcImportStatus.FAILED.value

        total = db_session.execute(
            select(func.count()).select_from(QcConversation).where(
                QcConversation.tenant_id == tenant.id
            )
        ).scalar_one()
        assert total == 2

    def test_batch_list(self, client: TestClient, user_token, tenant) -> None:
        token = _token(user_token)
        _post_import(client, token, tenant.id, "conversations.json", _json_file())
        response = client.get(
            f"{PREFIX}/import-batches",
            headers=auth_headers(token),
            params={"tenant_id": tenant.id},
        )
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 1


class TestImportValidation:
    def test_unsupported_extension_rejected(
        self, client: TestClient, user_token, tenant
    ) -> None:
        token = _token(user_token)
        response = _post_import(client, token, tenant.id, "conversations.csv", b"a,b,c\n")
        assert response.status_code == 400
        assert response.json()["code"] == 40001

    def test_empty_file_rejected(self, client: TestClient, user_token, tenant) -> None:
        token = _token(user_token)
        response = _post_import(client, token, tenant.id, "conversations.json", b"")
        assert response.status_code == 400