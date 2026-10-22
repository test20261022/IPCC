"""质检任务 / 明细项状态机单元测试（QC 一期，§18 状态机集中管理）。"""

import pytest

from app.core.exceptions import StateNotAllowed
from app.models.qc.enums import QcItemStatus, QcTaskStatus
from app.services.qc import item_state, task_state


class TestQcTaskState:
    def test_draft_can_dispatch_or_cancel(self) -> None:
        assert task_state.can_transition(QcTaskStatus.DRAFT, QcTaskStatus.DISPATCHED)
        assert task_state.can_transition(QcTaskStatus.DRAFT, QcTaskStatus.CANCELLED)

    def test_draft_cannot_complete_directly(self) -> None:
        assert not task_state.can_transition(QcTaskStatus.DRAFT, QcTaskStatus.COMPLETED)

    def test_dispatched_can_complete(self) -> None:
        """最后一单提交时由条件 UPDATE 从 DISPATCHED 直接置为 COMPLETED。"""
        assert task_state.can_transition(QcTaskStatus.DISPATCHED, QcTaskStatus.COMPLETED)

    def test_terminal_states_have_no_targets(self) -> None:
        assert task_state.allowed_targets(QcTaskStatus.COMPLETED) == []
        assert task_state.allowed_targets(QcTaskStatus.CANCELLED) == []

    def test_ensure_transition_same_status_raises(self) -> None:
        with pytest.raises(StateNotAllowed) as exc:
            task_state.ensure_transition(QcTaskStatus.DRAFT, QcTaskStatus.DRAFT)
        assert exc.value.code == 40902

    def test_ensure_transition_invalid_raises(self) -> None:
        with pytest.raises(StateNotAllowed):
            task_state.ensure_transition(QcTaskStatus.COMPLETED, QcTaskStatus.REVIEWING)

    def test_ensure_editable_only_draft(self) -> None:
        task_state.ensure_editable(QcTaskStatus.DRAFT)
        with pytest.raises(StateNotAllowed):
            task_state.ensure_editable(QcTaskStatus.DISPATCHED)

    def test_ensure_deletable(self) -> None:
        task_state.ensure_deletable(QcTaskStatus.DRAFT)
        task_state.ensure_deletable(QcTaskStatus.CANCELLED)
        with pytest.raises(StateNotAllowed):
            task_state.ensure_deletable(QcTaskStatus.COMPLETED)


class TestQcItemState:
    def test_pending_to_reviewing(self) -> None:
        assert item_state.can_transition(QcItemStatus.PENDING, QcItemStatus.REVIEWING)

    def test_reviewing_back_to_pending_for_recycle(self) -> None:
        assert item_state.can_transition(QcItemStatus.REVIEWING, QcItemStatus.PENDING)

    def test_reviewing_to_completed(self) -> None:
        assert item_state.can_transition(QcItemStatus.REVIEWING, QcItemStatus.COMPLETED)

    def test_completed_is_terminal(self) -> None:
        assert not item_state.can_transition(QcItemStatus.COMPLETED, QcItemStatus.REVIEWING)
        with pytest.raises(StateNotAllowed) as exc:
            item_state.ensure_item_transition(QcItemStatus.COMPLETED, QcItemStatus.REVIEWING)
        assert exc.value.code == 40902

    def test_pending_cannot_jump_to_completed(self) -> None:
        with pytest.raises(StateNotAllowed):
            item_state.ensure_item_transition(QcItemStatus.PENDING, QcItemStatus.COMPLETED)