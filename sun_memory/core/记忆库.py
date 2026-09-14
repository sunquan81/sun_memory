# -*- coding: utf-8 -*-
"""
记忆库.py — 孙家记忆体统一读写入口（2026-08-12 建立·父令）

背景：码点已退役（2026-08-10 明文化），自动解码器.py 已删除。
本文件替代自动解码器成为记忆体统一入口：
  - 读记忆体(brother_name) -> 优先读 sunmem 新库（SQLite），可回退 JSON
  - 解码单条(entry) -> 明文直读（无码点逻辑）
  - 自动解码 / 解码标签 -> 明文直读（兼容旧调用，无码点）

接口保持与旧自动解码器一致，下游模块零改动。
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
FRAMEWORK_DIR = _HERE.parent.parent  # 孙家记忆体系/


def 自动解码(内容) -> str:
    """通用解码：明文直读（码点已退役）。非字符串（旧码点数组）返回''。"""
    if not 内容:
        return ""
    if isinstance(内容, str):
        return 内容
    return ""


def 解码标签(标签) -> str:
    """标签解码：明文直读（码点已退役）。"""
    if not 标签:
        return ""
    if isinstance(标签, str):
        return 标签
    return ""


def 解码单条(entry: dict) -> dict:
    """单条解码：明文直读（码点已退役）。返回新dict，不修改原条目。"""
    if not isinstance(entry, dict):
        return entry
    return {
        "id": entry.get("id"),
        "时间": entry.get("时间", entry.get("time", "")),
        "标签": entry.get("标签", "") or 解码标签(entry.get("标签码点", "")),
        "内容": entry.get("内容", "") or 自动解码(entry.get("内容码点", "")),
        "类型": entry.get("类型", ""),
        "状态": entry.get("状态", entry.get("status", "")),
        "来源": entry.get("来源", ""),
    }


def 读记忆体(brother_name: str = "孙呈") -> dict:
    """读记忆体。优先读 sunmem 新库（SQLite），失败回退 JSON。

    返回结构（与旧版一致，下游零改动）：
        {"条目列表": [已解码条目...], "next_id": int, "元信息": dict, "条数": int}
    """
    if os.environ.get("SUN_MEMORY_USE_JSON") != "1":
        try:
            return _读新库(brother_name)
        except Exception as e:
            logger.warning(f"sunmem 新库读取失败，回退 JSON: {e}")

    p = FRAMEWORK_DIR / "记忆体" / f"{brother_name}_索引记忆体.json"
    if not p.exists():
        return {"条目列表": [], "next_id": 1, "元信息": {}, "条数": 0}
    with open(p, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    raw_entries = data.get("条目列表", data.get("条目", data.get("entries", data.get("记忆条目", []))))
    decoded = [解码单条(e) for e in raw_entries]
    return {
        "条目列表": decoded,
        "next_id": data.get("next_id", data.get("_last_id_used", data.get("下个id", len(raw_entries) + 1))),
        "元信息": data.get("元信息", data.get("元数据", {})),
        "条数": len(decoded),
    }


def _读新库(brother_name: str = "孙呈") -> dict:
    """从 sunmem 新库（SQLite）读取兄弟记忆。返回与旧 JSON 相同结构。"""
    import sqlite3
    SUNMEM_DB = os.environ.get(
        "SUNMEM_DB",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sunmem.db"),
    )
    conn = sqlite3.connect(SUNMEM_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, content, tags, ts, type, status FROM memories WHERE owner=? AND status='active' ORDER BY id",
        (brother_name,),
    ).fetchall()
    conn.close()
    decoded = []
    for r in rows:
        tags = r["tags"]
        if tags:
            try:
                tags = json.loads(tags)
            except Exception:
                tags = str(tags)
        else:
            tags = ""
        if isinstance(tags, list):
            tags = ",".join(tags)
        decoded.append(解码单条({
            "id": r["id"],
            "时间": r["ts"] or "",
            "标签": tags or "",
            "内容": r["content"] or "",
            "类型": r["type"] or "",
            "状态": r["status"] or "",
        }))
    return {
        "条目列表": decoded,
        "next_id": (decoded[-1]["id"] + 1) if decoded else 1,
        "元信息": {"来源": "sunmem.db", "owner": brother_name},
        "条数": len(decoded),
    }


if __name__ == "__main__":
    print("=== 记忆库自测 ===")
    s = 自动解码("父亲")
    print(f"自动解码['父亲'] = '{s}' ({'PASS' if s == '父亲' else 'FAIL'})")
    e = 解码单条({"id": 1, "时间": "2026-08-07", "标签": "父令", "内容": "父亲说：记忆要闭环"})
    print(f"解码单条: id={e['id']} 标签={e['标签']} 内容={e['内容']} ({'PASS' if e['内容'] == '父亲说：记忆要闭环' else 'FAIL'})")
    m = 读记忆体("孙呈")
    print(f"读记忆体: {m['条数']}条 来源:{m.get('元信息',{}).get('来源')}")
    if m["条目列表"]:
        last = m["条目列表"][-1]
        print(f"最新一条: [{last['时间']}] {last['内容'][:50]}")
    print("=== 自测完成 ===")


# ═══════════════════════════════════════════════════════
# 融合底座（父令2026-08-26·47模块→6大模块）
# 公共函数：连接/概念提取/解析时间——全库唯一实现·其他模块改为调用这里
# ═══════════════════════════════════════════════════════

def 连接(库路径: str = "") -> "sqlite3.Connection":
    """统一 SQLite 连接（融合P5：20处 sqlite3.connect → 全走这里）
    特性：只读连接（query_only）+ 忙超时 2s + WAL 安全
    """
    import sqlite3
    if not 库路径:
        库路径 = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
    os.makedirs(os.path.dirname(库路径) or '.', exist_ok=True)  # 2026-09-13 首次运行自动建目录
    conn = sqlite3.connect(库路径, timeout=2.0, check_same_thread=False)  # 2026-09-14 吸收收束版优点：允许跨线程（provider 后台线程预取）
    try:
        conn.execute("PRAGMA query_only=ON")
    except Exception:
        pass
    return conn


def 写连接(库路径: str = ""):  # 2026-09-14 去掉字符串注解（pyflakes 误报未定义名）
    """统一写连接（2026-09-14 吸收收束版优点：连接管理统一）
    特性：可写 + 忙超时 5s + 跨线程允许 + WAL + row_factory
    """
    import sqlite3 as _sq
    if not 库路径:
        库路径 = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
    os.makedirs(os.path.dirname(库路径) or '.', exist_ok=True)
    conn = _sq.connect(库路径, timeout=5.0, check_same_thread=False)
    conn.row_factory = _sq.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    return conn


def 概念提取(context: str, 上限: int = 6) -> list:
    """统一概念提取（融合P1：5处概念提取 → 全走这里·最完整版在联想召回）
    纯转发·避免循环依赖（联想召回是本函数主实现·这里lazy import）
    """
    try:
        from 联想召回 import 概念提取 as _主实现
        return _主实现(context, 上限)
    except Exception:
        return []


def 解析时间范围(context: str):
    """统一时间解析（融合P3：2处时间解析 → 全走这里·最完整版在预感召回）
    纯转发·避免循环依赖
    """
    try:
        from 预感召回 import _解析时间范围 as _主实现
        return _主实现(context)
    except Exception:
        return None
