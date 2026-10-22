"""敏感信息脱敏（§67）：日志中禁止出现完整手机号 / 身份证号。"""


def mask_phone(phone: str | None) -> str:
    """手机号脱敏：13812341234 -> 138****1234。"""
    if not phone:
        return ""
    value = phone.strip()
    if len(value) <= 7:
        return "*" * len(value)
    return f"{value[:3]}****{value[-4:]}"


def mask_id_card(id_card: str | None) -> str:
    """身份证脱敏：仅保留前 6 位与后 4 位。"""
    if not id_card:
        return ""
    value = id_card.strip()
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:6]}{'*' * (len(value) - 10)}{value[-4:]}"
