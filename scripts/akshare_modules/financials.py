"""Financial Report Minesweeper - FinancialsMixin.

Financial statement get_* methods using akshare API.
"""

import sys

import pandas as pd

from format_utils import format_number, format_table, format_header

try:
    import yfinance as yf
    _yf_available = True
except ImportError:
    _yf_available = False


def _yf():
    """Access yfinance module via akshare_collector for @patch compatibility."""
    return sys.modules["akshare_collector"].yf


class FinancialsMixin:
    """Mixin providing financial statement methods for AkshareClient."""

    # --- Field name mapping from akshare (Chinese) to project internal names ---

    # Income statement field map: internal_name -> akshare_col_name
    _INCOME_FIELD_MAP = {
        "revenue": "营业收入",
        "oper_cost": "营业成本",
        "biz_tax_surch": "营业税金及附加",
        "sell_exp": "销售费用",
        "admin_exp": "管理费用",
        "rd_exp": "研发费用",
        "finance_exp": "财务费用",
        "assets_impair_loss": "资产减值损失",
        "credit_impair_loss": "信用减值损失",
        "fv_value_chg_gain": "公允价值变动收益",
        "invest_income": "投资收益",
        "asset_disp_income": "资产处置收益",
        "operate_profit": "营业利润",
        "non_oper_income": "营业外收入",
        "non_oper_exp": "营业外支出",
        "total_profit": "利润总额",
        "income_tax": "所得税费用",
        "n_income": "净利润",
        "n_income_attr_p": "归属于母公司所有者的净利润",
        "minority_gain": "少数股东损益",
        "basic_eps": "基本每股收益",
        "diluted_eps": "稀释每股收益",
    }

    # Balance sheet field map
    _BALANCE_FIELD_MAP = {
        "money_cap": "货币资金",
        "trad_asset": "交易性金融资产",
        "notes_receiv": "应收票据",
        "accounts_receiv": "应收账款",
        "oth_receiv": "其他应收款",
        "inventories": "存货",
        "total_cur_assets": "流动资产合计",
        "lt_eqt_invest": "长期股权投资",
        "fix_assets": "固定资产净值",
        "cip": "在建工程合计",
        "intang_assets": "无形资产",
        "goodwill": "商誉",
        "total_assets": "资产总计",
        "st_borr": "短期借款",
        "notes_payable": "应付票据",
        "acct_payable": "应付账款",
        "contract_liab": "合同负债",
        "adv_receipts": "预收款项",
        "non_cur_liab_due_1y": "一年内到期的非流动负债",
        "total_cur_liab": "流动负债合计",
        "lt_borr": "长期借款",
        "bond_payable": "应付债券",
        "total_liab": "负债合计",
        "defer_tax_assets": "递延所得税资产",
        "defer_tax_liab": "递延所得税负债",
        "total_hldr_eqy_exc_min_int": "归属于母公司股东权益合计",
        "minority_int": "少数股东权益",
    }

    # Cash flow field map
    _CASHFLOW_FIELD_MAP = {
        "n_cashflow_act": "经营活动产生的现金流量净额",
        "n_cashflow_inv_act": "投资活动产生的现金流量净额",
        "n_cash_flows_fnc_act": "筹资活动产生的现金流量净额",
        "c_pay_acq_const_fiolta": "购建固定资产、无形资产和其他长期资产所支付的现金",
        "depr_fa_coga_dpba": "固定资产折旧",
        "amort_intang_assets": "无形资产摊销",
        "lt_amort_deferred_exp": "长期待摊费用摊销",
        "c_pay_to_staff": "支付给职工以及为职工支付的现金",
        "c_paid_for_taxes": "支付的各项税费",
        "c_pay_dist_dpcp_int_exp": "分配股利、利润或偿付利息所支付的现金",
        "n_recp_disp_fiolta": "处置固定资产、无形资产和其他长期资产所收回的现金净额",
        "c_recp_return_invest": "取得投资收益收到的现金",
        "n_cash_end_bal": "期末现金及现金等价物余额",
    }

    # --- Section 1: Basic company info ---

    def get_basic_info(self, ts_code: str) -> str:
        """Section 1: Basic company info from stock_individual_info_em."""
        symbol = self._convert_code_to_akshare(ts_code)

        df = self._safe_call("stock_individual_info_em", symbol=symbol)
        lines = [format_header(2, "1. 基本信息"), ""]

        if df.empty:
            lines.append("数据缺失\n")
            return "\n".join(lines)

        # Parse the item/value format into a dict
        info_dict = {}
        for _, row in df.iterrows():
            info_dict[row["item"]] = row["value"]

        # Get market data
        try:
            daily_df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date="", end_date="", adjust="qfq")
            if not daily_df.empty:
                self._store["basic_info"] = daily_df.tail(1).copy()
        except Exception:
            pass

        # Build info table
        info_table = format_table(
            ["项目", "内容"],
            [
                ["股票代码", info_dict.get("股票代码", symbol)],
                ["股票简称", info_dict.get("股票简称", "")],
                ["总股本", info_dict.get("总股本", "")],
                ["流通股", info_dict.get("流通股", "")],
                ["总市值", info_dict.get("总市值", "")],
                ["流通市值", info_dict.get("流通市值", "")],
                ["行业", info_dict.get("行业", "")],
                ["上市时间", info_dict.get("上市时间", "")],
            ],
            alignments=["l", "r"],
        )
        lines.append(info_table)
        return "\n".join(lines)

    # --- Section 2: Market data ---

    def get_market_data(self, ts_code: str) -> str:
        """Section 2: Current price and 52-week range."""
        symbol = self._convert_code_to_akshare(ts_code)
        lines = [format_header(2, "2. 市场行情"), ""]

        try:
            # Get daily history for 1 year
            end_date = pd.Timestamp.now().strftime("%Y%m%d")
            start_date = (pd.Timestamp.now() - pd.DateOffset(years=1)).strftime("%Y%m%d")

            df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                     start_date=start_date, end_date=end_date, adjust="qfq")

            if df.empty:
                lines.append("数据缺失\n")
                return "\n".join(lines)

            df = df.sort_values("日期", ascending=False)

            latest_close = df.iloc[0]["收盘"]
            high_52w = df["最高"].max()
            low_52w = df["最低"].min()
            high_date = df.loc[df["最高"].idxmax(), "日期"]
            low_date = df.loc[df["最低"].idxmin(), "日期"]
            avg_vol = df["成交量"].mean()

            table = format_table(
                ["指标", "数值"],
                [
                    ["最新收盘价", f"{latest_close:.2f}"],
                    ["52周最高", f"{high_52w:.2f} ({high_date})"],
                    ["52周最低", f"{low_52w:.2f} ({low_date})"],
                    ["52周涨跌幅", f"{(latest_close / low_52w - 1) * 100:.1f}% (自低点)"],
                    ["日均成交量 (手)", f"{avg_vol:,.0f}"],
                ],
                alignments=["l", "r"],
            )
            lines.append(table)
        except Exception as e:
            lines.append(f"数据获取失败: {e}\n")

        return "\n".join(lines)

    # --- Section 3: Income statement ---

    def get_income(self, ts_code: str, report_type: str = "1") -> str:
        """Section 3: Five-year consolidated income statement."""
        symbol = self._convert_code_to_akshare(ts_code)

        df = self._safe_call("stock_financial_report_sina", stock=symbol, symbol="利润表")
        lines = [format_header(2, "3. 合并利润表"), ""]

        if df.empty:
            lines.append("数据缺失\n")
            return "\n".join(lines)

        # Filter to annual reports (合并期末)
        df = df[df["类型"] == "合并期末"].copy()
        df = df.drop_duplicates(subset=["报告日"])
        df = df.sort_values("报告日", ascending=False)

        # Detect fiscal year end month
        if self._fy_end_month == 12:
            self._fy_end_month = self._detect_fy_end_month(df)

        df, years = self._prepare_display_periods(df)

        # Store for derived metrics
        store_key = "income_parent" if report_type == "6" else "income"
        self._store[store_key] = df
        self._store[store_key + "_years"] = years

        if not years:
            lines.append("无年报数据\n")
            return "\n".join(lines)

        # Build display rows
        fields = [
            ("营业收入", "revenue"),
            ("营业成本", "oper_cost"),
            ("税金及附加", "biz_tax_surch"),
            ("销售费用", "sell_exp"),
            ("管理费用", "admin_exp"),
            ("研发费用", "rd_exp"),
            ("财务费用", "finance_exp"),
            ("资产减值损失", "assets_impair_loss"),
            ("信用减值损失", "credit_impair_loss"),
            ("公允价值变动收益", "fv_value_chg_gain"),
            ("投资收益", "invest_income"),
            ("资产处置收益", "asset_disp_income"),
            ("营业利润", "operate_profit"),
            ("营业外收入", "non_oper_income"),
            ("营业外支出", "non_oper_exp"),
            ("利润总额", "total_profit"),
            ("所得税费用", "income_tax"),
            ("净利润", "n_income"),
            ("归母净利润", "n_income_attr_p"),
            ("少数股东损益", "minority_gain"),
            ("基本EPS", "basic_eps"),
            ("稀释EPS", "diluted_eps"),
        ]

        headers = ["项目 (百万元)"] + years
        rows = []
        for label, internal_name in fields:
            ak_name = self._INCOME_FIELD_MAP.get(internal_name)
            row = [label]
            for _, r in df.iterrows():
                val = r.get(ak_name) if ak_name else None
                if internal_name in ("basic_eps", "diluted_eps"):
                    row.append(f"{val:.2f}" if val is not None and val == val else "—")
                else:
                    row.append(format_number(val))
            rows.append(row)

        table = format_table(headers, rows, alignments=["l"] + ["r"] * len(years))
        lines.append(table)
        lines.append("")
        lines.append("*单位: 百万元 (原始数据 / 1,000,000), EPS为元/股*")
        return "\n".join(lines)

    def get_income_parent(self, ts_code: str) -> str:
        """Section 3P: Parent company income statement (not available from akshare)."""
        return format_header(2, "3P. 母公司利润表") + "\n\n数据缺失 (akshare 不提供母公司报表)\n"

    # --- Section 4: Balance sheet ---

    def get_balance_sheet(self, ts_code: str, report_type: str = "1") -> str:
        """Section 4: Five-year consolidated balance sheet."""
        symbol = self._convert_code_to_akshare(ts_code)

        df = self._safe_call("stock_financial_report_sina", stock=symbol, symbol="资产负债表")
        lines = [format_header(2, "4. 合并资产负债表"), ""]

        if df.empty:
            lines.append("数据缺失\n")
            return "\n".join(lines)

        # Filter to annual reports
        df = df[df["类型"] == "合并期末"].copy()
        df = df.drop_duplicates(subset=["报告日"])
        df = df.sort_values("报告日", ascending=False)

        df, years = self._prepare_display_periods(df)

        # Store for derived metrics
        store_key = "balance_sheet_parent" if report_type == "6" else "balance_sheet"
        self._store[store_key] = df
        self._store[store_key + "_years"] = years

        if not years:
            lines.append("无年报数据\n")
            return "\n".join(lines)

        fields = [
            ("货币资金", "money_cap"),
            ("交易性金融资产", "trad_asset"),
            ("应收票据", "notes_receiv"),
            ("应收账款", "accounts_receiv"),
            ("其他应收款", "oth_receiv"),
            ("存货", "inventories"),
            ("流动资产合计", "total_cur_assets"),
            ("长期股权投资", "lt_eqt_invest"),
            ("固定资产净值", "fix_assets"),
            ("在建工程合计", "cip"),
            ("无形资产", "intang_assets"),
            ("商誉", "goodwill"),
            ("总资产", "total_assets"),
            ("短期借款", "st_borr"),
            ("应付票据", "notes_payable"),
            ("应付账款", "acct_payable"),
            ("合同负债", "contract_liab"),
            ("预收款项", "adv_receipts"),
            ("一年内到期非流动负债", "non_cur_liab_due_1y"),
            ("流动负债合计", "total_cur_liab"),
            ("长期借款", "lt_borr"),
            ("应付债券", "bond_payable"),
            ("总负债", "total_liab"),
            ("递延所得税资产", "defer_tax_assets"),
            ("递延所得税负债", "defer_tax_liab"),
            ("归母所有者权益", "total_hldr_eqy_exc_min_int"),
            ("少数股东权益", "minority_int"),
        ]

        headers = ["项目 (百万元)"] + years
        rows = []
        for label, internal_name in fields:
            ak_name = self._BALANCE_FIELD_MAP.get(internal_name)
            row = [label]
            for _, r in df.iterrows():
                val = r.get(ak_name) if ak_name else None
                row.append(format_number(val))
            rows.append(row)

        table = format_table(headers, rows, alignments=["l"] + ["r"] * len(years))
        lines.append(table)
        lines.append("")
        lines.append("*单位: 百万元*")
        return "\n".join(lines)

    def get_balance_sheet_parent(self, ts_code: str) -> str:
        """Section 4P: Parent company balance sheet (not available from akshare)."""
        return format_header(2, "4P. 母公司资产负债表") + "\n\n数据缺失 (akshare 不提供母公司报表)\n"

    # --- Section 5: Cash flow statement ---

    def get_cashflow(self, ts_code: str) -> str:
        """Section 5: Five-year cash flow statement with FCF calculation."""
        symbol = self._convert_code_to_akshare(ts_code)

        df = self._safe_call("stock_financial_report_sina", stock=symbol, symbol="现金流量表")
        lines = [format_header(2, "5. 现金流量表"), ""]

        if df.empty:
            lines.append("数据缺失\n")
            return "\n".join(lines)

        # Filter to annual reports
        df = df[df["类型"] == "合并期末"].copy()
        df = df.drop_duplicates(subset=["报告日"])
        df = df.sort_values("报告日", ascending=False)

        df, years = self._prepare_display_periods(df)

        # Store for derived metrics
        self._store["cashflow"] = df
        self._store["cashflow_years"] = years

        if not years:
            lines.append("无年报数据\n")
            return "\n".join(lines)

        headers = ["项目 (百万元)"] + years
        rows = []

        simple_fields = [
            ("经营活动现金流 (OCF)", "n_cashflow_act"),
            ("投资活动现金流", "n_cashflow_inv_act"),
            ("筹资活动现金流", "n_cash_flows_fnc_act"),
            ("资本支出(购建固定资产等)", "c_pay_acq_const_fiolta"),
            ("支付给职工现金", "c_pay_to_staff"),
            ("支付的各项税费", "c_paid_for_taxes"),
            ("处置固定资产收回现金", "n_recp_disp_fiolta"),
            ("取得投资收益收到现金", "c_recp_return_invest"),
            ("分配股利偿付利息", "c_pay_dist_dpcp_int_exp"),
        ]

        for label, internal_name in simple_fields:
            ak_name = self._CASHFLOW_FIELD_MAP.get(internal_name)
            row = [label]
            for _, r in df.iterrows():
                val = r.get(ak_name) if ak_name else None
                row.append(format_number(val))
            rows.append(row)

        # D&A = 固定资产折旧 + 无形资产摊销 + 长期待摊费用摊销
        da_row = ["折旧与摊销 (D&A)"]
        for _, r in df.iterrows():
            depr = r.get("固定资产折旧")
            amort_intang = r.get("无形资产摊销")
            amort_deferred = r.get("长期待摊费用摊销")
            vals = [v for v in [depr, amort_intang, amort_deferred]
                   if v is not None and v == v]
            if vals:
                da_row.append(format_number(sum(float(v) for v in vals)))
            else:
                da_row.append("—")
        rows.append(da_row)

        # FCF = OCF - |Capex|
        fcf_row = ["自由现金流 (FCF)"]
        for _, r in df.iterrows():
            ocf = r.get("经营活动产生的现金流量净额")
            capex = r.get("购建固定资产、无形资产和其他长期资产所支付的现金")
            if ocf is not None and capex is not None:
                fcf = float(ocf) - abs(float(capex))
                fcf_row.append(format_number(fcf))
            else:
                fcf_row.append("—")
        rows.append(fcf_row)

        table = format_table(headers, rows, alignments=["l"] + ["r"] * len(years))
        lines.append(table)
        lines.append("")
        lines.append("*单位: 百万元; FCF = OCF - |Capex|*")
        return "\n".join(lines)

    # --- Section 6: Dividend history ---

    def get_dividends(self, ts_code: str) -> str:
        """Section 6: Dividend history."""
        symbol = self._convert_code_to_akshare(ts_code)
        lines = [format_header(2, "6. 分红历史"), ""]

        try:
            df = ak.stock_dividend_detail_em(symbol=symbol)
        except Exception as e:
            lines.append(f"数据缺失: {e}\n")
            return "\n".join(lines)

        if df.empty:
            lines.append("暂无分红数据\n")
            return "\n".join(lines)

        # Filter for implemented dividends
        df = df[df["分红方案"] != ""].copy()
        df = df.drop_duplicates(subset=["每股派息"])
        df = df.sort_values("除权除息日", ascending=False)

        # Store for derived metrics
        self._store["dividends"] = df

        if df.empty:
            lines.append("暂无已实施分红\n")
            return "\n".join(lines)

        # Take top 5 years
        df["年度"] = df["除权除息日"].astype(str).str[:4]
        top_years = df["年度"].drop_duplicates().head(5).tolist()
        df = df[df["年度"].isin(top_years)]

        headers = ["年度", "每股现金分红(含税)", "除权除息日", "总分红 (百万元)"]
        rows = []
        for _, r in df.iterrows():
            year = str(r.get("除权除息日", ""))[:4]
            cash_div = r.get("每股派息", 0) or 0
            ex_date = str(r.get("除权除息日", "—"))
            # Approximate total dividend in millions
            rows.append([
                year,
                f"{cash_div:.4f}",
                ex_date,
                "—"  # 总分红需要股本数据，这里简化处理
            ])

        table = format_table(headers, rows, alignments=["l", "r", "l", "r"])
        lines.append(table)
        return "\n".join(lines)

    # --- Section 11: Weekly prices ---

    def get_weekly_prices(self, ts_code: str) -> str:
        """Section 11: 10-year weekly price history."""
        symbol = self._convert_code_to_akshare(ts_code)
        lines = [format_header(2, "11. 十年周线行情"), ""]

        try:
            end_date = pd.Timestamp.now().strftime("%Y%m%d")
            ten_years_ago = (pd.Timestamp.now() - pd.DateOffset(years=10)).strftime("%Y%m%d")

            df = ak.stock_zh_a_hist(symbol=symbol, period="weekly",
                                    start_date=ten_years_ago, end_date=end_date, adjust="qfq")
        except Exception as e:
            lines.append(f"数据缺失: {e}\n")
            return "\n".join(lines)

        if df.empty:
            lines.append("数据缺失\n")
            return "\n".join(lines)

        df = df.sort_values("日期", ascending=True)

        # Store for derived metrics
        self._store["weekly_prices"] = df

        # 10-year summary
        high_10y = df["最高"].max()
        low_10y = df["最低"].min()
        high_date = df.loc[df["最高"].idxmax(), "日期"]
        low_date = df.loc[df["最低"].idxmin(), "日期"]
        latest_close = df.iloc[-1]["收盘"]

        summary_table = format_table(
            ["指标", "数值"],
            [
                ["10年最高", f"{high_10y:.2f} ({high_date})"],
                ["10年最低", f"{low_10y:.2f} ({low_date})"],
                ["最新收盘", f"{latest_close:.2f}"],
                ["距最高回撤", f"{(1 - latest_close / high_10y) * 100:.1f}%"],
                ["距最低涨幅", f"{(latest_close / low_10y - 1) * 100:.1f}%"],
            ],
            alignments=["l", "r"],
        )
        lines.append(summary_table)
        lines.append("")

        # Annual summary
        df["year"] = df["日期"].astype(str).str[:4]
        annual = df.groupby("year").agg(
            high=("最高", "max"),
            low=("最低", "min"),
            close=("收盘", "last"),
            avg_vol=("成交量", "mean"),
        ).reset_index()
        annual = annual.sort_values("year", ascending=False)

        lines.append(format_header(3, "年度行情汇总"))
        lines.append("")
        annual_table = format_table(
            ["年度", "最高", "最低", "年末收盘", "周均成交量(手)"],
            [[
                r["year"],
                f"{r['high']:.2f}",
                f"{r['low']:.2f}",
                f"{r['close']:.2f}",
                f"{r['avg_vol']:,.0f}",
            ] for _, r in annual.iterrows()],
            alignments=["l", "r", "r", "r", "r"],
        )
        lines.append(annual_table)
        return "\n".join(lines)

    # --- Section 12: Financial indicators ---

    def get_fina_indicators(self, ts_code: str) -> str:
        """Section 12: Key financial indicators (akshare doesn't have dedicated indicator API)."""
        # Akshare doesn't have a direct financial indicator API equivalent to tushare's fina_indicator
        # We compute basic indicators from the stored financial data
        lines = [format_header(2, "12. 关键财务指标"), ""]

        income_df = self._store.get("income")
        balance_df = self._store.get("balance_sheet")
        cashflow_df = self._store.get("cashflow")

        if income_df is None or income_df.empty:
            lines.append("数据缺失\n")
            return "\n".join(lines)

        # Build indicator table from computed data
        fy_month_str = f"{self._fy_end_month:02d}"
        annual_inc = income_df[income_df["报告日"].astype(str).str[4:6] == fy_month_str].copy()
        annual_inc = annual_inc.sort_values("报告日", ascending=False).head(5)

        if annual_inc.empty:
            lines.append("无年报数据\n")
            return "\n".join(lines)

        years = [str(r["报告日"])[:4] for _, r in annual_inc.iterrows()]

        # Compute ROE, gross margin, net margin from income data
        headers = ["指标"] + years
        rows = []

        # Gross margin
        gross_rows = []
        for _, r in annual_inc.iterrows():
            rev = r.get("营业收入")
            cost = r.get("营业成本")
            if rev and rev > 0:
                gross_rows.append(f"{(rev - cost) / rev * 100:.2f}")
            else:
                gross_rows.append("—")
        rows.append(["毛利率 (%)"] + gross_rows)

        # Net margin
        net_rows = []
        for _, r in annual_inc.iterrows():
            rev = r.get("营业收入")
            ni = r.get("净利润")
            if rev and rev > 0 and ni:
                net_rows.append(f"{ni / rev * 100:.2f}")
            else:
                net_rows.append("—")
        rows.append(["净利率 (%)"] + net_rows)

        table = format_table(headers, rows, alignments=["l"] + ["r"] * len(years))
        lines.append(table)
        lines.append("")
        lines.append("*注: akshare 未提供独立财务指标API，以上指标由利润表数据计算*")
        return "\n".join(lines)


# Import akshare locally to avoid circular import
import akshare as ak
