# Branch Integration Review

日期：2026-10-08。审查前远端主线：`f56b857`。整合与修复的源码提交：`f204ad9`。

## 分支审查

审查全部本地分支及 `git ls-remote --heads origin` 列出的全部远端分支，并执行 `git fetch origin --prune`。逐一以 `origin/main` 为基线检查可达提交；机器记录见 [branch inventory](../results/main-integration-review/validation/branch-inventory.json)。另一份 v0.2.1 worktree 没有未提交改动。

| 分支 | 审查前状态 | 整合结论 |
|---|---|---|
| `main` | 本地与远端均为 `f56b857` | 主线基线 |
| `v0.2.1-protocol-hardening` | 本地/远端 `4e320f9`，全部已在 main | 保留协议硬化历史，不重复合并 |
| `v0.3-physical-b1` | 本地/远端 `5a01dcd`，全部已在 main | 保留历史硬件证据，不重新运行硬件 |
| `v0.3-software-integration` | 本地 `20ceb6f`、远端 `79a5c5a`，均已在 main | 本地显示 ahead 的报告提交已在远端主线 |
| `v0.3.1-reliability-hardening` | 本地 `bc83741`、远端 `e9cf7a5`，均已在 main | 本地 ahead 的两个提交已在远端主线 |
| 旧本地 `codex/deployment-semantics` 指针 | 与 main 相同，没有独有提交或远端分支 | 没有待整合代码 |
| `feature/deployment-semantics` | 本地/远端 `a60c5d1`，比 main 新两个提交 | 整合 `bdc50f9` 的软件/固件代码与 `a60c5d1` 的完整实验记录 |
| `feature/main-integration-review` | 从上述开发线建立 | 增加合并前修复和本报告，再推进 main |

保留已有提交历史；整合不使用 squash、reset 或强制推送。既有分支保留供追溯。

## 代码与集成边界

- 配置：simulation/lab/deployment 分离，共享 JSON 生成 B1 C profile，并由 parity 测试检查一致性。
- B：SensorTrust 与 AdaptiveSense 仍分离；可信通道的控制相关 crossing 触发上传；业务 payload、传输 adapter 和 host duty-cycle 模型分离。故障读数不会污染环境变化评分。
- A：策略/ownership checkpoint；恢复先 STANDBY，peer evidence 或正式 timeout 推进恢复；Cloud 回执与本地入队分离；有界 outbox 与 HIGH 容量保留，不驱逐未确认记录，FIFO/PERSISTED_ACK/dedup 保留。
- C：epoch 与 command INTENT 在模拟执行前持久化，完成结果随后持久化；未知结果与重复抑制不包装为跨重启 exactly-once。
- Server：兼容 SQLite schema migration，保存 Gateway metadata；事务提交后确认和业务校验保持。
- 协议：兼容既有 TCP envelope；Zone/freshness 是独立 host contract，没有引入未实现的 E220 wire protocol。
- 实验：固定 B1→C1、B2→C2 的 Zone 映射，接管后 A2 必须实际驱动两 Zone；Cloud 恢复用有界持久化完成检查，不依赖固定主机吞吐假设。

完整 `Server / A1 / A2 / B1 / B2 / C1 / C2` 架构和 README 图保留。Server、Controller、heartbeat 仍在主仓库；未新增消息队列、微服务或前端工程。

## 审查发现并修复

1. **关键 checkpoint 回退**：查询只按 slot 排序但不保留 slot identity，slot 0 丢失后会把旧 slot 1 当成当前值，可能忘记更新后的 epoch 或 INTENT。现显式限定 slot：epoch/recent command 不允许回退；policy 仍可显式恢复前一有效 slot。
2. **运行时命令 ID 无限增长**：durable recent window 有界，SafetyGuard 的活跃进程集合原先没有同步驱逐。现仅在新的 INTENT 成功持久化后，移除已被窗口合法驱逐的 completed IDs；未完成 INTENT 和失败准入不会丢失保护。
3. **回放间隔漏校验**：profile load 原先允许负数、NaN、Infinity、布尔值及字符串。现要求 finite nonnegative number；simulation 的 0 间隔继续合法。

