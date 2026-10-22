"""全局配置：统一从环境变量 / .env 读取，禁止在代码中硬编码敏感信息。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录，保证 alembic / 脚本 / uvicorn 在任意工作目录下都能读到同一份 .env
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # 应用
    APP_NAME: str = "企业管理平台"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # 认证
    SECRET_KEY: str = "dev-only-secret-change-me-at-least-32-bytes"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # bcrypt 成本因子；测试环境可下调以加快用例（生产保持 12）
    BCRYPT_ROUNDS: int = 12

    # 数据库（PostgreSQL）
    DATABASE_URL: str = "postgresql+psycopg://app:app@localhost:5432/app"
    TEST_DATABASE_URL: str = "postgresql+psycopg://app:app@localhost:5432/app_test"
    DB_ECHO: bool = False

    # Redis：留空则自动降级（登出黑名单不生效，仅记录日志）
    REDIS_URL: str = ""

    # CORS，多个来源用英文逗号分隔
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 分页
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 200

    # 本地文件存储（名单导入原始文件、通话录音等）；相对路径基于 backend/ 解析
    STORAGE_DIR: str = "storage"

    # 名单导入
    MAX_IMPORT_FILE_SIZE_MB: int = 10
    MAX_IMPORT_FAILURE_DETAIL: int = 500

    # ---- 外部系统 Provider（§68：一律走配置，禁止硬编码地址与密钥）----
    CALL_GATEWAY_PROVIDER: str = "mock"
    CALL_GATEWAY_URL: str = ""
    CALL_GATEWAY_API_KEY: str = ""
    # 呼叫网关回写呼叫结果的签名密钥（§78 幂等回调）；留空表示未配置，回调接口一律拒绝
    CALL_GATEWAY_CALLBACK_SECRET: str = ""
    # 回调签名时间戳容差（秒），超出容差视为重放攻击
    CALL_GATEWAY_CALLBACK_TOLERANCE_SECONDS: int = 300

    PHONE_PROVIDER: str = "mock"
    PHONE_PROVIDER_URL: str = ""
    PHONE_PROVIDER_API_KEY: str = ""

    IVR_PROVIDER: str = "mock"
    ASR_PROVIDER: str = "mock"
    ASR_PROVIDER_URL: str = ""
    ASR_PROVIDER_API_KEY: str = ""
    TTS_PROVIDER: str = "mock"

    # 所有 Provider 调用的超时与重试（§69：禁止无限等待）
    PROVIDER_TIMEOUT_SECONDS: int = 10
    PROVIDER_MAX_RETRIES: int = 2

    # Mock 呼叫网关行为：接通时长（秒），失败判定规则见 providers/call/mock.py
    MOCK_CALL_CONNECT_DURATION: int = 30

    # ---- 定时任务（§22：超时回收必须有定时任务；MVP 单机，不做分布式调度）----
    SCHEDULER_ENABLED: bool = True
    TIMEOUT_RECYCLE_INTERVAL_SECONDS: int = 30
    RETRY_DISPATCH_INTERVAL_SECONDS: int = 60

    # ---- 坐席分配（§35 预占）----
    # 预占过期时间：超过后坐席自动释放回空闲
    RESERVATION_TIMEOUT_SECONDS: int = 60
    RESERVATION_EXPIRE_INTERVAL_SECONDS: int = 30

    # ---- 回呼（§45 / §46）----
    # 到期回呼派单扫描间隔
    CALLBACK_DISPATCH_INTERVAL_SECONDS: int = 60
    # 单次扫描最多派单的回呼任务数
    CALLBACK_DISPATCH_BATCH_SIZE: int = 50

    # 单次执行批量的最大记录数（并发上限由任务的 max_concurrency 控制）
    EXECUTE_BATCH_SIZE: int = 20

    # ---- 对话质检（QC）----
    # 单个质检任务下每位专家的明细上限，超过则拒绝派发并提示拆批
    QC_MAX_PER_REVIEWER: int = 20000
    # 专家组成员默认单轮质检量（新增成员时的默认值，可逐人覆盖）
    QC_DEFAULT_QUOTA_PER_REVIEWER: int = 50
    # 派发分批提交的批大小，避免单事务写入 10 万行长时间持锁
    QC_DISPATCH_BATCH_SIZE: int = 2000
    # 明细项领取锁定超时（秒），超时后回收为待质检
    QC_ITEM_LOCK_TIMEOUT_SECONDS: int = 1800
    # 超时回收扫描间隔（秒）
    QC_ITEM_RECYCLE_INTERVAL_SECONDS: int = 300
    # 质检报表按天分桶使用的时区（reviewed_at 存 UTC，必须显式换算）
    QC_REPORT_TIMEZONE: str = "Asia/Shanghai"
    # 评级阈值：优秀 / 及格 的下界（百分制）
    QC_GRADE_EXCELLENT_MIN: int = 90
    QC_GRADE_PASS_MIN: int = 60
    # 单次对话导入文件的最大条数
    QC_IMPORT_MAX_ROWS: int = 100000
    # 导入失败明细最多保留条数
    QC_IMPORT_MAX_FAILURE_DETAIL: int = 500

    # 初始超级管理员（首次执行 scripts/init_db.py 时创建）
    FIRST_SUPERUSER: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str = "Admin@123456"
    FIRST_SUPERUSER_NICKNAME: str = "系统管理员"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
