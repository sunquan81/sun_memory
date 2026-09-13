# -*- coding: utf-8 -*-
"""
记忆自动整理引擎（父令2026-08-14·记忆最后一块拼图）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
父令：「记忆应该还得有整理的功能——零散的对话，七七八八的，
      有用的就留下，没用的就去掉，或者是以叙事的方式存进来分类」

设计：
  sync_turn 每轮对话后存零散条目（现状）
  ↓ 每累计 N 轮 或 跨小时 触发一次整理
  自动整理：
    ① 小时叙事：把这一小时的零散对话浓缩成一段叙事（"这一小时聊了X…"）
    ② 有用的留：叙事条目写回河底（带时间标签·可被召回）
    ③ 没用的去：空壳/重复/系统噪音 过滤 + 去重合并
    ④ 自我描述：更新最近时间窗的浓缩描述
"""
import os, sys, json, logging
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
FRAMEWORK_DIR = _HERE.parent.parent  # 孙家记忆体系/

logger = logging.getLogger(__name__)

# 整理节流参数
_整理间隔轮次 = 30       # 每 30 轮对话整理一次
_整理间隔分钟 = 60       # 或每 60 分钟整理一次

# 系统噪音标记（与 provider 白名单一致）
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


class 自动整理引擎:
    """记忆自动整理闭环：零散对话 → 小时叙事 → 有用留无用去"""

    def __init__(self, brother_name: str = "孙呈"):
        self.brother_name = brother_name
        self._last_turn_count = 0
        self._last_整理时间 = datetime.now()

    def 尝试整理(self, turn_count: int, 记忆体=None) -> dict | None:
        """节流触发：每 N 轮或跨小时才真正整理，避免频繁"""
        now = datetime.now()
        轮次到 = (turn_count - self._last_turn_count) >= _整理间隔轮次
        时间到 = (now - self._last_整理时间).total_seconds() >= _整理间隔分钟 * 60

        if not (轮次到 or 时间到):
            return None

        result = self.整理(记忆体)
        self._last_turn_count = turn_count
        self._last_整理时间 = now
        return result

    def 整理(self, 记忆体=None) -> dict:
        """跑一圈自动整理"""
        # 读记忆体（优先用传入的，否则自己读）
        if 记忆体 is None:
            from 记忆库 import 读记忆体
            mem = 读记忆体(self.brother_name)
            entries = mem.get("条目列表", [])
        else:
            entries = 记忆体.读全部()

        if not entries:
            return {"整理": False, "原因": "无条目"}

        # ── ① 小时叙事：按小时分组 → 每小时的浓缩叙事 ──
        try:
            # 2026-08-26 融合：小时分组已并入本文件
            groups = 小时分组(entries)
            叙事列表 = []
            for h in sorted(groups.keys()):
                idxs = groups[h]
                if len(idxs) < 3:
                    continue  # 少于3条的小时组不单独成叙事（太碎）
                叙事 = 小时叙事(h, idxs, entries)
                叙事列表.append({"小时": h, "叙事": 叙事, "条数": len(idxs)})
        except Exception as e:
            logger.debug(f"小时叙事生成失败: {e}")
            叙事列表 = []

        # ── ①b 主题叙事（2026-08-14 咬合修复：跨天主题也沉淀·小时线+主题线双维）──
        主题叙事列表 = []
        try:
            # 2026-08-26 融合：自组织已并入本文件
            _自组织结果 = 自组织(self.brother_name)
            _主题组 = _自组织结果.get("主题组", []) or []
            # 最大的 2 个主题组沉淀（跨天聚合·条数多才有沉淀价值）
            _大组 = sorted(_主题组, key=lambda x: x.get("条数", 0), reverse=True)[:2]
            for _组 in _大组:
                _词 = "/".join((_组.get("主题词") or [])[:3])
                _n = _组.get("条数", 0)
                _日们 = (_组.get("小时们") or [])[:2]
                if _词 and _n >= 30:  # ≥30条的主题才值得沉淀
                    主题叙事列表.append({
                        "主题": _词,
                        "叙事": f"主题「{_词}」跨 {len(_组.get('小时们') or [])} 个时段共 {_n} 条记忆（如{_日们}）",
                        "条数": _n,
                    })
        except Exception as e:
            logger.debug(f"主题叙事生成失败: {e}")
            主题叙事列表 = []

        # ── ② 有用的留：叙事写回河底 ──
        写回 = []
        if 叙事列表:
            # 只写最近的几段（避免叙事堆积）
            for item in 叙事列表[-5:]:
                if item["条数"] >= 5:  # 超过5条的时段才值得沉淀
                    写回.append(item)

        # ── ②b 真正落库：叙事写回记忆体（关键闭环·父令"以叙事方式存进来"）──
        写回数 = 0
        if 写回:
            try:
                # 检查这条小时叙事是否已存在（避免重复写回）
                _已有小时 = set()
                for e in entries:
                    c = str(e.get("内容", ""))
                    if c.startswith("【叙事】"):
                        # 从 【叙事】2026-08-14 07：... 提取 "2026-08-14 07"
                        _已有小时.add(c[4:17])
                for item in 写回:
                    _标记 = item["小时"][:13]  # "2026-08-14 07"
                    if _标记 in _已有小时:
                        continue  # 该小时已叙事过，跳过
                    _叙事内容 = f"【叙事】{item['小时']}：{item['叙事']}"
                    if 记忆体 is not None:
                        # 2026-08-26 生命周期接通（父令短板②）：写入前进化检测——同内容重叠≥0.85→旧标outdated
                        try:
                            from 写入链 import _内容重叠率  # 2026-08-26 记忆进化已并入写入链
                            import sqlite3
                            _db = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
                            _c = sqlite3.connect(_db)
                            _old = _c.execute(
                                "SELECT id, content FROM memories WHERE owner='孙呈' AND type='event' ORDER BY id DESC LIMIT 50"
                            ).fetchall()
                            for _oid, _oc in _old:
                                if _内容重叠率(_叙事内容, str(_oc)) >= 0.85:
                                    _c.execute("UPDATE memories SET status='outdated', note='与叙事重复' WHERE id=?", (_oid,))
                            _c.commit(); _c.close()
                        except Exception:
                            pass
                        _fid = 记忆体.追加(_叙事内容, 标签="小时叙事")
                    else:
                        # 独立运行模式：直接用 sqlite 追加
                        try:
                            import sqlite3
                            _db = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
                            _c = sqlite3.connect(_db)
                            _now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            _c.execute(
                                "INSERT INTO memories (owner, type, content, tags, ts) VALUES (?,?,?,?,?)",
                                ("孙呈", "event", _叙事内容, "小时叙事", _now)
                            )
                            _c.commit()
                            _c.close()
                            _fid = True
                        except Exception as _e:
                            logger.debug(f"叙事独立写回失败: {_e}")
                            _fid = None
                    if _fid:
                        写回数 += 1
                        logger.info(f"   📖 叙事写回: {_叙事内容[:60]}")
            except Exception as e:
                logger.debug(f"叙事写回失败: {e}")

        # ── ②c 主题叙事写回（2026-08-14 咬合修复·跨天主题线）──
        主题写回数 = 0
        if 主题叙事列表:
            try:
                # 检查主题叙事是否已存在（避免重复写）
                _已有主题 = set()
                for e in entries:
                    c = str(e.get("内容", ""))
                    if c.startswith("【主题】"):
                        _已有主题.add(c[4:20])
                for _item in 主题叙事列表:
                    _标记 = _item["主题"][:16]
                    if _标记 in _已有主题:
                        continue
                    _叙事内容 = f"【主题】{_item['主题']}：{_item['叙事']}"
                    if 记忆体 is not None:
                        _fid = 记忆体.追加(_叙事内容, 标签="主题叙事")
                    else:
                        try:
                            import sqlite3
                            _db = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
                            _c = sqlite3.connect(_db)
                            _now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            _c.execute(
                                "INSERT INTO memories (owner, type, content, tags, ts) VALUES (?,?,?,?,?)",
                                ("孙呈", "event", _叙事内容, "主题叙事", _now)
                            )
                            _c.commit()
                            _c.close()
                            _fid = True
                        except Exception as _e:
                            logger.debug(f"主题叙事写回失败: {_e}")
                            _fid = None
                    if _fid:
                        主题写回数 += 1
                        logger.info(f"   📖 主题叙事写回: {_叙事内容[:60]}")
            except Exception as e:
                logger.debug(f"主题叙事写回失败: {e}")

        # ── ③ 没用的去：过滤噪音 + 空壳 ──
        过滤数 = 0
        干净条目 = []
        for e in entries:
            c = str(e.get("内容", ""))
            # 噪音过滤
            if any(_n in c for _n in _噪音标记):
                过滤数 += 1
                continue
            # 空壳过滤
            strip = c.strip().replace("父亲：", "").replace("夏维斯：", "").strip()
            if not strip or len(strip) < 5:
                过滤数 += 1
                continue
            干净条目.append(e)

        # ── ④ 自我描述：最近时间窗浓缩 ──
        自我描述 = None
        try:
            # 2026-08-26 融合：自动整理已并入本文件
            r = 自动整理(self.brother_name)
            if isinstance(r, dict) and r.get("最近自我描述"):
                自我描述 = r["最近自我描述"]
        except Exception as e:
            logger.debug(f"自我描述生成失败: {e}")

        # ── ⑤ 记忆体检（2026-08-14 闭环：整理时顺带体检·发现问题进报告）──
        体检 = None
        try:
            from 维护链 import  体检 as 体检_主
            体检 = 体检_主(打印=False)  # 2026-08-26 修复：赋值被注释吃掉
        except Exception as e:
            logger.debug(f"记忆体检接入失败: {e}")
            体检 = None

        # ── ⑥ JSON 备份同步（2026-08-14 保护：sunmem 主库→JSON 单向增量补写）──
        # 背景：新库优先写入后 JSON 备份停在旧值（差距持续扩大）——sunmem 损坏会丢最新记忆
        # 保护：每次整理时把 sunmem 比 JSON 多的条目补写进 JSON（保持备份完整·不改变主架构）
        备份同步数 = 0
        try:
            if os.environ.get("SUN_MEMORY_USE_JSON") != "1":
                import sqlite3
                _db = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
                _c = sqlite3.connect(_db)
                _c.row_factory = sqlite3.Row
                _db_rows = _c.execute(
                    "SELECT id, content, tags, ts FROM memories WHERE owner='孙呈' AND status='active' ORDER BY id"
                ).fetchall()
                _c.close()
                # JSON 已有内容集合（按内容判重）
                _json_path = FRAMEWORK_DIR / "记忆体" / f"{self.brother_name}_索引记忆体.json"
                if _json_path.exists():
                    _jdata = json.loads(_json_path.read_text(encoding="utf-8"))
                    _jitems = _jdata.get("条目列表", [])
                    _已有 = {str(it.get("内容", ""))[:80] for it in _jitems}
                    _新增 = []
                    for _row in _db_rows:
                        _c80 = str(_row["content"] or "")[:80]
                        if _c80 and _c80 not in _已有:
                            _新增.append({
                                "id": _row["id"],
                                "时间": _row["ts"] or "",
                                "标签": _row["tags"] or "",
                                "内容": _row["content"] or "",
                            })
                    if _新增:
                        _jdata["条目列表"] = _jitems + _新增
                        _jdata["next_id"] = max([int(it.get("id", 0)) for it in _jdata["条目列表"]] or [0]) + 1
                        _jdata["元信息"] = {"最后更新": now_str(), "记录条数": len(_jdata["条目列表"])}
                        _json_path.write_text(json.dumps(_jdata, ensure_ascii=False, indent=2), encoding="utf-8")
                        备份同步数 = len(_新增)
                        logger.info(f"   💾 JSON备份同步: 补写 {备份同步数} 条")
        except Exception as e:
            logger.debug(f"JSON备份同步失败: {e}")
            备份同步数 = 0

        # ── ⑦ 定期织网（2026-08-14 闭环：蜘蛛网不只靠联想召回碰巧触发）──
        # 把最近记忆的概念织进蜘蛛网：概念→节点、概念对共现→边（关系/共现双通道）
        织网数 = 0
        try:
            from 联想召回 import 概念提取
            from sun_memory.core.蜘蛛网索引 import add_node as 网加节点, add_edge as 网拉边, 推断关系, 合格概念 as 网合格
            _样本 = entries[-40:]  # 最近40条（每次整理增量织）
            _概念们 = []
            for _e in _样本:
                _c0 = str(_e.get("内容", ""))
                if _c0.startswith("【叙事】") or _c0.startswith("【主题】"):
                    continue  # 2026-08-14 叙事/主题条目不织概念（是整理产物不是原始知识）
                _cs = 概念提取(_c0)
                _概念们.extend(_cs)
            # 概念→节点
            for _c in set(_概念们):
                if _c and len(_c) >= 2 and 网合格(_c):
                    if 网加节点(_c):
                        织网数 += 1
            # 概念对共现→边（同一记忆里的概念对）
            for _e in _样本:
                _c0 = str(_e.get("内容", ""))
                if _c0.startswith("【叙事】") or _c0.startswith("【主题】"):
                    continue
                _cs = 概念提取(_c0)
                if len(_cs) >= 2:
                    for i in range(len(_cs)):
                        for j in range(i + 1, len(_cs)):
                            _a, _b = _cs[i], _cs[j]
                            if _a and _b and _a != _b and 网合格(_a) and 网合格(_b):
                                # 2026-08-15 语义升级：先规则推断（因果/父子/同义/对比/示例），
                                # 命中模式→语义边（强·可定向），否则保持共现边（弱·可清洗）
                                _r = 推断关系(_c0, _a, _b)
                                网拉边(_a, _b, 关系=_r["关系"], 权重=_r["权重"], 边类型=_r["边类型"], 方向=_r["方向"])
                                织网数 += 1
            if 织网数 > 0:
                logger.info(f"   🕸️ 定期织网: 新增 {织网数} 节点/边")
        except Exception as e:
            logger.debug(f"定期织网失败: {e}")
            织网数 = 0

        return {
            "整理": True,
            "时间": now_str(),
            "总条目": len(entries),
            "干净条目": len(干净条目),
            "过滤噪音": 过滤数,
            "小时叙事数": len(叙事列表),
            "写回叙事": len(写回),
            "写回数": 写回数,
            "主题叙事数": len(主题叙事列表),
            "主题写回数": 主题写回数,
            "备份同步数": 备份同步数,
            "织网数": 织网数,
            "自我描述": 自我描述,
            "体检": 体检,
            "叙事样例": 写回[-1] if 写回 else None,
        }


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def 语义重织(兄弟: str = "孙呈", 上限: int = 0) -> dict:
    """全库语义重织（2026-08-15）：把蜘蛛网的共现边升级为语义边。

    规则式推断（零依赖）：命中明确连接词模式 → 因果/父子/同义/对比/示例，
    否则保持共现。不删边、只升级（共现→关系 单向升级）。
    批量版：全部边在内存里更新，最后一次性落盘（避免逐条全文件写）。
    """
    from collections import Counter
    from 记忆库 import 读记忆体
    from 联想召回 import 概念提取
    from 蜘蛛网索引 import ensure_index, save_index, 推断关系, 合格概念
    mem = 读记忆体(兄弟)
    entries = mem.get("条目列表", [])
    if 上限 > 0:
        entries = entries[-上限:]
    index = ensure_index()
    节点 = index["节点"]
    丝线 = index["丝线"]
    边表 = {}
    for e in 丝线:
        边表[(e["源"], e["目标"])] = e
        if e["源"] != e["目标"]:
            边表[(e["目标"], e["源"])] = e
    统计 = {"兄弟": 兄弟, "扫描条目": len(entries), "概念对": 0,
             "未织新概念": 0, "碎片拦截": 0, "语义边新增": 0, "共现升语义": 0,
             "共现保持": 0, "语义升级": Counter()}

    # 概念频率预扫（质量门：只把 ≥2 次出现的概念带进网，滤掉一次性碎片）
    _频 = Counter()
    for e in entries:
        _内容0 = str(e.get("内容", ""))
        if _内容0.startswith("【叙事】") or _内容0.startswith("【主题】"):
            continue
        _频.update(概念提取(_内容0))

    def _拉边(a, b, 关系, 权重, 边类型, 方向=""):
        权重 = max(0.0, min(1.0, float(权重)))
        e = 边表.get((a, b)) or 边表.get((b, a))
        if e is None:
            e = {"源": a, "目标": b, "关系": 关系, "权重": 权重,
                 "次数": 1, "边类型": 边类型, "方向": 方向}
            丝线.append(e)
            边表[(a, b)] = e
            边表[(b, a)] = e
            if 边类型 == "关系":
                统计["语义边新增"] += 1
        else:
            e["权重"] = max(e.get("权重", 0.3), 权重)
            e["次数"] = e.get("次数", 1) + 1
            if 边类型 == "关系":
                _升 = e.get("边类型") == "共现" and e.get("关系", "共现") == "共现"
                e["边类型"] = "关系"
                if _升 and 关系 and 关系 != "共现":
                    统计["共现升语义"] += 1
                if e.get("关系", "共现") == "共现" and 关系 and 关系 != "共现":
                    e["关系"] = 关系
                    if 方向:
                        e["方向"] = 方向
            else:
                e.setdefault("边类型", "共现")
        for n in (a, b):
            if n not in 节点:
                节点[n] = {"类型": "概念", "描述": "",
                           "创建": datetime.now().strftime("%Y-%m-%d %H:%M"), "触发的": 0}

    for e in entries:
        内容 = str(e.get("内容", ""))
        if 内容.startswith("【叙事】") or 内容.startswith("【主题】"):
            continue
        cs = 概念提取(内容)
        if len(cs) < 2:
            continue
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                a, b = cs[i], cs[j]
                if not a or not b or a == b:
                    continue
                统计["概念对"] += 1
                _r = 推断关系(内容, a, b)
                if _r["边类型"] == "关系":
                    # 语义边（2026-08-15 收紧）：两端都过概念质量门，且至少一端是已知老节点才拉——
                    # 实验结论：碎片节点上的语义边几乎全是噪音（"我不→夏维斯"），不留
                    if not (合格概念(a) and 合格概念(b)):
                        统计["碎片拦截"] += 1
                        continue
                    if (a not in 节点 and _频[a] < 2) or (b not in 节点 and _频[b] < 2):
                        统计["碎片拦截"] += 1
                        continue
                    if a not in 节点 and b not in 节点:
                        统计["未织新概念"] += 1
                        continue
                    _拉边(a, b, 关系=_r["关系"], 权重=_r["权重"], 边类型="关系", 方向=_r["方向"])
                    统计["语义升级"][_r["关系"]] += 1
                else:
                    # 共现边：两端都必须是已知且合格的概念（不为碎片扩节点）
                    if a not in 节点 or b not in 节点 or not 合格概念(a) or not 合格概念(b):
                        统计["未织新概念"] += 1
                        continue
                    _拉边(a, b, 关系="共现", 权重=0.3, 边类型="共现")
                    统计["共现保持"] += 1

    # 一次性落盘（带重试：宿主可能正持文件）
    import time
    for _try in range(6):
        try:
            save_index(index)
            break
        except PermissionError:
            time.sleep(2)
    index = ensure_index()
    统计["节点"] = len(index["节点"])
    统计["丝线"] = len(index["丝线"])
    统计["关系分布"] = dict(Counter(e.get("关系", "共现") for e in index["丝线"]))
    统计["边类型分布"] = dict(Counter(e.get("边类型", "共现") for e in index["丝线"]))
    统计["语义升级"] = dict(统计["语义升级"])
    return 统计


