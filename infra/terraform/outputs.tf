output "lake_bucket" {
  description = "Bucket do lake (use em LAKE_ROOT=s3://<bucket>)."
  value       = aws_s3_bucket.lake.bucket
}

output "pipeline_role_arn" {
  description = "Papel para o aws-actions/configure-aws-credentials (role-to-assume)."
  value       = aws_iam_role.pipeline.arn
}

output "athena_workgroup" {
  description = "Workgroup do Athena com limite de bytes por consulta."
  value       = aws_athena_workgroup.lake.name
}

output "glue_databases" {
  description = "Bancos do Glue Data Catalog."
  value       = { bronze = aws_glue_catalog_database.bronze.name, marts = aws_glue_catalog_database.marts.name }
}

output "kms_key_arn" {
  description = "Chave KMS do lake."
  value       = aws_kms_key.lake.arn
}
