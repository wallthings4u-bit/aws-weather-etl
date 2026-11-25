resource "aws_scheduler_schedule" "daily_weather_fetch" {
  name       = "${var.project_name}-daily-2300-jst"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 23 * * ? *)"
  schedule_expression_timezone = "Asia/Tokyo"

  target {
    arn      = aws_lambda_function.weather_ingestor.arn
    role_arn = aws_iam_role.scheduler_exec_role.arn
  }
}
