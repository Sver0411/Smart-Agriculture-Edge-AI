# Smart Agriculture Edge AI v0.3

**Software Integration & Experimental Foundation**

完整的分布式智慧农业软件系统：可信感知、自适应采样、可切换的边缘决策、安全控制、网关接管、离线历史回放和可执行故障实验。所有七个角色可以在单台电脑上运行，运行时仅依赖 Python 标准库。

```text
                         Server
                      ↗          ↖
                    A1  ←──────→  A2
                   /  \          /  \
                 B1   C1       B2   C2
```

A1/A2 是边缘网关，B1/B2 是传感器节点，C1/C2 是同一区域的控制节点。B 与 C 并列；B1 的数据始终控制 C1，故障接管后也保持这个区域关系。Server、Controller 和网关可靠性机制均保留在本仓库。

## 数据与控制链路

```text
SensorSource → SensorTrust → AdaptiveSense → SENSOR_DATA / ALERT
                                               ↓
Gateway: quality gate → DecisionEngine → CONTROL_COMMAND
                                               ↓
Controller: ACK → SafetyGuard → simulated execution → CONTROL_RESULT
                                               ↓
Gateway: live upload / SQLite OfflineQueue → Server: atomic dedup + history
```

- **SensorTrust**：每个通道独立维护 RANGE、STUCK、SPIKE、DRIFT、MISSING 状态，输出 health_score、fault_flags 和 HEALTHY/DEGRADED/FAULT。DRIFT 使用每秒变化率。有效性与检测分数分开，MISSING 确认前的无效读数同样禁止控制。
- **数据可信边界**：HEALTHY 且有效的数据可进入决策；DEGRADED/FAULT 保存历史并产生 ALERT，自动控制被阻止。这是当前保守策略。状态不是经过校准的故障概率，也不能证明传感器物理损坏。
- **AdaptiveSense**：复用归一化 EMA/STD/ROC 评分和 STABLE/ACTIVE/ALERT 状态机，立即升级、逐级降级、滞回和分级周期；首次采样、状态/周期变化、事件、数据变化、上传心跳可触发上传。异常读数不进入变化评分，恢复后重建基线。
- **采样与保活**：默认 STABLE `[20,40,60]` 秒，ACTIVE `[15,10,5]` 秒，ALERT `[5]` 秒。SensorNode 的 socket RX、NODE_STATUS 保活和采样分别运行；保活周期不随采样周期变化。demo/实验使用明确配置的加速周期。
- **DecisionEngine**：Rule、Logistic、Tree、MLP 共用 `predict(sample, policy)`。Rule 为默认；其他模型是固定 seed 的合成策略模仿参考，供训练/导出/切换验证，尚不是经过真实农业数据验证的控制模型。特征顺序与版本在 `ai/features.py` 固定。

## 可靠性与安全

- B/C 注册后取得 owner/generation；SensorNode 和 Controller 都接收网关 NODE_STATUS 更新，并拒绝不一致来源和过期 generation。
- 网关节点 liveness 的 `last_seen` 来自本机接收时间。客户端时间戳不决定节点是否在线。
- CONTROL_COMMAND 使用稳定 message_id/command_id、有限 ACK 重试和幂等控制器。重试 attempt 递增，逻辑消息身份保持不变。
- ACK 只确认收到；CONTROL_RESULT 表示执行结果。ACK 后结果超时记为 UNKNOWN，产生告警；迟到结果可补全状态，不通过再次执行修复丢失结果。
- Controller 串行处理命令，SafetyGuard 检查类型、command_id、TTL、generation、owner、重复、duration 上限和 cooldown；并发重复命令只执行一次。
- 网关心跳超时触发 takeover 和 generation 增长；恢复的旧网关进入 STANDBY，无自动切回。
- 离线消息按 FIFO 分批完整回放，保留 ID；发送失败只保留未成功发送的部分；Server 重连主动触发回放。
- 服务器的去重记录和业务历史写入同一 SQLite 事务，拒绝的上传不消耗其去重身份。
- `SERVER_POLICY` 使用版本校验和原子参数验证；ACK 是 receipt acknowledgement，Server 不提供基于 ACK 的策略重试保证。

### 协议兼容

TCP 上使用逐行 JSON，原有六字段 envelope 保持兼容：

```json
{"type":"SENSOR_DATA","source":"B1","target":"A1","timestamp":1234567890.0,"message_id":"sample-001","payload":{}}
```

可选字段为 `protocol_version:1`、`sequence`、`attempt`、`generation`；未携带时按旧协议处理。新模拟传感器使用 boot_id + sequence 区分逻辑采样；重排/重复旧数据可保留用于审计，但不再驱动新控制。解析拒绝非有限数字、错误字段类型、不支持的版本和超长帧。协议不包含身份认证。

## 运行

