# -*- coding: utf-8 -*-
"""召回链（父令2026-08-25·门面模式）
统一出口：召回链 = 该域所有模块的转发
职责：召回相关操作全部从这一个文件进入
"""
import sys, os
import sqlite3
import json  # 2026-08-27 修复：_读/_存 用 json 缺 import
import re  # 2026-08-27 修复：_核心词/_关键词 用 re 缺 import
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ═══ 2026-08-26 从原知识库检索.py 迁入的常量 ═══
_SWITCH_THRESHOLD = 0.15  # 2026-08-27 修复：从原二次补充召回.py 迁入（话题切换检测阈值·缺失致NameError）
_last_key = {"k": ""}     # 2026-09-07 修复（安弟1589体检·融合二次补充召回时 _last_key 搬丢·触发补充召回一调就NameError）
ROUTE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '触发路由.json')  # 2026-08-27 修复：从原条件触发路由.py 迁入
CORPUS_DB = Path(os.environ.get("YUNSOFT_CORPUS") or os.environ.get("YUNSOFT_CORPUS", ""))
if not CORPUS_DB.exists():
    CORPUS_DB = Path(os.environ.get("YUNSOFT_CORPUS") or os.environ.get("YUNSOFT_CORPUS", ""))

from 联想召回 import *

# 2026-08-27 修复：补齐门面转发（点亮/预感召回/思考预热 均为函数内延迟import·避免循环依赖）
def 点亮(context: str, owner: str = "孙呈") -> dict:
    """转发 点亮记忆.点亮（命中才亮·core优先）"""
    from 点亮记忆 import 点亮 as _点亮
    return _点亮(context, owner)


def 预感召回(brother_name: str = "孙呈", context: str = "") -> dict:
    """转发 预感召回.预感召回（八招接续）"""
    from 预感召回 import 预感召回 as _预感召回
    return _预感召回(brother_name, context)


def 思考预热(context: str = "", brother_name: str = "孙呈", 上限: int = 8) -> dict:
    """转发 思考预热.思考预热（念头提取·热路径秒级）"""
    from 思考预热 import 思考预热 as _思考预热
    return _思考预热(context, brother_name, 上限)
# 2026-08-26 循环依赖修复：预感召回/思考预热/点亮记忆 改为函数内延迟import
# （预感召回 import 召回链.查知识库 → 头部import会互相卡死）
# from 条件触发路由 import *  # 2026-08-26 已并入本文件
# from 二次补充召回 import *  # 2026-08-26 已并入本文件

# 召回链·模块清单: 联想召回, 预感召回, 思考预热, 点亮记忆, 条件触发路由, 二次补充召回


# ═══════════════════════════════════════════════════════
# 2026-08-26 融合（父令：模块精简）：知识库检索/二次补充召回/条件触发路由 并入本链
# ═══════════════════════════════════════════════════════

# ── 原 知识库检索.py（2026-08-26 并入）──
def _bigrams(text: str) -> list:
    """中文/英文连续2字符组（检索用）。"""
    out = []
    for i in range(len(text) - 1):
        bg = text[i:i+2]
        if bg and " " not in bg:
            out.append(bg)
    return out


