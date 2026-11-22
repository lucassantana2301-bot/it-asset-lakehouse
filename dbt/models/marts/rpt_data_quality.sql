-- Qualidade de dados por fonte: volume, quarentena, frescor e órfãos de telemetria.
with manifests as (
    select
        source,
        count(*) as partitions,
        sum(rows_read) as rows_read,
        sum(rows_quarantined) as rows_quarantined,
        max(partition_date) as latest_partition,
        max(ingested_at) as last_ingested_at
    from {{ ref('stg_ingestion_manifests') }}
    group by all
),

orphans as (
    select 'telemetry' as source, count(*) as orphan_rows from {{ ref('int_telemetry_orphans') }}
)

select
    cast(m.source as varchar) as source,
    cast(m.partitions as integer) as partitions,
    cast(m.rows_read as bigint) as rows_read,
    cast(m.rows_quarantined as bigint) as rows_quarantined,
    cast(round(m.rows_quarantined::double / nullif(m.rows_read, 0), 5) as double) as quarantine_rate,
    cast(coalesce(o.orphan_rows, 0) as bigint) as orphan_rows,
    cast(m.latest_partition as date) as latest_partition,
    cast(m.last_ingested_at as timestamp) as last_ingested_at
from manifests as m
left join orphans as o using (source)
