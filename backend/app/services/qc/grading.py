"""质检评级：由百分制得分判定等级（等级不接受前端直传，避免绕过阈值）。"""

from app.core.config import settings
from app.core.exceptions import ParamError
from app.models.qc.enums import QcGrade

#: 百分制得分边界
MIN_SCORE = 0
MAX_SCORE = 100


def judge_grade(score: int) -> QcGrade:
    """按配置阈值判定等级；得分越界抛 40001。"""
    if score < MIN_SCORE or score > MAX_SCORE:
        raise ParamError(f"质检得分必须在 {MIN_SCORE}~{MAX_SCORE} 之间")
    if score >= settings.QC_GRADE_EXCELLENT_MIN:
        return QcGrade.EXCELLENT
    if score >= settings.QC_GRADE_PASS_MIN:
        return QcGrade.PASS
    return QcGrade.FAIL


__all__ = ["MAX_SCORE", "MIN_SCORE", "judge_grade"]