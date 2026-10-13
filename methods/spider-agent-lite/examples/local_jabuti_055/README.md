# JABUTI-SQL — Task local_jabuti_055

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
**Question**: Para o ano de 2025, retorne os registros da tabela leitos por mês de competência e por região do Brasil, agregando a quantidade_leitos_uti. Apresente, para cada região e para cada mês (1 a 12), o total de leitos de UTI e a variação percentual em relação ao mês imediatamente anterior, calculada a partir de fevereiro. Caso o total do mês anterior seja igual a zero, a variação deve ser retornada como nula. Considere a série mensal completa de janeiro a dezembro de 2025, garantindo que meses sem registro explícito sejam tratados como zero para fins de agregação e cálculo da variação.
**Difficulty**: hard
**Persona**: Analista de Dados em Saúde
