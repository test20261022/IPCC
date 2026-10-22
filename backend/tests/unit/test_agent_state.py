"""坐席状态机单元测试（§11 / §77）。纯内存，不依赖数据库。"""

import pytest

from app.core.exceptions import StateNotAllowed
from app.models.outbound.enums import AgentStatus
from app.services.outbound import agent_state


class TestAllowedTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (AgentStatus.OFFLINE, AgentStatus.IDLE),
            (AgentStatus.IDLE, AgentStatus.RESERVED),
            (AgentStatus.IDLE, AgentStatus.BUSY),
            (AgentStatus.IDLE, AgentStatus.PAUSED),
            (AgentStatus.IDLE, AgentStatus.OFFLINE),
            (AgentStatus.RESERVED, AgentStatus.BUSY),
            (AgentStatus.RESERVED, AgentStatus.IDLE),
            (AgentStatus.BUSY, AgentStatus.IDLE),
            (AgentStatus.BUSY, AgentStatus.PAUSED),
            (AgentStatus.PAUSED, AgentStatus.IDLE),
        ],
    )
    def test_legal_transition(self, current: AgentStatus, target: AgentStatus) -> None:
        assert agent_state.can_transition(current, target) is True
        agent_state.ensure_transition(current, target)

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            # §11 明确举例：OFFLINE → BUSY 必须拒绝
            (AgentStatus.OFFLINE, AgentStatus.BUSY),
            (AgentStatus.OFFLINE, AgentStatus.RESERVED),
            (AgentStatus.OFFLINE, AgentStatus.PAUSED),
            (AgentStatus.BUSY, AgentStatus.RESERVED),
            (AgentStatus.RESERVED, AgentStatus.PAUSED),
            (AgentStatus.PAUSED, AgentStatus.BUSY),
            (AgentStatus.PAUSED, AgentStatus.RESERVED),
        ],
    )
    def test_illegal_transition(self, current: AgentStatus, target: AgentStatus) -> None:
        assert agent_state.can_transition(current, target) is False
        with pytest.raises(StateNotAllowed) as exc_info:
            agent_state.ensure_transition(current, target)
        assert current.value in str(exc_info.value)
        assert target.value in str(exc_info.value)

    def test_offline_to_busy_message(self) -> None:
        with pytest.raises(StateNotAllowed) as exc_info:
            agent_state.ensure_transition(AgentStatus.OFFLINE, AgentStatus.BUSY)
        assert "离线" in str(exc_info.value)
        assert "不允许从" in str(exc_info.value)


class TestSameStatus:
    def test_same_status_rejected(self) -> None:
        with pytest.raises(StateNotAllowed) as exc_info:
            agent_state.ensure_transition(AgentStatus.BUSY, AgentStatus.BUSY)
        assert "已处于" in str(exc_info.value)


class TestMetadata:
    def test_every_status_has_entry(self) -> None:
        for status in AgentStatus:
            assert status in agent_state.AGENT_TRANSITIONS

    def test_allowed_targets_sorted(self) -> None:
        targets = agent_state.allowed_targets(AgentStatus.IDLE)
        assert targets == [
            AgentStatus.BUSY,
            AgentStatus.OFFLINE,
            AgentStatus.PAUSED,
            AgentStatus.RESERVED,
        ]

    def test_label_includes_both_text_and_code(self) -> None:
        assert agent_state.label(AgentStatus.IDLE) == "空闲（IDLE）"

    def test_reserved_can_return_to_idle(self) -> None:
        """释放预占后坐席必须能回到空闲，否则无法再次派单。"""
        assert agent_state.can_transition(AgentStatus.RESERVED, AgentStatus.IDLE) is True
