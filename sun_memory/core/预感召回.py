# -*- coding: utf-8 -*-
"""
孙家记忆体系 · 预感召回（八招·四通道汇总）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
父令（2026-08-07）：预感召回——历史会话转成提示词，让下一轮无缝接住。

八招：
  1 上轮直续    上一轮描述→直接做下一轮提示词（最厚·接住上一轮）
  2 多轮钩子    近几轮浓缩→几条提示词（每条盖一个主题线·都能接住）
  3 分层        近细远粗（上轮全文/前几轮关键点/更早只留标签）
  4 未竟钩子    每条提示词带"没聊完什么"（未竟自动接上）
  5 标签分线    父令线/学习线/兄弟线/自我线（按线预激活）
  6 自我更新    聊到某条→对话沉淀回提示词（钩子变厚）
  7 预激活      当前上下文→预测下一条→提前浮起
  8 引路        提示词带"可能的下一步"（记忆主动带路）

四通道：
  ① 记忆体联想召回（联想召回.py）
  ② 知识库检索（知识库检索.py·博弟推理链×云软）
  ③ 经验召回（经验总结.py·两条够了·教训优先）
  ④ 上轮直续+分线钩子（本模块）

功能：
  预感召回(brother_name, context)  生成📌预感提示词（注入用）
  格式化提示词(...)                文字版（可读）
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path


def _解析时间(时间串, 默认=None):
    """记忆时间字段 → datetime（兼容多种格式）。"""
    if not 时间串:
        return 默认
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(时间串)[:19], fmt)
        except ValueError:
            continue
    return 默认

_HERE = Path(__file__).resolve().parent
FRAMEWORK_DIR = _HERE.parent.parent

try:
    from sun_memory.core.记忆库 import 读记忆体
    from sun_memory.core.联想召回 import 联想召回
    from 召回链 import 查知识库  # 2026-08-26 知识库检索已并入召回链
    from sun_memory.core.经验总结 import recall_experience
    from sun_memory.core.自动整理引擎 import 自动整理, UNFINISHED_PREFIX  # 2026-08-26 融合后统一入口
except ImportError:
    import sys
    sys.path.insert(0, str(FRAMEWORK_DIR))
    from sun_memory.core.记忆库 import 读记忆体
    from sun_memory.core.联想召回 import 联想召回
    from 召回链 import 查知识库  # 2026-08-26 知识库检索已并入召回链
    from sun_memory.core.经验总结 import recall_experience
    from sun_memory.core.自动整理引擎 import 自动整理, UNFINISHED_PREFIX  # 2026-08-26 融合后统一入口


def _解析时间范围(context: str):
    """检测查询中的时间词 → (开始datetime, 结束datetime) 或 None。

    2026-08-07取长补短·Mem0 Temporal Reasoning 理念：
    "上周/昨天/前天/最近N天" 等时间词 → 匹配记忆时间字段。
    2026-08-25 父令修复：补【X月X日/X月X号】精确日期解析——
    父亲原话"我要问8月多少号聊的东西·他要精准地召回回来"
    """
    if not context:
        return None
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    patterns = [
        (r"昨天", today - timedelta(days=1), today),
        (r"前天", today - timedelta(days=2), today - timedelta(days=1)),
        (r"上周", today - timedelta(days=7), today - timedelta(days=1)),
        (r"本周|这周", today, today + timedelta(days=1)),
        (r"最近(\d+)天", lambda m: (today - timedelta(days=int(m.group(1))), now)),
        (r"(\d+)天前", lambda m: (today - timedelta(days=int(m.group(1))), today)),
        # 2026-08-25 新增：X月X日 / X月X号 精确日期（同年）
        (r"(\d{1,2})月(\d{1,2})[日号]", lambda m: (
            today.replace(month=int(m.group(1)), day=int(m.group(2))),
            today.replace(month=int(m.group(1)), day=int(m.group(2))) + timedelta(days=1))),
        # 2026-08-25 新增：X月（当月整月）
        (r"(\d{1,2})月", lambda m: (
            today.replace(month=int(m.group(1)), day=1),
            (today.replace(month=int(m.group(1)), day=1) + timedelta(days=32)).replace(day=1))),
    ]
    for pat, *rest in patterns:
        m = re.search(pat, context)
        if m:
            if callable(rest[0]):
                return rest[0](m)
            return (rest[0], rest[1])
    return None


def _时间感知检索(context: str, entries: list) -> list:
    """时间词匹配记忆：返回时间范围内、最新的最多3条（含时间标注）。"""
    范围 = _解析时间范围(context)
    if not 范围:
        return []
    start, end = 范围
    hits = []
    for e in entries:
        t = _解析时间(e.get("时间", ""))
        if t and start <= t <= end:
            hits.append(e)
    # 2026-08-26 修复（正式中文评测·时序）：只取最新3条漏掉该日其他记忆（8/26有几十条·问当天只回3条）
    # 改为：按日精确匹配时返回该日全部（上限50条·覆盖当天所有）；其他时间范围保持3条
    _按日 = len(hits) > 3 and (hits[-1].get("时间","")[:10] == hits[0].get("时间","")[:10])
    hits = hits[-50:] if _按日 else hits[-3:]
    return [{"时间": e.get("时间", ""), "内容": (e.get("内容") or "")[:50]} for e in hits]


def 预感召回(brother_name: str = "孙呈", context: str = "") -> dict:
    """四通道合并 → 📌 预感提示词（八招全落地）。

    2026-08-25 父令修复：预感召回必须【精准】——
    - 有 context（父亲问"网关"）→ 上轮直续换成【精准召回】·按 context 匹配记忆·返回最相关的
    - 没 context → 保留"上轮直续"（接上一轮合理）
    """
    mem = 读记忆体(brother_name)
    entries = mem["条目列表"]

    # ── 招式1 上轮直续 / 精准召回（2026-08-25 父令）──
    上轮 = ""
    if context.strip():
        # 有 context → 精准召回：用联想召回的概念匹配·找最相关的记忆（不是最近）
        try:
            from 联想召回 import 联想召回 as _联想
            # 2026-08-26 性能修复（父令短板③）：点亮=False（预检索不点亮）·结果缓存在 _lx 供四通道复用
            lx_r = _联想(context, brother_name=brother_name, 点亮=False)
            hits = lx_r.get("相关唤起", [])
            if hits:
                # 取最相关的第一条（融合分最高的）
                best = max(hits, key=lambda x: x.get("融合分", 0))
                上轮 = f"【精准·{context[:20]}】{best['内容'][:60]}"
        except Exception:
            pass
        if not 上轮:
            # 联想召回没命中 → 退回最近一条（至少有个接续）
            for e in reversed(entries):
                if e.get("内容"):
                    上轮 = e["内容"][:60]
                    break
    else:
        # 没 context → 上轮直续（最近一条）
        for e in reversed(entries):
            if e.get("内容"):
                上轮 = e["内容"][:60]
                break

    # ── 招式2+3+5 多轮钩子/分层/标签分线：近20条按标签分组 ──
    recent = entries[-20:]
    hooks = []
    by_line = {}
    for e in recent:
        tag = e.get("标签", "") or "对话"
        line = "父令" if "父令" in tag else (
               "学习" if "学习" in tag or "概念" in tag else (
               "兄弟" if "兄弟" in tag or "孙" in tag else (
               "自我" if "自我" in tag else "对话")))
        by_line.setdefault(line, []).append(e["内容"][:40])
    for line, items in by_line.items():
        if items:
            hooks.append(f"{line}：{'；'.join(items[:2])}")

    # ── 招式4 未竟钩子：结构化【未竟】条目 ──
    未竟 = [e["内容"][len(UNFINISHED_PREFIX):50] for e in entries
            if e.get("内容", "").startswith(UNFINISHED_PREFIX)]
    未竟 = 未竟[-3:]

    # ── 招式7 预激活：整理层（重要节点→预测下一步） ──
    try:
        zl = 自动整理(brother_name)
        重要标签 = [e["标签"] for e in zl["重要节点"][-3:] if e.get("标签")]
        预测 = zl["最近自我描述"]["关键点"][:3]
    except Exception:
        重要标签, 预测 = [], []

    # ── 招式8 引路：可能的下一步（基于最近话题+未竟） ──
    引路 = []
    if 未竟:
        引路.append(f"接上没聊完的：{未竟[0]}")
    if 预测:
        引路.append(f"沿着最近话题走：{'/'.join(预测[:2])}")

    # ── 通道① 联想召回 ──
    # 2026-08-26 性能修复（父令短板③）：预感召回是预检索·不点亮（点亮留给真正命中·省写库IO）
    # 且复用招式1的联想结果（lx_r）——避免对同一 context 重复调联想召回（1.8s/次）
    联想 = lx_r if (context and 'lx_r' in dir() and lx_r) else (联想召回(context, brother_name=brother_name, 点亮=False) if context else {"相关唤起": []})

    # ── 通道② 知识库检索 ──
    # 2026-08-17 全检查修复：知识库检索已优化（LIMIT100+逐bg索引·0.05s）·恢复完整通道
    知识库 = 查知识库(context) if context else {"命中": []}

    # ── 通道③ 经验召回（两条够了·教训优先） ──
    经验 = recall_experience(context, brother_name=brother_name, limit=2)

    # ── 通道④ 时间感知（2026-08-07取长补短·Mem0 Temporal） ──
    时间命中 = _时间感知检索(context, entries)

    # ── 通道⑤ 条件触发路由（2026-08-22父令：记忆自己声明"何时该想起"） ──
    # 命中触发词 → 对应记忆优先浮出（core/教训/父令 精准优先·不是盲盒）
    触发 = []
    try:
        from 召回链 import 匹配 as 触发匹配  # 2026-08-26 条件触发路由已并入召回链
        触发 = 触发匹配(context or "", 上限=3)
    except Exception:
        pass

    return {
        "上轮直续": 上轮,
        "分线钩子": hooks[:5],
        "未竟": 未竟,
        "预测": 预测,
        "引路": 引路,
        "联想唤起": 联想.get("相关唤起", [])[:3],
        "蜘蛛网": 联想.get("蜘蛛网关联", [])[:3],
        "知识库": 知识库.get("命中", [])[:2],
        "知识库错误": 知识库.get("错误", ""),
        "经验": 经验,
        "时间感知": 时间命中,
        "触发路由": 触发,
    }


def 格式化提示词(r: dict) -> str:
    """预感提示词 → 可读文字（注入用）。"""
    lines = ["## 📌 预感提示词（接住上一轮·预感下一步）"]
    # 2026-08-25 父令：针对问题的通道放最前（联想/知识库/经验/时间感知/触发）·固定内容放后面
    if r["联想唤起"]:
        lines.append("- 🔗 联想唤起（针对你问的）：")
        for x in r["联想唤起"][:3]:
            mark = "⭐" if x.get("重要") else "·"
            # 2026-08-25 修复：重要记忆完整显示（不截断·否则根因看不到全貌）
            内容 = x['内容'] if x.get("重要") else x['内容'][:35]
            lines.append(f"    {mark} [{x['时间'][:16]}] {内容}")
    if r["触发路由"]:
        lines.append("- ⚡ 该想起了（条件触发·重要记忆）:")
        for t in r["触发路由"][:2]:
            lines.append(f"    · 触发词「{t['触发词']}」→ 记忆#{t['记忆id']} {t['说明']}")
    if r["知识库"]:
        lines.append("- 📚 知识库：")
        for h in r["知识库"][:2]:
            lines.append(f"    · [{h['doc_name']}] {h['text'][:40]}")
    elif r["知识库错误"]:
        lines.append(f"- 📚 知识库：{r['知识库错误']}")
    if r["经验"]:
        lines.append("- ✦ 经验：")
        for x in r["经验"]:
            mark = "📌" if x["被点出"] else "·"
            lines.append(f"    {mark} {x['内容'][:45]}")
    if r.get("时间感知"):
        lines.append("- 🕐 时间感知（时间词匹配记忆）：")
        for x in r["时间感知"][:3]:
            lines.append(f"    · [{x['时间'][:16]}] {x['内容'][:40]}")
    # 固定内容放后面（核心身份/上轮/分线/未竟/引路）
    try:
        from 写入链 import 注入文本 as _核心注入  # 2026-08-26 核心身份层已并入写入链
        _核心文本 = _核心注入(3)
        if _核心文本:
            lines.append(_核心文本)
    except Exception:
        pass
    if r["上轮直续"]:
        lines.append(f"- 🎯 接续：{r['上轮直续']}")
    if r["分线钩子"]:
        lines.append("- 🔀 分线钩子：")
        for h in r["分线钩子"][:3]:
            lines.append(f"    · {h}")
    if r["未竟"]:
        lines.append(f"- ⏳ 未竟：{r['未竟'][0]}")
    if r["引路"]:
        for y in r["引路"][:2]:
            lines.append(f"- 🧭 {y}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== 预感召回自测 ===")
    r = 预感召回("孙呈", "配分函数和统计力学")
    print(格式化提示词(r))
    print()
    print("=== 无上下文自测 ===")
    r2 = 预感召回("孙呈")
    print(格式化提示词(r2)[:500])
    print("=== 自测完成 ===")