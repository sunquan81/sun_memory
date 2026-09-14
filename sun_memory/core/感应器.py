# -*- coding: utf-8 -*-
"""
感应器 · 全网扰动（2026-08-27 父令：活记忆·管线-感应器-大网）
================================================================
V3正式版（V1全拉噪音/V2字面匹配/V3概念链路+网自己长·最终版）

机制：
  ① 感应器发波：念头概念 → 信号沿蜘蛛网【语义边】（父子/同义/因果/关联）
     传导·共现边只从源头1跳（防边角料）·每跳×关系强度×距离衰减
  ② 按关联拉：无关联节点不进入思考（v2闸门保留）·碎片/数字/英文不进
  ③ 中心汇聚：夏维斯收到全网回流（所有线都通到中心）
  ④ 使用中增强（Hebbian）：一起被点亮的节点·边当场变粗（网自己长）
     遗忘：长期不一起亮的语义边×0.98缓慢变细（弛豫）

接口：
  感应器(念头概念, 深度=4) -> {节点: 波能}
"""
import json, os, re, sys
from collections import defaultdict

# ── 路径（可被SUNMEM_DB隔离的蜘蛛网用环境变量）──
SPIDER = os.environ.get('蜘蛛网_INDEX', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '蜘蛛网', '索引.json'))

# 关系强度（语义边>共现边·概念链路靠它传导）
REL_STRENGTH = {'父子': 1.0, '同义': 0.9, '因果': 0.85, '关联': 0.6, '共现': 0.15}
# 概念链路只走语义边·共现边只从源头1跳
语义边 = {'父子', '同义', '因果', '关联'}


def _是噪音(名称):
    if not 名称 or len(名称) < 2:
        return True
    if re.fullmatch(r'\d+', 名称):
        return True
    if re.fullmatch(r'[a-zA-Z]{1,3}', 名称):
        return True
    if re.fullmatch(r'[\u4e00-\u9fff]{1}', 名称):
        return True
    # 2026-08-27 修：词碎片过滤——中文双字若被更强概念包含且自身无描述·是切碎残留
    # （"函数"是"配分函数"的碎片·但"API/Code/Hermes"是独立概念·不误伤）
    return False


# 2026-08-27 修：词碎片判定——某节点是另一节点的子串·且波能低（碎片没自己的概念分量）
def _压碎片(响应, 念头概念):
    """压掉被念头包含的碎片节点：'配分函数'的碎片'函数/分函'不该汹涌"""
    if 念头概念 not in 响应:
        return 响应
    源波能 = 响应[念头概念]
    for n in list(响应.keys()):
        if n == 念头概念 or n == '夏维斯':
            continue
        # n 是念头的子串（碎片）或念头是 n 的子串（更细粒度）
        if n in 念头概念 and len(n) < len(念头概念):
            # 碎片：压到浸润以下（它只是念头的字面切片·不是独立概念）
            响应[n] = min(响应[n], 0.05)
        elif 念头概念 in n and len(n) > len(念头概念):
            pass  # 更完整的节点（配分函数统计力学）保留·是更强的
        elif re.fullmatch(r'[a-zA-Z]+', n) and len(n) <= 8:
            # 纯英文短词·若念头是中文·它是无关残留（除非是独立术语如API/SunFlow）
            if not (n[0].isupper() and 念头概念 not in n):
                响应[n] = min(响应[n], 0.05)
    return 响应


def _时间阻尼(创建时间):
    try:
        from datetime import datetime
        t0 = datetime.strptime(创建时间[:10], '%Y-%m-%d')
        t1 = datetime.now()  # 2026-08-27 修复：原硬编码'2026-08-27'→now（否则老节点被永久压制）
        days = (t1 - t0).days
    except Exception:
        days = 0
    return 1.0 / (1.0 + days / 365.0)


_网缓存 = {'数据': None, 'adj': None, '时间': 0}  # 2026-09-14 外部审查修复：进程内 5 秒缓存


def _加载网():
    """加载蜘蛛网 + 邻接表（2026-09-14 修复：原每次调用都读 1.1MB JSON + 重建 34845 边邻接表·
    _回写heat 与主流程各调一次 = 每次感应两遍重活）"""
    import time as _t
    if _网缓存['数据'] is not None and _t.time() - _网缓存['时间'] < 5:
        return _网缓存['数据'], _网缓存['adj']
    d = json.load(open(SPIDER, encoding='utf-8-sig'))
    adj = defaultdict(list)
    for l in d['丝线']:
        adj[l['源']].append((l['目标'], l.get('关系', '关联')))
        adj[l['目标']].append((l['源'], l.get('关系', '关联')))
    _网缓存['数据'], _网缓存['adj'], _网缓存['时间'] = d, adj, _t.time()
    return d, adj


