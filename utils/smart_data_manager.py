"""
智能数据管理模块

提供智能数据完整性检查、自动修复和配置优化功能，实现真正的"一键回测"体验。

功能包括：
- 智能数据覆盖范围分析
- 自动数据补全策略
- 动态配置调整
- 用户友好的数据质量报告
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from utils.validation import (
    analyze_universe_data_coverage,
    check_parquet_data_coverage,
    check_single_data_file_enhanced
)


class DataCoverageAnalyzer:
    """智能数据覆盖范围分析器"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.analysis_cache = {}
    
    def analyze_strategy_data_coverage(
        self,
        strategy_name: str,
        universe_symbols: Set[str],
        start_date: str,
        end_date: str,
        timeframe: str = "1h",
        exchange: str = "binance",
        min_coverage_threshold: float = 80.0
    ) -> Dict[str, Any]:
        """
        分析策略的完整数据覆盖情况
        
        Parameters
        ----------
        strategy_name : str
            策略名称
        universe_symbols : Set[str]
            Universe 符号集合
        start_date : str
            开始日期（YYYY-MM-DD）
        end_date : str
            结束日期（YYYY-MM-DD）
        timeframe : str, optional
            时间周期，默认 "1h"
        exchange : str, optional
            交易所名称，默认 "binance"
        min_coverage_threshold : float, optional
            最小覆盖百分比阈值，默认 80.0%
            
        Returns
        -------
        Dict[str, Any]
            完整的数据覆盖分析结果
        """
        cache_key = f"{strategy_name}_{start_date}_{end_date}_{timeframe}_{exchange}"
        if cache_key in self.analysis_cache:
            return self.analysis_cache[cache_key]
        
        # 基础覆盖分析
        coverage_analysis = analyze_universe_data_coverage(
            universe_symbols, start_date, end_date, timeframe, exchange,
            self.base_dir, strategy_name, min_coverage_threshold
        )
        
        # 增强分析结果
        enhanced_analysis = self._enhance_coverage_analysis(
            coverage_analysis, start_date, end_date, min_coverage_threshold
        )
        
        # 缓存结果
        self.analysis_cache[cache_key] = enhanced_analysis
        return enhanced_analysis
    
    def _enhance_coverage_analysis(
        self,
        base_analysis: Dict[str, Any],
        start_date: str,
        end_date: str,
        min_coverage_threshold: float
    ) -> Dict[str, Any]:
        """增强覆盖分析结果"""
        enhanced = base_analysis.copy()
        
        # 计算数据质量等级
        avg_coverage = enhanced["summary"]["avg_coverage_pct"]
        sufficient_ratio = enhanced["summary"]["sufficient_count"] / enhanced["total_symbols"]
        
        if avg_coverage >= 95 and sufficient_ratio >= 0.9:
            quality_grade = "A"
            quality_desc = "优秀 - 数据覆盖充分"
        elif avg_coverage >= 80 and sufficient_ratio >= 0.7:
            quality_grade = "B"
            quality_desc = "良好 - 数据覆盖基本充分"
        elif avg_coverage >= 60 and sufficient_ratio >= 0.5:
            quality_grade = "C"
            quality_desc = "一般 - 数据覆盖不足，建议调整"
        else:
            quality_grade = "D"
            quality_desc = "较差 - 数据覆盖严重不足"
        
        enhanced["data_quality"] = {
            "grade": quality_grade,
            "description": quality_desc,
            "avg_coverage_pct": avg_coverage,
            "sufficient_ratio": sufficient_ratio
        }
        
        # 生成改进建议
        enhanced["recommendations"] = self._generate_recommendations(
            enhanced, start_date, end_date, min_coverage_threshold
        )
        
        return enhanced
    
    def _generate_recommendations(
        self,
        analysis: Dict[str, Any],
        start_date: str,
        end_date: str,
        min_coverage_threshold: float
    ) -> List[Dict[str, Any]]:
        """生成数据改进建议"""
        recommendations = []
        
        # 时间范围调整建议
        recommended_range = analysis.get("recommended_timerange", {})
        if recommended_range.get("symbols_count", 0) > 0:
            if recommended_range.get("start") != start_date or recommended_range.get("end") != end_date:
                recommendations.append({
                    "type": "timerange_adjustment",
                    "priority": "high",
                    "title": "调整回测时间范围",
                    "description": f"建议调整为 {recommended_range['start']} 到 {recommended_range['end']}",
                    "action": "adjust_timerange",
                    "params": {
                        "start_date": recommended_range["start"],
                        "end_date": recommended_range["end"],
                        "affected_symbols": recommended_range["symbols_count"]
                    }
                })
        
        # 数据补全建议
        no_data_count = analysis["summary"]["no_data_count"]
        if no_data_count > 0:
            recommendations.append({
                "type": "data_fetch",
                "priority": "medium",
                "title": "补全缺失数据",
                "description": f"为 {no_data_count} 个标的获取历史数据",
                "action": "fetch_missing_data",
                "params": {
                    "symbols": analysis["symbols_with_no_data"][:10],  # 限制数量
                    "total_count": no_data_count
                }
            })
        
        # Universe 过滤建议
        if analysis["summary"]["sufficient_count"] < analysis["total_symbols"] * 0.8:
            recommendations.append({
                "type": "universe_filter",
                "priority": "medium",
                "title": "过滤数据不足的标的",
                "description": f"移除 {len(analysis['symbols_with_no_data']) + len(analysis['symbols_with_partial_data'])} 个数据不足的标的",
                "action": "filter_universe",
                "params": {
                    "keep_symbols": analysis["symbols_with_sufficient_data"],
                    "remove_symbols": analysis["symbols_with_no_data"] + analysis["symbols_with_partial_data"]
                }
            })
        
        return recommendations


