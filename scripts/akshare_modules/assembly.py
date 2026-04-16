"""Financial Report Minesweeper - AssemblyMixin + WarningsCollector.

Data pack assembly, derived metrics orchestration, and warning collection.
"""

import re

import pandas as pd

from format_utils import format_number, format_table, format_header


class AssemblyMixin:
    """Mixin providing data pack assembly for AkshareClient."""

    def compute_derived_metrics(self, ts_code: str) -> str:
        """Compute §17: Derived metrics from stored DataFrames.

        Must be called after all get_* methods have populated self._store.
        """
        lines = [
            format_header(2, "17. 衍生指标（Python 预计算）"),
            "",
            f"> 以下指标基于 §1-§16 原始数据确定性计算，无 LLM 判断成分。{self._unit_label()}。",
            "",
        ]

        sub_methods = [
            self._compute_financial_trends,
        ]

        for method in sub_methods:
            try:
                result = method()
                if result:
                    lines.append(result)
                    lines.append("")
            except Exception as e:
                name = getattr(method, "__name__", str(method))
                lines.append(f"*{name} 计算失败: {e}*")
                lines.append("")

        return "\n".join(lines)

    # --- Refresh-market helpers ---

    @staticmethod
    def _parse_sections(content: str):
        """Split data_pack_market.md content into header, sections list, and footer.

        Returns:
            (header_str, sections_list, footer_str)
        """
        section_re = re.compile(r"^(## (\d+[A-Z]?)\. .*)$", re.MULTILINE)

        matches = list(section_re.finditer(content))
        if not matches:
            return content, [], ""

        header = content[: matches[0].start()]

        sections = []
        for i, m in enumerate(matches):
            key = m.group(2)
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            sections.append((key, content[start:end]))

        # Separate footer from the last section
        footer = ""
        if sections:
            last_key, last_text = sections[-1]
            footer_re = re.compile(r"\n---\n\*共 .+$", re.DOTALL)
            fm = footer_re.search(last_text)
            if fm:
                footer = last_text[fm.start():]
                sections[-1] = (last_key, last_text[: fm.start()])

        return header, sections, footer

    def _build_header(self, ts_code: str) -> str:
        """Build the data pack header block (title, timestamp, source, unit)."""
        timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        currency = self._detect_currency(ts_code)
        self._currency = currency
        unit_label = {"HKD": "百万港元", "USD": "百万美元"}.get(currency, "百万元")
        lines = [
            format_header(1, f"数据包 — {ts_code}"),
            "",
            f"*生成时间: {timestamp}*",
            f"*数据来源: Akshare*",
            f"*金额单位: {unit_label} (除特殊标注)*",
        ]
        if currency == "HKD":
            lines.append("*报表币种: HKD*")
        elif currency == "USD":
            lines.append("*报表币种: USD*")
        lines.extend(["", "---", ""])
        return "\n".join(lines)

    @staticmethod
    def _check_staleness(content: str) -> int:
        """Return the number of days since the data pack was generated."""
        m = re.search(r"\*生成时间:\s*(\d{4}-\d{2}-\d{2})", content)
        if not m:
            return 999
        try:
            gen_date = pd.Timestamp(m.group(1))
            now = pd.Timestamp.now().normalize()
            return (now - gen_date.normalize()).days
        except Exception:
            return 999

    _REFRESH_SECTIONS = {"1", "2", "11", "14"}

    def refresh_market_sections(self, ts_code: str, existing_content: str) -> str:
        """Re-fetch market-sensitive sections and merge with existing data pack."""
        _header, sections, footer = self._parse_sections(existing_content)

        fetch_map = {
            "1": ("1. 基本信息", self.get_basic_info),
            "2": ("2. 市场行情", self.get_market_data),
            "11": ("11. 十年周线行情", self.get_weekly_prices),
            "14": ("14. 无风险利率", self.get_risk_free_rate),
        }

        currency = self._detect_currency(ts_code)
        self._currency = currency

        new_sections = []
        for key, text in sections:
            if key in fetch_map:
                name, method = fetch_map[key]
                try:
                    print(f"  Refreshing {name}...")
                    fresh_md = method(ts_code)
                    if not fresh_md.endswith("\n"):
                        fresh_md += "\n"
                    new_sections.append((key, fresh_md))
                except Exception as e:
                    print(f"  ⚠️ Failed to refresh {name}: {e}, keeping old data")
                    new_sections.append((key, text))
            else:
                new_sections.append((key, text))

        new_header = self._build_header(ts_code)
        new_header += "*刷新模式: --refresh-market（仅更新 §1/§2/§11/§14）*\n"
        new_header += "\n"

        parts = [new_header]
        for _key, text in new_sections:
            parts.append(text)

        result = "".join(parts)

        if footer:
            result = result.rstrip("\n") + footer
        else:
            result = result.rstrip("\n") + "\n"

        return result

    # --- Full data_pack_market.md assembly ---

    def assemble_data_pack(self, ts_code: str) -> str:
        """Assemble complete data_pack_market.md combining all sections."""
        timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        currency = self._detect_currency(ts_code)
        self._currency = currency
        unit_label = {"HKD": "百万港元", "USD": "百万美元"}.get(currency, "百万元")
        lines = [
            format_header(1, f"数据包 — {ts_code}"),
            "",
            f"*生成时间: {timestamp}*",
            f"*数据来源: Akshare*",
            f"*金额单位: {unit_label} (除特殊标注)*",
        ]
        if currency == "HKD":
            lines.append(f"*报表币种: HKD*")
        elif currency == "USD":
            lines.append(f"*报表币种: USD*")
        lines.extend(["", "---", ""])

        sections = [
            ("1. 基本信息", self.get_basic_info),
            ("2. 市场行情", self.get_market_data),
            ("3. 合并利润表", self.get_income),
            ("3P. 母公司利润表", self.get_income_parent),
            ("4. 合并资产负债表", self.get_balance_sheet),
            ("4P. 母公司资产负债表", self.get_balance_sheet_parent),
            ("5. 现金流量表", self.get_cashflow),
            ("6. 分红历史", self.get_dividends),
            ("11. 十年周线行情", self.get_weekly_prices),
            ("12. 关键财务指标", self.get_fina_indicators),
        ]

        completed = 0
        for name, method in sections:
            try:
                print(f"  Collecting {name}...")
                section_md = method(ts_code)
                lines.append(section_md)
                lines.append("")
                completed += 1
            except Exception as e:
                lines.append(format_header(2, name))
                lines.append(f"\n数据获取失败: {e}\n")

        # Risk-free rate placeholder
        try:
            print("  Collecting 14. 无风险利率...")
            rf_md = self.get_risk_free_rate(ts_code)
            lines.append(rf_md)
            lines.append("")
        except Exception as e:
            lines.append(format_header(2, "14. 无风险利率"))
            lines.append(f"\n数据获取失败: {e}\n")

        # §17 Derived metrics
        try:
            print("  Computing 17. 衍生指标...")
            derived_md = self.compute_derived_metrics(ts_code)
            lines.append(derived_md)
            lines.append("")
        except Exception as e:
            lines.append(format_header(2, "17. 衍生指标（Python 预计算）"))
            lines.append(f"\n计算失败: {e}\n")

        # §13 Warnings placeholder
        lines.append(format_header(2, "13. 风险警示"))
        lines.append("")
        lines.append("*[§13 待完善]*")
        lines.append("")

        lines.append("---")
        lines.append(f"*共 {completed}/{len(sections)} 个数据板块成功获取*")

        return "\n".join(lines)


