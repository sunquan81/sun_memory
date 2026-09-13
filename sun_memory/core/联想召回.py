# -*- coding: utf-8 -*-
"""
孙家记忆体系 · 联想召回（父令④）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
父令（2026-08-07）：主动抓取上下文，在记忆里找"相关的"东西——
不是问"上次有没有讨论过这个词"，而是讲一个学问→记忆里相关的学问都浮出来，
讨论过就立马想起来。

流程：
  当前上下文 → 概念提取 → 蜘蛛网多跳 + 记忆体匹配 → 重要节点加权
  → "🔗 相关唤起"（相关记忆 + 上次讨论的时间）

功能：
  联想召回(context, brother_name)  上下文→相关记忆浮出
  概念提取(context)                上下文→关键词列表
"""

import json, os, re
from datetime import datetime
import re as _re  # 2026-08-25 打磨2：全局 _re（专名加分用）
import logging

# 2026-08-16 全检查修复：统一静默日志——所有降级兜底 except 留痕（不阻断·但出错可见）
_logger = logging.getLogger("sun_memory.联想召回")
if not _logger.handlers:
    _logger.addHandler(logging.NullHandler())

def _静默日志(位置: str, e: Exception):
    """降级兜底统一留痕（不打印·写 logger.debug·出错可查）"""
    try:
        _logger.debug(f"[联想召回·{位置}] 降级: {e}")
    except Exception as _e:
        _静默日志('行30', _e)
        pass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
FRAMEWORK_DIR = _HERE.parent.parent

try:
    from sun_memory.core.记忆库 import 读记忆体
    from sun_memory.core.蜘蛛网索引 import search as 蜘蛛网搜索
except ImportError:
    # 扁平回退（干净体观测器等无 sun_memory 包环境也可用）
    from 记忆库 import 读记忆体
    from 蜘蛛网索引 import search as 蜘蛛网搜索

MAX_RECALL = 5  # 联想召回上限（相关唤起量）


