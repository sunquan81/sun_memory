# -*- coding: utf-8 -*-
"""
使用中增强·Hebbian（2026-08-27 父令：让网自己长·补种子后接入）
================================================================
父训：语义边跟着记忆的流自然生长——不是手补。
机制（接感应器扰动）：
  ① 感应器发波 → 一批节点同时被点亮
  ② 一起被点亮的节点之间 → 丝线权重 +Δ（Hebbian共激活）
  ③ 长期不一起亮的边 → 缓慢衰减（λ遗忘）
  ④ 权重上限1.0（防膨胀）·下限0.05（线不断·只是细）

这就是"一起被想起的边变粗"——网自己长。
"""
import json, os, shutil, time

try:
    from 线程保护 import 加锁  # 2026-09-14 吸收收束版优点：全局状态线程保护
except Exception:
    import threading as _th_mod
    _th_lock = _th_mod.RLock()
    def 加锁(): return _th_lock

from datetime import datetime
from collections import defaultdict

SPIDER = os.environ.get('蜘蛛网_INDEX', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '蜘蛛网', '索引.json'))

# ── 参数（父令口径·保守小步）──
增强Δ = 0.06          # 一起点亮·边+0.06（上限1.0）
遗忘λ = 0.02          # 每次被"想起但没一起亮"的边·衰减2%
上限 = 1.0            # 权重封顶
下限 = 0.05           # 线不断·只是细

# ── 2026-08-28 修复：批写缓存（原每次感应整文件读写蜘蛛网·6MB json.load/dump 成延迟+损坏风险）
# 策略同蜘蛛网索引._拉边累积：内存累加边Δ·每 20 次写盘一次
_缓存网 = None        # 内存缓存：读一次·改内存·攒批落盘
_脏累积 = 0           # 攒批计数
_批写阈值 = 20


def _读网():
    global _缓存网
    with 加锁():
        if _缓存网 is None:
            _缓存网 = json.load(open(SPIDER, encoding='utf-8-sig'))
        return _缓存网


def _写网():
    """原子写盘（临时文件 + os.replace）"""
    global _缓存网
    if _缓存网 is None:
        return
    tmp = SPIDER + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(_缓存网, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SPIDER)


def _落盘(立即=False):
    """攒批落盘：每 _批写阈值 次写一次·立即=True 强制写"""
    global _脏累积
    if 立即 or _脏累积 >= _批写阈值:
        _写网()
        _脏累积 = 0


def 增强一批(点亮的节点集):
    """一起被点亮的节点·两两之间的边变粗（Hebbian）"""
    global _脏累积
    if len(点亮的节点集) < 2:
        return 0
    d = _读网()
    丝线 = d['丝线']
    # 建索引 (源,目标) -> 边列表（2026-08-27 修复：同边对多关系不覆盖·全部增强）
    边索引 = defaultdict(list)
    for l in 丝线:
        边索引[(l['源'], l['目标'])].append(l)
        边索引[(l['目标'], l['源'])].append(l)
    增次数 = 0
    节点列表 = list(点亮的节点集)
    for i in range(len(节点列表)):
        for j in range(i+1, len(节点列表)):
            a, b = 节点列表[i], 节点列表[j]
            # 有边 → 增强；无边 → 跳过（不新建·避免噪音边）
            for l in 边索引.get((a, b), []):
                if l.get('关系') not in ('关联', '父子', '同义', '因果', '共现'):
                    continue
                w = l.get('权重', 0.6)
                l['权重'] = min(上限, w + 增强Δ)
                l['次数'] = l.get('次数', 1) + 1
                l['最后增强'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                增次数 += 1
    if 增次数:
        _脏累积 += 1
        _落盘()  # 攒批：每20次才真写盘（原每次整文件json.dump）
    return 增次数


def 遗忘一批(活跃节点集, 全部节点):
    """被想起但没一起亮的边·轻微衰减（网络弛豫·不用的边慢慢细）"""
    global _脏累积
    d = _读网()
    丝线 = d['丝线']
    活跃 = set(活跃节点集)
    遗忘次数 = 0
    for l in 丝线:
        if l['源'] in 活跃 and l['目标'] in 活跃:
            continue  # 一起亮的·不衰减
        if l.get('关系') not in ('关联', '父子', '同义', '因果'):
            continue  # 只衰减语义边·共现不动
        w = l.get('权重', 0.6)
        if w > 下限:
            l['权重'] = max(下限, w * (1 - 遗忘λ))
            遗忘次数 += 1
    if 遗忘次数:
        _脏累积 += 1
        _落盘()  # 攒批：每20次才真写盘
    return 遗忘次数


if __name__ == '__main__':
    # 验证：模拟一次"配分函数"扰动·点亮的节点一起增强
    print("═══ 使用中增强·验证 ═══")
    # 读当前权重
    d = json.load(open(SPIDER, encoding='utf-8-sig'))
    for l in d['丝线']:
        if l['源'] == '配分函数' and l['目标'] == '统计力学':
            print(f"增强前: 配分函数--{l['关系']}-->统计力学 权重={l.get('权重')} 次数={l.get('次数')}")
            break
    # 模拟一次扰动：配分函数/统计力学/玻尔兹曼分布/自由能一起被点亮
    点亮 = {'配分函数', '统计力学', '玻尔兹曼分布', '自由能', '温度'}
    n = 增强一批(点亮)
    print(f"✅ 一起点亮的边增强: {n}条")
    d = json.load(open(SPIDER, encoding='utf-8-sig'))
    for l in d['丝线']:
        if l['源'] == '配分函数' and l['目标'] == '统计力学':
            print(f"增强后: 配分函数--{l['关系']}-->统计力学 权重={l.get('权重')} 次数={l.get('次数')}")
            break
