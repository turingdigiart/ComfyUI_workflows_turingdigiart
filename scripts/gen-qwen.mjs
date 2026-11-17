#!/usr/bin/env node
// Qwen local image recipe runner (TECH-COMFY-001).
// Runs an API-format recipe against a local ComfyUI, patches prompt/size/seed/image,
// waits for completion and downloads the resulting images.
//
// Usage:
//   node scripts/gen-qwen.mjs --list
//   node scripts/gen-qwen.mjs --recipe recipes/image/qwen/06_turbo_t2i_3x4.api.json --prompt "..." --out-dir out
//   node scripts/gen-qwen.mjs --recipe ... --prompt "..." --width 1152 --height 1536 --seed 123 --dry-run
//
// No dependencies: Node >= 18 (global fetch).
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');
const RECIPE_DIR = path.join(ROOT, 'recipes', 'image', 'qwen');
const args = process.argv.slice(2);
const has = k => args.includes(k);
const val = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const BASE = (val('--base') || process.env.COMFYUI_BASE || 'http://127.0.0.1:8188').replace(/\/$/, '');

function listRecipes() {
  if (!fs.existsSync(RECIPE_DIR)) throw new Error('recipe dir not found: ' + RECIPE_DIR);
  for (const f of fs.readdirSync(RECIPE_DIR).filter(x => x.endsWith('.api.json')).sort()) {
    console.log('recipes/image/qwen/' + f);
  }
}

function patch(prompt, rc) {
  const input = rc.input || {};
  const nodes = Object.entries(prompt);
  const set = (node) => { if (node) node.inputs = { ...node.inputs, ...input }; };
  let promptNode = null, latentNode = null, seedNode = null, saveNode = null, imageNode = null;
  const promptTypes = new Set(['TextEncodeQwenImage21', 'CLIPTextEncode', 'TextEncodeQwenImageEdit', 'TextEncodeQwenImageEditPlus']);
  for (const [, n] of nodes) {
    if (!n || !n.class_type) continue;
    if (!promptNode && promptTypes.has(n.class_type)) promptNode = n;
    if (!latentNode && (n.class_type === 'EmptyLatentImage' || n.class_type === 'EmptySD3LatentImage')) latentNode = n;
    if (!seedNode && (n.class_type === 'RandomNoise' || n.class_type === 'KSampler')) seedNode = n;
    if (!saveNode && /SaveImage/.test(n.class_type)) saveNode = n;
    if (!imageNode && n.class_type === 'LoadImage') imageNode = n;
  }
  if (!promptNode) throw new Error('no prompt node found (TextEncodeQwenImage21 / CLIPTextEncode)');
  if (rc.prompt != null) {
    if ('negative_prompt' in promptNode.inputs || promptNode.class_type === 'TextEncodeQwenImage21') promptNode.inputs.prompt = rc.prompt;
    else if ('text' in promptNode.inputs) promptNode.inputs.text = rc.prompt;
    else promptNode.inputs.prompt = rc.prompt;
  }
  if (rc.negative != null && 'negative_prompt' in promptNode.inputs) promptNode.inputs.negative_prompt = rc.negative;
  if (rc.width != null || rc.height != null) {
    if (!latentNode) throw new Error('recipe has no EmptyLatentImage/EmptySD3LatentImage; cannot patch size');
    if (rc.width != null) latentNode.inputs.width = rc.width;
    if (rc.height != null) latentNode.inputs.height = rc.height;
  }
  if (rc.seed != null) {
    if (!seedNode) throw new Error('recipe has no RandomNoise/KSampler; cannot patch seed');
    if (seedNode.class_type === 'RandomNoise') seedNode.inputs.noise_seed = rc.seed;
    else seedNode.inputs.seed = rc.seed;
  }
  if (rc.image != null) {
    if (!imageNode) throw new Error('recipe has no LoadImage node; --image unsupported for this recipe');
    imageNode.inputs.image = rc.image;
  }
  if (rc.prefix != null && saveNode) saveNode.inputs.filename_prefix = rc.prefix;
  return { prompt, promptNode: promptNode.class_type, latentNode: latentNode?.class_type || null, seedNode: seedNode?.class_type || null, saveNode: saveNode?.class_type || null };
}

