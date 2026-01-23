# BDP Compact Agent - HITL 연동

## 개요

BDP Compact Agent는 Critical 심각도의 이상 탐지 시 Human-in-the-Loop (HITL) 요청을 자동으로 생성합니다.

## HITL 요청 구조

```python
@dataclass
class HITLRequest:
    request_id: str          # UUID
    request_type: str        # "PROMPT_INPUT"
    agent_id: str            # "bdp-compact"
    context: Dict[str, Any]  # 탐지 결과 상세
    prompt: str              # 사용자에게 표시할 메시지
    options: List[str]       # 선택 옵션
    created_at: datetime
    expires_at: datetime     # 기본 24시간 후
    status: str              # "pending", "responded", "expired"
```

## 트리거 조건

| 조건 | HITL 생성 |
|------|----------|
| 심각도 = CRITICAL | ✅ |
| 심각도 = HIGH | ❌ |
| 심각도 = MEDIUM | ❌ |
| 심각도 = LOW | ❌ |

환경 변수로 비활성화 가능:

```bash
export BDP_HITL_ON_CRITICAL=false
```

## HITL 요청 예시

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_type": "PROMPT_INPUT",
  "agent_id": "bdp-compact",
  "context": {
    "alert_type": "cost_drift",
    "service_name": "Amazon Athena",
    "account_name": "hyundaicard-payer",
    "current_cost": 750000,
    "historical_average": 250000,
    "change_percent": 200.0,
    "confidence_score": 0.95,
    "detection_timestamp": "2024-01-15T10:30:00Z"
  },
  "prompt": "Amazon Athena 비용이 200% 급증했습니다. 어떻게 처리할까요?",
  "options": [
    "정상적인 사용량 증가입니다 (무시)",
    "조사가 필요합니다 (티켓 생성)",
    "즉시 조치가 필요합니다 (긴급 알람)"
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "expires_at": "2024-01-16T10:30:00Z",
  "status": "pending"
}
```

## 응답 처리

### API 엔드포인트

```bash
# 대기 중인 HITL 요청 조회
GET /api/v1/hitl/pending

# HITL 요청 응답
POST /api/v1/hitl/{request_id}/respond
{
  "selected_option": 1,
  "comment": "예상된 배치 작업으로 인한 증가입니다."
}
```

### 응답 예시

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "responded",
  "selected_option": 0,
  "selected_option_text": "정상적인 사용량 증가입니다 (무시)",
  "comment": "예상된 배치 작업으로 인한 증가입니다.",
  "responded_at": "2024-01-15T11:00:00Z",
  "responded_by": "operator@example.com"
}
```

## 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `BDP_HITL_ON_CRITICAL` | Critical시 HITL 생성 | `true` |
| `RDS_PROVIDER` | RDS Provider (real/mock) | `mock` |

## 데이터베이스 스키마

HITL 요청은 RDS에 저장됩니다:

```sql
CREATE TABLE hitl_requests (
    request_id VARCHAR(36) PRIMARY KEY,
    request_type VARCHAR(50) NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    context JSONB NOT NULL,
    prompt TEXT NOT NULL,
    options JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    selected_option INT,
    comment TEXT,
    responded_at TIMESTAMP WITH TIME ZONE,
    responded_by VARCHAR(255)
);

CREATE INDEX idx_hitl_status ON hitl_requests(status);
CREATE INDEX idx_hitl_agent ON hitl_requests(agent_id);
CREATE INDEX idx_hitl_expires ON hitl_requests(expires_at);
```
