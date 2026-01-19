#!/bin/bash
# Scenario: High CPU Usage
# Injects container_cpu_usage_seconds_total metric to simulate high CPU
# Expected Detection: HIGH severity

set -e

PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
NAMESPACE="${1:-default}"
POD_NAME="${2:-high-cpu-pod}"
CONTAINER_NAME="${3:-app}"
CPU_USAGE="${4:-0.95}"  # 95% CPU usage

echo "=== Injecting High CPU Scenario ==="
echo "Namespace: $NAMESPACE"
echo "Pod: $POD_NAME"
echo "Container: $CONTAINER_NAME"
echo "CPU Usage: ${CPU_USAGE} (${CPU_USAGE}00%)"
echo "Pushgateway: $PUSHGATEWAY_URL"

# Calculate cumulative CPU seconds (simulating high sustained usage)
NOW=$(date +%s)
CPU_SECONDS=$(echo "$NOW * $CPU_USAGE" | bc -l)

# Push high CPU metrics
cat <<EOF | curl --data-binary @- "${PUSHGATEWAY_URL}/metrics/job/cadvisor/namespace/${NAMESPACE}/pod/${POD_NAME}"
# HELP container_cpu_usage_seconds_total Cumulative cpu time consumed.
# TYPE container_cpu_usage_seconds_total counter
container_cpu_usage_seconds_total{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} ${CPU_SECONDS}
# HELP kube_pod_container_resource_limits The number of requested limit resource by a container.
# TYPE kube_pod_container_resource_limits gauge
kube_pod_container_resource_limits{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}",resource="cpu"} 1
# HELP container_cpu_cfs_throttled_seconds_total Total time duration the container has been throttled.
# TYPE container_cpu_cfs_throttled_seconds_total counter
container_cpu_cfs_throttled_seconds_total{namespace="${NAMESPACE}",pod="${POD_NAME}",container="${CONTAINER_NAME}"} 1500
EOF

echo ""
echo "=== High CPU Scenario Injected ==="
echo "Expected Detection:"
echo "  - anomaly_type: high_cpu"
echo "  - metric: container_cpu_usage_seconds_total"
echo "  - threshold: > 90%"
echo "  - severity: HIGH"
echo ""
echo "Verify with:"
echo "  curl '${PUSHGATEWAY_URL}/metrics' | grep container_cpu_usage"
echo "  curl 'http://localhost:9090/api/v1/query?query=container_cpu_usage_seconds_total'"
