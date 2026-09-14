# -*- coding: utf-8 -*-
"""效果驱动强化（父令 2026-09-14 · 外部评价方向①+② 合并落地）
================================================================
**为什么有这个模块**：
外部 AI 对记忆体的评价（2026-09-14 父亲转来）——
「进化需要三件事：有变化 ✅ / 有选择 ⚠️弱 / 有积累 ✅。
 你们缺的不是新功能，是把『使用效果 → 强化/削弱』这条反馈链打通，让选择真正发生。」
父亲 8/16 也说过同一件事：「做一件事情之前，能改变长期用法——好用下次还这么用，
吃瘪了知道改道。」大哥 8/27 自省：「记忆被召回/注入，但还没有改变行为。」

**本模块做什么**：给每条记忆加一个**使用效果信号**——不是"用了就热"（频率），
而是"用了之后效果好不好"（效果）。

三个信号（全自动·纯规则·零模型·零 API）：
  · 被引用  +1   注入的记忆概念出现在我的回复里 → 说明真被用上了
  · 被确认  +2   父亲肯定（对/好/正是/就是这样…）→ 这条记忆帮上了忙
  · 被纠正  -2   父亲否定（不对/不是/错了/没用…）→ 这条记忆带偏了

存储：sunmem.db 的 effect_scores 表（与 memories 同库·不碰主表结构）

接口：
  记录注入(mids, 注入文本)          → prefetch 时调（记下"这轮给了什么"）
  结算本轮(父亲的话, 我的回复)       → sync_turn 时调（结算上一轮"用得怎么样"）
  效果分(mid) / 批量效果分(mids)    → 召回排序可选加项
  统计()                            → 观测（命中率/正负分布）

安全设计：
  · **影子模式默认开**：只记录不参与排序（SUNMEM_EFFECT_APPLY=1 才参与），
    先跑几天看信号准不准，再按父令"小步试点"精神接入排序
  · 效果分有上下限（±5）·防单条记忆被反复刷分
  · 结算失败不影响主流程（异常兜底·但不静默——debug 日志留痕）
"""
import os
import re
import sqlite3

_DB = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sunmem.db"))

# ── 信号词表（纯规则·可调）──
肯定词 = ("对", "好的", "好", "是的", "正是", "就是这样", "没错", "可以", "漂亮",
          "厉害", "棒", "很好", "不错", "正确", "就这样", "成了", "通了")
否定词 = ("不对", "不是", "错了", "有误", "没用", "不行", "别", "没有", "漏了",
          "少了", "不准确", "打脸", "失败", "退回", "重来", "再改", "又错")

# 效果分上限（防刷分）
_上限 = 5.0


def _连接(可写: bool = True):
    if 可写:
        c = sqlite3.connect(_DB, timeout=8.0)
        c.execute("PRAGMA journal_mode=WAL")
        return c
    return sqlite3.connect(f"file:{_DB}?mode=ro", uri=True, timeout=5.0)


