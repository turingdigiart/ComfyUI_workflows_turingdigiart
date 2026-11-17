# Qwen 本地图像 API 配方（Qwen-Image 2.1 / 原始 Qwen-Image）

本目录是 **API 格式**的可执行配方，配合 `scripts/gen-qwen.mjs` 或 `scripts/run.mjs` 直接提交到本机 ComfyUI。
UI 格式母版仍在 `workflows/image/qwen/`（06/07/08）；这里的配方用于自动化、批量迭代和后续衍生。

## 文件

| 配方 | 模型 | 画布 | 用途 |
|---|---|---|---|
| `06_turbo_t2i.api.json` | `qwen_image_2.1_turbo_int8_convrot` | 1024×1024 | 2.1 Turbo 文生图，8 步 |
| `06_turbo_t2i_3x4.api.json` | 同上 | 1152×1536 | 小红书/抖音 3:4 竖版底图 |
| `07_turbo_edit.api.json` | 同上 | 跟随参考图 | 指令改图（LoadImage 参考图） |
| `08_standard_t2i.api.json` | `qwen_image_2.1_int8_convrot` | 1024×1024 | 2.1 标准版 40 步 |
| `08_standard_t2i_3x4.api.json` | 同上 | 1152×1536 | 标准版竖版 |
| `09_original_t2i.api.json` | `qwen_image_fp8_e4m3fn` | 1328×1328 | 原始 Qwen-Image，20 步 |
| `09_original_t2i_3x4.api.json` | 同上 | 1152×1536 | 原始 Qwen 竖版（**Apache-2.0 商用路径**） |
| `10_prompt_enhancer.api.json` | `qwen3.5_9b_qwen_image_2.1_pe_t2i.int8_convrot` | — | 官方 PE 提示词增强（**可选**；权重未装完，当前用 Ollama Qwen3.5） |

共享文件：`qwen3vl_8b_int8_convrot`（2.1 编码器）/ `qwen_2.5_vl_7b_fp8_scaled`（原始 Qwen 编码器）/ 各自 VAE。

## 用法

```powershell
# 列出配方
node scripts/gen-qwen.mjs --list

# 3:4 竖版底图（Turbo，8 步）
node scripts/gen-qwen.mjs `
  --recipe recipes/image/qwen/06_turbo_t2i_3x4.api.json `
  --prompt "vertical 3:4 editorial paper background, warm rice paper, deep green ink wash lower-left, clean negative space upper-right, no text" `
  --width 1152 --height 1536 --seed 42 --out-dir out/qwen

# 原始 Qwen（Apache-2.0，商用路径）
node scripts/gen-qwen.mjs `
  --recipe recipes/image/qwen/09_original_t2i_3x4.api.json `
  --prompt "..." --out-dir out/qwen-original

# 先校验不排队
node scripts/gen-qwen.mjs --recipe ... --prompt "..." --dry-run
```

改图配方：先把参考图放进 `ComfyUI/input/`，再 `--image 文件名.png`。

## 常用参数

`--prompt` / `--negative` / `--width` / `--height` / `--seed` / `--image` / `--prefix` / `--out-dir` / `--base` / `--timeout` / `--dry-run`。

## 许可与用途门

- **Qwen-Image 2.1**（06/07/08）：`qwen-research` 非商用；负责人已声明商用授权、证据待补（`models.manifest.json` 的 `usage_gate`）。补齐前 2.1 成品不对外发布商业内容。
- **原始 Qwen-Image**（09）：**Apache-2.0，可商用**，保留许可/NOTICE。

## 画布规则

Qwen 2.1 与原始 Qwen 都按 32 的倍数生成；3:4 用 1152×1536（=3:4 的 32 倍数）。`article-headline-forge` 需要的 1080×1440 会在渲染层缩放/裁切，因此配方统一输出 1152×1536。

**底图出现汉字/竖排字**：Qwen 2.1 有时会自行补字。用 `--negative "text, letters, Chinese characters, calligraphy, handwriting, symbols, logo, watermark"` 并换 seed；仍出现就降低画面元素，用纯纹理提示词。

## 与 UI 工作流的关系

- UI 母版：`workflows/image/qwen/06–08`（ComfyUI 界面直接打开）。
- API 配方：本目录（脚本/批量）。
- 任一侧改动后，用 `node scripts/ui2api.mjs` 重新生成 API 配方并更新本 README，避免两份手工漂移。
