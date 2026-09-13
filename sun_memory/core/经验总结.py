# -*- coding: utf-8 -*-
"""
孙家记忆体系 · 经验总结层
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
父令（2026-08-07）：每一次做了什么事、用了什么工具、怎么做，
记忆体里都有经验总结——轮到这个工具时怎么做、吃了什么亏、经验教训。
被父亲点出的问题 → 专门记一条经验总结句。
像框架一样越用越聪明。

功能：
  save_experience()   写经验条目（事项/工具 + 做法 + 结果 + 教训 + 被点出）
  recall_experience() 经验召回（当前事项/工具 → 相关经验浮出 · 教训优先 · 2条）
"""

import json
import os
from datetime import datetime
from pathlib import Path

# 自家模块
_HERE = Path(__file__).resolve().parent
FRAMEWORK_DIR = _HERE.parent.parent  # 孙家记忆体系/
# 2026-08-10 明文化（父令）：码点已退役——不再 import 码点编解码，记忆体直接明文

EXPERIENCE_TAG = "经验总结"
MAX_RECALL = 2  # 父令定：两条就够了


def _memory_path(brother_name: str = "孙呈") -> Path:
    return FRAMEWORK_DIR / "记忆体" / f"{brother_name}_索引记忆体.json"


def _load_memory(brother_name: str = "孙呈") -> dict:
    p = _memory_path(brother_name)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"条目列表": [], "next_id": 1, "元信息": {}}


