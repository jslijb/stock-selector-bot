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
| `DASHSCOPE_API_KEY` | 阿里百炼 API Key（或 MiniMax 等其他兼容 OpenAI 接口的 Key） | [阿里百炼](https://bailian.console.aliyun.com/) |

**Windows（PowerShell）：**
```powershell
$env:TUSHARE_TOKEN="你的token"
$env:DASHSCOPE_API_KEY="你的key"
```

**Windows（CMD）：**
```cmd
set TUSHARE_TOKEN=你的token
set DASHSCOPE_API_KEY="你的key"
```

### 3. LLM 配置（热加载）

编辑 `config/llm_config.yaml`，修改后自动生效（每 5 秒检测），无需重启。

可选决策模型：`qwen-plus`(推荐)、`qwen-turbo`、`qwen-max`、`deepseek-v3`、`MiniMax-M2.5`
可选舆情模型：同上，推荐轻量模型节省成本。

API Key 优先级：`llm_config.yaml` 中的 `api_key` > 环境变量 `DASHSCOPE_API_KEY`

### 4. Embedding 模型

首次运行自动下载 `BAAI/bge-large-zh-v1.5`(~1.3GB)，CPU 推理约 50ms/条。

---

## 使用方法

### 快速开始（首次使用）

推荐按以下顺序初始化数据：

```bash
# 第0步（必须）：缓存股本数据 + 计算每日指标(PE/PB/市值等)
python main.py -db 20240101 20260430

# 第一阶段：采集日线+复权数据（~3秒/天，约30分钟/2年）
python main.py -p1 20240101 20260430

# 第二阶段：因子计算 + 选股决策 + 风控 + 进化（约2-3小时/2年）
python main.py -p2 20240101 20260430

# 补跑资金流向（可选，baostock 5分钟线估算，可多线程加速）
python main.py -mf 20240101 20260430
```

> **注意**：`-db` 必须在 `-p2` 之前运行，因为 `-p2` 的因子计算依赖 `daily_basic` 表中的 PE/PB/市值数据。

### 每日选股

```bash
python main.py
```

等价于 `python main.py -d 20260506`（指定日期）

### 全部命令

```bash
python main.py                           # 当日选股
python main.py -d 20260505               # 指定日期选股

python main.py -db 20250101 20260506     # 补跑每日指标(PE/PB/市值/换手率)
python main.py -p1 20250101 20260506     # 第一阶段：仅采集日线+复权数据
python main.py -p2 20250101 20260506     # 第二阶段：因子计算+选股+风控+进化
python main.py -p2 20250101 20260506 -f  # 第二阶段：强制重跑（覆盖已有决策）
python main.py -mf 20250101 20260506     # 补跑资金流向

python main.py -b 20250101 20260506      # 全量补跑（完整7步，每步独立）
python main.py -c 20250101 20260506      # 检查缺失日期（行情/因子/决策）
python main.py -t 15:30                  # 定时模式（每日15:30自动运行）
```

### 数据就绪检查

```bash
python main.py -c 20240101 20260430
```

输出示例：
```
交易日: 587 天
缺失行情: 3 天  [20240102, 20240103, 20240104]
缺失因子: 12 天  [20240102, 20240103, ...]
缺失决策: 15 天  [20240102, 20240103, ...]
```

---

## 日志系统

所有运行日志自动写入 `logs/` 目录：

| 日志文件 | 说明 | 轮转策略 |
|----------|------|----------|
| `stock_agent_YYYY-MM-DD.log` | 每日完整日志(DEBUG级别) | 按天 |
| `errors.log` | 错误日志(ERROR级别) | 10MB |
| `trace.log` | 全量追踪日志(TRACE级别) | 50MB |

终端输出：仅显示 WARNING 及以上级别，避免刷屏。
日志**永不过期**，后期手动清理。

当日志中出现异常时，完整调用栈会自动记录到日志文件和 `errors.log`，便于排查。

---

## 每日选股流程（7步）

| 步骤 | 内容 | 说明 |
|------|------|------|
| 1/7 | 数据采集 | Tushare日线/复权 + baostock交易日历 |
| 2/7 | 因子计算 | 150个因子 + 行业中性化 + MAD去极值 + Z-Score |
| 3/7 | 舆情分析 | 阿里百炼LLM新闻情感分析（如有新闻） |
| 4/7 | 情景记忆 | 市场快照 Embedding 存储到 ChromaDB |
| 5/7 | 三层推理 | 多因子打分 → XGBoost+SHAP精选 → LLM认知决策 |
| 6/7 | 风控校验 | 单票上限 + 行业偏离硬约束 |
| 7/7 | 绩效评估 | 事后1/3/5/10/20日收益记录 + 自动进化（每月） |

---

## 初筛规则

因子计算后、推理前执行粗筛，剔除不合格标的。所有参数可在 `config/settings.yaml` 的 `risk` 段配置。

| 规则 | 参数 | 默认值 | 数据来源 |
|------|------|--------|----------|
| 剔除ST股 | `exclude_st` | `true` | `stock_basic.name` |
| 剔除高价股 | `max_price` | 100元 | `daily_price.close` |
| 剔除小市值 | `min_market_cap` | 20亿 | `daily_basic.total_mv` |
| 剔除低换手 | `min_turnover_rate` | 2% | `daily_basic.turnover_rate` |
| 剔除低成交额 | `min_avg_amount` | 5000万 | `daily_price.amount` |
| 剔除低营收 | `min_revenue` | 5亿 | `financials.total_revenue` |
| 剔除负净资产 | — | — | `financials.total_hldr_eqy` |
| 非周期性行业PE上限 | `max_pe_noncyclical` | 50倍 | `daily_basic.pe_ttm` |
| 周期性行业负债上限 | `cyclical_max_debt_ratio` | 70% | `financials` |
| 非周期性行业亏损剔除 | — | 净利润≤0剔除 | `financials.net_profit` |
| 行业黑名单 | `excluded_industries` | 房地产/纺织/影视等 | `stock_basic.industry` |
| 北交所（默认关闭） | `enable_bj` | `false` | `daily_basic` |
| 科创板（默认关闭） | `enable_kcb` | `false` | `daily_basic` |
| 北交所最小市值 | `bj_min_market_cap` | 10亿 | `daily_basic` |
| 科创板最小市值 | `kcb_min_market_cap` | 15亿 | `daily_basic` |

### 周期性行业定义

以下行业视为周期性行业，适用负债比率限制：

`煤炭`、`石油石化`、`有色金属`、`贵金属`、`小金属`、`钢铁`、`基础化工`、`建筑材料`、`水泥`、`玻璃玻纤`、`工程机械`、`通用设备`、`轨交设备`、`电网设备`、`锂电`、`汽车`、`乘用车`、`家电`、`航运`、`航空`、`船舶制造`、`证券`、`保险`

### 行业黑名单

以下行业默认被剔除：

`房地产`、`房地产开发`、`房地产服务`、`纺织制造`、`服装`、`影视`、`院线`

---

## 数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| 日线行情 | Tushare `daily` | 120积分免费 |
| 复权因子 | Tushare `adj_factor` | 120积分免费 |
| 每日指标(PE/PB/市值) | baostock + 本地计算 | 免费，`-db` 命令执行 |
| 行业分类 | Tushare `stock_basic` | 120积分，一次持久化到DB |
| 交易日历 | baostock + daily_price推断 | 免费，按年同步持久化 |
| 资金流向 | baostock 5分钟线估算 | 免费，多线程加速，近似度约85% |
| 年报/季报 | Tushare `income_vip` | 120积分 |
| LLM | 阿里百炼(DashScope) / MiniMax | 兼容 OpenAI 接口 |

**Tushare 120积分不可用的接口**：`daily_basic` 等，已用本地计算替代（PE/PB/市值等通过 close × 股本 / 财务数据计算）。

---

## 核心配置参数

### `config/settings.yaml`

```yaml
database:
  duckdb_path: "./data/stock_agent.duckdb"

tushare:
  token_env: "TUSHARE_TOKEN"    # 环境变量名
  rate_limit: 200               # 每分钟最大请求数

embedding:
  model_name: "BAAI/bge-large-zh-v1.5"
  device: "cpu"                 # cpu 或 cuda

chromadb:
  persist_dir: "./data/chroma_db"
  collection_name: "market_state_memory"

factors:
  count: 150                    # 因子总数（注册数）
  neutralization: "industry"    # 中性化方法: industry
  extreme_value_method: "mad"   # 去极值方法: mad / percentile
  zscore_window: 252            # Z-Score滚动窗口

reasoning:
  layer1_top_pct: 0.20          # 第一层多因子打分候选比例
  layer2_top_n: 50              # 第二层XGBoost精选数量
  layer3_final_n: 20            # 第三层LLM最终持仓数

risk:
  max_single_weight: 0.10       # 单票权重上限
  industry_deviation: 0.05      # 行业偏离上限
  max_price: 100.0              # 剔除高价股阈值
  min_market_cap: 20.0          # 最小市值(亿)
  min_turnover_rate: 2.0        # 最小换手率(%)
  min_avg_amount: 5000.0        # 最小日成交额(万)
  min_revenue: 5.0              # 最小营收(亿)
  max_pe_noncyclical: 50.0      # 非周期行业PE上限
  exclude_st: true              # 剔除ST
  enable_bj: false              # 启用北交所
  enable_kcb: false             # 启用科创板
  bj_min_market_cap: 10.0       # 北交所最小市值(亿)
  kcb_min_market_cap: 15.0      # 科创板最小市值(亿)
  excluded_industries:          # 行业黑名单
    - 房地产
    - 房地产开发
    - 房地产服务
    - 纺织制造
    - 服装
    - 影视
    - 院线
  cyclical_industries:          # 周期性行业
    - 煤炭
    - 石油石化
    - 有色金属
    - 贵金属
    - 小金属
    - 钢铁
    - 基础化工
    - 建筑材料
    - 水泥
    - 玻璃玻纤
    - 工程机械
    - 通用设备
    - 轨交设备
    - 电网设备
    - 锂电
    - 汽车
    - 乘用车
    - 家电
    - 航运
    - 航空
    - 船舶制造
    - 证券
    - 保险
  cyclical_max_debt_ratio: 70.0   # 周期性行业负债上限(%)

evolution:
  frequency: "monthly"          # 进化频率
  ic_window_months: 3           # IC计算窗口(月)
  weight_bounds: [0.01, 0.30]   # 因子权重范围

scheduler:
  check_missing: true           # 因子计算时使用完整历史数据
  auto_backfill: true           # 自动补跑缺失数据

moneyflow:
  max_workers: 4                # 资金流向采集线程数
  stock_interval: 1.0           # 每只股票间隔秒数(免费接口建议 1.0-3.0)
```

### `config/llm_config.yaml`（热加载）

```yaml
api_key: ""                     # API Key（也可用环境变量）
base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"

decision_model: "qwen-plus"     # 选股决策模型
decision_max_tokens: 4096
decision_temperature: 0.3

sentiment_model: "qwen-turbo"   # 舆情分析模型
sentiment_max_tokens: 1024
sentiment_temperature: 0.1
```

修改后 5 秒内自动生效，无需重启。

---

## 项目架构

```
config/
├── settings.yaml          # 基础配置（数据库/因子/风控/进化/调度）
└── llm_config.yaml        # LLM配置（热加载，每5秒自动检测）

src/
├── config.py              # 配置加载 + 热加载监控(daemon线程)
├── scheduler.py           # 每日调度(7步流程) + 初筛 + 两阶段补跑
├── data/
│   ├── db.py              # DuckDB 连接管理(单例)
│   ├── schema.py          # 12张核心表 + 12条Sequence + stock_basic自动迁移
│   ├── collector.py       # Tushare采集 + baostock日历/资金流向
│   ├── money_flow.py      # baostock 5分钟线资金流向估算(多线程+可配置并发参数)
│   ├── daily_basic_local.py    # PE/PB/市值本地计算(baostock股本 + 财务数据)
│   └── daily_basic_collector.py # baostock每日指标采集(北交所等)
├── factors/
│   ├── engine.py          # 因子引擎(pipeline: 计算→中性化→去极值→Z-Score)
│   ├── registry.py        # 因子注册中心
│   ├── base.py            # 因子基类
│   ├── valuation.py       # 估值因子(15个)
│   ├── quality.py         # 质量因子(20个)
│   ├── growth.py          # 成长因子(15个)
│   ├── momentum.py        # 动量/反转因子(28个)
│   ├── sentiment.py       # 资金/情绪因子(15个)
│   ├── technical.py       # 技术因子(30个)
│   ├── alternative.py     # 另类因子(20个)
│   └── nlp_sentiment.py   # NLP舆情(LLM，兼容OpenAI接口)
├── memory/
│   └── memory.py          # ChromaDB + BGE向量检索(自动降级DuckDB)
├── reasoning/
│   └── engine.py          # 三层推理: 多因子→XGBoost+SHAP→LLM认知(15秒连接超时)
├── risk/
│   └── manager.py         # 风控(单票上限+行业偏离+自动权重归一化)
├── evolution/
│   └── evolver.py         # Rank IC + IR最大化权重优化(月度自动进化)
└── interface/
    ├── cli.py             # CLI入口(-d/-db/-p1/-p2/-mf/-b/-c/-f/-t)
    └── app.py             # Streamlit Web界面(5标签页)

logs/                      # 日志目录(按天/错误/追踪三级)
data/
├── stock_agent.duckdb     # DuckDB数据库(单文件)
└── chroma_db/             # ChromaDB向量存储

scripts/                   # 调试/验证脚本
├── check_data_coverage.py
├── check_db_data.py
├── test_baostock_basic.py
└── ...
```

---

## DuckDB 数据库（13张表）

| 表名 | 主键 | 说明 |
|------|------|------|
| `daily_price` | ts_code + trade_date | 日线行情(open/high/low/close/vol/amount) |
| `adj_factor` | ts_code + trade_date | 复权因子 |
| `daily_basic` | ts_code + trade_date | 每日指标(PE/PB/PS/市值/换手率/量比) |
| `financials` | ts_code + report_period | 年报/季报财务数据 |
| `money_flow` | ts_code + trade_date | 资金流向(大小单买卖/净流入) |
| `news_tags` | id(auto) | 新闻标签(情感/事件类型/影响分) |
| `factors_daily` | ts_code + trade_date + factor_name | 因子日截面(约150因子 × 5000股) |
| `market_state_snapshot` | snapshot_date | 市场快照(收益率/波动率/宽度) |
| `decisions` | id(auto) | 选股决策(持仓/权重/得分/理由) |
| `decision_performance` | id(auto) | 决策绩效(1/3/5/10/20日收益) |
| `factor_weights_history` | id(auto) | 因子权重历史(IC均值/IR/审批状态) |
| `trade_calendar` | trade_date | 交易日历 |
| `stock_basic` | ts_code | 股票基本信息(名称/行业/总股本/流通股本) |

---

## 三层推理详解

| 层级 | 方法 | 输入 | 输出 |
|------|------|------|------|
| 第一层 | 多因子加权打分 | 150个因子 + 历史IC权重 | Top 20% 候选池 |
| 第二层 | XGBoost回归 + SHAP解释 | 候选池因子值 + 历史训练标签 | Top 50 精选池 + SHAP归因 |
| 第三层 | LLM认知决策 | 精选池 + SHAP归因 + 市场环境 + 历史相似日 | 最终20只持仓 + 权重 + 理由 |

训练数据：近20个交易日，前向5日收益作为标签。样本不足时第二层降级为因子得分。

---

## 因子进化机制

每月自动评估因子表现并优化权重：

1. 取近 3 个月因子日截面数据
2. 计算每个因子的 Rank IC（与次日收益的 Spearman 秩相关）
3. 构建 IC 协方差矩阵
4. 使用 SLSQP 优化器最大化 IR（IC/IC_std）
5. 新权重写入 `factor_weights_history`（待审核 → 自动审批）
6. 下次选股自动使用新权重

---

## 常见问题

### Windows PowerShell 运行卡住不动

**已修复**：程序启动时自动禁用 Quick Edit Mode（鼠标点击暂停输出）。
如果仍然卡住，按 `Esc` 恢复。

### numpy 版本冲突

```bash
python -s main.py -d 20260506
```

或 `$env:PYTHONNOUSERSITE=1`

### Tushare 限频

`stock_basic` 接口 1次/小时，行业数据已持久化到 DB，无需重复调用。

### Baostock 连接失败

交易日历按年持久化，偶尔连接失败不影响运行。股本数据获取失败时会自动跳过并记录警告。

### 资金流向采集过慢

`-mf` 使用多线程采集，可在 `config/settings.yaml` 的 `moneyflow` 段调整：

```yaml
moneyflow:
  max_workers: 2              # 降低线程数减少 baostock 压力
  stock_interval: 2.0         # 增大间隔避免触发限频
```

默认参数（4线程 + 1.0秒/只）在 baostock 免费接口上约 90% 成功率。如失败率过高，建议降至 2线程 + 2.0秒/只。

### LLM 超时

connect 超时 15 秒，read 无超时（由服务端控制）。长时间无响应属于 LLM 服务端问题。

### LLM 额度耗尽

如果 LLM API Key 额度耗尽，`-p2` 阶段会报 403 错误。解决方案：
1. 切换模型到 `qwen-plus` 或 `qwen-turbo`（阿里百炼新账号有免费额度）
2. 充值当前服务商
3. 不配置 LLM Key，系统会降级为纯 ML 选股

### 数据不足

因子最大回溯窗口 252 交易日（约 1 年），推荐补跑 2-3 年数据以获得稳定的因子表现。

---

## 注意事项

- **首次运行顺序**：务必先 `-db`（缓存股本+计算PE/PB），再 `-p1`（采集行情），最后 `-p2`（因子+选股）
- **VPN/代理**：Tushare 和 baostock 可能需要网络畅通
- **磁盘空间**：DuckDB 约 2-5GB（2年数据），ChromaDB 约 500MB
- **内存**：ChromaDB + BGE 模型约需 2-4GB RAM
- **日志清理**：日志永不过期，建议定期手动清理 `logs/` 目录
- **数据库备份**：直接复制 `data/stock_agent.duckdb` 文件即可
- **LLM 依赖**：`-p2` 和每日 `-d` 命令需要 LLM，`-db` 和 `-p1` 不需要