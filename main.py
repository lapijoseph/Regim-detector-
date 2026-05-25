#!/usr/bin/env python3
"""
Capitalure Prime — Market Regime Detector & Trading Calculator
Entry point with unified CLI interface.
"""

import sys
import os
from pathlib import Path


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from regime_cli import main as cli_main
    cli_main()


if __name__ == '__main__':
    main()
