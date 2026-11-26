locals {
  github_oidc_host = join(".", ["token", "actions", "githubusercontent", "com"])
  sts_audience     = join(".", ["sts", "amazonaws", "com"])
}

# 1. GitHub OIDC プロバイダの登録
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://${local.github_oidc_host}"
  client_id_list  = [local.sts_audience]
  thumbprint_list = [
    "d367a47959a77b088bec4fe3e7dd3ec9ba733ab5",
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
    "d89e3bd43d5d909b47a18977aa9d5ce36cee184c"
  ]
}

# 2. GitHub Actions 用 IAM ロール（特定リポジトリの main ブランチのみ許可）
resource "aws_iam_role" "github_actions_deploy" {
  name = "aws-weather-etl-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${local.github_oidc_host}:aud" = local.sts_audience
          }
          StringLike = {
            "${local.github_oidc_host}:sub" = "repo:wallthings4u-bit@267817252/aws-weather-etl@1471420168:ref:refs/heads/main"
          }
        }
      }
    ]
  })
}

# 3. ECR プッシュ ＆ Lambda 更新用の最小権限ポリシー
resource "aws_iam_role_policy" "github_actions_policy" {
  name = "aws-weather-etl-github-actions-policy"
  role = aws_iam_role.github_actions_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction"
        ]
        Resource = aws_lambda_function.weather_ingestor.arn
      }
    ]
  })
}

# 4. 作成されたロールARNの出力
output "github_actions_role_arn" {
  description = "IAM Role ARN for GitHub Actions OIDC"
  value       = aws_iam_role.github_actions_deploy.arn
}
