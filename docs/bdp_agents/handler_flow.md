# DetectionHandler 실행 흐름

## Overview

`handler.py`는 BDP Agent의 이상 탐지 Lambda 진입점으로, 4가지 탐지 유형을 처리합니다.

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
        G -->|log_anomaly| H[_detect_log_anomalies]
        G -->|metric_anomaly| I[_detect_metric_anomalies]
        G -->|pattern_anomaly| J[_detect_pattern_anomalies]
        G -->|scheduled| K[_run_scheduled_detection]
    end

    H --> L[Return Result]
    I --> L
    J --> L
    K --> L
```

## 상세 메서드 흐름

### 1. Log Anomaly Detection

```mermaid
flowchart TD
    subgraph LogDetection["_detect_log_anomalies"]
        A[Start] --> B[Parse Parameters]
        B --> C[Calculate Time Range]
        C --> D[Build CloudWatch Query]
        D --> E[aws_client.query_cloudwatch_logs]
        E --> F{logs found?}

        F -->|No| G[Return: No anomalies]

        F -->|Yes| H[_summarize_logs]
        H --> I[llm_client.generate]
        I --> J[_create_log_anomaly_record]
        J --> K[_store_detection_result]
        K --> L{len >= 5?}

        L -->|Yes| M[_trigger_analysis]
        L -->|No| N[Skip trigger]

        M --> O[Return: Anomalies detected]
        N --> O
    end
```

### 2. Metric Anomaly Detection

```mermaid
flowchart TD
    subgraph MetricDetection["_detect_metric_anomalies"]
        A[Start] --> B[Parse Parameters]
        B --> C[Calculate Time Range]
        C --> D[aws_client.get_cloudwatch_metrics]
        D --> E{datapoints >= 2?}

        E -->|No| F[Return: Insufficient data]

        E -->|Yes| G[Calculate Statistics]
        G --> H["mean, variance, stddev"]
        H --> I[Calculate z_score]
        I --> J{abs z_score > 2.0?}

        J -->|No| K[Return: No anomaly]

        J -->|Yes| L[_create_metric_anomaly_record]
        L --> M[_store_detection_result]
        M --> N[_trigger_analysis]
        N --> O[Return: Anomaly detected]
    end
```

### 3. Pattern Anomaly Detection

```mermaid
flowchart TD
    subgraph PatternDetection["_detect_pattern_anomalies"]
        A[Start] --> B[Parse target_service, context]
        B --> C[pattern_service.execute_all_patterns]
        C --> D{results exist?}

        D -->|No| E[Return: No patterns configured]

        D -->|Yes| F[Filter anomalies]
        F --> G{anomalies found?}

        G -->|No| H[Return: No anomalies]

        G -->|Yes| I[Loop: top 10 anomalies]
        I --> J[_create_pattern_anomaly_record]
        J --> K[_store_detection_result]
        K --> L{More anomalies?}
        L -->|Yes| I

        L -->|No| M{critical/high severity?}
        M -->|Yes| N[_trigger_analysis]
        M -->|No| O[Skip trigger]

        N --> P[Return: Anomalies detected]
        O --> P
    end
```

### 4. Scheduled Detection

```mermaid
flowchart TD
    subgraph ScheduledDetection["_run_scheduled_detection"]
        A[Start] --> B[Get services list]
        B --> C[Initialize results dict]

        C --> D[Loop: each service]
        D --> E[_detect_log_anomalies]
        E --> F{success?}
        F -->|Yes| G[Store result]
        F -->|No| H[Log error, store error]
        G --> I{More services?}
        H --> I
        I -->|Yes| D

        I -->|No| J[_detect_pattern_anomalies]
        J --> K{success?}
        K -->|Yes| L[Store pattern result]
        K -->|No| M[Log error, store error]

        L --> N[Calculate total_anomalies]
        M --> N
        N --> O[Return results]
    end
```

## 공통 헬퍼 메서드

```mermaid
flowchart LR
    subgraph Storage["Storage & Trigger"]
        A[_store_detection_result] --> B[aws_client.put_dynamodb_item]
        C[_trigger_analysis] --> D[aws_client.put_eventbridge_event]
    end

    subgraph RecordCreation["Record Creation"]
        E[_create_log_anomaly_record] --> F[Dict with signature, severity]
        G[_create_metric_anomaly_record] --> H[Dict with z_score, metrics]
        I[_create_pattern_anomaly_record] --> J[Dict with pattern info]
    end

    subgraph Summarization["Log Summarization"]
        K[_summarize_logs] --> L[build_log_summarization_prompt]
        L --> M[llm_client.generate]
    end
```

## 클래스 초기화 흐름

```mermaid
flowchart TD
    subgraph Init["__init__"]
        A[DetectionHandler] --> B[super.__init__]
        B --> C[_init_clients]
        C --> D[Create LLMClient]
        C --> E[Create AWSClient]
        C --> F[Create DetectionPatternService]
    end
```

## 데이터 흐름 요약

| Detection Type | Data Source | Anomaly Criteria | Trigger Condition |
|---------------|-------------|------------------|-------------------|
| log_anomaly | CloudWatch Logs | Error patterns found | `len(logs) >= 5` |
| metric_anomaly | CloudWatch Metrics | `abs(z_score) > 2.0` | Always on anomaly |
| pattern_anomaly | RDS Patterns | Pattern match | `severity in (critical, high)` |
| scheduled | All above | Combined | Delegated to sub-detectors |
