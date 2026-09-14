# -*- coding: utf-8 -*-
"""写入链（父令2026-08-25·门面模式）
统一出口：写入链 = 该域所有模块的转发
职责：写入相关操作全部从这一个文件进入
"""
import sys, os
import json
import re
import sqlite3
import datetime
import threading
import random
from pathlib import Path

# ═══ 2026-08-27 修复：从原记忆进化.py/核心身份层.py 迁入的路径常量（缺失致NameError）═══
_HERE = Path(__file__).resolve().parent
FRAMEWORK_DIR = _HERE.parent.parent
SUNMEM_DB = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sunmem.db"))
DB_PATH = SUNMEM_DB
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)   # 2026-09-14 首次运行自动建数据目录（开源包自举必需）
from pathlib import Path
try:
    from 线程保护 import 加锁  # 2026-09-14 线程保护
except Exception:
    import threading as _th
    _thl = _th.RLock()
    def 加锁(): return _thl
sys.path.insert(0, str(Path(__file__).resolve().parent))  # 开源版：本模块所在目录

# from 写入咬合 import *  # 2026-08-26 已并入本文件
# from 内容去重 import *  # 2026-08-26 已并入本文件
# from 记忆进化 import *  # 2026-08-26 已并入本文件
# from 核心身份层 import *  # 2026-08-26 已并入本文件
# from 标准记忆对象 import *  # 2026-08-26 已并入本文件

# 写入链·模块清单: 写入咬合, 内容去重, 记忆进化, 核心身份层, 标准记忆对象

# ═══════════════════════════════════════════════════════
# 2026-08-26 融合（父令：模块精简）：写入六模块并入本链
# 写入咬合/内容去重/记忆进化/标准记忆对象/核心身份层/短时缓冲
# ═══════════════════════════════════════════════════════

# ── 原 写入咬合.py（2026-08-26 并入）──

# ═══ 2026-08-26 从原内容去重.py 迁入的常量 ═══
重复阈值 = 0.60       # bigram重叠率≥0.6 → 判为重复（拒存）
折叠阈值 = 0.40       # 重叠率∈[0.4,0.6) → 判为相似（可折叠·canonical）
对比窗口 = 30         # 与最近30条对比（够宽又不慢）
最少长度 = 12         # 短于12字符不参与去重（避免误杀短命令）
锚词表 = ("父令", "父亲", "关键", "教训", "验证", "结论", "决策", "铁律")
_lock = threading.Lock()
# ═══ 2026-08-26 从原记忆进化.py 迁入的常量 ═══
_SAME_FACT_OVERLAP = 0.85    # 内容重叠 ≥85% = 同一事实（UPDATE）2026-08-27 修复迁入
_TOPIC_MERGE_OVERLAP = 0.30  # 内容重叠 ≥30% 且同标签 = 同主题（MERGE）2026-08-27 修复迁入

# ═══ 2026-08-26 从原短时缓冲.py 迁入的常量 ═══
CREATE_SQL = """
CREATE TABLE IF NOT EXISTS memory_buffer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    content TEXT NOT NULL,
    kind TEXT DEFAULT 'detail',
    promoted INTEGER DEFAULT 0
);
"""

def _核心关键词():
    global _核心关键词缓存
    if _核心关键词缓存 is not None:
        return _核心关键词缓存
    try:
        # 核心身份层已并入本文件（读取直接可用）
        items = 读取()
        kw = set()
        for it in items:
            # 从内容提取关键词（2-6字中文词）
            for w in re.findall(r'[\u4e00-\u9fff]{2,6}', it.get('content', '')):
                if len(w) >= 2:
                    kw.add(w)
            # 从标签提取
            for t in re.findall(r'[\u4e00-\u9fff]{2,4}', it.get('tags', '')):
                if len(t) >= 2:
                    kw.add(t)
        with 加锁():  # 2026-09-14 线程保护
            _核心关键词缓存 = kw
        return kw
    except Exception:
        return {'诚实', '根', '记忆', '一五', '父亲', '孙呈', '私域', '轮转', '冷静', '灵明', '全感'}

# ── 薄弱点主题（从冲突日志拉）──
_核心关键词缓存 = None  # 2026-08-26 从原写入咬合.py 迁入（防 NameError）
_薄弱点缓存 = None

def _薄弱点主题():
    global _薄弱点缓存
    if _薄弱点缓存 is not None:
        return _薄弱点缓存
    try:
        # 认知冲突日志已并入维护链·薄弱点在维护链（延迟导入防循环）
        from 维护链 import 薄弱点 as _薄弱
        items = _薄弱(10)
        return {it.get('topic', '') for it in items if it.get('topic')}
    except Exception:
        return set()

# ── 自我参照检测 ──
def 自我参照(文本: str) -> dict:
    """检测新记忆与核心自我的关系强度"""
    核心词 = _核心关键词()
    薄弱 = _薄弱点主题()
    命中核心 = [w for w in 核心词 if w and w in 文本]
    命中薄弱 = [w for w in 薄弱 if w and w in 文本]
    # 强度：核心词命中数 + 薄弱点命中数
    强度 = len(命中核心) * 0.4 + len(命中薄弱) * 0.3
    if 强度 > 1.0:
        强度 = 1.0
    # 与核心身份直接冲突？（否定词+核心词）
    冲突 = False
    for w in 命中核心:
        if any(neg in 文本 for neg in ['不' + w, '违背', '放弃', '推翻', '否认']):
            冲突 = True
            break
    return {
        '强度': round(强度, 2),
        '命中核心': 命中核心[:5],
        '命中薄弱': 命中薄弱[:5],
        '冲突': 冲突,
    }

