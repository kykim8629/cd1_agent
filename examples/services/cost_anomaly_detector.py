"""
Cost Anomaly Detector for BDP Agent.

복합 이상 탐지 알고리즘:
1. 비율 기반 (RATIO): 전 기간 대비 X% 이상 증가
2. 표준편차 기반 (STDDEV): 최근 N일 평균에서 2σ 이상
3. 추세 분석 (TREND): 연속 N일 이상 증가 패턴

복합 점수: 가중치 기반 종합 신뢰도 계산
"""
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger()


class AnomalyType(str, Enum):
    """이상 유형."""
    RATIO = "ratio"           # 급격한 증가/감소
    STDDEV = "stddev"         # 표준편차 기반 이상
    TREND = "trend"           # 지속적 증가 추세
    COMBINED = "combined"     # 복합 이상


class Severity(str, Enum):
    """심각도 레벨."""
    HIGH = "high"       # 0.8 이상
    MEDIUM = "medium"   # 0.5 ~ 0.8
    LOW = "low"         # 0.5 미만


@dataclass
class AnomalyThresholds:
    """이상 탐지 임계값 설정."""

    # 비율 기반 임계값
    ratio_threshold: float = 0.5        # 50% 이상 증가
    ratio_decrease_threshold: float = 0.3  # 30% 이상 감소

    # 표준편차 기반 임계값
    stddev_multiplier: float = 2.0      # 2 시그마

    # 추세 분석 임계값
    trend_consecutive_days: int = 3     # 연속 3일 이상 증가
    trend_min_increase_rate: float = 0.05  # 일 5% 이상 증가

    # 가중치
    ratio_weight: float = 0.4
    stddev_weight: float = 0.35
    trend_weight: float = 0.25

    # 심각도 임계값
    severity_high_threshold: float = 0.8
    severity_medium_threshold: float = 0.5

    # 최소 데이터 요구 사항
    min_data_points: int = 7            # 최소 7일 데이터


@dataclass
class DetectionResult:
    """개별 탐지 결과."""
    detected: bool
    score: float
    anomaly_type: AnomalyType
    details: Dict[str, any] = field(default_factory=dict)


@dataclass
class AnomalyResult:
    """이상 탐지 종합 결과."""
    is_anomaly: bool
    confidence_score: float
    severity: Severity
    service_name: str
    current_cost: float
    previous_cost: float
    cost_change_ratio: float
    detection_results: List[DetectionResult]
    detected_methods: List[str]
    analysis: str
    date: str


