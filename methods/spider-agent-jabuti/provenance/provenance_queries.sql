-- ============================================================================
-- JABUTI-SQL PROVENANCE & TELEMETRY QUERY CATALOG
-- Standalone SQL script for DBeaver, TablePlus, or SQLite CLI
-- Compatible with: provenance.db
-- ============================================================================


-- ----------------------------------------------------------------------------
-- SECTION: ACCURACY & STRATIFICATION
-- ----------------------------------------------------------------------------

-- Query 01: Overall Benchmark Execution Summary (ID: overall_summary)
-- Description: High-level summary of the model, accuracy, task count, and average latencies.
SELECT 
    run_id,
    model,
    provider,
    total_tasks,
    correct_tasks,
    ROUND(accuracy * 100, 1) || '%' AS accuracy,
    ROUND(total_duration_sec / 60.0, 1) AS total_minutes,
    avg_llm_sec,
    avg_db_sec
FROM runs;

-- Query 02: Performance Stratified by Persona (ID: persona_performance)
-- Description: Measures accuracy, average inference time, and ReAct steps across the three distinct personas.
SELECT 
    persona,
    COUNT(*) AS total_tasks,
    SUM(is_correct) AS correct_tasks,
    ROUND(AVG(is_correct) * 100, 1) || '%' AS accuracy,
    ROUND(AVG(t_llm_ms) / 1000.0, 1) AS avg_llm_sec,
    ROUND(AVG(t_db_ms) / 1000.0, 3) AS avg_db_sec,
    ROUND(AVG(step_count), 1) AS avg_steps
FROM task_provenance
GROUP BY persona
ORDER BY AVG(is_correct) DESC;

-- Query 03: Performance Stratified by Difficulty Tier (ID: difficulty_breakdown)
-- Description: Examines how accuracy and reasoning effort scale across simple, medium, and hard tasks.
SELECT 
    difficulty,
    COUNT(*) AS total_tasks,
    SUM(is_correct) AS correct_tasks,
    ROUND(AVG(is_correct) * 100, 1) || '%' AS accuracy,
    ROUND(AVG(t_llm_ms) / 1000.0, 1) AS avg_llm_sec,
    ROUND(AVG(step_count), 1) AS avg_steps
FROM task_provenance
GROUP BY difficulty
ORDER BY 
    CASE difficulty 
        WHEN 'simple' THEN 1 
        WHEN 'medium' THEN 2 
        WHEN 'hard' THEN 3 
        ELSE 4 
    END;

-- Query 04: Semantic Consistency Across Persona Formulations (ID: semantic_consistency)
-- Description: Checks whether an agent consistently answers all 3 persona phrasings of the same underlying inquiry.
SELECT 
    parent_group,
    COUNT(*) AS total_personas,
    SUM(is_correct) AS correct_personas,
    CASE 
        WHEN SUM(is_correct) = 3 THEN 'Fully Consistent (3/3)'
        WHEN SUM(is_correct) > 0 THEN 'Partially Consistent'
        ELSE 'Failed (0/3)'
    END AS consistency_status,
    GROUP_CONCAT(persona || ': ' || CASE WHEN is_correct = 1 THEN '✅' ELSE '❌' END, ' | ') AS persona_details
FROM task_provenance
GROUP BY parent_group
ORDER BY CAST(parent_group AS INTEGER);

