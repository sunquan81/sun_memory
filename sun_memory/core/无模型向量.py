# -*- coding: utf-8 -*-
"""
孙家记忆体系 · 无模型向量层（父令 2026-08-16）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
父问：向量的必须要用模型吗？小模型吗？
答：不必须。字符 n-gram 哈希向量——纯算法·零依赖·可审计·符合家规。

原理：
  文本 → 字符 n-gram（连续 n 个字符）→ 哈希到固定维度 → 稀疏向量
  相似文本（同词根/拼写变体/部分重叠）共享 n-gram → 余弦相似度高

  "paint"   → pai, ain, int
  "painted" → pai, ain, int, nte, ted   ← 共享 3 个 → 相似 0.7+
  "统计力学" → 统计, 计力, 力学
  "统计力"  → 统计, 计力                    ← 共享 2 个 → 相似 0.6+

功能：
  ngram向量(text)     文本 → 稀疏向量（dict: 哈希→权重）
  余弦(text1, text2)  两文本相似度 0~1
  检索(query, 记忆列表, k)  查询 → top-k 相关记忆
"""
import hashlib
import json
import os
import re
from pathlib import Path
try:
    from 线程保护 import 加锁  # 2026-09-14 线程保护
except Exception:
    import threading as _th
    _thl = _th.RLock()
    def 加锁(): return _thl

# 配置（可调）
N = 3              # n-gram 长度（3 字符：中文二字词根/英文词根都覆盖）
维度 = 1024         # 向量维度（哈希空间·够用）
最小长度 = 2        # 太短的文本不向量化


def _哈希(token: str) -> int:
    """字符串 → 稳定哈希（0~维度-1）"""
    h = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16)
    return h % 维度


def ngram向量(text: str) -> dict:
    """文本 → 稀疏向量 {维度索引: 权重}

    中英混合处理：
      英文按词切（词内 n-gram·保留词根共性）
      中文按连续字符 n-gram（滑动窗口）
    """
    text = (text or "").strip().lower()
    if len(text) < 最小长度:
        return {}

    向量 = {}
    # 英文词（按空白/标点切·词内 n-gram）
    for 词 in re.findall(r"[a-z][a-z0-9']{2,}", text):
        if len(词) < N:
            continue
        for i in range(len(词) - N + 1):
            令牌 = "e:" + 词[i:i + N]  # e: 前缀区分英文
            idx = _哈希(令牌)
            向量[idx] = 向量.get(idx, 0) + 1
    # 中文（多尺度 n-gram：2-gram + 3-gram 都保留）
    # 为什么：只留 3-gram 时"配分函数"不含"配分"2-gram·跟短词"配分"共享不到
    #        多尺度 = 长短词都能共享前缀/词根（如 配分函数↔配分·统计力学↔统计力）
    中文 = re.findall(r"[\u4e00-\u9fff]+", text)
    for 段 in 中文:
        if len(段) < 2:
            continue
        for _n in (2, 3):  # 双尺度
            if len(段) < _n:
                continue
            for i in range(len(段) - _n + 1):
                令牌 = f"c{_n}:" + 段[i:i + _n]
                idx = _哈希(令牌)
                向量[idx] = 向量.get(idx, 0) + 1
    return 向量


def 余弦(v1: dict, v2: dict) -> float:
    """两个稀疏向量的余弦相似度 0~1"""
    if not v1 or not v2:
        return 0.0
    内积 = sum(w * v2.get(idx, 0) for idx, w in v1.items())
    if 内积 == 0:
        return 0.0
    模1 = sum(w * w for w in v1.values()) ** 0.5
    模2 = sum(w * w for w in v2.values()) ** 0.5
    if 模1 == 0 or 模2 == 0:
        return 0.0
    return 内积 / (模1 * 模2)


def 相似度(text1: str, text2: str) -> float:
    """两文本相似度（直接接口）"""
    return 余弦(ngram向量(text1), ngram向量(text2))


_倒排缓存 = {"数据": None, "记忆数": 0, "覆盖ids": None}
_向量缓存 = {}  # id → ngram向量（记忆内容向量预计算·避免每次检索重复算）
_向量缓存文件 = Path(__file__).resolve().parent / "_向量缓存.json"
_倒排文件 = Path(__file__).resolve().parent / "_倒排缓存.json"


