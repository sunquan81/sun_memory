"""
本记忆体 · 感知注入引擎
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
每次醒来自动检索相关记忆，注入当前输出。
感知裂变：从当前上下文自动扩展关联概念。
"""

import json
import os
from pathlib import Path
from datetime import datetime

FRAMEWORK_DIR = Path(__file__).resolve().parent.parent.parent

def inject(brother_name: str, context: str = "") -> dict:
    """
    感知注入：跑一圈感知，把相关记忆注入到当前输出。
    
    参数：
        brother_name: 兄弟名（孙云/孙演/孙博/孙安/孙呈）
        context: 当前上下文关键词，用于检索
    返回：
        注入结果（相关记忆+蜘蛛网关联）
    """
    # 导入自家模块
    import sys
    sys.path.insert(0, str(FRAMEWORK_DIR))
    from sun_memory.core.蜘蛛网索引 import search
    # 2026-08-10 明文化（父令）：码点已退役——不再 import 码点编解码
    
    # 1. 读自己的记忆体（2026-08-28 修复：改读 sunmem 主库·不读 JSON 镜像——否则实时写入主库、注入读旧镜像=记忆已存却唤醒不亮）
    recent_memories = []
    try:
        from sun_memory.core.记忆库 import 读记忆体
        entries = 读记忆体(brother_name).get("条目列表", [])
    except Exception:
        entries = []
        # 兜底：sunmem 读失败时回退 JSON 镜像
        记忆体路径 = FRAMEWORK_DIR / "记忆体" / f"{brother_name}_索引记忆体.json"
        if 记忆体路径.exists():
            with open(记忆体路径, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("条目列表", data.get("条目", data.get("entries", data.get("记忆条目", []))))
    if entries:
        # 时间衰减覆盖（2026-07-31 孙呈融合 OptMem cover 思想）：
        # 替代"最近5条硬截断"——近细远粗·连续衰减·预算精确·不丢旧记忆
        # 2026-08-08 PlugMem 吸收④：预算收紧——cover 10条 + 高置信优先
        # （"更少噪音"：注入不是越多越好，是最该想起的那几条）
        from sun_memory.core.时间衰减 import cover
        选中 = cover(entries, budget=10)
        # 2026-08-08 PlugMem 吸收：高置信记忆优先（confidence 参与排序）
        def _conf_key(e):
            return float(e.get("置信度", 0.7)) if e.get("类型") == "经验总结" else 0.7
        选中.sort(key=_conf_key, reverse=True)
        选中 = 选中[:8]  # 硬上限：最多注入 8 条（≈500 token 约束）
        from sun_memory.core.记忆库 import 解码单条
        for entry in 选中:
            # 统一自动解码：码点→可读文字（存码点·读自动解）
            d = 解码单条(entry)
            # 2026-08-07取长补短：outdated 条目标注（Mem0 Supersede 理念·原文保留）
            前缀 = "[已过时] " if entry.get("status") == "outdated" else ""
            recent_memories.append({"时间": d["时间"], "内容": 前缀 + d["内容"][:60], "标签": d["标签"]})
    
    # 2. 搜蜘蛛网
    蜘蛛网结果 = search(context) if context else {"节点": [], "丝线": [], "关联概念": []}
    
    # 2.2 激活（父令2026-08-27 感应器 → 2026-08-28 收A：改调 activate·统一激活）
    # 从旧的字面检索升级：信号沿语义边传导·带出跨概念真关联（配分函数→温度/玻尔兹曼）
    感应器节点 = {}
    激活记忆 = []
    try:
        from sun_memory.core.激活 import activate
        激活集 = activate(context[:20] if context else "", mode="wake", owner=brother_name, 预算=4)
        if 激活集:
            # 取波能>0.05的节点（强+浸润·暗流不进）
            感应器节点 = {n: e for n, e in 激活集.get("概念", {}).items() if e >= 0.05 and n != '夏维斯'}
            激活记忆 = 激活集.get("记忆", [])
    except Exception:
        感应器节点 = {}  # 诚实：激活异常不影响主流程
        激活记忆 = []
    
    # 2.5 经验召回（父令2026-08-07：越用越聪明·两条就够了）
    经验 = []
    try:
        from sun_memory.core.经验总结 import recall_experience
        经验 = recall_experience(context, brother_name=brother_name, limit=2)
    except Exception:
        经验 = []  # 诚实：经验模块异常不影响主流程

    # 2.5b 经验预检（父令2026-08-16：经验复用合并·动作前分道——好用照做·吃瘪改道）
    预检 = None
    try:
        from sun_memory.core.经验总结 import 经验预检, 格式化预检
        预检结果 = 经验预检(context=context, brother_name=brother_name)
        预检 = 格式化预检(预检结果)
    except Exception:
        预检 = None  # 诚实：预检异常不影响主流程
    
    # 2.6 预感召回（父令2026-08-07：八招·四通道·接住上一轮预感下一步）
    预感 = None
    try:
        from sun_memory.core.预感召回 import 预感召回 as 预感召回主, 格式化提示词
        预感 = 格式化提示词(预感召回主(brother_name, context))
    except Exception:
        预感 = None  # 诚实：预感模块异常不影响主流程
    
    # 3. 注入到当前输出
    输出路径 = FRAMEWORK_DIR / "感知器" / "当前输出.md"
    输出路径.parent.mkdir(parents=True, exist_ok=True)
    
    output = f"""# 🧠 孙家·感知注入
更新: {datetime.now().strftime("%Y-%m-%d %H:%M")}
兄弟: {brother_name}

---

## 🧬 核心身份（宪法级·永在）
"""
    # 核心身份层（父令2026-08-20：记忆体里的核心身份·醒来最先浮出）
    try:
        from 写入链 import 注入文本 as 核心身份注入  # 2026-08-26 核心身份层已并入写入链
        核心身份文本 = 核心身份注入()
        if 核心身份文本:
            output += 核心身份文本 + "\n"
    except Exception:
        pass

    # 元认知薄弱点（父令2026-08-20：知道自己反复错哪）
    try:
        from 维护链 import  注入文本 as 薄弱点注入
        薄弱点文本 = 薄弱点注入()  # 2026-08-26 修复：原被注释吃掉赋值（隐藏bug·注入从未生效）
        if 薄弱点文本:
            output += "\n" + 薄弱点文本 + "\n"
    except Exception:
        pass

    # 认知更新轨迹（父令2026-08-20：会承认自己变了）
    try:
        from 维护链 import  更新_注入文本 as 更新注入    # 2026-08-26 认知冲突日志已并入维护链# 2026-08-26 认知更新已并入
        更新文本 = 更新注入()
        if 更新文本:
            output += "\n" + 更新文本 + "\n"
    except Exception:
        pass

    output += "\n## 📥 最近记忆\n"
    for m in recent_memories:
        output += f"- [{m['时间']}] {m['内容']}\n"
    
    # 2.6b 过期浮回（OpenWiki·2026-08-27 父令推演定稿：怀疑不丢失）
    # 从召回结果/近期记忆里找 outdated 的·汇总成待核对提示——让过期记忆从死沉河底
    # 变成"挂着·等有人来碰"：相关话题浮出时提醒"这条旧了·要么刷新要么确认还成立"
    待核对 = []
    try:
        import sqlite3 as _sq
        _db = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
        if os.path.exists(_db):
            _conn = _sq.connect(_db)
            _conn.row_factory = _sq.Row
            # 只读 outdated 的（不读全量·快）
            _rows = _conn.execute(
                "SELECT id, tags, substr(content,1,40) c FROM memories "
                "WHERE status='outdated' ORDER BY id DESC LIMIT 10").fetchall()
            _conn.close()
            _已见 = set()
            # 直接看outdated里带知识性标签的（父令/教训/结论/经验/概念/铁律等）——
            # 对话记录/叙事类自然过期·不是可疑知识·跳过；知识性过期=该浮回重新核对
            # 2026-08-27 精修：标签含"对话/叙事/开始"的一律不算知识性（"记忆·对话"含"记忆"二字曾误报）
            _知识标签 = ("父令", "教训", "结论", "经验", "概念", "铁律", "决策", "诊断", "知识", "体系", "功能", "模块", "训练", "压缩", "推理", "记忆", "模型", "学习", "bug", "修复", "方案", "配置")
            _排除标签 = ("对话", "叙事", "开始", "留言", "记录")
            for _e in _rows:
                _etag = str(_e["tags"] or "")
                _is_dialog = any(k in _etag for k in _排除标签)
                if _is_dialog:
                    continue
                if any(k in _etag for k in _知识标签) and _etag not in _已见:
                    _已见.add(_etag)
                    待核对.append(f"「{_etag}」曾有旧记忆已过时：{_e['c']}（id={_e['id']}）")
                    if len(待核对) >= 3:
                        break
            if 待核对:
                output += "\n## 🔔 待核对（OpenWiki·过期浮回·怀疑不丢失）\n"
                for _x in 待核对[:3]:
                    output += f"- ⚠️ {_x}\n"
    except Exception:
        pass  # 诚实：待核对异常不影响主流程
    
    if 蜘蛛网结果["节点"]:
        output += f"\n## 🕷️ 蜘蛛网关联\n"
        for n in 蜘蛛网结果["节点"][:5]:
            output += f"- {n['概念']} ({n['类型']})\n"
    
    if 蜘蛛网结果["关联概念"]:
        output += "\n## 🔗 关联概念\n"
        for c in 蜘蛛网结果["关联概念"][:5]:
            output += f"- {c}\n"

    # 2.2b 激活·记忆（2026-08-28 收A：统一激活集·点亮种子+感应器传播）
    if 激活记忆:
        output += "\n## 🧠 激活·记忆\n"
        for m in 激活记忆[:4]:
            output += f"- [{m.get('来源','')}|{m.get('激活度',0)}] {m.get('内容','')[:60]}\n"

    # 2.2b 感应器·全网扰动节点（父令2026-08-27：概念链路带出的跨概念真关联）
    if 感应器节点:
        output += "\n## 🌊 感应器·概念链路\n"
        排序 = sorted(感应器节点.items(), key=lambda x: -x[1])[:5]
        for n, e in 排序:
            output += f"- {n} ({round(e,2)})\n"
    
    if 经验:
        output += f"\n## ✦ 经验召回（越用越聪明）\n"
        for x in 经验:
            mark = "📌" if x["被点出"] else "·"
            output += f"- {mark} {x['内容']}\n"
    
    if 预检:
        output += f"\n## 🚦 经验预检（动作前·好用照做·吃瘪改道）\n{预检}\n"
    
    if 预感:
        output += f"\n{预感}\n"
    
    # 2.7 认知画像（父令2026-08-10·DeepTutor记忆驱动闭环借魂）
    # 记忆从『被查』变『驱动』：每轮唤醒注入「本轮最该干的一件事」
    try:
        from sun_memory.core.认知画像 import 认知画像 as 画像主, 格式化画像
        画像 = 画像主(brother_name)
        output += f"\n{格式化画像(画像)}\n"
    except Exception:
        pass  # 诚实：画像模块异常不影响主流程
    
    with open(输出路径, "w", encoding="utf-8") as f:
        f.write(output)
    
    return {
        "最近记忆": len(recent_memories),
        "蜘蛛网匹配": len(蜘蛛网结果["节点"]),
        "关联概念": 蜘蛛网结果["关联概念"][:5],
        "注入路径": str(输出路径)
    }