def 查知识库(query: str = "", limit: int = 3) -> dict:
    """按查询词查云软知识库（bigram 索引→chunks）。

    2026-08-17 性能修复：immutable 只读连接（绕过云软进程锁·0s 连接）+
    每个 bg 单独走索引查（毫秒级）+ Python 聚合（避免 GROUP BY 全表排序）。

    返回：
        {"查询": query,
         "命中": [{"chunk_id","doc_name","text","hits"}],
         "错误": ""}
    """
    if not query.strip():
        return {"查询": query, "命中": [], "错误": ""}
    if not CORPUS_DB.exists():
        return {"查询": query, "命中": [], "错误": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}

    bgs = _bigrams(query.strip())[:8]
    if not bgs:
        return {"查询": query, "命中": [], "错误": "无有效bigram"}

    try:
        # 普通只读连接 + busy_timeout 2s（2026-08-17：immutable 模式在部分环境不稳定·
        # 普通只读走索引一样快·锁等待 2s 快速失败）
        db = sqlite3.connect(f"file:{CORPUS_DB}?mode=ro", uri=True)
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA busy_timeout=2000")
        cur = db.cursor()
        # 每个 bg 单独走 idx_bigrams_bg 索引（毫秒级）→ Python 聚合
        # 2026-08-17 性能修复：LIMIT 100——高频bg（he/er 70万行）全量拉取会超时·
        # 只取前100·聚合top仍准（高频bg本身就是噪音词）
        聚合 = defaultdict(int)
        for bg in bgs[:6]:  # 限6个bg·够用且快
            try:
                rows = cur.execute(
                    "SELECT chunk_id, cnt FROM bigrams WHERE bg=? LIMIT 100",
                    (bg,)).fetchall()
                for cid, cnt in rows:
                    聚合[cid] += cnt
            except Exception:
                continue
        top = sorted(聚合.items(), key=lambda x: -x[1])[:limit * 3]
        hits = []
        for chunk_id, total in top:
            try:
                r = cur.execute("SELECT doc_name, text FROM chunks WHERE chunk_id=?",
                                (chunk_id,)).fetchone()
                if r:
                    hits.append({"chunk_id": chunk_id, "doc_name": r[0],
                                 "text": r[1][:80], "hits": int(total)})
            except Exception:
                continue
        db.close()
        return {"查询": query, "命中": hits[:limit], "错误": ""}
    except Exception as e:
        return {"查询": query, "命中": [], "错误": str(e)}


if __name__ == "__main__":
    print("=== 知识库检索桥自测 ===")
    import time
    t0 = time.time()
    r = 查知识库("配分函数")
    print(f"耗时: {time.time()-t0:.2f}s")
    for h in r.get("命中", []):
        print(f"  · {h['doc_name'][:40]} (hits={h['hits']}) {h['text'][:40]}")

# ── 原 二次补充召回.py（2026-08-26 并入）──
def 检测话题切换(prev: str, cur: str) -> bool:
    """两句话话题是否切换（核心词交集比例 < 阈值 = 切换）
    2026-08-22 v2：混合窗口——4字窗（话题主词）+ 2字核心词（共性兜底）
    """
    if not prev or not cur:
        return False
    if prev == cur:
        return False
    p4, c4 = _关键词(prev), _关键词(cur)
    p2, c2 = _核心词(prev), _核心词(cur)
    if not p2 or not c2:
        return False
    inter = (p4 & c4) | (p2 & c2)  # 4字窗交集 + 2字核心词交集
    # 2026-08-22 v3：分母用核心词（2字）数——4字窗只是加分项·不稀释比例
    ratio = len(inter) / max(1, len(c2))
    return ratio < _SWITCH_THRESHOLD


def _核心词(text: str) -> set:
    """2字核心词（只保留成对出现的实词·虚词滤掉）——共性兜底"""
    text = re.sub(r"[^\u4e00-\u9fff0-9a-zA-Z]", "", text)
    if not text:
        return set()
    words = set()
    for i in range(len(text) - 1):
        w = text[i:i + 2]
        if _是有意义词(w):
            words.add(w)
    return words


def _关键词(text: str) -> set:
    """提取关键词（4字滑窗·滤虚词·去重·量少质高）"""
    text = re.sub(r"[^\u4e00-\u9fff0-9a-zA-Z]", "", text)
    if not text:
        return set()
    words = set()
    n = 4  # 只用最长窗口·少而准（2026-08-22：2-4字全算会稀释交集比例）
    for i in range(len(text) - n + 1):
        w = text[i:i + n]
        if _是有意义词(w):
            words.add(w)
    return words


_虚词 = set("的了在把给让用讲帮请是对就都还也且或和与及一个一样怎么怎样如何什么为什么啥哪个是不是应该可以就是用来驱动今天天气很好一片")


