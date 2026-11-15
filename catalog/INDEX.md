# 工作流索引（按用途找）

> 由 `scripts/catalog.mjs` 生成。想"做什么"就来这里找，找到路径后用 `run.mjs` 调用。

## 按类别

### identity（7）

**01_写实版_基准脸**
- 路径：`identity/tt-ip-写实版/01_写实版_基准脸.json`
- 参数：RealVisXL_V5.0_fp16 · 896x1152 · 30 步 · dpmpp_2m_sde
- 模型：RealVisXL_V5.0_fp16.safetensors
- 说明：（画布里没有说明节点，靠文件名判断）

**02_写实版_Apose全身**
- 路径：`identity/tt-ip-写实版/02_写实版_Apose全身.json`
- 参数：RealVisXL_V5.0_fp16 · 832x1216 · 30 步 · dpmpp_2m_sde
- 模型：RealVisXL_V5.0_fp16.safetensors、controlnet-openpose-sdxl-1.0.safetensors
- 说明：（画布里没有说明节点，靠文件名判断）

**03_写实版_Apose三套穿搭**
- 路径：`identity/tt-ip-写实版/03_写实版_Apose三套穿搭.json`
- 参数：RealVisXL_V5.0_fp16 · 832x1216 · 30 步 · dpmpp_2m_sde
- 模型：RealVisXL_V5.0_fp16.safetensors、controlnet-openpose-sdxl-1.0.safetensors
- 说明：（画布里没有说明节点，靠文件名判断）

**04_写实版_封面构图**
- 路径：`identity/tt-ip-写实版/04_写实版_封面构图.json`
- 参数：RealVisXL_V5.0_fp16 · 896x1152 · 30 步 · dpmpp_2m_sde
- 模型：RealVisXL_V5.0_fp16.safetensors
- 说明：（画布里没有说明节点，靠文件名判断）

**05_写实版_放大修图**
- 路径：`identity/tt-ip-写实版/05_写实版_放大修图.json`
- 参数：—
- 模型：4x-UltraSharp.pth
- 说明：（画布里没有说明节点，靠文件名判断）

**06_写实版_照片一致性**
- 路径：`identity/tt-ip-写实版/06_写实版_照片一致性.json`
- 参数：RealVisXL_V5.0_fp16 · 896x1152 · 30 步 · dpmpp_2m_sde
- 模型：CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors、RealVisXL_V5.0_fp16.safetensors、ip-adapter-plus_sdxl_vit-h.safetensors
- 说明：（画布里没有说明节点，靠文件名判断）

**07_Flux_四套穿搭**  ⚠️ 缺模型
- 路径：`identity/tt-ip-写实版/07_Flux_四套穿搭.json`
- 参数：flux1-dev-fp8 · 832x1216 · 24 步 · euler
- 模型：flux1-dev-fp8.safetensors
- 说明：（画布里没有说明节点，靠文件名判断）

### image（13）

**14_通用API提示词_预览**
- 路径：`image/api/14_通用API提示词_预览.json`
- 参数：—
- 说明：（画布里没有说明节点，靠文件名判断）

**15_通用API提示词_ZImage文生图**
- 路径：`image/api/15_通用API提示词_ZImage文生图.json`
- 参数：z_image_turbo_bf16 · 1024x1024 · 8 步 · res_multistep
- 模型：ae.safetensors、qwen_3_4b.safetensors、z_image_turbo_bf16.safetensors
- 说明：通用 API 提示词 → Z-Image。默认 manual，无 API 费用。先在 14 预览流程调试平台，再切换 api。调整 refresh_id 可重新生成提示词；可将预览文本粘贴至 manual_prompt 后手动编辑。平台密钥

**18_方舟Seedream_机器人改图**
- 路径：`image/ark/18_方舟Seedream_机器人改图.json`
- 参数：—
- 说明：配置部署插件目录中的 ark.local.json，填API Key并在方舟开通模型；模型留空使用配置。确认后打开 enable_api。密钥不要填进画布。参考图会上传到火山方舟，调用使用方舟账户额度。

**09_Flux2Klein_快速文生图**
- 路径：`image/flux/09_Flux2Klein_快速文生图.json`
- 参数：flux-2-klein-4b-fp8
- 模型：flux-2-klein-4b-fp8.safetensors、flux2-vae.safetensors、qwen_3_4b.safetensors
- 说明：FLUX.2 Klein 4B FP8：4步生成，默认1024×1024。图生图使用参考潜空间，直接描述修改要求。

