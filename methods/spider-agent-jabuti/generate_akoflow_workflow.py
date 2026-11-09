#!/usr/bin/env python3
"""Forwarder wrapper for akoflow/generate_akoflow_workflow.py."""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(SCRIPT_DIR, "akoflow", "generate_akoflow_workflow.py")

if __name__ == "__main__":
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    akoflow_dir = os.path.join(SCRIPT_DIR, "akoflow")
    if akoflow_dir not in sys.path:
        sys.path.insert(0, akoflow_dir)
    import generate_akoflow_workflow
    generate_akoflow_workflow.main()
