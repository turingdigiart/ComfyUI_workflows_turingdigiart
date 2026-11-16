# 工作流台账

> 由 `scripts/catalog.mjs` 生成，**不要手改**。改工作流后重跑脚本。
> 生成时间：2026-11-16T09:40:24.072Z
> 来源目录：`E:\Private\AIDev\TECH-COMFY-001_comfyui-workflows\workflows`
> 共 42 条｜缺模型 16 条｜缺说明 22 条

## 分类分布

| 类别 | 数量 |
|---|---:|
| audio | 1 |
| identity | 16 |
| image | 16 |
| model3d | 1 |
| video | 8 |

## audio

| 工作流 | 说明 | 参数 | 模型 | 校验 |
|---|---|---|---|:--:|
| `audio/ace/24_ACE_Step_文生音频.json` | ACE-Step 1.0 · 10 秒纯音乐 | ace_step_v1_3.5b · 30 步 · euler | 1 | ✅ |

## identity

| 工作流 | 说明 | 参数 | 模型 | 校验 |
|---|---|---|---|:--:|
| `identity/tt-ip-写实版/01_写实版_基准脸_v001.json` | 01_写实版_基准脸_v001 | RealVisXL_V5.0_fp16 · 896x1152 · 30 步 · dpmpp_2m_sde | 1 | ✅ |
| `identity/tt-ip-写实版/01_写实版_基准脸_v002.json` | 01_写实版_基准脸_v002 | RealVisXL_V5.0_fp16 · 896x1152 · 30 步 · dpmpp_2m_sde | 1 | ✅ |
| `identity/tt-ip-写实版/02_写实版_Apose全身_v001.json` | 02_写实版_Apose全身_v001 | RealVisXL_V5.0_fp16 · 832x1216 · 30 步 · dpmpp_2m_sde | 2 | ✅ |
| `identity/tt-ip-写实版/02_写实版_Apose全身_v002.json` | 02_写实版_Apose全身_v002 | RealVisXL_V5.0_fp16 · 832x1216 · 30 步 · dpmpp_2m_sde | 2 | ✅ |
| `identity/tt-ip-写实版/03_写实版_Apose三套穿搭_v001.json` | 03_写实版_Apose三套穿搭_v001 | RealVisXL_V5.0_fp16 · 832x1216 · 30 步 · dpmpp_2m_sde | 2 | ✅ |
| `identity/tt-ip-写实版/03_写实版_Apose三套穿搭_v002.json` | 03_写实版_Apose三套穿搭_v002 | RealVisXL_V5.0_fp16 · 832x1216 · 30 步 · dpmpp_2m_sde | 2 | ✅ |
| `identity/tt-ip-写实版/04_写实版_封面构图_v001.json` | 04_写实版_封面构图_v001 | RealVisXL_V5.0_fp16 · 896x1152 · 30 步 · dpmpp_2m_sde | 1 | ✅ |
| `identity/tt-ip-写实版/04_写实版_封面构图_v002.json` | 04_写实版_封面构图_v002 | RealVisXL_V5.0_fp16 · 896x1152 · 30 步 · dpmpp_2m_sde | 1 | ✅ |
| `identity/tt-ip-写实版/05_写实版_放大修图.json` | 05_写实版_放大修图 | — | 1 | ✅ |
| `identity/tt-ip-写实版/06_写实版_照片一致性_v001.json` | 06_写实版_照片一致性_v001 | RealVisXL_V5.0_fp16 · 896x1152 · 30 步 · dpmpp_2m_sde | 3 | ✅ |
| `identity/tt-ip-写实版/06_写实版_照片一致性_v002.json` | 06_写实版_照片一致性_v002 | RealVisXL_V5.0_fp16 · 896x1152 · 30 步 · dpmpp_2m_sde | 3 | ✅ |
| `identity/tt-ip-写实版/07_Flux_四套穿搭_v001.json` | 07_Flux_四套穿搭_v001 | flux1-dev-fp8 · 832x1216 · 24 步 · euler | 1 | ✅ |
| `identity/tt-ip-写实版/07_Flux_四套穿搭_v002.json` | 07_Flux_四套穿搭_v002 | flux1-dev-fp8 · 832x1216 · 24 步 · euler | 1 | ✅ |
| `identity/tt-ip-写实版/08_Flux_四套_锁姿势.json` | 08_Flux_四套_锁姿势 | flux1-dev-fp8 · 832x1216 · 24 步 · euler | 2 | ✅ |
| `identity/tt-ip-写实版/09_SDXL_四套_锁脸锁姿势.json` | 09_SDXL_四套_锁脸锁姿势 | RealVisXL_V5.0_fp16 · 832x1216 · 30 步 · dpmpp_2m_sde | 4 | ✅ |
| `identity/tt-ip-写实版/10_SDXL_LoRA_四套.json` | 10_SDXL_LoRA_四套 | RealVisXL_V5.0_fp16 · 832x1216 · 26 步 · dpmpp_2m_sde | 3 | ✅ |

