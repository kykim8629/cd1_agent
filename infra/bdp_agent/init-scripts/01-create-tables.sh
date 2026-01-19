#!/bin/bash
# Create DynamoDB tables for BDP Agent
# Executed automatically when LocalStack starts

set -e

echo "=== Creating DynamoDB Tables ==="

# Create cd1-agent-results table
awslocal dynamodb create-table \
    --table-name cd1-agent-results \
    --attribute-definitions \
        AttributeName=signature,AttributeType=S \
        AttributeName=timestamp,AttributeType=S \
    --key-schema \
        AttributeName=signature,KeyType=HASH \
        AttributeName=timestamp,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region ap-northeast-2

echo "Created table: cd1-agent-results"

# Create cd1-agent-patterns table (for detection patterns cache)
awslocal dynamodb create-table \
    --table-name cd1-agent-patterns \
    --attribute-definitions \
        AttributeName=pattern_id,AttributeType=S \
    --key-schema \
        AttributeName=pattern_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region ap-northeast-2

echo "Created table: cd1-agent-patterns"

# Verify tables created
awslocal dynamodb list-tables --region ap-northeast-2

echo "=== DynamoDB Tables Created Successfully ==="
