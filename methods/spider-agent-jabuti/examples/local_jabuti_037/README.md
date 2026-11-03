# JABUTI-SQL — Task local_jabuti_037

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
**Question**: Listar as 20 instituições com maior proporção (quantidade_leitos_uti / quantidade_leitos_gerais) calculada com base nos dados da visão mv_leitos_mais_recente. Retornar instituicao_id, nome_instituicao, data_de_competencia, quantidade_leitos_gerais, quantidade_leitos_uti e proporcao_uti_por_leito_geral. Excluir registros com quantidade_leitos_gerais NULL ou <= 0; ordenar por proporção decrescente e, em caso de empate, por instituicao_id. Limitar a 20.
**Difficulty**: medium
**Persona**: Analista de Dados em Saúde
