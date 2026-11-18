# 12_写实版_遮罩换发型_SDXL_IPAdapter_v001｜SDXL + IPAdapter 遮罩换发型（保脸）

```yaml
artifact_id: ORG-WORKFLOW-IDENTITY-HAIRMASK-001
current_version: v001
record_class: FormalRecord
retention_mode: FinalOnly
humanizer_status: ExceptionReviewed
exception_reason: 工作流说明与机器指令，不是面向受众的业务文案
updated_at: 2026-11-18
status: Candidate
```

## 一句话

底图 + 头发遮罩 + 发型参考，**只重绘遮罩区**：脸保持底图（遮罩外不重新采样），发型按参考与提示词换；代价是头发质感上限低于 Qwen/Seedream，只作保底方案。

## 为什么需要

身份已经确认、构图已经定稿，只想换发型时，整张重生成会重新掷一次脸。遮罩重绘把改动锁在头发区，是"改发型但不能动脸"的兜底手段。成片级质感仍回 Qwen 出图或放大修图。

方法来源：`TuringDigiArt/运营内容/常用人物/写实版/工作流/IP管线_v001/docs/IDENTITY_FACE_METHOD_v001.md` §3.4。

## 图结构（API 格式）

- `CheckpointLoaderSimple`：`RealVisXL_V5.0_fp16.safetensors` → MODEL / CLIP / VAE。
- IPAdapter 分支：`IPAdapterModelLoader`(`ip-adapter-plus_sdxl_vit-h.safetensors`) + `CLIPVisionLoader`(`CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`) → `IPAdapterAdvanced`（`image`=发型参考，`attn_mask`=头发遮罩，weight 0.75 / linear / concat / V only）。
- 重绘分支：`VAEEncodeForInpaint`（`pixels`=底图，`mask`=同款遮罩，`grow_mask_by`=16；1280 宽底图用 20）。
- 采样：`KSampler` → steps 30 / cfg 6.0 / `dpmpp_2m` / `karras` / denoise 1.0 → `VAEDecode` → `SaveImage`（`output/IP_hairmask_ipadapter_v001_*.png`）。

提示词只写发型结构，不写身份变更；负向必须带 `changed face`（完整片段见上引方法文档 §四）。

## 两份文件的关系（有意例外，先看再改）

| 文件 | 格式 | 作用 |
|---|---|---|
| `12_写实版_遮罩换发型_SDXL_IPAdapter_v001.json` | API（`class_type` 节点字典） | `/prompt` 直接提交的**执行版**；本工作流以本轮已验证的 API prompt 固化为准 |
| `12_写实版_遮罩换发型_SDXL_IPAdapter_v001_UI.json` | UI（`nodes` + `links`） | 给 ComfyUI 界面打开、看连线、临时改参用 |

- 仓库常规是「UI 为母版、API 以 `_api.json` 结尾」（`docs/DESIGN.md` §API/UI 格式）。本工作流**有意例外**：本轮实验本身就是以 API prompt 直接提交的，API 版是母版；UI 版为界面打开而重建，故加 `_UI` 后缀。
- 两份文件已用 `scripts/ui2api.mjs` 从 UI 版反向转出并与 API 版逐节点、逐连线、逐参数比对，**完全一致**。改参时以 API 版为准，改完 UI 也要同步。

```powershell
# 结构校验（不排队）
node scripts/run.mjs --prompt "workflows/identity/tt-ip-写实版/12_写实版_遮罩换发型_SDXL_IPAdapter_v001.json" --dry-run

# UI 版反查（可核对两份是否同步）
node scripts/ui2api.mjs --workflow "workflows/identity/tt-ip-写实版/12_写实版_遮罩换发型_SDXL_IPAdapter_v001_UI.json" --out "$env:TEMP/wf12.api.json"
```

## 输入

三个 `LoadImage` 默认指向本机 ComfyUI input 的运行副本（换图时替换）：

| 节点 | 默认文件 | 要求 |
|---|---|---|
| 底图 | `TT_IP_20261030/04_w2_base.png` | 已确认脸与构图的图；尺寸与遮罩同宽高 |
| 遮罩 | `TT_IP_20261030/04_w2_hair_mask.png` | 与底图同尺寸；白色=重绘区（头发） |
| 发型参考 | `TT_IP_20261030/03_hair_approved_v005.jpg` | v005 已确认发型图；单图，不要加第二张 |

## 已验证 / 未验证

- **已验证（2026-11-18 本机实跑）**：同链路组件——`IP_hairipa_H1`（weight 0.75、denoise 0.95、grow 16）与 `IP_hairv2_J1`（denoise 1.0、grow 20、1280 底图）均已在本机 ComfyUI 出图，遮罩外脸保持不变。
- **已验证（结构）**：`run.mjs --dry-run` 校验通过（13 节点，输入名与必填项齐全）；UI↔API 往返逐项一致。
- **未验证**：本模板的固定组合（steps 30 / cfg 6.0 / denoise 1.0 / grow 16）没有整跑逐张记录；头发质感上限结论来自对照图，不是可量化指标。
- **未验证**：1280 以上底图、多人/全身边框的遮罩效果。

## 边界

- 只换发型，不改身份、不改眼镜、不改构图；要改这些回 Qwen 参考图路线或 Seedream 单图锚点路线。
- 不产生正式交付物：输出只作候选，晋级为基准需本人确认。
- 人物照片与遮罩属受控素材，不上传外部、不进公开仓库。
