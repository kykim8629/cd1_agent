# EMR Batch Agent - Lambda Function

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# Lambda 실행 역할
resource "aws_iam_role" "emr_batch_agent_role" {
  name = "emr-batch-agent-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = "cd1-agent"
    Agent   = "emr-batch-agent"
  }
}

# Lambda 기본 정책 (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.emr_batch_agent_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB 접근 정책
resource "aws_iam_role_policy" "dynamodb_policy" {
  name = "emr-batch-agent-dynamodb-policy"
  role = aws_iam_role.emr_batch_agent_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.emr_connection_registry.arn,
          aws_dynamodb_table.emr_connection_limits.arn
        ]
      }
    ]
  })
}

# Lambda 함수
resource "aws_lambda_function" "emr_batch_agent" {
  function_name = "emr-batch-agent"
  description   = "EMR Batch Agent - Oracle Connection Pool Management"

  filename         = "${path.module}/../../dist/emr_batch_agent.zip"
  source_code_hash = filebase64sha256("${path.module}/../../dist/emr_batch_agent.zip")

  handler = "src.agents.emr.handler.lambda_handler"
  runtime = "python3.12"

  architectures = ["arm64"]  # Graviton2 (비용 절감)
  memory_size   = 256
  timeout       = 30

  role = aws_iam_role.emr_batch_agent_role.arn

  environment {
    variables = {
      EMR_AGENT_TABLE_REGISTRY = aws_dynamodb_table.emr_connection_registry.name
      EMR_AGENT_TABLE_LIMITS   = aws_dynamodb_table.emr_connection_limits.name
      DEFAULT_WAIT_SECONDS     = "30"
      MAX_WAIT_SECONDS         = "300"
    }
  }

  tags = {
    Project = "cd1-agent"
    Agent   = "emr-batch-agent"
  }
}

# Lambda 함수 URL (Optional - 테스트/모니터링용)
resource "aws_lambda_function_url" "emr_batch_agent_url" {
  function_name      = aws_lambda_function.emr_batch_agent.function_name
  authorization_type = "AWS_IAM"
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "emr_batch_agent_logs" {
  name              = "/aws/lambda/${aws_lambda_function.emr_batch_agent.function_name}"
  retention_in_days = 14

  tags = {
    Project = "cd1-agent"
    Agent   = "emr-batch-agent"
  }
}

# Outputs
output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.emr_batch_agent.function_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.emr_batch_agent.arn
}

output "lambda_function_url" {
  description = "Lambda function URL"
  value       = aws_lambda_function_url.emr_batch_agent_url.function_url
}
