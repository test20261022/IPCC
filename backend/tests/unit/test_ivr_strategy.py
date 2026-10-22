"""IVR 外呼策略引擎单元测试（OB-017 / §31 / §32）。纯内存，不依赖数据库。"""

import pytest

from app.models.outbound.enums import IvrConditionType, IvrNodeType, NoAgentAction
from app.services.outbound import ivr_strategy
from app.services.outbound.ivr_strategy import (
    INPUT_ASR,
    INPUT_KEY,
    IvrSimulationContext,
    IvrSimulationInput,
    is_valid_time_range,
    queue_available_matches,
    resolve_next,
    simulate,
    time_in_range,
)


class _Node:
    """引擎只读属性，用轻量桩对象即可覆盖，避免拖入 ORM 会话。"""

    def __init__(
        self,
        node_id: int,
        node_key: str,
        node_type: IvrNodeType,
        *,
        content: str = "",
        max_replay: int = 3,
        no_agent_action: NoAgentAction | None = None,
    ) -> None:
        self.id = node_id
        self.node_key = node_key
        self.name = f"节点-{node_key}"
        self.node_type = node_type
        self.content = content
        self.max_replay = max_replay
        self.no_agent_action = no_agent_action


class _Transition:
    def __init__(
        self,
        transition_id: int,
        from_node_id: int,
        to_node_id: int | None,
        condition_type: IvrConditionType,
        condition_value: str | None = None,
        *,
        priority: int = 0,
    ) -> None:
        self.id = transition_id
        self.from_node_id = from_node_id
        self.to_node_id = to_node_id
        self.condition_type = condition_type
        self.condition_value = condition_value
        self.priority = priority


def _inputs(*values: str, input_type: str = INPUT_KEY) -> tuple[IvrSimulationInput, ...]:
    return tuple(IvrSimulationInput(input_type=input_type, value=value) for value in values)


def _actions(result: ivr_strategy.IvrSimulationResult) -> list[str]:
    return [step.action for step in result.steps]


# ---------------- 条件工具 ----------------


class TestTimeRange:
    @pytest.mark.parametrize(
        ("value", "now", "expected"),
        [
            ("09:00-18:00", "12:00", True),
            ("09:00-18:00", "08:59", False),
            ("09:00-18:00", "18:00", True),
            ("09:00-12:00,14:00-18:00", "13:00", False),
            ("09:00-12:00,14:00-18:00", "15:30", True),
            ("22:00-06:00", "23:30", True),  # 跨零点
            ("22:00-06:00", "05:00", True),
            ("22:00-06:00", "12:00", False),
            ("invalid", "12:00", False),
            (None, "12:00", False),
            ("09:00-18:00", None, False),
        ],
    )
    def test_time_in_range(self, value: str | None, now: str | None, expected: bool) -> None:
        assert time_in_range(value, now) is expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("09:00-18:00", True),
            ("09:00-12:00,14:00-18:00", True),
            ("09:00", False),
            ("09:00-", False),
            ("25:00-26:00", False),
            ("09:00-12:00,", False),
            ("", False),
            (None, False),
        ],
    )
    def test_is_valid_time_range(self, value: str | None, expected: bool) -> None:
        assert is_valid_time_range(value) is expected


class TestQueueAvailable:
    @pytest.mark.parametrize(
        ("value", "available", "expected"),
        [
            (None, True, True),
            ("true", True, True),
            ("1", True, True),
            ("false", False, True),
            ("0", False, True),
            ("false", True, False),
            (None, False, False),
            (None, None, False),  # 无法判定时不命中
            ("whatever", True, False),
        ],
    )
    def test_matches(
        self, value: str | None, available: bool | None, expected: bool
    ) -> None:
        assert queue_available_matches(value, available) is expected


class TestResolveNext:
    def test_priority_wins(self) -> None:
        first = _Transition(1, 10, 11, IvrConditionType.KEY, "1", priority=5)
        second = _Transition(2, 10, 12, IvrConditionType.KEY, "1", priority=1)
        assert resolve_next([first, second], input_type=INPUT_KEY, input_value="1") is second

    def test_no_match_returns_none(self) -> None:
        edge = _Transition(1, 10, 11, IvrConditionType.KEY, "1")
        assert resolve_next([edge], input_type=INPUT_KEY, input_value="9") is None

    def test_fallback_matches_any_key(self) -> None:
        fallback = _Transition(1, 10, 11, IvrConditionType.KEY, None)
        assert resolve_next([fallback], input_type=INPUT_KEY, input_value="9") is fallback

    def test_fallback_matches_without_input(self) -> None:
        fallback = _Transition(1, 10, 11, IvrConditionType.KEY, "*")
        assert resolve_next([fallback]) is fallback

    def test_specific_key_not_matched_without_input(self) -> None:
        edge = _Transition(1, 10, 11, IvrConditionType.KEY, "1")
        assert resolve_next([edge]) is None


