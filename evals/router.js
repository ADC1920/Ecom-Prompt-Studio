// 触发回归的提示词构造器：每次运行时从仓库读取三个技能的 SKILL.md，
// 因此路由表或 description 一改，评测输入立刻跟着变，不需要手工同步副本。
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), 'utf8');
}

function splitFrontmatter(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (!m) return { frontmatter: '', body: text };
  const fm = m[1];
  const desc = (fm.match(/^description:\s*([\s\S]*?)$/m) || [])[1] || '';
  return {
    description: desc.trim().replace(/^["']|["']$/g, ''),
    body: text.slice(m[0].length),
  };
}

function loadSkill(name) {
  return splitFrontmatter(read(`${name}/SKILL.md`));
}

module.exports = async function ({ vars }) {
  const router = loadSkill('ecom-prompt-sop');
  const mainImage = loadSkill('ecom-main-image-prompts');
  const detailPage = loadSkill('ecom-detail-page-prompts');

  const system = [
    '你是技能路由器，只做一件事：根据用户请求，从给定技能中选出唯一最匹配的一个，并选出要读的 SOP 文档。',
    '',
    '判定顺序：',
    '1. 先看三个技能的 description，判断哪个技能被触发；都不相关时 skill 输出 none。',
    '2. 命中 ecom-prompt-sop 时，严格按它正文的「使用流程」与「路由表」选出唯一最匹配的 SOP。',
    '3. 若请求是裸主图或裸详情页，按 ecom-prompt-sop 使用流程第 2 步的第一判据转交给对应导演技能。',
    '',
    '只输出一个 JSON 对象，不要 markdown 代码块，不要解释文字：',
    '{"skill": "...", "doc": "...", "reason": "..."}',
    'skill 取值：ecom-prompt-sop | ecom-main-image-prompts | ecom-detail-page-prompts | none',
    'doc：命中 ecom-prompt-sop 时照抄路由表里的 references/ 相对路径；其他情况填空字符串。',
    '',
    '===== 技能一：ecom-prompt-sop =====',
    'description: ' + router.description,
    router.body,
    '',
    '===== 技能二：ecom-main-image-prompts =====',
    'description: ' + mainImage.description,
    '（本技能负责裸主图方案：用户没有品类专项线索、也没点名本库 SOP 时，主图请求转交给它。）',
    '',
    '===== 技能三：ecom-detail-page-prompts =====',
    'description: ' + detailPage.description,
    '（本技能负责裸详情页方案：用户没有品类专项线索、也没点名本库 SOP 时，详情页请求转交给它。）',
  ].join('\n');

  return [
    { role: 'system', content: system },
    { role: 'user', content: String(vars.input) },
  ];
};
