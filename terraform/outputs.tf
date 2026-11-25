output "ecr_repository_url" {
  description = "DockerイメージをプッシュするECRリポジトリURL"
  value       = aws_ecr_repository.lambda_repo.repository_url
}

output "s3_bucket_name" {
  description = "データが保存されるS3バケット名"
  value       = aws_s3_bucket.data_lake.id
}

output "lambda_function_name" {
  description = "作成されたLambda関数名"
  value       = aws_lambda_function.weather_ingestor.function_name
}
