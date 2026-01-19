#!/bin/bash
# Scenario: Excessive Pod Restarts
# Injects kube_pod_container_status_restarts_total metric to simulate excessive restarts
# Expected Detection: MEDIUM severity

set -e

PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
NAMESPACE="${1:-spark}"
POD_NAME="${2:-unstable-pod}"
CONTAINER_NAME="${3:-worker}"
RESTART_COUNT="${4:-25}"  # 25 restarts

echo "=== Injecting Excessive Pod Restarts Scenario ==="
echo "Namespace: $NAMESPACE"
echo "Pod: $POD_NAME"
echo "Container: $CONTAINER_NAME"
echo "Restart Count: $RESTART_COUNT"
echo "Pushgateway: $PUSHGATEWAY_URL"

# Push pod restart metrics
cat <<EOF | curl --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/kube-state-metrics/namespace/${NAMESPACE}/pod/${POD_NAME}"
# HELP kube_pod_container_status_restarts_total The number of container restarts per container.
# TYPE kube_pod_container_status_restarts_total counter
kube_pod_container_status_restarts_total{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} ${RESTART_COUNT}
# HELP kube_pod_container_status_running Describes whether the container is currently in running state.
# TYPE kube_pod_container_status_running gauge
kube_pod_container_status_running{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} 1
# HELP kube_pod_status_phase The pods current phase.
# TYPE kube_pod_status_phase gauge
kube_pod_status_phase{namespace="${NAMESPACE}",pod="${POD_NAME}",phase="Running"} 1
kube_pod_status_phase{namespace="${NAMESPACE}",pod="${POD_NAME}",phase="Pending"} 0
kube_pod_status_phase{namespace="${NAMESPACE}",pod="${POD_NAME}",phase="Failed"} 0
EOF

echo ""
echo "=== Excessive Pod Restarts Scenario Injected ==="
echo "Expected Detection:"
echo "  - anomaly_type: excessive_restarts"
echo "  - metric: kube_pod_container_status_restarts_total"
echo "  - threshold: > 10 restarts"
echo "  - severity: MEDIUM"
echo ""
echo "Verify with:"
echo "  curl '${PUSHGATEWAY_URL}/metrics' | grep kube_pod_container_status_restarts_total"
echo "  curl 'http://localhost:9090/api/v1/query?query=kube_pod_container_status_restarts_total'"
