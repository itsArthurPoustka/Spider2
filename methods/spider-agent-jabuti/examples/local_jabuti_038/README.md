# JABUTI-SQL — Task local_jabuti_038

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
**Question**: Mostre as 20 instituições ou hospitais com maior percentual de leitos de UTI em relação aos leitos gerais, com base nos dados da visão mv_leitos_mais_recente. Inclua id e nome da instituição, a data de competência, a quantidade de leitos gerais, a quantidade de leitos de UTI e a proporção UTI/geral. Considere somente instituições com mais de 0 leitos gerais operacionais e ordene do maior para o menor.
**Difficulty**: medium
**Persona**: Médico Gestor Hospitalar
