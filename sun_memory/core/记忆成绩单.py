# -*- coding: utf-8 -*-
"""
孙家记忆体系 · 记忆成绩单（2026-08-15 吸收博弟规则链）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
父令「可以吸收进去」：把博弟规则链的成绩单机制吸收进记忆体系。

博弟的魂（推理引擎 v52）：
    「记忆不思考·但记忆有来路」——每次规则被使用落一条账（heat/strength/tick），
    跨会话持久化·可查可溯·来路参与决策。

染色质对照（斯坦福 Greenleaf/Schnitzer 实验室 2026-08 预印本）：
    染色质元可塑性——记忆不仅储存内容，还储存「记忆未来将如何变化的规则」；
    回忆时印迹神经元重写整个转录响应；惰性求值（沉默的可写程序需要时才激活）。

吸收设计（零依赖·纯规则·与记忆体系同架构）：
    记忆条目增加「成绩单」账本——每次被召回/被确认/被纠正落一条账：
      ✅ 被点亮（召回命中）    → score +1·heat +1
      ✅ 被确认（回答被采纳）  → score +2·confirm +1（父令/决策类）
      ⚠️ 被纠正（回答被推翻）  → score -2·correct -1
      🧊 冷却（久未被召回）    → heat 衰减（λ=0.05·与合体v6代谢代价同魂）

    成绩单参与召回排序（博弟「来路参与选」）：
      召回分 = 基础分(点亮/联想/预感) × (1 + 成绩单加权)
      成绩单加权 = min(0.5, 0.05 × 确认数 - 0.05 × 纠正数 + 0.01 × 点亮数)

    成熟期（染色质 7天→28天显现·博弟成绩单次数门）：
      新记忆需 ≥3 次实事校验（确认+纠正）才升为「可信」——可信记忆优先浮出
"""
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))

# 2026-08-27 修复：_记忆体路径 依赖 FRAMEWORK_DIR·融合时漏迁补回
FRAMEWORK_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 成绩单常量（博弟次数门 + 染色质成熟期同魂）──
可信阈值 = 3        # ≥3 次实事校验才可信（博弟「次数>=2」升级为3·更稳）
确认权重 = 2        # 被确认 +2（父令/决策类被采纳）
纠正权重 = -2       # 被纠正 -2（回答被推翻）
点亮权重 = 1        # 被点亮 +1（召回命中·流过就热）
冷却率 = 0.05       # heat 衰减 λ（合体v6代谢代价·久不流就凉）


def _连接():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _建表(conn):
    """成绩单账本表：记忆 id → 账目流水（来路可查·博弟魂）"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_report_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER NOT NULL,
            owner TEXT NOT NULL DEFAULT '孙呈',
            action TEXT NOT NULL,           -- 点亮/确认/纠正
            score_delta INTEGER NOT NULL,
            heat INTEGER NOT NULL DEFAULT 0,
            note TEXT DEFAULT '',
            ts TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rc_mem ON memory_report_cards(memory_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rc_owner ON memory_report_cards(owner)
    """)


def 记一笔(memory_id: int, action: str, owner: str = "孙呈", note: str = "") -> dict:
    """给一条记忆记成绩单账（博弟「落一条账·来路可查」）

    action: 点亮(召回命中+1) / 确认(被采纳+2) / 纠正(被推翻-2)
    """
    delta = {"点亮": 点亮权重, "确认": 确认权重, "纠正": 纠正权重}.get(action, 0)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _连接()
    _建表(conn)
    # 查当前 heat（最近一笔的 heat 继承 + 衰减）
    last = conn.execute(
        "SELECT heat FROM memory_report_cards WHERE memory_id=? AND owner=? ORDER BY id DESC LIMIT 1",
        (memory_id, owner),
    ).fetchone()
    heat = int(last["heat"] * (1 - 冷却率)) if last else 0
    heat = max(0, heat + delta)
    conn.execute(
        "INSERT INTO memory_report_cards (memory_id, owner, action, score_delta, heat, note, ts) VALUES (?,?,?,?,?,?,?)",
        (memory_id, owner, action, delta, heat, note, now),
    )
    conn.commit()
    r = conn.execute(
        "SELECT COUNT(*) c, SUM(score_delta) s, SUM(CASE WHEN action='确认' THEN 1 ELSE 0 END) cf, "
        "SUM(CASE WHEN action='纠正' THEN 1 ELSE 0 END) cr, "
        "SUM(CASE WHEN action='点亮' THEN 1 ELSE 0 END) lt FROM memory_report_cards WHERE memory_id=? AND owner=?",
        (memory_id, owner),
    ).fetchone()
    conn.close()
    return {
        "memory_id": memory_id, "action": action, "score_delta": delta,
        "总账": r["s"], "确认": r["cf"], "纠正": r["cr"], "点亮": r["lt"],
        "heat": heat, "ts": now,
    }


