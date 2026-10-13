# JABUTI-SQL — Task local_jabuti_056

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
**Question**: Mostre como evoluiu a oferta de leitos de UTI ao longo de 2025 em cada região do Brasil. Para cada mês do ano, mostre o total de leitos de UTI disponíveis em cada região e a variação percentual em relação ao mês anterior. A partir de fevereiro, calcule essa variação; Só calcule se no mês anterior não houver leitos registrados.
**Difficulty**: hard
**Persona**: Médico Gestor Hospitalar
