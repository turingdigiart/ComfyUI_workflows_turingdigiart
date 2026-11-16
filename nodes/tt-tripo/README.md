# tt-tripo｜机构自研 Tripo 文生 3D 调用节点

在 ComfyUI 里提交 Tripo API 文生 3D 任务并取回结果（GLB + 渲染预览图）。

## 节点

| 节点 | 用途 | 输入 | 输出 |
|---|---|---|---|
| `TTTripoSubmit` | 提交 `POST /generation/text-to-model` | enable_api（默认关）、prompt、model、negative_prompt、face_limit、texture、pbr、seed（0=不传 model_seed） | `task_id`(STRING)、`调用信息`(STRING) |
| `TTTripoFetch` | 轮询 `GET /tasks/{task_id}` 并取回 | task_id（可连线/手工粘贴）、wait_seconds(600)、poll_interval(5)、refresh_id | `模型路径`(STRING，GLB 存 `output/Tripo/`)、`预览图`(IMAGE)、`状态`(STRING) |

## Key 管理（DEC-ORG-094「本机配置 + 中控只验证约束」）

- Key 值只存各机本机：插件目录 `tripo.local.json` 的 `api_key` 字段，或环境变量 `TRIPO_API_KEY`（环境变量优先）；**不入画布、不入同步盘、不发聊天**。
- 仓库内只有 `tripo.local.json.example`（api_key 留空）；`tripo.local.json` 已被 `.gitignore` 排除，不会进 Git。
- 开工前三项机器检查：插件目录存在；`tripo.local.json` 可读且 `api_key` 非空（或环境变量存在）；`/object_info` 注册 `TTTripoSubmit`/`TTTripoFetch`。任一缺失即提示负责人补齐。

## 付费与边界（P1）

- 每次真实生成消耗 Tripo 额度；付费调用属 P1，**每次生成前确认预算**，不沿用历史授权。
- `enable_api` **默认关闭**：先确认参数与预算，再打开，防误扣费。
- `TTTripoFetch` 只查询与下载，**不自动重试提交**（防止同一任务重复计费）；超时后用同一 task_id 再次取回即可。
- 任务查询路径已按官方文档核验：`GET {base_url}/tasks/{task_id}`（2026-11-16，developers.tripo3d.com 任务查询页；候选的 `/generation/task/{task_id}` 不成立）。Base URL 默认 `https://openapi.tripo3d.ai/v3`（2026-11-16 零费用余额连通实测：本机构 Key 在 .ai 实例返回 200/code 0，.com 实例返回 401/code 2），可在 `tripo.local.json` 覆盖。

## 与官方 ComfyUI-Tripo 的关系

官方 `ComfyUI-Tripo`（1.3.0，11 节点）仅作设计参考；本插件为机构**自研替代**：只保留文生 3D 提交/取回两个最小节点、Key 走 DEC-ORG-094 本机配置模式、enable_api 默认关、不自动重试提交。代码全部自写，不复制官方源码。

## 示例工作流

`workflows/model3d/tripo/26_Tripo_文生3D.json`（MarkdownNote 使用说明 → TTTripoSubmit → TTTripoFetch → PreviewImage/PreviewAny）。