新增 [13 项回归测试](../tests/test_branch_integration_review.py)，覆盖真实 Controller/Gateway 重启的 fail-closed 行为、策略显式回退、运行时窗口和非法配置。修改前为 **11 failed / 2 passed**，日志保留于 [review-before-fixes](../results/main-integration-review/validation/review-before-fixes.log)。原有 337 项测试全部保留。

## 本轮实际验证

| 命令 | 结果 | 证据 |
|---|---|---|
| `.venv/bin/python -m pytest tests/ -q`，Python 3.14.7 | 350 passed，44.36s | [log](../results/main-integration-review/validation/full-local.log) |
| `uv run --python 3.10 --with 'pytest>=7' python -m pytest tests/ -q` | 350 passed，43.32s | [log](../results/main-integration-review/validation/python310.log) |
| `uv run --python 3.12 --with 'pytest>=7' python -m pytest tests/ -q` | 350 passed，42.49s | [log](../results/main-integration-review/validation/python312.log) |
| `uv run --python 3.12 --with 'pytest>=7' python -m experiments.runner --all --output results/main-integration-review/software-scenarios` | 20/20 PASS，退出码 0 | [summary](../results/main-integration-review/software-scenarios/suite_summary.json)、[log](../results/main-integration-review/validation/software_scenarios.log) |
| `uv run --python 3.12 --with 'pytest>=7' python -m experiments.edgefaultlab --edgefaultlab-root .external/edgefaultlab --output results/main-integration-review/edgefaultlab` | 5/5 PASS，退出码 0 | [summary](../results/main-integration-review/edgefaultlab/suite_summary.json)、[log](../results/main-integration-review/validation/edgefaultlab.log) |

Python 版本为 3.10.21 / 3.12.14 / 3.14.7。完整执行参数、进程耗时和退出码见 [acceptance.json](../results/main-integration-review/validation/acceptance.json)，机器验收汇总见 [summary](../results/main-integration-review/validation/summary.json)。

内部实际运行：normal、full-control-loop、packet-loss、ack-loss、duplicate-command、delayed-result、lost-result、reordered-messages、sensor-fault、gateway-failover、gateway-recovery、stale-generation、server-offline、queue-replay、policy-replay、split-brain、expired-command、registration-race、persisted-ack-loss、controller-unavailable。独立 EdgeFaultLab 实际运行：gateway_failover、server_outage、duplicate_control_command、stale_command、lost_command。每个场景保存配置、raw events 和可判断 PASS/FAIL 的断言结果。

源码 SHA-256、tested source commit、seed42 和外部 EdgeFaultLab revision 见 [source manifest](../results/main-integration-review/validation/source-manifest.json)。EdgeFaultLab 固定在 `c7248239f456cc877114ca1e67c5949fb4a7b958`，与现有 CI 一致。

## Main 与 GitHub CI

主线以 fast-forward 整合到 `002e26a`，已推送 GitHub；所有审查分支均为该主线的祖先，没有遗留独有提交。[GitHub CI 37734482845](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37734482845) 对这一主线提交实际执行并 **全部通过**：Python 3.10/3.12 各 350 项，Python 3.12 的 20 个内部场景与 5 个外部故障场景通过。

远端原始 [run metadata](../results/main-integration-review/validation/main-ci.json) 和 [完整日志](../results/main-integration-review/validation/main-ci.log) 已归档。CI 回执后的提交仅更新报告、验证状态和结果记录；运行源码/配置/测试与 `002e26a` 一致，source manifest 仍可核验，不将后续文档提交描述为一次新的 CI 执行。

## 边界

本轮只有软件测试和软件故障注入，没有烧录、串口、LoRa RF、实物执行器或功耗实验。开发线中 lab/deployment ESP-IDF 编译及此前失败记录保留原日期与范围，不算本轮新硬件结果。

任意网络分区下的共识、整个 checkpoint 文件/flash 丢失的 provisioning 判定、recent 窗口外的永久幂等、Sensor 端持久化重传、损坏 FIFO 首条隔离以及物理磁盘/WAL quota 仍未解决。模型仍是 synthetic software reference，未声称农业精度。下一阶段的 E220/NVS/真实执行器工作保持既有路线。