class WarningsCollector:
    """Auto-detect anomalies during data collection."""

    def __init__(self):
        self.warnings = []

    def check_missing_data(self, section_name: str, df: pd.DataFrame):
        """Warn if a data section returned empty."""
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            self.warnings.append({
                "type": "DATA_MISSING",
                "severity": "中",
                "message": f"{section_name} 数据缺失",
            })

    def check_yoy_change(self, section_name: str, field_name: str,
                         values: list, threshold: float = 3.0,
                         dates: list = None):
        """Warn if year-over-year change exceeds threshold."""
        for i in range(len(values) - 1):
            curr, prev = values[i], values[i + 1]
            if prev is not None and curr is not None and float(prev) != 0:
                try:
                    change = abs(float(curr) / float(prev) - 1)
                    if change > threshold:
                        period = ""
                        if dates and i + 1 < len(dates):
                            period = f"{dates[i+1]}→{dates[i]} "
                        self.warnings.append({
                            "type": "YOY_ANOMALY",
                            "severity": "高",
                            "message": f"{section_name}/{field_name}: "
                                       f"{period}同比变化 {change*100:.0f}% 超过 {threshold*100:.0f}% 阈值",
                        })
                except (ValueError, ZeroDivisionError):
                    pass

    def check_audit_risk(self, audit_opinion: str):
        """Warn if audit opinion is not clean."""
        if audit_opinion and audit_opinion not in ("标准无保留意见", "—", ""):
            self.warnings.append({
                "type": "AUDIT_RISK",
                "severity": "高",
                "message": f"审计意见非标准: {audit_opinion}",
            })

    def check_goodwill_ratio(self, goodwill: float, total_assets: float):
        """Warn if goodwill/total_assets > 20%."""
        if goodwill and total_assets and total_assets > 0:
            ratio = float(goodwill) / float(total_assets)
            if ratio > 0.20:
                self.warnings.append({
                    "type": "GOODWILL_RISK",
                    "severity": "高",
                    "message": f"商誉占总资产比例 {ratio*100:.1f}% 超过 20%",
                })

    def check_debt_ratio(self, total_liab: float, total_assets: float):
        """Warn if debt ratio > 70%."""
        if total_liab and total_assets and total_assets > 0:
            ratio = float(total_liab) / float(total_assets)
            if ratio > 0.70:
                self.warnings.append({
                    "type": "LEVERAGE_RISK",
                    "severity": "中",
                    "message": f"资产负债率 {ratio*100:.1f}% 超过 70%",
                })

    def format_warnings(self) -> str:
        """Format all collected warnings as section 13 markdown."""
        lines = [format_header(2, "13. 风险警示 (脚本自动生成)"), ""]

        if not self.warnings:
            lines.append("未检测到异常。")
            return "\n".join(lines)

        high = [w for w in self.warnings if w["severity"] == "高"]
        medium = [w for w in self.warnings if w["severity"] == "中"]
        low = [w for w in self.warnings if w["severity"] == "低"]

        if high:
            lines.append("**高风险:**")
            for w in high:
                lines.append(f"- [{w['type']}] {w['message']}")
            lines.append("")
        if medium:
            lines.append("**中风险:**")
            for w in medium:
                lines.append(f"- [{w['type']}] {w['message']}")
            lines.append("")
        if low:
            lines.append("**低风险:**")
            for w in low:
                lines.append(f"- [{w['type']}] {w['message']}")
            lines.append("")

        lines.append(f"*共 {len(self.warnings)} 条自动警示*")
        return "\n".join(lines)