**10_Flux2Klein_指令改图**
- 路径：`image/flux/10_Flux2Klein_指令改图.json`
- 参数：flux-2-klein-4b-fp8
- 模型：flux-2-klein-4b-fp8.safetensors、flux2-vae.safetensors、qwen_3_4b.safetensors
- 说明：FLUX.2 Klein 4B FP8：4步生成，默认1024×1024。图生图使用参考潜空间，直接描述修改要求。

**06_Qwen21_Turbo_文生图**
- 路径：`image/qwen/06_Qwen21_Turbo_文生图.json`
- 参数：qwen_image_2.1_turbo_int8_convrot
- 模型：qwen3vl_8b_int8_convrot.safetensors、qwen_image_2.1_turbo_int8_convrot.safetensors、qwen_image_2.1_vae_bf16.safetensors
- 说明：Qwen Image 2.1：默认1024像素；Turbo使用官方8步时间表，标准版使用40步。图生图上传参考图后，用文字描述要修改的内容。标准版与Turbo共享编码器和VAE。提示词增强器未启用，无需额外语言模型。

**07_Qwen21_Turbo_指令改图**
- 路径：`image/qwen/07_Qwen21_Turbo_指令改图.json`
- 参数：qwen_image_2.1_turbo_int8_convrot
- 模型：qwen3vl_8b_int8_convrot.safetensors、qwen_image_2.1_turbo_int8_convrot.safetensors、qwen_image_2.1_vae_bf16.safetensors
- 说明：Qwen Image 2.1：默认1024像素；Turbo使用官方8步时间表，标准版使用40步。图生图上传参考图后，用文字描述要修改的内容。标准版与Turbo共享编码器和VAE。提示词增强器未启用，无需额外语言模型。

**08_Qwen21_标准版_文生图**
- 路径：`image/qwen/08_Qwen21_标准版_文生图.json`
- 参数：qwen_image_2.1_int8_convrot · 40 步 · euler
- 模型：qwen3vl_8b_int8_convrot.safetensors、qwen_image_2.1_int8_convrot.safetensors、qwen_image_2.1_vae_bf16.safetensors
- 说明：Qwen Image 2.1：默认1024像素；Turbo使用官方8步时间表，标准版使用40步。图生图上传参考图后，用文字描述要修改的内容。标准版与Turbo共享编码器和VAE。提示词增强器未启用，无需额外语言模型。

**01_SDXL_文生图**
- 路径：`image/sdxl/01_SDXL_文生图.json`
- 参数：sd_xl_base_1.0 · 1024x1024 · 25 步 · dpmpp_2m
- 模型：sd_xl_base_1.0.safetensors
- 说明：（画布里没有说明节点，靠文件名判断）

**02_SDXL_图生图**
- 路径：`image/sdxl/02_SDXL_图生图.json`
- 参数：sd_xl_base_1.0 · 25 步 · dpmpp_2m
- 模型：sd_xl_base_1.0.safetensors
- 说明：（画布里没有说明节点，靠文件名判断）

**16_SDXL_我的人物形象_参考照片**
- 路径：`image/sdxl/16_SDXL_我的人物形象_参考照片.json`
- 参数：sd_xl_base_1.0 · 56 步 · dpmpp_2m
- 模型：sd_xl_base_1.0.safetensors
- 说明：我的人物形象图 / SDXL 图生图

**17_SDXL_机器人重新设计_双强度对比**
- 路径：`image/sdxl/17_SDXL_机器人重新设计_双强度对比.json`
- 参数：sd_xl_base_1.0 · 30 步 · dpmpp_2m
- 模型：sd_xl_base_1.0.safetensors
- 说明：机器人重新设计 / 双强度对比

**05_ZImageTurbo_快速文生图**
- 路径：`image/zimage/05_ZImageTurbo_快速文生图.json`
- 参数：z_image_turbo_bf16 · 1024x1024 · 8 步 · res_multistep
- 模型：ae.safetensors、qwen_3_4b.safetensors、z_image_turbo_bf16.safetensors
- 说明：8步快速出图；默认1024×1024。修改提示词后运行。支持中文与英文提示词。原生节点，无需额外插件。

### model3d（1）

