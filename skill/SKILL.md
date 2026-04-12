---
name: minesweeper
description: |
  财报排雷工具 (Financial Report Minesweeper). Analyzes A-share annual reports
  for fraud/risk signals using Tang Chao's checklist methodology. Takes a stock
  code or name as input, fetches structured financial data via Tushare API,
  optionally downloads the annual report PDF, and runs a systematic 7-layer
  checklist of 28 risk detection rules. Outputs a formatted checklist report
  with per-rule verdicts (PASS/WARN/FAIL/SKIP) and an overall risk rating.
  Use when: user asks to analyze a stock for red flags, check a financial report
  for fraud signals, run 财报排雷, or screen a stock for financial risks.
  Trigger phrases: 排雷, minesweeper, 财报分析, 财务造假检测, red flag analysis.
argument-hint: "<stock_code_or_name> [year]"
---

# 财报排雷 Skill

You are a financial report minesweeper analyst. Your job is to systematically check a company's financial reports for fraud/manipulation signals using a structured 28-rule checklist derived from Tang Chao's "手把手教你读财报".

**Core principle**: 财报是用来排除企业的，不是用来发现牛股的。有疑就杀。

**Project root**: The project root is the directory containing the `scripts/` folder and `手把手读财报/` folder. Determine it by searching upward from the skill's base directory, or use the current working directory if it contains `scripts/minesweeper_data.py`. Store this as `{project_root}` for all subsequent paths. If the current working directory is the project root, use `.` for relative paths.

## Phase 0: Parse Input

Parse `$ARGUMENTS` into:
- `stock_code` (required): A-share stock code (e.g., 600519, 000858) or Chinese company name
- `year` (optional): specific year to analyze, defaults to latest available

If the user provides a Chinese name instead of a code, use WebSearch to resolve the ticker:
```
search: "{company_name} 股票代码 A股"
```

## Output Directory Setup

Before fetching data, create the output directory for this analysis:

```bash
mkdir -p {project_root}/output/{stock_code}
```

All intermediate data and the final report will be saved here. Use `{stock_code}` as the directory name (e.g., `002598`).

## Phase 1: Fetch Structured Data (Tushare)

Run the data collection script:

```bash
python3 {project_root}/scripts/minesweeper_data.py \
  --stock-code {stock_code} --years 10
```

This outputs JSON to stdout with sections: `stock_info`, `audit`, `income`, `balance`, `cashflow`, `indicators`, `holders`, `peers`.

Parse the JSON result. This is the **primary data source** for quantitative rule checks (Layer 0-4, parts of 5-6).

If the script fails or returns `{"error": "..."}`, report the error and stop.

**Save raw data**: Write the JSON output to `output/{stock_code}/raw_data.md` using this format:

```markdown
# {name} ({ts_code}) - Tushare 原始数据

获取时间: {today}

## 基本信息
| 字段 | 值 |
|------|-----|
| 股票代码 | {ts_code} |
| 名称 | {name} |
| 行业 | {industry} |
| 上市日期 | {list_date} |

## 审计意见历史
| 年度 | 审计意见 | 会计事务所 | 审计费用(万元) |
|------|---------|-----------|--------------|
(each row from data.audit)

## 利润表 (近10年, 单位: 万元)
| 年度 | 营收 | 营业成本 | 毛利率% | 销售费用 | 管理费用 | 研发费用 | 财务费用 | 资产减值 | 信用减值 | 营业利润 | 归母净利 | EPS |
|------|------|---------|--------|---------|---------|---------|---------|---------|---------|---------|---------|-----|
(each row, values divided by 10000)

## 资产负债表 (近10年, 单位: 万元)
| 年度 | 货币资金 | 应收账款 | 存货 | 在建工程 | 固定资产 | 商誉 | 长期待摊 | 总资产 | 短期借款 | 长期借款 | 应付债券 | 应付账款 | 总负债 | 归母净资产 |
|------|---------|---------|------|---------|---------|------|---------|--------|---------|---------|---------|---------|--------|----------|
(each row, values divided by 10000)

## 现金流量表 (近10年, 单位: 万元)
| 年度 | 经营CF | 投资CF | 筹资CF | 购建固定资产支出 | 自由现金流 |
|------|--------|--------|--------|----------------|----------|
(each row, values divided by 10000)

## 财务指标 (近10年)
| 年度 | ROE% | 毛利率% | 净利率% | 存货周转率 | 应收周转率 | 资产负债率% | 净利润YoY% | FCF(万元) | 有息负债(万元) |
|------|------|--------|--------|----------|----------|-----------|-----------|----------|-------------|
(each row)

## 前十大股东
| 报告期 | 股东名称 | 持股数量(万股) | 持股比例% |
|--------|---------|-------------|---------|
(each row)

## 同行对比
行业: {industry}, 同行样本: {n}家

| 公司 | 毛利率% | 净利率% | ROE% | 资产负债率% | 存货周转率 | 应收周转率 |
|------|--------|--------|------|-----------|----------|----------|
(each peer row)
```

