variable "aws_region" {
  description = "デプロイ先のAWSリージョン"
  type        = string
  default     = "ap-northeast-1"
}

variable "project_name" {
  description = "プロジェクト名（リソース名のプレフィックスに使用）"
  type        = string
  default     = "weather-pipeline"
}

variable "environment" {
  description = "環境名"
  type        = string
  default     = "prod"
}

variable "image_tag" {
  description = "Lambdaで使用するDockerイメージのタグ"
  type        = string
  default     = "latest"
}
