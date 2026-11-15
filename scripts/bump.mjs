#!/usr/bin/env node
// 从现有工作流派生一个新版本（_vNNN_ 递增，绝不覆盖）。
// 用法: node scripts/bump.mjs --workflow <path/to/x.json> [--label 说明]
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const val = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const src = val('--workflow');
const label = val('--label', '');
if (!src) { console.error('缺 --workflow <path>'); process.exitCode = 2; }
else {
  const abs = path.resolve(src);
  if (!fs.existsSync(abs)) { console.error('文件不存在: ' + abs); process.exitCode = 2; }
  else {
    const dir = path.dirname(abs);
    const name = path.basename(abs, '.json');
    // 去掉已有的 _vNNN_ 与说明后缀，得到基名
    const base = name.replace(/_v\d{3}.*$/, '');
    // 扫同目录，找同基名的最大版本号
    let max = 0;
    for (const f of fs.readdirSync(dir)) {
      if (!f.endsWith('.json')) continue;
      const m = f.match(new RegExp('^' + base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '_v(\\d{3})'));
      if (m) max = Math.max(max, Number(m[1]));
    }
    const next = 'v' + String(max + 1).padStart(3, '0');
    const suffix = label ? '_' + label.replace(/[\\/:*?"<>|\s]+/g, '-') : '';
    const target = path.join(dir, `${base}_${next}${suffix}.json`);
    if (fs.existsSync(target)) { console.error('目标已存在，拒绝覆盖: ' + target); process.exitCode = 1; }
    else {
      fs.copyFileSync(abs, target);
      console.log('已派生: ' + path.relative(process.cwd(), target));
      console.log('来源: ' + path.relative(process.cwd(), abs));
      console.log('下一步: node scripts/catalog.mjs 重建台账，再 node scripts/verify.mjs 校验');
    }
  }
}