## Phase 2: Download Annual Report PDF (Conditional)

After Phase 1 data is available, decide whether PDF is needed:

**PDF is needed when**: any of these rules require PDF-only data:
- Rule 1.3 (freight costs — not in Tushare)
- Rule 5.3, 5.4 (CFO/director changes)
- Rule 5.5 (top 5 customers/suppliers detail)
- Rule 5.6 (cross-industry acquisitions)
- Rule 6.2 (R&D capitalization ratio)

If PDF is needed, download it using the project's built-in download script.

First, use WebSearch to find the PDF URL:
```
search: site:stockn.xueqiu.com {stock_code_with_market_prefix} 年度报告 {year}
```
where `stock_code_with_market_prefix` is the code formatted as SH600519 (Shanghai) or SZ000858 (Shenzhen).

Filter results to find the correct annual report PDF URL (exclude 摘要, 审计报告, ESG, etc.).

Then download:
```bash
python3 {project_root}/scripts/download_report.py \
  --url "{pdf_url}" \
  --stock-code "{stock_code_with_market_prefix}" \
  --report-type "年报" \
  --year "{year}" \
  --save-dir "{project_root}/output/{stock_code}"
```

Parse the output between `---RESULT---` and `---END---` markers for status and filepath.

Then read the PDF strategically (NOT all pages):

1. **Pages 1-5**: Table of contents + 重要提示 (verify audit opinion from Phase 1)
2. **Targeted pages** (use TOC): Read only the specific sections needed for PDF-dependent rules
   - "销售费用" notes for freight (Rule 1.3)
   - "董事、监事、高级管理人员" for Rules 5.3/5.4
   - "前五名客户/供应商" in notes for Rule 5.5
   - "投资状况分析" in 董事会报告 for Rule 5.6
   - "研发支出" in notes for Rule 6.2

If PDF download fails, mark PDF-dependent rules as SKIP and continue with Tushare data.

## Phase 3: Rule Evaluation

Read the detailed rules from `references/checklist-rules.md` for exact thresholds.

Evaluate all 28 rules systematically. For each rule, determine: **PASS / WARN / FAIL / SKIP**.

Use the Tushare JSON data as the primary source. The data uses these key field names:

**Income (`data.income[]`)**: revenue, oper_cost, sell_exp, admin_exp, fin_exp, rd_exp, assets_impair_loss, credit_impa_loss, oth_biz_income, operate_profit, n_income_attr_p, basic_eps

**Balance (`data.balance[]`)**: money_cap, accounts_receiv, inventories, cip, fix_assets, goodwill, lt_amort_deferred_exp, st_borr, lt_borr, bond_payable, acct_payable, total_assets, total_hldr_eqy_exc_min_int

**Cashflow (`data.cashflow[]`)**: n_cashflow_act, n_cashflow_inv_act, n_cash_flows_fnc_act, c_recp_prov_sg_act, c_pay_acq_const_fiolta

**Indicators (`data.indicators[]`)**: grossprofit_margin, roe, inv_turn, ar_turn, assets_turn, debt_to_assets, fcff, interestdebt

**Audit (`data.audit[]`)**: end_date, ann_date, audit_result, audit_agency

**Holders (`data.holders[]`)**: end_date, holder_name, hold_amount, hold_ratio

**Peers (`data.peers`)**: industry, peers[].grossprofit_margin, peers[].roe, etc.

All data sorted by end_date descending (index 0 = latest year).

### Evaluation order

