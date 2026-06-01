# ts-data 评测机制

两层评测，对应方案 Part D。

## 1. 静态断言（进 CI，无需 token / API）

```bash
pytest tests/test_routing_map.py tests/test_envelope_contract.py tests/test_error_contract.py -q
```

- `test_routing_map.py` —— ROUTING_MAP 完整性：key 都是真实工具、无悬空边、实体类型合法、codes 生产者有下游消费者、param_from 路径可解析。
- `test_envelope_contract.py` —— 返回信封 schema + 错误带 hint + 枚举回显 valid_values + 向后兼容键集 + 所有错误码有 message。
- `test_error_contract.py` —— 枚举非法 → `invalid_enum` + `valid_values`（前置校验，不依赖 API）；deprecated facade 描述带 `[DEPRECATED→...]` 标记。

## 2. LLM 路由评测（需 ANTHROPIC_API_KEY，CI 默认不跑）

测两个直击改造价值的指标：
- **路由首选命中率**：给 LLM 工具目录 + 自然语言任务，看它选的第一个工具是否落在期望集合（衡量工具命名/描述清晰度 —— PR3 改名、PR4 拆分的收益）。
- **报错自纠命中率**：给 LLM 带 hint 的错误返回，看它能否据 hint 选对恢复工具（衡量 PR1/PR2 error+hint 的价值）。

```bash
export ANTHROPIC_API_KEY=...
python tests/eval/run_llm_eval.py --label after        # 当前分支
```

### A/B 对比（基线 vs 改造后）

在两个 git checkout 各跑一次，对比 scorecard：

```bash
# 改造后
python tests/eval/run_llm_eval.py --label after

# 基线
git stash && git checkout main
python tests/eval/run_llm_eval.py --label before
git checkout - && git stash pop

# 对比 tests/eval/scorecard_before.json vs scorecard_after.json
```

通过门槛：改造后 routing_hit_rate 不低于 before，recovery_hit_rate 应显著高于 before
（基线无 hint，自纠基本靠猜）。

### 用例集

`golden_traces.yaml` —— 9 条种子用例（8 路由 + 1 报错自纠），覆盖个股走势 / 板块龙头 /
市场扫描 / 相关性 / 指数估值 / 财务比率 / 宏观 / 名称误当代码的自纠。新增工具/场景时在此扩充。

> next_steps 运行时注入的正确性由 `test_routing_map.py` 的 attach_* 用例 + 真实 MCP 调用覆盖；
> LLM 评测聚焦"选不选得对工具"这一层。
