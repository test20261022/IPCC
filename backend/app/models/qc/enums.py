"""对话质检领域枚举。

复用外呼域的字符串枚举基类（入库值即成员值，便于迁移与人工排查），
状态一律使用 Enum，禁止魔法字符串散落。
"""

from app.models.outbound.enums import OutboundStrEnum


class QcStrEnum(OutboundStrEnum):
    """质检域字符串枚举基类。"""


# ---------------- 对话 ----------------

class ConversationChannel(QcStrEnum):
    """对话渠道。"""

    CHAT = "CHAT"
    VOICE = "VOICE"
    OTHER = "OTHER"


class ConversationSource(QcStrEnum):
    """对话来源：人工录入 / 批量导入。"""

    MANUAL = "MANUAL"
    IMPORT = "IMPORT"


class TranscriptStatus(QcStrEnum):
    """语音转写状态；纯文本对话直接置 NOT_REQUIRED。"""

    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class MessageRole(QcStrEnum):
    """消息说话人：客服（坐席）/ 客户 / 系统。"""

    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"


class MessageSource(QcStrEnum):
    """消息来源：原始文本 / 语音转写。"""

    TEXT = "TEXT"
    ASR = "ASR"


class QcImportFormat(QcStrEnum):
    """对话导入文件格式。"""

    TXT = "TXT"
    JSON = "JSON"
    XLSX = "XLSX"


class QcImportStatus(QcStrEnum):
    """对话导入批次状态。"""

    PENDING = "PENDING"
    PARSING = "PARSING"
    IMPORTING = "IMPORTING"
    SUCCESS = "SUCCESS"
    PARTIAL_FAILED = "PARTIAL_FAILED"
    FAILED = "FAILED"


# ---------------- 质检任务与执行 ----------------

class QcTaskStatus(QcStrEnum):
    """质检任务状态。"""

    DRAFT = "DRAFT"
    DISPATCHED = "DISPATCHED"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class QcDispatchMode(QcStrEnum):
    """派发分片方式：ROUND_ROBIN 交替轮询 / AVERAGE 连续均分段。"""

    ROUND_ROBIN = "ROUND_ROBIN"
    AVERAGE = "AVERAGE"


class QcItemStatus(QcStrEnum):
    """质检明细项状态。"""

    PENDING = "PENDING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    TIMEOUT = "TIMEOUT"


class QcGrade(QcStrEnum):
    """质检等级：优秀 / 及格 / 不及格（由 score 阈值判定，不接受前端直传）。"""

    EXCELLENT = "EXCELLENT"
    PASS = "PASS"
    FAIL = "FAIL"


__all__ = [
    "ConversationChannel",
    "ConversationSource",
    "MessageRole",
    "MessageSource",
    "QcDispatchMode",
    "QcGrade",
    "QcImportFormat",
    "QcImportStatus",
    "QcItemStatus",
    "QcStrEnum",
    "QcTaskStatus",
    "TranscriptStatus",
]