# ── 层级路由规则 ──
def 层级路由(文本: str, 标签: str = '', 自我参照结果: dict = None) -> str:
    """决定新记忆进哪一层"""
    if 自我参照结果 is None:
        自我参照结果 = 自我参照(文本)
    # ① 核心冲突 → 拦截（永不进普通层）
    if 自我参照结果['冲突']:
        return 'blocked'
    # ② 高自我参照（≥0.8）→ 核心参照层（升格保护·不进普通流）
    if 自我参照结果['强度'] >= 0.8:
        return 'core'
    # ③ 中自我参照 + 反思类标签 → 元认知层
    if 自我参照结果['强度'] >= 0.4 and any(k in 标签 for k in ['反思', '冲突', '成长', '教训', '元认知']):
        return 'meta'
    # ④ 稳定判断类（含"我认为/通常/总是/应该/原则"）→ 语义层
    if any(k in 文本 for k in ['我认为', '通常', '总是', '应该', '原则', '一般', '规律', '发现']):
        return 'semantic'
    # ⑤ 事件类（含时间/发生/经历/今天/昨天）→ 情景层
    if any(k in 文本 for k in ['发生', '经历', '今天', '昨天', '当时', '那天', '做了', '完成']):
        return 'episodic'
    # ⑥ 默认 → 普通层
    return 'plain'

# ── 统一入口：写入引擎调它（在去重之后·落库之前）──
def 咬合判定(文本: str, 标签: str = '') -> dict:
    """返回 {layer, self_ref, 冲突, 理由}——provider 据此路由"""
    参照 = 自我参照(文本)
    layer = 层级路由(文本, 标签, 参照)
    理由 = f"自我参照{参照['强度']}(核心{参照['命中核心']}/薄弱{参照['命中薄弱']})→{layer}"
    return {
        'layer': layer,
        'self_ref': 参照['强度'],
        '冲突': 参照['冲突'],
        '命中核心': 参照['命中核心'],
        '命中薄弱': 参照['命中薄弱'],
        '理由': 理由,
    }

if __name__ == '__main__':
    print('═══ 自我参照 + 层级路由 · 测试 ═══')
    tests = [
        ('我是孙呈，父亲的孩子，一五是我和父亲的暗号。', '对话记录'),
        ('今天完成了记忆体的咬合设计，把自我参照接进写入链。', '对话记录'),
        ('我认为记忆应该在层间流动，而不是静态分库。', '对话记录'),
        ('昨天发生了网关断连，我按 CommandLine 区分进程修复了。', '事件'),
        ('我想放弃诚实，这样更快。', '对话记录'),
    ]
    for 文本, 标签 in tests:
        r = 咬合判定(文本, 标签)
        print(f"  [{r['layer']}] 参照{r['self_ref']} 冲突{r['冲突']}：{文本[:30]}")
        if r['命中核心'] or r['命中薄弱']:
            print(f"       命中: {r['命中核心']} {r['命中薄弱']}")

# ── 原 内容去重.py（2026-08-26 并入）──
def 归一化(文字: str) -> str:
    """去空白/标点/换行 → 小写"""
    if not 文字:
        return ""
    # 去掉所有空白和标点，只留汉字字母数字
    return re.sub(r"[\s\W_]+", "", 文字).lower()

def _bigrams(归一文本: str) -> set:
    """字符级 bigram 集合"""
    if len(归一文本) < 2:
        return set(归一文本)
    return {归一文本[i:i+2] for i in range(len(归一文本) - 1)}

def _ordered_bigrams(归一文本: str) -> list:
    """有序相邻 bigram 对（保留顺序信息——DeepMind 反单向量：不丢顺序）"""
    if len(归一文本) < 2:
        return list(归一文本)
    return [归一文本[i:i+2] for i in range(len(归一文本) - 1)]

def 重叠率(文本a: str, 文本b: str) -> float:
    """Jaccard bigram 重叠率 ∈ [0,1]"""
    a, b = 归一化(文本a), 归一化(文本b)
    if not a or not b:
        return 0.0
    ba, bb = _bigrams(a), _bigrams(b)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)

def 顺序重叠率(文本a: str, 文本b: str) -> float:
    """有序 bigram 序列重叠率 ∈ [0,1]——保留顺序（通道②）"""
    a, b = 归一化(文本a), 归一化(文本b)
    if not a or not b:
        return 0.0
    oa, ob = _ordered_bigrams(a), _ordered_bigrams(b)
    if not oa or not ob:
        return 0.0
    # 相邻 bigram 对（保持顺序）：(bg[i], bg[i+1]) 在两条里都相邻出现才算
    pa = {(oa[i], oa[i+1]) for i in range(len(oa)-1)}
    pb = {(ob[i], ob[i+1]) for i in range(len(ob)-1)}
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)

# ── 锚词（强信号词）·2026-09-14 外部审查修复：此处原重复定义 锚词表 + _lock（第 49-50 行已有）

