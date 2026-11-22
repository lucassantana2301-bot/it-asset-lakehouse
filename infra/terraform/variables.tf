variable "project" {
  description = "Prefixo dos recursos."
  type        = string
  default     = "locabit-lakehouse"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,30}$", var.project))
    error_message = "Use de 3 a 30 caracteres: letras minúsculas, números e hífen."
  }
}

variable "environment" {
  description = "Ambiente (dev, staging, prod)."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "O ambiente precisa ser dev, staging ou prod."
  }
}

variable "aws_region" {
  description = "Região da AWS."
  type        = string
  default     = "sa-east-1"
}

variable "github_repository" {
  description = "Repositório (owner/nome) autorizado a assumir o papel do pipeline via OIDC."
  type        = string
  default     = "lucassantana2301-bot/it-asset-lakehouse"
}

variable "github_branch" {
  description = "Branch autorizada a assumir o papel (o pipeline só escreve no lake a partir dela)."
  type        = string
  default     = "main"
}

variable "create_github_oidc_provider" {
  description = "Cria o provedor OIDC do GitHub. Use false se a conta já tiver um (é único por conta)."
  type        = bool
  default     = true
}

variable "quarantine_retention_days" {
  description = "Dias que as linhas reprovadas ficam na quarentena antes de expirar."
  type        = number
  default     = 90
}

variable "athena_bytes_scanned_cutoff" {
  description = "Limite de bytes lidos por consulta no Athena (proteção de custo)."
  type        = number
  default     = 10737418240 # 10 GiB
}
