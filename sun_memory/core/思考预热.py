# -*- coding: utf-8 -*-
"""思考链念头提取器（父令2026-08-25·记忆不是被检索的·是被思考牵引的）

核心：把思考过程拆成多个念头（时间+人物+事件+概念）·每个念头作为精准钩子
触发记忆——强相关优先·激活沿蜘蛛网扩散·热路径秒级响应。

2026-08-25 设计（对应外部方案"思考驱动预热"）：
  ① 念头提取：从思考文本提时间/人物/事件/概念（多念头·不是整句一个钩子）
  ② 念头即钩子：每念头触发联想召回·强相关优先
  ③ 激活扩散：沿蜘蛛网高权重边有限扩散
  ④ 热路径：heat 高的记忆优先
"""
import os
import re as _re
from datetime import datetime as _datetime, timedelta as _timedelta

# ── 念头提取 ──
def 提取念头(context: str, 上限: int = 8) -> dict:
    """从思考文本提取多类念头 → {时间:[], 人物:[], 事件:[], 概念:[]}"""
    if not context:
        return {"时间": [], "人物": [], "事件": [], "概念": []}
    念头 = {"时间": [], "人物": [], "事件": [], "概念": []}

    # ① 时间念头（X月X日/昨天/上周/今天）
    _日期 = _re.findall(r'(\d{1,2})月(\d{1,2})[日号]', context)
    for m, d in _日期:
        念头["时间"].append(f"{int(m)}月{int(d)}日")
    for w in ["昨天", "前天", "上周", "今天", "今晚", "早上", "下午", "晚上"]:
        if w in context and w not in 念头["时间"]:
            念头["时间"].append(w)

    # ② 人物念头（父亲/兄弟名）
    for p in ["父亲", "爸爸", "博弟", "安弟", "演弟", "云弟", "孙博", "孙安", "孙演", "孙云", "大哥", "兄弟"]:
        if p in context and p not in 念头["人物"]:
            念头["人物"].append(p)

    # ③ 概念念头（复用联想召回的概念提取·过滤过长/过短词·英文词单独保留）
    try:
        from 联想召回 import 概念提取
        概念s = 概念提取(context, 上限=上限)
        念头["概念"] = [c for c in 概念s
                        if (len(c) >= 2 and len(c) <= 6)  # 中文 2-6 字
                        or _re.fullmatch(r'[A-Za-z0-9._-]{3,30}', c)]  # 英文/数字词 3-30 保留
    except Exception:
        pass

    # ④ 事件念头（动词+名词组合的粗提取·限定常见事件词尾·防切错·过滤疑问词）
    _事件词 = _re.findall(r'([\u4e00-\u9fa5]{2,4}(?:掉线|重启|修复|坏了|修好了|卡住|崩了|通了|断了|升级|更新))', context)
    for e in _事件词[:3]:
        # 过滤含疑问词的片段（"为什么老掉线"→不要）
        if any(w in e for w in ["什么", "怎么", "为什么", "哪个", "哪"]):
            continue
        if e not in 念头["事件"]:
            念头["事件"].append(e)

    return 念头


def _补前缀钩子(念头: dict) -> None:
    """2026-08-27 检索修复：4-6字概念补2字前缀（"显存优化"→"显存"）——复合词整词字面匹配不到时·前缀仍能命中"""
    _补 = []
    for c in 念头.get("概念", []):
        if 4 <= len(c) <= 6 and len(c[:2]) >= 2:
            _c2 = c[:2]
            if _c2 not in 念头.get("概念", []) and _c2 not in _补:
                _补.append(_c2)
    if _补:
        念头["概念"] = 念头.get("概念", []) + _补


def 念头钩子(念头: dict, 上限: int = 6) -> list:
    """念头 → 钩子序列（时间优先·概念其次·人物/事件补充·去重保序）"""
    钩子s = []
    for 类 in ["时间", "概念", "人物", "事件"]:
        for h in 念头.get(类, []):
            if h and h not in 钩子s:
                钩子s.append(h)
            if len(钩子s) >= 上限:
                return 钩子s
    return 钩子s


