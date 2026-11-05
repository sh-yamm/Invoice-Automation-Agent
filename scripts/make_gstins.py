"""Print valid GSTINs (with the correct check digit) for test data.

Usage:  py -3.11 scripts/make_gstins.py 29AABCZ5821K1Z 27AAPFN6620Q1Z ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
from ap_agent.rules.india.gstin import gstin_check_digit  # noqa: E402

for base in sys.argv[1:] or ["29AABCZ5821K1Z"]:
    print(base + gstin_check_digit(base.upper()))
