"""Financial Report Minesweeper - DerivedMetricsMixin.

Section 17 derived metrics: financial trends, Factor 2/3/4 computations.
"""

import pandas as pd

from format_utils import format_number, format_table, format_header


class DerivedMetricsMixin:
    """Mixin providing derived metrics computation for AkshareClient."""

    def _compute_financial_trends(self) -> str | None:
        """Compute §17.1: Financial trend summary (CAGR, debt ratios, net cash, payout)."""
        income_df = self._get_annual_df("income")
        bs_df = self._get_annual_df("balance_sheet")

        if income_df.empty or len(income_df) < 2:
            return None

        years_labels = [str(r["报告日"])[:4] for _, r in income_df.iterrows()]
        n_years = len(years_labels)

        lines = [format_header(3, "17.1 财务趋势速览"), ""]

        # Revenue & Net Profit series
        rev_series = [(y, self._safe_float(r.get("营业收入")))
                     for y, (_, r) in zip(years_labels, income_df.iterrows())]
        np_series = [(y, self._safe_float(r.get("归属于母公司所有者的净利润")))
                     for y, (_, r) in zip(years_labels, income_df.iterrows())]

        # CAGR calculation
        def _cagr(series: list[tuple[str, float | None]]) -> str:
            vals = [v for _, v in series if v is not None and v > 0]
            if len(vals) < 2:
                return "—"
            latest, oldest = vals[0], vals[-1]
            n = len(vals) - 1
            if oldest <= 0:
                return "—"
            cagr = (latest / oldest) ** (1 / n) - 1
            return f"{cagr * 100:.2f}%"

        rev_cagr = _cagr(rev_series)
        np_cagr = _cagr(np_series)

        # Interest-bearing debt per year
        def _interest_bearing_debt(row) -> float | None:
            components = ["短期借款", "长期借款", "应付债券", "一年内到期的非流动负债"]
            total = 0.0
            any_valid = False
            for c in components:
                v = self._safe_float(row.get(c))
                if v is not None:
                    total += v
                    any_valid = True
            return total if any_valid else None

        debt_series = []
        debt_ratio_series = []
        net_cash_series = []
        if not bs_df.empty:
            for _, r in bs_df.iterrows():
                year = str(r["报告日"])[:4]
                debt = _interest_bearing_debt(r)
                ta = self._safe_float(r.get("资产总计"))
                cash = self._safe_float(row.get("货币资金")) if (r := bs_df.iloc[0] if False else r) else None
                if cash is None:
                    cash = self._safe_float(r.get("货币资金"))
                debt_series.append((year, debt))
                if debt is not None and ta and ta > 0:
                    debt_ratio_series.append((year, debt / ta * 100))
                else:
                    debt_ratio_series.append((year, None))
                if cash is not None and debt is not None:
                    net_cash_series.append((year, cash - debt))
                else:
                    net_cash_series.append((year, None))

        # Payout ratio per year
        payout_lookup = self._get_payout_by_year()
        np_series_only = [(y, v) for y, v in np_series]
        payout_series = [(y, payout_lookup.get(y)) for y, _ in np_series_only]

        # Build table
        def _fmt_val(val: float | None, divider: float = 1e6, is_pct: bool = False) -> str:
            if val is None:
                return "—"
            if is_pct:
                return f"{val:.2f}"
            return format_number(val, divider=divider)

        def _lookup(series: list[tuple[str, float | None]], year: str) -> float | None:
            for y, v in series:
                if y == year:
                    return v
            return None

        headers = ["指标"] + years_labels + ["5年CAGR"]
        rows = []

        row = [f"营业收入（{self._unit_label()}）"]
        for y, v in rev_series:
            row.append(_fmt_val(v))
        row.append(rev_cagr)
        rows.append(row)

        row = [f"归母净利润（{self._unit_label()}）"]
        for y, v in np_series:
            row.append(_fmt_val(v))
        row.append(np_cagr)
        rows.append(row)

        row = [f"有息负债（{self._unit_label()}）"]
        for y in years_labels:
            row.append(_fmt_val(_lookup(debt_series, y)))
        row.append("—")
        rows.append(row)

        row = ["有息负债/总资产（%）"]
        for y in years_labels:
            row.append(_fmt_val(_lookup(debt_ratio_series, y), is_pct=True))
        row.append("—")
        rows.append(row)

        row = [f"广义净现金（{self._unit_label()}）"]
        for y in years_labels:
            row.append(_fmt_val(_lookup(net_cash_series, y)))
        row.append("—")
        rows.append(row)

        row = ["股息支付率（%）"]
        for y in years_labels:
            row.append(_fmt_val(_lookup(payout_series, y), is_pct=True))
        row.append("—")
        rows.append(row)

        table = format_table(headers, rows, alignments=["l"] + ["r"] * (n_years + 1))
        lines.append(table)
        return "\n".join(lines)
