"""SQLAlchemy database models"""
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Text, DateTime, Float, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class StrategyModel(Base):
    """策略数据库模型"""

    __tablename__ = "strategies"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    code = Column(Text, nullable=False)
    config = Column(Text, nullable=False)  # JSON string
    status = Column(String(50), nullable=False)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<StrategyModel(id={self.id}, name={self.name}, status={self.status})>"


class OptimizationModel(Base):
    """优化任务数据库模型"""

    __tablename__ = "optimizations"

    id = Column(String(36), primary_key=True)
    strategy_id = Column(String(36), nullable=False)
    status = Column(String(50), nullable=False)
    config = Column(Text, nullable=False)  # JSON string
    target_metric = Column(String(100), nullable=True)
    parameter_space = Column(Text, nullable=True)  # JSON string
    best_params = Column(Text, nullable=True)  # JSON string
    best_score = Column(Float, nullable=True)
    trials_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<OptimizationModel(id={self.id}, strategy_id={self.strategy_id}, status={self.status})>"


class TrialModel(Base):
    """优化试验数据库模型"""

    __tablename__ = "trials"

    id = Column(String(36), primary_key=True)
    optimization_id = Column(String(36), nullable=False)
    trial_number = Column(Integer, nullable=False)
    params = Column(Text, nullable=False)  # JSON string
    score = Column(Float, nullable=True)
    metrics = Column(Text, nullable=True)  # JSON string
    status = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<TrialModel(id={self.id}, optimization_id={self.optimization_id}, trial_number={self.trial_number})>"
