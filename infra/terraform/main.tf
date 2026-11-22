data "aws_caller_identity" "current" {}

locals {
  name        = "${var.project}-${var.environment}"
  bucket_name = "${local.name}-${data.aws_caller_identity.current.account_id}"
}

# ---------------------------------------------------------------------------------------------
# Criptografia: chave KMS própria, com rotação anual
# ---------------------------------------------------------------------------------------------
resource "aws_kms_key" "lake" {
  description             = "Criptografia do lake ${local.name}"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.kms.json
}

data "aws_iam_policy_document" "kms" {
  # Política padrão de chave da AWS: em key policy, "*" significa "esta chave", e a administração
  # fica com a conta (o acesso efetivo é concedido pelas políticas IAM, como a do papel do pipeline).
  #checkov:skip=CKV_AWS_111:Em key policy o recurso "*" é a própria chave.
  #checkov:skip=CKV_AWS_356:Em key policy o recurso "*" é a própria chave.
  #checkov:skip=CKV_AWS_109:Administração da chave delegada à conta, padrão recomendado pela AWS.
  statement {
    sid       = "AdministracaoPelaConta"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_kms_alias" "lake" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.lake.key_id
}

# ---------------------------------------------------------------------------------------------
# Bucket de logs de acesso
# ---------------------------------------------------------------------------------------------
resource "aws_s3_bucket" "access_logs" {
  #checkov:skip=CKV_AWS_18:Este é o próprio bucket de destino dos logs de acesso.
  #checkov:skip=CKV_AWS_144:Replicação entre regiões não se justifica para logs de acesso.
  #checkov:skip=CKV2_AWS_62:Sem consumidores de eventos para logs de acesso.
  #checkov:skip=CKV_AWS_145:Destino de server access logs só aceita SSE-S3, não KMS.
  bucket = "${local.bucket_name}-logs"
}

resource "aws_s3_bucket_public_access_block" "access_logs" {
  bucket                  = aws_s3_bucket.access_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    id     = "expira-logs"
    status = "Enabled"
    filter {}
    expiration {
      days = 365
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_policy" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id
  policy = data.aws_iam_policy_document.access_logs.json
}

data "aws_iam_policy_document" "access_logs" {
  statement {
    sid       = "ServicoDeLogsDoS3"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.access_logs.arn}/s3/*"]
    principals {
      type        = "Service"
      identifiers = ["logging.s3.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    sid       = "SomenteTLS"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.access_logs.arn, "${aws_s3_bucket.access_logs.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

# ---------------------------------------------------------------------------------------------
# Lake: landing/, bronze/, quarantine/, _manifests/ e resultados do Athena
# ---------------------------------------------------------------------------------------------
resource "aws_s3_bucket" "lake" {
  #checkov:skip=CKV_AWS_144:Replicação entre regiões fica a critério do ambiente (custo x RPO); versionamento cobre exclusão acidental.
  #checkov:skip=CKV2_AWS_62:A ingestão é disparada pelo orquestrador, não por eventos do S3.
  bucket = local.bucket_name
}

resource "aws_s3_bucket_ownership_controls" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.lake.arn
    }
    # Bucket key reduz as chamadas ao KMS (e o custo) em até 99%.
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_logging" "lake" {
  bucket        = aws_s3_bucket.lake.id
  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "s3/${local.bucket_name}/"
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    id     = "landing-para-armazenamento-frio"
    status = "Enabled"
    filter {
      prefix = "landing/"
    }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
  }

  rule {
    id     = "expira-quarentena"
    status = "Enabled"
    filter {
      prefix = "quarantine/"
    }
    expiration {
      days = var.quarantine_retention_days
    }
  }

  rule {
    id     = "expira-resultados-athena"
    status = "Enabled"
    filter {
      prefix = "athena-results/"
    }
    expiration {
      days = 7
    }
  }

  rule {
    id     = "limpeza-geral"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_policy" "lake" {
  bucket = aws_s3_bucket.lake.id
  policy = data.aws_iam_policy_document.lake_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.lake]
}

data "aws_iam_policy_document" "lake_bucket" {
  statement {
    sid       = "SomenteTLS"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

# ---------------------------------------------------------------------------------------------
# Catálogo e consulta: Glue Data Catalog + Athena com limites de custo
# ---------------------------------------------------------------------------------------------
resource "aws_glue_catalog_database" "bronze" {
  name        = replace("${local.name}_bronze", "-", "_")
  description = "Tabelas do bronze (Parquet particionado por dt) do ${local.name}."
}

resource "aws_glue_catalog_database" "marts" {
  name        = replace("${local.name}_marts", "-", "_")
  description = "Marts publicados pelo dbt do ${local.name}."
}

resource "aws_athena_workgroup" "lake" {
  name          = local.name
  force_destroy = false

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_bytes_scanned_cutoff

    result_configuration {
      output_location = "s3://${aws_s3_bucket.lake.bucket}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_key.lake.arn
      }
    }
  }
}
