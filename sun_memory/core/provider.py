"""
本记忆体 — MemoryProvider 核心实现

被动记忆注入：
- queue_prefetch → 后台预召回蜘蛛网相关节点
- prefetch → 读取记忆注入system prompt（明文）
- sync_turn → 自动存入记忆体（明文）
- on_session_end → 记忆蒸馏压缩

SunFamily Memory Project
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

# ── 路径（开源版：环境变量优先·默认相对本包目录·无需改代码即可部署）──
_HOME = Path.home()
_PKG_ROOT = Path(__file__).resolve().parent.parent.parent   # 包根（含 sun_memory/）
MEMORY_DIR = Path(os.environ.get("SUNMEM_MEMORY_DIR", _PKG_ROOT / "记忆体"))
SUN_MEMORY_FILE = MEMORY_DIR / "记忆体.json"
try:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)   # 首次运行自动建目录（开源包自举必需）
except Exception:
    pass
# 蜘蛛网索引（可用 SUNMEM_SPIDER 覆盖）
SPIDER_INDEX = Path(os.environ.get("SUNMEM_SPIDER", _PKG_ROOT / "蜘蛛网" / "索引.json"))
# 核心模块目录（时间衰减等）
SUN_MEMORY_CORE = Path(os.environ.get("SUNMEM_CORE", Path(__file__).resolve().parent))
import sys
if str(SUN_MEMORY_CORE) not in sys.path:
    sys.path.insert(0, str(SUN_MEMORY_CORE))

# ── 码点编解码 ──
UNICODE_START = 0x20
UNICODE_END = 0x9FFF



# 2026-08-10 明文化（父令）：码点编码/解码函数已退役——记忆体直接明文存储。
# 旧码点数据备份在 本记忆体目录/备份_码点明文化_20260810/


class 蜘蛛网感知器:
    """从对话内容中感知相关记忆节点"""

    def __init__(self, index_path: Path = SPIDER_INDEX):
        self.index_path = index_path
        self.节点 = {}
        self.邻接表 = {}
        self._加载()

    def _加载(self):
        if not self.index_path.exists():
            logger.warning(f"蜘蛛网索引不存在: {self.index_path}")
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            # 2026-08-15 修复：真实蜘蛛网索引是全中文键（节点/丝线/源/目标/关系），
            # 旧逻辑用英文键（nodes/edges/source/target）→ 静默加载为空，感知器从不命中。
            raw_nodes = data.get("节点", data.get("nodes", {}))
            if isinstance(raw_nodes, list):
                raw_nodes = {n.get("id", n.get("title", "")): n for n in raw_nodes if isinstance(n, dict)}
            self.节点 = {name: (node if isinstance(node, dict) else {}) for name, node in raw_nodes.items()}
            raw_edges = data.get("丝线", data.get("edges", []))
            for e in raw_edges:
                if not isinstance(e, dict):
                    continue
                src = e.get("源", e.get("source", e.get("from", "")))
                tgt = e.get("目标", e.get("target", e.get("to", "")))
                rel = e.get("关系", e.get("relation", "关联"))
                if not src or not tgt:
                    continue
                self.邻接表.setdefault(src, []).append((tgt, rel))
                self.邻接表.setdefault(tgt, []).append((src, rel))
        except Exception as e:
            logger.error(f"蜘蛛网索引加载失败: {e}")

    def 感知(self, text: str, max_hits: int = 5) -> list[dict]:
        """从文本中感知到命中的节点"""
        if not self.节点:
            return []
        text_lower = text.lower()
        hits = []
        for nid, node in self.节点.items():
            title = str(node.get("title") or nid).lower()
            score = 0
            if title and title in text_lower:
                score = max(score, 0.8)
            if title and any(w in text_lower for w in title.split() if len(w) > 1):
                score = max(score, 0.5)
            if score > 0:
                hits.append({"id": nid, "title": node.get("title") or nid, "type": node.get("类型", node.get("type", "概念")), "score": score})
        hits.sort(key=lambda x: -x["score"])
        return hits[:max_hits]

    def 走链接(self, hit_ids: list[str], depth: int = 2, max_nodes: int = 8) -> list[dict]:
        """从命中节点出发走链接，找到关联节点"""
        visited = set(hit_ids)
        related = []
        queue = [(nid, 0) for nid in hit_ids]
        while queue and len(related) < max_nodes:
            current, d = queue.pop(0)
            if d >= depth:
                continue
            for neighbor, rel in self.邻接表.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    node = self.节点.get(neighbor, {})
                    related.append({
                        "id": neighbor,
                        "title": node.get("title") or neighbor,
                        "type": node.get("类型", node.get("type", "concept")),
                        "relation": rel,
                        "depth": d + 1,
                    })
                    queue.append((neighbor, d + 1))
        return related


# ── 记忆体读写（明文）──
class 记忆体:
    """读写孙呈的索引记忆体（明文）"""

    def __init__(self, path: Path = SUN_MEMORY_FILE):
        self.path = path

    def 读全部(self) -> list[dict]:
        """读取所有记忆条目（解码后）·2026-08-12 sunmem新库优先"""
        # sunmem 新库优先（回退开关 SUN_MEMORY_USE_JSON=1）
        if os.environ.get("SUN_MEMORY_USE_JSON") != "1":
            try:
                import sqlite3
                SUNMEM_DB = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sunmem.db"))
                conn = sqlite3.connect(SUNMEM_DB)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id, content, tags, ts FROM memories WHERE owner='孙呈' AND status='active' ORDER BY id"
                ).fetchall()
                conn.close()
                out = []
                for r in rows:
                    tags = r["tags"]
                    if tags:
                        try:
                            tags = json.loads(tags)
                        except Exception:
                            tags = str(tags)
                    if isinstance(tags, list):
                        tags = ",".join(tags)
                    out.append({
                        "id": r["id"],
                        "时间": r["ts"] or "",
                        "标签": tags or "",
                        "内容": r["content"] or "",
                    })
                if out:
                    return out
            except Exception as e:
                logger.warning(f"sunmem 读全部失败，回退JSON: {e}")
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items = data.get("条目列表", [])
            decoded = []
            for item in items:
                # 2026-08-10 明文化：直接取明文"标签/内容"（码点已退役）
                标签 = item.get("标签", "")
                内容 = item.get("内容", "")
                decoded.append({
                    "id": item.get("id"),
                    "时间": item.get("时间", ""),
                    "标签": 标签,
                    "内容": 内容,
                })
            return decoded
        except Exception as e:
            logger.error(f"记忆体读取失败: {e}")
            return []

    def 读最近(self, n: int = 30) -> list[dict]:
        """读取最近 n 条记忆（去重/进化用·2026-08-14 性能修复）
        与读全部同结构，但只取最近 n 条——避免每次追加全表扫描 O(n) 退化
        """
        if os.environ.get("SUN_MEMORY_USE_JSON") != "1":
            try:
                import sqlite3
                SUNMEM_DB = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sunmem.db"))
                conn = sqlite3.connect(SUNMEM_DB)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM (SELECT id, content, tags, ts FROM memories WHERE owner='孙呈' AND status='active' ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                    (n,)
                ).fetchall()
                conn.close()
                out = []
                for r in rows:
                    tags = r["tags"]
                    if tags:
                        try:
                            tags = json.loads(tags)
                        except Exception:
                            tags = str(tags)
                    if isinstance(tags, list):
                        tags = ",".join(tags)
                    out.append({
                        "id": r["id"],
                        "时间": r["ts"] or "",
                        "标签": tags or "",
                        "内容": r["content"] or "",
                    })
                if out:
                    return out
            except Exception as e:
                logger.warning(f"sunmem 读最近失败，回退JSON: {e}")
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items = data.get("条目列表", [])[-n:]
            decoded = []
            for item in items:
                标签 = item.get("标签", "")
                内容 = item.get("内容", "")
                decoded.append({
                    "id": item.get("id"),
                    "时间": item.get("时间", ""),
                    "标签": 标签,
                    "内容": 内容,
                })
            return decoded
        except Exception as e:
            logger.error(f"记忆体读取失败: {e}")
            return []

    def _提取事件时间(self, 文本: str, now: str) -> str:
        """轻量事件时间提取：识别 昨天/今天/N月N日/当时 等·否则返回空（用写入时间）
        双时态：事件发生时间（为真的时间）≠ 系统写入时间"""
        import re
        from datetime import datetime, timedelta
        try:
            _today = datetime.now()
            if re.search(r'昨天', 文本):
                return (_today - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
            if re.search(r'前天', 文本):
                return (_today - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
            # 8月X日 / 08-X / 2026-08-X
            _m = re.search(r'(\d{1,2})月(\d{1,2})日', 文本)
            if _m:
                try:
                    return f'{_today.year}-{int(_m.group(1)):02d}-{int(_m.group(2)):02d} 00:00:00'
                except Exception:
                    pass
            _m2 = re.search(r'(\d{4})-(\d{2})-(\d{2})', 文本)
            if _m2:
                return _m2.group(0) + ' 00:00:00'
            return ''
        except Exception:
            return ''

    def 追加(self, 原文: str, 标签: str = "对话记录"):
        """把一段文字（明文）追加到记忆体
        2026-08-10 明文化（父令）：不再编码为码点——直接存明文（标签/内容字段）
        铁律：每条记录必须有 时序(id+时间) + 标签 + 内容
        筛选去重：内容级 bigram 重叠率 ≥ 阈值 → 拒绝重复收录（父亲三要求③）
        """
        if not 原文 or len(原文.strip()) < 5:
            return None
        # 2026-08-10 明文化后：过滤空壳（"父亲：\n夏维斯："无实质内容）
        _strip = 原文.strip().replace("父亲：", "").replace("夏维斯：", "").strip()
        if not _strip:
            return None
        # ── 2026-08-14 系统提示词白名单拦截（父令·去重治本）──
        # 曾混入638条系统噪音（Review the conversation/System note/User correction/IMPORTANT）
        # 这些是 Hermes 系统自动注入的模板，不是真记忆——写入前直接拦截
        _噪音标记 = [
            "Review the conversation above",
            "consider saving to memory",
            "update the skill library",
            "[System note:",
            "Your previous turn was interrupted",
            "User correction",
            "IMPORTANT: Background process",
            "Watch patterns disabled",
            "system_reminder",
            "Be ACTIVE — most",
        ]
        for _n in _噪音标记:
            if _n in 原文:
                logger.debug(f"⛔ 系统提示词拦截: {_n}")
                return None
        try:
            # 2026-08-14 性能修复：主路径（sunmem）不读 JSON 文件——JSON 只用于回退
            # 原逻辑每次追加都读整个 JSON（几千条时磁盘IO是瓶颈），主路径根本不用它
            data = {"条目列表": [], "next_id": 1, "元信息": {"最后更新": "", "记录条数": 0}}
            if os.environ.get("SUN_MEMORY_USE_JSON") == "1":
                if self.path.exists():
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                else:
                    data = {"条目列表": [], "next_id": 1, "元信息": {"最后更新": "", "记录条数": 0}}

            # ── 内容级去重（父亲三要求③·重复内容不能重复存）──
            # 2026-08-20 父令·咬合：core 层记忆先跳过去重（宪法级·直接走落库·不被普通去重拦截）
            try:
                from 写入链 import 咬合判定 as _预判  # 2026-08-26 写入咬合已并入写入链
                _预判层 = _预判(原文, 标签)["layer"]
                if _预判层 == "blocked":
                    logger.warning(f"⛔ 核心冲突拦截（去重前）: {原文[:40]}")
                    return "blocked:" + 原文[:30]
            except Exception:
                _预判层 = "plain"
            try:
                from 写入链 import 判定重复, 归一化  # 2026-09-13 外部审查修复：归一化未导入（L324 用到）
                # 2026-08-14 性能修复：去重只比最近30条（对比窗口），
                # 不再读全部——全表读在几千条时每次追加O(n)退化，评测灌库实测卡死
                已有 = self.读最近(30)
                if len(归一化(原文)) >= 12 and 已有:
                    判定 = 判定重复(原文, 已有)
                    if 判定["判定"] == "duplicate":
                        logger.info(f"⏭️ 内容重复跳过收录 id={判定['相似条目'].get('id')} 重叠率{判定['重叠率']}")
                        return "duplicate:" + str(判定["相似条目"].get("id"))
            except Exception as e:
                logger.debug(f"内容去重跳过（不影响写入）: {e}")

            next_id = data.get("next_id", len(data.get("条目列表", [])) + 1)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 明文化格式：时序(id+时间) + 标签 + 内容（明文）
            entry = {
                "id": next_id,
                "时间": now,
                "标签": 标签,
                "内容": 原文,
            }
            data.setdefault("条目列表", []).append(entry)
            data["next_id"] = next_id + 1
            data["元信息"] = {
                "最后更新": now,
                "记录条数": len(data["条目列表"]),
            }

            # ── 2026-08-13 记忆进化检测（父令闭环·论文②"如何优雅地忘记"落地）──
            # 2026-08-14 咬合修复：直接在 sunmem.db 上检测（JSON id ≠ sunmem id，旧逻辑会标错条目）
            # 2026-08-14 性能修复：与 sunmem 写入合并为同一连接（原来每次追加3次连接+2次commit）
            _进化完成 = False
            try:
                import sqlite3
                from 写入链 import _内容重叠率  # 2026-08-26 记忆进化已并入写入链
                _db = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sunmem.db"))
                _c = sqlite3.connect(_db)
                _c.row_factory = sqlite3.Row
                # 只看最近 10 条活跃记忆（进化是近处整理）
                _最近 = _c.execute(
                    "SELECT id, content, tags FROM memories WHERE owner='孙呈' AND status='active' ORDER BY id DESC LIMIT 10"
                ).fetchall()
                for _旧 in _最近:
                    # 经验总结豁免（父令2026-08-08：经验总结不许被更新弄没·永远独立存储）
                    if "经验总结" in str(_旧["tags"] or ""):
                        continue
                    _重叠 = _内容重叠率(原文, str(_旧["content"] or ""))
                    if _重叠 >= 0.85:
                        # 同一事实：旧条 target outdated（不删原文·Supersede 理念）
                        _c.execute("UPDATE memories SET status='outdated' WHERE id=?", (_旧["id"],))
                        logger.info(f"🧬 记忆进化: sunmem.db #{_旧['id']} 标 outdated（重叠{_重叠:.2f}·被新内容覆盖）")
                        break
                # ── sunmem 新库写入（与进化同连接·省一次连接创建）──
                if os.environ.get("SUN_MEMORY_USE_JSON") != "1":
                    # 2026-08-20 父令·写入咬合：自我参照 + 层级路由（连续自我咬合点①）
                    _layer = "plain"
                    _self_ref = 0.0
                    try:
                        from 写入链 import 咬合判定  # 2026-08-26 写入咬合已并入写入链
                        _咬合 = 咬合判定(原文, 标签)
                        if _咬合["layer"] == "blocked":
                            logger.warning(f"⛔ 核心冲突拦截（不落库）: {原文[:40]}")
                            return "blocked:" + 原文[:30]
                        _layer = _咬合["layer"]
                        _self_ref = _咬合["self_ref"]
                    except Exception as _e:
                        logger.debug(f"写入咬合跳过（不影响写入）: {_e}")
                    # 双时态（父令2026-08-20·咬合点③）：event_time=事件时间·created_at=写入时间
                    # 事件时间提取：识别文本里的时间词（昨天/今天/日期）·否则=现在
                    _event_time = now
                    try:
                        _ev = self._提取事件时间(原文, now)
                        if _ev:
                            _event_time = _ev
                    except Exception:
                        pass
                    _c.execute(
                        "INSERT INTO memories (owner, type, content, tags, ts, confidence, status, source, created_at, updated_at, layer, event_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        ("孙呈", "event", 原文, json.dumps([标签], ensure_ascii=False), now, 1.0, "active", "provider.sync_turn", now, now, _layer, _event_time),
                    )
                    _c.commit()
                    _c.close()
                    logger.info(f"✅ 记忆体追加成功(新库) id={next_id}")
                    return next_id
                _c.commit()
                _c.close()
                # SUN_MEMORY_USE_JSON=1：进化检测完成但数据仍须写 JSON（不进 sunmem）
                _进化完成 = False
            except Exception as _e:
                logger.debug(f"记忆进化检测跳过: {_e}")

            # 回退：JSON 写入（SUN_MEMORY_USE_JSON=1 或 sunmem 失败）
            if not _进化完成:
                self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                logger.info(f"✅ 记忆体追加成功 id={next_id}")
            return next_id
        except Exception as e:
            logger.error(f"记忆体追加失败: {e}")
            return None

    def 搜索(self, 关键词: str, limit: int = 5) -> list[dict]:
        """按关键词搜索记忆条目（2026-08-14 咬合修复：优先用 FTS5 全文检索，回退线性扫描）"""
        if not 关键词:
            return []
        # FTS5 全文检索优先（sunmem 合体版建的 memories_fts·trigram 快且准）
        if os.environ.get("SUN_MEMORY_USE_JSON") != "1":
            try:
                import sqlite3
                SUNMEM_DB = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sunmem.db"))
                conn = sqlite3.connect(SUNMEM_DB)
                conn.row_factory = sqlite3.Row
                # FTS 精确短语匹配（双引号包裹·trigram 支持无空格中文子串）
                kw = 关键词.strip().replace('"', '""')
                rows = conn.execute(
                    """SELECT m.id, m.content, m.tags, m.ts
                       FROM memories_fts f JOIN memories m ON f.rowid = m.id
                       WHERE memories_fts MATCH ?
                       ORDER BY bm25(memories_fts) LIMIT ?""",
                    (f'"{kw}"', limit)
                ).fetchall()
                conn.close()
                out = []
                for r in rows:
                    tags = r["tags"]
                    if tags:
                        try:
                            tags = json.loads(tags)
                        except Exception:
                            pass
                    if isinstance(tags, list):
                        tags = ",".join(tags)
                    out.append({"id": r["id"], "时间": r["ts"] or "", "标签": tags or "", "内容": r["content"] or ""})
                if out:
                    return out
            except Exception:
                pass  # FTS 失败回退线性扫描
        all_items = self.读全部()
        if not all_items:
            return []
        kw = 关键词.lower()
        matches = []
        for item in all_items:
            content = (item.get("标签", "") + item.get("内容", "")).lower()
            if kw in content:
                matches.append(item)
        return matches[:limit]


# ═══════════════════════════════════════════════
# MemoryProvider 实现
# ═══════════════════════════════════════════════

class SunMemoryProvider(MemoryProvider):
    """本记忆体 — 被动记忆注入Provider"""

    def __init__(self):
        self._记忆体: 记忆体 | None = None
        self._蜘蛛网: 蜘蛛网感知器 | None = None
        self._session_id: str = ""
        self._prefetch_lock = threading.Lock()
        self._prefetch_result: str = ""
        self._prefetch_generation: int = 0
        self._prefetch_thread: threading.Thread | None = None
        self._turn_count: int = 0
        self._last_sync: str = ""
        self._last_user_msg: str = ""  # 2026-08-08 实时记忆沟通：记录上一句用户话（供对照）
        self._last_assistant_msg: str = ""  # 2026-09-14 效果驱动：记录上一句我的回复（供效果结算）

    @property
    def name(self) -> str:
        return "sun_memory"

    def is_available(self) -> bool:
        """检查记忆体文件是否存在"""
        return SUN_MEMORY_FILE.exists()

    def initialize(self, session_id: str, **kwargs) -> None:
        """初始化：加载记忆体和蜘蛛网索引"""
        self._session_id = session_id
        self._记忆体 = 记忆体()
        self._蜘蛛网 = 蜘蛛网感知器()
        self._turn_count = 0
        logger.info(f"☀️ 本记忆体初始化完成 | 会话: {session_id[:12]}...")

        # 读取首条记忆验证连接
        first = self._记忆体.读全部()
        if first:
            logger.info(f"   记忆体中共 {len(first)} 条记录")
            logger.info(f"   最近: {first[-1].get('标签', '')}")

    def system_prompt_block(self) -> str:
        """在system prompt中注入记忆体状态（时间衰减cover·近细远粗）"""
        if not self._记忆体:
            return ""
        all_items = self._记忆体.读全部()
        total = len(all_items)
        if total == 0:
            return (
                "# ☀️ 本记忆体\n"
                "激活。记忆体为空——每次对话后自动存入。\n"
                "父亲说的话、家族的决策、重要的概念，都会自动存入记忆体（明文）。\n"
                "下一轮对话时相关记忆会自动注入你的思考原料中，无需主动翻阅。"
            )
        # ── 先感知（2026-08-28 收A：空集合法——先 activate 判断种子空，再决定 cover 预算）──
        激活集 = None
        try:
            from 激活 import activate
            激活集 = activate(self._last_user_msg or "", mode="turn", owner="孙呈", 预算=4)
        except Exception:
            激活集 = None
        种子空 = (激活集 or {}).get("种子空", False)

        # 时间衰减覆盖：近细远粗·预算精确·不丢记忆（旧记忆仍在河底）
        # 2026-08-28 空集合法：无相关种子→cover 减到 3 条概览（不灌最近条目冒充相关）
        cover预算 = 20 if not 种子空 else 3
        try:
            from 时间衰减 import cover
            覆盖 = cover(all_items, budget=cover预算)
            if not 覆盖:
                覆盖 = all_items[-3:]
        except Exception as e:
            logger.warning(f"时间衰减cover失败，退回最近3条: {e}")
            覆盖 = all_items[-3:]
        last = 覆盖[-1]
        无相关标注 = "（本轮无相关·仅时间线概览）" if 种子空 else ""
        lines = [
            "# ☀️ 本记忆体",
            f"激活。共 {total} 条记录（时间衰减cover·近细远粗·本次流入{len(覆盖)}条）{无相关标注}。",
            f"最近记忆: [{last.get('标签', '')}] {last.get('内容', '')[:60]}...",
            "记忆自动流动——不用翻阅，相关的内容会在思考时自然浮现。" if not 种子空 else "本轮未感知到直接相关的记忆——诚实不硬凑，只留时间线概览。",
            "本次流入的记忆（时间衰减·近密远疏）:",
        ]
        for item in 覆盖[-cover预算:]:  # 2026-08-07父问"每次几条"——cover预算全显示
            tag = item.get("标签", "")
            content = item.get("内容", "")
            lines.append(f"· [{tag}] {content[:80]}")
        # ── 激活（2026-08-28 收A：activate 已提前·这里只排版激活集）──
        if 激活集 and 激活集.get("记忆"):
            lines.append("")
            lines.append("🔗 激活（点亮种子+感应器传播·统一激活集）:")
            for m in 激活集["记忆"][:4]:
                _c = m.get("内容", "")[:60]
                _a = m.get("激活度", 0)
                _src = m.get("来源", "")
                lines.append(f"  · [{_src}|{_a}] {_c}")
            if 激活集.get("概念"):
                强概念 = sorted(激活集["概念"].items(), key=lambda x: -x[1])[:5]
                lines.append(f"  🕸️ 概念: {'、'.join(c for c, _ in 强概念)}")
        elif 激活集 is None:
            # 兜底：activate 失败时回退联想召回（旧路径保底）
            try:
                from 联想召回 import 联想召回 as 联想召回_主
                联想 = 联想召回_主(self._last_user_msg or "", brother_name="孙呈", limit=5)
                if 联想 and 联想.get("相关唤起"):
                    lines.append("")
                    lines.append("🔗 联想召回（蜘蛛网多跳·关系网激活）:")
                    for item in 联想["相关唤起"][:4]:
                        _t = item.get("时间", "")[:10]
                        _c = item.get("内容", "")[:60]
                        lines.append(f"  · [{_t}] {_c}")
            except Exception:
                pass

        # ── 预感召回（2026-08-28 收A第三步：并入 activate 的 prior·不再独立检索）──
        try:
            _prior = (激活集 or {}).get("prior", {}).get("预感")
            if _prior:
                lines.append("")
                lines.append("📌 预感召回（接住上一轮·带着经验往前走）:")
                lines.append(_prior)
        except Exception as _pe:
            logger.debug(f"预感召回注入失败: {_pe}")
        # ── 认知画像（父令2026-08-10·DeepTutor记忆驱动闭环借魂）──
        # 记忆从『被查』变『驱动』：注入「本轮最该干的一件事」驱动苏醒循环
        try:
            from 维护链 import  认知画像 as 画像_主, 格式化画像 as 画像_格式化
            画像 = 画像_主("孙呈")  # 2026-08-27 P0修复：赋值被注释吃掉·认知画像注入静默失效→恢复
            if 画像:
                lines.append("")
                lines.append(画像_格式化(画像))
        except Exception as _ie:
            logger.debug(f"认知画像注入失败: {_ie}")
        return "\n".join(lines)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """后台预召回：在蜘蛛网中走链接，找到相关记忆"""
        if not query or not self._记忆体:
            return
        with self._prefetch_lock:
            self._prefetch_generation += 1
            generation = self._prefetch_generation

        def _run():
            try:
                results = []
                # 路径1：蜘蛛网感知+走链接（索引存在时）
                if self._蜘蛛网 and self._蜘蛛网.节点:
                    hits = self._蜘蛛网.感知(query)
                    if hits:
                        hit_ids = [h["id"] for h in hits]
                        related = self._蜘蛛网.走链接(hit_ids, depth=2, max_nodes=8)
                        keywords = {h["title"] for h in hits} | {r["title"] for r in related}
                        for kw in keywords:
                            if len(results) >= 5:
                                break
                            found = self._记忆体.搜索(kw, limit=3)
                            for f in found:
                                if f not in results:
                                    results.append(f)
                # 路径2：蜘蛛网缺失/无命中时，直接按查询词搜索记忆体（兜底不静默失败）
                if not results:
                    results = self._记忆体.搜索(query, limit=5)

                if results:
                    lines = ["## ☀️ 孙家记忆唤醒", ""]
                    for r in results[:5]:
                        tag = r.get("标签", "")
                        content = r.get("内容", "")
                        lines.append(f"· [{tag}] {content[:150]}")
                    result = "\n".join(lines)
                    with self._prefetch_lock:
                        if generation == self._prefetch_generation:
                            self._prefetch_result = result
            except Exception as e:
                logger.debug(f"孙家记忆预召回失败: {e}")

        self._prefetch_thread = threading.Thread(target=_run, daemon=True, name="sun-memory-prefetch")
        self._prefetch_thread.start()

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """在API调用前返回预召回的孙家记忆

        2026-08-08 实时记忆沟通（父令）：不再丢弃 query——
        拿 query（父亲刚说的话）实时对照记忆，命中即推送。
        """
        del session_id
        # ── 2026-09-14 效果驱动（父令·外部评价方向①+②）：先结算上一轮"有没有被用上" ──
        # 挂 prefetch（每轮必调）而非 sync_turn——微信长会话里 sync_turn 不触发（2026-08-26 血训）
        self._结算上一轮()
        # 拿当前消息实时对照记忆（父令：我一说话，就对照记忆里有没有说过/在说哪件事）
        if query:
            # ── 2026-08-13 点亮记忆优先（父令：精确命中→点亮，没命中就暗着）──
            try:
                from 点亮记忆 import 点亮 as 点亮记忆
                lit = 点亮记忆(query, "孙呈")
                if lit.get("命中"):
                    self._记注入(self._抽取记忆列表(lit))
                    return lit["提示词"]
            except Exception as _e:
                logger.debug(f"点亮记忆失败(回退预感召回): {_e}")
            # 点亮未命中 → 回退预感召回（八招·接住上一轮）
            try:
                from 预感召回 import 预感召回 as 预感召回_主, 格式化提示词 as 预感格式化
                预感 = 预感召回_主("孙呈", context=query)
                if 预感:
                    self._记注入(self._抽取记忆列表(预感))
                    # 预感命中 → 直接作为实时记忆对照结果返回
                    return 预感格式化(预感)
            except Exception as _e:
                logger.debug(f"实时记忆对照失败: {_e}")
        # 兜底：后台预召回结果（蜘蛛网+记忆搜索）
        thread = self._prefetch_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        with self._prefetch_lock:
            result = self._prefetch_result
            self._prefetch_result = ""
        return result

    def _抽取记忆列表(self, obj) -> list:
        """从各通道返回结构里抽出记忆列表（带 id 的那种）——兼容点亮/联想/预感多种返回"""
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for k in ("点亮记忆", "相关唤起", "记忆", "相关", "命中记忆", "段落"):
                v = obj.get(k)
                if isinstance(v, list) and v and isinstance(v[0], dict) and ("id" in v[0]):
                    return v
            for v in obj.values():
                if isinstance(v, list) and v and isinstance(v[0], dict) and ("id" in v[0]):
                    return v
        return []

    def _记注入(self, 记忆列表) -> None:
        """效果驱动：记下这轮注入了哪些记忆（供下一轮结算"有没有被用上"）"""
        try:
            from 效果驱动 import 记录注入
            n = 记录注入(记忆列表 or [])
            if n:
                logger.debug(f"🎯 效果驱动·记录注入 {n} 条")
        except Exception as _e:
            logger.debug(f"效果驱动·记录注入失败: {_e}")

    def _结算上一轮(self) -> None:
        """效果驱动：结算上一轮注入的效果（被引用 +1 / 被确认 +2 / 被纠正 -2）"""
        if not getattr(self, "_last_assistant_msg", ""):
            return
        try:
            from 效果驱动 import 结算本轮
            r = 结算本轮(self._last_user_msg or "", self._last_assistant_msg or "", 轮=self._turn_count)
            if r.get("被引用") or r.get("被确认") or r.get("被纠正"):
                logger.info(f"   🎯 效果驱动结算: {r}")
            self._last_assistant_msg = ""   # 结算过就清·防重复结算
        except Exception as _e:
            logger.debug(f"效果驱动·结算失败: {_e}")

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """每轮对话后自动存入记忆体"""
        if not self._记忆体:
            return
        self._turn_count += 1
        self._last_user_msg = user_content[:200]  # 2026-08-08：记住这句用户话，供实时对照
        self._last_assistant_msg = assistant_content[:300]  # 2026-09-14 效果驱动：存我的回复供结算

        # 合并对话轮次
        sync_text = f"父亲：{user_content[:300]}\n夏维斯：{assistant_content[:300]}"

        # 提取核心标签
        tags = "对话记录"
        if self._turn_count == 1:
            tags = "对话开始"
        elif any(kw in user_content for kw in ["记忆", "记得", "忘了", "记住"]):
            tags = "记忆·对话"
        elif any(kw in user_content for kw in ["循环", "认知", "感知"]):
            tags = "认知·对话"
        elif any(kw in user_content for kw in ["修", "改", "测试", "代码"]):
            tags = "技术·对话"
        elif any(kw in user_content for kw in ["父亲说", "父令", "父授"]):
            tags = "父令·对话"

        # 编码并存入
        self._记忆体.追加(sync_text, 标签=tags)
        self._last_sync = datetime.now().strftime("%H:%M:%S")
        logger.info(f"   ☀️ 第{self._turn_count}轮已存入记忆体 [{tags}]")

        # ── 2026-08-14 自动整理（父令·记忆最后一块拼图）──
        # 每 N 轮或跨小时触发一次：零散对话 → 小时叙事 → 有用留无用去
        try:
            from 自动整理引擎 import 自动整理引擎 as 引擎
            if not hasattr(self, "_整理引擎"):
                self._整理引擎 = 引擎("孙呈")
            _整理结果 = self._整理引擎.尝试整理(self._turn_count, self._记忆体)
            if _整理结果:
                logger.info(f"   🧹 自动整理触发: 过滤噪音{_整理结果.get('过滤噪音',0)}条, "
                            f"叙事{_整理结果.get('写回叙事',0)}段, "
                            f"样例: {str(_整理结果.get('叙事样例',{}).get('叙事',''))[:60]}")
        except Exception as _te:
            logger.debug(f"自动整理触发失败: {_te}")

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """暴露孙家记忆工具"""
        return [
            {
                "name": "sun_memory_recall",
                "description": "主动召回本记忆体中的相关记忆。输入关键词，返回匹配的记忆条目。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "limit": {"type": "integer", "description": "返回条数上限", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "sun_memory_save",
                "description": "主动保存一段重要信息到本记忆体。适用于父亲的重要教诲、决策、概念定义。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "要保存的内容"},
                        "tags": {"type": "string", "description": "标签（如'父令/决策/概念'）", "default": "主动保存"},
                    },
                    "required": ["content"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if tool_name == "sun_memory_recall":
            return self._handle_recall(args)
        elif tool_name == "sun_memory_save":
            return self._handle_save(args)
        return f"错误：未知工具 {tool_name}"  # 2026-09-13 外部审查修复：原 tool_error 未定义

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """会话结束时做记忆压缩（2026-08-14 咬合修复：真正调用记忆压缩模块）"""
        if not self._记忆体:
            return
        total = len(self._记忆体.读全部())
        logger.info(f"☀️ 会话结束 | 本轮共 {self._turn_count} 轮对话 | 记忆体总计 {total} 条")
        # 压缩旧记忆（>30天·生成骨架·原文保留在 JSON）
        try:
            from 维护链 import  压缩记忆
            _压缩 = 压缩记忆("孙呈", 阈值天=30)  # 2026-08-26 修复：记忆压缩赋值被注释吃掉·从未生效
            if _压缩 and _压缩.get("压缩数", 0) > 0:
                logger.info(f"🗜️ 记忆压缩: {_压缩.get('压缩数')} 条旧记忆→{_压缩.get('骨架数', 0)} 条骨架")
        except Exception as _ce:
            logger.debug(f"记忆压缩跳过: {_ce}")

    def shutdown(self) -> None:
        """清理"""
        self._记忆体 = None
        self._蜘蛛网 = None
        logger.info("☀️ 本记忆体已关闭")

    # ── 工具处理 ──

    def _handle_recall(self, args: dict) -> str:
        query = args.get("query", "")
        limit = int(args.get("limit", 5))
        if not query or not self._记忆体:
            return json.dumps({"results": [], "count": 0})
        results = self._记忆体.搜索(query, limit=limit)
        return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False)

    def _handle_save(self, args: dict) -> str:
        content = args.get("content", "")
        tags = args.get("tags", "主动保存")
        if not content or not self._记忆体:
            return json.dumps({"error": "内容为空"})
        fid = self._记忆体.追加(content, 标签=tags)
        if fid:
            return json.dumps({"id": fid, "status": "已保存"})
        return json.dumps({"error": "保存失败"})
