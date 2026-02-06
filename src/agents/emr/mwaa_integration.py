"""
MWAA Integration - utils/api.py에 추가할 코드.

이 파일의 내용을 기존 MWAA 프로젝트의 utils/api.py에 복사하세요.

사용법:
1. _call_emr_agent, _acquire_connection, _release_connection 함수를 api.py에 추가
2. delay_function 맨 처음에 _acquire_connection() 호출 추가
3. done_api_function 맨 마지막에 _release_connection() 호출 추가
4. 환경변수 EMR_AGENT_ENABLED=true로 설정하여 활성화
"""

import os
import json
import boto3
from typing import Optional


# ============================================================
# Configuration
# ============================================================

# Feature flag - 환경변수로 on/off 가능
EMR_AGENT_ENABLED = os.getenv('EMR_AGENT_ENABLED', 'false').lower() == 'true'

# EMR Batch Agent Lambda 함수명
EMR_AGENT_FUNCTION_NAME = os.getenv('EMR_AGENT_FUNCTION_NAME', 'emr-batch-agent')


# ============================================================
# EMR Batch Agent 호출 함수
# ============================================================

def _call_emr_agent(action: str, spec: dict, dag_id: str, dag_run_id: str) -> dict:
    """
    EMR Batch Agent Lambda 호출.

    Args:
        action: 'acquire' | 'release' | 'status'
        spec: 배치 스펙 (athenaMetaData, rsrcSpecData 포함)
        dag_id: DAG ID
        dag_run_id: DAG Run ID

    Returns:
        Lambda 응답 dict
    """
    lambda_client = boto3.client('lambda')

    payload = {
        'action': action,
        'dag_id': dag_id,
        'dag_run_id': dag_run_id,
        'src_db_id': spec.get('athenaMetaData', {}).get('srcDbId'),
    }

    # acquire일 때만 hint, table_name 추가
    if action == 'acquire':
        payload['parallel_hint'] = spec.get('rsrcSpecData', {}).get('hint', '')
        payload['table_name'] = spec.get('athenaMetaData', {}).get('tableName', 'unknown')

    response = lambda_client.invoke(
        FunctionName=EMR_AGENT_FUNCTION_NAME,
        Payload=json.dumps(payload)
    )

    return json.loads(response['Payload'].read())


def _acquire_connection(spec: dict, dag_id: str, dag_run_id: str) -> Optional[dict]:
    """
    Connection 획득 시도.

    - EMR_AGENT_ENABLED=false면 스킵
    - Lambda 호출 실패, 코드 에러 등은 무시하고 배치 계속 진행
    - Connection 부족일 때만 Exception 발생 → Airflow retry

    Args:
        spec: 배치 스펙
        dag_id: DAG ID
        dag_run_id: DAG Run ID

    Returns:
        성공 시 결과 dict, 스킵/실패 시 None

    Raises:
        Exception: Connection 부족 시 (Airflow retry 유도)
    """
    # Feature flag 체크
    if not EMR_AGENT_ENABLED:
        print("[EMR Agent] 비활성화 상태, 스킵")
        return None

    try:
        result = _call_emr_agent('acquire', spec, dag_id, dag_run_id)

        if result.get('allowed'):
            print(f"✅ [EMR Agent] Connection 획득! "
                  f"사용량: {result.get('current_usage')}, "
                  f"parallel: {result.get('parallel')}")

            if result.get('downgraded'):
                print(f"⚠️ [EMR Agent] Parallel 다운그레이드: "
                      f"{result.get('original_parallel')} → {result.get('adjusted_parallel')}")

            return result
        else:
            # Connection 부족 → Exception → Airflow retry
            raise Exception(
                f"[EMR Agent] Connection 부족! "
                f"현재 사용량: {result.get('current_usage')}, "
                f"대기 필요: {result.get('wait_seconds')}초"
            )

    except Exception as e:
        error_msg = str(e)

        if "Connection 부족" in error_msg:
            # 진짜 connection 부족 → 재시도 필요
            raise
        else:
            # Lambda 호출 실패, 타임아웃, 코드 에러 등 → 무시하고 진행
            print(f"⚠️ [EMR Agent] acquire 오류 발생, 무시하고 진행: {e}")
            return None


def _release_connection(spec: dict, dag_id: str, dag_run_id: str) -> Optional[dict]:
    """
    Connection 반환.

    - EMR_AGENT_ENABLED=false면 스킵
    - 실패해도 무시 (배치 성공에 영향 없음)

    Args:
        spec: 배치 스펙
        dag_id: DAG ID
        dag_run_id: DAG Run ID

    Returns:
        성공 시 결과 dict, 스킵/실패 시 None
    """
    # Feature flag 체크
    if not EMR_AGENT_ENABLED:
        return None

    try:
        result = _call_emr_agent('release', spec, dag_id, dag_run_id)
        print(f"🔓 [EMR Agent] Connection 반환! "
              f"반환: {result.get('released_connections')}개, "
              f"현재 사용량: {result.get('current_usage')}")
        return result

    except Exception as e:
        # release 실패해도 배치는 성공으로 처리
        print(f"⚠️ [EMR Agent] release 오류 발생, 무시: {e}")
        return None


# ============================================================
# 기존 함수에 추가할 코드 예시
# ============================================================

"""
# delay_function에 추가 (맨 처음에)

def delay_function(spec, dag_id, dag_run_id, **kwargs):
    # 🆕 Connection 획득 (실패해도 배치는 계속 진행)
    _acquire_connection(spec, dag_id, dag_run_id)

    # 기존 로직...
    ...


# done_api_function에 추가 (맨 마지막에)

def done_api_function(spec, dag_id, dag_run_id, **kwargs):
    # 기존 로직...
    ...

    # 🆕 Connection 반환 (실패해도 무시)
    _release_connection(spec, dag_id, dag_run_id)
"""