# ---------------- 有效按键处理 ----------------


class TestValidKeyHandling:
    def test_key_hits_transition_and_records_collected_key(self) -> None:
        collect = _Node(1, "menu", IvrNodeType.COLLECT_DTMF, content="请按 1 转人工")
        agent = _Node(2, "agent", IvrNodeType.HANGUP)
        transitions = [_Transition(1, 1, 2, IvrConditionType.KEY, "1")]

        result = simulate(
            nodes=[collect, agent],
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("1")),
        )

        assert result.collected_keys == ["1"]
        assert result.final_node_key == "agent"
        assert result.end_reason == "HANGUP"
        assert _actions(result) == ["PLAY", "MOVE", "HANGUP"]

    def test_asr_result_keyword_match(self) -> None:
        collect = _Node(1, "voice", IvrNodeType.COLLECT_DTMF)
        target = _Node(2, "done", IvrNodeType.HANGUP)
        transitions = [_Transition(1, 1, 2, IvrConditionType.ASR_RESULT, "咨询")]

        result = simulate(
            nodes=[collect, target],
            transitions=transitions,
            entry_node_key="voice",
            context=IvrSimulationContext(
                inputs=_inputs("我想咨询业务", input_type=INPUT_ASR)
            ),
        )

        assert result.collected_keys == []  # ASR 输入不计入按键
        assert result.final_node_key == "done"
        assert result.end_reason == "HANGUP"

    def test_time_range_branch(self) -> None:
        collect = _Node(1, "menu", IvrNodeType.COLLECT_DTMF)
        work = _Node(2, "work", IvrNodeType.HANGUP)
        off = _Node(3, "off", IvrNodeType.HANGUP)
        transitions = [
            _Transition(1, 1, 2, IvrConditionType.TIME_RANGE, "09:00-18:00"),
            _Transition(2, 1, 3, IvrConditionType.TIME_RANGE, "18:00-23:59"),
        ]

        result = simulate(
            nodes=[collect, work, off],
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("1"), current_time="20:30"),
        )

        assert result.final_node_key == "off"

    def test_queue_available_branch_on_play_node(self) -> None:
        play = _Node(1, "start", IvrNodeType.PLAY, content="欢迎致电")
        agent = _Node(2, "agent", IvrNodeType.HANGUP)
        callback = _Node(3, "cb", IvrNodeType.CALLBACK)
        transitions = [
            _Transition(1, 1, 2, IvrConditionType.QUEUE_AVAILABLE, "true"),
            _Transition(2, 1, 3, IvrConditionType.QUEUE_AVAILABLE, "false"),
        ]

        busy = simulate(
            nodes=[play, agent, callback],
            transitions=transitions,
            entry_node_key="start",
            context=IvrSimulationContext(queue_available=False),
        )
        assert busy.final_node_key == "cb"
        assert busy.end_reason == "CALLBACK"

        free = simulate(
            nodes=[play, agent, callback],
            transitions=transitions,
            entry_node_key="start",
            context=IvrSimulationContext(queue_available=True),
        )
        assert free.final_node_key == "agent"


# ---------------- 非法按键处理 ----------------


