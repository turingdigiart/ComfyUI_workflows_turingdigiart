#!/usr/bin/env node
// Qwen prompt enhancer (TECH-COMFY-001): runs recipes/image/qwen/10_prompt_enhancer.api.json
// through the local ComfyUI TextGenerate node and prints/writes the enhanced prompt.
//
// Usage:
//   node scripts/enhance-qwen-prompt.mjs --brief "竖版3:4纸感背景，左下墨绿..." --seed 101
//   node scripts/enhance-qwen-prompt.mjs --brief "..." --out out/enhanced.txt
//   node scripts/enhance-qwen-prompt.mjs --brief "..." --dry-run
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');
const RECIPE = path.join(ROOT, 'recipes', 'image', 'qwen', '10_prompt_enhancer.api.json');
const args = process.argv.slice(2);
const has = k => args.includes(k);
const val = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const BASE = (val('--base') || process.env.COMFYUI_BASE || 'http://127.0.0.1:8188').replace(/\/$/, '');

async function main() {
  if (!fs.existsSync(RECIPE)) throw new Error('missing recipe: ' + RECIPE);
  let recipe = JSON.parse(fs.readFileSync(RECIPE, 'utf8').replace(/^\uFEFF/, ''));
  if (recipe.prompt) recipe = recipe.prompt;
  const nodeId = Object.keys(recipe).find(id => recipe[id]?.class_type === 'TextGenerate');
  if (!nodeId) throw new Error('recipe has no TextGenerate node');
  const node = recipe[nodeId];
  const brief = val('--brief');
  if (!brief) throw new Error('missing --brief "..."');
  const seed = Number(val('--seed', '42'));
  node.inputs.prompt = brief;
  node.inputs['sampling_mode.seed'] = seed;
  const sysFile = val('--system-prompt-file');
  if (sysFile) node.inputs.system_prompt = fs.readFileSync(path.resolve(sysFile), 'utf8');
  console.log(JSON.stringify({ recipe: path.relative(ROOT, RECIPE), seed, briefChars: brief.length }, null, 2));
  if (has('--dry-run')) { console.log('--dry-run: not queued'); return; }
  const info = await (await fetch(BASE + '/object_info')).json();
  const gen = info.TextGenerate;
  if (!gen) throw new Error('TextGenerate node not installed');
  const clipNode = Object.values(recipe).find(n => n && n.class_type === 'CLIPLoader');
  const clipName = clipNode?.inputs?.clip_name;
  const clips = info.CLIPLoader?.input?.required?.clip_name?.[0] || [];
  if (!clipName || !clips.includes(clipName)) throw new Error('PE model not visible in CLIPLoader enum; restart ComfyUI after download: ' + (clipName || 'unknown'));
  const started = Date.now();
  const queued = await (await fetch(BASE + '/prompt', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ prompt: recipe, client_id: 'enhance-qwen-prompt' }) })).json();
  if (!queued.prompt_id) throw new Error('queue failed: ' + JSON.stringify(queued));
  const id = queued.prompt_id;
  console.log('queued prompt_id=' + id);
  const deadline = started + Number(val('--timeout', '1800000'));
  let history = null;
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, 2000));
    const h = await (await fetch(BASE + '/history/' + id)).json();
    if (h[id]) { history = h[id]; break; }
  }
  if (!history) throw new Error('timeout waiting prompt ' + id);
  if (history.status?.status_str !== 'success') throw new Error('prompt failed: ' + JSON.stringify(history.status));
  const texts = [];
  for (const out of Object.values(history.outputs || {})) {
    if (Array.isArray(out.text)) texts.push(...out.text);
    else if (typeof out.text === 'string') texts.push(out.text);
    if (typeof out.generated_text === 'string') texts.push(out.generated_text);
  }
  const text = texts.filter(Boolean).join('\n').trim();
  if (!text) throw new Error('no text output in history; inspect /history/' + id);
  const elapsed_s = Math.round((Date.now() - started) / 1000);
  const outFile = val('--out');
  if (outFile) { fs.mkdirSync(path.dirname(path.resolve(outFile)), { recursive: true }); fs.writeFileSync(path.resolve(outFile), text + '\n', 'utf8'); }
  console.log(JSON.stringify({ prompt_id: id, elapsed_s, chars: text.length, out: outFile || null }, null, 2));
  console.log('--- enhanced prompt ---');
  console.log(text);
}

main().catch(e => { console.error('ERROR: ' + e.message); process.exitCode = 1; });
