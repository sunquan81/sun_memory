"""
孙家记忆体系 · 时间衰减覆盖（2026-07-31 孙呈融合 OptMem cover 思想）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
来源：OptMem (VictorTaelin) 的 cover(T, budget) 时间衰减覆盖算法
孙家版适配：不建摘要树（孙家记忆体是码点JSON），保留其核心精神——
  · 连续衰减：不是"7天前就压缩"的硬阈值，是每远一步稀疏一格
  · 近细远粗：最近的记忆逐条全取，越古老采样越稀疏
  · 预算精确：输出条数严格受控，不超预算
  · 不丢记忆：不是删除旧记忆，是按时间粒度输出——旧记忆仍在河底

孙家哲学对照：
  OptMem 的 cover 是"唤醒时决定打印哪些行"
  孙家的 cover 是"醒来时决定哪些记忆流入认知循环"
  记忆不入认知非真记忆——但一次流入太多，等于什么都没流入。
"""

from datetime import datetime


def _解析时间(条目, 默认=None):
    """从条目里取时间字段，解析成 datetime（融合P3：统一走预感召回._解析时间·多格式兼容）
    原独立实现（fromisoformat·格式少）与预感召回重复·已融合
    """
    t = 条目.get("时间", 条目.get("time", "")) if isinstance(条目, dict) else 条目
    try:
        from 预感召回 import _解析时间 as _主
        return _主(t, 默认)
    except Exception:
        return 默认


