"""质检评级阈值边界测试（优秀 ≥90 / 及格 ≥60，越界抛 40001）。"""

import pytest

from app.core.config import settings
from app.core.exceptions import ParamError
from app.models.qc.enums import QcGrade
from app.services.qc.grading import judge_grade


def test_thresholds_default() -> None:
    assert settings.QC_GRADE_EXCELLENT_MIN == 90
    assert settings.QC_GRADE_PASS_MIN == 60


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (100, QcGrade.EXCELLENT),
        (90, QcGrade.EXCELLENT),  # 边界：恰好达标优秀
        (89, QcGrade.PASS),  # 边界：差一分降为及格
        (60, QcGrade.PASS),  # 边界：恰好达标及格
        (59, QcGrade.FAIL),  # 边界：差一分不及格
        (0, QcGrade.FAIL),
    ],
)
def test_judge_grade_boundaries(score: int, expected: QcGrade) -> None:
    assert judge_grade(score) is expected


@pytest.mark.parametrize("score", [-1, 101])
def test_judge_grade_out_of_range(score: int) -> None:
    with pytest.raises(ParamError) as exc:
        judge_grade(score)
    assert exc.value.code == 40001