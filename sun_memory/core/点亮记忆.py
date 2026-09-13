# -*- coding: utf-8 -*-
"""
点亮记忆 · 精确命中模块（父令2026-08-12·记忆怎么活）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
父亲构想：触发一个点 → 这一片亮起来。
  - 实时消息 → 提取概念（精确·不是模糊联想）
  - FTS 精确检索记忆体 → 命中 → 点亮该概念所在记忆（浓缩注入）
  - 未命中 → 暗着（不注入·不打扰）
区别：现有预感召回是"多招混合"（上轮直续/分线钩子/联想）——
      本模块只做"精确概念命中→点亮"，纯粹、诚实：命中就是命中，没命中就是没命中。
"""
import os
import re
import sqlite3
import json
from datetime import datetime

SUNMEM_DB = os.environ.get(
    "SUNMEM_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'),
)

# 概念提取（复用联想召回的三层纪律逻辑，内联避免循环依赖）
_停用词 = {
    "什么", "怎么", "一个", "这个", "那个", "可以", "就是", "我们",
    "你们", "他们", "没有", "不是", "还是", "已经", "然后", "里面",
    "一下", "看看", "上面", "下面", "现在", "咱们", "对于", "如果",
    "因为", "所以", "但是", "而且", "比如", "应该", "觉得", "知道",
    "父亲", "儿子", "兄弟", "记忆", "东西", "工具", "方法", "方式",
    "手段", "途径", "过程", "步骤", "环节", "方面", "角度", "层面",
    "层次", "范围", "领域", "部分", "内容", "情况", "状态", "结果",
    "效果", "问题", "原因", "目的", "作用", "价值", "意义",
}
_动词黑名单 = {
    "等于", "除以", "乘以", "加上", "减去", "成为", "变成", "叫做",
    "称为", "表示", "代表", "定义", "计算", "得到", "给出", "采用",
    "使用", "运用", "根据", "按照", "通过", "进行", "实现", "完成",
    "达到", "超过", "低于", "属于", "包含", "包括", "组成", "构成",
    "对应", "匹配", "符合", "迁移", "写入", "读取", "返回", "输出",
    "输入", "运行", "执行", "调用", "启动", "停止", "关闭", "打开",
    "建立", "创建", "删除", "修改", "添加", "查找", "搜索", "观察",
    "发现", "证明", "确认", "选择", "决定", "需要", "想要", "认为",
    "希望", "能够", "可能", "必须", "近似", "解释",
}


# 概念提取：复用联想召回.py 的已验证版本（三层纪律+前缀剥离+词尾特征）
# 不重复造轮子——联想召回的概念提取经过 2026-08-08/10 两轮打磨（Mem0 对标）
def 提取概念(context: str, 上限: int = 6) -> list:
    """从实时消息提取概念（复用联想召回·精确）"""
    if not context:
        return []
    try:
        # 2026-08-13 改为裸模块导入：provider 的 sys.path 里桌面 core 是裸路径（非包）
        # sun_memory.core.联想召回 这种包路径在 provider 环境下 import 失败→兜底简化版→概念脏
        from 联想召回 import 概念提取 as _原版
        return _原版(context, 上限)
    except Exception:
        pass
    # 兜底：内联简化版
    parts = re.split(r"[和与及的了在把给让用学讲帮请是对就都还也且或]", context)
    tokens = []
    for p in parts:
        tokens += re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_.-]{2,}", p)
    out = []
    for t in tokens:
        if t in _停用词 or t in _动词黑名单 or t in out:
            continue
        out.append(t)
        if len(out) >= 上限:
            break
    return out