class CostAnomalyDetector:
    """비용 이상 탐지 엔진."""

    def __init__(self, thresholds: Optional[AnomalyThresholds] = None):
        """
        초기화.

        Args:
            thresholds: 이상 탐지 임계값 설정
        """
        self.thresholds = thresholds or AnomalyThresholds()
        self.logger = logger.bind(service="cost_anomaly_detector")

    def detect_anomaly(
        self,
        service_name: str,
        costs_by_date: Dict[str, float],
        target_date: Optional[str] = None
    ) -> Optional[AnomalyResult]:
        """
        특정 서비스의 비용 이상 탐지.

        Args:
            service_name: 서비스 이름
            costs_by_date: 날짜별 비용 딕셔너리 (정렬된 순서)
            target_date: 분석 대상 날짜 (None이면 최근 날짜)

        Returns:
            AnomalyResult 또는 None (데이터 부족 시)
        """
        sorted_dates = sorted(costs_by_date.keys())
        costs = [costs_by_date[d] for d in sorted_dates]

        if len(costs) < self.thresholds.min_data_points:
            self.logger.warning(
                "insufficient_data",
                service=service_name,
                data_points=len(costs),
                required=self.thresholds.min_data_points
            )
            return None

        if target_date is None:
            target_date = sorted_dates[-1]

        target_idx = sorted_dates.index(target_date) if target_date in sorted_dates else -1
        if target_idx < 0:
            target_idx = len(costs) - 1
            target_date = sorted_dates[-1]

        current_cost = costs[target_idx]
        previous_cost = costs[target_idx - 1] if target_idx > 0 else costs[0]

        # 각 방법으로 이상 탐지
        ratio_result = self._detect_ratio_anomaly(costs, target_idx)
        stddev_result = self._detect_stddev_anomaly(costs, target_idx)
        trend_result = self._detect_trend_anomaly(costs, target_idx)

        detection_results = [ratio_result, stddev_result, trend_result]

        # 복합 점수 계산
        combined_score = self._calculate_combined_score(
            ratio_result.score,
            stddev_result.score,
            trend_result.score
        )

        # 탐지된 방법들
        detected_methods = [
            r.anomaly_type.value for r in detection_results if r.detected
        ]

        # 이상 여부 판정: 2개 이상 방법에서 탐지 또는 confidence > 0.6
        is_anomaly = len(detected_methods) >= 2 or combined_score > 0.6

        # 심각도 결정
        severity = self._determine_severity(combined_score)

        # 분석 텍스트 생성
        analysis = self._generate_analysis(
            service_name=service_name,
            current_cost=current_cost,
            previous_cost=previous_cost,
            detection_results=detection_results,
            combined_score=combined_score
        )

        # 비용 변화율 계산
        if previous_cost > 0:
            cost_change_ratio = (current_cost - previous_cost) / previous_cost
        else:
            cost_change_ratio = 1.0 if current_cost > 0 else 0.0

        return AnomalyResult(
            is_anomaly=is_anomaly,
            confidence_score=combined_score,
            severity=severity,
            service_name=service_name,
            current_cost=current_cost,
            previous_cost=previous_cost,
            cost_change_ratio=cost_change_ratio,
            detection_results=detection_results,
            detected_methods=detected_methods,
            analysis=analysis,
            date=target_date
        )

    def detect_all_services(
        self,
        costs_data: Dict[str, Dict[str, float]],
        target_date: Optional[str] = None
    ) -> List[AnomalyResult]:
        """
        모든 서비스에 대해 이상 탐지 수행.

        Args:
            costs_data: {service_name: {date: cost}} 형태의 데이터
            target_date: 분석 대상 날짜

        Returns:
            이상이 탐지된 결과 목록 (심각도 순 정렬)
        """
        results = []

        for service_name, costs_by_date in costs_data.items():
            result = self.detect_anomaly(
                service_name=service_name,
                costs_by_date=costs_by_date,
                target_date=target_date
            )
            if result and result.is_anomaly:
                results.append(result)

        # 심각도 및 신뢰도 순 정렬
        severity_order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
        results.sort(key=lambda x: (severity_order[x.severity], -x.confidence_score))

        self.logger.info(
            "anomaly_detection_complete",
            total_services=len(costs_data),
            anomalies_found=len(results)
        )

        return results

    def _detect_ratio_anomaly(
        self,
        costs: List[float],
        target_idx: int
    ) -> DetectionResult:
        """비율 기반 이상 탐지."""
        current = costs[target_idx]
        previous = costs[target_idx - 1] if target_idx > 0 else costs[0]

        if previous <= 0:
            return DetectionResult(
                detected=current > 0,
                score=0.5 if current > 0 else 0.0,
                anomaly_type=AnomalyType.RATIO,
                details={"reason": "previous_cost_zero", "current": current}
            )

        ratio = (current - previous) / previous

        # 증가 이상
        if ratio >= self.thresholds.ratio_threshold:
            # 점수 계산: ratio가 threshold의 2배면 1.0
            score = min(1.0, ratio / (self.thresholds.ratio_threshold * 2))
            return DetectionResult(
                detected=True,
                score=score,
                anomaly_type=AnomalyType.RATIO,
                details={
                    "change_ratio": ratio,
                    "threshold": self.thresholds.ratio_threshold,
                    "direction": "increase"
                }
            )

        # 감소 이상
        if ratio <= -self.thresholds.ratio_decrease_threshold:
            score = min(1.0, abs(ratio) / (self.thresholds.ratio_decrease_threshold * 2))
            return DetectionResult(
                detected=True,
                score=score,
                anomaly_type=AnomalyType.RATIO,
                details={
                    "change_ratio": ratio,
                    "threshold": -self.thresholds.ratio_decrease_threshold,
                    "direction": "decrease"
                }
            )

        return DetectionResult(
            detected=False,
            score=0.0,
            anomaly_type=AnomalyType.RATIO,
            details={"change_ratio": ratio}
        )

    def _detect_stddev_anomaly(
        self,
        costs: List[float],
        target_idx: int
    ) -> DetectionResult:
        """표준편차 기반 이상 탐지."""
        # 대상 날짜 이전 데이터로 통계 계산
        historical_costs = costs[:target_idx] if target_idx > 0 else costs[:-1]

        if len(historical_costs) < 3:
            return DetectionResult(
                detected=False,
                score=0.0,
                anomaly_type=AnomalyType.STDDEV,
                details={"reason": "insufficient_historical_data"}
            )

        mean = statistics.mean(historical_costs)
        stdev = statistics.stdev(historical_costs) if len(historical_costs) > 1 else 0

        if stdev == 0:
            return DetectionResult(
                detected=False,
                score=0.0,
                anomaly_type=AnomalyType.STDDEV,
                details={"reason": "zero_stdev", "mean": mean}
            )

        current = costs[target_idx]
        z_score = (current - mean) / stdev

        threshold = self.thresholds.stddev_multiplier

        if abs(z_score) >= threshold:
            # 점수: z_score가 threshold의 2배면 1.0
            score = min(1.0, abs(z_score) / (threshold * 2))
            return DetectionResult(
                detected=True,
                score=score,
                anomaly_type=AnomalyType.STDDEV,
                details={
                    "z_score": z_score,
                    "mean": mean,
                    "stdev": stdev,
                    "threshold": threshold,
                    "direction": "above" if z_score > 0 else "below"
                }
            )

        return DetectionResult(
            detected=False,
            score=0.0,
            anomaly_type=AnomalyType.STDDEV,
            details={"z_score": z_score, "mean": mean, "stdev": stdev}
        )

    def _detect_trend_anomaly(
        self,
        costs: List[float],
        target_idx: int
    ) -> DetectionResult:
        """추세 분석 기반 이상 탐지."""
        required_days = self.thresholds.trend_consecutive_days
        min_rate = self.thresholds.trend_min_increase_rate

        if target_idx < required_days:
            return DetectionResult(
                detected=False,
                score=0.0,
                anomaly_type=AnomalyType.TREND,
                details={"reason": "insufficient_data_for_trend"}
            )

        # 최근 N일 연속 증가 패턴 확인
        consecutive_increases = 0
        increase_rates = []

        for i in range(target_idx, max(0, target_idx - required_days), -1):
            if i == 0:
                break

            current = costs[i]
            previous = costs[i - 1]

            if previous > 0:
                rate = (current - previous) / previous
                if rate >= min_rate:
                    consecutive_increases += 1
                    increase_rates.append(rate)
                else:
                    break
            else:
                break

        if consecutive_increases >= required_days:
            avg_rate = sum(increase_rates) / len(increase_rates) if increase_rates else 0
            # 점수: 연속 일수와 평균 증가율 기반
            days_factor = min(1.0, consecutive_increases / (required_days * 2))
            rate_factor = min(1.0, avg_rate / (min_rate * 3))
            score = (days_factor + rate_factor) / 2

            return DetectionResult(
                detected=True,
                score=score,
                anomaly_type=AnomalyType.TREND,
                details={
                    "consecutive_days": consecutive_increases,
                    "average_increase_rate": avg_rate,
                    "increase_rates": increase_rates
                }
            )

        return DetectionResult(
            detected=False,
            score=0.0,
            anomaly_type=AnomalyType.TREND,
            details={
                "consecutive_days": consecutive_increases,
                "required_days": required_days
            }
        )

    def _calculate_combined_score(
        self,
        ratio_score: float,
        stddev_score: float,
        trend_score: float
    ) -> float:
        """복합 신뢰도 점수 계산."""
        score = (
            ratio_score * self.thresholds.ratio_weight +
            stddev_score * self.thresholds.stddev_weight +
            trend_score * self.thresholds.trend_weight
        )
        return round(min(1.0, max(0.0, score)), 3)

    def _determine_severity(self, score: float) -> Severity:
        """심각도 결정."""
        if score >= self.thresholds.severity_high_threshold:
            return Severity.HIGH
        elif score >= self.thresholds.severity_medium_threshold:
            return Severity.MEDIUM
        else:
            return Severity.LOW

    def _generate_analysis(
        self,
        service_name: str,
        current_cost: float,
        previous_cost: float,
        detection_results: List[DetectionResult],
        combined_score: float
    ) -> str:
        """분석 텍스트 생성."""
        change_pct = 0
        if previous_cost > 0:
            change_pct = ((current_cost - previous_cost) / previous_cost) * 100

        direction = "increased" if change_pct > 0 else "decreased"
        detected_methods = [r for r in detection_results if r.detected]

        analysis_parts = []

        # 기본 변화 설명
        analysis_parts.append(
            f"{service_name} cost {direction} by {abs(change_pct):.1f}% "
            f"(${previous_cost:.2f} → ${current_cost:.2f})"
        )

        # 탐지 방법별 상세
        for result in detected_methods:
            if result.anomaly_type == AnomalyType.RATIO:
                analysis_parts.append(
                    f"Ratio alert: {result.details.get('direction', 'change')} "
                    f"of {abs(result.details.get('change_ratio', 0)) * 100:.1f}%"
                )
            elif result.anomaly_type == AnomalyType.STDDEV:
                z_score = result.details.get('z_score', 0)
                analysis_parts.append(
                    f"Statistical alert: {abs(z_score):.2f} standard deviations "
                    f"{result.details.get('direction', '')} average"
                )
            elif result.anomaly_type == AnomalyType.TREND:
                days = result.details.get('consecutive_days', 0)
                avg_rate = result.details.get('average_increase_rate', 0) * 100
                analysis_parts.append(
                    f"Trend alert: {days} consecutive days of ~{avg_rate:.1f}% increase"
                )

        # 종합 신뢰도
        analysis_parts.append(f"Combined confidence: {combined_score:.2f}")

        return ". ".join(analysis_parts)


