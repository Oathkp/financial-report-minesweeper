#!/usr/bin/env python3
"""财报排雷数据获取脚本 (Minesweeper Data Collector)

使用本项目内置的 AkshareClient，获取排雷分析所需的全部结构化数据。
输出 JSON 到 stdout，供 Claude Code Skill 调用。

Usage:
    python3 scripts/minesweeper_data.py --stock-code 600519 [--years 10]
    python3 scripts/minesweeper_data.py --stock-code 000858 --years 5
"""

import argparse
import json
import os
import sys
import time

# Ensure scripts/ directory is on the path for sibling module imports
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import pandas as pd
from config import validate_stock_code
from akshare_collector import AkshareClient


def _safe_val(v):
    """Convert pandas/numpy values to JSON-serializable Python types."""
    if v is None:
        return None
    if isinstance(v, float) and (pd.isna(v) or v != v):
        return None
    if hasattr(v, "item"):  # numpy scalar
        return v.item()
    if hasattr(v, "isoformat"):  # date/datetime objects
        return v.isoformat()
    return v


def _df_to_records(df: pd.DataFrame, cols: list[str] | None = None) -> list[dict]:
    """Convert DataFrame to list of dicts with safe values."""
    if df.empty:
        return []
    if cols:
        available = [c for c in cols if c in df.columns]
        df = df[available]
    records = []
    for _, row in df.iterrows():
        records.append({k: _safe_val(v) for k, v in row.items()})
    return records


def get_stock_info(client: AkshareClient, ts_code: str) -> dict:
    """Get basic stock info including industry classification."""
    try:
        # Use stock_individual_info_em which returns: 最新, 股票代码, 股票简称, 总股本, 流通股, 总市值, 流通市值, 行业, 上市时间
        symbol = client._convert_code_to_akshare(ts_code)
        df = client._safe_call("stock_individual_info_em", symbol=symbol)
        if df.empty:
            return {"ts_code": ts_code, "name": "", "industry": "", "market": ""}
        # Build lookup from the info table
        info_dict = {}
        for _, row in df.iterrows():
            if len(row) >= 2:
                key = _safe_val(row.iloc[0])
                val = _safe_val(row.iloc[1])
                if key:
                    info_dict[key] = val
        return {
            "ts_code": ts_code,
            "name": info_dict.get("股票简称", ""),
            "industry": info_dict.get("行业", ""),
            "area": "",
            "market": "",
            "list_date": info_dict.get("上市时间", ""),
            "fullname": "",
        }
    except Exception as e:
        print(f"Warning: stock_individual_info_em failed: {e}", file=sys.stderr)
        return {"ts_code": ts_code, "name": "", "industry": "", "market": ""}


def get_audit_data(client: AkshareClient, ts_code: str) -> list[dict]:
    """Get audit opinion history - akshare doesn't provide this directly."""
    # Akshare doesn't have a direct audit opinion API; return empty
    return []


def get_income_data(client: AkshareClient, ts_code: str) -> list[dict]:
    """Get income statement data (annual reports only) using stock_financial_report_sina."""
    try:
        symbol = client._convert_code_to_akshare(ts_code)
        df = client._safe_call("stock_financial_report_sina", stock=symbol, symbol="利润表")
        if df.empty:
            return []
        # Filter to annual reports (合并期末)
        if "类型" in df.columns:
            df = df[df["类型"] == "合并期末"].copy()
        # Keep only year-end reports (report dates ending in 1231)
        if "报告日" in df.columns:
            df = df[df["报告日"].astype(str).str.endswith("1231")]
        df = df.sort_values("报告日", ascending=False)
        return _df_to_records(df)
    except Exception as e:
        print(f"Warning: income statement failed: {e}", file=sys.stderr)
        return []


