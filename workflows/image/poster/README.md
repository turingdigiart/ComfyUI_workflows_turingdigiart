# POSTER_LAYERED_v001｜分层生成 + 单工作流合成

```yaml
artifact_id: ORG-WORKFLOW-POSTER-LAYERED-001
current_version: v001
record_class: FormalRecord
retention_mode: FinalOnly
humanizer_status: ExceptionReviewed
exception_reason: 工作流说明与机器指令，不是面向受众的业务文案
decision_id: DEC-ORG-067
updated_at: 2026-10-31
status: Validated-LocalRunOnly
```

## 一句话

一个 ComfyUI 工作流内跑完四层生成，再由工作流自身把四层合成一张成品，不分四次跑再外部拼图。

## 为什么分层

整张图一次生成，版式、光效、主体全绑在一起，改一处只能重生成整张，控制不了。分层之后每一层可以单独换提示词、种子、强度，合成规则也留在图里，重跑结果可复现。

| 层 | 内容 | 合成方式 |
|---|---|---|
| L1 | 背景：暗场、氛围、地面网格 | 底层 |
| L2 | 光带 / 体积光 | screen 叠加，0.50 |
| L3 | 粒子 / 尘埃 | screen 叠加，0.40 |
| L4 | 主体：半透明玻璃板 | 缩到 55%，取亮度蒙版，羽化后合成到下方 1/3 |

## 图结构（API 格式）

- 一个 `CheckpointLoaderSimple` 分三个分支采样，负面提示共用。
- 三条 `KSampler` 各自独立种子；每个分支都有 `SaveImage`，单层结果可单独取用。
- `ImageBlend`(screen) ×2 → `ImageScale`(L4 缩放) → `ImageToMask`/`GrowMask` → `ImageCompositeMasked` → `ImageSharpen` → `SaveImage` 成品。
- 所有合成在同一个 prompt 里完成，一次提交、一次返回。

## 运行

```powershell
# 1) 启动本机 ComfyUI（独立工具工程，位置按 TOOLS_ROOT 解析）
E:\RAE_ToolRoot\comfyui\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 2) 提交工作流（默认 3:4，1152×1536）
node ../../scripts/poster/run_poster_layered_v001.cjs

# 换尺寸/提示词：改环境变量再跑
$env:BG="..."; $env:SUBJ="..."; node run_poster_layered_v001.cjs
```

输出落在 ComfyUI 工程的 `output/qbank_poster_v002/`，包含 L1–L4 与 FINAL。

## 依赖

- 模型：`RealVisXL_V5.0_fp16.safetensors`（已在本机 ComfyUI `models/checkpoints/`）。
- 节点：全部为 ComfyUI 0.43.0 核心节点，无第三方节点依赖。
- 未使用需要下载的新权重：现有 SDXL 已能覆盖背景、光效、粒子、主体四类提示词。若后续要更强的画面一致性，再评估 Flux2 Klein 或训练专属 LoRA，另行登记。

## 已验证 / 未验证

- 已验证（2026-10-31 本机实跑）：工作流端到端成功，一次提交返回 5 张（L1–L4 + FINAL），成品 1152×1536。
- 未验证：9:16 封面尺寸、批量多张、文字层合成（本工作流只产出无字底图，文字按机构规则由程序排版，不交给模型）。

## 边界

只产出无文字底图。中文标题、机构名、数据一律由程序排版层写入，不让模型画字——模型画中文字形不可控，也过不了审校。

## 迁入本仓备注（2026-11-16）

- 工作流为 API 格式（class_type 节点字典），scripts/catalog.mjs 只能登记文件名，节点/模型元数据为空属预期；台账按手工登记口径维护。
- 迁移时仅改两处：runner 相对路径改为 ../../scripts/poster/，并追加本备注；其余正文与母版逐字一致。
