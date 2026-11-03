# JABUTI-SQL — Task local_jabuti_031

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
**Question**: Liste os itens da visão mv_estoque_mais_recente com quantidade positiva e data de validade no período de 2025-01-01 a 2025-01-14 (inclusive). Retorne instituicao_id, nome_instituicao, produto_id, quantidade_do_item_em_estoque, data_de_validade e o número de dias até o vencimento (calculado em relação a 2025-01-01), ordenando pelos menores prazos e, em seguida, por instituição.
**Difficulty**: medium
**Persona**: Analista de Dados em Saúde
