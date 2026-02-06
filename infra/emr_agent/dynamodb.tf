# EMR Batch Agent - DynamoDB Tables

# Connection Registry 테이블
# 실행 중인 배치의 connection 점유 정보 저장
resource "aws_dynamodb_table" "emr_connection_registry" {
  name         = "emr_connection_registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "src_db_id"
  range_key    = "dag_run_id"

  attribute {
    name = "src_db_id"
    type = "N"
  }

  attribute {
    name = "dag_run_id"
    type = "S"
  }

  # TTL 설정 (24시간 후 자동 삭제)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name        = "emr_connection_registry"
    Project     = "cd1-agent"
    Agent       = "emr-batch-agent"
    Description = "Tracks active batch connections per source database"
  }
}

# Connection Limits 테이블
# 원천 DB별 connection 제한 설정
resource "aws_dynamodb_table" "emr_connection_limits" {
  name         = "emr_connection_limits"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "src_db_id"

  attribute {
    name = "src_db_id"
    type = "N"
  }

  tags = {
    Name        = "emr_connection_limits"
    Project     = "cd1-agent"
    Agent       = "emr-batch-agent"
    Description = "Connection limits per source database"
  }
}

# 초기 데이터: ADW (srcDbId: 4)
resource "aws_dynamodb_table_item" "adw_limits" {
  table_name = aws_dynamodb_table.emr_connection_limits.name
  hash_key   = aws_dynamodb_table.emr_connection_limits.hash_key

  item = jsonencode({
    src_db_id = {
      N = "4"
    }
    name = {
      S = "ADW"
    }
    db_type = {
      S = "oracle"
    }
    max_connections = {
      N = "1000"
    }
    threshold_percent = {
      N = "95"
    }
    default_parallel = {
      N = "8"
    }
    min_parallel = {
      N = "2"
    }
  })
}

# Outputs
output "registry_table_name" {
  description = "Connection registry table name"
  value       = aws_dynamodb_table.emr_connection_registry.name
}

output "registry_table_arn" {
  description = "Connection registry table ARN"
  value       = aws_dynamodb_table.emr_connection_registry.arn
}

output "limits_table_name" {
  description = "Connection limits table name"
  value       = aws_dynamodb_table.emr_connection_limits.name
}

output "limits_table_arn" {
  description = "Connection limits table ARN"
  value       = aws_dynamodb_table.emr_connection_limits.arn
}
