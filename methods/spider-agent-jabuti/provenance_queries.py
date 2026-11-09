#!/usr/bin/env python3
"""Forwarder wrapper for provenance/provenance_queries.py."""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROV_DIR = os.path.join(SCRIPT_DIR, "provenance")

if __name__ == "__main__":
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    if PROV_DIR not in sys.path:
        sys.path.insert(0, PROV_DIR)
    import provenance_queries
    provenance_queries.main()
