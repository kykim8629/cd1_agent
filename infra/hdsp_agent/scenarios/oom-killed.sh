#!/bin/bash
# Scenario: OOMKilled
# Injects kube_pod_container_status_last_terminated_reason metric to simulate OOM
# Expected Detection: CRITICAL severity

set -e

PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
NAMESPACE="${1:-hdsp}"
POD_NAME="${2:-test-oom-pod}"
CONTAINER_NAME="${3:-processor}"

echo "=== Injecting OOMKilled Scenario ==="
echo "Namespace: $NAMESPACE"
echo "Pod: $POD_NAME"
echo "Container: $CONTAINER_NAME"
echo "Pushgateway: $PUSHGATEWAY_URL"

# Push OOMKilled metric
cat <<EOF | curl --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/kube-state-metrics/namespace/${NAMESPACE}/pod/${POD_NAME}"
# HELP kube_pod_container_status_last_terminated_reason Describes the last reason the container was in terminated state.
# TYPE kube_pod_container_status_last_terminated_reason gauge
kube_pod_container_status_last_terminated_reason{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}",reason="OOMKilled"} 1
# HELP kube_pod_container_status_terminated Describes whether the container is currently in terminated state.
# TYPE kube_pod_container_status_terminated gauge
kube_pod_container_status_terminated{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} 1
# HELP kube_pod_container_status_restarts_total The number of container restarts per container.
# TYPE kube_pod_container_status_restarts_total counter
kube_pod_container_status_restarts_total{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} 8
EOF

echo ""
echo "=== OOMKilled Scenario Injected ==="
echo "Expected Detection:"
echo "  - anomaly_type: oom_killed"
echo "  - metric: kube_pod_container_status_last_terminated_reason"
echo "  - reason: OOMKilled"
echo "  - severity: CRITICAL"
echo ""
echo "Verify with:"
echo "  curl '${PUSHGATEWAY_URL}/metrics' | grep kube_pod_container_status_last_terminated_reason"
echo "  curl 'http://localhost:9090/api/v1/query?query=kube_pod_container_status_last_terminated_reason'"
