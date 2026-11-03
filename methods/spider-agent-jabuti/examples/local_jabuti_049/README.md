# JABUTI-SQL — Task local_jabuti_049

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
**Question**: Para o ano de 2025, agregue os dados da tabela leitos por instituição e por trimestre (a partir de data_de_competencia) e identifique, em cada trimestre, as 5 instituições com maior soma de quantidade_leitos_sus. Retorne, por trimestre, o instituicao_id, o nome_instituicao e o total de leitos SUS, ordenando dentro de cada trimestre em ordem decrescente do total agregado.
**Difficulty**: medium
**Persona**: Analista de Dados em Saúde
