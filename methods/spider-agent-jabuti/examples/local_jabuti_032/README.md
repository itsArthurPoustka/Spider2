# JABUTI-SQL — Task local_jabuti_032

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
**Question**: Preciso identificar, por instituição, quais medicamentos com saldo disponível vencem no período de 2025-01-01 a 2025-01-14 (inclusive). Para cada item, apresente a instituição, o produto, a quantidade em estoque, a data de validade e quantos dias restam até o vencimento (considerando como referência 2025-01-01), priorizando os que vencem primeiro e, em seguida, ordenando por instituição.
**Difficulty**: medium
**Persona**: Médico Gestor Hospitalar