class TestIllegalKeyHandling:
    def test_illegal_key_replays_then_continues(self) -> None:
        collect = _Node(
            1, "menu", IvrNodeType.COLLECT_DTMF, content="请按 1 转人工", max_replay=3
        )
        agent = _Node(2, "agent", IvrNodeType.HANGUP)
        transitions = [_Transition(1, 1, 2, IvrConditionType.KEY, "1")]

        # 先按非法键 9（重播），再按 1（命中）
        result = simulate(
            nodes=[collect, agent],
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("9", "1")),
        )

        assert result.collected_keys == ["9", "1"]
        assert result.replay_count == 1
        assert result.final_node_key == "agent"
        assert _actions(result) == ["PLAY", "REPLAY", "PLAY", "MOVE", "HANGUP"]

    def test_illegal_key_exceeding_max_replay_hangs_up(self) -> None:
        collect = _Node(
            1, "menu", IvrNodeType.COLLECT_DTMF, content="请按 1 转人工", max_replay=2
        )
        agent = _Node(2, "agent", IvrNodeType.HANGUP)
        transitions = [_Transition(1, 1, 2, IvrConditionType.KEY, "1")]

        result = simulate(
            nodes=[collect, agent],
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("9", "8", "7")),
        )

        assert result.replay_count == 3
        assert result.end_reason == "HANGUP"
        assert result.final_node_key == "menu"
        assert _actions(result) == ["PLAY", "REPLAY", "PLAY", "REPLAY", "PLAY", "HANGUP"]

    def test_fallback_transition_absorbs_illegal_key(self) -> None:
        collect = _Node(1, "menu", IvrNodeType.COLLECT_DTMF)
        agent = _Node(2, "agent", IvrNodeType.HANGUP)
        end = _Node(3, "end", IvrNodeType.HANGUP)
        transitions = [
            _Transition(1, 1, 2, IvrConditionType.KEY, "1"),
            _Transition(2, 1, 3, IvrConditionType.KEY, "*", priority=9),
        ]

        result = simulate(
            nodes=[collect, agent, end],
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("9")),
        )

        assert result.final_node_key == "end"
        assert result.replay_count == 0

    def test_no_input_ends_flow(self) -> None:
        collect = _Node(1, "menu", IvrNodeType.COLLECT_DTMF)
        agent = _Node(2, "agent", IvrNodeType.HANGUP)
        transitions = [_Transition(1, 1, 2, IvrConditionType.KEY, "1")]

        result = simulate(
            nodes=[collect, agent],
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(),
        )

        assert result.end_reason == "NO_INPUT"
        assert result.final_node_key == "menu"


# ---------------- 转人工路由策略（§32） ----------------


class TestTransferRouting:
    def _flow(self, action: NoAgentAction | None, max_replay: int = 1) -> tuple:
        collect = _Node(1, "menu", IvrNodeType.COLLECT_DTMF)
        transfer = _Node(
            2,
            "transfer",
            IvrNodeType.TRANSFER_AGENT,
            max_replay=max_replay,
            no_agent_action=action,
        )
        hangup = _Node(3, "bye", IvrNodeType.HANGUP)
        transitions = [_Transition(1, 1, 2, IvrConditionType.KEY, "0")]
        return [collect, transfer, hangup], transitions

    def test_transfer_success_when_queue_available(self) -> None:
        nodes, transitions = self._flow(NoAgentAction.HANGUP)
        result = simulate(
            nodes=nodes,
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("0"), queue_available=True),
        )

        assert result.transferred is True
        assert result.end_reason == "TRANSFERRED"
        assert result.final_node_key == "transfer"
        assert result.no_agent_action is None

    @pytest.mark.parametrize(
        ("action", "expected_reason"),
        [
            (NoAgentAction.QUEUE, "QUEUE"),
            (NoAgentAction.CALLBACK, "CALLBACK"),
            (NoAgentAction.HANGUP, "HANGUP"),
        ],
    )
    def test_no_agent_fallback_actions(
        self, action: NoAgentAction, expected_reason: str
    ) -> None:
        nodes, transitions = self._flow(action)
        result = simulate(
            nodes=nodes,
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("0"), queue_available=False),
        )

        assert result.transferred is False
        assert result.end_reason == expected_reason
        assert result.no_agent_action == action.value

    def test_no_agent_replay_exhausts_then_hangs_up(self) -> None:
        nodes, transitions = self._flow(NoAgentAction.REPLAY, max_replay=1)
        result = simulate(
            nodes=nodes,
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("0"), queue_available=False),
        )

        assert result.end_reason == "HANGUP"
        assert result.replay_count == 2
        assert "REPLAY" in _actions(result)

    def test_unknown_queue_state_treated_as_unavailable(self) -> None:
        nodes, transitions = self._flow(NoAgentAction.CALLBACK)
        result = simulate(
            nodes=nodes,
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("0"), queue_available=None),
        )

        assert result.end_reason == "CALLBACK"
        assert result.transferred is False

    def test_transfer_node_ignores_outgoing_transitions(self) -> None:
        """ASSUMPTION-051：转人工节点的出口由 no_agent_action 决定，出向流转不参与匹配。"""
        collect = _Node(1, "menu", IvrNodeType.COLLECT_DTMF)
        transfer = _Node(
            2, "transfer", IvrNodeType.TRANSFER_AGENT, no_agent_action=NoAgentAction.QUEUE
        )
        other = _Node(3, "other", IvrNodeType.HANGUP)
        transitions = [
            _Transition(1, 1, 2, IvrConditionType.KEY, "0"),
            _Transition(2, 2, 3, IvrConditionType.KEY, None),
        ]

        result = simulate(
            nodes=[collect, transfer, other],
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs("0"), queue_available=False),
        )

        assert result.end_reason == "QUEUE"
        assert result.final_node_key == "transfer"


