"""回呼任务状态机单元测试（§46 / §77）。纯内存，不依赖数据库。"""

import pytest

from app.core.exceptions import StateNotAllowed
from app.models.outbound.enums import CallbackStatus
from app.services.outbound import callback_state


class TestAllowedTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (CallbackStatus.PENDING, CallbackStatus.ASSIGNED),
            (CallbackStatus.PENDING, CallbackStatus.CANCELLED),
            (CallbackStatus.ASSIGNED, CallbackStatus.CALLING),
            (CallbackStatus.ASSIGNED, CallbackStatus.SUCCESS),
            (CallbackStatus.ASSIGNED, CallbackStatus.FAILED),
            (CallbackStatus.ASSIGNED, CallbackStatus.PENDING),
            (CallbackStatus.ASSIGNED, CallbackStatus.CANCELLED),
            (CallbackStatus.CALLING, CallbackStatus.SUCCESS),
            (CallbackStatus.CALLING, CallbackStatus.FAILED),
            (CallbackStatus.CALLING, CallbackStatus.PENDING),
            (CallbackStatus.CALLING, CallbackStatus.CANCELLED),
            (CallbackStatus.FAILED, CallbackStatus.PENDING),
        ],
    )
    def test_legal_transition(self, current: CallbackStatus, target: CallbackStatus) -> None:
        assert callback_state.can_transition(current, target) is True
        callback_state.ensure_transition(current, target)  # 不应抛错

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (CallbackStatus.PENDING, CallbackStatus.CALLING),
            (CallbackStatus.PENDING, CallbackStatus.SUCCESS),
            (CallbackStatus.PENDING, CallbackStatus.FAILED),
            (CallbackStatus.SUCCESS, CallbackStatus.PENDING),
            (CallbackStatus.SUCCESS, CallbackStatus.FAILED),
            (CallbackStatus.CANCELLED, CallbackStatus.PENDING),
            (CallbackStatus.CANCELLED, CallbackStatus.ASSIGNED),
        ],
    )
    def test_illegal_transition(self, current: CallbackStatus, target: CallbackStatus) -> None:
        assert callback_state.can_transition(current, target) is False
        with pytest.raises(StateNotAllowed) as exc_info:
            callback_state.ensure_transition(current, target)
        assert current.value in str(exc_info.value)
        assert target.value in str(exc_info.value)

    def test_same_status_rejected(self) -> None:
        with pytest.raises(StateNotAllowed):
            callback_state.ensure_transition(
                CallbackStatus.PENDING, CallbackStatus.PENDING
            )


class TestTerminalStates:
    @pytest.mark.parametrize(
        "status",
        [CallbackStatus.SUCCESS, CallbackStatus.FAILED, CallbackStatus.CANCELLED],
    )
    def test_final_statuses(self, status: CallbackStatus) -> None:
        assert status in callback_state.FINAL_STATUSES

    @pytest.mark.parametrize(
        "status", [CallbackStatus.PENDING, CallbackStatus.ASSIGNED, CallbackStatus.CALLING]
    )
    def test_non_final_statuses(self, status: CallbackStatus) -> None:
        assert status not in callback_state.FINAL_STATUSES

    def test_success_and_cancelled_have_no_targets(self) -> None:
        assert callback_state.allowed_targets(CallbackStatus.SUCCESS) == []
        assert callback_state.allowed_targets(CallbackStatus.CANCELLED) == []

    def test_failed_can_requeue(self) -> None:
        assert callback_state.allowed_targets(CallbackStatus.FAILED) == [
            CallbackStatus.PENDING
        ]


class TestGuards:
    def test_assignable_only_pending(self) -> None:
        callback_state.ensure_assignable(CallbackStatus.PENDING)
        for status in (
            CallbackStatus.ASSIGNED,
            CallbackStatus.CALLING,
            CallbackStatus.SUCCESS,
        ):
            with pytest.raises(StateNotAllowed):
                callback_state.ensure_assignable(status)

    def test_callable_only_assigned(self) -> None:
        callback_state.ensure_callable(CallbackStatus.ASSIGNED)
        for status in (CallbackStatus.PENDING, CallbackStatus.CALLING, CallbackStatus.FAILED):
            with pytest.raises(StateNotAllowed):
                callback_state.ensure_callable(status)

    def test_cancellable_excludes_final(self) -> None:
        for status in (
            CallbackStatus.PENDING,
            CallbackStatus.ASSIGNED,
            CallbackStatus.CALLING,
        ):
            callback_state.ensure_cancellable(status)
        for status in (
            CallbackStatus.SUCCESS,
            CallbackStatus.FAILED,
            CallbackStatus.CANCELLED,
        ):
            with pytest.raises(StateNotAllowed):
                callback_state.ensure_cancellable(status)

    def test_label_contains_code(self) -> None:
        assert "待回呼" in callback_state.label(CallbackStatus.PENDING)
        assert "PENDING" in callback_state.label(CallbackStatus.PENDING)