## image

| 工作流 | 说明 | 参数 | 模型 | 校验 |
|---|---|---|---|:--:|
| `image/api/14_通用API提示词_预览.json` | 14_通用API提示词_预览 | — | 0 | ✅ |
| `image/api/15_通用API提示词_ZImage文生图.json` | 通用 API 提示词 → Z-Image。默认 manual，无 API 费用。先在 14 预览流程调试平台，再切换 api。调整 refresh_id 可重新生成提示词；可将预览文本粘贴至 manual_prompt 后手动编辑。平台密钥 | z_image_turbo_bf16 · 1024x1024 · 8 步 · res_multistep | 3 | ⚠️缺模型 |
| `image/ark/18_方舟Seedream_机器人改图.json` | 配置部署插件目录中的 ark.local.json，填API Key并在方舟开通模型；模型留空使用配置。确认后打开 enable_api。密钥不要填进画布。参考图会上传到火山方舟，调用使用方舟账户额度。 | — | 0 | ✅ |
| `image/ark/25_方舟Seedream_写实IP三视图_表情_细节.json` | 三视图/表情集/细节均为方向探索与角度占位，按 REALISTIC_IP_BRIEF_v002 逐张核对身份后再晋级，多视图生成不构成身份一致性保证；参考图上传方舟，仅限本人授权素材；enable_api 确认参数后再开；换新结果才增大 r | — | 0 | ✅ |
| `image/flux/09_Flux2Klein_快速文生图.json` | FLUX.2 Klein 4B FP8：4步生成，默认1024×1024。图生图使用参考潜空间，直接描述修改要求。 | flux-2-klein-4b-fp8 | 3 | ⚠️缺模型 |
| `image/flux/10_Flux2Klein_指令改图.json` | FLUX.2 Klein 4B FP8：4步生成，默认1024×1024。图生图使用参考潜空间，直接描述修改要求。 | flux-2-klein-4b-fp8 | 3 | ⚠️缺模型 |
| `image/poster/POSTER_LAYERED_v001_api.json` | POSTER_LAYERED_v001_api | — | 0 | ✅ |
| `image/qwen/06_Qwen21_Turbo_文生图.json` | Qwen Image 2.1：默认1024像素；Turbo使用官方8步时间表，标准版使用40步。图生图上传参考图后，用文字描述要修改的内容。标准版与Turbo共享编码器和VAE。提示词增强器未启用，无需额外语言模型。 | qwen_image_2.1_turbo_int8_convrot | 3 | ⚠️缺模型 |
| `image/qwen/07_Qwen21_Turbo_指令改图.json` | Qwen Image 2.1：默认1024像素；Turbo使用官方8步时间表，标准版使用40步。图生图上传参考图后，用文字描述要修改的内容。标准版与Turbo共享编码器和VAE。提示词增强器未启用，无需额外语言模型。 | qwen_image_2.1_turbo_int8_convrot | 3 | ⚠️缺模型 |
| `image/qwen/08_Qwen21_标准版_文生图.json` | Qwen Image 2.1：默认1024像素；Turbo使用官方8步时间表，标准版使用40步。图生图上传参考图后，用文字描述要修改的内容。标准版与Turbo共享编码器和VAE。提示词增强器未启用，无需额外语言模型。 | qwen_image_2.1_int8_convrot · 40 步 · euler | 3 | ⚠️缺模型 |
| `image/sd15/22_SD15_文生图.json` | 22_SD15_文生图 | v1-5-pruned-emaonly-fp16 · 512x512 · 20 步 · euler | 1 | ✅ |
| `image/sdxl/01_SDXL_文生图.json` | 01_SDXL_文生图 | sd_xl_base_1.0 · 1024x1024 · 25 步 · dpmpp_2m | 1 | ⚠️缺模型 |
| `image/sdxl/02_SDXL_图生图.json` | 02_SDXL_图生图 | sd_xl_base_1.0 · 25 步 · dpmpp_2m | 1 | ⚠️缺模型 |
| `image/sdxl/16_SDXL_我的人物形象_参考照片.json` | 我的人物形象图 / SDXL 图生图 | sd_xl_base_1.0 · 56 步 · dpmpp_2m | 1 | ⚠️缺模型 |
| `image/sdxl/17_SDXL_机器人重新设计_双强度对比.json` | 机器人重新设计 / 双强度对比 | sd_xl_base_1.0 · 30 步 · dpmpp_2m | 1 | ⚠️缺模型 |
| `image/zimage/05_ZImageTurbo_快速文生图.json` | 8步快速出图；默认1024×1024。修改提示词后运行。支持中文与英文提示词。原生节点，无需额外插件。 | z_image_turbo_bf16 · 1024x1024 · 8 步 · res_multistep | 3 | ⚠️缺模型 |