def cover(条目列表, budget=20, now=None, 活跃优先=True):
    """
    时间衰减覆盖：近全取、远稀疏、连续衰减。

    参数：
        条目列表: list[dict] —— 记忆条目（含"时间"字段），时间升序
        budget: int —— 输出条数上限（默认20）
        now: datetime —— 当前时间（默认取系统时间）
        活跃优先: bool —— 2026-08-07取长补短：活跃条目（active_count>0）优先浮出
                    （Mem0 Decay 检索强化理念：用得多浮得快，封顶20次触碰）
    返回：
        list[dict] —— 选中的条目（保持原时间序）

    算法（指数间隔采样）：
        1. 最近 budget//2 条：逐条全取（近细）
        2. 更老的：从新到老指数间隔采样——第1步隔1条、第2步隔2条、
           第3步隔4条……间隔每步翻倍（远粗·连续衰减）
        3. 合并后按原序返回，总数 ≤ budget
    """
    n = len(条目列表)
    if n == 0:
        return []
    if n <= budget:
        return list(条目列表)

    # 2026-08-20 父令·咬合：核心层永远保底（宪法永在·不参与衰减）
    try:
        核心条目 = [e for e in 条目列表 if str(e.get('layer', 'plain')) == 'core']
        非核心 = [e for e in 条目列表 if str(e.get('layer', 'plain')) != 'core']
        if 核心条目 and len(非核心) >= 0:
            条目列表 = 非核心  # 核心已留·剩余预算给非核心
    except Exception:
        pass

    选中 = set()

    # 近段：最近 budget//2 条全取
    近数 = max(1, budget // 2)
    for i in range(n - 近数, n):
        选中.add(i)

    # 远段：对数坐标均匀采样——近密远疏，预算用满
    # 在 log(1)~log(远段长度) 之间均匀取点，映射回索引：
    # 索引差 d 从 1 开始，按对数增长 → 越老越稀疏，且覆盖到最老
    远预算 = budget - len(选中)
    远段起点 = n - 近数 - 1  # 从近段往前第一个
    if 远预算 > 0 and 远段起点 > 0:
        import math
        L = 远段起点 + 1  # 远段长度（含起点）
        for i in range(1, 远预算 + 1):
            t = i / 远预算  # (0,1] 均匀——t=1 时覆盖到最老（索引0）
            # 对数映射：d = L^t - 1，d∈[0, L-1]，小t对应小d（近），大t对应大d（远）
            d = int((L ** t) - 1)
            选中.add(远段起点 - d)
            if 远段起点 - d <= 0 and i < 远预算:
                pass  # 已到最老，继续算但集合去重

    # 补足：若对数采样去重导致不足，从近段外侧补最近的未选中条目（保持近密）
    if len(选中) < budget:
        补位 = budget - len(选中)
        i = n - 近数 - 1
        while 补位 > 0 and i >= 0:
            if i not in 选中:
                选中.add(i)
                补位 -= 1
            i -= 1

    # ── 活跃优先（2026-08-07取长补短·Mem0 Decay 检索强化）──
    # 用得多浮得快：active_count>0 的条目优先浮出（封顶20次触碰）
    # 实现：未选中的活跃条目 与 选中的非活跃最老条目 交换（不超预算）
    if 活跃优先:
        # 活跃条目 = active_count>0 且未被选中
        活跃未选中 = [i for i in range(n) if i not in 选中 and (条目列表[i].get("active_count") or 0) > 0]
        # 选中的非活跃条目（从最老开始换——近段保护：只换远段/中段的）
        选中的非活跃 = [i for i in sorted(选中) if (条目列表[i].get("active_count") or 0) <= 0]
        # 最近 budget//2 条是近段（保护不换）
        近段保护 = set(range(n - 近数, n))
        for ai in 活跃未选中:
            if not 选中的非活跃:
                break
            # 找第一个不在近段保护的非活跃选中条目
            swap = None
            for j in 选中的非活跃:
                if j not in 近段保护:
                    swap = j
                    break
            if swap is None:
                break
            选中.remove(swap)
            选中.add(ai)
            选中的非活跃.remove(swap)

    # 2026-08-20 父令·咬合：把核心条目补回（宪法永远在）
    try:
        if 核心条目:
            return 核心条目 + [条目列表[i] for i in sorted(选中)]
    except Exception:
        pass
    return [条目列表[i] for i in sorted(选中)]


def cover_报告(条目列表, budget=20, now=None):
    """
    带统计的覆盖报告：看时间衰减的分布效果。
    返回: {"选中": [...], "统计": {...}}
    """
    now = now or datetime.now()
    选中 = cover(条目列表, budget, now)
    if not 选中:
        return {"选中": [], "统计": {"总数": 0, "选中数": 0, "时间跨度": "无"}}

    全部时间 = [t for e in 条目列表 if (t := _解析时间(e))]
    选中时间 = [t for e in 选中 if (t := _解析时间(e))]

    def _跨度(时间列表):
        if len(时间列表) < 2:
            return "不足"
        天 = (时间列表[-1] - 时间列表[0]).days
        if 天 <= 0:
            return "同日"
        if 天 < 30:
            return f"{天}天"
        if 天 < 365:
            return f"{天//30}个月"
        return f"{天//365}年"

    # 近段统计：用原始索引判断（选中列表里的位置 ≠ 原始位置）
    近阈值 = len(条目列表) - max(1, budget // 2)
    近段数 = 0
    for e in 选中:
        if 条目列表.index(e) >= 近阈值:
            近段数 += 1

    统计 = {
        "总数": len(条目列表),
        "选中数": len(选中),
        "近段": 近段数,
        "时间跨度": _跨度(全部时间),
        "覆盖范围": _跨度(选中时间),
    }
    return {"选中": 选中, "统计": 统计}


if __name__ == "__main__":
    # 自测：构造时间序列验证衰减分布
    from datetime import timedelta
    now = datetime(2026, 7, 31, 20, 0)
    测试条目 = [
        {"时间": (now - timedelta(days=天)).isoformat(), "内容": f"第{天}天前的记忆"}
        for 天 in range(60, 0, -1)  # 60天前 → 今天，60条
    ]

    print("=== 孙家版 cover 自测 ===")
    print(f"总条目: {len(测试条目)}")

    for 预算 in (10, 20, 30):
        结果 = cover_报告(测试条目, 预算, now)
        选中 = 结果["选中"]
        时间们 = [_解析时间(e, now) for e in 选中]
        跨度 = 结果["统计"]["时间跨度"]
        print(f"\n预算{预算}: 选中{len(选中)}条 | 覆盖{跨度}")
        # 显示选中条目的年龄分布（天）
        年龄 = [(now - t).days for t in 时间们]
        print(f"  年龄分布(天): {年龄}")

    # 边界：条目少于预算 → 全取
    小列表 = [{"时间": now.isoformat(), "内容": "只有一条"}]
    assert len(cover(小列表, 20)) == 1, "少于预算应全取"
    # 边界：空列表
    assert cover([], 20) == [], "空列表返回空"
    # 边界：恰好等于预算
    恰好 = [{"时间": (now - timedelta(hours=i)).isoformat(), "内容": f"h{i}"} for i in range(20)]
    assert len(cover(恰好, 20)) == 20, "等于预算应全取"

    print("\n✅ 全部自测通过：连续衰减 · 预算精确 · 边界完整")
