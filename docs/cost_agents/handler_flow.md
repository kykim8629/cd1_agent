# CostDetectionHandler 실행 흐름

## Overview

`handler.py`는 Cost Agent의 비용 이상 탐지 Lambda 진입점으로, 3가지 탐지 유형을 처리합니다:
- **Full Detection (all)**: Luminol 기반 비용 이상 탐지
- **Forecast**: AWS Cost Explorer 예측
- **AWS Anomalies**: AWS 네이티브 이상 탐지 서비스 조회

## 메인 실행 흐름

```mermaid
flowchart TD
    subgraph Entry["Lambda Entry Point"]
        A[handler] --> B[handler_instance.handle]
        B --> C[_validate_input]
        C --> D{validation OK?}
        D -->|No| E[Return Error]
        D -->|Yes| F[process]
    end

    subgraph Router["Detection Router"]
        F --> G{detection_type}
        G -->|all| H[_run_full_detection]
        G -->|forecast| I[_run_forecast_detection]
        G -->|aws_anomalies| J[_get_aws_anomalies]
        G -->|invalid| K[Raise ValueError]
    end

    H --> L[Return Result]
    I --> L
    J --> L
```

## 상세 메서드 흐름

### 1. Full Detection (`_run_full_detection`)

```mermaid
flowchart TD
    subgraph FullDetection["_run_full_detection"]
        A[Start] --> B[cost_client.get_historical_costs_for_detector]
        B --> C[Filter by min_cost_threshold]
        C --> D[detector.analyze_batch]
        D --> E[Filter anomalies only]
        E --> F[_count_by_severity]

        F --> G{anomalies found?}
        G -->|No| H[Return: No anomalies]

        G -->|Yes| I[_store_detection_results]
        I --> J{critical/high exists?}

        J -->|Yes| K[_trigger_analysis]
        J -->|No| L[Skip trigger]

        K --> M[Return: Detection result with anomalies]
        L --> M
    end
```

### 2. Forecast Detection (`_run_forecast_detection`)

```mermaid
flowchart TD
    subgraph ForecastDetection["_run_forecast_detection"]
        A[Start] --> B[Calculate date range]
        B --> C[cost_client.get_cost_forecast]
        C --> D[Return forecast result]

        D --> E["Result includes:
        - total_forecast
        - unit
        - daily_forecasts"]
    end
```

### 3. AWS Anomalies (`_get_aws_anomalies`)

```mermaid
flowchart TD
    subgraph AWSAnomalies["_get_aws_anomalies"]
        A[Start] --> B[Calculate date range]
        B --> C[cost_client.get_anomalies]
        C --> D[Return AWS-detected anomalies]

        D --> E["Result includes:
        - anomaly_count
        - anomalies list"]
    end
```

## 공통 헬퍼 메서드

```mermaid
flowchart LR
    subgraph Storage["Storage & Trigger"]
        A[_store_detection_results] --> B[aws_client.put_dynamodb_item]
        B --> C[Store summary record]
        B --> D[Store individual critical/high anomalies]

        E[_trigger_analysis] --> F[aws_client.put_eventbridge_event]
        F --> G["source: cd1-agent.cost
        detail_type: Cost Anomaly Detected"]
    end

    subgraph Helpers["Helper Methods"]
        H[_count_by_severity] --> I["Dict: critical, high, medium, low counts"]
        J[_generate_summary] --> K[Human-readable summary string]
        L[_result_to_dict] --> M[Convert CostAnomalyResult to dict]
        N[_get_highest_severity] --> O[Return highest severity level]
    end
```

## 클래스 초기화 흐름

```mermaid
flowchart TD
    subgraph Init["__init__"]
        A[CostDetectionHandler] --> B["super().__init__('CostDetectionHandler')"]
        B --> C[_init_clients]

        C --> D[Create AWSClient]
        C --> E[Create CostExplorerClient]
        E --> F["use_mock from COST_EXPLORER_MOCK env"]

        C --> G[Create CostAnomalyDetector]
        G --> H["sensitivity from COST_SENSITIVITY env"]

        C --> I[Set DynamoDB table names]
        I --> J["COST_HISTORY_TABLE
        COST_ANOMALY_TABLE"]
    end
```

## 데이터 흐름 요약

| Detection Type | Data Source | Anomaly Criteria | Trigger Condition |
|---------------|-------------|------------------|-------------------|
| all (full) | Cost Explorer Historical Data | Luminol-based detection (ratio, stddev, trend) | `severity in (critical, high)` |
| forecast | Cost Explorer Forecast API | N/A (예측 데이터 반환만) | N/A |
| aws_anomalies | AWS Cost Anomaly Detection | AWS 네이티브 탐지 결과 | N/A |

## 탐지 알고리즘

Full Detection에서 사용하는 `CostAnomalyDetector`는 다음 방식으로 이상을 탐지합니다:

| Method | Description | Threshold |
|--------|-------------|-----------|
| Ratio-based | 전일 대비 급격한 변화 | configurable |
| Standard deviation | 통계적 이상치 | z-score based |
| Trend detection | 트렌드 대비 이탈 | configurable |
| Luminol | 시계열 고급 분석 | sensitivity-based |

## 환경 변수

| Variable | Default | Description |
|----------|---------|-------------|
| COST_EXPLORER_MOCK | true | Mock 모드 사용 여부 |
| COST_SENSITIVITY | 0.7 | 이상 탐지 민감도 (0-1) |
| COST_HISTORY_TABLE | bdp-cost-history | 비용 이력 테이블 |
| COST_ANOMALY_TABLE | bdp-cost-anomaly-tracking | 이상 추적 테이블 |
