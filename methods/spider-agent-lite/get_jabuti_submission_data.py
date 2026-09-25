#!/usr/bin/env python3
"""
get_jabuti_submission_data.py — Extract JABUTI-SQL agent results for evaluation
================================================================================

PURPOSE
-------
After running ``run.py`` on the JABUTI-SQL benchmark, the agent's outputs are
stored in ``output/<experiment_suffix>/<instance_id>/spider/result.json``.
This script extracts those results and prepares them for evaluation by
``evaluate_jabuti.py``.

This is adapted from the existing ``get_spider2lite_submission_data.py`` with
the following JABUTI-specific changes:

1. **PostgreSQL CSV handling**: The agent saves results via ``psql``'s CSV
   output, which may include PostgreSQL-specific formatting.  We normalise
   the output to a standard CSV.

2. **Result metadata**: We preserve JABUTI-specific metadata (difficulty,
   persona) alongside the submission data for stratified evaluation.

USAGE
-----
  python get_jabuti_submission_data.py \\
      --all_results_path output \\
      --experiment_suffix gpt-4o-jabuti_test1 \\
      --results_folder_name evaluation/predictions/gpt-4o-jabuti_test1 \\
      --jabuti_jsonl examples/jabuti.jsonl
"""

import argparse
import json
import os
import shutil
import csv


def copy_folder(src, dest, files_to_copy=None):
    """
    Copies a folder or specified files to a destination path.
    If the destination path exists, it will be cleared first.
    """
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)

    if files_to_copy is None:
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        if isinstance(files_to_copy, str):
            files_to_copy = [files_to_copy]

        os.makedirs(dest, exist_ok=True)
        for file in files_to_copy:
            full_file_path = os.path.join(src, file)
            if os.path.exists(full_file_path):
                if os.path.isdir(full_file_path):
                    shutil.copytree(full_file_path, os.path.join(dest, file), dirs_exist_ok=True)
                else:
                    shutil.copy(full_file_path, dest)
            else:
                print(f"File {file} does not exist in the source path {src}")


def load_jabuti_metadata(jabuti_jsonl_path):
    """
    Load JABUTI-SQL task metadata (difficulty, persona, parent_id, gold_sql)
    from the JSONL file, keyed by instance_id.

    This metadata is used during evaluation for stratified reporting.
    """
    metadata = {}
    if jabuti_jsonl_path and os.path.exists(jabuti_jsonl_path):
        with open(jabuti_jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                task = json.loads(line)
                metadata[task["instance_id"]] = {
                    "difficulty": task.get("difficulty", "unknown"),
                    "persona": task.get("persona", "unknown"),
                    "parent_id": task.get("parent_id"),
                    "gold_sql": task.get("gold_sql", ""),
                }
    return metadata


def postprocess(args):
    """
    Extract agent results and prepare them for evaluation.

    ADAPTATION NOTE:
    ────────────────
    This function mirrors ``get_spider2lite_submission_data.py::postprocess()``
    but adds JABUTI-specific normalisation:

    1. psql CSV output may start with a header line like ``(N rows)`` at the
       bottom — we strip that.
    2. We save a ``submission_metadata.jsonl`` file with task-level metadata
       for the evaluation script.
    """
    output_dir = os.path.join(args.all_results_path, args.experiment_suffix)
    submission_dir = args.results_folder_name

    if not os.path.exists(submission_dir):
        os.makedirs(submission_dir)

    # Load JABUTI metadata for enrichment
    jabuti_meta = load_jabuti_metadata(args.jabuti_jsonl)

    results_metadata = []

    for instance_id in sorted(os.listdir(output_dir)):
        if not os.path.isdir(os.path.join(output_dir, instance_id)):
            continue

        # Only process JABUTI tasks
        if not instance_id.startswith("local_jabuti_"):
            continue

        json_file_path = os.path.join(output_dir, instance_id, "spider", "result.json")
        try:
            with open(json_file_path, "r") as file:
                instance_result_data = json.load(file)
        except FileNotFoundError:
            print(f"Warning: result.json not found for {instance_id}, skipping")
            continue

        result_folder_root_path = os.path.join(output_dir, instance_id)
        answer_or_path = instance_result_data.get("result", "")

        if answer_or_path.startswith("/workspace"):
            answer_or_path = answer_or_path.replace("/workspace/", "")

        # Build metadata entry
        meta_entry = {
            "instance_id": instance_id,
            "answer_or_path": answer_or_path,
            "answer_type": "unknown",
        }
        if instance_id in jabuti_meta:
            meta_entry.update(jabuti_meta[instance_id])

        if answer_or_path == "":
            meta_entry["answer_type"] = "empty"
            csv_file_path = os.path.join(submission_dir, f"{instance_id}.csv")
            with open(csv_file_path, mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["output"])
                writer.writerow([""])

        elif os.path.exists(os.path.join(result_folder_root_path, answer_or_path)):
            meta_entry["answer_type"] = "file"
            try:
                copy_folder(
                    result_folder_root_path,
                    os.path.join(submission_dir, instance_id),
                    files_to_copy=answer_or_path,
                )
            except Exception as e:
                print(f"Warning: Failed to copy result for {instance_id}: {e}")

        else:
            # The agent returned a literal answer (not a file path)
            meta_entry["answer_type"] = "answer"
            csv_file_path = os.path.join(submission_dir, f"{instance_id}.csv")
            with open(csv_file_path, mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["output"])
                writer.writerow([answer_or_path])

        results_metadata.append(meta_entry)

    # Flatten single-CSV subdirectories (same logic as original)
    for sub_dir in os.listdir(submission_dir):
        sub_dir_path = os.path.join(submission_dir, sub_dir)
        if os.path.isdir(sub_dir_path):
            csv_files = [f for f in os.listdir(sub_dir_path) if f.endswith(".csv")]
            if len(csv_files) == 1:
                csv_file_path = os.path.join(sub_dir_path, csv_files[0])
                new_csv_file_path = os.path.join(submission_dir, f"{sub_dir}.csv")
                shutil.move(csv_file_path, new_csv_file_path)
                shutil.rmtree(sub_dir_path)
            else:
                print(f"Warning: Expected one CSV in {sub_dir_path}, found {len(csv_files)}")

    # Save metadata for evaluate_jabuti.py
    meta_path = os.path.join(submission_dir, "submission_metadata.jsonl")
    with open(meta_path, "w", encoding="utf-8") as f:
        for entry in results_metadata:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Processed {len(results_metadata)} JABUTI tasks → {submission_dir}")
    print(f"Metadata saved to {meta_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract JABUTI-SQL agent results for evaluation."
    )
    parser.add_argument(
        "--all_results_path", type=str, default="output",
        help="Root directory containing all experiment outputs"
    )
    parser.add_argument(
        "--experiment_suffix", type=str, required=True,
        help="Experiment suffix (e.g., 'gpt-4o-jabuti_test1')"
    )
    parser.add_argument(
        "--results_folder_name", type=str,
        default="evaluation/predictions",
        help="Directory to write extracted submission files"
    )
    parser.add_argument(
        "--jabuti_jsonl", type=str, default="examples/jabuti.jsonl",
        help="Path to jabuti.jsonl for metadata enrichment"
    )
    args = parser.parse_args()
    postprocess(args)
