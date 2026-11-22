{# Valores numéricos não podem ser negativos (nulos são ignorados). #}
{% test non_negative(model, column_name) %}
select {{ column_name }} from {{ model }} where {{ column_name }} < 0
{% endtest %}

{# Valor dentro de uma faixa fechada [min_value, max_value]. #}
{% test between(model, column_name, min_value, max_value) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }}
{% endtest %}

{# Intervalo coerente: a coluna de fim, quando preenchida, não pode ser anterior à de início. #}
{% test valid_interval(model, column_name, end_column) %}
select {{ column_name }}, {{ end_column }}
from {{ model }}
where {{ end_column }} is not null and {{ end_column }} < {{ column_name }}
{% endtest %}

{# Combinação de colunas única (substitui dbt_utils.unique_combination_of_columns sem dependência externa). #}
{% test unique_combination(model, combination_of_columns) %}
select {{ combination_of_columns | join(', ') }}, count(*) as occurrences
from {{ model }}
group by {{ combination_of_columns | join(', ') }}
having count(*) > 1
{% endtest %}
