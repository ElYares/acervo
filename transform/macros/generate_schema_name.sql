{#
  Por defecto dbt concatena: `+schema: puente` sobre un target `gold` da
  `gold_puente`. Eso tiene sentido cuando el schema es un prefijo de aislamiento
  entre desarrolladores; aqui no lo es. `silver` y `gold` son namespaces reales
  del catalogo Iceberg, con nombres que ya estan escritos en las decisiones del
  proyecto y en las consultas de quien lo lea. Un `gold_puente` seria un
  namespace inventado por la herramienta.

  Asi que `+schema: X` significa literalmente X.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