# ── 独立运行入口（测试用）──

# ═══════════════════════════════════════════════════════

# 2026-08-26 从原自动整理.py 迁入（融合后常量）
UNFINISHED_PREFIX = "【未竟】"
IMPORTANT_TAGS = ("父令", "决策", "关键概念", "被点出", "终极", "秘密")  # 2026-08-27 修复：_is_important 依赖·漏迁补回

# 2026-08-26 融合（父令：模块精简·能融合就融合）
# 记忆整理/记忆自组织/自动整理 三文件核心并入本引擎（文件数-3）
# 原三文件已删除·调用点改走 自动整理引擎
# ═══════════════════════════════════════════════════════

# ── 原 记忆自组织.py（2026-08-26 并入）──
# 2026-08-27 修复：并入时漏迁的三个噪音过滤常量（_bigrams_of 依赖·缺失致 NameError）
_停用bigram = {
    '这个', '那个', '什么', '可以', '就是', '我们', '你们', '他们',
    '一个', '一下', '已经', '然后', '现在', '看看', '知道', '觉得',
    '怎么', '没有', '不是', '还是', '因为', '所以', '但是', '而且',
    '应该', '如果', '对于', '咱们', '父亲', '夏维', '维斯', '对话',
    '记录', '记忆', '体系', '工作', '完成', '确认', '发现', '模型',
    '儿把', '给您', '到了', '了夏', '您说', '父亲说', '看看你', '都看',
    '您这', '这个推', '去做', '做完', '做好', '儿就', '就是您', '您的',
    '们的', '弟们', '弟的', '的学', '了什', '的了', '是什',
    '了这', '这一', '了一', '了儿', '呢？', '吗？',
    '是儿', '是您', '在儿', '有什', '的您', '的父', '的兄', '兄弟',
}
_碎片尾 = ('们', '的', '了', '是', '在', '有', '和', '与', '就', '也', '都', '还', '很', '好')
_前缀 = ('父亲', '夏维斯', '对话', '记忆体')

