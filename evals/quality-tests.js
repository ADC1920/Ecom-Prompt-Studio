// 把 quality-cases.json 展开成 promptfoo 测试用例。
// 评分用 llm-rubric，断言只看该 SOP 的硬规则是否被保留。
const cases = require('./quality-cases.json');

module.exports = async function () {
  return cases.cases.map((c) => ({
    description: `${c.id} ${c.title}`,
    vars: { sop: c.sop, task: c.task },
    metadata: { id: c.id, sop: c.sop },
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
