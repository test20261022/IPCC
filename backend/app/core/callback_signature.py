"""呼叫网关回调签名校验（§78：Provider 回调必须可鉴权且幂等）。

真实呼叫网关不持有平台登录态，因此回调接口不能用 JWT 鉴权，改为共享密钥签名：

```text
X-Callback-Timestamp: 1695283200                  # unix 秒
X-Callback-Signature: <hex(HMAC-SHA256)>
签名原文 = f"{timestamp}.{请求体原文}"
密钥     = settings.CALL_GATEWAY_CALLBACK_SECRET（§68：一律走配置）
```

时间戳超出容差即视为重放，直接拒绝（§67：密钥禁止写入日志）。
"""

import hashlib
import hmac
import time

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import AppException, Unauthorized

TIMESTAMP_HEADER = "x-callback-timestamp"
SIGNATURE_HEADER = "x-callback-signature"


def build_signature(secret: str, timestamp: str, body: bytes) -> str:
    """生成回调签名；网关侧与平台侧共用同一实现。"""
    payload = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def verify_callback_signature(request: Request) -> None:
    """FastAPI 依赖：校验回调签名；不读取登录态，失败即拒绝。"""
    secret = settings.CALL_GATEWAY_CALLBACK_SECRET
    if not secret:
        raise AppException("未配置呼叫网关回调密钥 CALL_GATEWAY_CALLBACK_SECRET，回调接口不可用")

    timestamp = request.headers.get(TIMESTAMP_HEADER, "")
    signature = request.headers.get(SIGNATURE_HEADER, "")
    if not timestamp.isdigit() or not signature:
        raise Unauthorized("回调签名缺失")

    if abs(time.time() - int(timestamp)) > settings.CALL_GATEWAY_CALLBACK_TOLERANCE_SECONDS:
        raise Unauthorized("回调时间戳超出容差，疑似重放")

    expected = build_signature(secret, timestamp, await request.body())
    if not hmac.compare_digest(expected, signature):
        raise Unauthorized("回调签名校验失败")
