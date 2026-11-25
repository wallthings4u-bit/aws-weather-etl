resource "aws_cloudwatch_log_group" "lambda_log_group" {
  name              = "/aws/lambda/${var.project_name}-ingestor"
  retention_in_days = 14
}

resource "aws_lambda_function" "weather_ingestor" {
  function_name = "${var.project_name}-ingestor"
  role          = aws_iam_role.lambda_exec_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda_repo.repository_url}:${var.image_tag}"

  timeout     = 30
  memory_size = 512

  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.data_lake.id
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_log_group,
    aws_iam_role_policy_attachment.lambda_policy_attach
  ]
}