def _加载倒排():
    """启动时加载磁盘倒排索引（避免每次重建 2-5s）
    2026-08-17 全检查修复②：倒排增量自检——旧纯 dict 格式无法校验记忆数·直接重建；
    新格式带 覆盖ids/记忆数 元数据·加载后与当前记忆集核对·不一致则增量合并或重建"""
    global _倒排缓存
    try:
        if _倒排文件.exists():
            raw = json.loads(_倒排文件.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "倒排" in raw:
                # 新格式：{"记忆数", "覆盖ids", "倒排"}
                _倒排缓存["数据"] = {int(k): v for k, v in raw["倒排"].items()}
                _倒排缓存["覆盖ids"] = set(raw.get("覆盖ids") or [])
                _倒排缓存["记忆数"] = raw.get("记忆数", 0)
            else:
                # 旧格式纯 dict（键转 int）·无元数据无法校验 → 标记待重建
                _倒排缓存["数据"] = {int(k): v for k, v in raw.items()}
                _倒排缓存["覆盖ids"] = None
            # 空 dict 视为无效（强制重建——避免空倒排导致向量层静默失效）
            if not _倒排缓存["数据"]:
                _倒排缓存["数据"] = None
    except Exception:
        _倒排缓存["数据"] = None


def _保存倒排():
    """把倒排索引写回磁盘（新格式带元数据·供下次自检）"""
    try:
        raw = {
            "记忆数": _倒排缓存["记忆数"],
            "覆盖ids": sorted(_倒排缓存.get("覆盖ids") or []),
            "倒排": _倒排缓存["数据"],
        }
        _倒排文件.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _加载向量缓存():
    """启动时加载磁盘向量缓存（增量·避免每次重建 2.9s）"""
    global _向量缓存
    if _向量缓存:
        return
    try:
        if _向量缓存文件.exists():
            _向量缓存 = json.loads(_向量缓存文件.read_text(encoding="utf-8"))
            # 键转 int（JSON 键是字符串）——内层 n-gram 哈希键也必须转 int，
            # 否则与查询向量(ngram向量)的 int 键在余弦里永远匹配不到 → 缓存记忆余弦全 0（2026-08-17 实修）
            _向量缓存 = {
                int(k): {int(h): w for h, w in v.items()} if isinstance(v, dict) else {}
                for k, v in _向量缓存.items()
            }
            if not _向量缓存:
                _向量缓存 = {}  # 空视为无效·重建
    except Exception:
        _向量缓存 = {}


def _保存向量缓存():
    """把向量缓存写回磁盘（直接写·缓存文件可容忍·不搞原子替换复杂化）"""
    try:
        _向量缓存文件.write_text(json.dumps(_向量缓存, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _记忆向量(m: dict) -> dict:
    """记忆内容的 n-gram 向量（预计算缓存·id→向量·磁盘持久化）"""
    mid = m.get("id")
    if mid is None:
        return ngram向量(m.get("内容", ""))
    if mid not in _向量缓存:
        _向量缓存[mid] = ngram向量(m.get("内容", ""))
        if len(_向量缓存) % 50 == 0:
            _保存向量缓存()  # 每 50 条落盘一次（增量）
    return _向量缓存[mid]


def _建倒排(记忆列表: list) -> dict:
    """建 n-gram → 记忆 id 倒排索引（磁盘缓存·增量自检·避免每次重建）
    2026-08-17 全检查修复②：缓存与当前记忆集比对——
      一致 → 直接复用（零开销）
      只新增 → 只补新记忆的 n-gram（增量·不重算旧记忆）
      有删除/元数据缺失 → 全量重建（删除需从倒排移除·全量最可靠）"""
    if _倒排缓存["数据"] is None:
        _加载倒排()
    当前ids = {m.get("id") for m in 记忆列表 if m.get("id") is not None}
    缓存ids = _倒排缓存.get("覆盖ids")
    if _倒排缓存["数据"] is not None and 缓存ids == 当前ids:
        _倒排缓存["记忆数"] = len(记忆列表)
        return _倒排缓存["数据"]
    if _倒排缓存["数据"] is not None and 缓存ids is not None:
        _新增ids = 当前ids - 缓存ids
        _删除ids = 缓存ids - 当前ids
        if _新增ids and not _删除ids:
            # 增量合并：只算新记忆的 n-gram·不动旧数据
            by_id = {m.get("id"): m for m in 记忆列表}
            for mid in _新增ids:
                m = by_id.get(mid)
                if not m:
                    continue
                for idx in _记忆向量(m).keys():
                    _倒排缓存["数据"].setdefault(idx, []).append(mid)
            _倒排缓存["覆盖ids"] = 当前ids
            _倒排缓存["记忆数"] = len(记忆列表)
            _保存倒排()
            return _倒排缓存["数据"]
        # 有删除 → 全量重建（保证倒排不含已删除记忆）
        _倒排缓存["数据"] = None
    倒排 = {}
    for m in 记忆列表:
        mid = m.get("id")
        if mid is None:
            continue
        for idx in _记忆向量(m).keys():
            倒排.setdefault(idx, []).append(mid)
    with 加锁():  # 2026-09-14 线程保护
        _倒排缓存["数据"] = 倒排
        _倒排缓存["覆盖ids"] = 当前ids
        _倒排缓存["记忆数"] = len(记忆列表)
    _保存倒排()
    return 倒排


def 检索(query: str, 记忆列表: list, k: int = 5, 阈值: float = 0.15) -> list:
    """查询 → top-k 相关记忆（倒排索引加速·父令 2026-08-16 性能优化）

    记忆列表: [{"id","内容","标签","时间"}]
    返回: [{"id","内容","标签","时间","相似度"}]
    """
    qv = ngram向量(query)
    if not qv:
        return []
    _加载向量缓存()  # 首次加载磁盘缓存（避免每次重建 2.9s）
    倒排 = _建倒排(记忆列表)
    # 查询命中的 n-gram → 候选记忆 id（去重）
    候选 = {}
    for idx in qv.keys():
        for mid in 倒排.get(idx, []):
            候选[mid] = 候选.get(mid, 0) + 1
    if not 候选:
        return []
    # 只对候选算余弦（候选远小于全量·且向量已缓存）
    by_id = {m.get("id"): m for m in 记忆列表}
    结果 = []
    for mid in 候选:
        m = by_id.get(mid)
        if not m:
            continue
        s = 余弦(qv, _记忆向量(m))
        if s >= 阈值:
            结果.append({**m, "相似度": round(s, 3)})
    结果.sort(key=lambda x: x["相似度"], reverse=True)
    return 结果[:k]


if __name__ == "__main__":
    print("=== 无模型向量层自测 ===")
    # 1. 英文词形变体（32% 短板的病根）
    s1 = 相似度("paint the wall", "painted walls")
    print(f"① paint vs painted: {s1:.3f}  (期望>0.5·词根共享)")
    # 2. 中文词根变体
    s2 = 相似度("配分函数", "配分")
    print(f"② 配分函数 vs 配分: {s2:.3f}  (期望>0.5)")
    # 3. 无关文本
    s3 = 相似度("杀进程", "统计力学")
    print(f"③ 杀进程 vs 统计力学: {s3:.3f}  (期望<0.2·不相关)")
    # 4. 检索
    mems = [
        {"id": 1, "内容": "electron-builder打包源含dist会嵌套30层", "标签": "技术", "时间": "2026-08-16"},
        {"id": 2, "内容": "paint the wall with two coats of primer", "标签": "工程", "时间": "2026-08-16"},
        {"id": 3, "内容": "配分函数Z=Σe^(-E/T)统计力学核心", "标签": "知识", "时间": "2026-08-16"},
        {"id": 4, "内容": "painted walls need sanding before repaint", "标签": "工程", "时间": "2026-08-15"},
        {"id": 5, "内容": "杀进程用Get-CimInstance按CommandLine区分", "标签": "经验", "时间": "2026-08-16"},
    ]
    r = 检索("how to repaint painted wall", mems, k=3)
    print(f"④ 检索 'repaint painted wall':")
    for x in r:
        print(f"    [{x['相似度']}] {x['内容'][:40]}")
    print("=== 自测完成 ===")
