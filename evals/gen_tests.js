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
      expected_doc: c.expect.doc_contains || '',
    },
    assert: [
      {
        type: 'javascript',
        value: 'file://./assert_route.js',
        config: {
          skill: c.expect.skill,
          doc_contains: c.expect.doc_contains || '',
        },
        metric: '路由命中',
      },
    ],
  }));
};
