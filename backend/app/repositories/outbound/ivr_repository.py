"""IVR 域数据访问（OB-017）：流程 / 节点 / 流转。"""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.outbound import IvrFlow, IvrNode, IvrTransition
from app.models.outbound.enums import CommonStatus, IvrNodeType


class IvrFlowRepository:
    """IVR 流程查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, flow_id: int) -> IvrFlow | None:
        stmt = select(IvrFlow).where(IvrFlow.id == flow_id, IvrFlow.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_code(self, *, tenant_id: int, code: str) -> IvrFlow | None:
        stmt = select(IvrFlow).where(
            IvrFlow.tenant_id == tenant_id,
            IvrFlow.code == code,
            IvrFlow.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        tenant_id: int | None = None,
        code: str | None = None,
        name: str | None = None,
        status: CommonStatus | None = None,
    ) -> Select:
        stmt = stmt.where(IvrFlow.is_deleted.is_(False))
        if tenant_id is not None:
            stmt = stmt.where(IvrFlow.tenant_id == tenant_id)
        if code:
            stmt = stmt.where(IvrFlow.code.ilike(f"%{code}%"))
        if name:
            stmt = stmt.where(IvrFlow.name.ilike(f"%{name}%"))
        if status is not None:
            stmt = stmt.where(IvrFlow.status == status)
        return stmt

    def list_paged(
        self,
        *,
        page: int,
        page_size: int,
        tenant_id: int | None = None,
        code: str | None = None,
        name: str | None = None,
        status: CommonStatus | None = None,
    ) -> list[IvrFlow]:
        offset = (page - 1) * page_size
        stmt = self._apply_filters(
            select(IvrFlow), tenant_id=tenant_id, code=code, name=name, status=status
        )
        stmt = stmt.order_by(IvrFlow.id.asc()).offset(offset).limit(page_size)
        return list(self.db.execute(stmt).scalars().all())

    def count(
        self,
        *,
        tenant_id: int | None = None,
        code: str | None = None,
        name: str | None = None,
        status: CommonStatus | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(IvrFlow),
            tenant_id=tenant_id,
            code=code,
            name=name,
            status=status,
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> IvrFlow:
        flow = IvrFlow(**values)
        self.db.add(flow)
        self.db.flush()
        return flow


class IvrNodeRepository:
    """IVR 节点查询。节点按 flow 隔离，node_key 在流程内唯一。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, node_id: int) -> IvrNode | None:
        stmt = select(IvrNode).where(IvrNode.id == node_id, IvrNode.is_deleted.is_(False))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_ids(self, node_ids: list[int]) -> list[IvrNode]:
        if not node_ids:
            return []
        stmt = select(IvrNode).where(
            IvrNode.id.in_(node_ids), IvrNode.is_deleted.is_(False)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_key(self, *, flow_id: int, node_key: str) -> IvrNode | None:
        stmt = select(IvrNode).where(
            IvrNode.flow_id == flow_id,
            IvrNode.node_key == node_key,
            IvrNode.is_deleted.is_(False),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_flow(self, flow_id: int) -> list[IvrNode]:
        stmt = (
            select(IvrNode)
            .where(IvrNode.flow_id == flow_id, IvrNode.is_deleted.is_(False))
            .order_by(IvrNode.sort_order.asc(), IvrNode.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_by_type(self, *, flow_id: int, node_type: IvrNodeType) -> int:
        stmt = (
            select(func.count())
            .select_from(IvrNode)
            .where(
                IvrNode.flow_id == flow_id,
                IvrNode.node_type == node_type,
                IvrNode.is_deleted.is_(False),
            )
        )
        return int(self.db.execute(stmt).scalar_one())

    def create(self, **values: object) -> IvrNode:
        node = IvrNode(**values)
        self.db.add(node)
        self.db.flush()
        return node


class IvrTransitionRepository:
    """IVR 流转条件查询。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, transition_id: int) -> IvrTransition | None:
        stmt = select(IvrTransition).where(
            IvrTransition.id == transition_id, IvrTransition.is_deleted.is_(False)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_flow(self, flow_id: int) -> list[IvrTransition]:
        """按「优先级升序、ID 升序」返回，与引擎匹配顺序保持一致。"""
        stmt = (
            select(IvrTransition)
            .where(IvrTransition.flow_id == flow_id, IvrTransition.is_deleted.is_(False))
            .order_by(IvrTransition.priority.asc(), IvrTransition.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_by_from_node(self, from_node_id: int) -> list[IvrTransition]:
        stmt = (
            select(IvrTransition)
            .where(
                IvrTransition.from_node_id == from_node_id,
                IvrTransition.is_deleted.is_(False),
            )
            .order_by(IvrTransition.priority.asc(), IvrTransition.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_by_nodes(self, node_ids: list[int]) -> list[IvrTransition]:
        """命中任一 from_node_id 的流转（删除节点时用于级联清理）。"""
        if not node_ids:
            return []
        stmt = select(IvrTransition).where(
            IvrTransition.from_node_id.in_(node_ids), IvrTransition.is_deleted.is_(False)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_referencing_nodes(self, node_ids: list[int]) -> list[IvrTransition]:
        """以这些节点为目标的流转（删除节点时用于级联清理）。"""
        if not node_ids:
            return []
        stmt = select(IvrTransition).where(
            IvrTransition.to_node_id.in_(node_ids), IvrTransition.is_deleted.is_(False)
        )
        return list(self.db.execute(stmt).scalars().all())

    def exists_same_condition(
        self,
        *,
        from_node_id: int,
        condition_type: str,
        condition_value: str | None,
        exclude_id: int | None = None,
    ) -> bool:
        """同一源节点下相同条件不允许重复配置（避免流转歧义）。"""
        stmt = select(func.count()).select_from(IvrTransition).where(
            IvrTransition.from_node_id == from_node_id,
            IvrTransition.condition_type == condition_type,
            IvrTransition.is_deleted.is_(False),
        )
        stmt = (
            stmt.where(IvrTransition.condition_value.is_(None))
            if condition_value is None
            else stmt.where(IvrTransition.condition_value == condition_value)
        )
        if exclude_id is not None:
            stmt = stmt.where(IvrTransition.id != exclude_id)
        return int(self.db.execute(stmt).scalar_one()) > 0

    def create(self, **values: object) -> IvrTransition:
        transition = IvrTransition(**values)
        self.db.add(transition)
        self.db.flush()
        return transition