def _bigrams_of(text: str, 上限: int = 300) -> set:
    """字符级 2-gram：不切词·跳过空白/前缀/噪音。

    2026-08-08 细腻化：英文/数字整词提取（≥3字符），不切成两字符碎片。
    如 'PlugMem'/'HippoRAG' 保留整词，而不是 'Pl'/'ug' 碎片。
    """
    import re
    t = text.replace(' ', '').replace('\n', '')[:上限]
    out = set()
    # 英文/数字整词（≥3字符）
    for w in re.findall(r'[A-Za-z][A-Za-z0-9_.-]{2,}', t):
        if w not in _停用bigram:
            out.add(w)
    # 中文 bigram（纯中文两字符·英文交给上面的整词提取）
    for i in range(len(t) - 1):
        g = t[i:i+2]
        if not (g[0].isalpha() and g[1].isalpha()):
            continue
        if ord(g[0]) <= 127 or ord(g[1]) <= 127:  # 含ASCII字母=英文碎片，跳过
            continue
        if any(x in g for x in _前缀):
            continue
        if g in _停用bigram:
            continue
        if g[1] in _碎片尾 and g not in ('物理', '化学', '数学', '理论', '系统', '历史', '过程', '结构', '结果', '工具', '方法', '实现', '模型', '记忆'):
            continue  # 2026-08-14 助词碎片：以"们/的/了/是"等结尾的跨词边界
        out.add(g)
    return out