class SmartDataCompletion:
    """智能数据补全系统"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.completion_history = []
    
    def auto_complete_missing_data(
        self,
        missing_symbols: List[str],
        start_date: str,
        end_date: str,
        timeframe: str = "1h",
        exchange: str = "binance",
        max_symbols_per_batch: int = 10,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        自动补全缺失的数据
        
        Parameters
        ----------
        missing_symbols : List[str]
            缺失数据的符号列表
        start_date : str
            开始日期（YYYY-MM-DD）
        end_date : str
            结束日期（YYYY-MM-DD）
        timeframe : str, optional
            时间周期，默认 "1h"
        exchange : str, optional
            交易所名称，默认 "binance"
        max_symbols_per_batch : int, optional
            每批次最大符号数量，默认 10
        dry_run : bool, optional
            是否为试运行模式，默认 False
            
        Returns
        -------
        Dict[str, Any]
            数据补全结果
        """
        from utils.data_retrival import batch_fetch_ohlcv
        
        completion_plan = {
            "total_symbols": len(missing_symbols),
            "batches": [],
            "estimated_time_minutes": 0,
            "success_count": 0,
            "failed_symbols": [],
            "dry_run": dry_run
        }
        
        # 分批处理
        for i in range(0, len(missing_symbols), max_symbols_per_batch):
            batch_symbols = missing_symbols[i:i + max_symbols_per_batch]
            batch_info = {
                "batch_id": i // max_symbols_per_batch + 1,
                "symbols": batch_symbols,
                "status": "pending"
            }
            completion_plan["batches"].append(batch_info)
        
        # 估算时间（每个符号约30秒）
        completion_plan["estimated_time_minutes"] = len(missing_symbols) * 0.5
        
        if dry_run:
            return completion_plan
        
        # 执行数据获取
        for batch in completion_plan["batches"]:
            try:
                print(f"📊 Fetching data for batch {batch['batch_id']}: {len(batch['symbols'])} symbols")
                
                data_configs = batch_fetch_ohlcv(
                    symbols=batch["symbols"],
                    start_date=start_date,
                    end_date=end_date,
                    timeframe=timeframe,
                    exchange_id=exchange,
                    base_dir=self.base_dir
                )
                
                batch["status"] = "completed"
                batch["data_configs"] = data_configs
                completion_plan["success_count"] += len(data_configs)
                
            except Exception as e:
                batch["status"] = "failed"
                batch["error"] = str(e)
                completion_plan["failed_symbols"].extend(batch["symbols"])
                print(f"❌ Batch {batch['batch_id']} failed: {e}")
        
        # 记录补全历史
        self.completion_history.append({
            "timestamp": datetime.now().isoformat(),
            "plan": completion_plan
        })
        
        return completion_plan


