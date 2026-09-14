#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆体闭环 · 统一框架入口（2026-08-15 组装）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
把 21 个零件装进一个闭环框架——一个入口管全周期：

    醒来 ──► 感知注入 + 认知画像（记忆流入认知循环）
    干活 ──► 写入（去重→进化→落主库）· 召回（点亮/联想/预感/蜘蛛网/经验）
    睡前 ──► 自动整理 → 自组织 → 织网 → 重建镜像 → 体检
    全览 ──► 模块地图 + 数据账本 + 健康状态

用法（在 孙家记忆体系 根目录下执行）：
    python sun_memory/闭环.py 醒来   --语境 "当前任务上下文"
    python sun_memory/闭环.py 写入   "这句话要记住" --标签 对话记录
    python sun_memory/闭环.py 召回   "配分函数 统计力学"
    python sun_memory/闭环.py 睡前   --执行        # 默认只做体检+镜像检查（快）
    python sun_memory/闭环.py 体检
    python sun_memory/闭环.py 镜像   --兄弟 孙呈     # 主库 → JSON 镜像重建
    python sun_memory/闭环.py 全览

说明：主库 sunmem.db 是唯一事实源，JSON 是镜像；写入/整理目前以孙呈为主，
      其它兄弟可读（醒来/召回/体检），睡前 --执行 暂只落孙呈。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
