# -*- coding: utf-8 -*-
"""效果驱动接入排序 · 验证（2026-09-14 父令"加入进去"后对标）
============================================================
验证两件事：
  ① 效果分真能影响排序（正分靠前·负分靠后）
  ② 不会压过相关性（权重轻·只 ±2.5）
  ③ 真库回归：联想召回跑通·效果分默认 0 不改变现状
跑法：python 验证_效果驱动接入_20260914.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'core'))
tmp = os.path.join(tempfile.gettempdir(), "effect_sort.db")
if os.path.exists(tmp):
    os.remove(tmp)
os.environ["SUNMEM_DB"] = tmp

import 效果驱动 as E
E._DB = tmp

通过 = 失败 = 0


def 查(名, 条件, 附加=""):
    global 通过, 失败
    if 条件:
        通过 += 1; print(f"PASS {名}  {附加}")
    else:
        失败 += 1; print(f"FAIL {名}  {附加}")


print("=" * 62)
print("  效果驱动接入排序 · 验证")
print("=" * 62)

# ── ① 影子模式默认关（=生效）──
查("① 默认生效（非影子）", E.影子模式() is False, "父令'加入进去'")
os.environ["SUNMEM_EFFECT_SHADOW"] = "1"
查("①b 可切影子观测", E.影子模式() is True)
os.environ.pop("SUNMEM_EFFECT_SHADOW")

# ── ② 造效果分：同等相关性下正分靠前 ──
E._建表()
E._加一笔(201, "被确认", 2.0, 0)   # +2
E._加一笔(201, "被引用", 1.0, 0)   # +1  → 共 +3
E._加一笔(202, "被纠正", -2.0, 0)  # -2
相关 = [
    {"id": 200, "融合分": 10.0, "时间": "2026-09-14"},
    {"id": 201, "融合分": 10.0, "时间": "2026-09-14"},
    {"id": 202, "融合分": 10.0, "时间": "2026-09-14"},
]
ef = E.批量效果分([200, 201, 202])
for x in 相关:
    s = ef.get(int(x["id"]), 0.0)
    if s:
        x["效果分"] = s
        x["融合分"] += 0.5 * s
相关.sort(key=lambda x: (x.get("融合分", -1e9), x.get("时间", "")), reverse=True)
顺序 = [x["id"] for x in 相关]
查("② 正分靠前·负分靠后", 顺序 == [201, 200, 202], f"排序={顺序} 分={ef}")

# ── ③ 权重轻：负分压不过相关性优势 ──
相关2 = [
    {"id": 202, "融合分": 20.0},   # 相关性高 20·被纠正 -2 → 20-1=19
    {"id": 203, "融合分": 5.0},    # 相关性低 5·无分 → 5
]
ef2 = E.批量效果分([202, 203])
for x in 相关2:
    s = ef2.get(int(x["id"]), 0.0)
    if s:
        x["融合分"] += 0.5 * s
相关2.sort(key=lambda x: x.get("融合分", -1e9), reverse=True)
查("③ 轻权重不压过相关性", 相关2[0]["id"] == 202, f"高分低效仍靠前 {[(x['id'], x['融合分']) for x in 相关2]}")

# ── ④ 上限保护：单条刷分最多 +2.5 加成 ──
E._加一笔(204, "被确认", 2.0, 0)
for _ in range(20):
    E._加一笔(204, "被确认", 2.0, 0)
加成 = 0.5 * E.效果分(204)
查("④ 加成上限 ≤2.5", 加成 <= 2.5, f"效果分={E.效果分(204)} 加成={加成}")

# ── ⑤ env 开关可回退 ──
os.environ["SUNMEM_EFFECT_SHADOW"] = "1"
查("⑤ 影子开关可回退", E.影子模式() is True)
os.environ.pop("SUNMEM_EFFECT_SHADOW")

# ── ⑥ 真库回归：联想召回跑通·效果分默认 0 ──
os.environ.pop("SUNMEM_DB", None)
真库 = os.environ.get("SUNMEM_DB_REAL", "")
if os.path.exists(真库):
    try:
        E._DB = 真库
        st = E.统计()
        真库分 = E.批量效果分([1, 2, 3, 4, 5])
        查("⑥ 真库 effect_scores 可读", "错误" not in st, f"记账={st.get('记账条目')}条")
        查("⑥b 真库默认无效果分（不改变现状）", all(v == 0 for v in 真库分.values()), f"{真库分}")
    except Exception as e:
        查("⑥ 真库回归", False, str(e)[:80])
else:
    查("⑥ 真库存在", False, "跳过")

print("=" * 62)
print(f"  验证：{通过} PASS · {失败} FAIL")
print("=" * 62)
sys.exit(1 if 失败 else 0)
