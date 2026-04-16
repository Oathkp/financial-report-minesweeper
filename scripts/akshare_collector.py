#!/usr/bin/env python3
"""Financial Report Minesweeper - Akshare Data Collector.

Facade module: re-exports all public names and defines AkshareClient
which inherits from mixin classes in akshare_modules/.

Collects 5 years of financial data from Akshare API and outputs
a structured data_pack_market.md file.

Usage:
    python3 scripts/akshare_collector.py --code 600887
    python3 scripts/akshare_collector.py --code 600887 --output output/data_pack.md
    python3 scripts/akshare_collector.py --code 600887 --dry-run
"""

import argparse
import functools
import os
import sys
import time

import pandas as pd

try:
    import yfinance as yf
    _yf_available = True
except ImportError:
    _yf_available = False

import akshare as ak

from config import validate_stock_code
from format_utils import format_number, format_table, format_header

# Re-export all constants and mixin classes for backward compatibility.
from akshare_modules import (
    InfrastructureMixin, FinancialsMixin,
    DerivedMetricsMixin, AssemblyMixin,
    WarningsCollector,
)


def rate_limit(func):
    """Decorator to enforce 0.5s delay between Akshare API calls."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        time.sleep(0.5)
        return func(*args, **kwargs)
    return wrapper


class AkshareClient(
    InfrastructureMixin,
    FinancialsMixin,
    DerivedMetricsMixin,
    AssemblyMixin,
):
    """Client for Akshare API with rate limiting and retry logic."""

    MAX_RETRIES = 5
    RETRY_DELAY = 2.0  # seconds between retries

    BASIC_CACHE_TTL = 7 * 86400  # 7 days in seconds

    def __init__(self):
        self.token = None  # Akshare doesn't require a token
        self._store = {}  # {key: pd.DataFrame} for derived metrics computation
        self._yf_available = _yf_available
        self._cache_dir = os.path.join("output", ".collector_cache")
        self._fy_end_month: int = 12  # default: calendar year
        self._currency: str = "CNY"

    @rate_limit
    def _safe_call(self, api_name: str, **kwargs) -> pd.DataFrame:
        """Call an Akshare API endpoint with retry logic.

        Args:
            api_name: The Akshare function name (e.g., 'stock_individual_info_em').
            **kwargs: Parameters passed to the API call.

        Returns:
            DataFrame with results.

        Raises:
            RuntimeError: After MAX_RETRIES failures.
        """
        last_err = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                api_func = getattr(ak, api_name, None)
                if api_func is None:
                    raise RuntimeError(f"Akshare has no function: {api_name}")
                df = api_func(**kwargs)
                if df is None:
                    return pd.DataFrame()
                if isinstance(df, dict):
                    # Some akshare functions return dict, convert to DataFrame
                    return pd.DataFrame([df])
                return df
            except Exception as e:
                last_err = e
                if attempt < self.MAX_RETRIES:
                    is_conn_err = isinstance(e, (ConnectionError, OSError, TimeoutError)) or \
                        "RemoteDisconnected" in type(e).__name__ or \
                        "ConnectionAborted" in str(e) or \
                        "RemoteDisconnected" in str(e)
                    if is_conn_err:
                        print(f"[retry {attempt}/{self.MAX_RETRIES}] {api_name}: connection error, retrying...", file=sys.stderr)
                    else:
                        print(f"[retry {attempt}/{self.MAX_RETRIES}] {api_name}: {e}", file=sys.stderr)
                    time.sleep(self.RETRY_DELAY * attempt)
        raise RuntimeError(
            f"Akshare API '{api_name}' failed after {self.MAX_RETRIES} retries: {last_err}"
        )

    def _cached_basic_call(self, api_name: str, **kwargs) -> pd.DataFrame:
        """Call stock info API with 7-day file cache."""
        ts_code = kwargs.get("symbol", "all")
        cache_file = os.path.join(self._cache_dir, f"{api_name}_{ts_code}.json")
        if os.path.exists(cache_file):
            mtime = os.path.getmtime(cache_file)
            if time.time() - mtime < self.BASIC_CACHE_TTL:
                return pd.read_json(cache_file)
        df = self._safe_call(api_name, **kwargs)
        if not df.empty:
            os.makedirs(self._cache_dir, exist_ok=True)
            df.to_json(cache_file, orient="records", force_ascii=False)
        return df

    def _convert_code_to_akshare(self, ts_code: str) -> str:
        """Convert tushare-style code to akshare format.

        Akshare uses formats like: 600887.SH, 000858.SZ -> 600887, 000858
        """
        if "." in ts_code:
            return ts_code.split(".")[0]
        return ts_code

    def _convert_code_to_akshare_full(self, ts_code: str) -> str:
        """Convert to akshare full format.

        600887 -> 600887.SH
        000858 -> 000858.SZ
        """
        if "." in ts_code:
            return ts_code
        if ts_code.startswith(("0", "3")):
            return f"{ts_code}.SZ"
        return f"{ts_code}.SH"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect financial data from Akshare API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --code 600887
  %(prog)s --code 600887 --output output/data_pack_market.md
  %(prog)s --code 00700.HK --extra-fields balancesheet.defer_tax_assets
        """,
    )
    parser.add_argument(
        "--code",
        required=True,
        help="Stock code (e.g., 600887, 000858, 00700, or plain digits)",
    )
    parser.add_argument(
        "--output",
        default="output/data_pack_market.md",
        help="Output file path (default: output/data_pack_market.md)",
    )
    parser.add_argument(
        "--extra-fields",
        nargs="*",
        help="Additional fields to fetch (format: endpoint.field_name)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print parsed arguments and exit without calling API",
    )
    parser.add_argument(
        "--refresh-market",
        action="store_true",
        help="Only refresh market-sensitive sections (§1/§2/§11/§14) in existing data pack",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Validate and normalize stock code
    try:
        ts_code = validate_stock_code(args.code)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("=== Dry Run ===")
        print(f"  Stock code: {args.code} -> {ts_code}")
        print(f"  Data source: Akshare")
        print(f"  Output: {args.output}")
        print(f"  Extra fields: {args.extra_fields or 'none'}")
        return

    client = AkshareClient()

    if args.refresh_market:
        from pathlib import Path
        output_path = Path(args.output)
        if not output_path.exists():
            print(f"⚠️ {output_path} does not exist, falling back to full collection")
            print(f"Collecting data for {ts_code}...")
            data_pack = client.assemble_data_pack(ts_code)
        else:
            existing = output_path.read_text(encoding="utf-8")
            age_days = client._check_staleness(existing)
            if age_days > 7:
                print(f"⚠️ Data pack is {age_days} days old, falling back to full collection")
                print(f"Collecting data for {ts_code}...")
                data_pack = client.assemble_data_pack(ts_code)
            else:
                print(f"Refreshing market data for {ts_code} (data pack is {age_days} day(s) old)...")
                data_pack = client.refresh_market_sections(ts_code, existing)
    else:
        print(f"Collecting data for {ts_code}...")
        data_pack = client.assemble_data_pack(ts_code)

    # Handle extra fields
    if args.extra_fields:
        extra_lines = ["\n", format_header(2, "附加字段"), ""]
        for field_spec in args.extra_fields:
            parts = field_spec.split(".", 1)
            if len(parts) != 2:
                extra_lines.append(f"- 无效字段格式: {field_spec} (应为 endpoint.field_name)")
                continue
            endpoint, field_name = parts
            try:
                symbol = client._convert_code_to_akshare(ts_code)
                df = client._safe_call(endpoint, symbol=symbol)
                if not df.empty and field_name in df.columns:
                    extra_lines.append(f"**{endpoint}.{field_name}**:")
                    extra_lines.append(df[[field_name]].to_markdown(index=False))
                    extra_lines.append("")
                else:
                    extra_lines.append(f"- {endpoint}.{field_name}: 无数据")
            except Exception as e:
                extra_lines.append(f"- {endpoint}.{field_name}: 获取失败 ({e})")
        data_pack += "\n".join(extra_lines)

    # Write output
    import os
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(data_pack)
    print(f"Output written to {args.output}")
    print(f"File size: {os.path.getsize(args.output):,} bytes")


if __name__ == "__main__":
    main()