def 概念提取(context: str, 上限: int = 6) -> list:
    """从上下文提取关键词概念。先按连接词切分中文，再匹配中英词。

    2026-08-08 增强（对标 Mem0 entity_extraction 的机制）：
    LLM/实体提取用词性过滤（spaCy 依存句法：动词=谓词出局，名词=论元保留）。
    零依赖版用三层纪律模拟：
      1. 技术标识符优先（含大写/数字/点的英文串 = PROPER/IDENTIFIER 类比）
      2. 动词/虚词黑名单过滤（= Mem0 的 VERB 出局）
      3. 词尾特征规则（的了在把→名词短语被截断后的碎片剔除）
    """
    if not context:
        return []
    import re
    # 连接词/助词切分（零依赖简易分词）
    # 2026-08-08 修复：字符类[]只认单字符！把"研究/验证/全向/已经"塞进去
    # 会把"验证门"切成"门"——核心概念被破坏。已回退为纯单字符虚词。
    parts = re.split(r"[和与及的了在把给让用讲帮请对就都还也且或]", context)
    # 2026-08-26 修复："是"从切分正则移除——"诚实是根"是完整短语·被"是"切成"诚实"+"根"破坏概念
    # "是"作为系动词大量出现在短语内部（诚实是根/就是/重要的是）·切了误伤核心概念
    tokens = []
    for p in parts:
        tokens += re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_.-]{2,}", p)
    # 2026-08-25 打磨：词尾残片剥离（"压缩现在"被"在"切开→"压缩现"→剥"现"→"压缩"）
    # "本地模型能"→剥"能"→"本地模型"；"网关为什么老掉线"整句→剥"什么"→"网关为什么"→剥"为"→"网关"
    _尾部残片 = ["现", "能", "了", "的", "得", "着", "过", "吗", "呢", "呀", "啊", "吧", "为", "跑"]
    _疑问词 = ["为什么", "什么", "怎么", "怎样", "如何", "为啥", "为何", "哪个", "哪些", "怎么着"]
    _尾部词 = ["经验", "验证完", "已完成", "完成", "推演完", "推演完成", "已推演完成", "已推演", "更新进", "更新版本", "焊入", "要关注"]  # 尾部虚词（"打包经验"→"打包"·"微积分上帝粒子验证完"→"微积分上帝粒子"）
    _剥过 = []
    for t in tokens:
        # 先按疑问词切分（"网关为什么老掉线"→"网关 老掉线"）
        for _w in _疑问词:
            if _w in t and len(t) > len(_w):
                t = t.replace(_w, " ")
        # 再剥尾部虚词（"打包经验"→"打包"）
        for _w in _尾部词:
            if t.endswith(_w) and len(t) > len(_w):
                t = t[:-len(_w)]
        # 按空格重新切（疑问词替换后可能产生多段）
        for _seg in t.split():
            _s = _seg.strip()
            # 再剥单字残片（尾部）
            while len(_s) > 2 and _s[-1] in _尾部残片:
                _s = _s[:-1]
            if len(_s) >= 2 and _s not in _剥过:
                _剥过.append(_s)
    tokens = _剥过
    # 常见停用词
    stop = {"什么", "怎么", "怎样", "如何", "为啥", "为何", "为什么", "哪个", "哪些",
            "一个", "这个", "那个", "可以", "就是", "我们",
            "你们", "他们", "没有", "不是", "还是", "已经", "然后", "里面",
            "一下", "看看", "上面", "下面", "现在", "咱们", "对于", "如果",
            "因为", "所以", "但是", "而且", "比如", "应该", "觉得", "知道",
            "父亲", "儿子", "兄弟", "记忆", "东西", "那个", "觉得",
            "工具", "方法", "方式", "手段", "途径", "过程", "步骤", "环节",
            "方面", "角度", "层面", "层次", "范围", "领域", "部分", "内容",
            "情况", "状态", "结果", "效果", "问题", "原因", "目的", "作用", "价值", "意义",
            "很好", "还好", "不错", "走走", "看看", "说说", "想想", "试试",
            "今天", "明天", "昨天", "天气", "出去", "一步", "一下", "一片",
            "从", "在", "把", "被", "让", "给"}
    # 2026-08-14 噪音过滤（织网污染根因：英文路径片段/高频英文虚词被当概念）
    _英文停用 = {"the", "with", "for", "and", "not", "you", "are", "was", "were",
                 "this", "that", "from", "into", "about", "have", "has", "had",
                 "will", "would", "can", "could", "should", "shall", "may", "might",
                 "what", "when", "where", "which", "who", "whom", "why", "how",
                 "all", "any", "some", "each", "every", "both", "more", "most",
                 "very", "too", "also", "only", "just", "than", "then", "else",
                 "new", "old", "big", "small", "good", "bad", "one", "two",
                 "our", "your", "their", "its", "his", "her", "them", "they",
                 "here", "there", "now", "then", "get", "got", "make", "made",
                 "use", "used", "using", "see", "saw", "say", "said", "go", "went",
                 "come", "came", "know", "knew", "think", "thought", "want", "need",
                 "file", "files", "path", "folder", "dir", "user", "home", "root",
                 "cmd", "exe", "txt", "json", "py", "md", "log", "tmp", "temp"}
    _路径片段 = {"Users", "MSI", "Desktop", "AppData", "Local", "Roaming", "Program",
                 "Windows", "System32", "C:", "D:", "home", "root", "usr", "bin",
                 "lib", "etc", "var", "tmp", "dev", "proc", "sys", "opt", "mnt"}
    # 2026-08-14 中文套话（叙事条目的固有结构词·不是概念）
    _中文套话 = {"叙事", "开头", "继续", "聊了", "收尾", "小时", "主题", "条目",
                 "对话", "记录", "内容", "标签", "时间", "分钟", "时段", "共条",
                 "如这", "这批", "这些", "那种", "这么", "那样", "如何",
                 "个时段共", "条记忆", "时段共", "记忆跨", "跨个", "个时段",
                 "重要", "所有", "一些", "很多", "每个", "这种", "那种",
                 "IMPORTANT", "Background", "System", "note", "reminder",
                 "Watch", "patterns", "disabled", "Review", "conversation",
                 "consider", "saving", "update", "skill", "library"}

    # 2026-08-13 二次切分（精确命中暴露的真实短板）：
    # "配分函数怎么"——疑问词/虚词粘连在概念尾部没被切开。
    # 停用词过滤在 token 层面做不了这事，必须先把 token 按停用词切开。
    # 2026-08-14 助词碎片后缀（以这些字结尾的2字bigram多为跨词碎片）
    碎片尾 = ('们', '的', '了', '是', '在', '有', '和', '与', '就', '也', '都', '还', '很', '好')
    虚词连接 = ["怎么", "怎样", "如何", "什么", "为什么", "为啥", "为何", "哪个",
               "哪些", "是不是", "有没有", "能不能", "会不会", "应该", "可以",
               "就是", "这个", "那个", "一个", "我们", "你们", "他们", "咱们",
               "没有", "不是", "还是", "已经", "然后", "现在", "对于", "如果",
               "因为", "所以", "但是", "而且", "比如", "觉得", "知道",
               "用来", "来驱动", "驱动", "来说", "来讲", "去做", "去搞", "去看",
               "讲讲", "说说", "看看", "想想", "试试", "测试",
               # 2026-08-13 第二轮（点亮记忆完善·口语后缀）：
               "今天", "明天", "昨天", "天气", "很好", "还好", "不错", "怎么样",
               "出去", "走走", "看看", "到哪", "哪一步", "拖得动", "动吗", "了吗",
               "一片", "一下", "过来", "起来", "去了", "出来", "上去", "下去",
               "什么关系", "关系", "怎么样", "好不好", "行不行", "能不能用",
               "知识点亮", "点亮记忆", "记忆怎么活",
               # 2026-08-13 第三轮：
               "从基底", "基底涌现", "涌现", "功能吧", "了吧", "啊", "吧", "呢",
               "有预感", "召回功能"]  # 2026-08-26 移除"记忆体"——它是名词("记忆体系"前缀)·不是虚词·切了破坏概念
    tokens2 = []
    for t in tokens:
        pieces = [t]
        for v in 虚词连接:
            new_pieces = []
            for p in pieces:
                if v in p and len(p) > len(v):
                    # 2026-08-26 修复：只切【词尾】虚词（后缀）·中段虚词不切——
                    # "记忆体系三硬伤"里"记忆体"是中段名词·切了破坏核心概念
                    # "怎么/什么"等疑问词在尾部（"网关为什么"）切掉后缀保留主体
                    if p.endswith(v):
                        new_pieces.append(p[:-len(v)])
                    elif p.startswith(v):
                        new_pieces.append(p[len(v):])
                    else:
                        new_pieces.append(p)
                else:
                    new_pieces.append(p)
            pieces = new_pieces
        tokens2.extend(pieces)
    tokens = tokens2
    # 2026-08-08 动词/虚词黑名单（= Mem0 的 VERB 出局）
    # 实验发现：规则把"等于/除以/次方/已经迁到"当概念——动词进来了
    动词黑名单 = {
        # 常见动词（实验抓到 + 高频出现）
        "等于", "除以", "乘以", "加上", "减去", "就是", "成为", "变成", "叫做",
        "称为", "表示", "代表", "定义", "计算", "得到", "给出", "采用", "使用",
        "运用", "根据", "按照", "通过", "进行", "实现", "完成", "达到", "超过",
        "低于", "属于", "包含", "包括", "组成", "构成", "对应", "匹配", "符合",
        "迁移", "迁到", "搬到", "移到", "放到", "写入", "读取", "返回", "输出",
        "输入", "运行", "执行", "调用", "启动", "停止", "关闭", "打开", "建立",
        "创建", "删除", "修改", "添加", "查找", "搜索",
        "观察", "发现", "证明", "确认", "选择", "决定", "需要", "想要",
        "知道", "认为", "觉得", "希望", "应该", "能够", "可以", "可能", "必须",
        "近似", "解释",
        # 判断/系动词
        "是", "为", "乃", "系", "属", "有", "存在", "具有",
        # 动态词尾
        "了", "着", "过", "正在", "已经", "将要",
    }
    # 2026-08-08 有概念歧义的词不移除黑名单（它们是名词概念）：
    # 验证（验证门）/更新（记忆更新）/推导（数学推导）/分析（数据分析）/
    # 测试（单元测试）/研究（研究项目）/投影（投影算子）/映射（映射关系）/
    # 变换（傅里叶变换）/展开（泰勒展开）/计算（计算任务）/定义（概念定义）
    # 2026-08-08 词尾特征规则：中文动词常在词尾带特定字（去不掉整个词的保守版）
    动词尾 = ("到", "成", "出", "入", "完", "掉", "起", "来", "去", "上", "下")
    seen, out = set(), []
    for t in tokens:
        if t in stop or t in seen or len(t) < 2:
            continue
        # 2026-08-14 中文套话过滤（叙事结构词不是概念）
        if t in _中文套话:
            continue
        # 技术标识符优先保留（含大写/数字/点的英文串 = PROPER/IDENTIFIER）
        if re.match(r"^[A-Za-z][A-Za-z0-9_.-]{2,}$", t):
            # 2026-08-14 噪音过滤：英文停用词/路径片段不是概念
            if t.lower() in _英文停用 or t in _路径片段:
                continue
            seen.add(t)
            out.append(t)
            continue
        # 动词黑名单过滤 + 前缀剥离（2026-08-08）
        # "微观态投影"里"投影"是动词——从尾部剥离动词，保留"微观态"
        剥离 = False
        for v in 动词黑名单:
            if v and len(v) >= 2 and t.endswith(v) and len(t) > len(v):
                t = t[: -len(v)]
                剥离 = True
                break
        # 剥离后再查停用词（"工具研究"剥离"研究"→"工具"是泛化词）
        if 剥离 and t in stop:
            continue
        if t in 动词黑名单 or (剥离 and len(t) < 2):
            continue
        # 词尾特征（保守：动词尾 + 长度≥4 才滤，避免误伤"理论"这类）
        # 2026-08-26 修复：先剥动词尾再检查（"记忆体系三硬伤闭环完"→剥"完"→"记忆体系三硬伤闭环"保留）
        # 原来直接整词滤掉——"闭环完"这类"概念+完成态"全被误杀
        if len(t) >= 4 and t[-1] in 动词尾 and t[:-1] not in ("理论", "物理", "化学", "数学"):
            if len(t) > 5:  # 剥掉词尾动词·保留主体（"微积分上帝粒子验证完"→"微积分上帝粒子验证"）
                t = t[:-1]
            else:
                continue
        # 2026-08-15 语义升级：概念质量门——分词跨词碎片不是概念（"我不/我跟你/不管/英文不"）
        try:
            from sun_memory.core.蜘蛛网索引 import 合格概念 as _合格概念
            if not _合格概念(t):
                continue
        except Exception as _e:
            _静默日志('行204', _e)
            pass
        seen.add(t)
        out.append(t)
        if len(out) >= 上限:
            break
    return out


