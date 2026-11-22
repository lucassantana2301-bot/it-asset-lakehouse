{# Raiz do lake (diretório local ou s3://bucket/prefixo), definida pela variável de ambiente LAKE_ROOT. #}
{% macro lake_root() -%}
  {{- env_var('LAKE_ROOT', '../lake').strip().rstrip('/') -}}
{%- endmacro %}

{# Schema final = nome do schema customizado (staging, marts...), sem prefixo do target. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
