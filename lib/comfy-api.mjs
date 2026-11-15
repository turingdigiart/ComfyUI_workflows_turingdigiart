// ComfyUI 本地 API 客户端。只读为主：查询节点、排队、取历史。
const BASE = process.env.COMFYUI_BASE || 'http://127.0.0.1:8188';

export async function objectInfo() {
  const r = await fetch(BASE + '/object_info');
  if (!r.ok) throw new Error('object_info 返回 ' + r.status);
  return r.json();
}

export async function systemStats() {
  const r = await fetch(BASE + '/system_stats');
  if (!r.ok) throw new Error('system_stats 返回 ' + r.status);
  return r.json();
}

export async function queuePrompt(prompt, clientId = 'tech-comfy-001') {
  const r = await fetch(BASE + '/prompt', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ prompt, client_id: clientId })
  });
  return { status: r.status, body: await r.json().catch(() => null) };
}

export async function history(promptId) {
  const r = await fetch(BASE + '/history/' + encodeURIComponent(promptId));
  if (!r.ok) throw new Error('history 返回 ' + r.status);
  return r.json();
}

export async function isUp() {
  try { const r = await fetch(BASE + '/system_stats', { signal: AbortSignal.timeout(3000) }); return r.ok; }
  catch { return false; }
}

export const base = BASE;