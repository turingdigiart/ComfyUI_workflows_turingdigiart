#!/usr/bin/env node
// 环境自检：用一条最小 SDXL 链路真跑一次，确认 ComfyUI 能出图。
// 目的不是画质，是确认"模型能加载、能排队、能执行、能落盘"。
// 用法: node scripts/smoke.mjs [--steps 6] [--size 512] [--ckpt sd_xl_base_1.0.safetensors] [--keep]
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const val = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const has = k => args.includes(k);
const base = process.env.COMFYUI_BASE || 'http://127.0.0.1:8188';
const steps = Number(val('--steps', '6'));
const size = Number(val('--size', '512'));
const ckpt = val('--ckpt', 'sd_xl_base_1.0.safetensors');

const prompt = {
  '3': { class_type: 'KSampler', inputs: { seed: 12345, steps, cfg: 6, sampler_name: 'euler', scheduler: 'normal', denoise: 1, model: ['4', 0], positive: ['6', 0], negative: ['7', 0], latent_image: ['5', 0] } },
  '4': { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: ckpt } },
  '5': { class_type: 'EmptyLatentImage', inputs: { width: size, height: size, batch_size: 1 } },
  '6': { class_type: 'CLIPTextEncode', inputs: { text: 'a red apple on a wooden table, studio light', clip: ['4', 1] } },
  '7': { class_type: 'CLIPTextEncode', inputs: { text: 'blurry, watermark', clip: ['4', 1] } },
  '8': { class_type: 'VAEDecode', inputs: { samples: ['3', 0], vae: ['4', 2] } },
  '9': { class_type: 'SaveImage', inputs: { images: ['8', 0], filename_prefix: 'tech-comfy-smoke' } }
};

const t0 = Date.now();
try {
  const info = await (await fetch(base + '/object_info')).json();
  console.log('节点库: ' + Object.keys(info).length + ' 个类型');

  const r = await fetch(base + '/prompt', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ prompt, client_id: 'tech-comfy-smoke' }) });
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error('排队失败 ' + r.status + ' ' + JSON.stringify(body));
  const id = body.prompt_id;
  console.log('已排队: ' + id);

  let done = null;
  for (let i = 0; i < 300; i++) {
    await new Promise(res => setTimeout(res, 1000));
    const h = await (await fetch(base + '/history/' + encodeURIComponent(id))).json();
    if (h[id]) { done = h[id]; break; }
  }
  if (!done) throw new Error('超时 300s');

  const files = [];
  for (const o of Object.values(done.outputs || {})) for (const f of (o.images || [])) files.push(f);
  if (!files.length) throw new Error('执行完成但没有图片产出');

  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`完成: ${files.length} 个文件, 耗时 ${secs}s`);
  for (const f of files) console.log('  ' + (f.subfolder ? f.subfolder + '/' : '') + f.filename);
  console.log('环境自检: 通过');
  process.exitCode = 0;
} catch (e) {
  console.error('环境自检: 失败 — ' + e.message);
  process.exitCode = 1;
}