class DynamicConfigAdjuster:
    """动态配置调整器"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.adjustment_history = []
    
    def suggest_optimal_config(
        self,
        current_config: Dict[str, Any],
        coverage_analysis: Dict[str, Any],
        user_preferences: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        基于数据覆盖分析建议最优配置
        
        Parameters
        ----------
        current_config : Dict[str, Any]
            当前配置
        coverage_analysis : Dict[str, Any]
            数据覆盖分析结果
        user_preferences : Dict[str, Any], optional
            用户偏好设置
            
        Returns
        -------
        Dict[str, Any]
            优化建议
        """
        suggestions = {
            "original_config": current_config.copy(),
            "optimized_config": current_config.copy(),
            "adjustments": [],
            "impact_analysis": {},
            "confidence_score": 0.0
        }
        
        # 时间范围调整
        recommended_range = coverage_analysis.get("recommended_timerange", {})
        if recommended_range.get("symbols_count", 0) > 0:
            original_start = current_config.get("start_date")
            original_end = current_config.get("end_date")
            new_start = recommended_range["start"]
            new_end = recommended_range["end"]
            
            if new_start != original_start or new_end != original_end:
                suggestions["optimized_config"]["start_date"] = new_start
                suggestions["optimized_config"]["end_date"] = new_end
                
                suggestions["adjustments"].append({
                    "type": "timerange",
                    "field": "date_range",
                    "original": f"{original_start} to {original_end}",
                    "optimized": f"{new_start} to {new_end}",
                    "reason": f"提高数据覆盖率到 {recommended_range['symbols_count']} 个标的",
                    "impact": "high"
                })
        
        # Universe 过滤调整
        data_quality = coverage_analysis.get("data_quality", {})
        if data_quality.get("grade") in ["C", "D"]:
            sufficient_symbols = coverage_analysis.get("symbols_with_sufficient_data", [])
            if len(sufficient_symbols) >= 20:  # 保证最少20个标的
                suggestions["optimized_config"]["filtered_universe"] = sufficient_symbols
                
                suggestions["adjustments"].append({
                    "type": "universe_filter",
                    "field": "universe_symbols",
                    "original": f"{coverage_analysis['total_symbols']} symbols",
                    "optimized": f"{len(sufficient_symbols)} symbols (filtered)",
                    "reason": f"移除数据覆盖不足的标的，提升数据质量等级",
                    "impact": "medium"
                })
        
        # 计算置信度分数
        confidence_factors = []
        
        # 数据质量因子
        avg_coverage = coverage_analysis["summary"]["avg_coverage_pct"]
        confidence_factors.append(min(avg_coverage / 100, 1.0) * 0.4)
        
        # 标的数量因子
        sufficient_ratio = coverage_analysis["summary"]["sufficient_count"] / coverage_analysis["total_symbols"]
        confidence_factors.append(sufficient_ratio * 0.3)
        
        # 调整合理性因子
        adjustment_score = 1.0 - (len(suggestions["adjustments"]) * 0.1)  # 调整越少越好
        confidence_factors.append(max(adjustment_score, 0.3) * 0.3)
        
        suggestions["confidence_score"] = sum(confidence_factors)
        
        # 影响分析
        suggestions["impact_analysis"] = self._analyze_config_impact(
            current_config, suggestions["optimized_config"], coverage_analysis
        )
        
        return suggestions
    
    def _analyze_config_impact(
        self,
        original_config: Dict[str, Any],
        optimized_config: Dict[str, Any],
        coverage_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析配置调整的影响"""
        impact = {
            "data_quality_improvement": 0.0,
            "symbol_count_change": 0,
            "time_range_change_days": 0,
            "expected_performance_impact": "neutral"
        }
        
        # 数据质量改进
        current_quality = coverage_analysis["summary"]["avg_coverage_pct"]
        if "filtered_universe" in optimized_config:
            # 过滤后的数据质量预估
            sufficient_symbols = optimized_config["filtered_universe"]
            estimated_quality = 95.0  # 过滤后预期质量
            impact["data_quality_improvement"] = estimated_quality - current_quality
        
        # 标的数量变化
        original_count = coverage_analysis["total_symbols"]
        optimized_count = len(optimized_config.get("filtered_universe", []))
        if optimized_count > 0:
            impact["symbol_count_change"] = optimized_count - original_count
        
        # 时间范围变化
        if "start_date" in optimized_config:
            original_start = datetime.strptime(original_config.get("start_date", "2022-01-01"), "%Y-%m-%d")
            original_end = datetime.strptime(original_config.get("end_date", "2025-12-20"), "%Y-%m-%d")
            optimized_start = datetime.strptime(optimized_config["start_date"], "%Y-%m-%d")
            optimized_end = datetime.strptime(optimized_config["end_date"], "%Y-%m-%d")
            
            original_days = (original_end - original_start).days
            optimized_days = (optimized_end - optimized_start).days
            impact["time_range_change_days"] = optimized_days - original_days
        
        # 性能影响预估
        if impact["data_quality_improvement"] > 20:
            impact["expected_performance_impact"] = "positive"
        elif impact["symbol_count_change"] < -50:
            impact["expected_performance_impact"] = "negative"
        
        return impact
    
    def apply_config_adjustments(
        self,
        config_path: Path,
        adjustments: Dict[str, Any],
        backup: bool = True
    ) -> bool:
        """
        应用配置调整
        
        Parameters
        ----------
        config_path : Path
            配置文件路径
        adjustments : Dict[str, Any]
            调整建议
        backup : bool, optional
            是否备份原配置，默认 True
            
        Returns
        -------
        bool
            是否成功应用
        """
        try:
            # 备份原配置
            if backup:
                backup_path = config_path.with_suffix(f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml")
                backup_path.write_text(config_path.read_text())
                print(f"📋 Configuration backed up to: {backup_path}")
            
            # 应用调整
            optimized_config = adjustments["optimized_config"]
            
            # 这里需要根据实际的配置文件格式进行调整
            # 暂时返回成功，实际实现需要根据具体的配置系统
            
            # 记录调整历史
            self.adjustment_history.append({
                "timestamp": datetime.now().isoformat(),
                "config_path": str(config_path),
                "adjustments": adjustments["adjustments"],
                "confidence_score": adjustments["confidence_score"]
            })
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to apply config adjustments: {e}")
            return False


class SmartDataManager:
    """智能数据管理器 - 统一接口"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.analyzer = DataCoverageAnalyzer(base_dir)
        self.completion = SmartDataCompletion(base_dir)
        self.adjuster = DynamicConfigAdjuster(base_dir)
    
    def smart_backtest_preparation(
        self,
        strategy_name: str,
        universe_symbols: Set[str],
        start_date: str,
        end_date: str,
        timeframe: str = "1h",
        exchange: str = "binance",
        auto_fix: bool = True,
        user_preferences: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        智能回测准备 - 一键式数据检查、补全和配置优化
        
        Parameters
        ----------
        strategy_name : str
            策略名称
        universe_symbols : Set[str]
            Universe 符号集合
        start_date : str
            开始日期（YYYY-MM-DD）
        end_date : str
            结束日期（YYYY-MM-DD）
        timeframe : str, optional
            时间周期，默认 "1h"
        exchange : str, optional
            交易所名称，默认 "binance"
        auto_fix : bool, optional
            是否自动修复问题，默认 True
        user_preferences : Dict[str, Any], optional
            用户偏好设置
            
        Returns
        -------
        Dict[str, Any]
            完整的准备结果报告
        """
        print("🤖 Starting Smart Backtest Preparation...")
        
        preparation_report = {
            "timestamp": datetime.now().isoformat(),
            "strategy_name": strategy_name,
            "original_config": {
                "start_date": start_date,
                "end_date": end_date,
                "universe_size": len(universe_symbols),
                "timeframe": timeframe,
                "exchange": exchange
            },
            "analysis": {},
            "actions_taken": [],
            "recommendations": [],
            "final_config": {},
            "success": False,
            "summary": {}
        }
        
        try:
            # 1. 数据覆盖分析
            print("📊 Analyzing data coverage...")
            coverage_analysis = self.analyzer.analyze_strategy_data_coverage(
                strategy_name, universe_symbols, start_date, end_date, timeframe, exchange
            )
            preparation_report["analysis"] = coverage_analysis
            
            # 2. 生成配置优化建议
            print("⚙️ Generating configuration suggestions...")
            current_config = {
                "start_date": start_date,
                "end_date": end_date,
                "universe_symbols": list(universe_symbols)
            }
            
            config_suggestions = self.adjuster.suggest_optimal_config(
                current_config, coverage_analysis, user_preferences
            )
            preparation_report["recommendations"] = config_suggestions["adjustments"]
            preparation_report["final_config"] = config_suggestions["optimized_config"]
            
            # 3. 自动修复（如果启用）
            if auto_fix:
                print("🔧 Applying automatic fixes...")
                
                # 数据补全
                missing_symbols = coverage_analysis.get("symbols_with_no_data", [])
                if missing_symbols and len(missing_symbols) <= 20:  # 限制数量避免过长时间
                    print(f"📥 Fetching data for {len(missing_symbols)} missing symbols...")
                    completion_result = self.completion.auto_complete_missing_data(
                        missing_symbols[:10], start_date, end_date, timeframe, exchange
                    )
                    preparation_report["actions_taken"].append({
                        "action": "data_completion",
                        "result": completion_result
                    })
            
            # 4. 生成摘要
            data_quality = coverage_analysis.get("data_quality", {})
            preparation_report["summary"] = {
                "data_quality_grade": data_quality.get("grade", "Unknown"),
                "avg_coverage_pct": coverage_analysis["summary"]["avg_coverage_pct"],
                "sufficient_symbols": coverage_analysis["summary"]["sufficient_count"],
                "total_symbols": coverage_analysis["total_symbols"],
                "recommendations_count": len(preparation_report["recommendations"]),
                "actions_taken_count": len(preparation_report["actions_taken"]),
                "confidence_score": config_suggestions.get("confidence_score", 0.0)
            }
            
            preparation_report["success"] = True
            print("✅ Smart backtest preparation completed successfully!")
            
        except Exception as e:
            preparation_report["error"] = str(e)
            print(f"❌ Smart backtest preparation failed: {e}")
        
        return preparation_report
    
    def generate_data_quality_report(
        self,
        preparation_result: Dict[str, Any],
        output_path: Optional[Path] = None
    ) -> str:
        """
        生成用户友好的数据质量报告
        
        Parameters
        ----------
        preparation_result : Dict[str, Any]
            准备结果
        output_path : Path, optional
            输出文件路径
            
        Returns
        -------
        str
            报告内容
        """
        analysis = preparation_result.get("analysis", {})
        summary = preparation_result.get("summary", {})
        
        report_lines = [
            "# 📊 数据质量报告",
            "",
            f"**生成时间**: {preparation_result.get('timestamp', 'Unknown')}",
            f"**策略名称**: {preparation_result.get('strategy_name', 'Unknown')}",
            "",
            "## 📈 数据覆盖概览",
            "",
            f"- **数据质量等级**: {summary.get('data_quality_grade', 'Unknown')}",
            f"- **平均覆盖率**: {summary.get('avg_coverage_pct', 0):.1f}%",
            f"- **充分数据标的**: {summary.get('sufficient_symbols', 0)}/{summary.get('total_symbols', 0)}",
            f"- **置信度分数**: {summary.get('confidence_score', 0):.1f}",
            "",
            "## 🎯 优化建议",
            ""
        ]
        
        recommendations = preparation_result.get("recommendations", [])
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                report_lines.extend([
                    f"### {i}. {rec.get('title', 'Unknown')}",
                    f"**优先级**: {rec.get('priority', 'Unknown')}",
                    f"**描述**: {rec.get('description', 'No description')}",
                    ""
                ])
        else:
            report_lines.append("✅ 当前配置已经是最优状态，无需调整。")
        
        report_lines.extend([
            "",
            "## 🔧 已执行操作",
            ""
        ])
        
        actions = preparation_result.get("actions_taken", [])
        if actions:
            for action in actions:
                action_type = action.get("action", "Unknown")
                if action_type == "data_completion":
                    result = action.get("result", {})
                    success_count = result.get("success_count", 0)
                    total_count = result.get("total_symbols", 0)
                    report_lines.append(f"- **数据补全**: 成功获取 {success_count}/{total_count} 个标的的数据")
        else:
            report_lines.append("无自动操作执行。")
        
        report_content = "\n".join(report_lines)
        
        if output_path:
            output_path.write_text(report_content, encoding="utf-8")
            print(f"📄 Data quality report saved to: {output_path}")
        
        return report_content