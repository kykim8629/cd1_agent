# DriftDetectionHandler 실행 흐름

## Overview

`handler.py`는 Drift Agent의 AWS Configuration Drift Detection Lambda 진입점으로, 다음 기능을 수행합니다:
- **Baseline 비교**: 로컬 baseline 파일과 현재 AWS 리소스 설정 비교
- **Drift 탐지**: 설정 변경(drift) 식별 및 심각도 분류
- **LLM 분석**: Critical/High 심각도 drift에 대한 근본 원인 분석
- **지원 리소스**: EKS, MSK, S3, EMR, MWAA

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

    subgraph Processing["Main Processing"]
        F --> G[Parse event parameters]
        G --> H[_run_drift_detection]
        H --> I{_should_analyze?}

        I -->|Yes| J[_analyze_drifts]
        I -->|No| K[Skip LLM analysis]

        J --> L[_store_drift_results]
        K --> L

        L --> M{critical/high exists?}
        M -->|Yes| N[_trigger_analysis]
        M -->|No| O[Skip trigger]

        N --> P[Return Result]
        O --> P
    end
```

## 상세 메서드 흐름

### 1. Drift Detection (`_run_drift_detection`)

```mermaid
flowchart TD
    subgraph DriftDetection["_run_drift_detection"]
        A[Start] --> B[Get baseline info]
        B --> C[Loop: resource_types]

        C --> D[Get resource_list for type]
        D --> E[Loop: each resource_id]

        E --> F[_check_resource_drift]
        F --> G[Store drift_configs for analysis]
        G --> H[_meets_severity_threshold?]

        H -->|Yes| I[Add to drifts list]
        H -->|No| J[Skip this drift]

        I --> K{More resources?}
        J --> K
        K -->|Yes| E
        K -->|No| L{More types?}
        L -->|Yes| C

        L -->|No| M[Create AggregatedDriftResult]
        M --> N["Return (result, drift_configs)"]
    end
