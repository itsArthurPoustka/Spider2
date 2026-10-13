# JABUTI-SQL — Task local_jabuti_010

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
**Question**: Retorne, por produto_id, a soma da quantidade_do_item_em_estoque para registros com data_de_validade preenchida e anterior a 2025-12-31 (e quantidade_do_item_em_estoque > 0), representando o total de estoque expirado até o fechamento de 2025; agrupe por produto_id, ordene por quantidade expirada decrescente e produto_id ascendente, limitando aos 100 primeiros.
**Difficulty**: simple
**Persona**: Analista de Dados em Saúde
