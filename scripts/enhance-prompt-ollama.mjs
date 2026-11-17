#!/usr/bin/env node
// Local Qwen prompt enhancer via Ollama (tested path; no cloud).
// Uses the locally installed qwen35-9b-flash:latest to rewrite a Chinese/English brief
// into one detailed English image prompt for Qwen-Image 2.1 / original Qwen.
//
// Usage:
//   node scripts/enhance-prompt-ollama.mjs --brief "竖版 3:4 纸感背景..." --out out/enhanced.txt
//   node scripts/enhance-prompt-ollama.mjs --brief "..." --dry-run
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const has = k => args.includes(k);
const val = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const BASE = (val('--base') || process.env.OLLAMA_BASE || 'http://127.0.0.1:11434').replace(/\/$/, '');
const MODEL = val('--model', 'qwen35-9b-flash:latest');
const brief = val('--brief');
if (!brief) { console.error('ERROR: missing --brief "..."'); process.exit(2); }

const instruction = `You are a senior art director writing image-generation prompts. Rewrite the user's brief into ONE continuous English paragraph of 100-150 words, describing the finished image as an observer. It must be a vertical 3:4 pure abstract paper/studio background with no text, no letters, no logo, no watermark, no people. Specify the material and its texture, the exact palette with modifiers, where the ink/shadow sits, the light source and direction, and the clean negative space reserved for a headline. Output the paragraph only, no preamble, no analysis, no quotes.

User brief: ${brief}`;

console.log(JSON.stringify({ engine: 'ollama', model: MODEL, base: BASE, briefChars: brief.length }, null, 2));
if (has('--dry-run')) { console.log('--dry-run: not called'); process.exit(0); }

const res = await fetch(BASE + '/api/generate', {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ model: MODEL, prompt: instruction, raw: true, stream: false, keep_alive: 0, options: { temperature: Number(val('--temperature', '0.7')), num_predict: Number(val('--num-predict', '3000')) } })
});
if (!res.ok) { console.error('ERROR: ollama HTTP ' + res.status); process.exit(1); }
let data = await res.json();
let text = String(data.response || '').trim();
// Qwen3.5 may emit its reasoning inside <think>...</think>; if the tag is unclosed the
// generation budget was exhausted before the final paragraph — retry with a larger budget.
let budget = Number(val('--num-predict', '3000'));
for (let attempt = 1; attempt <= 3; attempt++) {
  if (text.includes('</think>')) { text = text.slice(text.lastIndexOf('</think>') + 8).trim(); break; }
  if (!text.includes('<think>')) break;
  if (attempt === 3) { console.error('ERROR: model kept emitting unclosed <think>; raise --num-predict or shorten brief'); process.exit(1); }
  budget = Math.min(budget * 2, 12000);
  console.error(`WARN: unclosed <think>, retry ${attempt + 1}/3 with num_predict=${budget}`);
  const retry = await fetch(BASE + '/api/generate', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ model: MODEL, prompt: instruction, raw: true, stream: false, keep_alive: 0, options: { temperature: Number(val('--temperature', '0.7')), num_predict: budget } })
  });
  if (!retry.ok) { console.error('ERROR: ollama HTTP ' + retry.status); process.exit(1); }
  data = await retry.json();
  text = String(data.response || '').trim();
}
if (!text) { console.error('ERROR: empty response (model may have exhausted token budget while thinking; raise --num-predict)'); process.exit(1); }
const out = val('--out');
if (out) { fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true }); fs.writeFileSync(path.resolve(out), text + '\n', 'utf8'); }
console.log(JSON.stringify({ chars: text.length, out: out ? path.resolve(out) : null }, null, 2));
console.log('--- enhanced prompt ---');
console.log(text);
