#!/usr/bin/env python3
"""CLI entry point for the Eightfold Multi-Source Candidate Data Transformer."""

import argparse
import json
import sys
import logging
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline import run_pipeline
from pipeline.validator import validate_output


def main():
    parser = argparse.ArgumentParser(
        description='Eightfold Multi-Source Candidate Data Transformer',
        epilog='Ingests candidate data from multiple sources, normalizes, merges, and outputs schema-valid JSON.'
    )
    parser.add_argument(
        '--input-dir', required=True,
        help='Directory containing source files (CSV, JSON, TXT)'
    )
    parser.add_argument(
        '--config', default=None,
        help='Path to runtime config JSON for output projection (optional)'
    )
    parser.add_argument(
        '--output', default=None,
        help='Output file path (default: stdout)'
    )
    parser.add_argument(
        '--validate', action='store_true',
        help='Validate output against canonical schema'
    )
    parser.add_argument(
        '--verbose', action='store_true',
        help='Print pipeline progress'
    )
    
    args = parser.parse_args()
    
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    # Suppress noisy third-party loggers
    logging.getLogger('pdfminer').setLevel(logging.WARNING)
    logging.getLogger('pdfplumber').setLevel(logging.WARNING)
    
    logger = logging.getLogger('eightfold')
    
    if not os.path.isdir(args.input_dir):
        logger.error(f"Input directory does not exist: {args.input_dir}")
        sys.exit(1)
    
    try:
        results = run_pipeline(args.input_dir, args.config)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)
    
    if args.verbose:
        logger.info(f"Pipeline produced {len(results)} merged candidate profile(s)")
    
    if args.validate and results:
        is_valid, errors = validate_output(results)
        if not is_valid:
            logger.error("Output validation failed:")
            for err in errors:
                logger.error(f"  - {err}")
            _write_output(results, args.output)
            sys.exit(1)
        else:
            if args.verbose:
                logger.info("Output validation passed")
    
    _write_output(results, args.output)
    sys.exit(0)


def _write_output(results: list[dict], output_path: str | None) -> None:
    output_json = json.dumps(results, indent=2, default=str)
    
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(output_json)
    else:
        print(output_json)


if __name__ == '__main__':
    main()