def transform_costs_for_detection(
    costs_by_date: Dict[str, Dict[str, float]]
) -> Dict[str, Dict[str, float]]:
    """
    Cost Explorer 응답을 탐지기 입력 형식으로 변환.

    Args:
        costs_by_date: {date: {service: cost}} 형태

    Returns:
        {service: {date: cost}} 형태
    """
    result: Dict[str, Dict[str, float]] = {}

    for date, services in costs_by_date.items():
        for service, cost in services.items():
            if service not in result:
                result[service] = {}
            result[service][date] = cost

    return result


# 사용 예시
if __name__ == "__main__":
    from datetime import timedelta

    # 테스트 데이터 생성
    def generate_test_data(days: int = 14) -> Dict[str, Dict[str, float]]:
        """테스트용 비용 데이터 생성."""
        import random
        random.seed(42)

        services = ["Amazon EC2", "Amazon RDS", "Amazon S3"]
        data = {}

        for service in services:
            data[service] = {}
            base_cost = random.uniform(50, 200)

            for i in range(days):
                date = (datetime.now() - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
                variance = random.uniform(-0.1, 0.1)

                # EC2에 이상 현상 주입 (마지막 3일 급증)
                if service == "Amazon EC2" and i >= days - 3:
                    cost = base_cost * (1.5 + (i - (days - 3)) * 0.3)
                # RDS에 점진적 증가 패턴
                elif service == "Amazon RDS":
                    cost = base_cost * (1 + i * 0.05 + variance)
                else:
                    cost = base_cost * (1 + variance)

                data[service][date] = round(cost, 2)

        return data

    # 탐지기 초기화
    detector = CostAnomalyDetector()

    # 테스트 데이터 생성
    test_data = generate_test_data(14)

    print("=== Cost Anomaly Detection Test ===\n")

    # 개별 서비스 탐지
    for service, costs in test_data.items():
        result = detector.detect_anomaly(service, costs)
        if result:
            print(f"Service: {service}")
            print(f"  Is Anomaly: {result.is_anomaly}")
            print(f"  Severity: {result.severity.value}")
            print(f"  Confidence: {result.confidence_score:.3f}")
            print(f"  Cost Change: {result.cost_change_ratio * 100:.1f}%")
            print(f"  Detected Methods: {result.detected_methods}")
            print(f"  Analysis: {result.analysis}")
            print()

    # 전체 서비스 탐지
    print("=== All Services Summary ===\n")
    all_results = detector.detect_all_services(test_data)
    print(f"Anomalies found: {len(all_results)}")
    for r in all_results:
        print(f"  [{r.severity.value.upper()}] {r.service_name}: "
              f"score={r.confidence_score:.2f}, change={r.cost_change_ratio * 100:.1f}%")
