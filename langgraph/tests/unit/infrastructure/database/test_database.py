"""Tests for database models and repositories"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from langgraph.infrastructure.database.models import Base, StrategyModel, OptimizationModel
from langgraph.infrastructure.database.repositories import (
    SQLAlchemyStrategyRepository,
    SQLAlchemyOptimizationRepository,
)
from langgraph.domain.models.strategy import Strategy, StrategyStatus
from langgraph.domain.models.optimization import Optimization, OptimizationStatus


@pytest.fixture
def engine():
    """创建内存数据库引擎"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """创建数据库会话"""
    session = Session(engine)
    yield session
    session.close()


class TestStrategyModel:
    """测试策略数据库模型"""

    def test_create_strategy_model(self, session):
        """测试创建策略模型"""
        model = StrategyModel(
            id="test-id",
            name="Test Strategy",
            description="Test description",
            code="class TestStrategy: pass",
            config='{"param": 1}',
            status="draft",
        )
        session.add(model)
        session.commit()

        result = session.query(StrategyModel).filter_by(id="test-id").first()
        assert result is not None
        assert result.name == "Test Strategy"
        assert result.status == "draft"

    def test_strategy_timestamps(self, session):
        """测试策略时间戳"""
        model = StrategyModel(
            id="test-id",
            name="Test",
            code="pass",
            config="{}",
            status="draft",
        )
        session.add(model)
        session.commit()

        assert model.created_at is not None
        assert model.updated_at is not None
        assert isinstance(model.created_at, datetime)


class TestOptimizationModel:
    """测试优化数据库模型"""

    def test_create_optimization_model(self, session):
        """测试创建优化模型"""
        model = OptimizationModel(
            id="opt-id",
            strategy_id="strategy-id",
            status="pending",
            config='{"max_trials": 100}',
        )
        session.add(model)
        session.commit()

        result = session.query(OptimizationModel).filter_by(id="opt-id").first()
        assert result is not None
        assert result.strategy_id == "strategy-id"
        assert result.status == "pending"

    def test_optimization_with_results(self, session):
        """测试带结果的优化"""
        model = OptimizationModel(
            id="opt-id",
            strategy_id="strategy-id",
            status="completed",
            config="{}",
            best_params='{"period": 20}',
            best_score=1.5,
        )
        session.add(model)
        session.commit()

        result = session.query(OptimizationModel).filter_by(id="opt-id").first()
        assert result.best_params == '{"period": 20}'
        assert result.best_score == 1.5


class TestSQLAlchemyStrategyRepository:
    """测试策略仓储实现"""

    @pytest.fixture
    def repository(self, session):
        """创建策略仓储"""
        return SQLAlchemyStrategyRepository(session)

    def test_save_strategy(self, repository, session):
        """测试保存策略"""
        strategy = Strategy(
            name="Test Strategy",
            description="Test description",
            code="class TestStrategy: pass",
            config={"param": 1},
        )

        import asyncio

        asyncio.run(repository.save(strategy))

        # 验证保存成功
        result = session.query(StrategyModel).filter_by(id=strategy.strategy_id).first()
        assert result is not None
        assert result.name == "Test Strategy"

    def test_find_by_id(self, repository):
        """测试根据 ID 查找策略"""
        strategy = Strategy(
            name="Test Strategy",
            description="Test description",
            code="pass",
            config={},
        )
        import asyncio

        asyncio.run(repository.save(strategy))

        found = repository.find_by_id(strategy.strategy_id)
        assert found is not None
        assert found.strategy_id == strategy.strategy_id
        assert found.name == "Test Strategy"

    def test_find_by_id_not_found(self, repository):
        """测试查找不存在的策略"""
        result = repository.find_by_id("non-existent-id")
        assert result is None

    def test_find_all(self, repository):
        """测试查找所有策略"""
        strategy1 = Strategy(name="Strategy 1", description="Desc 1", code="pass", config={})
        strategy2 = Strategy(name="Strategy 2", description="Desc 2", code="pass", config={})

        import asyncio

        asyncio.run(repository.save(strategy1))
        asyncio.run(repository.save(strategy2))

        all_strategies = repository.find_all()
        assert len(all_strategies) == 2
        assert any(s.name == "Strategy 1" for s in all_strategies)
        assert any(s.name == "Strategy 2" for s in all_strategies)

    def test_find_by_status(self, repository):
        """测试根据状态查找策略"""
        draft = Strategy(name="Draft", description="Draft desc", code="pass", config={})
        validated = Strategy(name="Validated", description="Validated desc", code="pass", config={})
        validated.status = StrategyStatus.VALIDATED

        import asyncio

        asyncio.run(repository.save(draft))
        asyncio.run(repository.save(validated))

        drafts = repository.find_by_status(StrategyStatus.DRAFT)
        assert len(drafts) == 1
        assert drafts[0].name == "Draft"

    def test_update_strategy(self, repository):
        """测试更新策略"""
        strategy = Strategy(name="Original", description="Original desc", code="pass", config={})
        import asyncio

        asyncio.run(repository.save(strategy))

        # 更新策略
        strategy.name = "Updated"
        strategy.description = "New description"
        asyncio.run(repository.save(strategy))

        # 验证更新
        found = repository.find_by_id(strategy.strategy_id)
        assert found.name == "Updated"
        assert found.description == "New description"

    def test_delete_strategy(self, repository, session):
        """测试删除策略"""
        strategy = Strategy(name="To Delete", description="Delete desc", code="pass", config={})
        import asyncio

        asyncio.run(repository.save(strategy))

        repository.delete(strategy.strategy_id)

        # 验证删除
        result = session.query(StrategyModel).filter_by(id=strategy.strategy_id).first()
        assert result is None


class TestSQLAlchemyOptimizationRepository:
    """测试优化仓储实现"""

    @pytest.fixture
    def repository(self, session):
        """创建优化仓储"""
        return SQLAlchemyOptimizationRepository(session)

    def test_save_optimization(self, repository, session):
        """测试保存优化"""
        optimization = Optimization(
            strategy_id="strategy-id",
            parameter_space={"period": {"min": 10, "max": 50}},
        )

        repository.save(optimization)

        # 验证保存成功
        result = session.query(OptimizationModel).filter_by(id=optimization.optimization_id).first()
        assert result is not None
        assert result.strategy_id == "strategy-id"

    def test_find_by_id(self, repository):
        """测试根据 ID 查找优化"""
        optimization = Optimization(
            strategy_id="strategy-id",
            parameter_space={},
        )
        repository.save(optimization)

        found = repository.find_by_id(optimization.optimization_id)
        assert found is not None
        assert found.optimization_id == optimization.optimization_id

    def test_find_by_strategy_id(self, repository):
        """测试根据策略 ID 查找优化"""
        opt1 = Optimization(
            strategy_id="strategy-1",
            parameter_space={},
        )
        opt2 = Optimization(
            strategy_id="strategy-1",
            parameter_space={},
        )
        opt3 = Optimization(
            strategy_id="strategy-2",
            parameter_space={},
        )

        repository.save(opt1)
        repository.save(opt2)
        repository.save(opt3)

        results = repository.find_by_strategy_id("strategy-1")
        assert len(results) == 2
        assert all(opt.strategy_id == "strategy-1" for opt in results)

    def test_find_by_status(self, repository):
        """测试根据状态查找优化"""
        pending = Optimization(
            strategy_id="strategy-id",
            parameter_space={},
        )
        running = Optimization(
            strategy_id="strategy-id",
            parameter_space={},
        )
        running.start()

        repository.save(pending)
        repository.save(running)

        running_opts = repository.find_by_status(OptimizationStatus.RUNNING)
        assert len(running_opts) == 1
        assert running_opts[0].status == OptimizationStatus.RUNNING
