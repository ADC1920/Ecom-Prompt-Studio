// 把 cases.json 展开成 promptfoo 测试用例。
// 新增用例只改 cases.json，不需要动这个文件。
const path = require('path');
const cases = require('./cases.json');

module.exports = async function () {
  return cases.cases.map((c) => ({
    description: `#${c.id} [${c.group}] ${c.input}`,
    vars: { input: c.input },
    metadata: {
      id: c.id,
      group: c.group,
      expected_skill: c.expect.skill,
      expected_atom: c.expect.atom || '',
    },
    assert: [
      {
        type: 'javascript',
        value: 'file://./assert_route.js',
        config: {
          skill: c.expect.skill,
          // assert_route 用包含匹配，传原子编号即可（模型输出 `_atoms/a21.json` 也能命中）
          doc_contains: c.expect.atom || '',
        },
        metric: '路由命中',
      },
    ],
  }));
};