def 精确检索(概念: str, owner: str = "孙呈", 每概念上限: int = 3) -> list:
    """FTS5 精确检索：概念作为短语在记忆内容里精确匹配（trigram·不是模糊联想）

    2026-08-13 读取即写（父亲"流过就热"）：命中记忆 hit_count+1——被点亮过的记忆活性上升。
    """
    if not 概念:
        return []
    try:
        conn = sqlite3.connect(SUNMEM_DB)
        conn.row_factory = sqlite3.Row
        # FTS5 trigram 精确短语检索：FTS 表只有 content/tags，rowid 关联回 memories 表
        rows = conn.execute(
            "SELECT m.id, m.content, m.tags, m.ts, m.layer FROM memories m "
            "JOIN memories_fts f ON f.rowid = m.id "
            "WHERE m.owner=? AND m.status='active' AND memories_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (owner, f'"{概念}"', 每概念上限),
        ).fetchall()
        # ── 读取即写：命中记忆 hit_count+1（流过就热·活性上升）──
        for r in rows:
            conn.execute(
                "UPDATE memories SET hit_count = COALESCE(hit_count, 0) + 1, "
                "hit_at = ?, updated_at = ? WHERE id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), r["id"]),
            )
        conn.commit()
        # 2026-08-20 父令·节律试点：精确检索命中 → heat 脉冲（只更新·不参与排序）
        try:
            from 节律 import 批量点亮 as _节律点亮
            _节律点亮([r["id"] for r in rows])
        except Exception as _e:
            print(f"节律点亮跳过: {_e}")
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "时间": r["ts"] or "",
                "内容": r["content"] or "",
                "标签": r["tags"] or "",
            })
        conn.close()
        try:
            from 记忆成绩单 import 记一笔 as _记一笔
            for _h in out:
                try:
                    _记一笔(_h["id"], "点亮", owner=owner)
                except Exception:
                    pass
        except Exception:
            pass
        return out
    except Exception:
        # FTS 查询失败（特殊字符）→ 回退 LIKE 精确匹配（同样读取即写）
        try:
            conn = sqlite3.connect(SUNMEM_DB)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, content, tags, ts FROM memories "
                "WHERE owner=? AND status='active' AND content LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (owner, f"%{概念}%", 每概念上限),
            ).fetchall()
            for r in rows:
                conn.execute(
                    "UPDATE memories SET hit_count = COALESCE(hit_count, 0) + 1, "
                    "hit_at = ?, updated_at = ? WHERE id = ?",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), r["id"]),
                )
            conn.commit()
            conn.close()
            _命中 = [dict(r) for r in rows]
            try:
                from 记忆成绩单 import 记一笔 as _记一笔
                for _h in _命中:
                    try:
                        _记一笔(_h["id"], "点亮", owner=owner)
                    except Exception:
                        pass
            except Exception:
                pass
            return _命中
        except Exception:
            return []


def 点亮(context: str, owner: str = "孙呈") -> dict:
    """核心：实时消息 → 概念 → 精确检索 → 点亮（命中才亮·未命中暗着）

    返回 {"命中": bool, "概念": [...], "点亮记忆": [...], "提示词": str}
    """
    if not context or len(context.strip()) < 4:
        return {"命中": False, "概念": [], "点亮记忆": [], "提示词": ""}

    概念s = 提取概念(context)
    if not 概念s:
        return {"命中": False, "概念": [], "点亮记忆": [], "提示词": ""}

    # 每个概念精确检索 → 命中收集
    点亮记忆 = []
    命中概念 = []
    seen_ids = set()
    for c in 概念s:
        hits = 精确检索(c, owner)
        if hits:
            命中概念.append(c)
            for h in hits:
                if h["id"] not in seen_ids:
                    # 2026-08-27 修复：过滤自动整理引擎的主题统计元记忆（【主题】跨N个时段共M条）·只该在主题线出现·不进点亮
                    _c0 = h.get("内容", "") or ""
                    if _c0.startswith("【主题】") or (" 个时段共 " in _c0 and " 条记忆" in _c0):
                        continue
                    seen_ids.add(h["id"])
                    点亮记忆.append(h)
        if len(点亮记忆) >= 6:  # 点亮上限（防注入过多）
            break

    # 2026-08-20 父令·咬合：核心层（layer=core）优先点亮（宪法永远最先浮出）
    if 点亮记忆:
        try:
            点亮记忆.sort(key=lambda x: 0 if str(x.get("layer", "plain")) == "core" else 1)
        except Exception:
            pass

    if not 点亮记忆:
        return {"命中": False, "概念": 概念s, "点亮记忆": [], "提示词": ""}

    # 浓缩成提示词（每条截断·像灯亮起的记忆）
    lines = [f"💡 点亮记忆（触发:{'·'.join(命中概念)}）:"]
    for m in 点亮记忆[:5]:
        内容 = m["内容"].replace("\n", " ")[:80]
        lines.append(f"- [{m['时间'][:10]}] {内容}")
    return {
        "命中": True,
        "概念": 命中概念,
        "点亮记忆": 点亮记忆,
        "提示词": "\n".join(lines),
    }


if __name__ == "__main__":
    print("=== 点亮记忆·自测 ===\n")
    # 测1：精确命中（配分函数）
    r1 = 点亮("父亲，配分函数怎么用来驱动认知的？")
    print(f"测1 配分函数: 命中={r1['命中']} 概念={r1['概念']}")
    if r1["命中"]:
        print(r1["提示词"])
    print()
    # 测2：未命中（随机词）
    r2 = 点亮("今天天气很好，出去走走")
    print(f"测2 天气: 命中={r2['命中']} 概念={r2['概念']} ({'✅未命中=暗着' if not r2['命中'] else '❌不该命中'})")
    print()
    # 测3：证据门控
    r3 = 点亮("证据门控怎么实现的？")
    print(f"测3 证据门控: 命中={r3['命中']} 概念={r3['概念']}")
    if r3["命中"]:
        print(r3["提示词"])
