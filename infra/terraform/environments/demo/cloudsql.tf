# Cloud SQL for PostgreSQL
resource "google_sql_database_instance" "main" {
  name             = "openisec-db-${var.environment}"
  database_version = "POSTGRES_15"
  region           = var.region
  project          = var.project_id

  # prd/stgではtrueに設定（terraform destroyによる誤削除防止）
  deletion_protection = contains(["prd", "demo"], var.environment) ? true : false

  # vpc.tf の private services access 設定が先に完了している必要がある
  depends_on = [google_service_networking_connection.private_vpc_connection]

  settings {
    tier = var.db_tier

    # prd/stgはREGIONAL（マルチAZ高可用性）、devはZONAL（コスト削減）
    availability_type = contains(["prd", "demo"], var.environment) ? "REGIONAL" : "ZONAL"

    # トップレベルのdeletion_protectionはTerraform操作のみを防ぐガード。
    # こちらはCloud SQL API自体の削除保護（gcloud/コンソールからの直接削除も防ぐ）。
    # prdでは必ずtrueにすること。
    deletion_protection_enabled = contains(["prd", "demo"], var.environment) ? true : false

    backup_configuration {
      enabled    = true
      start_time = "18:00" # UTC = JST 03:00
      # prdのみPITR（任意時点復元）を有効化
      point_in_time_recovery_enabled = contains(["prd", "demo"], var.environment) ? true : false
    }

    ip_configuration {
      # dev: Cloud SQL Auth Proxy経由でパブリックIP接続
      # stg/prd: プライベートIP（VPC内接続）のみ
      # SNYK-CC-TF-242: dev環境のみ許容。stg/prdは ipv4_enabled=false + private_network使用
      # stg/demo/prdはそれぞれ自環境のVPC（vpc.tf）を参照する
      ipv4_enabled    = var.environment == "dev" ? true : false
      private_network = var.environment != "dev" ? google_compute_network.vpc.id : null
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    database_flags {
      name  = "log_connections"
      value = "on"
    }

    database_flags {
      name  = "log_disconnections"
      value = "on"
    }

    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }

    database_flags {
      name  = "cloudsql.enable_pgaudit"
      value = "on"
    }

    database_flags {
      name  = "log_min_messages"
      value = "log"
    }

    # prd/stgのみIAMデータベース認証を有効化
    dynamic "database_flags" {
      for_each = var.environment != "dev" ? [1] : []
      content {
        name  = "cloudsql.iam_authentication"
        value = "on"
      }
    }
  }
}

resource "google_sql_database" "main" {
  name     = var.db_name
  instance = google_sql_database_instance.main.name
  project  = var.project_id
}

resource "google_sql_user" "app_user" {
  name     = "appuser"
  instance = google_sql_database_instance.main.name
  password = random_password.db_password.result
  project  = var.project_id
}

resource "random_password" "db_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "db-password-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

resource "google_secret_manager_secret" "db_connection_string" {
  secret_id = "db-connection-string-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_connection_string" {
  secret      = google_secret_manager_secret.db_connection_string.id
  # 同期版 create_engine を使用しているため psycopg2 ドライバを指定
  secret_data = "postgresql+psycopg2://appuser:${random_password.db_password.result}@/openisec?host=/cloudsql/${var.project_id}:${var.region}:openisec-db-${var.environment}"
}
