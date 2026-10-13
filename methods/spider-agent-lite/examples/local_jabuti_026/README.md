# JABUTI-SQL — Task local_jabuti_026

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
**Question**: Quais são as 20 unidades (ID da instituição) com maior número de medicamentos com estoque crítico (1 a 5 unidades)? Forneça o ID da instituição e a contagem de produtos nessa condição, ordenadas pelas que têm mais itens críticos; em caso de empate, ordenar pelo ID da instituição (crescente).
**Difficulty**: simple
**Persona**: Médico Gestor Hospitalar
