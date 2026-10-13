# JABUTI-SQL — Task local_jabuti_058

## Database
- **Engine**: PostgreSQL (running inside this container)
- **Database name**: `jabuti_sql`
- **Connect**: `psql -U postgres jabuti_sql`

## Schema
The full DDL is in `ddl.sql`.  Run `cat ddl.sql` to inspect it.
There are 15 tables with Portuguese column names.

## Key tables
| Table | Rows | Description |
|---|---|---|
| instituicao | 610K | Health institutions |
| instituicao_estoca_produto | 143M | Stock records (LARGE!) |
| mantenedora_compra_produto | 26K | Purchase records |
| leitos | 86K | Hospital beds |
| produto | 20K | Products |
| municipio | 5.5K | Municipalities |
| mv_estoque_mais_recente | — | Materialized view: latest stock |
| mv_leitos_mais_recente | — | Materialized view: latest beds |

## Warning
- `instituicao_estoca_produto` has 143 MILLION rows.
  **Never run `SELECT *` without LIMIT** on this table.
- Use the materialized views (`mv_estoque_mais_recente`,
  `mv_leitos_mais_recente`) when you need only the latest snapshot.
- All names are in Portuguese.

## Task
**Question**: Considerando o período de 01/01/2025 a 31/12/2025, identifique os 10 fornecedores com maior contagem de produto_id distintos registrados na tabela de compras da mantenedora. Para cada fornecedor, retorne fornecedor_id, nome_fornecedor, total de produtos distintos fornecidos e a mediana de preco_unitario (arredondada para duas casas decimais). Ordene por produtos_distintos em ordem decrescente.
**Difficulty**: hard
**Persona**: Analista de Dados em Saúde
