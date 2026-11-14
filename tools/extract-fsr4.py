#!/usr/bin/env python3
"""Standalone entry point, also shipped in FSR4-Extractor.zip."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "py_modules"))
from fsr4_extract import cli
if __name__ == "__main__":
    raise SystemExit(cli())