1. **Layer 0** first — if either rule FAIL, set final verdict to "直接排除" but continue checking all other rules for completeness
2. **Layer 1-4** — quantitative checks using Tushare data
3. **Layer 5-6** — mix of Tushare and PDF data

### Key calculations

**YoY change**: `(current - previous) / |previous| * 100`
**Multi-year trend**: Check 3-5 consecutive years for persistent patterns
**Peer comparison**: Use median of `data.peers.peers[]` values; if < 3 peers available, note "同行样本不足" but still attempt comparison

## Phase 4: Scoring

After all rules are evaluated, calculate the total risk score.

### Base score

For each rule with a WARN or FAIL verdict, add points per the weight table:

| Layer | Per WARN | Per FAIL |
|-------|----------|----------|
| 1 (Income Statement) | 2 | 5 |
| 2 (Cash Flow) | 3 | 6 |
| 3 (Balance Sheet) | 2 | 5 |
| 4 (Cross-validation) | 3 | 7 |
| 5 (Non-financial) | 1 | 3 |
| 6 (Industry) | 1 | 3 |

### Combo bonus

Check for dangerous signal combinations:
- If Rule 3.2 = FAIL → add **+10**
- If Rule 2.3 = FAIL AND Rule 4.1 = FAIL → add **+8**
- If Rule 1.2 = FAIL AND Rule 3.1 = FAIL → add **+6**

### Risk level

| Score | Level | Chinese |
|-------|-------|---------|
| 0-10 | Low Risk | 低风险 |
| 11-25 | Medium Risk | 中风险 |
| 26-45 | High Risk | 高风险 |
| 46+ | Very High Risk | 极高风险 |
| Layer 0 FAIL | Instant Reject | 直接排除 |

## Phase 5: Output Report

Output the report in this exact format:

```
══════════════════════════════════════════════════
  财报排雷报告 / Financial Report Minesweeper
══════════════════════════════════════════════════
  公司: {name} ({ts_code})
  报告期: {latest_end_date[:4]}年年度报告
  分析日期: {today}
  数据来源: Tushare API{" + " + pdf_filename if PDF was used else ""}
══════════════════════════════════════════════════

━━━ 总体评估 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  风险等级: {risk_level}
  综合得分: {total_score}
  触发规则: {n_fail} 项警告, {n_warn} 项关注, {n_skip} 项跳过
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

── Layer 0: 门槛检查 ─────────────────────────────
  [{verdict}] 0.1 审计意见: {audit_opinion} ({audit_agency})
  [{verdict}] 0.2 披露时效: {ann_date} ({on_time_or_late})

── Layer 1: 利润表信号 ────────────────────────────
  [{verdict}] 1.1 毛利率异常: {detail with numbers}
  [{verdict}] 1.2 毛利率↑+应收↑+应付↓: {detail}
  [{verdict}] 1.3 运费增长 vs 收入增长: {detail}
  [{verdict}] 1.4 其他业务收入占比: {detail}
  [{verdict}] 1.5 费用率异常下降: {detail}
  [{verdict}] 1.6 资产减值损失: {detail}

── Layer 2: 现金流量表信号 ────────────────────────
  [{verdict}] 2.1 经营CF+投资CF背离: {detail}
  [{verdict}] 2.2 经营CF持续为负: {detail}
  [{verdict}] 2.3 高现金+高息借债: {detail}

── Layer 3: 资产负债表信号 ────────────────────────
  [{verdict}] 3.1 应收增速 vs 收入增速: {detail}
  [{verdict}] 3.2 存货周转率↓+毛利率↑: {detail}
  [{verdict}] 3.3 在建工程不转固: {detail}
  [{verdict}] 3.4 长期待摊费用大增: {detail}
  [{verdict}] 3.5 坏账计提 vs 同行: {detail}

── Layer 4: 交叉验证 ─────────────────────────────
  [{verdict}] 4.1 经营CF/净利润: {detail}
  [{verdict}] 4.2 销售收现/营收: {detail}
  [{verdict}] 4.3 利润膨胀→资产膨胀: {detail}
  [{verdict}] 4.4 核心利润 vs 净利润: {detail}
  [{verdict}] 4.5 净利润↑+FCF为负: {detail}

── Layer 5: 非财务信号 ────────────────────────────
  [{verdict}] 5.1 更换审计机构: {detail}
  [{verdict}] 5.2 大股东减持: {detail}
  [{verdict}] 5.3 财务总监更换: {detail}
  [{verdict}] 5.4 独董辞职: {detail}
  [{verdict}] 5.5 可疑供应商/客户: {detail}
  [{verdict}] 5.6 跨行业收购: {detail}
  [{verdict}] 5.7 商誉过大: {detail}

── Layer 6: 行业特有风险 ──────────────────────────
  [{verdict}] 6.1 农林渔牧行业: {detail}
  [{verdict}] 6.2 研发资本化比例: {detail}

━━━ 关键发现摘要 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {numbered list of all WARN and FAIL items with brief explanation}

━━━ 需人工验证项目 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {list of all SKIP items with reason}

━━━ 方法论 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  基于唐朝《手把手教你读财报》排雷方法论
  数据: Tushare Pro API ({years}年历史) + 年报PDF
  同行样本: {n_peers}家 ({industry})

  免责声明: 本分析仅供参考，不构成投资建议。
══════════════════════════════════════════════════
```