def _建表():
    try:
        with _连接() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS effect_scores (
                mid INTEGER PRIMARY KEY,
                被引用 INTEGER DEFAULT 0,
                被确认 INTEGER DEFAULT 0,
                被纠正 INTEGER DEFAULT 0,
                效果分 REAL DEFAULT 0.0,
                最后更新 TEXT DEFAULT '',
                来源轮 INTEGER DEFAULT 0
            )""")
            c.commit()
    except Exception as _e:  # 2026-09-14 按《模块标准》⑤修：建表失败=功能全废·必须留痕（原静默 pass）
        import sys as _sys
        print(f"[效果驱动] ⚠️ effect_scores 建表失败: {_e}", file=_sys.stderr)


def _概念集(文本: str, 上限: int = 12) -> set:
    """轻量概念提取（复用联想召回的正规提取·失败退化为 2-6 字中文词）"""
    if not 文本:
        return set()
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from 联想召回 import 概念提取
        cs = 概念提取(文本, 上限=上限)
        if cs:
            return set(cs)
    except Exception as _e:  # 2026-09-14 按标准⑤：概念提取退化到正则（可接受·但留 debug 痕迹）
        import sys as _sys
        print(f"[效果驱动] · 概念提取退化: {type(_e).__name__}", file=_sys.stderr)
    return set(re.findall(r'[\u4e00-\u9fff]{2,6}', 文本)) - set()


def _bigrams(s: str) -> set:
    s = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', s or '')
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()


def _用上了(注入文本: str, 回复文本: str, 阈值: float = 0.34) -> bool:
    """注入的内容有没有被我"用上"——bigram 重合判定
    （比"概念完全相等"稳：不依赖分词/提取质量——实测概念提取对无空格长串会切成整段）
    """
    A, B = _bigrams(注入文本), _bigrams(回复文本)
    if not A or not B:
        return False
    return len(A & B) / min(len(A), len(B)) >= 阈值


# ── 轮次状态（进程内·由 provider 每轮调）──
_本轮 = {"注入": []}       # [{"mid": int, "摘要": str, "概念": set}]


def 记录注入(记忆列表: list, 来源: str = "prefetch"):
    """prefetch 时调用：记下这轮注入了哪些记忆（含它们的概念）
    记忆列表: [{"id": int, "摘要"/"内容": str}, ...]
    """
    _本轮["注入"] = []
    for m in (记忆列表 or [])[:25]:
        mid = m.get("id") or m.get("记忆id")
        if not mid:
            continue
        文本 = str(m.get("摘要") or m.get("内容") or m.get("content") or "")[:200]
        _本轮["注入"].append({"mid": int(mid), "摘要": 文本[:60], "原文": 文本, "概念": _概念集(文本)})
    return len(_本轮["注入"])


def _加一笔(mid: int, 字段: str, Δ: float, 轮: int = 0):
    """给一条记忆记一笔效果账（上下限保护）"""
    if not mid:
        return
    列 = {"被引用": "被引用", "被确认": "被确认", "被纠正": "被纠正"}[字段]
    try:
        with _连接() as c:
            c.execute("""INSERT INTO effect_scores (mid, 被引用, 被确认, 被纠正, 效果分, 最后更新, 来源轮)
                         VALUES (?,0,0,0,0.0,datetime('now','localtime'),?)
                         ON CONFLICT(mid) DO NOTHING""", (mid, 轮))
            if 字段 != "被引用":
                c.execute(f"UPDATE effect_scores SET {列} = {列} + 1, 效果分 = MAX(-?, MIN(?, 效果分 + ?)), "
                          f"最后更新 = datetime('now','localtime'), 来源轮 = ? WHERE mid = ?",
                          (_上限, _上限, Δ, 轮, mid))
            else:
                c.execute("UPDATE effect_scores SET 被引用 = 被引用 + 1, "
                          "效果分 = MAX(-?, MIN(?, 效果分 + ?)), "
                          "最后更新 = datetime('now','localtime'), 来源轮 = ? WHERE mid = ?",
                          (_上限, _上限, Δ, 轮, mid))
            c.commit()
    except Exception as _e:  # 2026-09-14 按标准⑤修：记账失败=效果信号丢失·留痕（原静默 pass）
        import sys as _sys
        print(f"[效果驱动] ⚠️ 记账失败(mid={mid}): {_e}", file=_sys.stderr)


def 结算本轮(父亲的话: str, 我的回复: str, 轮: int = 0) -> dict:
    """sync_turn 时调用：结算上一轮注入的效果
    返回 {"被引用": n, "被确认": n, "被纠正": n}
    """
    注入 = _本轮.get("注入") or []
    if not 注入:
        return {"被引用": 0, "被确认": 0, "被纠正": 0, "说明": "上轮无注入"}

    _建表()
    回复概念 = _概念集(我的回复, 上限=20)
    父亲话 = (父亲的话 or "").strip()

    # ① 被引用：注入记忆的内容出现在我的回复里（bigram 重合 ≥34% = 真用上）
    被引用 = 0
    for it in 注入:
        if _用上了(it.get("原文") or it.get("摘要", ""), 我的回复):
            _加一笔(it["mid"], "被引用", 1.0, 轮)
            被引用 += 1

    # ② 被确认 / ③ 被纠正：看父亲这一轮的话（只对"被引用过"或"注入了还没结算"的记忆动账）
    被确认 = 被纠正 = 0
    打 = None
    if 父亲话:
        if any(w in 父亲话 for w in 否定词):
            打 = ("被纠正", -2.0)
        elif any(w in 父亲话 for w in 肯定词) and len(父亲话) <= 40:
            打 = ("被确认", 2.0)
    if 打:
        字段, Δ = 打
        # 对上一轮注入过的记忆记账（被引用的优先·其余轻记）
        for it in 注入[:5]:
            _加一笔(it["mid"], 字段, Δ, 轮)
            if 字段 == "被确认":
                被确认 += 1
            else:
                被纠正 += 1

    _本轮["注入"] = []   # 结算完清空
    return {"被引用": 被引用, "被确认": 被确认, "被纠正": 被纠正}


def 效果分(mid: int) -> float:
    try:
        with _连接(可写=False) as c:
            r = c.execute("SELECT 效果分 FROM effect_scores WHERE mid=?", (mid,)).fetchone()
            return float(r[0]) if r else 0.0
    except Exception:
        return 0.0


def 批量效果分(mids: list) -> dict:
    out = {}
    if not mids:
        return out
    try:
        with _连接(可写=False) as c:
            q = ",".join("?" * len(mids))
            for mid, s in c.execute(f"SELECT mid, 效果分 FROM effect_scores WHERE mid IN ({q})", list(mids)):
                out[int(mid)] = float(s or 0)
    except Exception:
        pass
    return out


def 影子模式() -> bool:
    """True=只记录不参与排序 · False=参与排序
    2026-09-14 父令「把它加入进去」→ **默认生效**；
    观测期可用 SUNMEM_EFFECT_SHADOW=1 切回影子模式（只记录不排序）
    """
    return os.environ.get("SUNMEM_EFFECT_SHADOW", "0") == "1"


def 统计() -> dict:
    _建表()
    try:
        with _连接(可写=False) as c:
            总 = c.execute("SELECT COUNT(*), SUM(被引用), SUM(被确认), SUM(被纠正) FROM effect_scores").fetchone()
            正 = c.execute("SELECT COUNT(*) FROM effect_scores WHERE 效果分 > 0").fetchone()[0]
            负 = c.execute("SELECT COUNT(*) FROM effect_scores WHERE 效果分 < 0").fetchone()[0]
            top = c.execute("SELECT mid, 效果分 FROM effect_scores ORDER BY 效果分 DESC LIMIT 5").fetchall()
        return {"记账条目": 总[0] or 0, "被引用合计": 总[1] or 0, "被确认合计": 总[2] or 0,
                "被纠正合计": 总[3] or 0, "正分条": 正, "负分条": 负,
                "最高分": [{"mid": m, "分": round(s, 2)} for m, s in top]}
    except Exception as e:
        return {"错误": str(e)[:80]}


if __name__ == "__main__":
    # 自检用临时库（绝不碰真库——父训：铁律，测试不污染生产）
    import tempfile
    _tmp = os.path.join(tempfile.gettempdir(), "effect_selftest.db")
    if os.path.exists(_tmp):
        os.remove(_tmp)
    os.environ["SUNMEM_DB"] = _tmp
    globals()["_DB"] = _tmp
    print("=== 效果驱动 · 自检（临时库）===")
    print("影子模式:", 影子模式(), "（True=只记录·不参与排序）")
    _建表()
    # 造一次注入 + 结算
    n = 记录注入([{"id": 1, "摘要": "统计力学配分函数的定义与自由能关系"},
                 {"id": 2, "摘要": "孙家模块标准 v1.0 的十五项检查清单"}])
    print("记录注入:", n, "条")
    r1 = 结算本轮("配分函数是怎么定义的？", "配分函数是统计力学的核心，自由能由它导出")
    print("结算1（应命中被引用）:", r1)
    n = 记录注入([{"id": 3, "摘要": "旧版本错误的三值量化方案"}])
    r2 = 结算本轮("不对，这个方案是错的", "抱歉，我改了")
    print("结算2（应命中被纠正）:", r2)
    print("统计:", 统计())
    print("✅ 自检完成")
