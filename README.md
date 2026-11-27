# 天気データの自動取得・データ格納・BIダッシュボード（aws-weather-etl）

**「毎日の天気データを自動で集めて、クラウドに綺麗に整理し、グラフで見える化する」** ための自動化システムです。

これまで手動で調べてExcelにまとめるような作業を **完全自動化** し、サーバーの管理も不要（サーバーレス）なため、**月額ほぼ無料（数円〜数十円レベル）** で24時間365日動き続けます。

---

## 🎯 このシステムでできること（3つのポイント）

1. **毎日決まった時間に自動でデータ収集**
   - 毎日23時に、日本主要6都市（札幌・東京・大阪・松山・福岡・那覇）の気象データを自動で取得して保存します。
2. **「今この瞬間の天気」と「過去の推移」を1つの画面で確認**
   - Web画面（**主要都市の現在の天気 & 過去の気象履歴**）を開くと、日本地図クリックでの都市切り替えとともに、**「現在の天気・気温・湿度・降水量」**と**「これまでの気温・降水量の2軸推移グラフ」**がひと目でわかります。
3. **コマンド1つで誰でも構築・起動できる**
   - 複雑な画面操作や設定作業をなくし、プログラムを1つ実行するだけでクラウド環境の構築から画面表示まで完結します。

## 🖥 ダッシュボード画面イメージ
Splunk風のNOC/SOC監視UIを意識し、リアルタイム気象・バッチ最新結果・過去の推移グラフ（Athena検索）を1画面に集約しています。

![ダッシュボード画面プレビュー](docs/dashboard_preview.png)
---
## 🏗 アーキテクチャ構成図

```mermaid
flowchart LR
    EB[Amazon EventBridge Scheduler<br/>毎日 23:00 JST] -->|定期トリガー| Lambda[AWS Lambda<br/>Python 3.12 / Container Image]
    ECR[Amazon ECR<br/>Docker Image] -.->|イメージ取得| Lambda
    API[(Open-Meteo API<br/>6都市の気象データ)] -->|Extract| Lambda
    Lambda -->|Transform & Load<br/>Parquet / Snappy圧縮| S3[(Amazon S3 Data Lake<br/>year=YYYY/month=MM/day=DD)]
    S3 -->|Lifecycle 90日経過| Glacier[(S3 Glacier IR)]
    Glue[AWS Glue Data Catalog<br/>Partition Projection] -.->|スキーマ・パーティション定義| S3
    Athena[Amazon Athena<br/>SQL分析] -->|クエリ実行| S3
    Athena -->|クエリ結果出力| S3
    Athena -->|awswrangler経由でデータ取得| Streamlit[Streamlit BI Dashboard<br/>主要都市の現在の天気 & 過去の気象履歴]
    API -.->|現在時刻のリアルタイム気象を即時取得| Streamlit
    JMA[(気象庁 アメダスAPI)] -.->|API障害時フォールバック| Streamlit
```

---

## 💡 技術選定と設計のポイント（AWS設計ベストプラクティス）

データエンジニアリングおよびクラウドアーキテクチャの観点から、以下の設計を採用しています。

1. **列指向フォーマット（Parquet + Snappy圧縮）の採用**
   - `pandas` と `pyarrow` を用いて JSON データを Apache Parquet 形式へ変換し、スキャンデータ量の削減と Athena クエリの高速化・コスト最適化を実現しました。
2. **コンテナイメージ形式の AWS Lambda**
   - `pandas` / `pyarrow` などの重いデータ処理ライブラリを安定してパッケージングするため、Amazon ECR を用いたコンテナベース Lambda（Python 3.12）を採用しています。
   - ECR のライフサイクルポリシーにより最新3世代のイメージのみを保持し、ストレージコストを抑制しています。
3. **Partition Projection による運用レス・低コスト設計**
   - S3 キーを Hive 形式（`raw/weather_daily/year=YYYY/month=MM/day=DD/`）でパーティショニングしつつ、Glue Data Catalog テーブルに **Partition Projection** を設定しました。
   - AWS Glue Crawler の定期実行コストや `MSCK REPAIR TABLE` の運用なしで、新規追加された日付のデータを即座にクエリ可能です。
4. **冪等性（Idempotency）とストレージ階層化**
   - 日付単位の決定論的な S3 キー名で出力することで、パイプライン再実行時にもデータ重複が発生しない冪等性を担保しています。
   - S3 ライフサイクルルールを設定し、90日経過した生データは自動的に `GLACIER_IR`（Glacier Instant Retrieval）へ移行させています。
5. **セキュリティと最小権限の原則（IAM）**
   - Lambda 実行ロールには対象 S3 バケットの `raw/*` プレフィックスへの `PutObject` と CloudWatch Logs 出力のみを許可しています。
   - S3 バケットのパブリックアクセス全ブロック、SSE-S3 暗号化、および Athena ワークグループ側での暗号化強制を有効化しています。
6. **リアルタイム＆バッチのハイブリッド可視化（Streamlit）**
   - ダッシュボード表示時に現在時刻の最新気象（天気・気温・湿度・降水量）を即時取得して表示しつつ、Athena に蓄積された日次履歴データの推移グラフもあわせて確認できます。
7. **サーバーレス監視とハイブリッド可視化（CloudWatch Alarm + SNS / Streamlit）**
   - Lambda 関数の `Errors` メトリクスを CloudWatch Alarm で常時監視し、バッチ処理失敗時には Amazon SNS 経由で即座にメール通知を行う異常検知体制を構築しました。
   - 正常時は Streamlit ダッシュボード上に最終バッチ実行日時と全都市の同期完了ステータスを表示し、異常時のみプッシュ通知を行うことで運用者の通知疲れを防止しています。