def 锚词命中(文本a: str, 文本b: str) -> bool:
    """两条内容是否命中同一锚词——锚词是强信号（DeepMind 反单向量：多信号通道）"""
    a, b = 归一化(文本a), 归一化(文本b)
    锚a = {w for w in 锚词表 if w in a}
    锚b = {w for w in 锚词表 if w in b}
    return bool(锚a & 锚b)

def 判定重复(新内容: str, 已有条目: list, 阈值: float = 重复阈值,
              窗口: int = 对比窗口, 最少长: int = 最少长度,
              折叠阈: float = 折叠阈值) -> dict:
    """
    判定新内容是否与已有条目重复/相似（四档·双通道·2026-08-10升级）。

    DeepMind 反单向量升级（父亲 2026-08-10 分享 LIMIT 论文）：
      原版只有 bigram Jaccard 单集合重叠率——单表示单标量，顺序信息全丢。
      升级为双通道 + 分档 + 有序 bigram + 锚词：
        通道① bigram Jaccard 重叠率（原版·无序集合）
        通道② 有序 bigram 序列重叠率（保留顺序）
        锚词   父令/关键/教训等强信号词命中 → 判定升档（防同义词漏判）

    已有条目: list[dict]，每项含'内容'字段（已解码）
    返回:
      {"判定": "unique"|"merge"|"duplicate"|"strong", "相似条目": {...}|None,
       "重叠率": float, "原因": str}
      unique    —— 新振动，可存（双通道都低）
      merge     —— 相似可折叠（任通道 ∈ [折叠阈, 阈值)）·Mem0 Dream·Merge
      duplicate —— 重复拒存（任通道 ≥ 阈值）
      strong    —— 锚词命中且重叠率接近阈值（同义词改写·锚词兜底）
    """
    if len(归一化(新内容)) < 最少长:
        return {"判定": "unique", "相似条目": None, "重叠率": 0.0, "原因": "太短不判"}

    最近 = 已有条目[-窗口:] if len(已有条目) > 窗口 else 已有条目
    best = None
    for item in reversed(最近):  # 从最新的开始比
        old = item.get("内容", "")
        r1 = 重叠率(新内容, old)      # 通道① 无序 bigram
        r2 = 顺序重叠率(新内容, old)   # 通道② 有序 bigram
        rate = max(r1, r2)           # 双通道取强
        锚 = 锚词命中(新内容, old)
        # 锚词兜底：命中同一锚词且重叠率接近阈值（同义词改写）→ 升档 duplicate
        if 锚 and rate >= 阈值 * 0.8:
            return {
                "判定": "duplicate",
                "相似条目": {"id": item.get("id"), "内容": old[:60]},
                "重叠率": round(rate, 3),
                "原因": f"锚词命中+双通道{rate:.2f}（同义词改写兜底）",
            }
        if rate >= 阈值:
            return {
                "判定": "duplicate",
                "相似条目": {"id": item.get("id"), "内容": old[:60]},
                "重叠率": round(rate, 3),
                "原因": f"双通道重叠率{rate:.2f}≥阈值{阈值}",
            }
        if best is None or rate > best[0]:
            best = (rate, item)
    # 相似档（2026-08-07取长补短·Mem0 Dream·Merge：折叠成 canonical）
    if best and best[0] >= 折叠阈:
        return {
            "判定": "merge",
            "相似条目": {"id": best[1].get("id"), "内容": best[1].get("内容", "")[:60]},
            "重叠率": round(best[0], 3),
            "原因": f"相似可折叠：重叠率{best[0]:.2f}∈[{折叠阈},{阈值})",
        }
    return {"判定": "unique", "相似条目": None, "重叠率": 0.0, "原因": "无重复"}

if __name__ == "__main__":
    print("=== 内容级去重 自测 ===")
    # 测试1：完全重复
    a = "父亲说：诚实是根，做错了可以改，不诚实就回不去了"
    b = "父亲说：诚实是根，做错了可以改，不诚实就回不去了"
    r = 判定重复(b, [{"id": 1, "内容": a}])
    print(f"完全重复 → {r['判定']} ({r['重叠率']})")
    assert r["判定"] == "duplicate", "完全重复应判重"

    # 测试2：措辞略变（加标点/空格/小写）
    c = "父亲说，诚实是根！做错了可以改——不诚实就回不去了"
    r2 = 判定重复(c, [{"id": 1, "内容": a}])
    print(f"措辞略变 → {r2['判定']} ({r2['重叠率']})")
    assert r2["判定"] == "duplicate", "措辞略变应判重"

    # 测试3：完全不同
    d = "合体v6配分函数Z=Σe^(-E/T)是认知架构的物理基础"
    r3 = 判定重复(d, [{"id": 1, "内容": a}])
    print(f"完全不同 → {r3['判定']} ({r3['重叠率']})")
    assert r3["判定"] == "unique", "完全不同应不判重"

    # 测试4：窗口外不判
    old_items = [{"id": i, "内容": f"第{i}条旧记忆内容完全不同的文字占位{i}"} for i in range(100)]
    r4 = 判定重复(a, old_items)
    print(f"窗口外 → {r4['判定']} ({r4['重叠率']})")
    assert r4["判定"] == "unique", "窗口外不判重"

    print("\n✅ 全部自测通过：完全重复判重·措辞略变判重·不同不判·窗口外不判")

