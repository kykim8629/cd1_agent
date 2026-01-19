#!/bin/bash
# Scenario: Node MemoryPressure
# Injects kube_node_status_condition metric to simulate node pressure
# Expected Detection: HIGH severity

set -e

PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
NODE_NAME="${1:-worker-node-1}"
CONDITION="${2:-MemoryPressure}"

echo "=== Injecting Node Pressure Scenario ==="
echo "Node: $NODE_NAME"
echo "Condition: $CONDITION"
echo "Pushgateway: $PUSHGATEWAY_URL"

# Push node pressure metric
cat <<EOF | curl --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/kube-state-metrics/node/${NODE_NAME}"
# HELP kube_node_status_condition The condition of a cluster node.
# TYPE kube_node_status_condition gauge
kube_node_status_condition{node="${NODE_NAME}",condition="${CONDITION}",status="true"} 1
kube_node_status_condition{node="${NODE_NAME}",condition="${CONDITION}",status="false"} 0
kube_node_status_condition{node="${NODE_NAME}",condition="${CONDITION}",status="unknown"} 0
# HELP kube_node_status_allocatable_memory_bytes The allocatable memory of a node that is available for scheduling.
# TYPE kube_node_status_allocatable_memory_bytes gauge
kube_node_status_allocatable_memory_bytes{node="${NODE_NAME}"} 8000000000
# HELP node_memory_MemAvailable_bytes Memory information field MemAvailable_bytes.
# TYPE node_memory_MemAvailable_bytes gauge
node_memory_MemAvailable_bytes{node="${NODE_NAME}"} 500000000
EOF

echo ""
echo "=== Node Pressure Scenario Injected ==="
echo "Expected Detection:"
echo "  - anomaly_type: node_pressure"
echo "  - metric: kube_node_status_condition"
echo "  - condition: ${CONDITION}"
echo "  - severity: HIGH"
echo ""
echo "Verify with:"
echo "  curl '${PUSHGATEWAY_URL}/metrics' | grep kube_node_status_condition"
echo "  curl 'http://localhost:9090/api/v1/query?query=kube_node_status_condition{status=\"true\"}'"