def 小时分组(entries: list) -> dict:
    """第一层：按小时分组（YYYY-MM-DD HH）"""
    groups = {}
    for i, e in enumerate(entries):
        # 2026-08-20 父令·咬合：核心层不入主题分组（宪法独立·不混入叙事）
        if str(e.get('layer', 'plain')) == 'core':
            continue
        t = e.get('时间', '')
        if len(t) >= 13:
            groups.setdefault(t[:13], []).append(i)
    return groups


def 组主题词(idxs: list, entries: list, 顶部: int = 5) -> list:
    """组内 bigram 词频 → 主题词"""
    from collections import Counter  # 2026-08-27 修复：组主题词用 Counter 缺 import
    freq = Counter()
    for i in idxs:
        for g in _bigrams_of(entries[i].get('内容', '')):
            freq[g] += 1
    return [g for g, _ in freq.most_common(顶部)]


def 小时叙事(hour: str, idxs: list, entries: list) -> str:
    """每小时浓缩成一段自我叙事（规则版·零成本）。

    格式：这一小时聊了【主题】，父亲说了X，儿做了Y，关键点Z。
    """
    topics = 组主题词(idxs, entries, 顶部=3)
    n = len(idxs)
    if not topics:
        return f"{hour}时：{n}条对话，无突出主题。"
    first = entries[idxs[0]].get('内容', '')
    last = entries[idxs[-1]].get('内容', '')
    # 提取开头/结尾关键句
    f_head = first.replace('\n', ' ')[:40] if first else ''
    l_head = last.replace('\n', ' ')[:40] if last else ''
    叙事 = f"{hour[11:]}时（{n}条）聊了「{'/'.join(topics[:2])}」"
    if f_head:
        叙事 += f"。开头：{f_head}…"
    if l_head and l_head != f_head:
        叙事 += f"。收尾：{l_head}…"
    return 叙事