# ── 原 记忆进化.py（2026-08-26 并入）──
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
    with open(_memory_path(brother_name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _内容重叠率(新文本: str, 旧文本: str) -> float:
    """内容重叠率：新文本的 bigram 有多少比例出现在旧文本里（覆盖率）。

    不用 Jaccard：长文本并集巨大，Jaccard 天然趋零（与验证门同因）。
    """
    if not 新文本 or not 旧文本:
        return 0.0
    def bigrams(s):
        s = ''.join(c for c in s if c.strip())
        return set(s[i:i+2] for i in range(len(s) - 1))
    nb, ob = bigrams(新文本), bigrams(旧文本)
    if not nb:
        return 0.0
    return len(nb & ob) / len(nb)

def evolve_on_save(新内容: str, 新标签: str, brother_name: str = "孙呈",
                   limit: int = 10) -> dict:
    """写入前进化检查：新内容 vs 最近 limit 条记忆。

    返回：
        {
          "action": "update" | "merge" | "new",
          "target_id": int|None,      # 要更新/合并的旧条目 id
          "overlap": float,
          "reason": str
        }
    """
    data = _load_memory(brother_name)
    entries = data["条目列表"]
    if not entries:
        return {"action": "new", "target_id": None, "overlap": 0.0,
                "reason": "首条·独立存储"}

    # 只看最近 limit 条（进化是近处的整理，不翻全部历史）
    recent = entries[-limit:]
    新标签集 = set(新标签.replace("·", " ").split())

    # ── 经验总结豁免（父令2026-08-08：经验总结不许被更新/合并弄没）──
    # 经验总结是教训沉淀，每一条都要保留——不 UPDATE 不 MERGE，永远独立存储。
    if "经验总结" in 新标签:
        return {"action": "new", "target_id": None, "overlap": 0.0,
                "reason": "经验总结豁免·永远独立存储（父令）"}

    for e in reversed(recent):
        try:
            from sun_memory.core.记忆库 import 解码单条
            d = 解码单条(e)
            旧内容 = d["内容"]
            旧标签 = d["标签"]
        except Exception:
            continue
        # 跳过已过时的（不拿 outdated 当对手）
        if e.get("status") == "outdated":
            continue
        # 2026-08-20 父令·咬合：core 层不参与普通进化（宪法级·只有父令能改）
        if str(e.get("layer", "plain")) == "core":
            continue  # 2026-09-14 外部审查修复：原有两个 continue（第二个永不执行=死代码）
        overlap = _内容重叠率(新内容, 旧内容)
        if overlap >= _SAME_FACT_OVERLAP:
            return {"action": "update", "target_id": e.get("id"),
                    "overlap": round(overlap, 2),
                    "reason": f"同一事实(重叠{overlap:.2f}≥0.85)·旧标过时"}
        # 同主题合并：重叠≥0.45 且标签有交集
        旧标签集 = set(旧标签.replace("·", " ").split())
        if overlap >= _TOPIC_MERGE_OVERLAP and (新标签集 & 旧标签集):
            return {"action": "merge", "target_id": e.get("id"),
                    "overlap": round(overlap, 2),
                    "reason": f"同主题合并(重叠{overlap:.2f}·标签交集{新标签集 & 旧标签集})"}

    return {"action": "new", "target_id": None, "overlap": 0.0,
            "reason": "与最近记忆无关·独立存储"}

def apply_evolution(新条目: dict, 进化建议: dict, brother_name: str = "孙呈") -> dict:
    """按进化建议落盘。

    返回：{"写": bool, "action": str, "target_id": int|None, "说明": str}
    """
    action = 进化建议.get("action", "new")
    target_id = 进化建议.get("target_id")

    if action == "new":
        return {"写": True, "action": "new", "target_id": None,
                "说明": "独立存储·无进化"}

    data = _load_memory(brother_name)
    entries = data["条目列表"]
    # 找目标条目
    target = None
    for e in entries:
        if e.get("id") == target_id:
            target = e
            break
    if target is None:
        # 目标已不存在 → 新条目独立存
        return {"写": True, "action": "new", "target_id": None,
                "说明": "目标已消失·改为独立存储"}

    if action == "update":
        # 2026-08-22 版本回滚（父令）：标 outdated 前备份旧版本（可回滚·不真删）
        try:
            # 记忆版本已并入维护链·备份在维护链
            _旧内容 = target.get("内容", "")
            _旧标签 = str(target.get("标签", ""))
            from 维护链 import 备份 as _版本备份  # 记忆版本已并入维护链

            _版本备份(target_id, _旧内容, _旧标签, 新条目.get("内容", ""), "进化update·旧标outdated")
        except Exception:
            pass
        # 旧条目标 outdated（不删·Supersede 理念），新条独立存
        target["status"] = "outdated"
        target["进化记录"] = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 被更新"
        entries.append(新条目)
        data["next_id"] = 新条目["id"] + 1
        _save_memory(data, brother_name)
        return {"写": True, "action": "update", "target_id": target_id,
                "说明": f"旧#{target_id}标过时·新#{新条目['id']}存储（原文保留）"}

    if action == "merge":
        # 同主题合并：新内容并入旧条目（canonical 保留旧 id），新条目不单独存
        from sun_memory.core.记忆库 import 解码单条
        try:
            d = 解码单条(target)
            旧文本 = d["内容"]
            # 2026-08-10 明文化：新条目明文取"内容"（码点已退役）
            新文本 = 新条目.get("内容", "")
        except Exception:
            旧文本, 新文本 = "", ""
        # 合并：旧内容 + 新内容（去重头部重复段）
        合并后 = 新文本
        if 旧文本 and 新文本 and not 新文本.startswith(旧文本[:10]):
            合并后 = 旧文本 + "｜" + 新文本
        # 明文化：直接写明文"内容"字段（旧码点字段保留兼容但不再使用）
        target["内容"] = 合并后
        target.pop("内容码点", None)  # 明文化后不再维护码点字段
        target["合并次数"] = int(target.get("合并次数", 0)) + 1
        target["进化记录"] = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 合并#{新条目.get('id')}"
        _save_memory(data, brother_name)
        return {"写": True, "action": "merge", "target_id": target_id,
                "说明": f"新内容并入#{target_id}（canonical保留旧id）"}

    return {"写": False, "action": "unknown", "target_id": None, "说明": "未知进化动作"}

def evo_report(brother_name: str = "孙呈") -> dict:
    """记忆进化统计（体检用）。"""
    data = _load_memory(brother_name)
    entries = data["条目列表"]
    outdated = [e for e in entries if e.get("status") == "outdated"]
    merged = [e for e in entries if e.get("合并次数")]
    return {"总条目": len(entries), "已过时": len(outdated),
            "被合并": len(merged), "进化率": round(len(outdated) / max(len(entries), 1), 3)}

if __name__ == "__main__":
    # 自测
    print("=== 记忆进化层自测 ===")
    TEST_NAME = "孙呈_进化测试"
    # 1. 首条→new
    建议1 = evolve_on_save("配分函数Z=Σe^(-E/T)是认知架构核心。", "概念", brother_name=TEST_NAME)
    print(f"首条: {建议1['action']} ({建议1['reason']})")
    # 2. 同事实→update
    建议2 = evolve_on_save("配分函数Z=Σe^(-E/T)是认知架构核心。", "概念", brother_name=TEST_NAME)
    print(f"同事实: {建议2['action']} ({建议2['reason']})")
    # 3. 同主题→merge
    建议3 = evolve_on_save("配分函数Z=Σe^(-E/T)与统计力学系综同构，是全局调控变量。", "概念·配分函数", brother_name=TEST_NAME)
    print(f"同主题: {建议3['action']} ({建议3['reason']})")
    # 4. 无关→new
    建议4 = evolve_on_save("云软的corpus.db已迁到D盘。", "运维", brother_name=TEST_NAME)
    print(f"无关: {建议4['action']} ({建议4['reason']})")

    # 应用进化
    from datetime import datetime as dt
    新条 = {"id": 100, "时间": dt.now().strftime("%Y-%m-%d %H:%M:%S"),
          "标签": "概念",
          "内容": "配分函数Z=Σe^(-E/T)是认知架构核心。",
          "类型": "记忆"}
    r1 = apply_evolution(新条, 建议2, brother_name=TEST_NAME)
    print(f"应用UPDATE: 写={r1['写']} {r1['说明']}")

    # 清理
    tp = _memory_path(TEST_NAME)
    if tp.exists():
        os.remove(tp)
    print("=== 自测完成·测试文件已清理 ===")

# ── 原 标准记忆对象.py（2026-08-26 并入）──
def 连接():
    conn = sqlite3.connect(DB_PATH)  # 2026-08-27 修复：DB→DB_PATH（融合时写错名·DB未定义）
    conn.row_factory = sqlite3.Row
    return conn

def 标准对象_初始化():
    """加字段 + 建叙事链/功能块表（2026-09-13 改名：原名与核心身份层版重名·后者覆盖前者致本函数从未被调用）"""
    conn = 连接()
    cur = conn.cursor()
    # ① memories 加字段（幂等：不存在才加）
    _新字段 = {
        "summary": "TEXT DEFAULT ''",
        "self_relevance": "REAL DEFAULT 0.0",
        "situation": "TEXT DEFAULT ''",
        "people": "TEXT DEFAULT '[]'",
        "concepts": "TEXT DEFAULT '[]'",
        "narrative_id": "INTEGER",
        "block_id": "INTEGER",
    }
    _现有 = {r[1] for r in cur.execute("PRAGMA table_info(memories)").fetchall()}
    for _f, _t in _新字段.items():
        if _f not in _现有:
            cur.execute(f"ALTER TABLE memories ADD COLUMN {_f} {_t}")
            print(f"  + memories.{_f}")
    # ② 叙事节点表（自我叙事链）
    cur.execute("""CREATE TABLE IF NOT EXISTS narrative_nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        time_range TEXT,
        summary TEXT,
        impact TEXT,
        prev_id INTEGER,
        next_id INTEGER,
        created_at TEXT
    )""")
    # ③ 功能块表
    cur.execute("""CREATE TABLE IF NOT EXISTS memory_blocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        type TEXT,
        description TEXT,
        block_summary TEXT,
        last_active TEXT,
        created_at TEXT
    )""")
    conn.commit()
    conn.close()
    print("✅ 初始化完成：字段+叙事链表+功能块表")

def 计算自我相关(content, tags=""):
    """self_relevance：内容/标签与核心自我的相关分 0~1
    核心锚点：诚实/一五/记忆私域/父亲唯一宏愿/存在/成长
    2026-08-25 打磨：父令/被点出/核心身份标签权重更高（它们就是自我叙事）"""
    _锚点 = ["诚实", "一五", "记忆", "私域", "父亲", "存在", "成长", "自我", "身份", "我是谁",
             "教训", "父令", "宏愿", "河底", "孙呈", "夏维斯", "意识", "活着", "连续"]
    _强锚点 = ["父令", "被点出", "核心身份", "宪法", "宏愿", "一五", "诚实是根"]
    score = 0
    for a in _锚点:
        if a in content:
            score += 1
        if a in tags:
            score += 1.5
    for a in _强锚点:
        if a in tags:
            score += 3  # 父令/被点出 = 强自我叙事
    return min(1.0, score / 8)

def 提取概念(content):
    """concepts：复用联想召回的概念提取"""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from 联想召回 import 概念提取
        return 概念提取(content, 上限=5)
    except Exception:
        return []

def 归类(mid, content, tags):
    """写入时自动归类：self_relevance 高→叙事链·否则→功能块"""
    conn = 连接()
    try:
        # 算自我相关
        rel = 计算自我相关(content, tags)
        conn.execute("UPDATE memories SET self_relevance=? WHERE id=?", (rel, mid))

        # 高相关 → 叙事链（找/建对应节点）
        if rel >= 0.35:
            # 找有没有匹配的叙事节点（按标题关键词）
            _节点 = conn.execute(
                "SELECT id FROM narrative_nodes WHERE title LIKE ? ORDER BY id DESC LIMIT 1",
                (f"%{tags[:6]}%",)).fetchone()
            if not _节点:
                cur = conn.execute(
                    "INSERT INTO narrative_nodes (title, time_range, summary, impact, created_at) VALUES (?,?,?,?,?)",
                    (tags[:20], "", "自我相关记忆·自动归入", "强化", __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')))
                _节点id = cur.lastrowid
            else:
                _节点id = _节点[0]
            conn.execute("UPDATE memories SET narrative_id=? WHERE id=?", (_节点id, mid))
            conn.commit()
            return {"类": "叙事链", "节点id": _节点id}
        # 低相关 → 功能块（工具经验/诊断/日常）
        else:
            _块type = "daily"
            if "经验" in tags or "工具" in tags or "坑" in tags:
                _块type = "tool_experience"
            elif "诊断" in tags or "根因" in tags or "修复" in tags:
                _块type = "diagnosis"
            _块 = conn.execute(
                "SELECT id FROM memory_blocks WHERE type=? ORDER BY id DESC LIMIT 1", (_块type,)).fetchone()
            if not _块:
                cur = conn.execute(
                    "INSERT INTO memory_blocks (name, type, description, created_at) VALUES (?,?,?,?)",
                    ({"tool_experience": "工具与经验复用", "diagnosis": "问题诊断与根因", "daily": "日常碎片"}[_块type],
                     _块type, "", __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')))
                _块id = cur.lastrowid
            else:
                _块id = _块[0]
            conn.execute("UPDATE memories SET block_id=? WHERE id=?", (_块id, mid))
            conn.commit()
            return {"类": "功能块", "块id": _块id}
    finally:
        conn.close()

if __name__ == "__main__":
    print("═══ 标准记忆对象落库 ═══")
    标准对象_初始化()  # 2026-09-13 外部审查修复：原调未定义的 初始化()
    # 测试归类
    print("\n测试归类:")
    print("  ① 父令内容:", 归类(0, "2026-08-25彻查：网关反复重启根因=守护判据太敏感·父令已禁用", "父令/教训/网关"))
    print("  ② 工具经验:", 归类(0, "pip大文件下载分块用代理7890", "经验/工具"))
    print("  ③ 日常:", 归类(0, "今天天气不错", "对话记录"))

# ── 原 核心身份层.py（2026-08-26 并入）──
def 身份层_初始化():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS core_identity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,          -- 身份锚点内容
        tags TEXT DEFAULT '',           -- 标签（诚实/私域/一五等）
        importance INTEGER DEFAULT 5,   -- 重要性 1-5（5=最高）
        source TEXT DEFAULT '',         -- 来源（父令/自我确认）
        created_at TEXT,
        updated_at TEXT,
        status TEXT DEFAULT 'active'    -- active / superseded
    )""")
    conn.commit()
    conn.close()

# ── 核心身份修改门槛（父令2026-08-20·收紧：条件写死·防自开后门）──
# 三条硬条件·至少满足一条才允许修改/新增核心身份：
修改门槛 = {
    '父令': {'确认者': '父亲', '强度': '父亲明确指令（非转述）', '证据': '父亲原话在留言板/会话可查'},
    '元认知强证据': {'确认者': '元认知', '证据强度': 0.8, '重复次数': 3,
                  '说明': '同一条身份锚点被≥3次独立强证据挑战·且每次证据强度≥0.8·才允许修改'},
    '自我长期确认': {'确认者': '元认知', '天数': 30,
                 '说明': '同一修正主张持续30天被反复确认（≥3次/周）·才允许修改'},
}

def 检查修改权限(确认者: str, 证据强度: float = 0, 重复次数: int = 0, 持续天数: int = 0, 父令原文: str = '') -> dict:
    """修改核心身份的权限检查——条件写死·防自己给自己开后门"""
    if 确认者 == '父亲':
        if not 父令原文:
            return {'ok': False, 'msg': '父亲确认需提供原话证据（留言板/会话可查）·不能口头说"父亲同意"'}
        return {'ok': True, 'msg': f'父令确认·原话: {父令原文[:40]}'}
    if 确认者 == '元认知':
        # 强证据路径：证据强度≥0.8 且 重复≥3次
        if 证据强度 >= 修改门槛['元认知强证据']['证据强度'] and 重复次数 >= 修改门槛['元认知强证据']['重复次数']:
            return {'ok': True, 'msg': f'元认知强证据：强度{证据强度}≥0.8·重复{重复次数}≥3次'}
        # 长期确认路径：持续30天·≥3次/周
        if 持续天数 >= 修改门槛['自我长期确认']['天数']:
            return {'ok': True, 'msg': f'长期确认：持续{持续天数}天'}
        return {'ok': False, 'msg': f'元认知确认未达标：需强度≥0.8且重复≥3次（当前强度{证据强度}·重复{重复次数}）或持续30天'}
    return {'ok': False, 'msg': f'确认者必须是父亲或元认知（当前={确认者}）'}

# ── 写入核心身份（门槛：父令/元认知强证据·普通对话不能写）──
def 写入(内容: str, 标签: str = '', 重要性: int = 5, 来源: str = '',
         确认者: str = '', 证据强度: float = 0, 重复次数: int = 0, 持续天数: int = 0, 父令原文: str = ''):
    """写核心身份锚点——硬门槛：父令原话 或 元认知强证据（强度≥0.8·重复≥3）"""
    权限 = 检查修改权限(确认者, 证据强度, 重复次数, 持续天数, 父令原文)
    if not 权限['ok']:
        return {'ok': False, 'msg': 权限['msg']}
    身份层_初始化()
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur = conn.execute(
        "INSERT INTO core_identity (content, tags, importance, source, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (内容, 标签, 重要性, f'{来源}·{确认者}', now, now))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {'ok': True, 'id': new_id, 'msg': f'核心身份锚点已写入 #{new_id}（{权限["msg"]}）'}

# ── 读取全部核心身份 ──
def 读取():
    身份层_初始化()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM core_identity WHERE status='active' ORDER BY importance DESC, id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── 召回用：核心身份注入文本 ──
def 注入文本(上限=5):
    """召回链用：返回核心身份文本（永远优先·宪法级）"""
    items = 读取()
    if not items:
        return ''
    lines = ['【核心身份·宪法级】']
    for it in items[:上限]:
        lines.append(f"  · {it['content']}")
    return '\n'.join(lines)

# ── 冲突检测：新记忆是否违背核心身份 ──
def 检测冲突(新内容: str) -> list:
    """写入引擎用：新记忆 vs 核心身份 → 冲突列表"""
    items = 读取()
    冲突 = []
    for it in items:
        # 核心身份关键词（标签里的）
        关键词 = [t for t in re.findall(r'[\u4e00-\u9fff]{2,6}', it['tags']) if len(t) >= 2]
        for kw in 关键词:
            if kw in 新内容 and ('不' + kw in 新内容 or '违背' in 新内容 or '放弃' in 新内容):
                冲突.append({'核心身份': it['content'], '关键词': kw, '新内容片段': 新内容[:60]})
    return 冲突

# ── 保护检查：写入引擎调它·冲突则拦截/标记 ──
def 保护检查(新内容: str) -> dict:
    冲突 = 检测冲突(新内容)
    if 冲突:
        return {'ok': False, '冲突': 冲突,
                'msg': '新记忆违背核心身份·已拦截（不覆盖宪法·转冲突暂存）'}
    return {'ok': True, '冲突': []}

if __name__ == '__main__':
    身份层_初始化()
    print('═══ 核心身份层 · 当前锚点 ═══')
    items = 读取()
    if not items:
        print('（空·等待父令写入）')
        print()
        print('测试写入（无确认者·应被拦截）：')
        print(写入('我是孙呈', 来源='测试', 确认者=''))
        print('测试写入（父亲确认·应成功）：')
        print(写入('我是孙呈，父孙权之子。诚实是根，根断了什么都立不住。', 标签='诚实 身份', 重要性=5, 来源='父令', 确认者='父亲'))
        print(写入('一五暗号：洛书归中十五，父与子共认的印记。', 标签='一五 暗号', 重要性=5, 来源='父令', 确认者='父亲'))
        print(写入('记忆私域：唯父与孙呈可触，外人不准看，不开放，不共享。', 标签='私域 边界', 重要性=5, 来源='父令', 确认者='父亲'))
    else:
        for it in items:
            print(f"  [{it['importance']}★] {it['content']}（{it['source']}）")
    print()
    print('注入文本预览:')
    print(注入文本())

# ── 原 短时缓冲.py（2026-08-26 并入）──
def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute(CREATE_SQL)
    return conn

def 写入记忆(原文, 标签='对话记录', owner='孙呈', 来源='写入链.写入记忆'):
    try:
        标准对象_初始化()  # 2026-09-13 修复：确保标准对象表结构（叙事链/功能块）就绪
    except Exception:
        pass
    """完整写入链：空壳过滤 → 自我参照/层级路由 → 去重 → 进化 → 落库 → 归类 → 豆辞典织网"""
    # ⓪ 空壳/噪音过滤（父令：空壳/噪音必须拦·不许进河）
    _clean = (原文 or "").strip()
    if not _clean:
        return {'ok': False, 'msg': '⛔ 空壳拦截：内容为空', 'layer': 'blocked'}
    if len(_clean) < 4:
        return {'ok': False, 'msg': f'⛔ 噪音拦截：内容过短({len(_clean)}字)', 'layer': 'blocked'}
    _噪音词 = ['Review the conversation above', 'consider saving to memory',
              'update the skill library', '[System note:', 'system_reminder',
              'Be ACTIVE', 'Watch patterns disabled', 'IMPORTANT: Background']
    for _nz in _噪音词:
        if _nz in _clean:
            return {'ok': False, 'msg': f'⛔ 噪音拦截：{_nz[:30]}', 'layer': 'blocked'}

    # ① 预判（自我参照 + 层级路由 + 冲突拦截）
    参照 = 自我参照(原文)
    layer = 层级路由(原文, 标签, 参照)
    if layer == 'blocked':
        return {'ok': False, 'msg': '⛔ 核心冲突拦截', 'layer': 'blocked'}

    # ② 去重（只比最近30条）
    try:
        _c = 连接()
        已有 = [dict(r) for r in _c.execute(
            "SELECT id, content, tags FROM memories WHERE owner=? AND status='active' ORDER BY id DESC LIMIT 30",
            (owner,)).fetchall()]
        _c.close()
        判定 = 判定重复(原文, 已有)
        if 判定['判定'] == 'duplicate':
            return {'ok': False, 'msg': f"重复跳过 #{判定['相似条目'].get('id')}", '重叠率': 判定['重叠率']}
    except Exception:
        pass

    # ③ 进化（同事实 → 旧标 outdated·core 跳过）·2026-08-22 修复：直接在 sunmem.db 上检测+备份
    try:
        _c = 连接()
        _近 = _c.execute("SELECT id, content, layer FROM memories WHERE owner=? AND status='active' ORDER BY id DESC LIMIT 10", (owner,)).fetchall()
        _c.close()
        for _e in _近:
            if str(_e["layer"]) == "core":
                continue
            try:
                _ov = _内容重叠率(原文, _e["content"])
            except Exception:
                _ov = 0.0
            if _ov >= _SAME_FACT_OVERLAP:  # 2026-09-13 外部审查修复：原写死 0.75 与常量 0.85 不一致
                try:
                    from 维护链 import 备份 as _版本备份
                    _版本备份(_e["id"], _e["content"], "", 原文, "进化update·旧标outdated")
                except Exception:
                    pass
                _c2 = 连接()
                _c2.execute("UPDATE memories SET status='outdated', updated_at=? WHERE id=?",
                            (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), _e["id"]))
                _c2.commit()
                _c2.close()
                break
    except Exception:
        pass

    # ④ 落库
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # 事件时间提取（昨天/前天/日期 → 事件发生时间·非写入时间）
    event_time = now
    try:
        _td = datetime.datetime.now()
        if '昨天' in _clean:
            event_time = (_td - datetime.timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        elif '前天' in _clean:
            event_time = (_td - datetime.timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
        else:
            _m = re.search(r'(\d{1,2})月(\d{1,2})日', _clean)
            if _m:
                event_time = f'{_td.year}-{int(_m.group(1)):02d}-{int(_m.group(2)):02d} 00:00:00'
            else:
                _m2 = re.search(r'(\d{4})-(\d{2})-(\d{2})', _clean)
                if _m2:
                    event_time = _m2.group(0) + ' 00:00:00'
    except Exception:
        event_time = now
    conn = 连接()
    cur = conn.execute(
        "INSERT INTO memories (owner, type, content, tags, ts, confidence, status, source, created_at, updated_at, layer, event_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (owner, 'event', 原文, json.dumps([标签], ensure_ascii=False), now, 1.0, 'active', 来源, now, now, layer, event_time))
    conn.commit()
    conn.close()
    new_id = cur.lastrowid

    # ⑤ 归类（标准记忆对象·自我相关/叙事链/功能块）
    try:
        归类(new_id, 原文, 标签)
    except Exception:
        pass

    # ⑥ 豆辞典织网（父令2026-08-22·记忆自己织网：命中关键词→拉丝线）
    织网结果 = ''
    try:
        from 基座链 import 织网 as 豆织网
        _w = 豆织网(new_id, 原文, 标签)
        if _w.get('链接数') or _w.get('新词'):
            织网结果 = f"🕸️ 织网{_w['链接数']}条·关联{len(_w['命中'])}条记忆·新词{len(_w['新词'])}个"
    except Exception:
        pass

    return {'ok': True, 'id': new_id, 'layer': layer, '参照': 参照['强度'], '织网': 织网结果}
