// 质量抽检的提示词构造器：把指定 SOP 原文完整放进上下文，让模型按原文执行。
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

module.exports = async function ({ vars }) {
  const sop = fs.readFileSync(path.join(ROOT, vars.sop), 'utf8');
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