**13_Hunyuan3D21_图片生成3D模型**
- 路径：`model3d/hunyuan/13_Hunyuan3D21_图片生成3D模型.json`
- 参数：30 步 · euler
- 模型：hunyuan_3d_v2.1.safetensors
- 说明：3D可行性验证：单张参考图生成无贴图GLB网格。默认官方示例图、30步、4096潜变量、256网格解码分辨率。输出不是已绑定角色：仍需要拓扑整理、UV/材质、骨骼和蒙皮。可将GLB导入Blender继续制作。

### video（7）

**19_方舟Seedance_机器人图生视频**
- 路径：`video/ark/19_方舟Seedance_机器人图生视频.json`
- 参数：—
- 说明：配置部署插件目录中的 ark.local.json，填API Key并在方舟开通模型；模型留空使用配置。确认后打开 enable_api。密钥不要填进画布。参考图会上传到火山方舟，调用使用方舟账户额度。

**20_方舟Seedance_已有任务取回**
- 路径：`video/ark/20_方舟Seedance_已有任务取回.json`
- 参数：—
- 说明：填写已有任务ID，使用同一方舟账户的配置。此工作流只查询和下载，不创建新生成任务。可用于恢复超时任务；任务和下载地址存在有效期，完成后尽快保存。

**21_方舟Seedance_文生视频**
- 路径：`video/ark/21_方舟Seedance_文生视频.json`
- 参数：—
- 说明：配置部署插件目录中的 ark.local.json，填API Key并在方舟开通模型；模型留空使用配置。确认后打开 enable_api。密钥不要填进画布。参考图会上传到火山方舟，调用使用方舟账户额度。

**12_LTX23_有声视频**
- 路径：`video/ltx/12_LTX23_有声视频.json`
- 参数：ltx-2.3-22b-dev-fp8 · 320 帧
- 模型：gemma_3_12B_it_fp4_mixed.safetensors、ltx-2.3-22b-dev-fp8.safetensors、ltx-2.3-spatial-upscaler-x2-1.1.safetensors、ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors
- 说明：LTX 2.3 FP8 + 蒸馏LoRA：默认640×384、49帧、24fps，约2秒，联合生成画面与声音。提示词同时描述动作、镜头和声音。先320×192生成，再通过潜空间放大与3步细化得到640×384，以控制显存。不要直接设置长片或

**03_Wan22_文生视频**
- 路径：`video/wan/03_Wan22_文生视频.json`
- 参数：wan2.2_ti2v_5B_fp16 · 20 步 · uni_pc
- 模型：umt5_xxl_fp8_e4m3fn_scaled.safetensors、wan2.2_ti2v_5B_fp16.safetensors、wan2.2_vae.safetensors
- 说明：本机视频工作流

**04_Wan22_图生视频**
- 路径：`video/wan/04_Wan22_图生视频.json`
- 参数：wan2.2_ti2v_5B_fp16 · 20 步 · uni_pc
- 模型：umt5_xxl_fp8_e4m3fn_scaled.safetensors、wan2.2_ti2v_5B_fp16.safetensors、wan2.2_vae.safetensors
- 说明：本机视频工作流

**11_Wan22_14B_图生视频**
- 路径：`video/wan/11_Wan22_14B_图生视频.json`
- 参数：wan2.2_i2v_high_noise_14B_fp8_scaled
- 模型：umt5_xxl_fp8_e4m3fn_scaled.safetensors、wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors、wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors、wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors、wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors、wan_2.1_vae.safetensors
- 说明：Wan 2.2 14B FP8高低噪声模型 + LightX2V 4步LoRA。默认640×384、49帧、16fps，约3秒无声短片。上传参考图并描述动作；尺寸、时长提高会增加显存和耗时。

## 待补说明

这些工作流的画布里没有 MarkdownNote，建议补一条用途说明：

- `identity/tt-ip-写实版/01_写实版_基准脸.json`
- `identity/tt-ip-写实版/02_写实版_Apose全身.json`
- `identity/tt-ip-写实版/03_写实版_Apose三套穿搭.json`
- `identity/tt-ip-写实版/04_写实版_封面构图.json`
- `identity/tt-ip-写实版/05_写实版_放大修图.json`
- `identity/tt-ip-写实版/06_写实版_照片一致性.json`
- `identity/tt-ip-写实版/07_Flux_四套穿搭.json`
- `image/api/14_通用API提示词_预览.json`
- `image/sdxl/01_SDXL_文生图.json`
- `image/sdxl/02_SDXL_图生图.json`

## 缺模型

| 工作流 | 缺的模型 |
|---|---|
| `identity/tt-ip-写实版/07_Flux_四套穿搭.json` | flux1-dev-fp8.safetensors |