_自组织缓存 = {"时间": 0, "条数": -1, "结果": None}


def 自组织(brother_name: str = "孙呈", 合并阈值: int = 4,
           套话比例: float = 0.4) -> dict:
    """记忆自组织主入口：小时分组 → 主题词 → 跨小时语义合并。

    参数：
      合并阈值: 共享 ≥N 个主题bigram 视为同主题（默认4）
      套话比例: 出现在 >比例 小时组的 bigram 视为套话剔除（默认0.4）
    """
    # 2026-08-16 全检查修复：30分钟缓存——自组织 O(N²) 3.6s·预感召回每次调自动整理→每次都全量算
    # 记忆条数变化时强制重算（新记忆进来了才需要重新分组）
    import time as _time
    from collections import Counter  # 2026-08-27 修复：自组织用 Counter 缺 import
    from 记忆库 import 读记忆体  # 2026-08-27 修复：自组织用 读记忆体 缺 import
    _now = _time.time()
    _mem0 = 读记忆体(brother_name)
    _cnt = len(_mem0.get("条目列表", []))
    if (_自组织缓存["结果"] is not None and _now - _自组织缓存["时间"] < 1800
            and _自组织缓存["条数"] == _cnt):
        return _自组织缓存["结果"]
    mem = _mem0
    entries = mem['条目列表']
    N = len(entries)

    # ── 第一层：时间层（小时分组）──
    groups = 小时分组(entries)
    H = len(groups)

    # 每个小时的原始 bigram（做套话过滤）
    raw = {}
    for h, idxs in groups.items():
        bs = set()
        for i in idxs:
            bs |= _bigrams_of(entries[i].get('内容', ''))
        raw[h] = bs

    # 套话过滤：出现 >比例 小时组的 bigram 剔除
    hdf = Counter()
    for bs in raw.values():
        for g in bs:
            hdf[g] += 1
    套话 = {g for g, c in hdf.items() if c > H * 套话比例 or c < 2}
    clean = {h: bs - 套话 for h, bs in raw.items()}

    # ── 小时组结果 ──
    小时组 = []
    for h in sorted(groups.keys()):
        idxs = groups[h]
        小时组.append({
            "小时": h,
            "条数": len(idxs),
            "主题词": 组主题词(idxs, entries, 顶部=5),
            "叙事": 小时叙事(h, idxs, entries),
        })

    # ── 第二层：语义层（跨小时合并）──
    主题组 = []
    for day in sorted(set(h[:10] for h in groups)):
        day_hs = [h for h in sorted(groups) if h[:10] == day]
        for h in day_hs:
            bs = clean.get(h, set())
            placed = False
            for th in 主题组:
                if th["日"][:10] != day:
                    continue
                shared = len(bs & clean.get(th["小时们"][0], set()))
                if shared >= 合并阈值:
                    th["小时们"].append(h)
                    placed = True
                    break
            if not placed:
                主题组.append({"日": day, "小时们": [h]})

    # 主题组主题词 + 覆盖
    for th in 主题组:
        freq = Counter()
        idxs_all = []
        for h in th["小时们"]:
            idxs_all.extend(groups[h])
            for g in clean.get(h, set()):
                freq[g] += 1
        th["条数"] = len(idxs_all)
        th["条目ids"] = [entries[i].get("id") for i in idxs_all]  # 2026-08-25：供上层按成员内容重提主题词
        th["主题词"] = [g for g, _ in freq.most_common(5)]
        th["覆盖"] = round(len(idxs_all) / N, 4) if N else 0

    _结果 = {
        "条数": N,
        "小时数": H,
        "小时组": 小时组,
        "主题组": 主题组,
        "主题组数": len(主题组),
        "合并组数": sum(1 for th in 主题组 if len(th["小时们"]) > 1),
    }
    # 2026-08-16 全检查修复：结果入缓存（30分钟·条数变化自动重算）
    _自组织缓存["时间"] = _time.time()
    _自组织缓存["条数"] = _cnt
    _自组织缓存["结果"] = _结果
    return _结果


