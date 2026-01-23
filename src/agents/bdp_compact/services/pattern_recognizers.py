"""
Pattern Recognizers for Cost Drift Detection.

패턴 인식기 모듈 - False Positive 감소를 위한 패턴 인식 전략.

Features:
- DayOfWeekRecognizer: 평일/주말 패턴 인식
- TrendRecognizer: 점진적 추세 인식
- PatternChain: 여러 인식기를 체인으로 연결

Lambda-Friendly: numpy만 사용, scipy/pandas 의존성 없음.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Protocol

import numpy as np

if TYPE_CHECKING:
    from src.agents.bdp_compact.services.cost_explorer_provider import ServiceCostData

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """패턴 타입."""

    DAY_OF_WEEK = "day_of_week"  # 요일 패턴
    MONTH_CYCLE = "month_cycle"  # 월말/월초
    TREND = "trend"  # 점진적 추세
    SERVICE_PROFILE = "service"  # 서비스 특성
    SEASONALITY = "seasonality"  # 계절성


@dataclass
class PatternContext:
    """패턴 인식 결과 맥락 정보."""

    pattern_type: PatternType
    expected_value: float  # 패턴 기반 예상 비용
    actual_value: float  # 실제 비용
    confidence_adjustment: float  # -0.4 ~ +0.1 범위
    explanation: str  # 한글 설명


class PatternRecognizer(Protocol):
    """패턴 인식기 인터페이스 (Protocol)."""

    def recognize(self, data: "ServiceCostData") -> Optional[PatternContext]:
        """패턴을 인식하고 맥락 정보 반환.

        Args:
            data: 서비스 비용 데이터

        Returns:
            PatternContext if pattern recognized, None otherwise
        """
        ...


class DayOfWeekRecognizer:
    """평일/주말 패턴 인식기.

    같은 요일 타입(평일/주말)끼리 비교하여 정상 범위 판정.

    평일 비용이 주말보다 높은 경우가 많고, 월요일에 비용이 급증하는
    패턴은 정상적인 업무 패턴일 수 있음.

    Adjustment: -0.20 (20% 신뢰도 하향)
    """

    WEEKDAY_ADJUSTMENT = -0.20
    TOLERANCE_RATIO = 0.30  # ±30% 범위를 정상으로 간주

    def recognize(self, data: "ServiceCostData") -> Optional[PatternContext]:
        """평일/주말 패턴 인식.

        Args:
            data: 서비스 비용 데이터

        Returns:
            PatternContext if within same day-type average, None otherwise
        """
        timestamps = data.timestamps
        costs = data.historical_costs

        if len(costs) < 7:  # 최소 1주일 데이터 필요
            return None

        try:
            # 현재 날짜의 요일 타입 확인
            current_date = datetime.fromisoformat(timestamps[-1])
            is_weekend = current_date.weekday() >= 5  # 토(5), 일(6)

            # 같은 요일 타입의 비용만 추출
            same_type_costs = self._filter_by_day_type(costs, timestamps, is_weekend)

            if len(same_type_costs) < 2:
                return None  # 데이터 부족

            expected = float(np.mean(same_type_costs))
            actual = data.current_cost

            if expected <= 0:
                return None

            # 같은 요일 타입 평균 대비 정상 범위 확인
            ratio = actual / expected
            lower_bound = 1 - self.TOLERANCE_RATIO
            upper_bound = 1 + self.TOLERANCE_RATIO

            if lower_bound <= ratio <= upper_bound:
                day_type = "주말" if is_weekend else "평일"
                return PatternContext(
                    pattern_type=PatternType.DAY_OF_WEEK,
                    expected_value=expected,
                    actual_value=actual,
                    confidence_adjustment=self.WEEKDAY_ADJUSTMENT,
                    explanation=f"{day_type} 평균 대비 정상 범위",
                )

            return None

        except (ValueError, IndexError) as e:
            logger.debug(f"DayOfWeekRecognizer failed: {e}")
            return None

    def _filter_by_day_type(
        self, costs: List[float], timestamps: List[str], is_weekend: bool
    ) -> List[float]:
        """요일 타입별 비용 필터링.

        Args:
            costs: 비용 리스트
            timestamps: 타임스탬프 리스트
            is_weekend: 주말 여부

        Returns:
            같은 요일 타입의 비용 리스트
        """
        filtered = []

        for cost, ts in zip(costs[:-1], timestamps[:-1]):  # 현재 제외
            try:
                date = datetime.fromisoformat(ts)
                ts_is_weekend = date.weekday() >= 5

                if ts_is_weekend == is_weekend:
                    filtered.append(cost)
            except ValueError:
                continue

        return filtered


class TrendRecognizer:
    """점진적 추세 인식기.

    선형 회귀로 추세선을 계산하고, 현재 비용이 추세선 기반
    예상 범위 내에 있으면 정상으로 판정.

    비즈니스 성장에 따른 자연스러운 비용 증가를 anomaly로
    오탐하는 것을 방지.

    Adjustment: -0.15 (15% 신뢰도 하향)
    """

    TREND_ADJUSTMENT = -0.15
    DEVIATION_THRESHOLD = 0.15  # 추세선 대비 15% 이내

    def recognize(self, data: "ServiceCostData") -> Optional[PatternContext]:
        """추세 패턴 인식.

        Args:
            data: 서비스 비용 데이터

        Returns:
            PatternContext if within trend line, None otherwise
        """
        costs = data.historical_costs

        if len(costs) < 7:  # 최소 1주일 데이터 필요
            return None

        try:
            # 선형 회귀로 추세선 계산
            x = np.arange(len(costs))
            coeffs = np.polyfit(x, costs, 1)
            slope, intercept = coeffs[0], coeffs[1]

            # 추세선 기반 예상값 (다음 날)
            expected = slope * len(x) + intercept
            actual = data.current_cost

            if expected <= 0:
                return None

            # 추세선 대비 편차 계산
            deviation = abs(actual - expected) / expected

            if deviation <= self.DEVIATION_THRESHOLD:
                return PatternContext(
                    pattern_type=PatternType.TREND,
                    expected_value=expected,
                    actual_value=actual,
                    confidence_adjustment=self.TREND_ADJUSTMENT,
                    explanation=f"추세선 기반 예상 범위 내 (편차: {deviation:.1%})",
                )

            return None

        except (ValueError, np.linalg.LinAlgError) as e:
            logger.debug(f"TrendRecognizer failed: {e}")
            return None


class PatternChain:
    """패턴 인식기 체인.

    여러 패턴 인식기를 체인으로 연결하여 순차적으로 적용.
    책임 연쇄 패턴 (Chain of Responsibility) 구현.

    Usage:
        chain = PatternChain([
            DayOfWeekRecognizer(),
            TrendRecognizer(),
        ])
        contexts = chain.recognize_all(data)
        adjustment = chain.get_total_adjustment(data)
    """

    DEFAULT_MAX_ADJUSTMENT = -0.40  # 최대 40% 하향

    def __init__(
        self,
        recognizers: Optional[List[PatternRecognizer]] = None,
        max_adjustment: Optional[float] = None,
    ):
        """PatternChain 초기화.

        Args:
            recognizers: 패턴 인식기 리스트
            max_adjustment: 최대 조정값 (음수, 기본: -0.4)
        """
        self.recognizers = recognizers or []

        # 환경 변수 또는 파라미터에서 최대 조정값 설정
        if max_adjustment is not None:
            self.max_adjustment = max_adjustment
        else:
            env_max = os.getenv("BDP_PATTERN_MAX_ADJUSTMENT", "0.4")
            try:
                self.max_adjustment = -abs(float(env_max))
            except ValueError:
                self.max_adjustment = self.DEFAULT_MAX_ADJUSTMENT

    def recognize_all(self, data: "ServiceCostData") -> List[PatternContext]:
        """모든 인식된 패턴 반환.

        Args:
            data: 서비스 비용 데이터

        Returns:
            인식된 모든 PatternContext 리스트
        """
        contexts = []

        for recognizer in self.recognizers:
            try:
                ctx = recognizer.recognize(data)
                if ctx is not None:
                    contexts.append(ctx)
            except Exception as e:
                logger.warning(f"Pattern recognizer failed: {e}")
                continue

        return contexts

    def get_total_adjustment(self, data: "ServiceCostData") -> float:
        """모든 패턴의 신뢰도 조정값 합산.

        Args:
            data: 서비스 비용 데이터

        Returns:
            총 조정값 (음수, 최대 max_adjustment)
        """
        contexts = self.recognize_all(data)
        total = sum(ctx.confidence_adjustment for ctx in contexts)

        # 최대 조정값 제한
        return max(total, self.max_adjustment)

    def get_explanations(self, data: "ServiceCostData") -> List[str]:
        """모든 패턴의 설명 반환.

        Args:
            data: 서비스 비용 데이터

        Returns:
            설명 문자열 리스트
        """
        contexts = self.recognize_all(data)
        return [ctx.explanation for ctx in contexts]


def create_default_pattern_chain(
    enabled: Optional[bool] = None,
    max_adjustment: Optional[float] = None,
) -> Optional[PatternChain]:
    """기본 패턴 체인 생성.

    환경 변수 BDP_PATTERN_RECOGNITION으로 활성화/비활성화 제어.

    Args:
        enabled: 활성화 여부 (None이면 환경 변수 사용)
        max_adjustment: 최대 조정값

    Returns:
        PatternChain 또는 None (비활성화 시)
    """
    if enabled is None:
        env_enabled = os.getenv("BDP_PATTERN_RECOGNITION", "true").lower()
        enabled = env_enabled in ("true", "1", "yes")

    if not enabled:
        logger.info("Pattern recognition disabled")
        return None

    chain = PatternChain(
        recognizers=[
            DayOfWeekRecognizer(),
            TrendRecognizer(),
        ],
        max_adjustment=max_adjustment,
    )

    logger.info(
        f"Pattern chain created with {len(chain.recognizers)} recognizers, "
        f"max_adjustment={chain.max_adjustment}"
    )

    return chain