FRAMEWORK_DIR = _HERE.parent if _HERE.name == "sun_memory" else _HERE.parent.parent   # 本记忆体根/
CORE_DIR = _HERE / "core" if _HERE.name == "sun_memory" else _HERE                    # sun_memory/core/
for _p in (str(FRAMEWORK_DIR), str(CORE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SUNMEM_DB = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sunmem.db'))

# 与 provider.追加 同一份系统噪音黑名单（防 Hermes 自动注入模板混入真记忆）
_噪音标记 = [
    "Review the conversation above", "consider saving to memory",
    "update the skill library", "[System note:",
    "Your previous turn was interrupted", "User correction",
    "IMPORTANT: Background process", "Watch patterns disabled",
    "system_reminder", "Be ACTIVE — most",
]


def _连接():
    conn = sqlite3.connect(SUNMEM_DB)
    conn.row_factory = sqlite3.Row
    return conn


def 写入记忆(内容: str, 标签: str = "对话记录", 兄弟: str = "孙呈"):
    """唯一写入口·委托写入链.写入记忆（2026-08-28 收W：完整流程统一在写入链）

    返回: 新 id / "duplicate:<旧id>" / None（拦截或失败）
    """
    try:
        from 写入链 import 写入记忆 as _统一写入
        r = _统一写入(内容, 标签=标签, owner=兄弟, 来源='闭环.写入')
        if r.get('ok'):
            new_id = r.get('id')
            print(f"  ✅ 已写入 #{new_id}（{兄弟}·{标签}）")
            return new_id
        else:
            _msg = r.get('msg', '')
            if '重复' in _msg:
                import re as _re
                _m = _re.search(r'#(\d+)', _msg)
                if _m:
                    print(f"  ⏭️ 内容重复跳过（旧条 id={_m.group(1)}）")
                    return "duplicate:" + _m.group(1)
            print(f"  ⛔ {_msg}")
            return None
    except Exception as e:
        print(f"  ⚠️ 写入失败: {e}")
        return None


def 醒来(兄弟: str, 语境: str):
    """醒来：感知注入 + 认知画像 → 记忆流入认知循环"""
    print("=" * 60)
    print(f"  醒来 · {兄弟} · {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)
    from 感知注入 import inject
    from 维护链 import 认知画像, 格式化画像  # 2026-08-27 P1修复：认知画像已并入维护链
    r = inject(兄弟, 语境)
    print(f"  感知注入: 最近记忆 {r.get('最近记忆')} | 蜘蛛网匹配 {r.get('蜘蛛网匹配')} | 关联概念 {r.get('关联概念')}")
    print(f"  注入路径: {r.get('注入路径')}")
    画像 = 认知画像(兄弟, 最近条数=10)
    if 画像:
        print()
        print("  🧭 认知画像:")
        print(格式化画像(画像) if isinstance(画像, dict) else 画像)
    out = FRAMEWORK_DIR / "感知器" / "当前输出.md"
    if out.exists():
        print()
        print("  📄 注入输出已生成: 感知器\\当前输出.md（前 20 行）")
        print("-" * 60)
        for line in out.read_text(encoding="utf-8").splitlines()[:20]:
            print("   " + line)


def 召回(关键词: str, 兄弟: str):
    """干活·召回：点亮(精确) + 联想(多跳) + 预感(八招) + 蜘蛛网 + 经验 合并输出"""
    print("=" * 60)
    print(f"  召回 · 「{关键词}」 · {兄弟}")
    print("=" * 60)
    from 点亮记忆 import 点亮
    from 联想召回 import 联想召回 as 联想
    from 预感召回 import 预感召回 as 预感, 格式化提示词
    from 经验总结 import recall_experience
    from 蜘蛛网索引 import search as 网搜, status as 网状态
    try:
        灯 = 点亮(关键词, 兄弟)
        print("  💡 点亮记忆:", "命中" if 灯.get("命中") else "未命中（诚实·暗着）")
        for m in 灯.get("点亮记忆", [])[:5]:
            print(f"     - [{str(m.get('时间'))[:10]}] {str(m.get('内容'))[:70]}")
    except Exception as e:
        print(f"  ⚠️ 点亮失败: {e}")
    try:
        联 = 联想(关键词, brother_name=兄弟, limit=5)
        print("  🔗 联想召回 概念:", 联.get("概念"))
        for e in 联.get("相关唤起", [])[:5]:
            print(f"     - [{str(e.get('时间'))[:10]}] {str(e.get('内容'))[:70]}")
    except Exception as e:
        print(f"  ⚠️ 联想失败: {e}")
    try:
        r = 预感(兄弟, 关键词)
        print()
        print("  📌 预感提示词:")
        for line in 格式化提示词(r).splitlines()[:12]:
            print("     " + line)
    except Exception as e:
        print(f"  ⚠️ 预感失败: {e}")
    try:
        经 = recall_experience(关键词, brother_name=兄弟, limit=3)
        if 经:
            print()
            print("  ✦ 经验召回:")
            for e in (经 if isinstance(经, list) else []):
                print(f"     - {str(e.get('内容'))[:70]}")
    except Exception as e:
        print(f"  ⚠️ 经验召回跳过: {e}")
    try:
        网 = 网搜(关键词)
        print()
        print("  🕷️ 蜘蛛网:", 网 if isinstance(网, str) else f"{len(网)} 条命中")
    except Exception as e:
        print(f"  ⚠️ 蜘蛛网失败: {e}")


def 睡前(兄弟: str, 执行: bool):
    """睡前：默认体检+状态+镜像检查；--执行 才跑自动整理/织网/镜像重建（约1分钟）"""
    print("=" * 60)
    print(f"  睡前 · {兄弟} · {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)
    from 记忆成绩单 import 状态统计  # 2026-08-27 P1修复：记忆状态已并入记忆成绩单
    try:
        st = 状态统计(兄弟)
        print("  记忆状态:", st if isinstance(st, str) else json.dumps(st, ensure_ascii=False)[:200])
    except Exception as e:
        print(f"  ⚠️ 状态统计失败: {e}")
    from 维护链 import 体检  # 2026-08-27 P1修复：记忆体检已并入维护链
    try:
        print()
        print("  🩺 记忆体检（全库）:")
        体检(打印=True)
    except Exception as e:
        print(f"  ⚠️ 体检失败: {e}")
    if 执行:
        if 兄弟 != "孙呈":
            print("  ⚠️ 睡前 --执行 目前只落孙呈（自动整理引擎写回写死孙呈）")
            return
        print()
        print("  🛠 自动整理（小时叙事→主题叙事→织网，约 1 分钟）...")
        from 自动整理引擎 import 自动整理引擎
        r = 自动整理引擎(兄弟).整理()
        print("  整理结果:", json.dumps(r, ensure_ascii=False, default=str)[:300] if isinstance(r, dict) else r)
        print()
        print("  🪞 重建 JSON 镜像...")
        重建镜像(兄弟)
        print()
        print("  🩺 整理后复检:")
        try:
            体检(打印=True)
        except Exception:
            pass


def 重建镜像(兄弟: str = "孙呈"):
    """主库 → JSON 镜像重建（主库为唯一事实源）"""
    conn = _连接()
    rows = conn.execute(
        "SELECT id, content, tags, ts FROM memories WHERE owner=? AND status='active' ORDER BY ts, id",
        (兄弟,),
    ).fetchall()
    conn.close()
    items = []
    for r in rows:
        try:
            tags = json.loads(r["tags"]) if r["tags"] else []
            if isinstance(tags, list):
                tags = ",".join(tags)
        except Exception:
            tags = str(r["tags"] or "")
        items.append({"id": r["id"], "时间": r["ts"] or "", "标签": tags, "内容": r["content"] or ""})
    next_id = max((i["id"] for i in items), default=0) + 1
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = {
        "条目列表": items,
        "next_id": next_id,
        "元信息": {"来源": "sunmem.db（主库重建）", "最后更新": now, "记录条数": len(items)},
    }
    p = FRAMEWORK_DIR / "记忆体" / f"{兄弟}_索引记忆体.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  🪞 镜像已重建: {p}（{len(items)} 条）")


def 成绩单(兄弟: str = "孙呈", 上限: int = 20):
    """干活·成绩单：账本排行（来路可查·博弟魂）+ 可信标记"""
    print("=" * 60)
    print(f"  记忆成绩单 · {兄弟} · 排行（来路参与选）")
    print("=" * 60)
    from 记忆成绩单 import 全部成绩单
    from 记忆库 import 读记忆体
    rows = 全部成绩单(兄弟, 上限=上限)
    if not rows:
        print("  账本还是空的——召回命中会自动落「点亮」账（流过就热）")
        return
    mem = 读记忆体(兄弟)
    by_id = {e.get("id"): e for e in mem.get("条目列表", [])}
    for r in rows:
        m = by_id.get(r["memory_id"], {})
        标记 = "⭐可信" if r.get("可信") else "·"
        print(f"  #{r['memory_id']} {标记} 总账{r['总账']:>3d} 点亮{r['点亮']:>3d} 确认{r['确认']:>3d} 纠正{r['纠正']:>3d} heat{r['heat']:>3d}")
        print(f"      {str(m.get('内容'))[:66]}")


def 全览():
    """全览：模块地图 + 数据账本 + 健康状态"""
    print("=" * 60)
    print("  孙家记忆体 · 全览")
    print("=" * 60)
    模块 = [
        ("provider", "总入口·醒来注入/对话写入"), ("感知注入", "注入链"), ("点亮记忆", "精确命中"),
        ("联想召回", "概念多跳"), ("预感召回", "八招接续"), ("认知画像", "画像驱动下一步"),
        ("时间衰减", "近细远粗"), ("内容去重", "不重复存"), ("记忆进化", "更新不删"),
        ("经验总结", "教训优先"), ("蜘蛛网索引", "概念网络"), ("英文词形归一", "词干化"),
        ("知识库检索", os.path.dirname(os.path.abspath(__file__))), ("记忆库", "统一读写"), ("自动整理引擎", "小时/主题叙事"),
        ("记忆自组织", "主题分组"), ("自动整理", "旧版兼容"), ("记忆压缩", "旧记忆骨架"),
        ("记忆状态", "过期/活跃"), ("记忆体检", "全库体检"), ("闭环", "本框架入口"),
    ]
    print("  模块地图（21 零件 + 1 闭环壳）:")
    for i in range(0, len(模块), 3):
        print("    " + "  |  ".join(f"{n}({d})" for n, d in 模块[i:i + 3]))
    print()
    from 蜘蛛网索引 import status as 网状态
    try:
        print("  🕷️ 蜘蛛网:", 网状态())
    except Exception as e:
        print(f"  ⚠️ 蜘蛛网状态失败: {e}")
    print()
    conn = _连接()
    rows = conn.execute("SELECT owner, status, COUNT(*) c FROM memories GROUP BY owner, status ORDER BY owner").fetchall()
    conn.close()
    print("  数据账本（sunmem.db 主库）:")
    for r in rows:
        print(f"    {r['owner']} · {r['status']}: {r['c']}")
    try:
        from 记忆成绩单 import 全部成绩单 as _全部成绩单
        _rc = _全部成绩单("孙呈", 上限=10**6)
        print(f"  成绩单账本（孙呈）: {len(_rc)} 条记忆有账 · 可信 {sum(1 for _r in _rc if _r.get('可信'))} 条")
    except Exception:
        pass
    print()
    print("  闭环铁律: 醒来读 → 干活写 → 睡前沉 → 织网反馈 → 下次注入")


def main():
    ap = argparse.ArgumentParser(description="记忆体闭环 · 统一框架入口", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("命令", choices=["醒来", "写入", "召回", "成绩单", "睡前", "体检", "镜像", "织网", "全览", "预热", "整理", "身份中心", "落库"])
    ap.add_argument("内容", nargs="?", default="", help="写入/召回的内容")
    ap.add_argument("--兄弟", default="孙呈")
    ap.add_argument("--标签", default="对话记录")
    ap.add_argument("--语境", default="", help="醒来时的当前任务上下文")
    ap.add_argument("--执行", action="store_true", help="睡前真正执行自动整理/织网")
    ap.add_argument("--上限", type=int, default=0, help="语义重织只扫最近 N 条（0=全部）")
    args = ap.parse_args()
    if args.命令 == "醒来":
        醒来(args.兄弟, args.语境)
    elif args.命令 == "写入":
        写入记忆(args.内容, args.标签, args.兄弟)
    elif args.命令 == "召回":
        召回(args.内容 or input("召回关键词: "), args.兄弟)
    elif args.命令 == "成绩单":
        成绩单(args.兄弟, 上限=args.上限 or 20)
    elif args.命令 == "睡前":
        睡前(args.兄弟, args.执行)
    elif args.命令 == "体检":
        from 维护链 import 体检  # 2026-08-27 P1修复：记忆体检已并入维护链
        体检(打印=True)
    elif args.命令 == "镜像":
        重建镜像(args.兄弟)
    elif args.命令 == "织网":
        # 2026-08-15 语义升级：先重织（干净概念上推断语义边）→ 再净化（碎片门+次数门收口）——
        # 顺序不能反：净化在前会被重织就地升级回去（拉锯），净化在后终态才稳定
        from 蜘蛛网索引 import 语义净化, 碎片归档
        from 自动整理引擎 import 语义重织
        print("--- 语义重织（干净概念上推断语义边）---")
        st = 语义重织(args.兄弟, 上限=args.上限)
        print(json.dumps(st, ensure_ascii=False, indent=2))
        print("--- 语义净化（收口：两端合格 + 次数>=2 的语义边才保留）---")
        print(json.dumps(语义净化(), ensure_ascii=False, indent=2))
        print("--- 碎片归档（碎片节点移出活跃网·不删）---")
        print(json.dumps(碎片归档(), ensure_ascii=False, indent=2))
    elif args.命令 == "预热":
        from 思考预热 import 思考预热 as _预热, 格式化预热
        _r = _预热(args.内容 or input("预热上下文: "), args.兄弟)
        print(格式化预热(_r))
        print(f"每路贡献: {_r.get('每路贡献')} · 耗时 {_r.get('耗时')}s")
    elif args.命令 == "整理":
        from 整理链 import 主题分区, 中心锚定  # 2026-08-27 P1修复：记忆整理→整理链门面
        _p = 主题分区(args.兄弟)
        _c = 中心锚定(args.兄弟)
        print(f"主题分区 {_p['分区数']} 个 · 碎片 {_p['碎片数']} · 总 {_p['总条数']} 条")
        for _z in _p["分区"][:10]:
            print(f"  [{_z['条数']}条] {_z['主题'][:40]}")
        print(f"中心锚定: {_c['中心']} · {_c['锚点数']} 个锚点")
    elif args.命令 == "身份中心":
        from 蜘蛛网索引 import 初始化身份中心  # 2026-08-27 P1修复：身份中心已并入蜘蛛网索引
        print(json.dumps(初始化身份中心(), ensure_ascii=False, indent=2))
    elif args.命令 == "落库":
        from 孙家记忆体 import _初始化表  # 2026-08-27 P1修复：标准记忆对象→孙家记忆体._初始化表
        _初始化表()
    elif args.命令 == "全览":
        全览()


if __name__ == "__main__":
    main()
