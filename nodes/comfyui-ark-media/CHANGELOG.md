# 开发记录

## 1.0.0 — 2026-10-30

- 火山方舟个人Key直连：Seedream图片、Seedance创建任务、Seedance获取视频3节点。
- 图片和视频参考输入、原生IMAGE/VIDEO输出、音轨保留由原生SaveVideo处理。
- 本地提交回执防重复，未确认提交不自动重试，独立任务恢复入口。
- 密钥配置隔离、媒体下载不附带API鉴权、白名单迁移包。
- 默认关闭API调用，18～21示例；无Key阶段仅模拟验收，不产生真实平台调用费用。

## 1.0.0 实机验证 — 2026-11-16

- 负责人实测全部通过：`doubao-seed-2-1-pro-260915` 聊天、`doubao-seedream-5-0-flash-260915` / `doubao-seedream-5-5-261028` 同步生图（2K）、`doubao-seedance-2-5-260628` 视频任务（succeeded，下载 mp4）；插件代码路径端到端验证（core.Client + submit_once + download）。
- 关键口径确认：Seedream 只能走同步 `/images/generations`（异步 tasks 报 `does not support content generation`）；视频走异步 `/contents/generations/tasks` + 轮询；`watermark:false` 可去"AI生成"角标（对外发布需自行补显式标识）；`ratio` 参数名与官方一致，无需改代码。
- 环境事实：本机便携包位于 `E:\RAE_ToolRoot\comfyui\ComfyUI_windows_portable`，启动 `run_nvidia_gpu.bat`（CWD 必须为便携包根目录）；示例工作流 18–21 由 `tools/create_workflows.py` 生成到 `ComfyUI\user\default\workflows`。
- 安全：部署副本 `ark.local.json` 存 Key，不入同步盘；已暴露的 Key 建议轮换（只需改此一处）。

## 纳入统一仓库 — 2026-11-16

- 源码母版迁入 `turingdigiart/ComfyUI_workflows_turingdigiart` 的 `nodes/comfyui-ark-media/`；本地运行时 `custom_nodes/comfyui-ark-media` 改为 junction 指向本仓库，避免双份正文。
- 示例工作流路径更新为仓库内 `workflows/image/ark/`、`workflows/video/ark/`；默认模型标注为 2026-11-16 实机验证（Seedream 5.0-flash / 5.5、Seedance 2.5）。

## 1.0.1 — 2026-11-17｜机构规则：所有生成一律不加水印

- 负责人「记住 所有水印都不要加！」→ 节点 `ArkSeedream` / `ArkSeedanceSubmit` 的 `watermark` 默认值由 true 改为 false；`tools/create_workflows.py` 生成的示例也改为 false。
- 仓库工作流 18/19/21/25 的 `watermark` 参数批量固化为 false（20 号为任务取回，无提交节点）；脚本调用须显式传 `watermark: false`。
- 合规：对外发布仍须按《人工智能生成合成内容标识办法》由使用方自行补显式标识，本规则不解除该义务。
