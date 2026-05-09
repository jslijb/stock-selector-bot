# 认知型智能选股 Agent

个人用、单机、零预算、无 GPU 的 A 股量化选股系统。运行即输出股票代码。

## 环境准备

### 1. Python 环境
- Python >= 3.12
- 推荐: conda 创建虚拟环境

```bash
conda create -n stock_agent python=3.12
conda activate stock_agent
pip install -r requirements.txt
```

### 2. 环境变量

| 变量名 | 说明 | 获取方式 |
|--------|------|---------|
| `TUSHARE_TOKEN` | Tushare API Token (120积分即可) | [Tushare官网](https://tushare.pro/) |
| `DASHSCOPE_API_KEY` | 阿里百炼 API Key | [阿里百炼](https://bailian.console.aliyun.com/) |

**Windows：**
```bash
set TUSHARE_TOKEN=你的token
set DASHSCOPE_API_KEY=你的key
```

### 3. LLM 配置（热加载）

编辑 `config/llm_config.yaml`，修改后自动生效，无需重启。

可选模型：`qwen-plus`(推荐)、`qwen-turbo`、`qwen-max`、`deepseek-v3`

### 4. Embedding 模型

首次运行自动下载 `BAAI/bge-large-zh-v1.5`(~1.3GB)，CPU 推理约 50ms/条。

---

## 使用方法

### 每日选股

```bash
python main.py
```

### 历史补跑（两阶段，推荐）

```bash
# 第一阶段：仅采集日线+复权数据（~3秒/天）
python main.py -p1 20240101 20260430

# 第二阶段：因子计算 + 选股决策 + 风控 + 进化
python main.py -p2 20240101 20260430

# 补跑资金流向（可选）
python main.py -mf 20240101 20260430
```

### 其他命令

```bash
python main.py -d 20260505          # 补跑单日
python main.py -b 20250101 20260506 # 批量补跑(完整7步)
python main.py -t 15:30             # 定时模式
python main.py -c                   # 检查缺失日期
python main.py -f                   # 强制重跑(跳过已有数据)
```

### 一次性数据准备

首次使用需要初始化基础数据：

```bash
# 1. 采集行情数据（p1阶段，约30分钟/2年）
python main.py -p1 20240101 20260430

# 2. 行业分类（从东方财富获取，免费无限制，约20秒）
python -c "import akshare as ak; ..."  # 系统会自动调用

# 3. 年报/季报财务数据（从东方财富获取，约2分钟）
python -c "import akshare as ak; ..."  # 系统会自动调用

# 4. 因子计算+选股（p2阶段，约2-3小时/2年）
python main.py -p2 20240101 20260430
```

**最低数据要求**：因子最大回溯窗口252交易日(1年)，推荐补跑2-3年数据。

---

## 项目架构

```
config/
├── settings.yaml          # 基础配置（数据库/因子/风控/进化/初筛）
└── llm_config.yaml        # LLM配置（热加载）

src/
├── config.py              # 配置加载 + 热加载监控(daemon线程)
├── scheduler.py           # 每日调度(7步流程) + 初筛 + 两阶段补跑
├── data/
│   ├── db.py              # DuckDB 连接管理(单例)
│   ├── schema.py          # 12张核心表Schema
│   ├── collector.py       # Tushare采集 + baostock日历/资金流向
│   └── money_flow.py      # baostock 5分钟线资金流向估算
├── factors/
│   ├── engine.py          # 因子引擎(pipeline: 计算→中性化→去极值→Z-Score)
│   ├── registry.py        # 因子注册中心
│   ├── valuation.py       # 估值因子(15)
│   ├── quality.py         # 质量因子(20)
│   ├── growth.py          # 成长因子(15)
│   ├── momentum.py        # 动量/反转因子(28)
│   ├── sentiment.py       # 资金/情绪因子(15)
│   ├── technical.py       # 技术因子(30)
│   ├── alternative.py     # 另类因子(20)
│   └── nlp_sentiment.py   # NLP舆情(阿里百炼LLM)
├── memory/
│   └── memory.py          # ChromaDB + BGE向量检索(容错降级)
├── reasoning/
│   └── engine.py          # 三层推理: 多因子→XGBoost+SHAP→LLM认知
├── risk/
│   └── manager.py         # 风控(单票上限+行业偏离)
├── evolution/
│   └── evolver.py         # Rank IC + IR最大化权重优化
└── interface/
    ├── cli.py             # CLI(-d/-b/-p1/-p2/-mf/-c/-f/-t)
    └── app.py             # Streamlit Web(5标签页)

logs/                      # 按天轮转日志文件
data/
├── stock_agent.duckdb     # DuckDB数据库
└── chroma_db/             # ChromaDB向量存储
```

---

## 每日选股流程(7步)

| 步骤 | 内容 | 说明 |
|------|------|------|
| 1/7 | 数据采集 | Tushare日线/复权 + baostock交易日历 |
| 2/7 | 因子计算 | 143个因子 + 行业中性化(110行业) + MAD去极值 + Z-Score |
| 3/7 | 舆情分析 | 阿里百炼LLM新闻情感分析(如有新闻) |
| 4/7 | 情景记忆 | 市场快照embedding存储到ChromaDB |
| 5/7 | 三层推理 | 多因子打分 → XGBoost+SHAP精选 → LLM认知决策 |
| 6/7 | 风控校验 | 单票上限+行业偏离硬约束 |
| 7/7 | 绩效评估 | 事后N日收益记录 + 自动进化 |

---

## 初筛规则

因子计算后、推理前执行粗筛，剔除不合格标的：

| 规则 | 标准 | 数据来源 |
|------|------|----------|
| 剔除ST | 股票名含"ST" | `stock_basic.name` |
| 剔除高价股 | close > 150元 | `daily_price.close` |
| 剔除北交所小盘 | 市值 < 30亿(或股价 < 10元) | `daily_basic.total_mv` / `daily_price.close` |
| 剔除持续亏损 | 近5年年报净利润为负 >= 3年 | `financials.net_profit` |
| 剔除高危行业 | 房地产/纺织/造纸/影视 | `stock_basic.industry` |

所有参数可在 `config/settings.yaml` 的 `risk` 段配置。

---

## 数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| 日线行情 | Tushare `daily` | 120积分免费 |
| 复权因子 | Tushare `adj_factor` | 120积分免费 |
| 行业分类 | akshare 东方财富 | 免费，一次持久化到DB |
| 交易日历 | baostock | 免费，按年同步持久化 |
| 资金流向 | baostock 5分钟线估算 | 免费，近似度约85% |
| 年报/季报 | akshare 东方财富 | 免费，5年×4期持久化 |
| LLM | 阿里百炼(DashScope) | qwen-plus/qwen-turbo |

**Tushare 120积分不可用的接口**：`daily_basic`、`income`、`forecast` 等，均已用 baostock/akshare 替代。

---

## 核心配置参数

`config/settings.yaml` 关键参数：

```yaml
risk:
  max_single_weight: 0.10       # 单票权重上限
  industry_deviation: 0.05      # 行业偏离上限
  max_price: 150.0              # 剔除高价股阈值
  bj_min_market_cap: 30.0       # 北交所最小市值(亿)
  bj_min_price: 10.0            # 北交所最小股价(降级用)
  exclude_st: true              # 剔除ST
  loss_lookback_years: 5        # 亏损回看年数
  loss_min_years: 3             # 亏损年数阈值
  excluded_industries:           # 行业黑名单
    - 房地产
    - 纺织制造
    - 造纸
    - 影视

reasoning:
  layer1_top_pct: 0.20          # 第一层候选比例
  layer2_top_n: 50              # 第二层精选数量
  layer3_final_n: 20            # 第三层最终持仓数

evolution:
  frequency: monthly            # 进化频率
  ic_window_months: 3           # IC计算窗口
```

---

## DuckDB 数据库(12张表)

| 表名 | 说明 |
|------|------|
| daily_price | 日线行情 |
| adj_factor | 复权因子 |
| financials | 年报/季报财务数据 |
| money_flow | 资金流向 |
| news_tags | 新闻标签 |
| factors_daily | 因子日截面 |
| market_state_snapshot | 市场快照 |
| decisions | 选股决策 |
| decision_performance | 决策绩效 |
| factor_weights_history | 因子权重历史 |
| trade_calendar | 交易日历 |
| stock_basic | 股票基本信息(含行业) |

---

## 注意事项

- **numpy 冲突**：若遇到 numpy 版本冲突，使用 `python -s` 运行或 `set PYTHONNOUSERSITE=1`
- **Tushare 限频**：`stock_basic` 接口1次/小时，行业数据已持久化到DB，无需重复调用
- **baostock 网络**：偶尔连接失败，交易日历按年持久化后不影响运行
- **LLM 超时**：读取超时由 DashScope 服务端控制，本地仅设 connect 超时(15秒)
- **日志**：终端输出 + `logs/stock_agent_YYYY-MM-DD.log` 文件双写
- **Windows Console**：长时间大量输出偶尔卡住，按 Esc 恢复