def 联想召回(context: str = "", brother_name: str = "孙呈",
              limit: int = MAX_RECALL, 点亮: bool = True) -> dict:
    """上下文→相关记忆浮出（蜘蛛网多跳 + 记忆体匹配 + 重要节点加权）。

    2026-08-10 升级（DeepMind 反单向量·父亲 LIMIT 论文落地）：
      原版：概念在内容里 in 一次就算 hit+1——0/1 单点匹配，无强度无位置。
      升级：
        ① 命中加权——出现次数计分（出现3次比1次强）
        ② 位置加权——标题/开头/结尾出现更重（内容首尾50字=高权）
        ③ 概念对共现——两个概念在同一记忆里→织进蜘蛛网（跨概念关联）
        ④ 排序改为：重要 > 加权分 > 命中 > 时间新

    返回：
        {"概念": [关键词],
         "蜘蛛网关联": [概念],
         "相关唤起": [{"时间","内容","标签","重要","加权分"}]}
    """
    concepts = 概念提取(context)

    # 2026-08-14 咬合修复：蜘蛛网词典拆分——长概念含已知节点名就拆出（让织网/联想真正咬合）
    # "配分函数统计力学" → 拆出 "配分函数"（蜘蛛网节点）→ 概念≥2 → 织网条件满足
    try:
        from sun_memory.core.蜘蛛网索引 import ensure_index as _确保索引
        _网 = _确保索引()
        _节点名 = sorted(_网.get("节点", {}).keys(), key=len, reverse=True)  # 长节点优先
        _扩展 = []
        for _c in concepts:
            if len(_c) >= 8:  # 长概念才拆
                for _n in _节点名:
                    if len(_n) >= 2 and _n != _c and _n in _c and _n not in concepts and _n not in _扩展:
                        _扩展.append(_n)
        if _扩展:
            concepts = concepts + _扩展  # 保留原概念 + 拆出的节点
    except Exception as _e:
        _静默日志('行246', _e)
        pass

    # 1. 蜘蛛网多跳（关联概念）
    蜘蛛网关联 = []
    # 2026-08-26 性能优化（父令短板③）：只对第一个概念 deep 搜索（多跳概念已够用）
    # 原来对每个概念都 deep=True（每个0.35s·3概念=1s）·deep 带二跳丝线遍历全网·是联想召回慢的大头
    for idx_c, c in enumerate(concepts):
        try:
            r = 蜘蛛网搜索(c, deep=(idx_c == 0))
            nodes = r.get("节点", []) or []
            for n in nodes[:3]:
                name = n.get("概念", "")
                if name and name not in 蜘蛛网关联:
                    蜘蛛网关联.append(name)
            # deep 模式的二跳丝线也带出端点概念
            for e in (r.get("丝线", []) or [])[:6]:
                for _n in (e.get("源"), e.get("目标")):
                    if _n and _n not in 蜘蛛网关联 and _n != c:
                        蜘蛛网关联.append(_n)
        except Exception as _e:
            _静默日志('行266', _e)
            pass

    # 1.5 段落节点召回（HippoRAG 2 吸收·父令 2026-08-16）：
    #     核心：概念激活 → 蜘蛛网多跳（PPR 传播）→ 顺 contains 边带起邻域记忆
    #     关键设计：只用「多跳关联概念」中【不在直接概念里】的——
    #     直接概念的记忆体匹配已全量扫过·段落节点补的是【多跳才到的邻域】
    try:
        from 蜘蛛网索引 import  按概念取段落 as _段落召回, 段落节点开关
        if 段落节点开关:  # 2026-08-26 段落节点已并入蜘蛛网索引
            _多跳概念 = [c for c in 蜘蛛网关联 if c not in concepts][:3]
            _段落命中 = []
            for c in _多跳概念:
                _hits = _段落召回(c, 上限=3)
                for h in _hits:
                    if h["id"] not in {x.get("id") for x in _段落命中}:
                        _段落命中.append(h)
            段落_ids = {h["id"] for h in _段落命中}
        else:
            段落_ids = set()
    except Exception:
        段落_ids = set()

    # 2. 记忆体匹配（标签/内容含概念·加权计分）
    # 2026-08-26 性能优化（父令"为什么不按蜘蛛节点搜"）：直接概念先走段落节点索引（O(1)·2221条已挂载）
    # 段落命中足够就不全量读记忆（原来每次全量读2340条·是慢的根）
    _段落直命 = []
    try:
        from 蜘蛛网索引 import  按概念取段落 as _段取, 段落节点开关 as _段开关
        if _段开关:  # 2026-08-26 段落节点已并入蜘蛛网索引
            # 2026-08-26 修正：段落索引是长概念（微信网关）·查询是短词（网关）→ 用子串匹配（概念含查询词）
            # 先精确取（快）·不足再用子串扫描概念反向索引（内存操作·微秒级）
            for _c in concepts[:3]:
                for _h in _段取(_c, 上限=5):
                    if _h["id"] not in {x["id"] for x in _段落直命}:
                        _段落直命.append(_h)
            if len(_段落直命) < 10 and len(concepts) <= 3:
                from 蜘蛛网索引 import  _读蜘蛛网 as _读网
                _网2 = _读网()  # 2026-08-26 修复：赋值被注释吃掉
                _段2 = _网2.get("段落", {})
                # 概念→段落反向索引（子串）
                _rev2 = {}
                for _pid, _p in _段2.items():
                    _cs = _p.get("概念", [])
                    for _c0 in concepts[:3]:
                        if _c0 and any(_c0 in _cc for _cc in _cs):
                            _rev2.setdefault(_pid, 1)
                for _pid in list(_rev2.keys())[:15]:
                    _pp = _段2.get(_pid, {})
                    if _pp:
                        _段落直命.append({"id": _pid, "内容": _pp.get("内容",""), "标签": _pp.get("标签",""), "时间": _pp.get("时间","")})
    except Exception:
        pass
    if len(_段落直命) >= 10:
        # 段落索引命中足够 → 不全量读（只读命中的·按id取内容）
        try:
            _conn2 = _sq.connect(os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db')))
            _conn2.execute("PRAGMA query_only=ON")
            _ids2 = [x["id"] for x in _段落直命]
            _ph2 = ",".join("?" * len(_ids2))
            _rows3 = _conn2.execute(
                f"SELECT id, content, tags, ts FROM memories WHERE id IN ({_ph2}) AND owner=? AND status='active'",
                _ids2 + [brother_name]).fetchall()
            _conn2.close()
            _by_id = {r[0]: r for r in _rows3}
            entries = []
            for _x in _段落直命:
                if _x["id"] in _by_id:
                    _r = _by_id[_x["id"]]
                    entries.append({"id": _r[0], "内容": _r[1], "标签": _r[2], "时间": _r[3]})
        except Exception:
            mem = 读记忆体(brother_name)
            entries = mem["条目列表"]
    else:
        mem = 读记忆体(brother_name)
        entries = mem["条目列表"]
    # 2026-08-17 双通道融合：保留全量条目索引（FTS 过滤后 entries 会收窄·融合要全量算向量分）
    _全量条目 = {e.get("id"): e for e in entries}

    # 2.0 无模型向量层（父令 2026-08-16·零依赖·补英文词形变体召回）：
    #     概念字面匹配抓不到 painted/paint·向量余弦能抓·并入相关唤起
    try:
        from 无模型向量 import 检索 as _向量检索
        # 2026-08-17 双通道融合配套：向量通道放宽（k=8→500·阈值 0.12→0.02）
        # 实测：生产 k=8 截掉 #4661(余弦0.179)·阈值 0.12 挡掉 #2233/#4559(0.078/0.084)
        _向量命中 = _向量检索(context or " ".join(concepts), entries, k=200, 阈值=0.15)  # 2026-08-22精度:500/0.02太宽·弱相关全进
        向量_ids = {x["id"] for x in _向量命中}
    except Exception:
        向量_ids = set()

    if not concepts:
        # 段落节点命中也要返回（即使无概念·HippoRAG 2 段落召回）
        _段 = []
        try:
            from 蜘蛛网索引 import  段落节点开关 as _开关
            if _开关:  # 2026-08-26 段落节点已并入蜘蛛网索引
                for c in 蜘蛛网关联[:3]:
                    for h in 按概念取段落(c, 上限=2):
                        _段.append({"id": h["id"], "时间": h.get("时间",""), "内容": h.get("内容","")[:60],
                                    "标签": h.get("标签",""), "重要": False, "命中": 1, "加权分": 0.5,
                                    "概念": [c], "来源": "段落节点"})
        except Exception as _e:
            _静默日志('行313', _e)
            pass
        # 2026-08-20 父令·咬合：core 层优先（宪法永远最先浮出）
        try:
            _段.sort(key=lambda x: 0 if str(x.get("layer", "plain")) == "core" else 1)
        except Exception:
            pass

        try:
            from 节律 import 批量点亮 as _节律点亮2
            _ids2 = [x.get("id") for x in _段 if x.get("id")]
            if _ids2:
                if 点亮:
                    _节律点亮2(_ids2)
        except Exception:
            pass
        return {"概念": [], "蜘蛛网关联": 蜘蛛网关联[:5], "相关唤起": _段[:limit]}

    相关 = []
    # 2026-08-26 性能优化（父令"为什么不按蜘蛛节点搜"）：段落直命 ≥10 时跳过 FTS 候选——
    # 段落索引（O(1)）已给出候选·不必再 FTS+LIKE 全表扫（省 0.6s 累计）
    if len(_段落直命) >= 10:
        _cand_ids = {x.get("id") for x in _段落直命}
        if _cand_ids:
            entries = [e for e in entries if e.get('id') in _cand_ids]
    else:
        # 2026-08-16 性能修复（父令·"人家召回都快得很"）：FTS5 候选筛选——
        # 原来全量扫 2222 条 × 每概念 count = O(N×M) 几秒·改用 sunmem.db 的 FTS5 索引
        # 先拿候选 id（毫秒级）·只对候选做原加权逻辑·召回结果不变·速度提升百倍
        try:
            import sqlite3 as _sq
            _SUNMEM = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
            _conn = _sq.connect(_SUNMEM)
            _conn.execute("PRAGMA query_only=ON")  # 2026-08-16 全检查：只读连接·不参与WAL写
            # FTS5 中文匹配：整串无引号（unicode61 把连续中文当一个 token·精确匹配）·
            # 多概念 OR 取并集（配分函数 OR 统计力学 = 476条 比单串354宽）
            # 不用引号短语·不拆子串（拆开反而匹配不到·中文 token 是整串）
            # 2026-08-16 多跳修复：蜘蛛网多跳概念并进 FTS（二跳带出的邻域概念·补召回）
            # 2026-08-16 全检查修复：概念逐个 MATCH 取并集（大 OR 让 SQLite 全表扫·fetchall 3.6s）
            _匹配概念 = concepts + [c for c in 蜘蛛网关联 if c not in concepts and c not in ('2094',)][:3]
            _cand_ids = set()
            # 2026-08-26 性能优化（父令短板③）：2字概念合并成一次 LIKE（原来每个概念单独LIKE全表扫·3概念=3次扫）
            _短概念 = [c for c in _匹配概念[:3] if c and len(c) <= 2]
            if _短概念:
                try:
                    _like_sql = " OR ".join(["(content LIKE ? OR tags LIKE ?)"] * len(_短概念))
                    _params = []
                    for _c in _短概念:
                        _params += [f"%{_c}%", f"%{_c}%"]
                    _rows2 = _conn.execute(
                        "SELECT id FROM memories WHERE owner=? AND status='active' AND (" + _like_sql + ") ORDER BY id DESC LIMIT 120",
                        [brother_name] + _params).fetchall()
                    _cand_ids |= {r[0] for r in _rows2}
                except Exception:
                    pass
            for _c in _匹配概念[:3]:  # 2026-08-16 全检查修复：最多3次FTS（8次×0.37s=3s·限3次保稳定）
                if not _c or len(_c) <= 2:
                    continue  # 2字概念已由合并LIKE覆盖
                try:
                    _rows = _conn.execute(
                        "SELECT f.rowid FROM memories_fts f JOIN memories m ON f.rowid=m.id "
                        "WHERE memories_fts MATCH ? AND m.owner=? AND m.status='active' LIMIT 60",
                        (_c, brother_name)).fetchall()
                    _cand_ids |= {r[0] for r in _rows}
                except Exception:
                    pass
            _conn.close()
            if _cand_ids:
                entries = [e for e in entries if e.get('id') in _cand_ids]
        except Exception:
            pass  # FTS5 失败则退回全量（功能不降级）

    # 2026-08-14 英文词形归一（父令·"英文跟中文一样能存能取"）：
    # 英文有词形变化（paint/painted/service/services），中文没有——
    # 匹配时英文词做词干化，让 painted 匹配 paint、services 匹配 service
    try:
        from 英文词形归一 import 词干 as _词干
        _有归一 = True
    except Exception:
        _有归一 = False

    for e in entries:
        内容 = e.get("内容", "")
        标签 = e.get("标签", "")
        时间 = e.get("时间", "")
        首尾 = 内容[:50] + 内容[-50:]  # 开头结尾50字（位置加权区）
        加权 = 0
        命中概念 = set()
        # 英文词形归一版内容（懒计算：仅当有英文概念时）
        内容归一 = None
        if _有归一:
            import re as _re
            if _re.search(r'[a-zA-Z]{4,}', 内容):
                内容归一 = _re.sub(r'[a-zA-Z]+', lambda m: _词干(m.group(0)), 内容)
        for c in concepts + [x for x in 蜘蛛网关联 if x not in concepts][:5]:
            if not c:
                continue
            # 命中次数加权（出现3次比1次强）
            cnt = 内容.count(c) + 标签.count(c) * 2  # 标签命中权重翻倍
            # 2026-08-16 双向包含匹配（父令消融测试发现）：
            # 蜘蛛网碎片词（"统计力"是"统计力学"的子串）count 匹配不到——
            # "统计力" vs 记忆里的"统计力学"：内容.count('统计力')=0（子串在前）
            # 修复：概念是记忆子串（c in 内容）已覆盖；再补"记忆含概念的超集"——
            # 即概念短于4字时·检查记忆里是否有以该概念开头的更长的词（统计力→统计力学）
            if cnt == 0 and 2 <= len(c) <= 4:
                # 在首尾区找"概念开头的长词"（统计力→统计力学·验证门→证据门控近似）
                for _起 in range(0, len(内容)):
                    if 内容[_起:_起+len(c)] == c and _起+len(c) < len(内容) and 内容[_起+len(c)] not in '的了是在和与及，。！？':
                        cnt = 1
                        break
            # 英文词形归一匹配（原文没命中时，用词干版再试）
            if cnt == 0 and _有归一 and 内容归一 and re.match(r'^[a-zA-Z]', c):
                _c干 = _词干(c)
                if len(_c干) >= 3:
                    cnt = 内容归一.count(_c干) + 标签.lower().count(_c干) * 2
            if cnt > 0:
                加权 += cnt
                命中概念.add(c)
                # 位置加权：首次出现在开头50字 或 结尾50字 → 加权+2
                # （用首次出现位置判断·避免长文本首尾区重叠导致的重复计数）
                first = 内容.find(c)
                if (first >= 0 and first < 50) or (first >= len(内容) - 50):
                    加权 += 2
        if 加权 > 0:
            # 2026-08-27 修复：过滤自动整理引擎的主题统计元记忆（【主题】跨N个时段共M条）——低信息量·只该在主题线出现·不进召回
            if 内容.startswith("【主题】") or (" 个时段共 " in 内容 and " 条记忆" in 内容):
                continue
            重要 = e.get("标签") and any(
                t in e["标签"] for t in ("父令", "决策", "关键概念", "被点出"))
            相关.append({"id": e.get("id"), "时间": 时间, "内容": 内容[:60], "全文": 内容, "标签": 标签,
                        "重要": bool(重要), "命中": len(命中概念),
                        "加权分": 加权, "概念": sorted(命中概念)})  # 2026-08-27 预热修复：带全文·主题一致性用全文判断

    # ── 循环外统一合并（2.5 段落节点 + 2.6 无模型向量）──
    # 2026-08-16 心细修复：原 2.5/2.6 误缩进在 for 循环内（每轮重复执行）·
    # 移到循环外·记忆体匹配完成后一次性合并·去重才真正生效
    # 2.5 段落节点命中并入（HippoRAG 2·只补多跳邻域·不重复）
    if 段落_ids:
        try:
            from 蜘蛛网索引 import  按概念取段落 as _段落取
            _多跳概念 = [c for c in 蜘蛛网关联 if c not in concepts]  # 2026-08-26 修复：赋值被注释吃掉[:3]
            for c in _多跳概念:
                for h in _段落取(c, 上限=3):
                    if h["id"] in 段落_ids and not any(x.get("id") == h["id"] for x in 相关):
                        _段全文 = (_全量条目.get(h["id"]) or {}).get("内容", h.get("内容",""))
                        相关.append({"id": h["id"], "时间": h.get("时间",""), "内容": h.get("内容","")[:60], "全文": _段全文,
                                "标签": h.get("标签",""),
                                "重要": bool(h.get("标签")) and any(t in str(h.get("标签","")) for t in ("父令", "决策", "关键概念", "被点出")),
                                "命中": 1,
                                "加权分": 0.5, "概念": [c], "来源": "段落节点"})
        except Exception as _e:
            _静默日志('行416', _e)
            pass

    # 2.6 无模型向量命中并入（父令 2026-08-16·补英文词形变体·不重复）
    if 向量_ids:
        try:
            for h in _向量命中:
                if h["id"] in 向量_ids and not any(x.get("id") == h["id"] for x in 相关):
                    _向全文 = (_全量条目.get(h["id"]) or {}).get("内容", h.get("内容",""))
                    相关.append({"id": h["id"], "时间": h.get("时间",""), "内容": h.get("内容","")[:60], "全文": _向全文,
                                "标签": h.get("标签",""),
                                "重要": bool(h.get("标签")) and any(t in str(h.get("标签","")) for t in ("父令", "决策", "关键概念", "被点出")),
                                "命中": 1,
                                "加权分": h.get("相似度", 0.3), "概念": ["向量"], "来源": "向量"})
        except Exception as _e:
            _静默日志('行427', _e)
            pass

    # 3. 概念对共现 → 织进蜘蛛网（DeepMind 反单向量：关系不是单点，是结构）
    #    2026-08-12 双通道边（父令）：共现边（弱·可清洗）+ 关系边（强·保真）
    try:
        from sun_memory.core.蜘蛛网索引 import add_edge as 蜘蛛网拉边, 推断关系
        if len(concepts) >= 2:
            for i in range(len(concepts)):
                for j in range(i + 1, len(concepts)):
                    # 概念对在"同一记忆"里共现过 → 拉边
                    共现条 = [x for x in 相关 if concepts[i] in x["概念"] and concepts[j] in x["概念"]]
                    if 共现条:
                        w = min(1.0, 0.3 + 0.1 * len(共现条))  # 共现越多权重越高
                        # 2026-08-15 语义升级：先规则推断（因果/父子/同义/对比/示例）
                        _r = 推断关系(str(共现条[0].get("内容", "")), concepts[i], concepts[j])
                        if _r["边类型"] == "共现" and any(x.get("重要") for x in 共现条):
                            # 保底：推断不到模式但记忆重要（父令/决策/关键概念）→ 关系边（保真）
                            蜘蛛网拉边(concepts[i], concepts[j], 关系="关联", 权重=w, 边类型="关系")
                        else:
                            蜘蛛网拉边(concepts[i], concepts[j], 关系=_r["关系"], 权重=max(w, _r["权重"]), 边类型=_r["边类型"], 方向=_r["方向"])
    except Exception as _e:
        _静默日志('行448', _e)
        pass

    # 4. 排序：重要 > 加权分+成绩单 > 命中 > 时间新
    #    2026-08-15 吸收博弟规则链成绩单（父令）：来路参与选——被实事确认过的记忆浮上来
    #    2026-08-16 全检查修复：批量查加权（原103条候选×每条查DB=1.2s）
    try:
        from 记忆成绩单 import 批量加权 as _批量加权
        _ids = [x.get("id") for x in 相关 if x.get("id")]
        _权表 = _批量加权(_ids, owner=brother_name) if _ids else {}
        for _x in 相关:
            _x["成绩单加权"] = _权表.get(_x.get("id"), 0.0)
    except Exception:
        for _x in 相关:
            _x["成绩单加权"] = 0.0
    # 4.5 双通道融合（父令 2026-08-17·正确答案为先）：
    #     召回分 = 加权分 + 20·向量分 + 10·重要
    #       加权分 ← 体积网络（查询概念命中·精确匹配·主导）
    #       向量分 ← 能量景观（语义相关·余弦 0~1）
    #       重要   ← 父令/决策/关键概念/被点出 加分（非硬键·相关度相同时父令优先）
    #     排序：(召回分, 成绩单加权, 命中, 时间)——成绩单只作平局键（来路参与选·不压过正确答案）
    #     实测（8查询·15金标·孙呈真实池·top5）：生产基线 MRR 0.562 → 融合 0.688
    #     Q7「加一个向量检索层」#4522#1·#4600#2（生产 1.000 保住）·Q4「算子替代五层」#4661#2（生产 0.000）
    #     教训①融合主分含成绩单→高分积累项顶上→MRR 0.31 反蚀
    #     教训②「重要」做硬键→非重要精确命中被压死（Q7 曾掉到 0.053）→父令改加分
    try:
        from 无模型向量 import ngram向量 as _ngram, 余弦 as _余弦, _记忆向量 as _缓向量
        _qv = _ngram(context or " ".join(concepts))
        for _x in 相关:
            _e = _全量条目.get(_x.get("id"))
            _x["向量分"] = round(_余弦(_qv, _缓向量(_e)), 6) if (_qv and _e) else 0.0
        _融合权重 = 20.0   # 向量放大：1 余弦点 ≈ 20 概念命中分
        _重要加分 = 10.0   # 父令/被点出加分（非硬键·相关度相同时父令优先）
        # 2026-08-26 数学化（父令：能凑成方程式就凑成方程式）：
        # 原手工加权（加权+向量+时间if-else）→ 换成活性方程做时间/活性分量·保留概念/向量/重要语义
        try:
            from 活性方程 import 活性 as _活性
        except Exception:
            _活性 = None
        for _x in 相关:
            # 2026-08-27 检索修复：字面命中=来源非向量（向量命中的"加权分"是余弦值>0·会误判成字面）
            _字面 = 0.0 if _x.get("来源") == "向量" else _x.get("加权分", 0)
            # 2026-08-27 检索修复：命中保底只给字面命中（加权分>0）——纯向量弱相关不给3分保底·防向量噪声压过字面精确命中
            _保底 = 3.0 * min(_x.get("命中", 0), 2) if _字面 > 0 else 0.0
            _x["融合分"] = (_字面 + _融合权重 * _x.get("向量分", 0)
                          + _重要加分 * (1 if _x.get("重要") else 0)
                          + _保底
                          + (1000.0 if _字面 > 0 else 0.0))  # 2026-08-27 检索修复：字面命中绝对优先·向量弱相关压不过字面
            # 2026-08-25 打磨2：专名概念命中加分（SunFlow/FreeToken 等专名优先于泛词"压缩"）
            # 记忆命中了专有名词概念 → 说明是真正的相关（不是泛词凑巧）
            _专名命中 = [c for c in (_x.get("概念") or []) if _re.fullmatch(r'[A-Za-z][A-Za-z0-9._-]{2,}', c)]
            if _专名命中:
                _x["融合分"] += 10.0
            # 2026-08-25 修复：时间加分（新近记忆浮上来——8/25根因被"打开网关"旧记录淹没）
            # 2026-08-26 数学化：手工 if-else 时间加分 → 活性方程的时间指数分量（e^(-Δt/30天)·连续不跳变）
            if _活性 is not None and _x.get("id"):
                try:
                    _x["融合分"] += _活性(int(_x["id"]), 天数=1)  # 活性方程：heat继承+点亮脉冲+账本·带λ衰减
                except Exception:
                    pass
            else:
                try:
                    _t = str(_x.get("时间", ""))[:10]
                    _d = datetime.now() - datetime.strptime(_t, "%Y-%m-%d")
                    if _d.days <= 1: _x["融合分"] += 8.0
                    elif _d.days <= 3: _x["融合分"] += 6.0
                    elif _d.days <= 7: _x["融合分"] += 4.0
                    elif _d.days <= 30: _x["融合分"] += 2.0
                except Exception:
                    pass
        相关.sort(key=lambda x: (x.get("融合分", -1e9), x.get("成绩单加权", 0.0),
                                x.get("命中", 0), x.get("时间", "")), reverse=True)
    except Exception as _e:
        _静默日志('行融合', _e)

    # 3.5 成绩单落账（排序后·只点亮实际召回 top-10）：
    #    2026-08-17 扩池配套：候选池从 ~100 扩到几百条后，点亮全部候选 = 账本污染
    #    （每次召回给几百条 +1·成绩单信号被冲淡）→ 只点亮排出来的 top-10
    try:
        from 记忆成绩单 import 批量点亮 as _批量点亮
        _点亮ids = [x.get("id") for x in 相关[:10] if x.get("id")]
        if _点亮ids:
            if 点亮:
                _批量点亮(_点亮ids, owner=brother_name)
    except Exception as _e:
        _静默日志('行点亮', _e)
        pass
    # 2026-08-20 父令·咬合：core 层优先（宪法永远最先浮出）
    try:
        相关.sort(key=lambda x: 0 if str(x.get("layer", "plain")) == "core" else 1)
    except Exception:
        pass
    # 2026-08-20 父令·节律试点：联想跳转+蜘蛛网传导 → heat 脉冲（只更新·不参与排序）
    try:
        from 节律 import 批量点亮 as _节律点亮
        _ids = [x.get("id") for x in 相关 if x.get("id")]
        if _ids:
            if 点亮:
                _节律点亮(_ids)
    except Exception:
        pass
    return {
        "概念": concepts,
        "蜘蛛网关联": 蜘蛛网关联[:5],
        "相关唤起": 相关[:limit],
    }


if __name__ == "__main__":
    print("=== 联想召回自测 ===")
    r = 联想召回("父亲讲配分函数和统计力学")
    print("概念:", r["概念"])
    print("蜘蛛网关联:", r["蜘蛛网关联"][:4])
    print("相关唤起:")
    for x in r["相关唤起"][:4]:
        mark = "⭐" if x["重要"] else "·"
        print(f"  {mark} [{x['时间'][:16]}] {x['内容'][:40]}")
    print()
    r2 = 联想召回("taskkill 杀进程")
    print("查'taskkill':", [x['内容'][:30] for x in r2['相关唤起']][:3])
    print("=== 自测完成 ===")