# ---------------- 其他节点与保护 ----------------


class TestNodeBehaviours:
    def test_play_advances_through_fallback_transition(self) -> None:
        play = _Node(1, "welcome", IvrNodeType.PLAY, content="欢迎")
        menu = _Node(2, "menu", IvrNodeType.COLLECT_DTMF)
        byebye = _Node(3, "bye", IvrNodeType.HANGUP)
        transitions = [
            _Transition(1, 1, 2, IvrConditionType.KEY, None),
            _Transition(2, 2, 3, IvrConditionType.KEY, "1"),
        ]

        result = simulate(
            nodes=[play, menu, byebye],
            transitions=transitions,
            entry_node_key="welcome",
            context=IvrSimulationContext(inputs=_inputs("1")),
        )

        assert result.collected_keys == ["1"]
        assert result.end_reason == "HANGUP"

    def test_play_without_transition_ends_flow(self) -> None:
        play = _Node(1, "welcome", IvrNodeType.PLAY, content="欢迎")
        result = simulate(
            nodes=[play], transitions=[], entry_node_key="welcome"
        )
        assert result.end_reason == "FLOW_END"
        assert result.final_node_key == "welcome"

    def test_replay_node_counts_towards_max_replay(self) -> None:
        """REPLAY 节点重播超过 max_replay 后挂断（需要自环流转才能回到自身）。"""
        replay = _Node(1, "again", IvrNodeType.REPLAY, content="重播", max_replay=1)
        transitions = [_Transition(1, 1, 1, IvrConditionType.KEY, None)]

        result = simulate(
            nodes=[replay], transitions=transitions, entry_node_key="again"
        )

        assert result.end_reason == "HANGUP"
        assert result.replay_count == 2
        assert _actions(result) == ["REPLAY", "MOVE", "HANGUP"]

    def test_replay_node_without_transition_ends_flow(self) -> None:
        replay = _Node(1, "again", IvrNodeType.REPLAY, content="重播", max_replay=1)
        result = simulate(nodes=[replay], transitions=[], entry_node_key="again")
        assert result.end_reason == "FLOW_END"
        assert result.replay_count == 1

    def test_callback_node_ends_with_callback(self) -> None:
        callback = _Node(1, "cb", IvrNodeType.CALLBACK)
        result = simulate(nodes=[callback], transitions=[], entry_node_key="cb")
        assert result.end_reason == "CALLBACK"

    def test_entry_node_not_found(self) -> None:
        play = _Node(1, "welcome", IvrNodeType.PLAY)
        result = simulate(nodes=[play], transitions=[], entry_node_key="missing")
        assert result.end_reason == "ENTRY_NOT_FOUND"

    def test_empty_entry_key(self) -> None:
        play = _Node(1, "welcome", IvrNodeType.PLAY)
        result = simulate(nodes=[play], transitions=[], entry_node_key=None)
        assert result.end_reason == "ENTRY_NOT_FOUND"

    def test_self_loop_is_bounded_by_max_steps(self) -> None:
        """自环流转必须被步数上限截断，不能无限推演。"""
        menu = _Node(1, "menu", IvrNodeType.COLLECT_DTMF, max_replay=99)
        transitions = [_Transition(1, 1, 1, IvrConditionType.KEY, None)]

        result = simulate(
            nodes=[menu],
            transitions=transitions,
            entry_node_key="menu",
            context=IvrSimulationContext(inputs=_inputs(*(["1"] * 30))),
            max_steps=10,
        )

        assert result.end_reason == "MAX_STEPS"
        assert len(result.steps) == 11