-- Query 05: Semantic Consistency Aggregate Summary (ID: semantic_consistency_summary)
-- Description: Calculates the overall percentage of inquiry groups that are fully vs partially correct.
WITH group_stats AS (
    SELECT 
        parent_group,
        SUM(is_correct) AS correct_count
    FROM task_provenance
    GROUP BY parent_group
)
SELECT 
    COUNT(*) AS total_inquiry_groups,
    SUM(CASE WHEN correct_count = 3 THEN 1 ELSE 0 END) AS fully_consistent_groups,
    ROUND(AVG(CASE WHEN correct_count = 3 THEN 1.0 ELSE 0.0 END) * 100, 1) || '%' AS fully_consistent_pct,
    SUM(CASE WHEN correct_count > 0 THEN 1 ELSE 0 END) AS partially_consistent_groups,
    ROUND(AVG(CASE WHEN correct_count > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) || '%' AS partially_consistent_pct,
    SUM(CASE WHEN correct_count = 0 THEN 1 ELSE 0 END) AS completely_failed_groups
FROM group_stats;


-- ----------------------------------------------------------------------------
-- SECTION: LATENCY & TELEMETRY
-- ----------------------------------------------------------------------------

-- Query 06: Decomposed Wall-Clock Latency Breakdown (T_LLM vs T_DB) (ID: decomposed_latency_summary)
-- Description: Aggregates total runtime into LLM inference, DB execution, and container/IO overhead.
SELECT 
    COUNT(*) AS tasks,
    ROUND(AVG(t_total_ms) / 1000.0, 2) AS avg_total_sec,
    ROUND(AVG(t_llm_ms) / 1000.0, 2) AS avg_llm_sec,
    ROUND(AVG(t_llm_ms) * 100.0 / AVG(t_total_ms), 1) || '%' AS llm_time_pct,
    ROUND(AVG(t_db_ms) / 1000.0, 3) AS avg_db_sec,
    ROUND(AVG(t_db_ms) * 100.0 / AVG(t_total_ms), 1) || '%' AS db_time_pct,
    ROUND(AVG(t_other_ms) / 1000.0, 2) AS avg_other_sec,
    ROUND(AVG(t_llm_ms) / NULLIF(AVG(t_db_ms), 0), 1) || 'x' AS llm_over_db_ratio
FROM task_provenance;

-- Query 07: Top 10 Slowest Tasks (Total Wall-Clock Time) (ID: slowest_tasks)
-- Description: Identifies tasks with the longest total execution time and decomposes where time was spent.
SELECT 
    task_id,
    persona,
    difficulty,
    step_count,
    ROUND(t_total_ms / 1000.0, 1) AS total_sec,
    ROUND(t_llm_ms / 1000.0, 1) AS llm_sec,
    ROUND(t_db_ms / 1000.0, 2) AS db_sec,
    is_correct,
    exit_code
FROM task_provenance
ORDER BY t_total_ms DESC
LIMIT 10;

-- Query 08: Top 10 Tasks with Highest PostgreSQL Query Latency (T_DB) (ID: db_heavy_tasks)
-- Description: Finds queries that performed heavy database work (e.g. joins over large stock tables).
SELECT 
    task_id,
    persona,
    difficulty,
    ROUND(t_db_ms / 1000.0, 2) AS db_sec,
    ROUND(t_llm_ms / 1000.0, 1) AS llm_sec,
    step_count,
    is_correct
FROM task_provenance
ORDER BY t_db_ms DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- SECTION: COGNITIVE & TOKENS
-- ----------------------------------------------------------------------------

-- Query 09: Token Consumption & Economics by Persona (ID: token_consumption_by_persona)
-- Description: Measures total and average prompt/completion tokens consumed per persona.
SELECT 
    persona,
    COUNT(*) AS tasks,
    SUM(tokens_total) AS total_tokens,
    ROUND(AVG(tokens_prompt), 0) AS avg_prompt_tokens,
    ROUND(AVG(tokens_completion), 0) AS avg_completion_tokens,
    ROUND(AVG(tokens_total), 0) AS avg_total_tokens
FROM task_provenance
GROUP BY persona
ORDER BY total_tokens DESC;

-- Query 10: Tasks with Long Reasoning Loops (Steps >= 8) (ID: high_step_tasks)
-- Description: Lists tasks where the agent required many ReAct iterations to converge or struggle.
SELECT 
    task_id,
    persona,
    difficulty,
    step_count,
    ROUND(t_llm_ms / 1000.0, 1) AS llm_sec,
    is_correct,
    exit_code,
    SUBSTR(error_info, 1, 40) AS error_snippet
FROM task_provenance
WHERE step_count >= 8
ORDER BY step_count DESC;

-- Query 11: Distribution of Agent Action Types in Steps (ID: react_action_distribution)
-- Description: Counts how many times each action type (Bash, Terminate, etc.) was executed.
SELECT 
    action_type,
    COUNT(*) AS total_executions,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM task_steps), 1) || '%' AS percentage
FROM task_steps
GROUP BY action_type
ORDER BY total_executions DESC;