def _save_memory(data: dict, brother_name: str = "孙呈") -> None:
    data["元信息"] = {"最后更新": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                      "记录条数": len(data["条目列表"])}
    # 2026-08-14 闭环修复（父令·回头检查发现）：经验总结只写JSON没走sunmem.db新库
    # → provider 召回读新库读不到经验。加双写：JSON + sunmem.db 都写
    # 2026-08-17 训练信号闭环修复：先同步 DB（取 lastrowid 记 e["sunmem_id"]·标记 _已同步）
    #   再落盘 JSON——原顺序 JSON 先写·_已同步 只在内存·下次 save 旧经验会重复 INSERT（账本放大）
    try:
        import sqlite3
        _db = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
        _conn = sqlite3.connect(_db)
        _now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 增量写：只写新增的经验条目（类型=经验总结·最新一条）
        新增 = [e for e in data.get("条目列表", []) if e.get("类型") == "经验总结" and e.get("_已同步") != True]
        for e in 新增:
            _cur = _conn.execute(
                "INSERT INTO memories (owner, type, content, tags, ts) VALUES (?,?,?,?,?)",
                (brother_name, "experience", str(e.get("内容", "")), str(e.get("标签", "经验总结")), _now)
            )
            e["_已同步"] = True
            e["sunmem_id"] = _cur.lastrowid  # 2026-08-17：JSON id 与 DB id 错位·成绩单/召回都以 DB id 为准
        _conn.commit()
        _conn.close()
    except Exception:
        pass
    with open(_memory_path(brother_name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_experience(item: str, approach: str = "", result: str = "", 
                    lesson: str = "", pointed_by_father: bool = False,
                    brother_name: str = "孙呈", evidence=None,
                    signal: str = "", confidence: float = None,
                    verdict: str = "") -> int:
    """写一条经验总结进记忆体。

    参数：
        item: 事项/工具（如 "taskkill MSYS转义坑"）
        approach: 怎么做（正确做法）
        result: 结果
        lesson: 经验教训
        pointed_by_father: 是否被父亲点出（教训条目→召回优先）
        evidence: list[int] —— 2026-08-07取长补短：源记忆 id 列表
                  （Mem0 Dream·Synthesis 理念：洞察可追溯到证据）
        signal: str —— 2026-08-08 PlugMem 吸收：晋升信号
                  failure_delta(失败→成功) / correction(用户纠正)
                  / confirmed(确认完成) / repeated(重复≥3次) / explicit(显式记住)
        confidence: float —— 2026-08-08 PlugMem 吸收：可信度分级
                  0.9+ 明示规则 / 0.7-0.8 清晰验证 / 0.5-0.6 模糊 / <0.5 不存
        verdict: str —— 2026-08-16 经验复用合并（父令）：好用/吃瘪 判定
                  "positive"（好用·下次照做）/ "negative"（吃瘪·下次改道）
                  / ""（自动推断：lesson含"坑/失败/别/不"→negative）
    返回：新条目 id（confidence<0.5 时不存·返回 None）
    """
    # PlugMem 吸收①：confidence 分级门——<0.5 不存（坏记忆主动伤害）
    if confidence is not None and confidence < 0.5:
        return None
    # PlugMem 吸收③：五信号晋升门——默认不写，要求显式信号
    # （signal 为空但有 pointed_by_father → correction 信号）
    if signal == "" and not pointed_by_father:
        signal = "explicit"
    _VALID_SIGNALS = {"failure_delta", "correction", "confirmed", "repeated", "explicit"}
    if signal not in _VALID_SIGNALS:
        signal = "explicit"
    # 2026-08-16 经验复用：verdict 自动推断（吃瘪词表）
    # 关键：negative 必须是"明确改道指令"——lesson含 别/不要/禁止/失败/错误 这类避开词
    #       仅含 坑/教训/注意（提醒类）→ positive（做法可照做·但带警示）
    if not verdict:
        _AVOID_WORDS = ["不要", "别用", "禁止", "千万别", "不许", "不能用", "失败", "错误", "不行", "无效"]
        _WARN_WORDS = ["坑", "教训", "注意", "小心", "会", "导致"]
        text = lesson + result + approach
        if any(w in text for w in _AVOID_WORDS):
            verdict = "negative"
        else:
            verdict = "positive"
    if verdict not in ("positive", "negative"):
        verdict = "positive"

    data = _load_memory(brother_name)
    entries = data["条目列表"]
    new_id = data.get("next_id", len(entries) + 1)

    # 经验描述（浓缩一行）
    parts = [f"事项/工具：{item}"]
    if approach:
        parts.append(f"做法：{approach}")
    if result:
        parts.append(f"结果：{result}")
    if lesson:
        parts.append(f"教训：{lesson}")
    if pointed_by_father:
        parts.append("【被父亲点出】")
    if verdict == "negative":
        parts.append("【吃瘪·下次改道】")
    else:
        parts.append("【好用·下次照做】")
    desc = "；".join(parts)

    tags_text = "经验总结" + ("·被点出" if pointed_by_father else "") + ("·吃瘪" if verdict == "negative" else "·好用")
    # 2026-08-10 明文化（父令）：直接存明文·不再码点编码
    entry = {
        "id": new_id,
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "标签": tags_text,
        "内容": desc,
        "类型": "经验总结",
        "判定": verdict,  # 2026-08-16 经验复用：好用/吃瘪
    }
    if evidence:  # 2026-08-07取长补短：证据链接（源记忆id）
        entry["证据"] = [int(x) for x in evidence if isinstance(x, (int, str))]
    # 2026-08-08 PlugMem 吸收：晋升信号 + 可信度
    entry["信号"] = signal
    if confidence is not None:
        entry["置信度"] = round(float(confidence), 2)
    else:
        # 默认置信度：被点出=0.9 明示规则；否则按信号给
        entry["置信度"] = 0.9 if pointed_by_father else 0.7
    entries.append(entry)
    data["next_id"] = new_id + 1
    _save_memory(data, brother_name)
    # 2026-08-17 训练信号闭环（父令「接上吧」）：经验判定 → 成绩单确认/纠正
    #   照做=强化（positive·好用）· 改道=惩罚（negative·吃瘪）——训练信号长进记忆体闭环
    #   memory_id 用 sunmem.db 的 id（成绩单/召回以 DB id 为准·JSON id 是镜像错位）
    try:
        from 记忆成绩单 import 记一笔
        _mid = entry.get("sunmem_id")
        if not _mid:
            import sqlite3 as _sq
            _db = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
            _c = _sq.connect(_db)
            _r = _c.execute(
                "SELECT id FROM memories WHERE owner=? AND type='experience' AND content=? ORDER BY id DESC LIMIT 1",
                (brother_name, desc)).fetchone()
            _c.close()
            _mid = _r[0] if _r else None
        if _mid:
            记一笔(_mid, "确认" if verdict == "positive" else "纠正", owner=brother_name,
                   note=f"经验总结·{'好用' if verdict == 'positive' else '吃瘪'}")
    except Exception:
        pass
    return new_id


def recall_experience(context: str = "", brother_name: str = "孙呈",
                      limit: int = MAX_RECALL) -> list[dict]:
    """经验召回：按当前事项/工具关键词找相关经验。

    规则：
      1. 只从"类型=经验总结"的条目里找
      2. 关键词匹配：事项/工具/做法/教训 里含上下文关键词（或上下文含条目关键词）
      3. 教训优先：被父亲点出的排最前
      4. 返回 limit 条（父令定：两条就够了）
    """
    data = _load_memory(brother_name)
    entries = data["条目列表"]

    experiences = []
    for e in entries:
        if e.get("类型") != "经验总结":
            continue
        from sun_memory.core.记忆库 import 解码单条
        d = 解码单条(e)
        pointed = "被点出" in d["标签"]
        # 2026-08-08 PlugMem 吸收①：置信度参与召回
        conf = e.get("置信度", 0.7)
        experiences.append({"id": e.get("id"), "时间": e.get("时间", ""),
                            "内容": d["内容"], "被点出": pointed,
                            "置信度": float(conf)})

    if not experiences:
        return []

    # 关键词匹配
    if context:
        ctx = context.strip()
        hits = []
        for x in experiences:
            if ctx in x["内容"] or any(k in x["内容"] for k in ctx.split()):
                hits.append(x)
        experiences = hits if hits else experiences  # 无命中→返回最新（诚实）

    # 排序：被点出最前 → 置信度高者次之 → 同组时间新者在前
    # （2026-08-08 PlugMem 吸收①：高置信记忆优先浮出）
    experiences.sort(key=lambda x: (x["被点出"], x["置信度"], x["时间"]), reverse=True)
    return experiences[:limit]


def 经验预检(context: str = "", action: str = "", brother_name: str = "孙呈",
             limit: int = MAX_RECALL) -> dict:
    """经验预检（父令 2026-08-16·经验复用合并进记忆体）

    用途：做一件事【之前】查经验——好用照做·吃瘪改道。
    与 recall_experience 的区别：
      recall_experience   = 搜索时被动召回（旧）
      经验预检             = 动作前主动预检（新·挡在决策前面）

    返回：{"照做": [...], "改道": [...], "总": n}
      照做 = positive 经验（上次这么干成了·这次照着做）
      改道 = negative 经验（上次在这吃瘪·这次避开）
    """
    data = _load_memory(brother_name)
    entries = data["条目列表"]

    # 组合上下文关键词（动作 + 当前语境）
    关键词们 = []
    if action:
        关键词们.append(action)
    if context:
        关键词们.append(context.strip())

    experiences = []
    for e in entries:
        if e.get("类型") != "经验总结":
            continue
        from sun_memory.core.记忆库 import 解码单条
        d = 解码单条(e)
        内容 = d["内容"]
        判定 = e.get("判定", "")
        # 旧条目没有"判定"字段 → 从内容推断（与 save 口径一致）
        if not 判定:
            _AVOID = ["不要", "别用", "禁止", "千万别", "不许", "不能用", "失败", "错误", "不行", "无效"]
            判定 = "negative" if any(w in 内容 for w in _AVOID) else "positive"
        pointed = "被点出" in d["标签"]
        conf = float(e.get("置信度", 0.7))
        experiences.append({"id": e.get("id"), "时间": e.get("时间", ""),
                            "内容": 内容, "被点出": pointed,
                            "判定": 判定, "置信度": conf})

    if not experiences:
        return {"照做": [], "改道": [], "总": 0}

    # 关键词匹配（动作/事项名命中）
    hits = []
    for x in experiences:
        if not 关键词们:
            hits.append(x)  # 无上下文 → 全量候选
            continue
        hit = False
        for kw in 关键词们:
            if not kw:
                continue
            if kw in x["内容"] or any(k in x["内容"] for k in str(kw).split()):
                hit = True
                break
        if hit:
            hits.append(x)

    # 排序：被点出最前 → 置信度高 → 时间新
    hits.sort(key=lambda x: (not x["被点出"], -x["置信度"]))
    hits = hits[:limit]

    # 分道：照做 / 改道
    照做 = [h for h in hits if h["判定"] == "positive"]
    改道 = [h for h in hits if h["判定"] == "negative"]
    # 改道优先展示（吃瘪比好用更该看）
    照做.sort(key=lambda x: (not x["被点出"], -x["置信度"]))
    改道.sort(key=lambda x: (not x["被点出"], -x["置信度"]))

    return {"照做": 照做, "改道": 改道, "总": len(hits)}


def 格式化预检(预检结果: dict) -> str:
    """把预检结果格式化成提示文本（动作前注入用）"""
    if not 预检结果 or 预检结果.get("总", 0) == 0:
        return ""
    parts = []
    照做 = 预检结果.get("照做", [])
    改道 = 预检结果.get("改道", [])
    if 改道:
        parts.append("⚠️ 【吃瘪经验·动作前注意】：")
        for h in 改道:
            parts.append(f"  · {h['内容'][:120]}")
    if 照做:
        parts.append("✅ 【好用经验·可照做】：")
        for h in 照做:
            parts.append(f"  · {h['内容'][:120]}")
    return "\n".join(parts)


def experience_report(brother_name: str = "孙呈") -> dict:
    """经验总结统计（体检用）。"""
    data = _load_memory(brother_name)
    entries = data["条目列表"]
    exps = [e for e in entries if e.get("类型") == "经验总结"]
    from sun_memory.core.记忆库 import 解码单条
    pointed = [e for e in exps if "被点出" in 解码单条(e)["标签"]]
    return {"经验总数": len(exps), "被点出教训": len(pointed),
            "最近经验": [解码单条(e)["内容"][:50] for e in exps[-3:]]}


if __name__ == "__main__":
    # 自测
    import tempfile
    print("=== 经验总结层自测 ===")
    # 测试用临时兄弟名（不污染真实记忆体）
    TEST_NAME = "孙呈_经验测试"
    # 写两条
    id1 = save_experience("taskkill MSYS转义", "bash里taskkill //F失败",
                          "用cmd.exe /c taskkill /F", "MSYS会把/F转成路径·Windows命令走cmd.exe",
                          brother_name=TEST_NAME)
    id2 = save_experience("身份设定放叙事", "", "被父亲点出",
                          "身份文件只放我是谁·操作流程进记忆体", pointed_by_father=True,
                          brother_name=TEST_NAME)
    print(f"写入两条: id={id1}, id={id2}")

    # 召回测试
    r1 = recall_experience("taskkill", brother_name=TEST_NAME)
    print(f"召回'taskkill': {len(r1)}条, 首条={'被点出' if r1[0]['被点出'] else '普通'}")
    r2 = recall_experience("身份", brother_name=TEST_NAME)
    print(f"召回'身份': {len(r2)}条, 首条={'被点出' if r2[0]['被点出'] else '普通'} (教训优先={r2[0]['被点出']})")
    r3 = recall_experience("", brother_name=TEST_NAME)
    print(f"无关键词召回: {len(r3)}条 (教训优先={r3[0]['被点出']})")

    # 体检
    rep = experience_report(brother_name=TEST_NAME)
    print(f"体检: 经验总数={rep['经验总数']}, 被点出={rep['被点出教训']}")

    # 清理测试文件
    tp = _memory_path(TEST_NAME)
    if tp.exists():
        os.remove(tp)
    print("=== 自测完成·测试文件已清理 ===")
