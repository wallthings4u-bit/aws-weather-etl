#!/usr/bin/env bash
set -e

REGION="ap-northeast-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=== 1. ECRリポジトリの先行作成 ==="
cd terraform
terraform init
terraform apply -target=aws_ecr_repository.lambda_repo -auto-approve

REPO_URI=$(terraform output -raw ecr_repository_url)

echo "=== 2. Dockerイメージのビルド & ECRプッシュ ==="
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

cd ../src
docker build --provenance=false -t weather-pipeline-lambda:latest .
docker tag weather-pipeline-lambda:latest ${REPO_URI}:latest
docker push ${REPO_URI}:latest

echo "=== 3. 全AWSリソースのデプロイ ==="
cd ../terraform
terraform apply -auto-approve

echo "=== デプロイ完了！ ==="
