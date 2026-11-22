# Papel assumido pelo GitHub Actions via OIDC: sem chave de acesso de longa duração guardada em secret.

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  github_oidc_provider_arn = (
    var.create_github_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
    : data.aws_iam_openid_connect_provider.github[0].arn
  )
}

data "aws_iam_policy_document" "pipeline_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Só a branch principal do repositório configurado pode assumir o papel.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/${var.github_branch}"]
    }
  }
}

resource "aws_iam_role" "pipeline" {
  name                 = "${local.name}-pipeline"
  description          = "Pipeline do ${local.name} (GitHub Actions via OIDC)."
  assume_role_policy   = data.aws_iam_policy_document.pipeline_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "pipeline" {
  statement {
    sid       = "ListarPrefixosDoLake"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["landing/*", "bronze/*", "quarantine/*", "_manifests/*", "gold/*", "athena-results/*"]
    }
  }

  statement {
    sid     = "LerELandingEscreverCamadas"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.lake.arn}/landing/*",
      "${aws_s3_bucket.lake.arn}/bronze/*",
      "${aws_s3_bucket.lake.arn}/_manifests/*",
      "${aws_s3_bucket.lake.arn}/gold/*",
      "${aws_s3_bucket.lake.arn}/athena-results/*",
    ]
  }

  statement {
    sid     = "EscreverSomenteCamadasDoPipeline"
    actions = ["s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${aws_s3_bucket.lake.arn}/bronze/*",
      "${aws_s3_bucket.lake.arn}/quarantine/*",
      "${aws_s3_bucket.lake.arn}/_manifests/*",
      "${aws_s3_bucket.lake.arn}/gold/*",
      "${aws_s3_bucket.lake.arn}/athena-results/*",
    ]
  }

  statement {
    sid       = "UsarChaveDoLake"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.lake.arn]
  }

  statement {
    sid = "CatalogoGlue"
    actions = [
      "glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartitions",
      "glue:CreateTable", "glue:UpdateTable", "glue:BatchCreatePartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.bronze.arn,
      aws_glue_catalog_database.marts.arn,
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.bronze.name}/*",
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.marts.name}/*",
    ]
  }

  statement {
    sid       = "ConsultarNoWorkgroup"
    actions   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"]
    resources = [aws_athena_workgroup.lake.arn]
  }
}

resource "aws_iam_role_policy" "pipeline" {
  name   = "lake-access"
  role   = aws_iam_role.pipeline.id
  policy = data.aws_iam_policy_document.pipeline.json
}