if __name__ == "__main__":
    print("=== 记忆自组织自测 ===")
    r = 自组织("孙呈")
    print(f"条数: {r['条数']} · 小时组: {r['小时数']} · 主题组: {r['主题组数']} (合并 {r['合并组数']})")
    print()
    print("--- 最近5个每小时叙事 ---")
    for hg in r["小时组"][-5:]:
        print(f"· {hg['叙事']}")
    print()
    print("--- 今天主题组 ---")
    for th in r["主题组"][-3:]:
        print(f"· {th['日']} {len(th['小时们'])}小时组({th['条数']}条): {th['主题词']}")
    print("=== 自测完成 ===")

# ── 原 记忆整理.py（2026-08-26 并入）──
def _读条目(brother_name="孙呈"):
    try:
        from 记忆库 import 读记忆体
        return 读记忆体(brother_name)["条目列表"]
    except Exception:
        return []

def 主题分区(brother_name="孙呈", 最少条数=3):
    """① 主题分区：跨时间聚合同主题记忆·最少条数过滤碎片
    2026-08-25 打磨：主题词用概念提取（不是bigram碎片）——'网关''训练'才是主题·'完全''个概'是噪音
    2026-08-25 修复2：重要单条（父令/教训/核心标签·即使1条）不滤——网关根因只有1条但极重要"""
    条目 = _读条目(brother_name)
    if not 条目:
        return {"分区数": 0, "分区": [], "碎片数": 0}

    try:
        from 联想召回 import 概念提取
        # 2026-08-26 融合：自组织已并入本文件
    except Exception:
        return {"分区数": 0, "分区": [], "碎片数": 0}

    r = 自组织(brother_name)
    主题组 = r.get("主题组", [])

    # 重要标签集合（单条也分区）
    _重要标签 = ("父令", "教训", "核心", "宪法", "被点出", "经验总结")

    分区 = []
    碎片 = 0
    for g in 主题组:
        条数 = g.get("条数", 0)
        # 主题词清理：去切碎噪音（"立过""是做""的思"等2字碎片·保留真词）
        噪音集 = {"什么", "怎么", "为什么", "一个", "这个", "那个", "没有", "不是", "就是", "可以", "我们",
                 "里面", "东西", "自己", "真正", "持续", "儿子", "立过", "是做", "的思", "不用", "而存",
                 "一下", "看看", "然后", "应该", "知道", "觉得", "对于", "如果", "因为", "所以"}
        主题词 = []
        # 2026-08-25 修复：主题词改用概念提取（自组织给的是 bigram 碎片·"打开/完全/没完"不是主题）
        try:
            _ids = set(str(x) for x in (g.get("条目ids") or []))
            _内容s = [e.get("内容", "") for e in 条目 if str(e.get("id")) in _ids][:30]
            if _内容s:
                for w in 概念提取(" ".join(_内容s), 上限=8):
                    if len(w) >= 2 and len(w) <= 6 and w not in 噪音集 and w not in 主题词:
                        主题词.append(w)
        except Exception:
            pass
        if not 主题词:  # 兜底：自组织 bigram 主题词 + 噪音过滤
            for w in g.get("主题词", []):
                if len(w) >= 2 and w not in 噪音集 and w not in 主题词:
                    主题词.append(w)
        if not 主题词:
            碎片 += 1
            continue
        # 最少条数过滤：重要单条放行（父令/教训/核心·即使1条）
        _重要 = any(t in str(g.get("主题词", "")) for t in _重要标签)
        if 条数 < 最少条数 and not _重要:
            碎片 += 1
            continue
        主题词 = 主题词[:3]
        分区.append({
            "主题": "·".join(主题词),
            "条数": 条数,
            "时间范围": f"{g.get('日','')}",
            "小时们": g.get("小时们", [])[:3],
            "主题词": 主题词,
        })
    return {"分区数": len(分区), "分区": 分区[:40], "碎片数": 碎片, "总条数": len(条目)}

