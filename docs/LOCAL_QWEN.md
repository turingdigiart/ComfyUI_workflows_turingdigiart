# Qwen 本地图像工作流（Qwen-Image 2.1 / 原始 Qwen-Image）

本机 ComfyUI（`TOOL-ORG-COMFYUI-001`）已接入两套 Qwen 图像模型，全部本地推理，无云 API 费用。
本页是 **迭代/衍生入口**：模型、许可、配方、性能、扩展方式、与 `article-headline-forge` 的衔接。

## 1. 模型与许可

| 路径 | 文件 | 许可 | 用途 |
|---|---|---|---|
| Qwen-Image 2.1 Turbo | `qwen_image_2.1_turbo_int8_convrot.safetensors` | `qwen-research`（负责人声明商用授权、证据待补） | 日常 8 步出图/改图 |
| Qwen-Image 2.1 标准版 | `qwen_image_2.1_int8_convrot.safetensors` | 同上 | 40 步，细节更好 |
| Qwen-Image 2.1 编码器 | `qwen3vl_8b_int8_convrot.safetensors` | 同上 | 2.1 文本编码 |
| Qwen-Image 2.1 VAE | `qwen_image_2.1_vae_bf16.safetensors` | 同上 | 2.1 解码 |
| 原始 Qwen-Image | `qwen_image_fp8_e4m3fn.safetensors` | **Apache-2.0（可商用）** | 商用路径，20 步 |
| 原始 Qwen 编码器 | `qwen_2.5_vl_7b_fp8_scaled.safetensors` | Apache-2.0 | 原始 Qwen 文本编码 |
| 原始 Qwen VAE | `qwen_image_vae.safetensors` | Apache-2.0 | 原始 Qwen 解码 |

- 权重的 SHA-256、大小、来源与下载配方在机构清单 `工具配置/ComfyUI/models.manifest.json`（7 件均 `Installed/verified`）。
- **2.1 为 `qwen-research` 非商用**：台账为 `OwnerClaimedCommercial_EvidencePending`，授权证据补齐前不对外发布 2.1 成品；**原始 Qwen（09 路径）Apache-2.0，可商用**。

## 2. 配方

### UI 格式（ComfyUI 界面）

`workflows/image/qwen/06_Qwen21_Turbo_文生图.json`、`07_Qwen21_Turbo_指令改图.json`、`08_Qwen21_标准版_文生图.json`

### API 格式（脚本/批量）

`recipes/image/qwen/`：

| 配方 | 模型 | 画布 |
|---|---|---|
| `06_turbo_t2i.api.json` | 2.1 Turbo | 1024×1024 |
| `06_turbo_t2i_3x4.api.json` | 2.1 Turbo | 1152×1536 |
| `07_turbo_edit.api.json` | 2.1 Turbo | 参考图 |
| `08_standard_t2i.api.json` | 2.1 标准版 | 1024×1024 |
| `08_standard_t2i_3x4.api.json` | 2.1 标准版 | 1152×1536 |
| `09_original_t2i.api.json` | 原始 Qwen | 1328×1328 |
| `09_original_t2i_3x4.api.json` | 原始 Qwen | 1152×1536 |

### 运行

```powershell
node scripts/gen-qwen.mjs --list

node scripts/gen-qwen.mjs `
  --recipe recipes/image/qwen/06_turbo_t2i_3x4.api.json `
  --prompt "vertical 3:4 rice paper backdrop, deep green ink wash lower-left, empty upper-right, no text" `
  --width 1152 --height 1536 --seed 42 --out-dir out/qwen
```

改图：

```powershell
# 先把参考图放进 ComfyUI/input/
node scripts/gen-qwen.mjs --recipe recipes/image/qwen/07_turbo_edit.api.json `
  --image my-ref.png --prompt "change the ink to terracotta, keep texture" --out-dir out/qwen-edit
```

`--dry-run` 只校验和打印补丁结果，不排队。

## 3. 自动选路（preset）

`gen-qwen.mjs` 内置 preset，按意图直接选工作流；**对外商用自动走 Apache-2.0 路径**：

| 意图 | 命令 |
|---|---|
| 内部快打样 3:4 | `--preset turbo-3x4` |
| 内部精修 3:4 | `--preset standard-3x4` |
| 改图 | `--preset edit` |
| 对外商业底图 | `--commercial`（自动选 `original-3x4`，2.1 会被拒绝） |
| 指定原始 Qwen | `--preset original-3x4` |

```powershell
node scripts/gen-qwen.mjs --preset turbo-3x4 --prompt "..." --out-dir out/qwen
node scripts/gen-qwen.mjs --commercial --prompt "..." --out-dir out/qwen-commercial
```

`--list` 会同时列出 presets 与 recipes。跨能力选路：本地 Qwen 生图 → `local-qwen-image`；版式/文字层 → `article-headline-forge`；云端 Seedream/Seedance → `volcano-ark-media`。

## 4. 本机性能实测（RTX 5060 8GB，ComfyUI 0.43，int8/fp8 + offload）

