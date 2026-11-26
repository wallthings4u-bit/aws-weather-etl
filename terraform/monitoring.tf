variable "alert_email" {
  description = "wallthings4u@gmail.com"
  type        = string
}

# 1. SNSトピックの作成
resource "aws_sns_topic" "lambda_error_topic" {
  name = "aws-weather-etl-lambda-errors"
}

# 2. メールサブスクリプションの登録
resource "aws_sns_topic_subscription" "email_target" {
  topic_arn = aws_sns_topic.lambda_error_topic.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# 3. CloudWatch アラーム（LambdaのErrorsメトリクスを監視）
resource "aws_cloudwatch_metric_alarm" "lambda_error_alarm" {
  alarm_name          = "aws-weather-etl-lambda-error-alarm"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Weather ETL Lambda関数（weather_ingestor）でエラーが発生しました。"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.weather_ingestor.function_name
  }

  alarm_actions = [aws_sns_topic.lambda_error_topic.arn]
}