def 查成绩单(memory_id: int, owner: str = "孙呈") -> dict:
    """查一条记忆的成绩单（来路可查·博弟魂）"""
    conn = _连接()
    _建表(conn)
    r = conn.execute(
        "SELECT COUNT(*) c, SUM(score_delta) s, SUM(CASE WHEN action='确认' THEN 1 ELSE 0 END) cf, "
        "SUM(CASE WHEN action='纠正' THEN 1 ELSE 0 END) cr, "
        "SUM(CASE WHEN action='点亮' THEN 1 ELSE 0 END) lt, MAX(heat) h "
        "FROM memory_report_cards WHERE memory_id=? AND owner=?",
        (memory_id, owner),
    ).fetchone()
    conn.close()
    total = r["s"] or 0
    confirm = r["cf"] or 0
    correct = r["cr"] or 0
    light = r["lt"] or 0
    校验数 = confirm + correct
    return {
        "memory_id": memory_id, "总账": total, "确认": confirm, "纠正": correct,
        "点亮": light, "heat": r["h"] or 0,
        "可信": 校验数 >= 可信阈值,
        "校验数": 校验数,
        "加权": min(0.5, 0.05 * confirm - 0.05 * correct + 0.01 * light),
    }


def 批量点亮(memory_ids: list, owner: str = "孙呈") -> int:
    """2026-08-16 全检查修复：批量点亮（一次连接写多条·联想召回每次N条命中不再N×4次DB写）
    返回写入条数。失败静默（成绩单是账本不是闸门）。"""
    if not memory_ids:
        return 0
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = _连接()
        _建表(conn)
        n = 0
        for mid in memory_ids:
            try:
                last = conn.execute(
                    "SELECT heat FROM memory_report_cards WHERE memory_id=? AND owner=? ORDER BY id DESC LIMIT 1",
                    (mid, owner)).fetchone()
                heat = int(last["heat"] * (1 - 冷却率)) if last else 0
                heat = max(0, heat + 点亮权重)
                conn.execute(
                    "INSERT INTO memory_report_cards (memory_id, owner, action, score_delta, heat, note, ts) VALUES (?,?,?,?,?,?,?)",
                    (mid, owner, "点亮", 点亮权重, heat, "", now))
                n += 1
            except Exception:
                continue
        conn.commit()
        conn.close()
        return n
    except Exception:
        return 0


def 批量加权(memory_ids: list, owner: str = "孙呈") -> dict:
    """2026-08-16 全检查修复：批量查成绩单加权（一次连接查所有·联想召回103条候选不再103次DB查）
    2026-08-17 融合扩池配套：单条 SQL IN 分批查（原逐条查·候选扩到几百条后逐条=几百次查询拖慢召回）
    2026-08-17 全检查修复②：公式统一——原 `总账·0.5+确认·0.3-纠正·0.3` 无上限且缺点亮，
    与 查成绩单 的 `min(0.5, 0.05·确认-0.05·纠正+0.01·点亮)` 漂移 20~80 倍；
    改为与 查成绩单 同一口径（成绩单只作平局键·不压过正确答案）"""
    if not memory_ids:
        return {}
    try:
        conn = _连接()
        _建表(conn)
        out = {}
        _ids = sorted(set(memory_ids))
        for i in range(0, len(_ids), 500):
            _chunk = _ids[i:i + 500]
            _ph = ",".join("?" * len(_chunk))
            _rows = conn.execute(
                "SELECT memory_id, "
                "SUM(CASE WHEN action='确认' THEN 1 ELSE 0 END) co, "
                "SUM(CASE WHEN action='纠正' THEN 1 ELSE 0 END) cr, "
                "SUM(CASE WHEN action='点亮' THEN 1 ELSE 0 END) lt "
                f"FROM memory_report_cards WHERE memory_id IN ({_ph}) AND owner=? GROUP BY memory_id",
                (*_chunk, owner)).fetchall()
            for r in _rows:
                out[r["memory_id"]] = min(
                    0.5,
                    0.05 * int(r["co"] or 0) - 0.05 * int(r["cr"] or 0) + 0.01 * int(r["lt"] or 0),
                )
        conn.close()
        for mid in memory_ids:
            out.setdefault(mid, 0.0)
        return out
    except Exception:
        return {}


