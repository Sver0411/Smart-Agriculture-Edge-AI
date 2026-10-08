# Phase 1.1 软件验证证据

- validation/baseline.log：重新运行第一阶段基线，363 passed。
- validation/*before.log：缺陷复现失败，保留原失败条件。
- validation/full-initial.log：首次全量 374 passed/1 failed，实验测量结束窗口缺陷。
- validation/full-verified.log：最终本地 378 passed/0 failed。
- validation/retry-observations.log：一小时虚拟离线 11 次尝试（6 次 probe）及 20000 次随机状态交错。
- scenarios/ 与 scenarios-final/：两个不同开发快照的 20 个本地系统实验，未覆盖历史文件。
- edgefaultlab/：本地独立进程外部 5 场景及原始证据。
- ci-software-110295e.tar.gz：GitHub Actions 精确代码版本 110295e 的 20+5 场景原始证据；解压至新的临时目录阅读，SQLite 二进制文件省略，hash 见 validation/ci-software-archive.json。
- ci-firmware-*：首次 GitHub 容器构建下载的日志。首次 manifest 路径问题已修复并另行跑 CI，最终运行 37768007288 全部通过；ci-firmware-final-* 各包含四个预期文件，未覆盖首次归档。
- validation/firmware-*-manifest.json 与 size.log：本地公开合成配置的完整网络路径构建证据。
- validation/source_manifest.json：源码 SHA256 与验证边界；GitHub 状态与完整日志另存于 validation。

所有结果是 Host/模拟/编译证据，没有实体掉电、电流、射频或执行器实验。before/initial 的失败用于缺陷定位；最终结果必须以完整回归和相应 CI 状态为准。
