"""Financial Report Minesweeper - InfrastructureMixin.

Utility methods: market detection, display formatting, store helpers.
"""

import pandas as pd

from format_utils import format_number


class InfrastructureMixin:
    """Mixin providing infrastructure utilities for AkshareClient."""

    @staticmethod
    def _detect_currency(ts_code: str) -> str:
        """Detect reporting currency based on stock code suffix."""
        upper = ts_code.upper()
        if upper.endswith(".HK"):
            return "HKD"
        elif upper.endswith(".US"):
            return "USD"
        return "CNY"

    @staticmethod
    def _is_hk(ts_code: str) -> bool:
        """Check if stock code is a Hong Kong listing."""
        return ts_code.upper().endswith(".HK")

    @staticmethod
    def _is_us(ts_code: str) -> bool:
        """Check if stock code is a US listing."""
        return ts_code.upper().endswith(".US")

    def _unit_label(self) -> str:
        """Return currency-appropriate unit label for display."""
        return {"HKD": "百万港元", "USD": "百万美元"}.get(self._currency, "百万元")

    def _price_unit(self) -> str:
        """Return currency-appropriate price unit for display."""
        return {"HKD": "港元", "USD": "美元"}.get(self._currency, "元")

    def _detect_fy_end_month(self, df: pd.DataFrame) -> int:
        """Infer fiscal-year end month from end_date column.

        Groups by month, finds the month appearing in most distinct years.
        For calendar-year companies -> 12. For AAPL (Sep FY) -> 9.
        """
        if df.empty or "end_date" not in df.columns:
            return 12
        months = df["end_date"].astype(str).str[4:6].astype(int)
        years = df["end_date"].astype(str).str[:4]
        temp = pd.DataFrame({"month": months, "year": years})
        counts = temp.groupby("month")["year"].nunique()
        if counts.empty:
            return 12
        return int(counts.idxmax())

    @staticmethod
    def _us_api_code(ts_code: str) -> str:
        """Strip .US suffix for US API calls (uses plain tickers)."""
        return ts_code.rsplit(".", 1)[0]

    def _prepare_display_periods(self, df, max_annual=5):
        """Select up to max_annual annual reports + any newer interim reports.

        Returns (display_df, column_labels) where column_labels are like:
        ["2025Q3", "2025H1", "2025Q1", "2024", "2023", "2022", "2021", "2020"]
        """
        if df.empty:
            return df, []

        df = df.drop_duplicates(subset=["end_date"])

        fy_month_str = f"{self._fy_end_month:02d}"

        # Split into annual (FY end month) and non-annual
        annual = df[df["end_date"].str[4:6] == fy_month_str].copy()
        non_annual = df[df["end_date"].str[4:6] != fy_month_str].copy()

        # Sort annual descending, take top max_annual
        annual = annual.sort_values("end_date", ascending=False).head(max_annual)

        latest_annual_date = annual["end_date"].max() if not annual.empty else "00000000"

        # Keep only non-annual entries strictly newer than latest annual
        interim = non_annual[non_annual["end_date"] > latest_annual_date].copy()
        interim = interim.sort_values("end_date", ascending=False)

        # Build labels
        fy_month = self._fy_end_month

        def _label(end_date):
            mm = end_date[4:6]
            mmdd = end_date[4:]
            year = end_date[:4]
            if mm == fy_month_str:
                return year
            elif mmdd == "0630":
                return f"{year}H1"
            elif mmdd == "0331":
                return f"{year}Q1"
            elif mmdd == "0930":
                return f"{year}Q3"
            else:
                return f"{year}_{mmdd}"

        # Combine: interim (desc) + annual (desc)
        display_df = pd.concat([interim, annual], ignore_index=True)
        if display_df.empty:
            return display_df, []

        labels = [_label(d) for d in display_df["end_date"]]
        return display_df, labels

    # --- Feature #90-92: Derived metrics (Section 17) ---

    @staticmethod
    def _safe_float(val) -> float | None:
        """Convert a value to float, returning None for NaN/None."""
        if val is None:
            return None
        try:
            f = float(val)
            return None if f != f else f  # NaN check
        except (TypeError, ValueError):
            return None

    def _get_annual_df(self, store_key: str) -> pd.DataFrame:
        """Get stored DataFrame filtered to annual periods only."""
        df = self._store.get(store_key)
        if df is None or df.empty:
            return pd.DataFrame()
        fy_month_str = f"{self._fy_end_month:02d}"
        annual = df[df["end_date"].str[4:6] == fy_month_str].copy()
        return annual.sort_values("end_date", ascending=False)

    def _get_annual_series(self, store_key: str, col: str) -> list[tuple[str, float | None]]:
        """Extract (year_label, value) pairs for annual periods, sorted desc."""
        df = self._get_annual_df(store_key)
        if df.empty or col not in df.columns:
            return []
        result = []
        for _, r in df.iterrows():
            year = str(r["end_date"])[:4]
            result.append((year, self._safe_float(r.get(col))))
        return result

    def _get_payout_by_year(self) -> dict[str, float]:
        """Get payout ratio (%) by year from stored dividend data.

        A-share path: computes from dividend / net_income × 100.
        """
        div_df = self._store.get("dividends")
        income_df = self._get_annual_df("income")
        if div_df is None or div_df.empty or income_df.empty:
            return {}

        # Build dividend total lookup by year (sum multiple payments per year)
        div_lookup: dict[str, float] = {}
        for _, r in div_df.iterrows():
            year = str(r.get("end_date", ""))[:4]
            cash_div = self._safe_float(r.get("cash_div")) or 0
            total_div = self._safe_float(r.get("total_div")) or 0
            div_lookup[year] = div_lookup.get(year, 0) + (cash_div or total_div)

        # Build net income lookup by year
        np_lookup = {}
        for _, r in income_df.iterrows():
            year = str(r["end_date"])[:4]
            np_lookup[year] = self._safe_float(r.get("n_income_attr_p"))

        result = {}
        for year, div_total in div_lookup.items():
            np_val = np_lookup.get(year)
            if div_total and np_val and np_val > 0:
                result[year] = div_total / np_val * 100
        return result