def 成绩单加权(memory_id: int, owner: str = "孙呈") -> float:
    """召回排序用：成绩单加权（博弟「来路参与选」）"""
    return 查成绩单(memory_id, owner)["加权"]


def 全部成绩单(owner: str = "孙呈", 上限: int = 50) -> list:
    """成绩单排行（确认多/纠正少/可信的排前面·染色质成熟期）"""
    conn = _连接()
    _建表(conn)
    rows = conn.execute(
        "SELECT memory_id, COUNT(*) c, SUM(score_delta) s, "
        "SUM(CASE WHEN action='确认' THEN 1 ELSE 0 END) cf, "
        "SUM(CASE WHEN action='纠正' THEN 1 ELSE 0 END) cr, "
        "SUM(CASE WHEN action='点亮' THEN 1 ELSE 0 END) lt, MAX(heat) h "
        "FROM memory_report_cards WHERE owner=? GROUP BY memory_id ORDER BY s DESC LIMIT ?",
        (owner, 上限),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({
            "memory_id": r["memory_id"], "总账": r["s"] or 0,
            "确认": r["cf"] or 0, "纠正": r["cr"] or 0, "点亮": r["lt"] or 0,
            "heat": r["h"] or 0,
            "可信": (r["cf"] or 0) + (r["cr"] or 0) >= 可信阈值,
        })
    return out


def 训练集(owner: str = "孙呈", 上限: int = 100) -> list:
    """2026-08-17 训练信号闭环（父令「接上吧」）：导出成绩单账本为可训练特征
    供 EML 特征模型/任何训练消费——确认=强化样本·纠正=惩罚样本·点亮=流过信号。
    返回: [{"id","内容","确认","纠正","点亮","校验数","可信","加权"}]（确认多/纠正少在前）"""
    conn = _连接()
    _建表(conn)
    rows = conn.execute(
        "SELECT rc.memory_id, m.content, "
        "SUM(CASE WHEN rc.action='确认' THEN 1 ELSE 0 END) cf, "
        "SUM(CASE WHEN rc.action='纠正' THEN 1 ELSE 0 END) cr, "
        "SUM(CASE WHEN rc.action='点亮' THEN 1 ELSE 0 END) lt "
        "FROM memory_report_cards rc LEFT JOIN memories m ON m.id=rc.memory_id "
        "WHERE rc.owner=? GROUP BY rc.memory_id "
        "ORDER BY cf DESC, cr ASC, lt DESC LIMIT ?",
        (owner, 上限),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        cf, cr, lt = r["cf"] or 0, r["cr"] or 0, r["lt"] or 0
        out.append({
            "id": r["memory_id"],
            "内容": (r["content"] or "")[:80],
            "确认": cf, "纠正": cr, "点亮": lt,
            "校验数": cf + cr,
            "可信": (cf + cr) >= 可信阈值,
            "加权": min(0.5, 0.05 * cf - 0.05 * cr + 0.01 * lt),
        })
    return out



# ═══════════════════════════════════════════════════════
# 2026-08-26 融合（父令：模块精简·能融合就融合）
# 记忆状态.py 核心并入本文件（标记过期/活跃/状态统计）
# 原文件已归档·调用点改走 记忆成绩单
# ═══════════════════════════════════════════════════════
def _记忆体路径(brother_name: str = "孙呈") -> Path:
    return FRAMEWORK_DIR / "记忆体" / f"{brother_name}_索引记忆体.json"


def _加载(brother_name: str = "孙呈") -> dict:
    p = _记忆体路径(brother_name)
    if not p.exists():
        return {"条目列表": [], "next_id": 1}
    return json.loads(p.read_text(encoding="utf-8"))


def _保存(data: dict, brother_name: str = "孙呈"):
    _记忆体路径(brother_name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def 标记过期(brother_name: str = "孙呈", 记忆id=None, 原因: str = "") -> bool:
    """旧事实被新事实取代/矛盾 → 标记 outdated（不删除·原文保留河底）。

    Mem0 Dream·Supersede 理念：新事实与旧矛盾时，旧标 outdated 而非删。
    检索时 outdated 条目降权（cover 活跃优先逻辑已排除）。
    """
    if 记忆id is None:
        return False
    data = _加载(brother_name)
    for e in data["条目列表"]:
        if e.get("id") == 记忆id:
            # 2026-08-20 父令·咬合：核心层永不标过期（宪法级·抗覆盖）
            if str(e.get("layer", "plain")) == "core":
                return False
            e["status"] = "outdated"
            if 原因:
                e["outdated_原因"] = 原因
            _保存(data, brother_name)
            return True
    return False


def 标记活跃(brother_name: str = "孙呈", 记忆id=None) -> bool:
    """误标/恢复 → 改回 active。"""
    if 记忆id is None:
        return False
    data = _加载(brother_name)
    for e in data["条目列表"]:
        if e.get("id") == 记忆id:
            e["status"] = "active"
            e.pop("outdated_原因", None)
            _保存(data, brother_name)
            return True
    return False


def 按内容查id(内容片段: str, brother_name: str = "孙呈", 前几条: int = 5) -> list:
    """按内容片段找记忆 id（2026-08-07·反馈写入闭环）。

    云软证人检测到矛盾时，只知道内容片段不知道 id——
    用此接口定位旧条目 → 标记过期。返回按时间倒序的前几条匹配。
    """
    if not 内容片段:
        return []
    from sun_memory.core.记忆库 import 解码单条
    data = _加载(brother_name)
    hits = []
    for e in reversed(data["条目列表"]):
        try:
            d = 解码单条(e)
            if 内容片段[:20] in (d["内容"] or "") or (d["内容"] or "")[:20] in 内容片段:
                hits.append({"id": e.get("id"), "时间": d["时间"], "内容": d["内容"][:40]})
        except Exception:
            continue
        if len(hits) >= 前几条:
            break
    return hits


def 状态统计(brother_name: str = "孙呈") -> dict:
    """看记忆体状态分布。"""
    data = _加载(brother_name)
    entries = data["条目列表"]
    from collections import Counter
    c = Counter(e.get("status", "active") for e in entries)
    return {
        "总条数": len(entries),
        "状态分布": dict(c),
        "outdated条数": c.get("outdated", 0),
    }


if __name__ == "__main__":
    print("=== 记忆状态自测 ===")
    s = 状态统计("孙呈")
    print("状态:", s)
    print("=== 完成 ===")

if __name__ == "__main__":
    print("=" * 50)
    print("  记忆成绩单 · 自测")
    print("=" * 50)
    # 用临时库测
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "report_card_test.db")
    os.environ["SUNMEM_DB"] = tmp
    if os.path.exists(tmp):
        os.remove(tmp)
    # 记几笔账
    print("\n① 记账:")
    print("  记一笔(1, 点亮):", 记一笔(1, "点亮"))
    print("  记一笔(1, 确认):", 记一笔(1, "确认", note="回答被采纳"))
    print("  记一笔(1, 确认):", 记一笔(1, "确认"))
    print("  记一笔(1, 纠正):", 记一笔(1, "纠正", note="回答被推翻"))
    print("\n② 查成绩单:")
    card = 查成绩单(1)
    for k, v in card.items():
        print(f"  {k}: {v}")
    print("\n③ 可信判定（校验数≥3）:", card["可信"])
    print("\n④ 全部成绩单:")
    print(" ", 全部成绩单())