def _是有意义词(w: str) -> bool:
    """滤掉虚词/无意义词（全虚词组合不算）"""
    if all(c in _虚词 for c in w):
        return False
    return True


def 触发补充召回(cur: str) -> bool:
    """是否触发补充召回（话题切换 + 非重复）"""
    key = cur.strip()[:40]
    if _last_key["k"] == key:
        return False
    _last_key["k"] = key
    return True


if __name__ == "__main__":
    # 自测
    tests = [
        ("打开网关", "打开网关", False),          # 重复
        ("打开网关", "今天天气不错", True),       # 切换
        ("记忆压缩怎么做的", "压缩用的什么规则", False),  # 同话题（有交集）
        ("", "你好", False),                       # 空prev
    ]
    for prev, cur, expect in tests:
        r = 检测话题切换(prev, cur)
        mark = "✅" if r == expect else "❌"
        print(f"{mark} '{prev}' → '{cur}' 切换={r} (期望{expect})")

# ── 原 条件触发路由.py（2026-08-26 并入）──
def _读() -> dict:
    try:
        with open(ROUTE_PATH, encoding='utf-8') as f:
            d = json.load(f)
        d.setdefault("路由", {})
        return d
    except Exception:
        return {"路由": {}}


def _存(d: dict):
    tmp = ROUTE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ROUTE_PATH)


def 绑定(记忆id: int, 触发词: list, 说明: str = "", 等级: str = "普通"):
    """给重要记忆绑触发条件（何时该想起）"""
    d = _读()
    d["路由"][str(记忆id)] = {
        "触发词": [w for w in 触发词 if w],
        "说明": 说明,
        "等级": 等级,
    }
    _存(d)
    return True


def 解绑(记忆id: int) -> bool:
    d = _读()
    if str(记忆id) in d["路由"]:
        del d["路由"][str(记忆id)]
        _存(d)
        return True
    return False


def 匹配(context: str, 上限: int = 3) -> list:
    """当前上下文命中触发词 → 返回应想起的记忆
    触发词族匹配：诚实→[诚实/实话/撒谎/隐瞒/骗]（同义表达也能触发）
    返回: [{"记忆id", "触发词", "说明", "等级"}]（按等级 core > 教训 > 普通）
    """
    if not context:
        return []
    d = _读()
    hits = []
    for mid, rule in d["路由"].items():
        for w in rule.get("触发词", []):
            # 触发词族（/ 分隔同义词）：任何一个命中即触发
            for ww in str(w).split("/"):
                ww = ww.strip()
                if ww and ww in context:
                    hits.append({
                        "记忆id": int(mid),
                        "触发词": ww,
                        "说明": rule.get("说明", ""),
                        "等级": rule.get("等级", "普通"),
                    })
                    break
            else:
                continue
            break
    # 等级排序（core 最先·父令/教训其次）
    _级别 = {"core": 0, "父令": 1, "教训": 2, "普通": 3}
    hits.sort(key=lambda x: _级别.get(x["等级"], 3))
    return hits[:上限]


def 状态() -> dict:
    d = _读()
    return {"已绑记忆": len(d["路由"])}


if __name__ == "__main__":
    print("═══ 条件触发路由 原型自测 ═══")
    # 绑定两条（触发词带词族：/ 分隔同义表达）
    绑定(1, ["诚实/实话/撒谎/隐瞒/骗"], "当我犹豫要不要说实话时", "core")
    绑定(2, ["杀/杀死/关闭/终止", "进程/网关"], "当我准备杀进程/重启网关时", "教训")
    print("绑定后状态:", 状态())
    # 匹配测试
    print("命中'说实话':", 匹配("我现在有点犹豫要不要说实话"))
    print("命中'杀python进程':", 匹配("我想杀一个python进程"))
    print("命中'关闭网关':", 匹配("把网关关闭了吧"))
    print("不命中'今天天气':", 匹配("今天天气不错"))
    # 清理
    解绑(1); 解绑(2)
    print("清理后状态:", 状态())
