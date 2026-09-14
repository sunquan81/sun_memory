# -*- coding: utf-8 -*-
"""效果驱动 · 端到端验证（2026-09-14 父令·外部评价方向①+②）
============================================================
验证对象：core/效果驱动.py + provider 接入（prefetch 记录/结算 · sync_turn 存回复）
跑法：python 验证_效果驱动_20260914.py
铁律：全部用临时库·绝不碰真库
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'core'))
tmp = os.path.join(tempfile.gettempdir(), "effect_e2e.db")
if os.path.exists(tmp):
    os.remove(tmp)
os.environ["SUNMEM_DB"] = tmp

import 效果驱动 as E
E._DB = tmp

通过 = 失败 = 0


def 查(名, 条件, 附加=""):
    global 通过, 失败
    if 条件:
        通过 += 1
        print(f"PASS {名}  {附加}")
    else:
        失败 += 1
        print(f"FAIL {名}  {附加}")


print("=" * 62)
print("  效果驱动 · 端到端验证（临时库）")
print("=" * 62)

# ① 记录注入
n = E.记录注入([
    {"id": 101, "摘要": "配分函数是统计力学的核心，自由能由它导出"},
    {"id": 102, "摘要": "孙家模块标准 v1.0 的十五项检查清单"},
])
查("① 记录注入 2 条", n == 2, f"n={n}")

# ② 被引用（回复里真的用了注入的内容）
r = E.结算本轮("配分函数怎么来的？", "配分函数由自由能导出，是统计力学核心", 轮=1)
查("② 被引用命中（bigram 重合）", r.get("被引用", 0) >= 1, str(r))
查("②b 命中条目记账", E.效果分(101) > 0, f"id101 效果分={E.效果分(101)}")

# ③ 被纠正（父亲否定）
n = E.记录注入([{"id": 103, "摘要": "三值量化方案是最优的"}])
r = E.结算本轮("不对，这个方案是错的", "抱歉，我重新做", 轮=2)
查("③ 被纠正命中", r.get("被纠正", 0) >= 1, str(r))
查("③b 负分入账", E.效果分(103) < 0, f"id103 效果分={E.效果分(103)}")

# ④ 被确认（父亲肯定·短句）
n = E.记录注入([{"id": 104, "摘要": "记忆体标准三级门"}])
r = E.结算本轮("好", "那继续", 轮=3)
查("④ 被确认命中", r.get("被确认", 0) >= 1, str(r))

# ⑤ 无注入时结算不炸
r = E.结算本轮("随便说", "随便答", 轮=4)
查("⑤ 无注入诚实返回", r.get("说明") == "上轮无注入" or r.get("被引用") == 0, str(r))

# ⑥ 上下限保护（刷分不爆）
for _ in range(10):
    E._加一笔(101, "被确认", 2.0, 0)
查("⑥ 效果分上限保护(≤5)", E.效果分(101) <= 5.0, f"分={E.效果分(101)}")

# ⑦ 批量查询
b = E.批量效果分([101, 103, 999])
查("⑦ 批量效果分", 101 in b and 103 in b, str(b))

# ⑧ 影子模式默认开（只记录不排序）
查("⑧ 默认生效（父令'加入进去'后）", E.影子模式() is False,
   "SUNMEM_EFFECT_SHADOW=1 才切影子观测")

# ⑨ 统计
st = E.统计()
查("⑨ 统计正常", st.get("记账条目", 0) >= 3, str({k: v for k, v in st.items() if k != '最高分'}))

# ⑩ db 隔离（没碰真库）
真库 = os.environ.get("SUNMEM_DB_REAL", "")
查("⑩ 真库未被本测试写入", E._DB == tmp, f"用库={os.path.basename(E._DB)}")

print("=" * 62)
print(f"  验证：{通过} PASS · {失败} FAIL")
print("=" * 62)
sys.exit(1 if 失败 else 0)