def get_balance_data(client: AkshareClient, ts_code: str) -> list[dict]:
    """Get balance sheet data (annual reports only) using stock_financial_report_sina."""
    try:
        symbol = client._convert_code_to_akshare(ts_code)
        df = client._safe_call("stock_financial_report_sina", stock=symbol, symbol="资产负债表")
        if df.empty:
            return []
        # Filter to annual reports (合并期末)
        if "类型" in df.columns:
            df = df[df["类型"] == "合并期末"].copy()
        # Keep only year-end reports
        if "报告日" in df.columns:
            df = df[df["报告日"].astype(str).str.endswith("1231")]
        df = df.sort_values("报告日", ascending=False)
        return _df_to_records(df)
    except Exception as e:
        print(f"Warning: balance sheet failed: {e}", file=sys.stderr)
        return []


def get_cashflow_data(client: AkshareClient, ts_code: str) -> list[dict]:
    """Get cash flow statement data (annual reports only) using stock_financial_report_sina."""
    try:
        symbol = client._convert_code_to_akshare(ts_code)
        df = client._safe_call("stock_financial_report_sina", stock=symbol, symbol="现金流量表")
        if df.empty:
            return []
        # Filter to annual reports (合并期末)
        if "类型" in df.columns:
            df = df[df["类型"] == "合并期末"].copy()
        # Keep only year-end reports
        if "报告日" in df.columns:
            df = df[df["报告日"].astype(str).str.endswith("1231")]
        df = df.sort_values("报告日", ascending=False)
        return _df_to_records(df)
    except Exception as e:
        print(f"Warning: cash flow statement failed: {e}", file=sys.stderr)
        return []


def get_indicator_data(client: AkshareClient, ts_code: str) -> list[dict]:
    """Get financial indicators - akshare uses stock_financial_report_sina for this."""
    # Akshare doesn't have a separate fina_indicator API equivalent;
    # financial indicators can be derived from the income/balance data
    return []


def get_holder_data(client: AkshareClient, ts_code: str) -> list[dict]:
    """Get top 10 shareholders using stock_main_stock_holder."""
    try:
        symbol = client._convert_code_to_akshare(ts_code)
        df = client._safe_call("stock_main_stock_holder", stock=symbol)
        if df.empty:
            return []
        cols = ["股东名称", "持股数量", "持股比例", "截至日期"]
        available = [c for c in cols if c in df.columns]
        df = df[available].sort_values("持股比例", ascending=False)
        return _df_to_records(df)
    except Exception as e:
        print(f"Warning: stock_main_stock_holder failed: {e}", file=sys.stderr)
        return []


def get_peer_data(client: AkshareClient, ts_code: str,
                  industry: str) -> dict:
    """Get peer company financial indicators for comparison.

    Finds companies in the same industry and pulls their latest
    gross margin, expense ratios, etc.
    """
    if not industry:
        return {"industry": "", "peers": []}

    try:
        # Get all stocks to find industry peers
        all_stocks = client._safe_call("stock_info_a_code_name")
        if all_stocks.empty:
            return {"industry": industry, "peers": []}

        # Filter by industry if column exists
        if "industry" in all_stocks.columns:
            peers = all_stocks[all_stocks["industry"] == industry]
        elif "所属行业" in all_stocks.columns:
            peers = all_stocks[all_stocks["所属行业"] == industry]
        else:
            return {"industry": industry, "peers": []}

        # Exclude self and limit to 20 peers
        peers = peers[peers["ts_code"] != ts_code].head(20)

        if peers.empty:
            return {"industry": industry, "peers": []}

        peer_data = []
        for _, peer_row in peers.iterrows():
            peer_code = peer_row["ts_code"]
            try:
                # Get financial data for peer
                ind_df = client._safe_call(
                    "stock_financial_report_sina", stock=peer_code, symbol="利润表"
                )
                if ind_df.empty:
                    continue
                # Get latest year-end data
                if "报告日" in ind_df.columns:
                    ind_df = ind_df[ind_df["报告日"].astype(str).str.endswith("1231")]
                if ind_df.empty:
                    continue
                ind_df = ind_df.sort_values("报告日", ascending=False)
                latest = ind_df.iloc[0]
                peer_data.append({
                    "ts_code": _safe_val(peer_code),
                    "name": _safe_val(peer_row.get("name", "")),
                    "end_date": _safe_val(latest.get("报告日", "")),
                    "grossprofit_margin": _safe_val(latest.get("毛利率")),
                    "netprofit_margin": _safe_val(latest.get("净利率")),
                    "debt_to_assets": None,
                    "roe": _safe_val(latest.get("净资产收益率")),
                    "assets_turn": None,
                    "inv_turn": None,
                    "ar_turn": None,
                })
            except Exception:
                continue  # Skip peers that fail

        return {"industry": industry, "peers": peer_data}

    except Exception as e:
        print(f"Warning: peer data failed: {e}", file=sys.stderr)
        return {"industry": industry, "peers": []}


