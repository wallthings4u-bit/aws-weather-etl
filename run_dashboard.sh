#!/usr/bin/env bash
set -e

if [ ! -d ".venv-dashboard" ]; then
  echo "初回セットアップを実行中（仮想環境・ライブラリインストール）..."
  python3 -m venv .venv-dashboard
  .venv-dashboard/bin/pip install -q -r dashboard/requirements.txt
fi

export AWS_DEFAULT_REGION="ap-northeast-1"
export ATHENA_DATABASE=$(terraform -chdir=terraform output -raw glue_database_name)
export ATHENA_WORKGROUP=$(terraform -chdir=terraform output -raw athena_workgroup_name)

echo "ダッシュボードを起動します: http://localhost:8501"
.venv-dashboard/bin/streamlit run dashboard/app.py
