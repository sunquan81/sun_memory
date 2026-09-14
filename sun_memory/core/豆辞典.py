# -*- coding: utf-8 -*-
"""豆辞典自动超链接 v2（父令2026-08-22：记忆自己织网·动态网络）
对标 nocturne_memory 的 Glossary Auto-Hyperlinking：
  关键词绑定记忆节点 → 新记忆写入时自动检出关键词 → 建跨节点链接
  → 写得越多·关联自动越密·记忆网络自己织网

v2 架构修正（2026-08-22 整体考虑后）：
  ⚠️ v1 把"记忆#id"塞进蜘蛛网概念网 → 污染概念节点·联想召回/星空会碰到垃圾
  ✅ v2 记忆↔记忆链接【独立存储】（豆辞典.json 自己管）·蜘蛛网只存概念不动
  三层：
    ① 词典（关键词 → [记忆id]）——关键词注册表
    ② 链接（记忆id → {关联记忆id列表}）——记忆自己织的网（双向）
    ③ 召回（联想时用链接跳转）——从一条记忆跳相关记忆

零依赖·纯规则·原子写
"""
import json
import os
import re
import sqlite3
from collections import Counter

# 豆辞典路径（词典+链接一体·JSON 持久化）
GLOSSARY_PATH = os.environ.get('豆辞典路径', os.path.join(os.path.dirname(os.path.abspath(__file__)), '豆辞典.json'))

# 虚词切分（'记忆压缩的概念' → ['记忆压缩','概念']）
_虚词正则 = re.compile(
    r"[的了在把给让用讲帮请是对就都还也且或和与及一个一样怎么怎样如何什么为什么啥哪个"
    r"是不是应该可以就是用来驱动今天天气很好一片：，。、·\s]+"
)


# ── 关键词提取（虚词切分·完整概念词优先）──
def _提关键词(文本: str, 上限: int = 8) -> list:
    t = str(文本)
    segs = _虚词正则.split(t)
    cand = Counter()
    for seg in segs:
        seg = re.sub(r"[^\u4e00-\u9fff0-9a-zA-Z]", "", seg)
        if len(seg) < 2:
            continue
        # 2026-08-25 修复：英文报错残片/纯数字不是关键词（poll/erro/2026/0260 曾污染词典）
        if re.fullmatch(r"[a-zA-Z0-9._-]+", seg):
            if re.fullmatch(r"[0-9]+", seg):
                continue
            if len(seg) < 6 and not re.search(r"[A-Z]", seg):
                continue
        if len(seg) <= 4:
            cand[seg] += 1
        elif re.fullmatch(r"[a-zA-Z0-9._-]+", seg):
            cand[seg] += 1  # 2026-08-25 修复：英文专名整词保留（SunFlow/FreeToken 不拆 4-gram）
        else:
            for i in range(len(seg) - 3):
                cand[seg[i:i + 4]] += 1
    picked = []
    for w, _ in sorted(cand.items(), key=lambda x: (-len(x[0]), -x[1])):
        if any(w == p or w in p or p in w for p in picked):
            continue
        picked.append(w)
        if len(picked) >= 上限:
            break
    return picked


def _读() -> dict:
    """读词典+链接（原子·异常回退空结构）"""
    try:
        with open(GLOSSARY_PATH, encoding='utf-8') as f:
            d = json.load(f)
        d.setdefault("词典", {})
        d.setdefault("链接", {})
        return d
    except Exception:
        return {"词典": {}, "链接": {}}


def _存(d: dict):
    tmp = GLOSSARY_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, GLOSSARY_PATH)


def _读记忆内容(记忆id: int) -> str:
    """从 sunmem.db 读记忆内容（织网时需要内容·但调用方已传入时跳过）"""
    try:
        conn = sqlite3.connect(os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db')))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT content FROM memories WHERE id=?", (记忆id,)).fetchone()
        conn.close()
        return row['content'] if row else ""
    except Exception:
        return ""


def 织网(记忆id: int, 内容: str = "", 标签: str = "") -> dict:
    """新记忆写入时自动织网：
    ① 内容里的关键词命中词典 → 建 记忆id ↔ 关联记忆 双向链接
    ② 新关键词注册进词典（挂当前记忆）
    返回 {"命中": [关联记忆id], "新词": [新注册关键词], "链接数": N}
    """
    全文 = str(内容 or "") + str(标签 or "")
    关键词 = _提关键词(全文, 上限=10)
    if not 关键词:
        return {"命中": [], "新词": [], "链接数": 0}

    d = _读()
    词典, 链接 = d["词典"], d["链接"]

    # ① 命中已有词典关键词 → 建双向链接
    命中 = []
    for w in 关键词:
        if w in 词典:
            for mid in 词典[w][-8:]:
                if mid != 记忆id and mid not in 命中:
                    命中.append(mid)
    # 双向链接（当前记忆 ↔ 关联记忆）
    if 命中:
        链接.setdefault(str(记忆id), [])
        for mid in 命中:
            if mid not in 链接[str(记忆id)]:
                链接[str(记忆id)].append(mid)
            # 反向
            链接.setdefault(str(mid), [])
            if 记忆id not in 链接[str(mid)]:
                链接[str(mid)].append(记忆id)
        # 每节点链接上限（防膨胀）
        for k in 链接:
            if len(链接[k]) > 30:
                链接[k] = 链接[k][-30:]

    # ② 新关键词注册（挂当前记忆）
    新词 = []
    for w in 关键词:
        if w not in 词典:
            词典[w] = [记忆id]
            新词.append(w)
        elif 记忆id not in 词典[w]:
            词典[w].append(记忆id)
            词典[w] = 词典[w][-20:]

    _存(d)
    return {"命中": 命中, "新词": 新词, "链接数": len(命中)}


def 联想(记忆id: int, 深度: int = 2, 上限: int = 5) -> list:
    """从一条记忆出发·沿链接跳相关记忆（记忆网络的流动）
    深度1：直接关联；深度2：关联的关联（多跳·像联想）"""
    d = _读()
    链接 = d.get("链接", {})
    seen = set()
    frontier = [记忆id]
    for _ in range(深度):
        nxt = []
        for cur in frontier:
            for nid in 链接.get(str(cur), []):
                if nid not in seen and nid != 记忆id:
                    seen.add(nid)
                    nxt.append(nid)
        frontier = nxt
    return list(seen)[:上限]


def 状态() -> dict:
    d = _读()
    return {
        "词典词数": len(d["词典"]),
        "记忆节点数": len(d["链接"]),
        "链接数": sum(len(v) for v in d["链接"].values()),
    }


if __name__ == "__main__":
    print("═══ 豆辞典 v2 自测（独立链接·不碰蜘蛛网）═══")
    print("关键词:", _提关键词("记忆压缩的概念·按需展开", 6))
    r1 = 织网(5000, "记忆压缩的核心是存规则不存原文", "记忆压缩")
    print("织网1:", "新词", len(r1["新词"]), "命中", r1["命中"])
    r2 = 织网(5001, "今天研究记忆压缩的规则链", "压缩")
    print("织网2:", "命中", r2["命中"], "链接数", r2["链接数"])
    print("联想(5001,深度2):", 联想(5001, 2))
    print("状态:", 状态())
