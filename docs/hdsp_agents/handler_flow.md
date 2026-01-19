# HDSPDetectionHandler 실행 흐름

## Overview

`handler.py`는 HDSP Agent의 On-Prem K8s 이상 탐지 Lambda 진입점으로, 4가지 탐지 유형을 처리합니다:
- **Full Detection (all)**: 모든 K8s 이상 탐지
- **Pod Failure**: Pod 장애 탐지 (CrashLoopBackOff, OOMKilled, restarts)
- **Node Pressure**: 노드 상태 이상 탐지 (MemoryPressure, DiskPressure, NotReady)
- **Resource**: 리소스 사용량 이상 탐지 (high CPU/Memory usage)

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
        G -->|pod_failure| I[_detect_pod_failures_only]
        G -->|node_pressure| J[_detect_node_pressure_only]
        G -->|resource| K[_detect_resource_anomalies_only]
        G -->|invalid| L[Raise ValueError]
    end

    H --> M[Return Result]
    I --> M
    J --> M
    K --> M
```

## 상세 메서드 흐름

### 1. Full Detection (`_run_full_detection`)

```mermaid
flowchart TD
    subgraph FullDetection["_run_full_detection"]
        A[Start] --> B[detector.detect_all]
        B --> C["Returns HDSPDetectionResult with:
        - anomalies list
        - severity counts
        - cluster info"]

        C --> D[_store_detection_result]
        D --> E{has_critical OR high_count > 0?}

        E -->|Yes| F[_trigger_analysis]
        E -->|No| G[Skip trigger]

        F --> H[Return: Full detection result]
        G --> H
    end
```

### 2. Pod Failure Detection (`_detect_pod_failures_only`)

```mermaid
flowchart TD
    subgraph PodFailure["_detect_pod_failures_only"]
        A[Start] --> B[detector.detect_pod_failures]
        B --> C[_create_partial_result]
        C --> D{has_critical OR high_count > 0?}

        D -->|Yes| E[_store_detection_result]
        E --> F[_trigger_analysis]

        D -->|No| G[Skip store/trigger]

        F --> H[Return: Pod failure result]
        G --> H
    end
```

### 3. Node Pressure Detection (`_detect_node_pressure_only`)

```mermaid
flowchart TD
    subgraph NodePressure["_detect_node_pressure_only"]
        A[Start] --> B[detector.detect_node_pressure]
        B --> C[_create_partial_result]
        C --> D{has_critical OR high_count > 0?}

        D -->|Yes| E[_store_detection_result]
        E --> F[_trigger_analysis]

        D -->|No| G[Skip store/trigger]

        F --> H[Return: Node pressure result]
        G --> H
    end
```

### 4. Resource Anomaly Detection (`_detect_resource_anomalies_only`)

```mermaid
flowchart TD
    subgraph ResourceAnomaly["_detect_resource_anomalies_only"]
        A[Start] --> B[detector.detect_resource_anomalies]
        B --> C[_create_partial_result]
        C --> D{has_critical OR high_count > 0?}

        D -->|Yes| E[_store_detection_result]
        E --> F[_trigger_analysis]

        D -->|No| G[Skip store/trigger]

        F --> H[Return: Resource anomaly result]
        G --> H
    end
```

## 공통 헬퍼 메서드

```mermaid
flowchart LR
    subgraph PartialResult["Partial Result Creation"]
        A[_create_partial_result] --> B[Count by severity]
        B --> C["HDSPSeverity.CRITICAL
        HDSPSeverity.HIGH
        HDSPSeverity.MEDIUM
        HDSPSeverity.LOW"]
        C --> D[Create HDSPDetectionResult]
    end

    subgraph Storage["Storage & Trigger"]
        E[_store_detection_result] --> F[aws_client.put_dynamodb_item]
        F --> G[Store summary record]
        F --> H[Store individual critical/high anomalies]

        I[_trigger_analysis] --> J[aws_client.put_eventbridge_event]
        J --> K["source: cd1-agent.hdsp
        detail_type: K8s Anomaly Detected"]
    end

    subgraph Helpers["Helper Methods"]
        L[_get_highest_severity] --> M[Return highest severity from result]
    end
```

## 클래스 초기화 흐름

```mermaid
flowchart TD
    subgraph Init["__init__"]
        A[HDSPDetectionHandler] --> B["super().__init__('HDSPDetectionHandler')"]
        B --> C[_init_clients]

        C --> D[Create AWSClient]
        C --> E[Create PrometheusClient]
        E --> F["Auto-detects mock mode from env"]

        C --> G[Create HDSPAnomalyDetector]
        G --> H["Uses prometheus_client"]
    end
```

## 데이터 흐름 요약

| Detection Type | Data Source | Anomaly Criteria | Trigger Condition |
|---------------|-------------|------------------|-------------------|
| all (full) | Prometheus Metrics | Combined pod/node/resource checks | `has_critical OR high_count > 0` |
| pod_failure | Prometheus Metrics | CrashLoopBackOff, OOMKilled, high restarts | `has_critical OR high_count > 0` |
| node_pressure | Prometheus Metrics | MemoryPressure, DiskPressure, NotReady | `has_critical OR high_count > 0` |
| resource | Prometheus Metrics | High CPU/Memory usage thresholds | `has_critical OR high_count > 0` |

## 탐지 알고리즘

`HDSPAnomalyDetector`가 탐지하는 이상 유형:

### Pod Failure Detection
| Metric | Description | Severity |
|--------|-------------|----------|
| CrashLoopBackOff | Pod가 반복적으로 crash | CRITICAL |
| OOMKilled | 메모리 부족으로 kill | HIGH |
| High restart count | 재시작 횟수 임계치 초과 | MEDIUM-HIGH |

### Node Pressure Detection
| Metric | Description | Severity |
|--------|-------------|----------|
| MemoryPressure | 노드 메모리 압박 | HIGH |
| DiskPressure | 노드 디스크 압박 | HIGH |
| NotReady | 노드 Ready 상태 아님 | CRITICAL |

### Resource Anomaly Detection
| Metric | Description | Threshold |
|--------|-------------|-----------|
| CPU Usage | Container CPU 사용률 | configurable |
| Memory Usage | Container Memory 사용률 | configurable |

## DynamoDB 저장 구조

### Summary Record
```
PK: HDSP#{cluster_name}#{date}
SK: DETECTION#{timestamp}
```

### Individual Anomaly Record
```
PK: ANOMALY#{signature}
SK: HDSP#{timestamp}
signature: hdsp_{anomaly_type}_{namespace}_{resource_name}
```

## EventBridge 이벤트 구조

```json
{
  "source": "cd1-agent.hdsp",
  "detail-type": "K8s Anomaly Detected",
  "detail": {
    "signature": "hdsp_{cluster}_{date}",
    "anomaly_type": "k8s_anomaly",
    "service_name": "hdsp-{cluster}",
    "agent": "hdsp",
    "cluster_name": "...",
    "severity": "critical|high|medium|low",
    "summary": "...",
    "anomaly_details": [...],
    "metrics_snapshot": {...}
  }
}
```