8. **OIDC 認証 ＆ 自動ロールバック付き CI/CD パイプライン（GitHub Actions）**
   - 長期的な AWS アクセスキーを一切保持せず、GitHub OIDC と最小権限 IAM ロール（特定リポジトリの `main` ブランチのみ許可）による一時クレデンシャル認証を採用しました。
   - `src/` 配下のコード変更をプッシュすると、Docker イメージのビルド（Lambda 互換マニフェスト指定）・ECR プッシュ・Lambda 更新後に**自動スモークテスト（`aws lambda invoke`）**を実行し、エラー検知時は直前の正常イメージへ**自動ロールバック**する自己修復型デプロイを実現しています。
9. **NOC/SOC風ダークUI・地図クリック連動・モジュール分割設計（Streamlit / Plotly）**
   - Splunk風のダーク基調UIを採用し、Plotly による**インタラクティブ日本地図パネル**（選択都市の赤丸ハイライト＆地図上の都市クリックによる表示切替）と、**2軸複合チャート**（左軸：最高/最低気温の折れ線、右軸：降水量の棒グラフ）を実装しました。
   - 外部API通信の可用性を高めるため、Open-Meteo API 取得失敗時に**気象庁アメダスAPI → wttr.in API へ自動フォールバック**する耐障害設計を組み込んでいます。
   - 保守性を高めるため、ダッシュボードコードを責務ごとに4ファイル（`app.py` / `config.py` / `data_loader.py` / `charts.py`）へモジュール分割しています。

---

## 🛠 使用技術スタック

| カテゴリ | 技術・サービス | 用途 |
| :--- | :--- | :--- |
| **IaC** | Terraform | AWSリソース全体のプロビジョニング |
| **Compute / Container** | AWS Lambda, Amazon ECR, Docker | サーバーレスETL処理の実行環境 |
| **Language / Library** | Python 3.12, pandas, pyarrow, boto3, requests | データ取得・Parquet変換・S3アップロード |
| **Orchestration** | Amazon EventBridge Scheduler | タイムゾーン指定（`Asia/Tokyo`）での定期実行 |
| **Storage** | Amazon S3 | パーティション構成データレイク・クエリ結果保存 |
| **Data Catalog / Query** | AWS Glue Data Catalog, Amazon Athena | メタデータ管理・サーバーレスSQL分析 |
| **BI / Visualization** | Streamlit, awswrangler, Plotly | Athenaデータ取得・日本地図連動・2軸複合チャート可視化 |
| **Monitoring / CI/CD** | CloudWatch Alarm, SNS, GitHub Actions (OIDC) | 障害メール通知・スモークテスト・自動ロールバック付デプロイ |
| **External API** | Open-Meteo API, 気象庁 アメダスAPI | 日本6都市の気象データ取得・リアルタイムAPIフォールバック |

---

## 📂 ディレクトリ構成

```text
aws-weather-etl/
├── README.md
├── .gitignore
├── deploy.sh                      # AWSインフラ・コンテナ一括デプロイスクリプト
├── run_dashboard.sh               # Streamlitダッシュボードワンコマンド起動スクリプト
├── .github/
│   └── workflows/
│       └── deploy.yml           # GitHub Actions CI/CD（OIDC認証・スモークテスト・自動ロールバック）
├── src/
│   ├── Dockerfile                 # public.ecr.aws/lambda/python:3.12 ベース
│   ├── requirements.txt           # Lambda用Python依存ライブラリ
│   └── handler.py                 # ETL処理本体（Extract / Transform / Load）
├── terraform/
│   ├── main.tf                    # Provider設定
│   ├── variables.tf               # 変数定義
│   ├── ecr.tf                     # ECRリポジトリ・ライフサイクルポリシー
│   ├── s3.tf                      # S3バケット・暗号化・ライフサイクル設定
│   ├── iam.tf                     # Lambda最小権限IAMロール・ポリシー
│   ├── lambda.tf                  # Lambda関数・CloudWatch Logs設定
│   ├── eventbridge.tf             # EventBridge Scheduler設定
│   ├── athena.tf                  # Glue Data Catalog・Athena Workgroup設定
│   ├── monitoring.tf              # CloudWatch Alarm・SNS 障害メール通知設定
│   ├── github_actions.tf          # GitHub OIDC プロバイダ・最小権限デプロイ用IAMロール設定
│   └── outputs.tf                 # 出力値定義
└── dashboard/
    ├── app.py                     # メインUI・レイアウト制御（日本地図クリック連動・カード配置）
    ├── config.py                  # 6都市マスタ・WMO天気コード絵文字変換・NOC風カスタムCSS
    ├── data_loader.py             # Athenaクエリ・Open-Meteo/気象庁アメダスAPI取得ロジック
    ├── charts.py                  # Plotly日本地図パネル・気温/降水量2軸複合チャート描画
    └── requirements.txt           # ダッシュボード用Python依存ライブラリ
```

---

## 🚀 デプロイ手順

前提条件（AWS CLI / Terraform / Docker）が整った状態で、以下のスクリプトを実行すると ECR 作成・イメージプッシュ・全インフラ構築が一括で完了します。

```bash
./deploy.sh
```

---

## 📈 BIダッシュボードの起動手順

以下のスクリプトを実行し、ブラウザで `http://localhost:8501` にアクセスするとダッシュボード（**主要都市の現在の天気 & 過去の気象履歴**）が表示されます（初回は仮想環境とライブラリが自動セットアップされます）。

```bash
./run_dashboard.sh
```
