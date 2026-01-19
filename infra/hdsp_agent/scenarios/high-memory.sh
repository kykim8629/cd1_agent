#!/bin/bash
# Scenario: High Memory Usage
# Injects container_memory_working_set_bytes metric to simulate high memory
# Expected Detection: HIGH severity

set -e

PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
NAMESPACE="${1:-hdsp}"
POD_NAME="${2:-high-memory-pod}"
CONTAINER_NAME="${3:-processor}"
MEMORY_USAGE_GB="${4:-3.8}"  # 3.8 GB out of 4 GB limit (95%)
MEMORY_LIMIT_GB="${5:-4.0}"  # 4 GB limit

echo "=== Injecting High Memory Scenario ==="
echo "Namespace: $NAMESPACE"
echo "Pod: $POD_NAME"
echo "Container: $CONTAINER_NAME"
echo "Memory Usage: ${MEMORY_USAGE_GB} GB / ${MEMORY_LIMIT_GB} GB"
echo "Pushgateway: $PUSHGATEWAY_URL"

# Convert GB to bytes
MEMORY_BYTES=$(echo "$MEMORY_USAGE_GB * 1024 * 1024 * 1024" | bc | cut -d'.' -f1)
MEMORY_LIMIT_BYTES=$(echo "$MEMORY_LIMIT_GB * 1024 * 1024 * 1024" | bc | cut -d'.' -f1)

# Push high memory metrics
cat <<EOF | curl --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/cadvisor/namespace/${NAMESPACE}/pod/${POD_NAME}"
# HELP container_memory_working_set_bytes Current working set of the container in bytes.
# TYPE container_memory_working_set_bytes gauge
container_memory_working_set_bytes{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} ${MEMORY_BYTES}
# HELP container_memory_usage_bytes Current memory usage in bytes.
# TYPE container_memory_usage_bytes gauge
container_memory_usage_bytes{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} ${MEMORY_BYTES}
# HELP kube_pod_container_resource_limits The number of requested limit resource by a container.
# TYPE kube_pod_container_resource_limits gauge
kube_pod_container_resource_limits{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}",resource="memory"} ${MEMORY_LIMIT_BYTES}
# HELP container_memory_cache Total page cache memory.
# TYPE container_memory_cache gauge
container_memory_cache{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} 100000000
EOF

echo ""
echo "=== High Memory Scenario Injected ==="
echo "Expected Detection:"
echo "  - anomaly_type: high_memory"
echo "  - metric: container_memory_working_set_bytes"
echo "  - threshold: > 85%"
echo "  - severity: HIGH"
echo ""
echo "Verify with:"
echo "  curl '${PUSHGATEWAY_URL}/metrics' | grep container_memory_working_set"
echo "  curl 'http://localhost:9090/api/v1/query?query=container_memory_working_set_bytes'"