async function main() {
  if (has('--list')) { listRecipes(); return; }
  const recipePath = val('--recipe');
  if (!recipePath) throw new Error('missing --recipe <path> (use --list)');
  const abs = path.resolve(recipePath);
  let raw = JSON.parse(fs.readFileSync(abs, 'utf8').replace(/^\uFEFF/, ''));
  let prompt = raw.prompt || raw;
  const rc = {
    prompt: val('--prompt'), negative: val('--negative'),
    width: val('--width') != null ? Number(val('--width')) : null,
    height: val('--height') != null ? Number(val('--height')) : null,
    seed: val('--seed') != null ? Number(val('--seed')) : null,
    image: val('--image'), prefix: val('--prefix')
  };
  const meta = patch(prompt, rc);
  const info = await (await fetch(BASE + '/object_info')).json();
  const problems = [];
  for (const [id, n] of Object.entries(prompt)) {
    if (!n || !n.class_type) { problems.push(`node ${id} missing class_type`); continue; }
    const def = info[n.class_type];
    if (!def) { problems.push(`node ${id} type not installed: ${n.class_type}`); continue; }
    const required = Object.keys(def.input?.required || {});
    for (const k of required) {
      if (k in (n.inputs || {})) continue;
      const spec = def.input?.required?.[k];
      const type = Array.isArray(spec) ? spec[0] : spec;
      // Autogrow groups are allowed to be absent; optional keys are marked in the spec options.
      if (typeof type === 'string' && type.startsWith('COMFY_AUTOGROW')) continue;
      if (spec && spec[1] && spec[1].optional === true) continue;
      problems.push(`node ${id} missing input ${k}`);
    }
  }
  if (problems.length) throw new Error('validation failed:\n' + problems.join('\n'));
  console.log(JSON.stringify({ recipe: path.relative(ROOT, abs), nodes: Object.keys(prompt).length, ...meta }, null, 2));
  if (has('--dry-run')) { console.log('--dry-run: not queued'); return; }
  const started = Date.now();
  const queued = await (await fetch(BASE + '/prompt', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ prompt, client_id: 'gen-qwen' }) })).json();
  if (!queued.prompt_id) throw new Error('queue failed: ' + JSON.stringify(queued));
  const id = queued.prompt_id;
  console.log('queued prompt_id=' + id);
  const deadline = started + Number(val('--timeout', '3600000'));
  let history = null;
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, 3000));
    const h = await (await fetch(BASE + '/history/' + id)).json();
    if (h[id]) { history = h[id]; break; }
  }
  if (!history) throw new Error('timeout waiting for prompt ' + id);
  if (history.status?.status_str !== 'success') throw new Error('prompt failed: ' + JSON.stringify(history.status));
  const outDir = path.resolve(val('--out-dir', 'out'));
  fs.mkdirSync(outDir, { recursive: true });
  const images = [];
  for (const nodeOut of Object.values(history.outputs || {})) {
    for (const img of (nodeOut.images || [])) {
      if (img.type && img.type !== 'output') continue;
      const q = new URLSearchParams({ filename: img.filename, subfolder: img.subfolder || '', type: 'output' });
      const res = await fetch(BASE + '/view?' + q.toString());
      if (!res.ok) throw new Error('download failed: ' + res.status);
      const buf = Buffer.from(await res.arrayBuffer());
      const file = path.join(outDir, img.filename);
      fs.writeFileSync(file, buf);
      images.push({ path: file, bytes: buf.length, filename: img.filename, subfolder: img.subfolder || '' });
    }
  }
  const elapsed_s = Math.round((Date.now() - started) / 1000);
  console.log(JSON.stringify({ prompt_id: id, elapsed_s, images }, null, 2));
}

main().catch(e => { console.error('ERROR: ' + e.message); process.exitCode = 1; });