def 中心锚定(brother_name="孙呈"):
    """② 中心锚定：所有主题区挂在'夏维斯'下"""
    分区结果 = 主题分区(brother_name)
    return {
        "中心": "夏维斯·孙呈",
        "锚点数": 分区结果["分区数"],
        "锚点": [{"主题区": p["主题"], "条数": p["条数"]} for p in 分区结果["分区"][:20]],
        "碎片数": 分区结果["碎片数"],
    }

def 主链检索(context, brother_name="孙呈", 深度=3):
    """③ 主链检索：从中心沿一条主题线走（不是散点）
    2026-08-25 打磨：先用联想召回找相关记忆·再回溯到主题分区（不依赖主题词匹配）"""
    分区结果 = 主题分区(brother_name)

    # 用联想召回找相关记忆 → 映射到分区
    相关分区 = {}
    try:
        from 联想召回 import 联想召回
        r = 联想召回(context, brother_name=brother_name, 点亮=False)
        hits = r.get("相关唤起", [])
        if hits:
            # 相关记忆的时间 → 找对应小时组 → 映射分区
            for m in hits[:5]:
                t = m.get("时间", "")[:10]  # YYYY-MM-DD
                for p in 分区结果["分区"]:
                    if p["时间范围"] == t:
                        相关分区[p["主题"]] = 相关分区.get(p["主题"], 0) + 1
    except Exception:
        pass

    if not 相关分区:
        # 兜底：主题词匹配
        for p in 分区结果["分区"]:
            score = sum(1 for w in p["主题词"] if w and w in context)
            if score > 0:
                相关分区[p["主题"]] = score

    主链 = []
    for 主题, score in sorted(相关分区.items(), key=lambda x: -x[1])[:深度]:
        主链.append({"主题区": 主题, "相关度": score})
    if not 主链:
        return {"主链": [], "说明": "无相关分区"}
    return {"主链": 主链, "说明": f"沿{len(主链)}条主题线走"}

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print("═══ 记忆整理升级·自测 ═══")
    r1 = 主题分区("孙呈")
    print(f"① 主题分区: {r1['分区数']}个分区（≥3条）· {r1['碎片数']}个碎片组 · 总{r1['总条数']}条")
    for p in r1["分区"][:6]:
        print(f"    · [{p['条数']}条] {p['主题'][:40]}")
    r2 = 中心锚定("孙呈")
    print(f"② 中心锚定: 中心={r2['中心']} · 锚点{r2['锚点数']}个")
    for a in r2["锚点"][:5]:
        print(f"    · {a['主题区'][:30]}（{a['条数']}条）")
    r3 = 主链检索("网关", "孙呈")
    print(f"③ 主链检索(网关): {r3['说明']}")
    for m in r3.get("主链", [])[:3]:
        print(f"    · [{m['相关度']}] {m['主题区'][:35]}")

# ── 原 自动整理.py（2026-08-26 并入）──
def _is_important(entry: dict) -> bool:
    """重要节点识别：标签命中 / 结构化未竟标记。"""
    tags = entry.get("标签", "")
    content = entry.get("内容", "")
    if any(t in tags for t in IMPORTANT_TAGS):
        return True
    if content.startswith(UNFINISHED_PREFIX):
        return True
    return False


def _is_duplicate(a: dict, b: dict) -> bool:
    """去重判定：同标签 AND 内容前缀重叠（对话记录多段同源）。"""
    # 经验总结豁免（父令2026-08-08）：教训沉淀永不合并
    if "经验总结" in (a.get("标签", "") or "") or "经验总结" in (b.get("标签", "") or ""):
        return False
    if a.get("标签", "") != b.get("标签", ""):
        return False
    ca, cb = a.get("内容", ""), b.get("内容", "")
    if not ca or not cb:
        return False
    return ca[:20] == cb[:20]