```

### 2. Resource Drift Check (`_check_resource_drift`)

```mermaid
flowchart TD
    subgraph CheckDrift["_check_resource_drift"]
        A[Start] --> B[baseline_loader.get_resource_baseline]
        B --> C["Get baseline from local files
        (conf/baselines/{type}/{resource}.yaml)"]

        C --> D[config_fetcher.get_config]
        D --> E["Get current config from AWS
        (boto3 describe calls)"]

        E --> F[drift_detector.detect]
        F --> G["Compare baseline vs current
        - Field-level comparison
        - Severity classification"]

        G --> H["Return (DriftResult, BaselineFile, ResourceConfig)"]
    end
```

### 3. LLM Analysis (`_analyze_drifts`)

```mermaid
flowchart TD
    subgraph AnalyzeDrifts["_analyze_drifts"]
        A[Start] --> B[Filter critical/high severity drifts]
        B --> C[Limit to max_drifts_to_analyze]

        C --> D[Loop: each drift]
        D --> E[Get drift_configs for this drift]
        E --> F{configs found?}

        F -->|No| G[Log warning, skip]
        F -->|Yes| H[drift_analyzer.analyze_drift]

        H --> I["LLM Analysis:
        - Root cause identification
        - Remediation recommendations
        - Confidence scoring"]

        I --> J[Add to analysis_results]
        J --> K{More drifts?}
        K -->|Yes| D

        K -->|No| L[Return analysis_results]
        G --> K
    end
```

## 공통 헬퍼 메서드

```mermaid
flowchart LR
    subgraph Validation["Validation"]
        A[_validate_input] --> B[Check resource_types]
        B --> C[Check severity_threshold]
        C --> D["Valid: CRITICAL, HIGH, MEDIUM, LOW"]
    end

    subgraph Filtering["Filtering"]
        E[_should_analyze] --> F{analysis_enabled?}
        F -->|No| G[Return False]
        F -->|Yes| H{critical/high exists?}
        H --> I[Return True/False]

        J[_meets_severity_threshold] --> K[Compare field severity to threshold]
    end

    subgraph Storage["Storage & Trigger"]
        L[_store_drift_results] --> M[aws_client.put_dynamodb_item]
        M --> N[Store summary record]
        M --> O[Store individual drift records]
        O --> P[Include analysis results if available]

        Q[_trigger_analysis] --> R[aws_client.put_eventbridge_event]
        R --> S["source: cd1-agent.drift
        detail_type: Configuration Drift Detected"]
    end
```

## 클래스 초기화 흐름

```mermaid
flowchart TD
    subgraph Init["__init__"]
        A[DriftDetectionHandler] --> B["super().__init__('DriftDetectionHandler')"]
        B --> C[_init_clients]

        C --> D[Create AWSClient]
        C --> E[Create BaselineLoader]
        C --> F[Create ConfigFetcher]
        C --> G[Create ConfigDriftDetector]

        C --> H[_init_drift_analyzer]
    end

    subgraph AnalyzerInit["_init_drift_analyzer"]
        H --> I{ENABLE_DRIFT_ANALYSIS?}
        I -->|No| J[drift_analyzer = None]

        I -->|Yes| K[Determine LLM provider]
        K --> L["vllm / gemini / mock"]
        L --> M[Create LLMClient]
        M --> N[Create DriftAnalyzer]
        N --> O["max_iterations, confidence_threshold"]
    end
```

## 데이터 흐름 요약

| Resource Type | Data Source | Drift Detection | Trigger Condition |
|--------------|-------------|-----------------|-------------------|
| EKS | describe_cluster, describe_nodegroup | Field-level comparison | `CRITICAL or HIGH severity` |
| MSK | describe_cluster | Field-level comparison | `CRITICAL or HIGH severity` |
| S3 | get_bucket_* APIs | Security/lifecycle config | `CRITICAL or HIGH severity` |
| EMR | describe_cluster | Cluster/instance config | `CRITICAL or HIGH severity` |
| MWAA | get_environment | Environment config | `CRITICAL or HIGH severity` |

## Drift Severity 기준

| Severity | Examples | Description |
|----------|----------|-------------|
| CRITICAL | Security group 변경, IAM 정책 변경 | 즉시 조치 필요 |
| HIGH | 네트워크 설정, 암호화 설정 변경 | 빠른 검토 필요 |
| MEDIUM | 리소스 크기, 인스턴스 타입 변경 | 계획된 검토 |
| LOW | 태그, 설명 변경 | 정보 목적 |

## LLM Analysis 출력 구조

```json
{
  "drift_id": "EKS:production-eks",
  "cause_analysis": {
    "category": "manual_change|automation|drift|unknown",
    "root_cause": "상세 원인 설명"
  },
  "confidence_score": 0.85,
  "urgency_score": 0.9,
  "requires_human_review": true,
  "remediations": [
    {
      "action": "remediation action",
      "priority": "high",
      "estimated_impact": "..."
    }
  ]
}
```

## DynamoDB 저장 구조

### Summary Record
```
PK: DRIFT#{date}
SK: DETECTION#{timestamp}
```

### Individual Drift Record
```
PK: DRIFT#{resource_type}#{resource_id}
SK: DRIFT#{timestamp}
```

Analysis 결과가 있는 경우 추가 필드:
- `analysis_cause_category`
- `analysis_root_cause`
- `analysis_confidence`
- `analysis_urgency`
- `analysis_requires_review`
- `analysis_remediations`

## EventBridge 이벤트 구조

```json
{
  "source": "cd1-agent.drift",
  "detail-type": "Configuration Drift Detected",
  "detail": {
    "signature": "drift_{date}",
    "anomaly_type": "config_drift",
    "service_name": "drift-agent",
    "agent": "drift",
    "severity": "critical|high|medium|low",
    "summary": "Configuration drift detected: X drifts across Y resources",
    "drift_details": [...],
    "severity_summary": {...},
    "baseline_info": {...},
    "analysis_enabled": true,
    "analysis_count": 3,
    "analysis_summary": [...]
  }
}
```

## 환경 변수

| Variable | Default | Description |
|----------|---------|-------------|
| ENABLE_DRIFT_ANALYSIS | true | LLM 분석 활성화 여부 |
| LLM_PROVIDER | mock | LLM 제공자 (vllm/gemini/mock) |
| VLLM_ENDPOINT | - | vLLM 서버 엔드포인트 |
| LLM_MODEL | - | 사용할 LLM 모델명 |
| GEMINI_API_KEY | - | Gemini API 키 |
| VLLM_API_KEY | - | vLLM API 키 |
| MAX_ANALYSIS_ITERATIONS | 3 | 분석 반복 최대 횟수 |
| ANALYSIS_CONFIDENCE_THRESHOLD | 0.7 | 분석 신뢰도 임계값 |
| MAX_DRIFTS_TO_ANALYZE | 5 | 분석할 최대 drift 수 |
