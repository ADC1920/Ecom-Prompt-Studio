// 路由断言：解析模型输出的 JSON，比较技能名与 SOP 文档路径。
// 比较是「包含」而不是全等，这样重命名 SOP 文件名后缀不会误报，
// 但选错分类目录（比如包包类选成服饰类）一定会失败。
function normalize(value) {
  return String(value == null ? '' : value)
    .replace(/\\/g, '/')
    .replace(/^\.\//, '')
    .replace(/^references\//, '')
    .replace(/[`"'\s]+$/g, '')
    .trim();
}

function extractJson(text) {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = fenced ? fenced[1] : text;
  const start = candidate.indexOf('{');
  if (start === -1) return null;
  // 先试首尾配对，失败再从后往前收缩，避免字符串里的花括号干扰。
  const ends = [];
  for (let i = candidate.length - 1; i > start; i--) {
    if (candidate[i] === '}') ends.push(i);
  }
  for (const end of ends) {
    try {
      return JSON.parse(candidate.slice(start, end + 1));
    } catch {
      // 继续尝试更短的片段
    }
  }
  return null;
}

const NONE_ALIASES = new Set(['none', 'null', '无', '不适用', 'n/a', 'na', '-']);

function normalizeSkill(value) {
  const s = String(value == null ? '' : value)
    .toLowerCase()
    .replace(/^skill\s*[:：=]\s*/, '')
    .replace(/[`"'。.\s]/g, '')
    .trim();
  return NONE_ALIASES.has(s) ? 'none' : s;
}

const SKILL_NAMES = ['ecom-prompt-sop', 'ecom-main-image-prompts', 'ecom-detail-page-prompts'];

function extractFromText(text) {
  const lower = text.toLowerCase();
  const hits = SKILL_NAMES.filter((s) => lower.includes(s));
  if (hits.length !== 1) return null;
  const doc = (text.match(/references\/[^`|\]\n"'）)]+?\.md/) || [])[0] || '';
  return { skill: hits[0], doc, reason: '从纯文本输出中提取（非 JSON）' };
}

module.exports = (output, context) => {
  const expect = (context && context.config) || {};
  const expectedSkill = expect.skill;
  const docContains = expect.doc_contains ? normalize(expect.doc_contains) : '';

  const text = typeof output === 'string' ? output : JSON.stringify(output);
  const parsed = extractJson(text) || extractFromText(text);
  if (!parsed) {
    return {
      pass: false,
      score: 0,
      reason: '输出中没有可解析的路由结论（既无 JSON，也无法唯一识别技能名）',
    };
  }

  const gotSkill = normalizeSkill(parsed.skill);
  if (gotSkill !== expectedSkill) {
    return {
      pass: false,
      score: 0,
      reason: `技能不符：期望 ${expectedSkill}，实际 ${gotSkill || '(空)'}｜模型理由 ${parsed.reason || '(无)'}`,
    };
  }

  if (docContains) {
    const gotDoc = normalize(parsed.doc);
    if (!gotDoc.includes(docContains)) {
      return {
        pass: false,
        score: 0,
        reason: `SOP 不符：期望包含 ${docContains}，实际 ${gotDoc || '(空)'}｜模型理由 ${parsed.reason || '(无)'}`,
      };
    }
  }

  return {
    pass: true,
    score: 1,
    reason: `命中 ${gotSkill}${docContains ? ' / ' + normalize(parsed.doc) : ''}`,
  };
};
