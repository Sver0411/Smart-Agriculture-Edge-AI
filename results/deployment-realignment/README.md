# Deployment realignment evidence

2026-10-06，本地 `codex/deployment-semantics` 工作树，基线 `f56b857`。完整说明见 [十项报告](../../docs/DEPLOYMENT_REALIGNMENT_REPORT.md)。本轮没有硬件操作，没有新的远端 CI。

## 最终接受结果

| 运行 | 实际结果 | 证据 |
|---|---|---|
| Python 3.14.7 `.venv/bin/python -m pytest tests/ -q` | 298 passed，42.48s | [log](validation/acceptance-python314-sequential.log) |
| Python 3.10.21 `uv run --python 3.10 --with 'pytest>=7' python -m pytest tests/ -q` | 298 passed，41.77s | [log](validation/acceptance-python310-sequential.log) |
| `.venv/bin/python -m experiments.runner --all --output results/deployment-realignment/scenarios-acceptance` | 20/20 PASS | [summary](scenarios-acceptance/suite_summary.json)、[raw console](validation/scenarios-acceptance.log) |
| ESP-IDF5.4.4 ESP32-S3 lab | Build PASS，未 flash | [log](validation/firmware-lab-acceptance.log) |
| ESP-IDF5.4.4 deployment+PM+tickless+light sleep | Build PASS，未 flash | [log](validation/firmware-low-power-acceptance.log) |
| 稳定物理 B1 C host trace | 100 samples；simulation/lab/deployment sink calls 10/3/2 | [counts](validation/stable-upload-counts.json) |
| 独立 EdgeFaultLab | 本轮 NOT RUN，clone GitHub443 失败 | [failure](validation/external-unavailable.log) |

[机器汇总](validation/summary.json) 与 [source manifest](validation/manifest.json) 保存最终结果和代码配置 SHA-256。最终测试覆盖原231项+新增50项parity+17项deployment semantics。parity 测试编译实际 C scheduler / B1 policy / queue / telemetry，cJSON/FreeRTOS 是 host 桩；sink 调用不证明真实 JSON 序列化、TCP/RF 交付或功耗。

`scenarios-acceptance/` 每个场景均含 config、manifest、raw/events、truth/injection_plan、metrics、summary、report。SQLite 数据库仅是本地运行产物，被现有 `.gitignore` 排除；JSON/日志证据可随仓库保存。场景使用随机端口和模拟 source/actuator，不能计为硬件接管验证。

## 编译复现

先激活 IDF 对应 Python3.13 环境，再 source IDF export。使用独立 SDKCONFIG，避免复用本地 ignored Wi-Fi 配置；本轮未读取、拷贝或提交凭据。

```bash
source /Users/mac/.espressif/python_env/idf5.4_py3.13_env/bin/activate
source /Users/mac/esp/esp-idf/export.sh
cd firmware/b1
idf.py -B /tmp/sa-realignment-b1-build \
  -D SDKCONFIG=/tmp/sa-realignment-b1-sdkconfig build
```

默认 Kconfig 为 lab。第二配置 defaults 文件包含 `CONFIG_B1_DEPLOYMENT_MODE=y`、`CONFIG_PM_ENABLE=y`、`CONFIG_FREERTOS_USE_TICKLESS_IDLE=y`、`CONFIG_B1_LIGHT_SLEEP=y`：

```bash
idf.py -B /tmp/sa-realignment-b1-low-power-build \
  -D SDKCONFIG=/tmp/sa-realignment-b1-low-power-sdkconfig \
  -D SDKCONFIG_DEFAULTS='sdkconfig.defaults;/tmp/sa-realignment-low-power.defaults' build
```

部署采样值从 JSON 生成，不从临时 SDKCONFIG 读取。修改 profile 后先 `python scripts/generate_b1_profiles.py`；`--check`/全量测试会拒绝过期 header。`sdkconfig.defaults` 只含 target/stack；首次复现可用新的临时路径，不覆盖任何设备配置。

## 过程证据和失败保留

- `baseline.log`：修改前231 passed；`initial-regression.log`：核心修改后旧231项通过。
- `upload-parity-initial.log`：3失败/22通过，fault signature 变化断言不正确；修正测试后25通过，扩展四通道后50通过。
- `full-suite.log` / `scenarios/`：新增 Zone 实验断言漏 `config` import 失败；补齐后 `full-suite-final.log` / `scenarios-final/` 通过。
- `python310.log`、`final-python*.log`：中间阶段295/297项通过，随后继续补回归到298项。
- `acceptance-python314.log` / `acceptance-python310.log`：并行两套 pytest 竞争固定9201/9202端口，9/7失败；最终两套 sequential 日志各298通过。
- 其他 build/new-tests/parity 日志是中间检查，不能代替上表最新验收。

没有 LoRa、电流、电池寿命、农业准确率或实物 failover 新结果。历史 HW1/CI/external 结果保持原日期和范围，不转用为本轮证据。
