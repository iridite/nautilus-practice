"""SQLAlchemy repository implementations"""

import json
from typing import Optional, List
from sqlalchemy.orm import Session

from langgraph.application.interfaces.strategy_repository import StrategyRepository
from langgraph.domain.models.strategy import Strategy, StrategyStatus
from langgraph.domain.models.optimization import Optimization, OptimizationStatus
from langgraph.infrastructure.database.models import StrategyModel, OptimizationModel
from langgraph.shared.logging import get_logger

logger = get_logger(__name__)


class SQLAlchemyStrategyRepository(StrategyRepository):
    """SQLAlchemy 策略仓储实现"""

    def __init__(self, session: Session):
        """
        初始化仓储

        Args:
            session: SQLAlchemy 会话
        """
        self.session = session

    async def save(self, strategy: Strategy) -> None:
        """
        保存策略

        Args:
            strategy: 策略领域对象
        """
        # 检查是否已存在
        existing = self.session.query(StrategyModel).filter_by(id=strategy.strategy_id).first()

        if existing:
            # 更新现有记录
            existing.name = strategy.name
            existing.description = strategy.description
            existing.code = strategy.code
            existing.config = json.dumps(strategy.config)
            existing.status = strategy.status.value
            existing.version = strategy.version
        else:
            # 创建新记录
            model = StrategyModel(
                id=strategy.strategy_id,
                name=strategy.name,
                description=strategy.description,
                code=strategy.code,
                config=json.dumps(strategy.config),
                status=strategy.status.value,
                version=strategy.version,
            )
            self.session.add(model)

        self.session.commit()
        logger.info("Strategy saved", strategy_id=strategy.strategy_id, name=strategy.name)

    async def get_by_id(self, strategy_id: str) -> Optional[Strategy]:
        """
        根据 ID 查找策略

        Args:
            strategy_id: 策略 ID

        Returns:
            策略领域对象，如果不存在则返回 None
        """
        model = self.session.query(StrategyModel).filter_by(id=strategy_id).first()
        if not model:
            return None

        return self._to_domain(model)

    def find_by_id(self, strategy_id: str) -> Optional[Strategy]:
        """
        同步版本的 get_by_id（用于测试和非异步场景）

        Args:
            strategy_id: 策略 ID

        Returns:
            策略领域对象，如果不存在则返回 None
        """
        model = self.session.query(StrategyModel).filter_by(id=strategy_id).first()
        if not model:
            return None

        return self._to_domain(model)

    def find_all(self) -> List[Strategy]:
        """
        查找所有策略

        Returns:
            策略列表
        """
        models = self.session.query(StrategyModel).all()
        return [self._to_domain(model) for model in models]

    def find_by_status(self, status: StrategyStatus) -> List[Strategy]:
        """
        根据状态查找策略

        Args:
            status: 策略状态

        Returns:
            策略列表
        """
        models = self.session.query(StrategyModel).filter_by(status=status.value).all()
        return [self._to_domain(model) for model in models]

    def delete(self, strategy_id: str) -> None:
        """
        删除策略

        Args:
            strategy_id: 策略 ID
        """
        self.session.query(StrategyModel).filter_by(id=strategy_id).delete()
        self.session.commit()
        logger.info("Strategy deleted", strategy_id=strategy_id)

    def _to_domain(self, model: StrategyModel) -> Strategy:
        """
        将数据库模型转换为领域对象

        Args:
            model: 数据库模型

        Returns:
            策略领域对象
        """
        strategy = Strategy(
            name=model.name,
            description=model.description,
            code=model.code,
            config=json.loads(model.config),
        )
        # 覆盖自动生成的 ID 和状态
        strategy.strategy_id = model.id
        strategy.status = StrategyStatus(model.status)
        strategy.version = model.version
        strategy.created_at = model.created_at
        strategy.updated_at = model.updated_at

        return strategy


class SQLAlchemyOptimizationRepository:
    """SQLAlchemy 优化仓储实现"""

    def __init__(self, session: Session):
        """
        初始化仓储

        Args:
            session: SQLAlchemy 会话
        """
        self.session = session

    def save(self, optimization: Optimization) -> None:
        """
        保存优化任务

        Args:
            optimization: 优化领域对象
        """
        # 检查是否已存在
        existing = (
            self.session.query(OptimizationModel).filter_by(id=optimization.optimization_id).first()
        )

        if existing:
            # 更新现有记录
            existing.status = optimization.status.value
            existing.parameter_space = json.dumps(optimization.parameter_space)
            existing.best_params = (
                json.dumps(optimization.best_params) if optimization.best_params else None
            )
            existing.best_score = optimization.best_score
            existing.trials_count = len(optimization.trials)
            existing.error_message = optimization.error_message
            existing.started_at = optimization.started_at
            existing.completed_at = optimization.completed_at
        else:
            # 创建新记录
            model = OptimizationModel(
                id=optimization.optimization_id,
                strategy_id=optimization.strategy_id,
                status=optimization.status.value,
                config=json.dumps({}),  # 可以扩展为存储优化配置
                parameter_space=json.dumps(optimization.parameter_space),
                best_params=json.dumps(optimization.best_params)
                if optimization.best_params
                else None,
                best_score=optimization.best_score,
                trials_count=len(optimization.trials),
                error_message=optimization.error_message,
                started_at=optimization.started_at,
                completed_at=optimization.completed_at,
            )
            self.session.add(model)

        self.session.commit()
        logger.info(
            "Optimization saved",
            optimization_id=optimization.optimization_id,
            status=optimization.status.value,
        )

    def find_by_id(self, optimization_id: str) -> Optional[Optimization]:
        """
        根据 ID 查找优化任务

        Args:
            optimization_id: 优化任务 ID

        Returns:
            优化领域对象，如果不存在则返回 None
        """
        model = self.session.query(OptimizationModel).filter_by(id=optimization_id).first()
        if not model:
            return None

        return self._to_domain(model)

    def find_by_strategy_id(self, strategy_id: str) -> List[Optimization]:
        """
        根据策略 ID 查找优化任务

        Args:
            strategy_id: 策略 ID

        Returns:
            优化任务列表
        """
        models = self.session.query(OptimizationModel).filter_by(strategy_id=strategy_id).all()
        return [self._to_domain(model) for model in models]

    def find_by_status(self, status: OptimizationStatus) -> List[Optimization]:
        """
        根据状态查找优化任务

        Args:
            status: 优化状态

        Returns:
            优化任务列表
        """
        models = self.session.query(OptimizationModel).filter_by(status=status.value).all()
        return [self._to_domain(model) for model in models]

    def _to_domain(self, model: OptimizationModel) -> Optimization:
        """
        将数据库模型转换为领域对象

        Args:
            model: 数据库模型

        Returns:
            优化领域对象
        """
        optimization = Optimization(
            strategy_id=model.strategy_id,
            parameter_space=json.loads(model.parameter_space) if model.parameter_space else {},
        )
        # 覆盖自动生成的 ID 和状态
        optimization.optimization_id = model.id
        optimization.status = OptimizationStatus(model.status)
        optimization.best_params = json.loads(model.best_params) if model.best_params else None
        optimization.best_score = model.best_score
        optimization.error_message = model.error_message
        optimization.created_at = model.created_at
        optimization.updated_at = model.updated_at
        optimization.started_at = model.started_at
        optimization.completed_at = model.completed_at

        return optimization
