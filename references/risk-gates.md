# 光储充风险闸门

| 标志 | 含义 | 默认处置 |
|---|---|---|
| `INVALID_INPUT` | 输入缺失、越界或年度数组错误 | 阻断并修复 |
| `ENERGY_BALANCE_BROKEN` | 能量来源和去向不守恒 | 阻断 |
| `CHARGING_CAPACITY_EXCEEDED` | 预测充电量超过功率、在线率和时间上限 | 重建负荷 |
| `STORAGE_DISPATCH_INFEASIBLE` | 循环、能量或需求不能支持储能放电 | 重建调度 |
| `UNVERIFIED_ANCILLARY_REVENUE` | 需求响应/VPP/补贴无资格或结算 | 基准剔除 |
| `BASE_PROJECT_NPV_NEGATIVE` | 基准项目NPV低于0 | 原则上不满足投资门槛 |
| `NEGATIVE_CFADS_IN_BASE` | 基准期出现负CFADS | 阻断或落实补足 |
| `BASE_DSCR_BELOW_THRESHOLD` | 基准DSCR低于审批阈值 | 重构融资 |
| `P90_DSCR_BELOW_1` | P90任一期不能覆盖本息 | 阻断现有融资结构 |
| `SITE_TERM_SHORTER_THAN_FINANCING` | 场地期限短于融资期 | 阻断至续期落实 |
| `PAYBACK_NOT_WITHIN_SITE_TERM` | 回收期超出场地期限 | 不接受远期价值 |
| `REPLACEMENT_CAPEX_MISSING` | 长周期未列储能/逆变器/充电模块更新 | 暂缓 |
| `LOAD_DATA_UNVERIFIED` | 无后台、计量、账单和流水交叉验证 | 低置信度/暂缓 |

多项同时触发时取最保守结论。黄色问题必须列责任人、期限和转绿标准。