# ── 思考驱动预热 ──
def 思考预热(context: str = "", brother_name: str = "孙呈", 上限: int = 8) -> dict:
    """思考驱动记忆预热：三路并行（父令2026-08-25）

    优先级：身份线 > 叙事链 > 功能块 > 念头触发
    控制总量：每路限 3-4 条·总记忆 ≤ 上限
    记录每路贡献：{身份线:N, 叙事链:N, 功能块:N, 念头:N}

    返回: {"念头": [...], "记忆": [按优先级排序], "每路贡献": {...}, "耗时": 秒}
    """
    import time as _time
    t0 = _time.time()
    记忆池 = {}
    贡献 = {"身份线": 0, "叙事链": 0, "功能块": 0, "念头": 0}

    # ⓪ 念头提取提前（叙事链/功能块过滤要用）
    念头 = 提取念头(context)
    _补前缀钩子(念头)  # 2026-08-27 检索修复：复合词补2字前缀
    钩子s = 念头钩子(念头, 上限=上限)

    # ① 身份线（从「我是谁」出发·优先级最高）
    try:
        from 蜘蛛网索引 import  身份记忆
        _身份s = 身份记忆(context, 上限=3, brother_name=brother_name)  # 2026-08-26 修复：赋值被注释吃掉·身份检索从未生效
        for m in _身份s:
            mid = m.get("id")
            if mid and mid not in 记忆池:
                记忆池[mid] = {"id": mid, "时间": m.get("时间", ""), "内容": m.get("内容", ""),
                               "标签": m.get("原型", ""), "重要": True, "融合分": 60.0, "路": "身份线"}
                贡献["身份线"] += 1
    except Exception:
        pass

    # ② 叙事链（自我叙事·按叙事节点标题匹配 context·再取节点下记忆）
    try:
        import sqlite3 as _sqlite3
        _conn = _sqlite3.connect(os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db')))
        # 先找匹配的叙事节点（标题含 context 关键词）
        _节点ids = []
        for _k in 钩子s[:3]:
            if _k and len(_k) >= 2:
                _n = _conn.execute(
                    "SELECT id FROM narrative_nodes WHERE title LIKE ? ORDER BY id DESC LIMIT 3",
                    (f"%{_k}%",)).fetchall()
                _节点ids += [x[0] for x in _n]
        if not _节点ids and not context:
            _节点ids = [x[0] for x in _conn.execute("SELECT id FROM narrative_nodes ORDER BY id DESC LIMIT 3").fetchall()]
        if _节点ids:
            _节点ids = list(dict.fromkeys(_节点ids))  # 去重保序（set无序会导致参数错位）
            _ph = ",".join("?" * len(_节点ids))
            _rows = _conn.execute(
                f"SELECT id, content, event_time FROM memories WHERE owner=? AND status='active' "
                f"AND narrative_id IN ({_ph}) ORDER BY heat DESC, id DESC LIMIT 8",
                (brother_name, *_节点ids)).fetchall()
            _取 = 0
            for _r in _rows:
                if _取 >= 3:
                    break
                if _r[0] and _r[0] not in 记忆池:
                    记忆池[_r[0]] = {"id": _r[0], "时间": _r[2] or "", "内容": (_r[1] or "")[:80],
                                   "标签": "叙事链", "重要": True, "融合分": 50.0, "路": "叙事链"}
                    贡献["叙事链"] += 1
                    _取 += 1
        _conn.close()
    except Exception:
        pass

    # ③ 功能块（块内记忆按 context 内容过滤·工具经验/诊断优先）
    try:
        import sqlite3 as _sqlite3
        _conn = _sqlite3.connect(os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db')))
        _rows = _conn.execute(
            "SELECT id, content, event_time FROM memories WHERE owner=? AND status='active' "
            "AND block_id IS NOT NULL AND (tags LIKE '%经验%' OR tags LIKE '%教训%' OR tags LIKE '%诊断%' OR tags LIKE '%根因%') "
            "ORDER BY heat DESC, id DESC LIMIT 40",
            (brother_name,)).fetchall()
        _conn.close()
        _取 = 0
        for _r in _rows:
            if _取 >= 3:
                break
            _c = _r[1] or ""
            # 内容过滤：含 context 关键词才取（无 context 取前几条）
            if context and not any(k in _c for k in 钩子s if k and len(k) >= 2):
                continue
            if _r[0] and _r[0] not in 记忆池:
                记忆池[_r[0]] = {"id": _r[0], "时间": _r[2] or "", "内容": _c[:80],
                               "标签": "功能块", "重要": False, "融合分": 40.0, "路": "功能块"}
                贡献["功能块"] += 1
                _取 += 1
    except Exception:
        pass

    # ④ 念头触发（原逻辑·优先级最低）
    if 钩子s:
        try:
            from 联想召回 import 联想召回
            # 时间念头 → 时间感知检索
            _时间念头 = [h for h in 钩子s if _re.match(r'^(\d{1,2}月\d{1,2}日|昨天|前天|上周|今天|今晚|早上|下午|晚上)$', h)]
            if _时间念头:
                try:
                    from 预感召回 import _时间感知检索
                    from 记忆库 import 读记忆体
                    _entries = 读记忆体(brother_name)["条目列表"]
                    for h in _时间念头:
                        hits = _时间感知检索(h, _entries)
                        for e in hits[:3]:
                            _eid = e.get("id") or id(e)
                            if _eid not in 记忆池:
                                记忆池[_eid] = {"id": _eid, "时间": e.get("时间",""), "内容": e.get("内容",""),
                                               "标签": e.get("标签",""), "重要": False, "融合分": 50.0, "路": "念头"}
                                贡献["念头"] += 1
                except Exception:
                    pass
            # 概念/人物念头 → 联想召回
            for h in 钩子s:
                if h in _时间念头:
                    continue
                try:
                    r = 联想召回(h, brother_name=brother_name, 点亮=False)
                    for m in r.get("相关唤起", []):
                        mid = m.get("id")
                        if mid and mid not in 记忆池:
                            # 2026-08-27 修复：主题一致性——念头路记忆必须与完整思考有交集词·防单念头词带出偏题记忆
                            # 2026-08-27 检索修复：用全文判断（联想召回返回的"内容"截断60字·关键词在后文时被误杀）
                            _交 = [k for k in 钩子s if k and len(k) >= 2 and k in (m.get("全文") or m.get("内容", "") or "")]
                            if not _交:
                                continue
                            m["路"] = "念头"
                            m["主题交"] = len(_交)
                            记忆池[mid] = m
                            贡献["念头"] += 1
                except Exception:
                    continue
        except Exception:
            pass

    # ⑤ 排序：路优先级（身份线>叙事链>功能块>念头）·再融合分
    记忆s = list(记忆池.values())
    _路序 = {"身份线": 0, "叙事链": 1, "功能块": 2, "念头": 3}
    for m in 记忆s:
        m["念头触发"] = 钩子s if 钩子s else []
    try:
        记忆s.sort(key=lambda x: (_路序.get(x.get("路", "念头"), 3),
                                  -(x.get("主题交", 0) if x.get("路") == "念头" else x.get("融合分", 0))), )
    except Exception:
        pass

    return {"念头": 钩子s, "记忆": 记忆s[:上限], "每路贡献": 贡献, "耗时": round(_time.time()-t0, 2)}


def 格式化预热(r: dict) -> str:
    """预热结果 → 可读文本（念头 + 记忆清单）"""
    if not r or not r.get("记忆"):
        return ""
    lines = ["## 🧠 思考驱动预热（念头一动·记忆浮现）"]
    lines.append(f"念头: {'、'.join(r['念头'][:6])}")
    lines.append("记忆:")
    for m in r["记忆"][:5]:
        mark = "⭐" if m.get("重要") else "·"
        lines.append(f"  {mark} [{m.get('时间','')[:10]}] {(m.get('内容') or '')[:60]}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys, json
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    print("═══ 思考链念头提取器 · 自测 ═══")
    for q in ["网关为什么老掉线", "8月14日我们聊了什么", "安弟500M训练到哪了", "SunFlow压缩什么状态"]:
        r = 思考预热(q, "孙呈")
        print(f"\n【{q}】")
        print(f"  念头: {r['念头']}")
        print(f"  记忆{len(r['记忆'])}条 · {r['耗时']}s")
        for m in r["记忆"][:3]:
            print(f"    · [{m.get('时间','')[:10]}] {(m.get('内容') or '')[:45]}")