def collect_minesweeper_data(stock_code: str, years: int = 10) -> dict:
    """Collect all data needed for minesweeper analysis.

    Args:
        stock_code: Stock code (e.g., '600519', '000858.SZ')
        years: Number of years of historical data to fetch

    Returns:
        Dict with all structured data for rule evaluation
    """
    # Normalize stock code
    ts_code = validate_stock_code(stock_code)

    # Initialize client
    client = AkshareClient()

    print(f"Collecting data for {ts_code}...", file=sys.stderr)

    # Collect all data sections
    stock_info = get_stock_info(client, ts_code)
    print(f"  [1/7] Basic info: {stock_info.get('name', '?')}", file=sys.stderr)

    audit = get_audit_data(client, ts_code)
    print(f"  [2/7] Audit data: {len(audit)} records", file=sys.stderr)

    income = get_income_data(client, ts_code)
    print(f"  [3/7] Income statement: {len(income)} years", file=sys.stderr)

    balance = get_balance_data(client, ts_code)
    print(f"  [4/7] Balance sheet: {len(balance)} years", file=sys.stderr)

    cashflow = get_cashflow_data(client, ts_code)
    print(f"  [5/7] Cash flow: {len(cashflow)} years", file=sys.stderr)

    indicators = get_indicator_data(client, ts_code)
    print(f"  [6/7] Financial indicators: {len(indicators)} years", file=sys.stderr)

    holders = get_holder_data(client, ts_code)
    print(f"  [7/7] Shareholders: {len(holders)} records", file=sys.stderr)

    # Trim to requested years
    if income and len(income) > years:
        income = income[:years]
    if balance and len(balance) > years:
        balance = balance[:years]
    if cashflow and len(cashflow) > years:
        cashflow = cashflow[:years]
    if indicators and len(indicators) > years:
        indicators = indicators[:years]

    # Peer comparison (can be slow, do it last)
    industry = stock_info.get("industry", "")
    print(f"  [bonus] Fetching peer data for industry: {industry}...",
          file=sys.stderr)
    peers = get_peer_data(client, ts_code, industry)
    print(f"  [bonus] Peer data: {len(peers.get('peers', []))} peers",
          file=sys.stderr)

    return {
        "stock_info": stock_info,
        "audit": audit,
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
        "indicators": indicators,
        "holders": holders,
        "peers": peers,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Collect financial data for minesweeper analysis"
    )
    parser.add_argument(
        "--stock-code", required=True,
        help="Stock code (e.g., 600519, 000858.SZ)"
    )
    parser.add_argument(
        "--years", type=int, default=10,
        help="Number of years of historical data (default: 10)"
    )
    args = parser.parse_args()

    try:
        data = collect_minesweeper_data(args.stock_code, args.years)
        # Output JSON to stdout
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        error_result = {"error": str(e)}
        print(json.dumps(error_result, ensure_ascii=False), file=sys.stdout)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()