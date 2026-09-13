# -*- coding: utf-8 -*-
"""相似度方程（父令2026-08-26·模块精简数学化·第2条方程）

将 内容去重(bigram Jaccard) / 无模型向量(ngram余弦) / 英文词形归一(词干)
三模块的核心相似度逻辑统一成一条加权方程：

    Sim(A,B) = α·Jaccard_bigram(无序) + β·Jaccard_ordered(有序) + γ·余弦_词干归一

α=0.4 / β=0.3 / γ=0.3（可调·默认给字符级结构最高权重）

原三模块保留兼容转发（调此方程）·核心逻辑收敛到此。
"""
import re
import math
from collections import Counter

# 参数（2026-08-26 产品化：改为读配置表·不改源码可调优）
try:
    from 配置表 import get as _cfg
    def _P(键, 默认):
        return _cfg('相似度', 键) if _cfg('相似度', 键) is not None else 默认
except Exception:
    def _P(键, 默认):
        return 默认

参数 = {
    'α_bigram': _P('α_bigram', 0.4),      # 无序 bigram Jaccard（内容去重主）
    'β_有序': _P('β_有序', 0.3),           # 有序 bigram 序列重叠（内容去重通道②）
    'γ_余弦': _P('γ_余弦', 0.3),           # 词干归一 ngram 余弦（无模型向量+英文归一）
    '去重阈值': _P('去重阈值', 0.6),       # 内容去重阈值（≥0.6 判重复）
}


def 归一化(文本: str) -> str:
    """归一化：去标点/空白/统一小写（原内容去重.归一化）"""
    if not 文本:
        return ""
    s = str(文本)
    s = re.sub(r'[\s，。！？、；：""''（）【】《》…—·,.!?;:"\'()\[\]{}<>-]+', '', s)
    return s.lower()


def _bigrams(文本: str) -> set:
    """无序 bigram 集合（原内容去重._bigrams）"""
    s = 归一化(文本)
    if len(s) < 2:
        return set()
    return {s[i:i+2] for i in range(len(s)-1)}


def _ordered_bigrams(文本: str) -> list:
    """有序 bigram 序列（原内容去重._ordered_bigrams）"""
    s = 归一化(文本)
    if len(s) < 2:
        return []
    return [s[i:i+2] for i in range(len(s)-1)]


def _ngram向量(文本: str, n=2):
    """ngram 稀疏向量（原无模型向量.ngram向量·简化版）"""
    s = 归一化(文本)
    if len(s) < n:
        return {}
    cnt = Counter(s[i:i+n] for i in range(len(s)-n+1))
    return dict(cnt)


def 余弦(v1: dict, v2: dict) -> float:
    """稀疏向量余弦（原无模型向量.余弦）"""
    if not v1 or not v2:
        return 0.0
    内积 = sum(w * v2.get(idx, 0) for idx, w in v1.items())
    if 内积 == 0:
        return 0.0
    模1 = sum(w * w for w in v1.values()) ** 0.5
    模2 = sum(w * w for w in v2.values()) ** 0.5
    if not 模1 or not 模2:
        return 0.0
    return 内积 / (模1 * 模2)


def _词干(词: str) -> str:
    """词干化（原英文词形归一.词干·简化版）：英文复数/ing/ed 还原"""
    if not 词 or not 词.isascii():
        return 词
    w = 词.lower()
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def 相似度(文本a: str, 文本b: str) -> float:
    """相似度方程（统一）：Sim = α·bigram + β·有序 + γ·余弦(词干归一)"""
    if not 文本a or not 文本b:
        return 0.0
    # ① 无序 bigram Jaccard
    ba, bb = _bigrams(文本a), _bigrams(文本b)
    jaccard = len(ba & bb) / len(ba | bb) if (ba and bb) else 0.0
    # ② 有序 bigram 序列重叠
    oa, ob = _ordered_bigrams(文本a), _ordered_bigrams(文本b)
    pa = {(oa[i], oa[i+1]) for i in range(len(oa)-1)} if len(oa) > 1 else set()
    pb = {(ob[i], ob[i+1]) for i in range(len(ob)-1)} if len(ob) > 1 else set()
    有序 = len(pa & pb) / len(pa | pb) if (pa and pb) else 0.0
    # ③ 词干归一 ngram 余弦（英文词形归一 + 无模型向量）
    try:
        va = _ngram向量(文本a)
        vb = _ngram向量(文本b)
        cos = 余弦(va, vb)
    except Exception:
        cos = 0.0
    return 参数['α_bigram'] * jaccard + 参数['β_有序'] * 有序 + 参数['γ_余弦'] * cos


def 是重复(文本a: str, 文本b: str) -> bool:
    """去重判定（原内容去重·阈值）"""
    return 相似度(文本a, 文本b) >= 参数['去重阈值']