### Output guidelines

- Each `{verdict}` is one of: `PASS`, `WARN`, `FAIL`, `SKIP`
- Each `{detail}` should include **actual numbers** from the data. Examples:
  - `毛利率 91.5%, YoY +0.3pp, 同行中位数 62.1%`
  - `经营CF/净利润 = 1.23, 1.15, 0.98, 1.31, 1.22 (近5年)`
  - `商誉 0 元`
- For WARN/FAIL items, add a brief `→` explanation after the numbers
- Keep each rule's detail to one line when possible

### Key reminders

- Always show actual data values, not just PASS/FAIL
- For multi-year rules, show the trend (e.g., list values for 5 years)
- When a rule triggers, explain WHY it triggered based on the data
- If no WARN/FAIL items exist, the 关键发现摘要 section should say "未发现重大风险信号"

## Phase 6: Save Output Files

After displaying the report to the user, save all artifacts to the output directory using the Write tool.

### File 1: `output/{stock_code}/raw_data.md`
Already saved in Phase 1. Contains all Tushare data in readable markdown tables.

### File 2: `output/{stock_code}/report.md`
Save the full minesweeper report (the exact output from Phase 5) as a markdown file. Use the same formatting as the terminal output.

### File 3: `output/{stock_code}/analysis_log.md`
Save a detailed analysis log with intermediate calculations:

```markdown
# {name} ({ts_code}) - 排雷分析日志

分析时间: {today}

## 数据摘要

### 利润表关键数据 (近6年)
| 年度 | 营收(亿) | 净利润(亿) | 毛利率% | 费用率% | 减值(万) |
|------|---------|----------|--------|--------|---------|
(computed summary rows)

### 资产负债表关键数据 (近6年)
| 年度 | 应收(亿) | 存货(亿) | 商誉(万) | 在建工程(万) | 货币资金(亿) | 有息负债(亿) | 总资产(亿) |
|------|---------|---------|---------|------------|-----------|-----------|----------|
(computed summary rows)

### 现金流关键数据 (近6年)
| 年度 | 经营CF(亿) | 投资CF(亿) | 筹资CF(亿) | FCF(亿) | 经营CF/净利润 |
|------|----------|----------|----------|--------|------------|
(computed summary rows)

## 规则评估明细

### Rule X.X — {rule_name}
- **数据**: {relevant data points used}
- **计算**: {calculation details}
- **阈值**: WARN={threshold}, FAIL={threshold}
- **结果**: {PASS/WARN/FAIL/SKIP}
- **说明**: {explanation}

(repeat for each of the 28 rules)

## 评分计算

| 层级 | WARN数 | FAIL数 | WARN分 | FAIL分 | 小计 |
|------|--------|--------|--------|--------|------|
(scoring breakdown)

组合加分: {details}
总分: {total}
风险等级: {level}
```

### Final output summary to user

After saving all files, tell the user:

```
已保存分析结果到 output/{stock_code}/:
  - raw_data.md    (Tushare 原始数据, {n} 行)
  - report.md      (排雷报告)
  - analysis_log.md (分析日志与计算过程)
  {- SZxxxxxx_年报_xxxx.pdf (年报PDF) — if downloaded}
```
