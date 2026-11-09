// 把 quality-cases.json 展开成 promptfoo 测试用例。
// 评分用 llm-rubric，断言只看该 SOP 的硬规则是否被保留。
// v2 起用例指向原子编号（atom），原文由原子内的 source_text 提供。
const cases = require('./quality-cases.json');

module.exports = async function () {
  return cases.cases.map((c) => ({
    description: `${c.id} ${c.title}`,
    vars: { atom: c.atom, task: c.task },
    metadata: { id: c.id, atom: c.atom },
    assert: [
      {
        type: 'llm-rubric',
        value: c.rubric,
        threshold: 0.7,
        metric: 'SOP 硬规则',
      },
    ],
  }));
};