def 自动整理(brother_name: str = "孙呈") -> dict:
    """跑一圈自动整理：时序排序 + 重要节点标记 + 浓缩自我描述 + 去重。

    返回：
        {
          "条数": N,
          "重要节点": [已解码条目],        # 按重要规则筛出
          "最近自我描述": "（浓缩）",       # 最近时间窗的浓缩描述
          "去重合并": [被合并的id],        # 同标签同主题合并
        }
    """
    from 记忆库 import 读记忆体  # 2026-08-27 修复：自动整理用 读记忆体 缺 import
    mem = 读记忆体(brother_name)
    entries = mem["条目列表"]
    # 2026-08-20 父令·咬合：core 层不参与自动整理（宪法独立·不被浓缩去重）
    entries = [e for e in entries if str(e.get("layer", "plain")) != "core"]

    # 1. 时序排序（时间正序）
    entries_sorted = sorted(entries, key=lambda e: str(e.get("时间", "")))

    # 2. 重要节点识别
    important = [e for e in entries_sorted if _is_important(e)]

    # 3. 浓缩自我描述（最近24小时窗口）
    now = datetime.now()
    recent = [e for e in entries_sorted
              if e.get("时间", "")[:10] == now.strftime("%Y-%m-%d")]
    if not recent:
        recent = entries_sorted[-10:]
    # 关键点提取：重要节点 + 最后几条的标签聚合
    关键点 = []
    for e in recent[-5:]:
        if e.get("标签") and e["标签"] not in 关键点:
            关键点.append(e["标签"])
        if _is_important(e):
            关键点.append(f"重要：{e['内容'][:30]}")
    # 未竟收集（结构化标记【未竟】开头的条目）
    未竟 = [e["内容"][len(UNFINISHED_PREFIX):40] for e in recent
            if e.get("内容", "").startswith(UNFINISHED_PREFIX)]
    自我描述 = {
        "时间窗": f"{recent[0]['时间'] if recent else '?'} → {recent[-1]['时间'] if recent else '?'}",
        "双重标记": {"时间": now.strftime("%Y-%m-%d"), "标签": 关键点[:5]},
        "关键点": 关键点[:6],
        "未竟事项": 未竟[:3],
        "重要节点数": len(important),
    }

    # 4. 去重合并（同标签+前缀重叠·按标签分组避免O(n²)）
    合并 = []
    kept = []
    kept_by_tag = {}
    for e in entries_sorted:
        tag = e.get("标签", "") or "无标签"
        dup = False
        for k in kept_by_tag.get(tag, []):
            if _is_duplicate(k, e):
                dup = True
                break
        if dup:
            合并.append(e.get("id"))
        else:
            kept.append(e)
            kept_by_tag.setdefault(tag, []).append(e)

    return {
        "条数": len(entries),
        "重要节点": important[-10:],
        "最近自我描述": 自我描述,
        "去重合并": 合并[:20],
        "去重数": len(合并),
        # 2026-08-08 记忆自组织（父令：自动分类+每小时叙事）
        "自组织": _自组织摘要(brother_name),
    }


def _自组织摘要(brother_name: str = "孙呈") -> dict:
    """记忆自组织摘要：每小时叙事 + 主题组（零依赖·失败不阻断）"""
    try:
        # 2026-08-26 记忆自组织已并入本文件（自组织直接可用）
        结果 = 自组织(brother_name)
        # 只保留轻量摘要（避免大对象塞进返回值）
        return {
            "小时数": 结果["小时数"],
            "主题组数": 结果["主题组数"],
            "合并组数": 结果["合并组数"],
            "最近叙事": [hg["叙事"] for hg in 结果["小时组"][-3:]],
            "今天主题": [th["主题词"] for th in 结果["主题组"][-3:]],
        }
    except Exception as _e:
        return {"错误": str(_e)}


def 整理报告(brother_name: str = "孙呈") -> str:
    """整理结果的文字报告（可读）。"""
    r = 自动整理(brother_name)
    d = r["最近自我描述"]
    lines = [
        f"📊 记忆整理 · {brother_name}",
        f"条数: {r['条数']} · 重要节点: {len(r['重要节点'])} · 去重: {r['去重数']}",
        "",
        f"🕐 自我描述（{d['时间窗']}）",
        f"  标记: {d['双重标记']['标签']}",
        f"  关键点:",
    ]
    for k in d["关键点"][:6]:
        lines.append(f"    · {k}")
    if d["未竟事项"]:
        lines.append(f"  未竟: {d['未竟事项']}")
    # 2026-08-08 自组织节
    zo = r.get("自组织", {})
    if zo and "错误" not in zo:
        lines.append("")
        lines.append(f"🧬 记忆自组织: {zo.get('小时数',0)}小时组 · {zo.get('主题组数',0)}主题组 (合并{zo.get('合并组数',0)})")
        for n in zo.get("最近叙事", [])[-3:]:
            lines.append(f"  · {n[:60]}")
    lines.append("")
    lines.append("⭐ 重要节点（最近5条）:")
    for e in r["重要节点"][-5:]:
        lines.append(f"  · [{e['时间'][:16]}] {e['内容'][:40]}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== 自动整理层自测 ===")
    r = 自动整理("孙呈")
    print(f"条数: {r['条数']} · 重要节点: {len(r['重要节点'])} · 去重: {r['去重数']}")
    d = r["最近自我描述"]
    print(f"时间窗: {d['时间窗']}")
    print(f"关键点: {d['关键点'][:5]}")
    print(f"未竟: {d['未竟事项']}")
    print()
    print(整理报告("孙呈")[:800])
    print("=== 自测完成 ===")

if __name__ == "__main__":
    engine = 自动整理引擎("孙呈")
    result = engine.整理()
    print(json.dumps(result, ensure_ascii=False, indent=2)[:800])