## model3d

| 工作流 | 说明 | 参数 | 模型 | 校验 |
|---|---|---|---|:--:|
| `model3d/hunyuan/13_Hunyuan3D21_图片生成3D模型.json` | 3D可行性验证：单张参考图生成无贴图GLB网格。默认官方示例图、30步、4096潜变量、256网格解码分辨率。输出不是已绑定角色：仍需要拓扑整理、UV/材质、骨骼和蒙皮。可将GLB导入Blender继续制作。 | 30 步 · euler | 1 | ⚠️缺模型 |

## video

| 工作流 | 说明 | 参数 | 模型 | 校验 |
|---|---|---|---|:--:|
| `video/ark/19_方舟Seedance_机器人图生视频.json` | 配置部署插件目录中的 ark.local.json，填API Key并在方舟开通模型；模型留空使用配置。确认后打开 enable_api。密钥不要填进画布。参考图会上传到火山方舟，调用使用方舟账户额度。 | — | 0 | ✅ |
| `video/ark/20_方舟Seedance_已有任务取回.json` | 填写已有任务ID，使用同一方舟账户的配置。此工作流只查询和下载，不创建新生成任务。可用于恢复超时任务；任务和下载地址存在有效期，完成后尽快保存。 | — | 0 | ✅ |
| `video/ark/21_方舟Seedance_文生视频.json` | 配置部署插件目录中的 ark.local.json，填API Key并在方舟开通模型；模型留空使用配置。确认后打开 enable_api。密钥不要填进画布。参考图会上传到火山方舟，调用使用方舟账户额度。 | — | 0 | ✅ |
| `video/ltx/12_LTX23_有声视频.json` | LTX 2.3 FP8 + 蒸馏LoRA：默认640×384、49帧、24fps，约2秒，联合生成画面与声音。提示词同时描述动作、镜头和声音。先320×192生成，再通过潜空间放大与3步细化得到640×384，以控制显存。不要直接设置长片或 | ltx-2.3-22b-dev-fp8 · 320 帧 | 4 | ⚠️缺模型 |
| `video/wan/03_Wan22_文生视频.json` | 本机视频工作流 | wan2.2_ti2v_5B_fp16 · 20 步 · uni_pc | 3 | ⚠️缺模型 |
| `video/wan/04_Wan22_图生视频.json` | 本机视频工作流 | wan2.2_ti2v_5B_fp16 · 20 步 · uni_pc | 3 | ⚠️缺模型 |
| `video/wan/11_Wan22_14B_图生视频.json` | Wan 2.2 14B FP8高低噪声模型 + LightX2V 4步LoRA。默认640×384、49帧、16fps，约3秒无声短片。上传参考图并描述动作；尺寸、时长提高会增加显存和耗时。 | wan2.2_i2v_high_noise_14B_fp8_scaled | 6 | ⚠️缺模型 |
| `video/wan/23_Wan21_13B_文生视频.json` | 23_Wan21_13B_文生视频 | wan2.1_t2v_1.3B_fp16 · 20 步 · 416 帧 · uni_pc | 3 | ✅ |