| 配方 | 步数 | 冷/暖 | 耗时 | 画布 |
|---|---|---|---|---|
| 2.1 Turbo 3:4 | 8 | 冷 | ~83s | 1152×1536 |
| 2.1 Turbo 3:4 | 8 | 暖 | ~24s | 1152×1536 |
| 2.1 标准版 3:4 | 40 | 暖 | ~104s | 1152×1536 |
| 原始 Qwen 3:4 | 20 | 冷 | ~251s | 1152×1536 |

- 8GB 显存可跑，但首次加载/切换模型明显慢；批量任务尽量同一模型连续跑。
- 模型列表变化后需重启 ComfyUI（`/object_info` 才会出现新文件名）。
- 3:4 一律用 32 的倍数：1152×1536；**不要**用 1080×1440 直接生成（非 32 倍数），交给 `article-headline-forge` 缩放/裁切。

## 5. 提示词增强（本机 Qwen）

**首选：Ollama `qwen35-9b-flash:latest`（已安装，已实测）**

```powershell
node scripts/enhance-prompt-ollama.mjs --brief "竖版 3:4 纸感背景，墨绿左下，右上留白" --out out/enhanced.txt
```

- 输出 100–150 词英文提示词，含材质/色调/光向/负空间，并强制 no text/logo/people。
- 本机实测 7–30s/条；脚本会检测未闭合 `<think>` 并自动加倍 token 重试。
- 注意：Ollama 与 ComfyUI 共用 8GB 显存；**先改写、后出图**（脚本会 `keep_alive:0` 卸载）。

**可选：官方 Qwen-Image 2.1 PE（`10_prompt_enhancer.api.json`）**：Qwen3.5-9B `pe_t2i.int8` 权重（8.82GB）尚未装完（`text_encoders/*.part` 暂停在 ~3.5GB），配方与 `scripts/enhance-qwen-prompt.mjs` 已备好，未启用；恢复下载后可用 `TextGenerate` 路径。

> 深色主题（guochao/midnight）配现有深色 Logo 对比不足；本机 5 封面 demo 在底图右上角合成了浅色 Logo 安全牌。长期方案：补白色版 2026 Logo 资产并登记 `MAT-EXAM-LOGO-2026-*`，不要把历史 2023 白 Logo 当 Current。

## 6. 迭代与衍生

### 换提示词 / 种子 / 尺寸

`gen-qwen.mjs` 自动定位 `TextEncodeQwenImage21`（2.1）或 `CLIPTextEncode`（原始 Qwen）、`EmptyLatentImage`/`EmptySD3LatentImage`、`RandomNoise`/`KSampler`、`SaveImage`，无需手改 JSON。

### 加 LoRA / ControlNet / 新节点

1. 在 ComfyUI UI 里加节点，导出 UI 工作流；
2. `node scripts/ui2api.mjs --workflow <新UI.json> --out recipes/image/qwen/<新配方>.api.json`；
3. 更新本页与 `recipes/image/qwen/README.md`，提交；不要手改 API JSON 与 UI 各一套还不同步。
4. LoRA 放 `models/loras/`，ControlNet 放 `models/controlnet/`；新增权重先在 `models.manifest.json` 登记 source/size/SHA 再落地。

### 加新 Qwen 变体 / 新模型

- 新模型文件必须先在 `models.manifest.json` 登记（url/revision/sha256/target/license），再下载；许可为 research 的模型在 `usage_gate` 标注用途。
- 新工作流先过 Git 同步门与 `check-worktree-integrity.ps1`，再提交。
- 2.1 的 prompt enhancer（`qwen3.5_9b_qwen_image_2.1_pe_t2i/int8`）尚未下载；需要时按同一配方登记后接入 `TextGenerate`。

### 与 `article-headline-forge` 衔接

1. 用 `06_turbo_t2i_3x4.api.json` 或 `09_original_t2i_3x4.api.json` 生成 1152×1536 底图；
2. 在 headline-forge `content.json` 用 `background.mode="image"` 指向该图，`scrim` 0.45–0.55；
3. 后续排版、Logo、QA 由 headline-forge 负责；本仓库不产出文字层。

## 5. 故障排查

| 现象 | 原因 | 修法 |
|---|---|---|
| `/object_info` 没有模型 | ComfyUI 未重扫 | 重启 ComfyUI |
| 队列失败 `value not in list` | 模型文件没到目标目录/文件名不一致 | 对照 `models.manifest.json` 的 `target` |
| 8GB 显存 OOM | fp8 19GB 模型 + 大画布 | 用 2.1 int8 / 降画布 / 关其他 GPU 程序 |
| 改图 404 | 参考图不在 `ComfyUI/input/` | 先复制或用 `--image` 传 input 目录内文件名 |
| 生成有字/水印 | 提示词未约束，或 Qwen 2.1 自行补字/竖排字 | 提示词加 `no text, no letters, no logo, no watermark`；再用 `--negative "text, letters, Chinese characters, calligraphy, handwriting, symbols, logo, watermark"` 并换 seed；仍出现则降低画面元素、改用纯纹理提示词 |

## 7. 相关记录

- `models.manifest.json`（7 件 Qwen 均 verified）
- `OP-20261117-QWEN-LOCAL-001/002`、`SESSION_HANDOFF` 2026-11-17
- 技能：`.agents/skills/local-qwen-image/`（机构侧调用入口）；`article-headline-forge` 负责排版。
