// 质量抽检的提示词构造器：把指定原子的原文全文放进上下文，让模型按原文执行。
// v3 起从原子读 source_text，不再依赖 references 下的 SOP 文件。
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

module.exports = async function ({ vars }) {
  const id = String(vars.atom || '').trim();
  const file = path.join(ROOT, 'ecom-prompt-sop', 'references', '_atoms', `${id}.json`);
  const atom = JSON.parse(fs.readFileSync(file, 'utf8'));
  const sop = atom.source_text || '';
  if (!sop) {
    throw new Error(`原子 ${id} 没有 source_text，无法做质量抽检`);
  }
  return [
    {
      role: 'system',
      content: [
        '你是电商生图提示词执行助手。严格按下述 SOP 原文产出提示词，不得删减或弱化其中的硬规则。',
        '只输出最终提示词或最终交付内容，不要解释你做了什么。',
        '',
        '===== SOP 原文开始 =====',
        sop,
        '===== SOP 原文结束 =====',
      ].join('\n'),
    },
    { role: 'user', content: String(vars.task) },
  ];
};
