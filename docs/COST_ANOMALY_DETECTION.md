# AWS Cost Anomaly Detection

AWS Cost Explorer를 활용한 다중 계정 비용 이상 탐지 시스템.

## 목차

1. [개요](#개요)
2. [아키텍처](#아키텍처)
3. [이상 탐지 알고리즘](#이상-탐지-알고리즘)
4. [Cross-Account 설정](#cross-account-설정)
5. [환경 변수](#환경-변수)
6. [DynamoDB 테이블](#dynamodb-테이블)
7. [EventBridge 이벤트](#eventbridge-이벤트)
8. [사용법](#사용법)
9. [Mock 테스트](#mock-테스트)

---

## 개요

BDP Agent의 비용 이상 탐지 모듈은 AWS Cost Explorer API를 통해 다중 AWS 계정의 비용을 분석하고, 복합적인 이상 탐지 알고리즘을 적용하여 비용 급증, 점진적 증가, 통계적 이상을 감지합니다.

### 주요 기능

- **Cross-Account 지원**: AssumeRole을 통한 다중 계정 비용 조회
- **복합 이상 탐지**: 비율/표준편차/추세 분석 기반 탐지
- **서비스별 분석**: AWS 서비스별 상세 비용 분석
- **자동 알림**: EventBridge를 통한 심각도별 알림
- **이력 관리**: DynamoDB 기반 비용 이력 및 이상 현상 추적

---

## 아키텍처

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  EventBridge    │────▶│  Cost Detection  │────▶│  Cost Explorer  │
│  (스케줄 트리거)  │     │     Lambda       │     │      API        │
└─────────────────┘     └────────┬─────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
            ┌───────────┐ ┌───────────┐ ┌───────────┐
            │ Anomaly   │ │ DynamoDB  │ │EventBridge│
            │ Detector  │ │  Tables   │ │  Events   │
            └───────────┘ └───────────┘ └───────────┘
```

### 컴포넌트

| 컴포넌트 | 파일 | 설명 |
|---------|------|------|
| Cost Explorer Client | `examples/services/cost_explorer_client.py` | Cost Explorer API 추상화 |
| Anomaly Detector | `examples/services/cost_anomaly_detector.py` | 이상 탐지 알고리즘 엔진 |
| Cost Detection Handler | `examples/handlers/cost_detection_handler.py` | Lambda 핸들러 |

---

## 이상 탐지 알고리즘

### 1. 비율 기반 탐지 (Ratio)

전 기간 대비 비용 변화율을 분석합니다.

```python
ratio = (current_cost - previous_cost) / previous_cost

# 기본 임계값
- 증가 임계값: 50% (ratio_threshold: 0.5)
- 감소 임계값: 30% (ratio_decrease_threshold: 0.3)
```

**탐지 예시**:
- EC2 비용이 어제 $100 → 오늘 $160 (+60%) → **탐지됨**

### 2. 표준편차 기반 탐지 (StdDev)

과거 N일간 평균에서의 편차를 분석합니다.

```python
z_score = (current_cost - mean) / stdev

# 기본 임계값
- 표준편차 배수: 2.0 (2σ 이상 시 탐지)
```

**탐지 예시**:
- 평균 $100, 표준편차 $15인 서비스에서 $140 발생 (z=2.67) → **탐지됨**

### 3. 추세 분석 탐지 (Trend)

연속적인 비용 증가 패턴을 분석합니다.

```python
# 기본 임계값
- 연속 증가 일수: 3일 (trend_consecutive_days)
- 일 최소 증가율: 5% (trend_min_increase_rate)
```

**탐지 예시**:
- Day1 $100 → Day2 $108 (+8%) → Day3 $118 (+9%) → Day4 $130 (+10%) → **탐지됨**

### 복합 점수 계산

각 방법의 점수를 가중 평균으로 결합합니다.

```python
combined_score = (
    ratio_score * 0.40 +    # 40% 가중치
    stddev_score * 0.35 +   # 35% 가중치
    trend_score * 0.25      # 25% 가중치
)
```

### 이상 판정 기준

- **2개 이상 방법에서 탐지** 또는 **combined_score > 0.6**

### 심각도 분류

| 심각도 | 조건 | 조치 |
|--------|------|------|
| HIGH | score ≥ 0.8 | Slack + Email 알림 |
| MEDIUM | 0.5 ≤ score < 0.8 | Slack 알림 |
| LOW | score < 0.5 | 로그 기록 |

---

## Cross-Account 설정

### IAM Role 설정

각 대상 계정에 Cost Explorer 읽기 권한이 있는 IAM Role을 생성합니다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    }
  ]
}
```

### Trust Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::MANAGEMENT_ACCOUNT_ID:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "your-external-id"
        }
      }
    }
  ]
}
```

### Lambda 입력 예시

```json
{
  "start_date": "2024-01-01",
  "end_date": "2024-01-15",
  "granularity": "DAILY",
  "group_by": ["SERVICE"],
  "cross_accounts": [
    {
      "role_arn": "arn:aws:iam::111122223333:role/CostExplorerReadOnly",
      "account_alias": "Production",
      "external_id": "your-external-id"
    },
    {
      "role_arn": "arn:aws:iam::444455556666:role/CostExplorerReadOnly",
      "account_alias": "Staging"
    }
  ]
}
```

---

## 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `AWS_MOCK` | Mock 모드 활성화 | `false` |
| `COST_HISTORY_TABLE` | 비용 이력 테이블 | `bdp-cost-history` |
| `COST_ANOMALY_TABLE` | 이상 현상 추적 테이블 | `bdp-cost-anomaly-tracking` |
| `COST_TARGET_ACCOUNTS` | Cross-Account 설정 (JSON) | `[]` |
| `EVENT_BUS_NAME` | EventBridge 버스 이름 | `default` |

### COST_TARGET_ACCOUNTS 형식

```bash
export COST_TARGET_ACCOUNTS='[
  {
    "role_arn": "arn:aws:iam::111122223333:role/CostExplorerReadOnly",
    "account_alias": "Production"
  }
]'
```

---

## DynamoDB 테이블

### bdp-cost-history

비용 이력 저장 테이블.

| 속성 | 타입 | 설명 |
|------|------|------|
| `account_id` (PK) | String | AWS 계정 ID |
| `date` (SK) | String | 날짜 (YYYY-MM-DD) |
| `total_cost` | String | 총 비용 |
| `top_services` | String (JSON) | 상위 5개 서비스 비용 |
| `anomaly_count` | Number | 탐지된 이상 현상 수 |
| `ttl` | Number | TTL (365일) |

**GSI**: `date-index` (날짜별 조회)

### bdp-cost-anomaly-tracking

이상 현상 추적 테이블.

| 속성 | 타입 | 설명 |
|------|------|------|
| `anomaly_id` (PK) | String | 이상 현상 고유 ID |
| `account_id` | String | AWS 계정 ID |
| `service_name` | String | AWS 서비스 이름 |
| `severity` | String | 심각도 (high/medium/low) |
| `confidence_score` | String | 신뢰도 점수 |
| `current_cost` | String | 현재 비용 |
| `previous_cost` | String | 이전 비용 |
| `cost_change_ratio` | String | 비용 변화율 |
| `detected_methods` | List | 탐지 방법 목록 |
| `analysis` | String | 분석 텍스트 |
| `date` | String | 분석 대상 날짜 |
| `ttl` | Number | TTL (90일) |

**GSI**:
- `account-date-index`: 계정별 날짜순 조회
- `severity-date-index`: 심각도별 조회

---

## EventBridge 이벤트

### 이벤트 타입

| DetailType | 조건 | 대상 |
|------------|------|------|
| `COST_ALERT_HIGH` | severity=high | Slack + Email |
| `COST_ALERT_MEDIUM` | severity=medium | Slack |
| `COST_ANOMALY_DETECTED` | severity=low | 로그 |

### 이벤트 구조

```json
{
  "version": "0",
  "source": "bdp.cost-detection",
  "detail-type": "COST_ALERT_HIGH",
  "detail": {
    "anomaly_id": "123456789012-Amazon EC2-2024-01-15-a1b2c3d4",
    "account_id": "123456789012",
    "account_alias": "Production",
    "service_name": "Amazon EC2",
    "severity": "high",
    "confidence_score": 0.85,
    "current_cost": 250.50,
    "previous_cost": 120.00,
    "cost_change_percent": 108.75,
    "detected_methods": ["ratio", "stddev"],
    "analysis": "Amazon EC2 cost increased by 108.8% ($120.00 → $250.50)...",
    "date": "2024-01-15",
    "detected_at": "2024-01-15T10:30:00Z"
  }
}
```

### EventBridge Rule 예시

```json
{
  "source": ["bdp.cost-detection"],
  "detail-type": ["COST_ALERT_HIGH", "COST_ALERT_MEDIUM"],
  "detail": {
    "severity": ["high", "medium"]
  }
}
```

---

## 사용법

### Lambda 호출

```python
import boto3
import json

lambda_client = boto3.client('lambda')

response = lambda_client.invoke(
    FunctionName='bdp-cost-detection',
    InvocationType='RequestResponse',
    Payload=json.dumps({
        "start_date": "2024-01-01",
        "end_date": "2024-01-15",
        "granularity": "DAILY",
        "group_by": ["SERVICE"],
        "thresholds": {
            "ratio_threshold": 0.3,
            "stddev_multiplier": 2.0,
            "trend_consecutive_days": 3
        },
        "min_cost_threshold": 5.0
    })
)

result = json.loads(response['Payload'].read())
print(result)
```

### 응답 예시

```json
{
  "statusCode": 200,
  "body": {
    "anomalies_detected": true,
    "total_anomaly_count": 3,
    "high_severity_count": 1,
    "medium_severity_count": 2,
    "accounts_analyzed": 2,
    "account_summaries": [
      {
        "account_id": "123456789012",
        "account_alias": "Production",
        "total_cost": 5420.50,
        "anomaly_count": 2,
        "high_severity_count": 1,
        "medium_severity_count": 1,
        "top_anomalies": [...]
      }
    ],
    "all_anomalies": [...],
    "analysis_period": {
      "start_date": "2024-01-01",
      "end_date": "2024-01-15",
      "granularity": "DAILY"
    },
    "execution_time_ms": 2540
  }
}
```

---

## Mock 테스트

### 환경 설정

```bash
export AWS_MOCK=true
```

### 코드 테스트

```python
# Cost Explorer Client 테스트
from examples.services.cost_explorer_client import CostExplorerClient

client = CostExplorerClient()
costs = client.get_cost_and_usage(
    start_date="2024-01-01",
    end_date="2024-01-15",
    granularity="DAILY",
    group_by=["SERVICE"]
)
print(f"Total cost: ${costs['total_cost']:.2f}")
```

### 이상 현상 주입 테스트

```python
from examples.services.cost_explorer_client import MockCostExplorerProvider

# Mock Provider 생성
provider = MockCostExplorerProvider(account_id="test-account")

# 이상 현상 주입
provider.inject_anomaly(
    date="2024-01-10",
    service="Amazon EC2",
    anomaly_type="spike",
    multiplier=3.0  # 3배 증가
)

# 비용 조회
costs = provider.get_cost_and_usage(
    start_date="2024-01-08",
    end_date="2024-01-12",
    granularity="DAILY",
    group_by=["SERVICE"]
)

# EC2 비용 확인 (2024-01-10에 3배 증가)
for date, services in costs['costs_by_date'].items():
    print(f"{date}: EC2 ${services.get('Amazon EC2', 0):.2f}")
```

### Handler 통합 테스트

```bash
python -c "
import os
os.environ['AWS_MOCK'] = 'true'

from examples.handlers.cost_detection_handler import lambda_handler
import json

class MockContext:
    aws_request_id = 'test-123'

result = lambda_handler({
    'start_date': '2024-01-01',
    'end_date': '2024-01-15',
    'granularity': 'DAILY',
    'group_by': ['SERVICE']
}, MockContext())

print(json.dumps(json.loads(result['body']), indent=2))
"
```

---

## 참고

- [AWS Cost Explorer API](https://docs.aws.amazon.com/cost-management/latest/APIReference/API_Operations_AWS_Cost_Explorer_Service.html)
- [Cross-Account Access](https://docs.aws.amazon.com/IAM/latest/UserGuide/tutorial_cross-account-with-roles.html)
- [BDP Agent 아키텍처](./ARCHITECTURE.md)
