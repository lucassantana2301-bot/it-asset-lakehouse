"""Painel executivo estático gerado a partir dos marts (publicado no GitHub Pages pelo CI).

Os gráficos são SVG gerados no servidor com matplotlib e embutidos no HTML: a página não carrega
nenhum script nem recurso externo, e funciona aberta direto do disco.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

INK, MUTED, GRID = "#1f2328", "#59636e", "#e6e8eb"
MOVEMENT_COLORS = {
    "new": "#2563eb",
    "expansion": "#16a34a",
    "reactivation": "#0d9488",
    "contraction": "#f59e0b",
    "churn": "#dc2626",
}
MOVEMENT_LABELS = {
    "new": "Novos",
    "expansion": "Expansão",
    "reactivation": "Reativação",
    "contraction": "Redução",
    "churn": "Churn",
}
ACTION_LABELS = {
    "ok": "Sem ação",
    "subutilizado": "Subutilizado",
    "investigar_sem_sinal": "Sem sinal (3+ dias)",
    "trocar_bateria": "Trocar bateria",
    "liberar_disco": "Liberar disco",
}
MONTHS_PT = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _brl(value: float | Decimal, decimals: int = 0) -> str:
    text = f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


def _pct(value: float | None, decimals: int = 1) -> str:
    return "—" if value is None else f"{value * 100:.{decimals}f}%".replace(".", ",")


def _style(ax: Any) -> None:
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _svg(fig: Any) -> str:
    buffer = io.StringIO()
    fig.savefig(buffer, format="svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    svg = buffer.getvalue()
    return svg[svg.index("<svg") :]


def _mrr_chart(rows: list[tuple[Any, ...]]) -> str:
    if not rows:
        return '<p class="note">Ainda não há meses completos depois da base inicial.</p>'
    months = sorted({r[0] for r in rows})
    fig, ax = plt.subplots(figsize=(10, 3.2))
    width = 0.15
    kinds = [k for k in MOVEMENT_COLORS if any(r[1] == k for r in rows)]
    for i, kind in enumerate(kinds):
        values = [float(next((r[2] for r in rows if r[0] == m and r[1] == kind), 0)) for m in months]
        offsets = [x + (i - (len(kinds) - 1) / 2) * width for x in range(len(months))]
        ax.bar(offsets, values, width=width * 0.9, color=MOVEMENT_COLORS[kind], label=MOVEMENT_LABELS[kind])
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xticks(range(len(months)), [f"{MONTHS_PT[m.month - 1]}/{m.year % 100}" for m in months])
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda v, _: "0" if v == 0 else f"{v / 1000:,.0f} mil".replace(",", "."))
    )
    _style(ax)
    ax.legend(frameon=False, fontsize=8, ncol=len(kinds), loc="upper center", bbox_to_anchor=(0.5, 1.15))
    return _svg(fig)


def _hbar_chart(labels: list[str], values: list[float], color: str, fmt: str = "{:.0f}") -> str:
    if not labels:
        return '<p class="note">Nada a destacar no período.</p>'
    fig, ax = plt.subplots(figsize=(5.6, 0.45 * len(labels) + 0.6))
    ax.barh(labels[::-1], values[::-1], color=color, height=0.6)
    for y, value in enumerate(values[::-1]):
        ax.text(value, y, " " + fmt.format(value), va="center", fontsize=9, color=INK)
    _style(ax)
    ax.grid(False)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="y", labelsize=9, colors=INK)
    return _svg(fig)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


CSS = """
:root { --ink:#1f2328; --muted:#59636e; --line:#e6e8eb; --bg:#f7f8fa; --card:#fff; --accent:#2563eb; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1100px; margin:0 auto; padding:32px 20px 56px; }
h1 { margin:0; font-size:26px; letter-spacing:-.01em; }
h2 { margin:0 0 12px; font-size:17px; }
p.lead { color:var(--muted); margin:4px 0 24px; }
.kpis { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:16px; }
@media (max-width:720px) { .kpis { grid-template-columns:repeat(2,1fr); } }
.kpi, .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
.kpi span { display:block; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
.kpi strong { font-size:24px; font-variant-numeric:tabular-nums; }
.kpi small { display:block; color:var(--muted); font-size:12px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:16px; margin-top:16px; }
svg { max-width:100%; height:auto; }
.wide svg { width:100%; }
.card p.note { color:var(--muted); font-size:13px; margin:-6px 0 8px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
.card { overflow-x:auto; }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); font-variant-numeric:tabular-nums; }
td, th { white-space:nowrap; }
td:first-child { white-space:normal; }
th { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
footer { color:var(--muted); font-size:13px; margin-top:28px; }
a { color:var(--accent); }
"""


def build_report(database: Path, output: Path, *, revision: str | None = None) -> Path:
    con = duckdb.connect(str(database), read_only=True)
    try:
        kpi = con.execute("select * from marts.rpt_fleet_kpis").fetchone()
        cols = [d[0] for d in con.description or ()]
        k = dict(zip(cols, kpi or (), strict=False))
        mrr_rows = con.execute(
            # O primeiro mês é a carteira inicial, não aquisição: fica fora do gráfico e vira a base.
            "select month_start, movement_type, sum(mrr_change) from marts.fct_mrr_movements "
            "where movement_type <> 'flat' and month_start > (select min(month_start) from marts.fct_mrr_movements) "
            "group by all order by 1"
        ).fetchall()
        base_month, base_mrr = con.execute(
            "select month_start, sum(mrr) from marts.fct_mrr_movements "
            "where month_start = (select min(month_start) from marts.fct_mrr_movements) group by 1"
        ).fetchone() or (None, 0)
        actions = con.execute(
            "select recommended_action, count(*) from marts.fct_asset_health "
            "where recommended_action <> 'ok' group by 1 order by 2 desc"
        ).fetchall()
        sla = con.execute(
            "select priority, avg(case when is_breached then 0 else 1 end), count(*) "
            "from marts.fct_ticket_sla group by 1 order by 1"
        ).fetchall()
        top_customers = con.execute(
            "select customer_name, segment, state, current_seats, current_mrr from marts.dim_customers "
            "where is_active order by current_mrr desc limit 8"
        ).fetchall()
        quality = con.execute(
            "select source, partitions, rows_read, rows_quarantined, quarantine_rate, orphan_rows "
            "from marts.rpt_data_quality order by source"
        ).fetchall()
    finally:
        con.close()

    kpis = [
        ("MRR", _brl(k["mrr"]), f"churn no último mês: {_brl(k['churned_mrr_last_month'])}"),
        ("Clientes ativos", str(k["active_customers"]), ""),
        (
            "Equipamentos alocados",
            f"{k['assets_deployed']:,}".replace(",", "."),
            f"ocupação {_pct(k['fleet_utilization'])}",
        ),
        ("SLA de chamados (30d)", _pct(k["sla_compliance_30d"]), "resolvidos dentro do prazo"),
        (
            "Devoluções",
            f"{k['return_median_cycle_days']:.1f} dias".replace(".", ","),
            f"{_pct(k['return_issue_rate'])} com avaria",
        ),
        ("Ações na frota", str(k["assets_needing_action"]), f"quarentena na ingestão: {_pct(k['quarantine_rate'], 2)}"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><span>{escape(t)}</span><strong>{escape(v)}</strong><small>{escape(s)}</small></div>'
        for t, v, s in kpis
    )
    actions_svg = _hbar_chart([ACTION_LABELS.get(a, a) for a, _ in actions], [float(n) for _, n in actions], "#f59e0b")
    sla_svg = _hbar_chart(
        [f"{p} ({n} chamados)" for p, _, n in sla], [float(r) * 100 for _, r, _ in sla], "#2563eb", "{:.1f}%"
    )
    customers_table = _table(
        ["Cliente", "Segmento", "UF", "Assentos", "MRR"],
        [[n, s, uf, str(seats), _brl(mrr)] for n, s, uf, seats, mrr in top_customers],
    )
    quality_table = _table(
        ["Fonte", "Partições", "Linhas", "Quarentena", "Taxa", "Órfãos"],
        [[s, str(p), f"{r:,}".replace(",", "."), str(q), _pct(rate, 2), str(o)] for s, p, r, q, rate, o in quality],
    )
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    base_label = f"{MONTHS_PT[base_month.month - 1]}/{base_month.year}" if base_month else "—"
    rev = f" · revisão <code>{escape(revision[:7])}</code>" if revision else ""

    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<title>Locabit · painel da frota</title>
<style>{CSS}</style>
</head>
<body>
<main>
  <h1>Locabit · painel da frota</h1>
  <p class="lead">Dados sintéticos de uma locadora fictícia de equipamentos de TI, processados pelo pipeline
  (ingestão → bronze → dbt → marts) a cada push. Dados até {escape(str(k["data_until"]))}{rev}.
  <a href="dbt/">Documentação e linhagem do dbt</a>.</p>
  <section class="kpis">{kpi_html}</section>
  <section class="card wide"><h2>Movimentação de MRR por mês</h2>
  <p class="note">Base inicial em {escape(base_label)}:
  {escape(_brl(base_mrr))}. A soma das barras de cada mês é exatamente a variação do MRR (teste no dbt).</p>
  {_mrr_chart(mrr_rows)}</section>
  <div class="grid">
    <section class="card"><h2>Equipamentos que pedem ação</h2>{actions_svg}</section>
    <section class="card"><h2>Chamados dentro do SLA por prioridade</h2>{sla_svg}</section>
  </div>
  <div class="grid">
    <section class="card"><h2>Maiores clientes</h2>{customers_table}</section>
    <section class="card"><h2>Qualidade de dados na ingestão</h2>{quality_table}</section>
  </div>
  <footer>Gerado em {generated}. Código e modelagem em
  <a href="https://github.com/lucassantana2301-bot/it-asset-lakehouse">it-asset-lakehouse</a>.</footer>
</main>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
