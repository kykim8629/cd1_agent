#!/bin/bash
# Scenario: CrashLoopBackOff
# Injects kube_pod_container_status_waiting_reason metric to simulate pod crash loop
# Expected Detection: CRITICAL severity

set -e

PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
NAMESPACE="${1:-spark}"
POD_NAME="${2:-test-crash-loop-pod}"
CONTAINER_NAME="${3:-main}"

echo "=== Injecting CrashLoopBackOff Scenario ==="
echo "Namespace: $NAMESPACE"
echo "Pod: $POD_NAME"
echo "Container: $CONTAINER_NAME"
echo "Pushgateway: $PUSHGATEWAY_URL"

# Push CrashLoopBackOff metric
cat <<EOF | curl --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/kube-state-metrics/namespace/${NAMESPACE}/pod/${POD_NAME}"
# HELP kube_pod_container_status_waiting_reason Describes the reason the container is currently in waiting state.
# TYPE kube_pod_container_status_waiting_reason gauge
kube_pod_container_status_waiting_reason{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}",reason="CrashLoopBackOff"} 1
# HELP kube_pod_container_status_restarts_total The number of container restarts per container.
# TYPE kube_pod_container_status_restarts_total counter
kube_pod_container_status_restarts_total{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} 15
EOF

echo ""
echo "=== CrashLoopBackOff Scenario Injected ==="
echo "Expected Detection:"
echo "  - anomaly_type: crash_loop"
echo "  - metric: kube_pod_container_status_waiting_reason"
echo "  - reason: CrashLoopBackOff"
echo "  - severity: CRITICAL"
echo ""
echo "Verify with:"
echo "  curl '${PUSHGATEWAY_URL}/metrics' | grep kube_pod_container_status_waiting_reason"
echo "  curl 'http://localhost:9090/api/v1/query?query=kube_pod_container_status_waiting_reason'"
