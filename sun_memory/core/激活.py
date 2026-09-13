# -*- coding: utf-8 -*-
"""激活方程 A · 统一入口（2026-08-28 收 A·阶段3第一步）
================================================================
父令：把 点亮(精确种子) + 感应器(全网传播) + 联想(概念提取) 合成一条线，
provider.prefetch 与 感知注入.inject 只调 activate()，不再各查各的。

本文件是第一步：统一入口 + 概念波能→记忆条映射。
后续第二步：provider/inject 迁移到 activate；第三步：联想/预感降级为种子/prior。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def activate(context, mode='turn', owner='孙呈', 预算=8):
    """激活唯一入口：种子 → 传播 → 激活集。

    返回 ActivationSet:
        {"记忆": [{id, 内容, 标签, 激活度, 来源}], "概念": {概念: 波能}}

    mode: turn=对话轮次 / think=思考中途 / wake=醒来
    """
    from 感应器 import 感应器 as _感应器, _加载网

    # ── 1. 感应器发波（全网扰动·概念链路）──
    概念波能 = {}
    try:
        概念波能 = _感应器(context[:20]) if context and len(context) >= 2 else {}
    except Exception:
        概念波能 = {}

    # ── 2. 点亮（精确命中·记忆条种子·layer=core 优先）──
    记忆激活 = {}  # id -> {内容, 标签, 激活度, 来源}
    try:
        from 点亮记忆 import 点亮 as _点亮
        点亮结果 = _点亮(context, owner)
        for h in 点亮结果.get("点亮记忆", []):
            mid = h.get("id")
            if mid is None:
                continue
            记忆激活[mid] = {
                "id": mid, "内容": h.get("内容", ""), "标签": h.get("标签", ""),
                "激活度": 1.0, "来源": "点亮",
            }
    except Exception:
        pass

    # ── 3. 概念波能 → 记忆条（通过段落节点 contains 边·波能高才映射）──
    try:
        d = _加载网()[0]
        段落 = d.get("段落", {})
        for 概念, 波能 in 概念波能.items():
            if 波能 < 0.3 or 概念 == '夏维斯':
                continue
            for pid, p in 段落.items():
                if 概念 not in p.get("概念", []):
                    continue
                try:
                    mid = int(pid)
                except Exception:
                    continue
                激活 = round(min(1.0, 波能), 3)  # 感应器映射：激活度=波能（关联强度·钳到[0,1]）
                if mid not in 记忆激活 or 记忆激活[mid]["激活度"] < 激活:
                    记忆激活[mid] = {
                        "id": mid, "内容": p.get("内容", ""), "标签": p.get("标签", ""),
                        "激活度": 激活, "来源": "感应器",
                    }
    except Exception:
        pass

    # ── 4. 排序截断（激活度降序·预算 N 条）──
    记忆列表 = sorted(记忆激活.values(), key=lambda x: -x["激活度"])[:预算]

    # ── 5. prior（预感召回·接续/未竟 → 先验·非独立检索）──
    prior = {}
    try:
        from 预感召回 import 预感召回 as _预感, 格式化提示词 as _格式化
        预感 = _预感(owner, context)
        if 预感:
            prior["预感"] = _格式化(预感)
    except Exception:
        pass

    # ── 感知诚实（2026-08-28 收A：空集合法·种子空则下游禁灌）──
    # 感知为空（无概念波能 + 无精确命中）→ 种子空=True → 下游只留 core 地板，不灌最近条目冒充相关
    种子空 = (not 概念波能) and (not 记忆激活)

    return {"记忆": 记忆列表, "概念": 概念波能, "prior": prior, "种子空": 种子空}


if __name__ == "__main__":
    import json
    for q in ["配分函数", "苏醒循环", "孙博"]:
        r = activate(q)
        print(f"\n═══ activate「{q}」═══")
        print(f"概念: {len(r['概念'])} 个 · 记忆: {len(r['记忆'])} 条")
        for m in r["记忆"][:5]:
            print(f"  [{m['来源']}|{m['激活度']}] {m['内容'][:40]}")
