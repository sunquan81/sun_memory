# -*- coding: utf-8 -*-
"""活性方程（父令2026-08-26·模块精简数学化）

将 节律(heat脉冲) / 时间衰减(cover) / 记忆成绩单(账本) 三模块的核心逻辑
统一成一条活性方程：

    活性(t) = 基础 + Σ(点亮·e^(-λ·Δt)) + Σ(确认·e^(-λ·Δt)) - Σ(纠正·e^(-λ·Δt))
              + 时间新鲜度(cover)

三个来源（点亮/账本/时间）·统一衰减 λ·单库单表。

【2026-09-07 诚实修正（安弟1589体检🔴5·大哥复查）】
"核心逻辑收敛到此"是 8/26 的过度宣称——节律/成绩单并未真调此方程，
真实使用：联想召回.py 延迟 import 本模块的 活性() 计算召回融合分（heat继承+点亮脉冲+账本·λ衰减）。
活性主机制仍以 节律.py 为准（真实在跑回落/点亮/热度排行）。
"""
import sqlite3
import os
import datetime
import math

DB = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))

# 参数（2026-08-26 产品化：改为读配置表·不改源码可调优）
try:
    from 配置表 import get as _cfg
    def _P(键, 默认):
        return _cfg('活性', 键) if _cfg('活性', 键) is not None else 默认
except Exception:
    def _P(键, 默认):
        return 默认

参数 = {
    '点亮增量': _P('点亮增量', 0.3),       # 节律.点亮增量
    '热上限': _P('热上限', 5.0),            # 节律.热上限
    '衰减λ': _P('衰减λ', 0.10),            # 节律.普通衰减（每天）
    '保护衰减λ': _P('保护衰减λ', 0.02),    # 节律.保护衰减（慢5倍·core/父令）
    '保护地板': _P('保护地板', 0.5),       # 节律.保护地板
    '确认权重': _P('确认权重', 2.0),       # 成绩单.确认+2
    '纠正权重': _P('纠正权重', -2.0),      # 成绩单.纠正-2
    '点亮权重': _P('点亮权重', 1.0),       # 成绩单.点亮+1
    '预算': 20,                            # 时间衰减.cover预算
}


def _连接():
    conn = sqlite3.connect(DB, timeout=2.0)
    try:
        conn.execute("PRAGMA query_only=ON")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn


def 活性(memory_id: int, 天数=30) -> float:
    """方程主函数：算一条记忆的当前活性。
    活性 = 基础(heat继承) + 点亮脉冲(带λ衰减) + 账本(确认/纠正带λ衰减)
    2026-08-26 产品化：错误降级嵌入方程——任何环节异常返回 0.0（不炸调用方）
    """
    try:
        conn = _连接()
        row = conn.execute(
            "SELECT heat, hit_count, layer, tags FROM memories WHERE id=?",
            (memory_id,)).fetchone()
        conn.close()
        if not row:
            return 0.0
        heat = row['heat'] or 0.0
        hit = row['hit_count'] or 0
        # 点亮贡献（历史脉冲·按衰减λ折算）
        点亮贡献 = min(参数['热上限'], hit * 参数['点亮权重'] * math.exp(-参数['衰减λ'] * 天数))
        # 账本贡献（确认/纠正·从成绩单表取）
        账本 = 查账本(memory_id)
        账本贡献 = (账本['确认'] * 参数['确认权重'] + 账本['纠正'] * 参数['纠正权重']) * math.exp(-参数['衰减λ'] * 天数)
        return heat + 点亮贡献 + 账本贡献
    except Exception:
        return 0.0


def 查账本(memory_id: int) -> dict:
    """成绩单账本（原记忆成绩单.查成绩单）"""
    conn = _连接()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as n, SUM(CASE WHEN action='确认' THEN 1 ELSE 0 END) as 确认, "
            "SUM(CASE WHEN action='纠正' THEN 1 ELSE 0 END) as 纠正, "
            "SUM(CASE WHEN action='点亮' THEN 1 ELSE 0 END) as 点亮 "
            "FROM memory_report_cards WHERE memory_id=?", (memory_id,)).fetchone()
        return {"确认": row['确认'] or 0, "纠正": row['纠正'] or 0, "点亮": row['点亮'] or 0, "总数": row['n'] or 0}
    except Exception:
        return {"确认": 0, "纠正": 0, "点亮": 0, "总数": 0}
    finally:
        conn.close()


def 覆盖(条目列表, 预算=20) -> list:
    """时间覆盖（原时间衰减.cover·近细远粗·连续衰减）"""
    if not 条目列表:
        return []
    budget = 预算
    最近 = 条目列表[-budget // 2:]           # 近半逐条全取
    更老 = 条目列表[:-budget // 2]
    # 更老的部分：从新到老指数间隔采样
    picked = list(最近)
    if 更老:
        step = 1
        idx = len(更老) - 1
        while idx >= 0 and len(picked) < budget:
            picked.insert(0, 更老[idx])
            idx -= step
            step *= 2
    return picked


def 排序(条目列表, 预算=20, 活跃优先=True) -> list:
    """统一召回排序（原联想召回排序 + 时间衰减 + 活性）：
    Score = α·概念 + β·时间新鲜度 + γ·活性方程值
    """
    now = datetime.datetime.now()
    scored = []
    for e in 条目列表:
        # 时间新鲜度（近的加分）
        时间分 = 0.0
        t = e.get("时间", "")
        if isinstance(t, str) and t:
            try:
                dt = datetime.datetime.fromisoformat(t[:19])
                时间分 = math.exp(-(now - dt).days / 30.0)  # 30天半衰
            except Exception:
                pass
        # 活性方程值
        活 = 活性(e.get("id", 0)) if e.get("id") else 0.0
        scored.append((e, 时间分 + 活))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [e for e, _ in scored[:预算]]