def _回写heat(响应, 阈值=0.5, 上限概念=3, 上限记忆=10):
    """2026-08-28 修复：波能回写 heat（方案·网在响条不热——概念波能带动记忆条 heat）
    只对真正汹涌的强概念（波能≥0.5）·限 top 概念·反查段落节点找记忆·调节律.点亮
    """
    强概念 = [n for n, e in 响应.items() if e >= 阈值 and n != '夏维斯'][:上限概念]
    if not 强概念:
        return 0
    try:
        d = _加载网()[0]
        段落 = d.get('段落', {})
    except Exception:
        return 0
    if not 段落:
        return 0
    命中 = []
    for 概念 in 强概念:
        for pid, p in 段落.items():
            if 概念 in p.get('概念', []):
                try:
                    命中.append(int(pid))
                except Exception:
                    pass
    if not 命中:
        return 0
    # 去重保序·限上限
    命中 = list(dict.fromkeys(命中))[:上限记忆]
    try:
        from 节律 import 点亮 as _节律点亮
        for mid in 命中:
            _节律点亮(mid)
    except Exception:
        pass
    return len(命中)


def 感应器(念头概念, 深度=4, 中心='夏维斯'):
    """
    感应器·全网扰动（V3）：
      发波 → 语义边概念链路传导 → 按关联拉 → 中心汇聚 → 使用中增强
    返回 {节点: 波能} —— 强关联汹涌·弱关联浸润·无关联不进
    """
    try:
        d, adj = _加载网()
    except Exception:
        return {}
    nodes = d['节点']

    if 念头概念 not in adj:
        命中 = [n for n in nodes if 念头概念 in n or n in 念头概念]
        if not 命中:
            return {}
        念头概念 = 命中[0]

    # ── 扰动波沿【语义边】传导（概念链路）──
    链路波能 = defaultdict(float)
    链路波能[念头概念] = 1.0
    当前层 = {念头概念: 1.0}
    visited = {念头概念}
    for 跳 in range(1, 深度+1):
        下一层 = defaultdict(float)
        for 节点, 能 in 当前层.items():
            for 邻居, 关系 in adj.get(节点, []):
                if 邻居 == 中心:
                    continue
                if 邻居 in visited and 跳 > 1:
                    continue
                s = REL_STRENGTH.get(关系, 0.15)
                # 共现边只从源头1跳·不参与深层链路
                if 关系 not in 语义边 and 节点 != 念头概念:
                    continue
                传导 = 能 * s * (0.5 ** (跳-1))
                下一层[邻居] += 传导
                visited.add(邻居)
        for n, e in 下一层.items():
            链路波能[n] += e
        当前层 = 下一层

    # ── 响应筛选：非噪音·非中心→直接进入（波能已含关系强度）──
    响应 = {}
    for n, e in 链路波能.items():
        if n == 中心:
            响应[n] = e * 1.0
            continue
        if _是噪音(n):
            continue
        if n == 念头概念:
            响应[n] = e
            continue
        响应[n] = e

    # 时间阻尼：老节点波能被压制（但>0·线不断）
    for n in 响应:
        if n in nodes and isinstance(nodes[n], dict):
            响应[n] *= _时间阻尼(nodes[n].get('创建', ''))

    # 2026-08-27 修：压词碎片（"配分函数"的碎片"函数/分函"不该汹涌）
    响应 = _压碎片(响应, 念头概念)

    # 中心感应器：全网回流
    响应[中心] = sum(响应.values()) * 0.5

    # ── 使用中增强（Hebbian）：一起被点亮·边当场变粗（网自己长）──
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from 使用中增强 import 增强一批
        增强一批(set(响应.keys()))
    except Exception:
        pass

    # ── 2026-08-28 修复：波能回写 heat（网在响·条不热 → 强概念带动记忆条 heat）──
    try:
        _回写heat(响应)
    except Exception:
        pass

    return 响应


if __name__ == '__main__':
    import sys
    for 念头 in ['配分函数', '苏醒循环', '孙博']:
        r = 感应器(念头)
        items = sorted(r.items(), key=lambda x: -x[1])
        print(f"\n═══ 感应器「{念头}」═══")
        for n, e in items[:10]:
            print(f"  {n} ({round(e,3)})")
        print(f"  ...共{len(r)}个")
