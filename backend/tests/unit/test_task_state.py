"""外呼任务状态机单元测试（§18 / §77）。纯内存，不依赖数据库。"""

import pytest

from app.core.exceptions import StateNotAllowed
from app.models.outbound.enums import TaskStatus
from app.services.outbound import task_state


class TestAllowedTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (TaskStatus.DRAFT, TaskStatus.READY),
            (TaskStatus.DRAFT, TaskStatus.CANCELLED),
            (TaskStatus.READY, TaskStatus.RUNNING),
            (TaskStatus.READY, TaskStatus.PAUSED),
            (TaskStatus.READY, TaskStatus.DRAFT),
            (TaskStatus.READY, TaskStatus.CANCELLED),
            (TaskStatus.RUNNING, TaskStatus.PAUSED),
            (TaskStatus.RUNNING, TaskStatus.COMPLETED),
            (TaskStatus.RUNNING, TaskStatus.CANCELLED),
            (TaskStatus.PAUSED, TaskStatus.RUNNING),
            (TaskStatus.PAUSED, TaskStatus.CANCELLED),
        ],
    )
    def test_legal_transition(self, current: TaskStatus, target: TaskStatus) -> None:
        assert task_state.can_transition(current, target) is True
        task_state.ensure_transition(current, target)  # 不应抛错

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (TaskStatus.DRAFT, TaskStatus.RUNNING),
            (TaskStatus.DRAFT, TaskStatus.COMPLETED),
            (TaskStatus.RUNNING, TaskStatus.DRAFT),
            (TaskStatus.RUNNING, TaskStatus.READY),
            (TaskStatus.COMPLETED, TaskStatus.READY),
            (TaskStatus.COMPLETED, TaskStatus.RUNNING),
            (TaskStatus.CANCELLED, TaskStatus.DRAFT),
            (TaskStatus.CANCELLED, TaskStatus.RUNNING),
            (TaskStatus.PAUSED, TaskStatus.DRAFT),
            (TaskStatus.PAUSED, TaskStatus.COMPLETED),
        ],
    )
    def test_illegal_transition(self, current: TaskStatus, target: TaskStatus) -> None:
        assert task_state.can_transition(current, target) is False
        with pytest.raises(StateNotAllowed) as exc_info:
            task_state.ensure_transition(current, target)
        assert current.value in str(exc_info.value)
        assert target.value in str(exc_info.value)


class TestTerminalStates:
    def test_completed_is_terminal(self) -> None:
        assert task_state.allowed_targets(TaskStatus.COMPLETED) == []

    def test_cancelled_is_terminal(self) -> None:
        assert task_state.allowed_targets(TaskStatus.CANCELLED) == []

    def test_same_status_is_rejected(self) -> None:
        with pytest.raises(StateNotAllowed) as exc_info:
            task_state.ensure_transition(TaskStatus.RUNNING, TaskStatus.RUNNING)
        assert "已处于" in str(exc_info.value)

    def test_allowed_targets_sorted_and_complete(self) -> None:
        targets = task_state.allowed_targets(TaskStatus.READY)
        assert targets == [
            TaskStatus.CANCELLED,
            TaskStatus.DRAFT,
            TaskStatus.PAUSED,
            TaskStatus.RUNNING,
        ]


class TestEditAndDeleteGuards:
    @pytest.mark.parametrize(
        "status",
        [TaskStatus.DRAFT, TaskStatus.READY, TaskStatus.PAUSED],
    )
    def test_editable_statuses(self, status: TaskStatus) -> None:
        task_state.ensure_editable(status)

    @pytest.mark.parametrize(
        "status",
        [TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.CANCELLED],
    )
    def test_non_editable_statuses(self, status: TaskStatus) -> None:
        with pytest.raises(StateNotAllowed):
            task_state.ensure_editable(status)

    @pytest.mark.parametrize("status", [TaskStatus.DRAFT, TaskStatus.CANCELLED])
    def test_deletable_statuses(self, status: TaskStatus) -> None:
        task_state.ensure_deletable(status)

    @pytest.mark.parametrize(
        "status",
        [TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.COMPLETED],
    )
    def test_non_deletable_statuses(self, status: TaskStatus) -> None:
        with pytest.raises(StateNotAllowed):
            task_state.ensure_deletable(status)

    def test_every_status_has_transition_entry(self) -> None:
        """流转表必须覆盖全部状态，避免新增状态后静默不可流转。"""
        for status in TaskStatus:
            assert status in task_state.TASK_TRANSITIONS
