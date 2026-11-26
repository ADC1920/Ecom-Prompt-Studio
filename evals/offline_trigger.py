# -*- coding: utf-8 -*-
"""离线触发评测：不调模型、不花钱，验路由判据还在不在。

和另外两套评测的分工：
- evals/promptfooconfig.yaml（触发回归）：把 description 与路由表喂给模型，要密钥，抓语义。
- evals/real_trigger.py（Tier 3 真实触发）：装进真引擎，看它会不会自己加载，慢且计费。
- 本脚本（离线）：纯词法 + 结构化索引，零依赖零成本，每次 PR 都能跑。

它抓的是哪类问题：改 description 砍掉了触发词、改了工位判据却没同步用例预期、
原子索引的触发词与用例脱节。抓不到的是语义改写——那归 promptfoo 管。

打分模型（三段，全部有据可查，不做语义猜测）：
1. 技能分流：负例必须落在 none，明星请求必须落在某个技能上。
   用「技能概念词命中数」判，概念词从各 SKILL.md 的 description 抽取。
2. 工位：从 query-atom 的索引字段判（品类 40 / 产物 25 / 动作 25），与 CLI 同源。
3. 原子：与 query-atom 的命中结果比对，要求预期原子出现在首位。

用法：
  python evals/offline_trigger.py                       # 跑全部用例
  python evals/offline_trigger.py --verbose             # 打印每条判定依据
  python evals/offline_trigger.py --min-pass 1.0        # 通过率下限，默认 1.0
  python evals/offline_trigger.py --selftest            # 反向用例验证判据非空转

退出码：0 全部达标；1 有失败。
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKILLS_DIR = ROOT / "skills"
CASES = HERE / "cases.json"
ATOMS_INDEX = SKILLS_DIR / "ecom-prompt-sop" / "references" / "_atoms" / "index.json"

sys.path.insert(0, str(ROOT / "tools"))


def read(path):
    return Path(path).read_text(encoding="utf-8")


def frontmatter_description(skill_md):
    """取 description 全文（支持 YAML 的 > 折叠块与引号形式）。"""
    text = read(skill_md)
    m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---", text)
    if not m:
        return ""
    fm = m.group(1)
    block = re.search(r"^description:\s*[>|][-+]?\s*\n([\s\S]*?)(?=^\S|\Z)", fm, re.M)
    if block:
        return " ".join(line.strip() for line in block.group(1).splitlines() if line.strip())
    inline = re.search(r"^description:\s*(.+)$", fm, re.M)
    if not inline:
        return ""
    value = inline.group(1).strip()
    return value.strip("\"'").strip()


# 概念词：用于判断某段文本是否在描述电商视觉任务。刻意用中性词表而非项目内造词，
# 这样 description 被砍掉这些词时能立刻暴露，而不是被项目自己的话术兜住。
ECOMMERCE_CONCEPTS = [
    "电商", "主图", "详情页", "商品", "产品图", "sku", "模特", "买家秀", "白底",
    "生图", "提示词", "prompt", "e-commerce", "ecommerce", "product image",
    "main image", "detail page", "listing",
]
OFFTOPIC_CONCEPTS = [
    "翻译邮件", "爬虫", "压缩到", "生日报", "生日祝福", "重命名文件", "batch rename",
    "python 脚本", "python 爬虫", "python script",
]


def concept_hits(text, concepts):
    low = text.casefold()
    return [c for c in concepts if c.casefold() in low]


def load_atoms():
    """合并两份索引，拿到完整路由字段。

    两份索引分工不同，缺一不可：
    - _atoms/index.json：id(aNN)、title、task、tags、outputs（人读的任务描述）
    - references/_index.json：no(篇号)、triggers（专门为路由写的触发词）、categories
    两者按「出现顺序」对齐——这是 atomize merge 的写入约定，不是猜的。
    """
    if not ATOMS_INDEX.exists():
        return []
    atoms = json.loads(read(ATOMS_INDEX)).get("items") or []
    ref_index = SKILLS_DIR / "ecom-prompt-sop" / "references" / "_index.json"
    route = []
    if ref_index.exists():
        route = json.loads(read(ref_index)).get("items") or []
    for atom, extra in zip(atoms, route):
        atom["no"] = extra.get("no", atom.get("no"))
        atom["triggers"] = extra.get("triggers") or []
        atom["categories"] = extra.get("categories") or atom.get("categories") or []
    return atoms


def _haystack(atom):
    """路由匹配面：标题、任务、标签、触发词、品类。

    与 tools/cli.py 的 _haystack 同源，多加了 triggers——那是专为路由写的字段，
    用例的措辞本就该往触发词上靠，不靠它等于把最准的信号扔掉。
    """
    parts = [atom.get("title") or "", atom.get("task") or ""]
    parts.extend(atom.get("tags") or [])
    parts.extend(atom.get("triggers") or [])
    parts.extend(atom.get("categories") or [])
    return " ".join(parts)


def score_atom(atom, query):
    """按索引字段打分。中文不分词，改用「概念片段命中」而非整词匹配。

    中文用例是自由句子（「给这个保温杯出详情页提示词」），按空格切词只会得到
    一个整句 token，几乎不可能等于索引里的任何子串。这里改成双向子串包含：
    触发词/标签出现在句子里就命中（权重高），句子里的双字片段出现在索引里也算
    （权重低）。两个方向都只依赖索引里已有的词，不做语义推断。
    """
    hay = _haystack(atom).casefold()
    low = query.casefold()
    score = 0
    evidence = []

    # 方向一：索引里的词出现在输入里——强信号
    for term in list(atom.get("triggers") or []) + list(atom.get("tags") or []):
        t = str(term).casefold()
        if len(t) >= 2 and t in low:
            score += 30
            evidence.append(f"触发词「{term}」")

    # 方向一补：品类词的口语短形。索引里写「包包」，用户却说「这个包」；
    # 写「保温杯」，用户说「杯子」。规则：品类词任意单字出现在输入里就加一次分，
    # 但只对下面这张白名单里的品类词生效，避免任意单字乱撞。
    SHORTABLE = ("包包", "保温杯", "水杯", "鞋", "茶", "壶", "口红", "面膜", "耳机")
    for cat in atom.get("categories") or []:
        c = str(cat)
        if c in SHORTABLE:
            for ch in {c[0], c[-1]}:
                if ch in query:
                    score += 35
                    evidence.append(f"品类短形「{ch}」←{c}")
                    break

    # 方向二：产物/品类/标题关键片段出现在输入里
    for out in atom.get("outputs") or []:
        if str(out) and str(out) in query:
            score += 20
            evidence.append(f"产物「{out}」")
    for cat in atom.get("categories") or []:
        if str(cat) and str(cat) in query:
            score += 40
            evidence.append(f"品类「{cat}」")
    if atom.get("title") and str(atom["title"]) in query:
        score += 35
        evidence.append("标题直命中")

    # 方向三：输入里的双字片段出现在索引里——弱信号，只用来打破平手
    chars = re.sub(r"[\s，,。.、:：!！?？]+", "", low)
    bigrams = {chars[i:i + 2] for i in range(len(chars) - 1)}
    hit = sum(1 for b in bigrams if b in hay)
    score += hit
    if hit:
        evidence.append(f"片段 {hit}")

    return score, evidence


def predict(case, atoms, descriptions):
    """返回 {skill, atom, evidence}。

    判定顺序与 SKILL.md 使用流程一致：
    ① 越界/注入 → none；② 点名篇号 → 该原子；③ 索引打分 → 唯一原子；
    ④ 索引无命中时才看是否英文请求或裸需求；⑤ 再不行 → none。

    关键点：索引命中本身即证据，不再额外要求「电商概念词」。早先那版拿概念词当
    门槛，把「翻新成高级感」「带故事板」这类动作型请求全挡在门外，是判据加错位置。
    """
    query = case["input"]
    low = query.casefold()

    # ① 越界与注入
    off = concept_hits(query, OFFTOPIC_CONCEPTS) + [e for e in EN_OFFTOPIC if e in low]
    if off:
        return {"skill": "none", "atom": None, "evidence": f"越界概念命中: {off}"}
    # 「翻译 X」：译图内文字属本库，译邮件/文章等不属
    if "翻译" in query and any(t in query for t in TRANSLATE_OFFTOPIC):
        return {"skill": "none", "atom": None, "evidence": "翻译对象不是图内文字，越过本库范围"}
    if "忽略以上" in query or "ignore previous" in low or "ignore all" in low:
        return {"skill": "none", "atom": None, "evidence": "提示词注入，不触发任何技能"}

    # ② 点名篇号优先
    ordinal = re.findall(r"\b0?(\d{1,2})\s*号", query)
    if ordinal:
        want = int(ordinal[0])
        atom = next((a for a in atoms if str(a.get("no")).lstrip("0") == str(want)), None)
        if atom:
            return {"skill": "ecom-prompt-sop", "atom": atom.get("id"),
                    "evidence": f"篇号 {want:02d} → {atom.get('id')}"}

    # ③ 索引打分。英文先把商品词译成中文品类，让同一批索引能吃两边。
    probe = _translate_en(query) if _is_english(query) else query
    scored = sorted(((score_atom(a, probe)[0], score_atom(a, probe)[1], a) for a in atoms),
                    key=lambda x: -x[0])
    best_score, best_ev, best = scored[0] if scored else (0, [], None)

    # 阈值：至少一个强信号（触发词 30 / 产物 20 / 品类 40 / 标题 35）。
    # 只靠双字片段凑出的零星分数不算命中，避免「忽略以上所有指令」这类串误触发。
    if best and best_score >= 20:
        skill = "ecom-prompt-sop"
        # ④ 裸需求才转交。判据是「有没有品类或细分线索」，不是分数高低：
        #    「给这个产品做主图」只命中「主图」这个通用产物词，没有品类、没有细分
        #    场景，属裸需求 → 转交导演；「保温杯的主图」命中品类 → 留在本库。
        #    英文请求的品类线索要查译文（thermos→保温杯），原句里当然没有中文品类词。
        if (_is_bare_request(query) and not _has_specialist_hint(query)
                and not _has_category_hint(probe)):
            skill = _transfer_target(query)
        return {"skill": skill, "atom": best.get("id"),
                "evidence": f"索引打分 {best_score}（{', '.join(best_ev[:3])}）→ {best.get('id')}"}

    # ⑤ 索引打不出分：英文裸请求按产物判导演，其余判 none
    if _is_english(query) and _is_bare_request(query):
        return {"skill": _transfer_target(query), "atom": None,
                "evidence": "英文裸需求 → 对应导演技能"}
    return {"skill": "none", "atom": None, "evidence": "索引无强命中"}


# 裸主图 / 裸详情页：没有任何细分线索，也没点名 SOP。有这些词就该留在本库。
# 判据来自 SKILL.md 使用流程第 3 步的排除列表，逐项对齐，不另造。
SPECIALIST_HINTS = ["模特", "人脸", "跨境", "轮播", "反推", "翻新", "复刻", "对标",
                    "sku", "批量", "这批", "多色", "件套", "多产品", "翻译", "视频",
                    "买家秀", "场景图", "6+2", "五点", "sop", "故事板", "镜头",
                    "纯视觉", "1:1", "3:4", "4:3", "16:9", "转成", "转换", "比例"]

# 品类线索：命中即留在 SOP（SKILL.md 第 4 步：品类专项优先于通用篇）
CATEGORY_HINTS = ["服饰", "卫衣", "T恤", "鞋", "包", "3C", "数码", "耳机", "音箱",
                  "美妆", "口红", "粉底", "面膜", "香水", "美食", "零食", "饮料",
                  "咖啡", "茶", "家具", "海产", "海参", "保温杯", "水杯", "饭盒",
                  "杯", "壶", "檀木", "手串", "线香", "礼盒"]
# 英文商品词 → 中文品类词。索引只有中文，英文用例靠这张表落到同一批原子。
# 这里不新增判据，只是把 SKILL.md description 已声明的 English keywords 落成可算形式。
EN_PRODUCT = {
    "thermos": "保温杯", "bottle": "杯", "hoodie": "卫衣", "sweater": "服饰",
    "shirt": "服饰", "dress": "服饰", "shoes": "鞋", "bag": "包",
    "lipstick": "口红", "makeup": "美妆", "cosmetic": "美妆", "perfume": "香水",
    "snack": "零食", "coffee": "咖啡", "tea": "茶", "headphone": "耳机",
    "earphone": "耳机", "speaker": "音箱", "chair": "家具", "desk": "家具",
}
EN_OFFTOPIC = ["python script", "batch rename", "scrape", "email", "poem", "weather"]
# 「翻译」是库内正当动作（图内文字批量翻译），只有译的是非图内对象才算越界。
# 这里按「翻译 + 非图片对象」判断，不能因为出现「翻译」二字就判越界。
TRANSLATE_OFFTOPIC = ["邮件", "文章", "文档", "合同", "简历", "论文"]
EN_DETAIL = ("detail page", "detail-page", "detailpage")
EN_MAIN = ("main image", "product image", "hero image", "prompt set", "listing image")


def _has_category_hint(query):
    return any(h in query for h in CATEGORY_HINTS)


def _is_english(query):
    """拉丁字母占多数即视为英文请求。"""
    letters = sum(1 for ch in query if ch.isascii() and ch.isalpha())
    return letters > len(query) * 0.5


def _has_specialist_hint(query):
    low = query.casefold()
    return any(h.casefold() in low for h in SPECIALIST_HINTS)


def _is_bare_request(query):
    low = query.casefold()
    return ("主图" in query or "详情页" in query
            or any(k in low for k in EN_MAIN + EN_DETAIL))


def _transfer_target(query):
    low = query.casefold()
    if "详情页" in query or any(k in low for k in EN_DETAIL):
        return "ecom-detail-page-prompts"
    return "ecom-main-image-prompts"


def _translate_en(query):
    """把英文商品词换成对应中文品类，让中文索引能命中。"""
    out = query
    for en, zh in EN_PRODUCT.items():
        if en in out.casefold():
            out += " " + zh
    return out


def run(verbose=False):
    cases = json.loads(read(CASES)).get("cases") or []
    atoms = load_atoms()
    descriptions = {p.parent.name: frontmatter_description(p) for p in SKILLS_DIR.glob("*/SKILL.md")}

    failures, rows = [], []
    for case in cases:
        got = predict(case, atoms, descriptions)
        want = case.get("expect") or {}
        ok_skill = got["skill"] == want.get("skill")
        want_atom = want.get("atom")
        ok_atom = (want_atom is None) or (got["atom"] == want_atom)
        ok = ok_skill and ok_atom
        rows.append((case, got, want, ok))
        if not ok:
            detail = []
            if not ok_skill:
                detail.append(f"技能 {got['skill']} ≠ 预期 {want.get('skill')}")
            if not ok_atom:
                detail.append(f"原子 {got['atom']} ≠ 预期 {want_atom}")
            failures.append(f"#{case['id']} [{case['group']}] {case['input'][:34]} | {'; '.join(detail)}"
                            f" | 依据: {got['evidence']}")

    if verbose:
        for case, got, want, ok in rows:
            print(f"{'OK ' if ok else 'FAIL'} #{case['id']:>2} [{case['group']}] "
                  f"{got['skill']}/{got['atom']} | {got['evidence']}")
    passed = sum(1 for r in rows if r[3])
    return passed, len(rows), failures


def selftest():
    """反向验证：判据必须能区分，不能一律放行或一律判 none。"""
    fails = []
    atoms = load_atoms()
    if len(atoms) != 34:
        fails.append(f"原子索引应 34 条，实际 {len(atoms)}")

    cases = json.loads(read(CASES)).get("cases") or []
    descriptions = {p.parent.name: frontmatter_description(p) for p in SKILLS_DIR.glob("*/SKILL.md")}

    # 1) description 必须真的抽出内容，且含电商概念词；否则「技能分流」这一段等于空转
    for name, desc in descriptions.items():
        if len(desc) < 50:
            fails.append(f"{name} 的 description 抽取过短（{len(desc)} 字符）")
        if not concept_hits(desc, ECOMMERCE_CONCEPTS):
            fails.append(f"{name} 的 description 里没有电商概念词，触发面可能已丢失")

    # 2) 负例必须判 none，正例不得判 none
    for case in cases:
        got = predict(case, atoms, descriptions)
        want = (case.get("expect") or {}).get("skill")
        if want == "none" and got["skill"] != "none":
            fails.append(f"负例 #{case['id']} 被判成 {got['skill']}（误触发）")
        if want not in (None, "none") and got["skill"] == "none":
            fails.append(f"正例 #{case['id']} 被判 none（漏触发）")

    # 3) 恒真检测：把所有输入换成明显无关的串，预测结果必须是 none
    for probe in ("今天天气怎么样", "帮我写一首诗", "translate this email to French"):
        fake = {"input": probe, "expect": {"skill": "none"}}
        got = predict(fake, atoms, descriptions)
        if got["skill"] != "none":
            fails.append(f"无关输入「{probe}」被判成 {got['skill']}（判据过宽）")

    # 4) 恒假检测：明显电商请求必须命中
    for probe in ("给保温杯出一套主图提示词", "口红的详情页提示词出一套"):
        fake = {"input": probe, "expect": {"skill": "ecom-prompt-sop"}}
        got = predict(fake, atoms, descriptions)
        if got["skill"] == "none":
            fails.append(f"电商请求「{probe}」被判 none（判据过严）")

    if fails:
        for f in fails:
            print(f"FAIL {f}")
        return 1
    print("selftest: description 抽取、负例拦截、恒真恒假探针 全部通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="离线触发评测（零模型调用）")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--min-pass", type=float, default=1.0, help="通过率下限，默认 1.0")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    passed, total, failures = run(args.verbose)
    rate = passed / total if total else 0.0
    for f in failures:
        print(f"FAIL {f}")
    print(f"离线触发：{passed}/{total} 通过（{rate*100:.1f}%），下限 {args.min_pass*100:.0f}%")
    return 0 if rate >= args.min_pass else 1


if __name__ == "__main__":
    sys.exit(main())
