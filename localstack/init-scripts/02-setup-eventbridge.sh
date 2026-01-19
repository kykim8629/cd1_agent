#!/bin/bash
# Setup EventBridge for BDP Agent notifications
# Executed automatically when LocalStack starts

set -e

echo "=== Setting up EventBridge ==="

# Create custom event bus for CD1 Agent
awslocal events create-event-bus \
    --name cd1-agent-events \
    --region ap-northeast-2

echo "Created event bus: cd1-agent-events"

# Create rule for anomaly detection events
awslocal events put-rule \
    --name cd1-anomaly-detection \
    --event-bus-name cd1-agent-events \
    --event-pattern '{
        "source": ["cd1.agent.bdp"],
        "detail-type": ["AnomalyDetected"]
    }' \
    --state ENABLED \
    --region ap-northeast-2

echo "Created rule: cd1-anomaly-detection"

# Create rule for critical alerts
awslocal events put-rule \
    --name cd1-critical-alerts \
    --event-bus-name cd1-agent-events \
    --event-pattern '{
        "source": ["cd1.agent.bdp"],
        "detail-type": ["CriticalAlert"]
    }' \
    --state ENABLED \
    --region ap-northeast-2

echo "Created rule: cd1-critical-alerts"

# List rules to verify
awslocal events list-rules \
    --event-bus-name cd1-agent-events \
    --region ap-northeast-2

echo "=== EventBridge Setup Complete ==="