Python 3.10+：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python demo.py --duration 30
.venv/bin/python -m pytest tests/ -q
```

独立节点 CLI：

```bash
python -m server.server --port 9100 --db server.db
python -m gateway.gateway --id A1 --engine rule
python -m gateway.gateway --id A2 --engine rule
python -m sensor_node.sensor_node --id B1
python -m sensor_node.sensor_node --id B2
python -m controller_node.controller_node --id C1
python -m controller_node.controller_node --id C2
```

demo 保留 normal、failover、server-offline 场景及旧命令/重复命令注入选项。正式实验有独立配置、端口和数据库。

## 配置

`config/software.json` 是软件默认参数源，分 system、node、policy、experiment 四组。`common/settings.py` 验证，`common/config.py` 保留兼容常量；`SMART_AGRICULTURE_CONFIG=/path/config.json` 可为独立进程指定配置。构造器覆盖和实验 runtime_overrides 写入实验配置。未来固件配置需要显式映射/校验；本轮未声称新 Python adapter 与现有固件调度配置完全等价。

## 实验与实际验证

```bash
python -m experiments.runner --all --output results/software-v0.3/my-run
python -m experiments.runner --scenario ack-loss --output results/software-v0.3/ack-loss-run

git clone https://github.com/Sver0411/EdgeFaultLab ../EdgeFaultLab
python -m experiments.edgefaultlab --edgefaultlab-root ../EdgeFaultLab --output results/software-v0.3/efl-run
```

正式复现请将 EdgeFaultLab 检出为 `docs/integration_sources.json` 中的审查版本。它保持独立，主项目只提供配置/CLI/端口适配器。运行失败返回非零退出码。

每个内部实验保存 `config.json`、`manifest.json`、`truth/injection_plan.json`、`raw/events.jsonl`、`results/metrics.json`、`results/summary.json` 和报告。输出目录拒绝覆盖。指标中的 `null / not measured` 与 `0 / observed` 分开；TCP 读取、ACK、执行和持久化也分开记账。

实际运行结果：

- 合并基线 94 个测试通过；最终 155 个测试通过，完整结果见[整合报告](docs/V0_3_INTEGRATION_REPORT.md)。原有测试保留。
- 17/17 内部场景通过：normal、full-control-loop、packet-loss、ack-loss、duplicate-command、delayed-result、lost-result、reordered-messages、sensor-fault、gateway-failover、gateway-recovery、stale-generation、server-offline、queue-replay、policy-replay、split-brain、expired-command。
- 独立 EdgeFaultLab 第二轮 5/5 通过。第一轮 4/5 通过，启动时节点归属分离导致重复命令场景没有执行；失败原始记录保留。
- SensorTrust Python 参考与冻结 C core 的共享五故障/恢复轨迹在主机端一致。
- [CI 验收通过](https://github.com/Sver0411/Smart-Agriculture-Edge-AI/actions/runs/37142688673)：155 个测试、17 个内部场景和 5 个外部场景。
- 三个 FP32 导出在 240 条留出样本上与训练器预测一致；相同 seed 的四个训练/导出文件逐字节复现。
- INT8 权重存储参考：Logistic 有 2/240 条预测与 FP32 不一致，MLP 为 0/240。激活与 bias 保持浮点、推理先反量化，尚无整数内核或设备结果。

新软件能力的验证等级为 **host-tested / software experimentally evaluated**。历史 B1 固件和实验记录保留在 [firmware/b1](firmware/b1/README.md) 与 [results/v0.3](results/v0.3/README.md)，其验证范围独立于本轮。

## 模型软件工具

仅离线训练需要额外依赖，运行节点不需要 sklearn/numpy：

```bash
pip install -r requirements-training.txt
python -m ai.train --seed 42 --output ai/artifacts
python -m ai.quantize --output ai/artifacts/int8
python -m ai.benchmark --output model_benchmark.json
```

`ai.train.train(..., rows=feature_label_rows)` 接受外部提供的特征/标签数据，输出标记为 `user-provided-unvalidated`；这是未来数据替换入口。训练/留出划分、数据 hash、seed、特征版本和来源写入模型导出。Logistic 在合成留出集中有 10/240 条策略模仿误差；这是如实保留的负面结果，不是农业效果评估。主机延迟和 JSON 字节数不能当作 MCU 延迟、flash 或能耗。

## 当前限制

- OfflineQueue 仍以 TCP write/drain 成功为删除条件，尚无 Server 持久化 ACK；进程/连接边界上可能丢失已经从本地删除、但尚未持久化的上传。
- 网关 epoch、控制器幂等状态和未知结果记录仍在内存中，跨进程重启没有持久化 exactly-once 保证。
- 双网关 heartbeat 与 owner/generation 检查不构成共识协议。split-brain 场景验证的是过期 generation 和同 epoch 非 owner 拒绝，不能证明任意网络分区下的独占控制。
- STUCK 无法区分真正恒定环境与冻结传感器；DRIFT 也可能来自真实持续环境变化。DEGRADED 禁止控制有可用性代价。
- telemetry 仍是尽力传输；sequence 防旧数据控制，不提供传感器端持久化/重传。
- 无认证、加密、跨节点时钟同步和部署配置校准。CONTROL_COMMAND 时间戳仍要求 Unix wall clock，用于 TTL。
- 模型只验证软件流程，INT8 只验证权重存储参考；完整 C 推理/config parity、真实数据效果、设备资源和能耗未测量。

## 文档与下一阶段

[代码级设计审计](docs/V0_3_INTEGRATION_REVIEW.md) · [整合报告与复现记录](docs/V0_3_INTEGRATION_REPORT.md) · [复用来源](docs/integration_sources.json)

下一阶段优先补持久化 receipt/epoch/idempotency 边界，确定农业数据与故障配置，再建立固件配置与算法 parity。完整拓扑始终保留。

MIT。直接复用的 AdaptiveSense Python 文件保留其 MIT 许可证与来源记录。