-- ----------------------------------------------------------------------------
-- SECTION: TOOL ADHERENCE
-- ----------------------------------------------------------------------------

-- Query 12: SQL Export Syntax Adherence (RFC 4180 Compliance) (ID: export_syntax_compliance)
-- Description: Checks adherence to recommended COPY (...) TO STDOUT WITH CSV HEADER syntax.
SELECT 
    export_syntax,
    COUNT(*) AS task_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM task_provenance), 1) || '%' AS percentage,
    SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_tasks,
    ROUND(AVG(is_correct) * 100, 1) || '%' AS accuracy
FROM task_provenance
GROUP BY export_syntax
ORDER BY task_count DESC;

-- Query 13: Tasks Using Non-Standard Export Methods (ID: non_standard_exports)
-- Description: Lists tasks that fell back to PSQL_PLAIN or failed to export result.csv cleanly.
SELECT 
    task_id,
    persona,
    export_syntax,
    is_correct,
    exit_code,
    error_info
FROM task_provenance
WHERE export_syntax != 'COPY_TO_STDOUT';


-- ----------------------------------------------------------------------------
-- SECTION: FAILURE DIAGNOSTICS
-- ----------------------------------------------------------------------------

-- Query 14: Detailed Diagnostics on Failed Tasks (ID: failed_tasks_detail)
-- Description: Inspects predicted row count vs gold row count for all incorrect tasks.
SELECT 
    task_id,
    persona,
    difficulty,
    step_count,
    pred_rows,
    gold_rows,
    exit_code,
    COALESCE(error_info, 'Result value mismatch') AS failure_reason
FROM task_provenance
WHERE is_correct = 0 OR is_correct IS NULL
ORDER BY CAST(SUBSTR(task_id, 14) AS INTEGER);

-- Query 15: Row Count Mismatches (Prediction vs Gold Standard) (ID: row_count_mismatches)
-- Description: Tasks where the model produced rows, but the number of rows was different from gold.
SELECT 
    task_id,
    persona,
    difficulty,
    pred_rows,
    gold_rows,
    (pred_rows - gold_rows) AS row_delta
FROM task_provenance
WHERE pred_rows != gold_rows AND is_correct = 0 AND pred_rows IS NOT NULL
ORDER BY ABS(pred_rows - gold_rows) DESC;

-- Query 16: Tasks with Missing or Empty Predictions (ID: empty_predictions)
-- Description: Finds tasks where result.csv was empty (0 bytes) or failed to execute.
SELECT 
    task_id,
    persona,
    difficulty,
    exit_code,
    csv_sha256,
    error_info
FROM task_provenance
WHERE pred_rows IS NULL OR pred_rows = 0 OR exit_code != 0;


-- ----------------------------------------------------------------------------
-- SECTION: SCIENTIFIC LINEAGE
-- ----------------------------------------------------------------------------

-- Query 17: Cryptographic Lineage Audit (SHA256 Integrity) (ID: provenance_integrity_audit)
-- Description: Verifies that all required cryptographic digests were captured for scientific audit.
SELECT 
    COUNT(*) AS total_tasks,
    SUM(CASE WHEN prompt_hash IS NOT NULL AND prompt_hash != '' THEN 1 ELSE 0 END) AS valid_prompt_hashes,
    SUM(CASE WHEN schema_sha256 IS NOT NULL AND schema_sha256 != '' THEN 1 ELSE 0 END) AS valid_schema_hashes,
    SUM(CASE WHEN model_digest IS NOT NULL AND model_digest != '' THEN 1 ELSE 0 END) AS valid_model_digests,
    SUM(CASE WHEN csv_sha256 IS NOT NULL AND csv_sha256 != '' THEN 1 ELSE 0 END) AS valid_csv_hashes,
    SUM(CASE WHEN raw_prov_json IS NOT NULL THEN 1 ELSE 0 END) AS valid_w3c_records
FROM task_provenance;

-- Query 18: Model Version and Weights Digest Audit (ID: model_version_audit)
-- Description: Audits model tag, weights digest, provider, and container across tasks.
SELECT 
    model,
    model_digest,
    provider,
    COUNT(*) AS task_count
FROM task_provenance
GROUP BY model, model_digest, provider;
