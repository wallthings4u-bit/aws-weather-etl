# 1. AWS Glue Data Catalog データベース
resource "aws_glue_catalog_database" "weather_db" {
  # AthenaのSQLで扱いやすいようにハイフンをアンダースコアに変換
  name = "${replace(var.project_name, "-", "_")}_db"
}

# 2. AWS Glue Data Catalog テーブル（Parquet + Partition Projection）
resource "aws_glue_catalog_table" "weather_daily" {
  name          = "weather_daily"
  database_name = aws_glue_catalog_database.weather_db.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"            = "parquet"
    "parquet.compression"       = "SNAPPY"
    "EXTERNAL"                  = "TRUE"
    # Partition Projection 設定（Crawler不要で新規パーティションを自動認識）
    "projection.enabled"        = "true"
    "projection.year.type"      = "integer"
    "projection.year.range"     = "2025,2035"
    "projection.year.digits"    = "4"
    "projection.month.type"     = "integer"
    "projection.month.range"    = "1,12"
    "projection.month.digits"   = "2"
    "projection.day.type"       = "integer"
    "projection.day.range"      = "1,31"
    "projection.day.digits"     = "2"
    "storage.location.template" = "s3://${aws_s3_bucket.data_lake.id}/raw/weather_daily/year=$${year}/month=$${month}/day=$${day}"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.id}/raw/weather_daily/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "ParquetHiveSerDe"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "date"
      type = "string"
    }
    columns {
      name = "city"
      type = "string"
    }
    columns {
      name = "weather_code"
      type = "bigint"
    }
    columns {
      name = "weather_desc"
      type = "string"
    }
    columns {
      name = "temp_max"
      type = "double"
    }
    columns {
      name = "temp_min"
      type = "double"
    }
    columns {
      name = "sunrise"
      type = "string"
    }
    columns {
      name = "sunset"
      type = "string"
    }
    columns {
      name = "fetched_at"
      type = "string"
    }
  }
}

# 3. Amazon Athena ワークグループ（クエリ結果のS3出力先指定）
resource "aws_athena_workgroup" "weather_wg" {
  name          = "${var.project_name}-workgroup"
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = false

    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_lake.id}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
