// v002: layered poster with a smaller, positioned subject layer and cleaner top space.
const COMFY = 'http://127.0.0.1:8188';
const fs = require('node:fs');

const CKPT = process.env.CKPT || 'RealVisXL_V5.0_fp16.safetensors';
const W = 1152, H = 1536;
const STEPS = Number(process.env.STEPS || 30), CFG = Number(process.env.CFG || 6.5);

const NEG = 'text, letters, watermark, signature, logo, people, human, face, hands, low quality, worst quality, jpeg artifacts, blurry, oversaturated, cluttered, multiple objects';

const BG = process.env.BG || 'empty dark theatre stage, almost black, soft violet haze rising from the floor, faint cyan grid lines on the dark floor, huge empty black space in the upper half, cinematic volumetric light, minimal, poster background, no text';
const GLOW = process.env.GLOW || 'soft violet to cyan volumetric haze and a single diagonal light shaft, wispy smoke, isolated on pure black background, no objects, no text';
const PART = process.env.PART || 'fine dust particles and tiny sparks floating in darkness, sparse bokeh, isolated on pure black background, no text';
const SUBJ = process.env.SUBJ || 'a small translucent glass rectangular panel standing upright on a dark stage floor, faint thin grid etched on the glass, cyan rim light on edges, isolated on pure black background, distant, minimal, no text';

const g = {};
const add = (id, class_type, inputs) => { g[id] = { class_type, inputs }; };

add('1', 'CheckpointLoaderSimple', { ckpt_name: CKPT });
add('2', 'CLIPTextEncode', { text: BG, clip: ['1', 1] });
add('3', 'CLIPTextEncode', { text: NEG, clip: ['1', 1] });
add('4', 'EmptyLatentImage', { width: W, height: H, batch_size: 1 });
add('5', 'KSampler', { model: ['1', 0], seed: 771001, steps: STEPS, cfg: CFG, sampler_name: 'dpmpp_2m', scheduler: 'karras', positive: ['2', 0], negative: ['3', 0], latent_image: ['4', 0], denoise: 1.0 });
add('6', 'VAEDecode', { samples: ['5', 0], vae: ['1', 2] });
add('7', 'SaveImage', { images: ['6', 0], filename_prefix: 'qbank_poster_v002/L1_background' });

add('8', 'CLIPTextEncode', { text: GLOW, clip: ['1', 1] });
add('9', 'EmptyLatentImage', { width: W, height: H, batch_size: 1 });
add('10', 'KSampler', { model: ['1', 0], seed: 771002, steps: STEPS, cfg: CFG, sampler_name: 'dpmpp_2m', scheduler: 'karras', positive: ['8', 0], negative: ['3', 0], latent_image: ['9', 0], denoise: 1.0 });
add('11', 'VAEDecode', { samples: ['10', 0], vae: ['1', 2] });
add('12', 'SaveImage', { images: ['11', 0], filename_prefix: 'qbank_poster_v002/L2_glow' });

add('13', 'CLIPTextEncode', { text: PART, clip: ['1', 1] });
add('14', 'EmptyLatentImage', { width: W, height: H, batch_size: 1 });
add('15', 'KSampler', { model: ['1', 0], seed: 771003, steps: STEPS, cfg: CFG, sampler_name: 'dpmpp_2m', scheduler: 'karras', positive: ['13', 0], negative: ['3', 0], latent_image: ['14', 0], denoise: 1.0 });
add('16', 'VAEDecode', { samples: ['15', 0], vae: ['1', 2] });
add('17', 'SaveImage', { images: ['16', 0], filename_prefix: 'qbank_poster_v002/L3_particles' });

add('18', 'CLIPTextEncode', { text: SUBJ, clip: ['1', 1] });
add('19', 'EmptyLatentImage', { width: W, height: H, batch_size: 1 });
add('20', 'KSampler', { model: ['1', 0], seed: 771004, steps: STEPS, cfg: CFG, sampler_name: 'dpmpp_2m', scheduler: 'karras', positive: ['18', 0], negative: ['3', 0], latent_image: ['19', 0], denoise: 1.0 });
add('21', 'VAEDecode', { samples: ['20', 0], vae: ['1', 2] });
add('22', 'SaveImage', { images: ['21', 0], filename_prefix: 'qbank_poster_v002/L4_subject' });

// subject: scale down to 55% and position in the lower third
const SW = Math.round(W * 0.55), SH = Math.round(H * 0.55);
add('30', 'ImageScale', { image: ['21', 0], upscale_method: 'lanczos', width: SW, height: SH, crop: 'center' });
add('31', 'ImageToMask', { image: ['30', 0], channel: 'red' });
add('32', 'GrowMask', { mask: ['31', 0], expand: 4, tapered_corners: true });

// composite chain
add('40', 'ImageBlend', { image1: ['6', 0], image2: ['11', 0], blend_factor: 0.5, blend_mode: 'screen' });
add('41', 'ImageBlend', { image1: ['40', 0], image2: ['16', 0], blend_factor: 0.4, blend_mode: 'screen' });
add('42', 'ImageCompositeMasked', { destination: ['41', 0], source: ['30', 0], x: Math.round((W - SW) / 2), y: H - SH - 96, resize_source: false, mask: ['32', 0] });
add('43', 'ImageSharpen', { image: ['42', 0], sharpen_radius: 2, sigma: 0.8, alpha: 0.3 });
add('44', 'SaveImage', { images: ['43', 0], filename_prefix: process.env.OUT_PREFIX || 'qbank_poster_v002/FINAL_poster' });

fs.writeFileSync('C:/Users/rvo04/AppData/Local/Temp/qbshot/poster/poster_layered_v002_api.json', JSON.stringify(g, null, 2));

(async () => {
  const res = await fetch(COMFY + '/prompt', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ prompt: g, client_id: 'qbank-poster-v2' }) });
  const body = await res.json();
  if (!res.ok) { console.log('PROMPT_ERR', JSON.stringify(body).slice(0, 900)); process.exit(1); }
  const id = body.prompt_id;
  console.log('PROMPT_ID', id);
  for (let i = 0; i < 240; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const h = await fetch(COMFY + '/history/' + id).then((r) => r.json());
    if (h[id]) {
      const st = h[id].status || {};
      const err = (st.messages || []).find((m) => m[0] === 'execution_error');
      if (err) { console.log('EXEC_ERROR', JSON.stringify(err[1]).slice(0, 900)); process.exit(1); }
      const outs = h[id].outputs || {};
      const files = [];
      for (const k of Object.keys(outs)) for (const im of (outs[k].images || [])) files.push(im.subfolder + '/' + im.filename);
      if (files.length) { console.log('DONE', JSON.stringify(files)); return; }
    }
  }
  console.log('TIMEOUT');
})();
