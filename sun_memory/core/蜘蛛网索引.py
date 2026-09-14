"""
本记忆体 · 蜘蛛网索引引擎
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
蜘蛛网：节点（概念）→ 丝线（关联）→ 索引（快速检索）
感知裂变：写入时自动织网，检索时多跳扩展。
"""

import json, os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    from 线程保护 import 加锁  # 2026-09-14 吸收收束版优点：全局状态线程保护
except Exception:
    import threading as _th_mod
    _th_lock = _th_mod.RLock()
    def 加锁(): return _th_lock

# ── 框架根路径 ──
# 2026-08-16 路径修复（父令消融测试发现）：插件版 parent.parent.parent 解析到 plugins/·
# 而真实蜘蛛网在孙家记忆体系——生产环境蜘蛛网一直是空壳（联想召回多跳从未生效）
# 修复：显式指向本记忆体根/蜘蛛网（核心版与插件版共用此路径）
FRAMEWORK_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_PATH = Path(os.environ.get('蜘蛛网_INDEX', str(FRAMEWORK_DIR / "蜘蛛网" / "索引.json")))

_索引缓存 = {'数据': None, '时间': 0}
_触发累积 = 0
_拉边累积 = 0  # 2026-08-16 全检查修复：add_edge 攒批落盘（原每次拉边全量写4.3MB）

# 2026-08-27 修复：并入的段落节点.py/身份中心.py 用旧变量名（蜘蛛网路径/_网缓存/段落节点开关）·融合时漏迁·补别名
蜘蛛网路径 = INDEX_PATH
_网缓存 = _索引缓存
段落节点开关 = True


def ensure_index():
    """确保蜘蛛网索引文件存在。"""
    # 2026-08-16 性能修复：模块级缓存（5秒内复用）——联想召回每概念调 search→ensure_index·
    # 每次都读 1.1MB 文件导致基准/召回极慢·缓存后只读一次
    import time as _time
    if _索引缓存['数据'] is not None and _time.time() - _索引缓存['时间'] < 300:  # 2026-08-26 性能优化(父令短板③)：5秒→300秒
        return _索引缓存['数据']
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        default = {
            "版本": "1.0",
            "最后织网": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "节点": {},
            "丝线": [],
            "统计": {"节点数": 0, "丝线数": 0}
        }
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default
    with 加锁():  # 2026-09-14 线程保护：读文件+写缓存原子化
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            _索引缓存['数据'] = json.load(f)
            _索引缓存['时间'] = _time.time()
            return _索引缓存['数据']

def save_index(index):
    _tmp = str(INDEX_PATH) + ".tmp"  # 2026-09-13 外部审查修复：提前定义（原 L82 才定义·L66 异常分支先用会 NameError）
    # 2026-08-16 性能修复配套：写盘后缓存失效（ensure_index 缓存的是旧数据）
    with 加锁():  # 2026-09-14 线程保护
        _索引缓存['数据'] = None
    # 2026-08-16 自愈接入（父令）：写盘后轻量读回校验（只验证文件可打开·不全量 load 避免拖慢）
    # 全量完整性校验由 自愈.py 定期做（provider 启动时）——热路径只做防损坏最小检查
    try:
        with open(INDEX_PATH, 'rb') as _f:
            _头 = _f.read(64)
        if not _头.startswith(b'{'):
            raise ValueError('写回文件头异常')
    except Exception as _e:
        try:
            with open(_tmp, 'a', encoding='utf-8') as _f:
                _f.write("\\n# save_index 写回校验失败: %s\\n" % _e)
        except Exception:
            pass
    # 2026-09-14 修复：统计字段曾被外部脚本写成字符串（"节点6888·丝线34845·..."）→ 规范化为 dict
    # 影响：save_index 一直在 TypeError → 蜘蛛网写盘静默失败
    if not isinstance(index.get("统计"), dict):
        _旧 = index.get("统计")
        index["统计"] = {"_备注": _旧} if _旧 else {}
    index["统计"]["节点数"] = len(index["节点"])
    index["统计"]["丝线数"] = len(index["丝线"])
    # 2026-08-15 语义升级：统计按 边类型/关系 真分布（旧值曾是残留脏数据）
    _边类型 = defaultdict(int)
    _关系 = defaultdict(int)
    for _e in index["丝线"]:
        _边类型[_e.get("边类型", "共现")] += 1
        _关系[_e.get("关系", "共现")] += 1
    index["统计"]["边类型"] = dict(_边类型)
    index["统计"]["关系"] = dict(_关系)
    index["最后织网"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 2026-08-14 原子写修复：先写临时文件再改名——直接覆盖写入中途崩溃会截断文件（实测损坏）
    _tmp = str(INDEX_PATH) + ".tmp"
    with open(_tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(_tmp, INDEX_PATH)  # 原子替换

def add_node(概念: str, 类型: str = "概念", 描述: str = ""):
    """添加一个概念节点到蜘蛛网。"""
    index = ensure_index()
    if 概念 not in index["节点"]:
        index["节点"][概念] = {
            "类型": 类型,
            "描述": 描述,
            "创建": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "触发的": 0
        }
        save_index(index)
        return True
    return False


# ── 语义边推断（2026-08-15 升级：蜘蛛网从共现图 → 语义图）──
# 规则式·零依赖：命中明确连接词模式才升级为语义边，否则保持共现（保守·不瞎标）
_因果词 = ["因为", "所以", "因此", "导致", "使得", "源于", "由于", "造成", "引发",
           "之所以", "归因", "起因", "从而", "进而", "触发", "带来", "催生", "引致"]
_父子词 = ["包括", "包含", "属于", "是一种", "分为", "组成", "构成", "子类", "大类",
           "归类", "隶属", "归纳为", "细分为", "隶属于", "衍生于", "归属于", "派生于"]
_同义词 = ["也称", "又称", "又名", "亦名", "别名", "同义", "俗称", "别称", "也就是"]
_对比词 = ["不同于", "相比", "相反", "区别于", "差异", "区别", "较之",
           "相较", "versus", " vs ", "而非", "不是而是"]
_示例词 = ["例如", "比如", "如：", "举例", "譬如", "比方", "举个例子", "例如说"]


def 推断关系(文本: str, 概念A: str, 概念B: str) -> dict:
    """从一条记忆文本推断 概念A-概念B 的语义关系。

    返回 {"关系", "边类型", "权重", "方向"}：
      关系:   因果/父子/同义/对比/示例/共现
      边类型: 关系（语义·强）/ 共现（弱·可清洗）
      方向:   "A→B" 或 "B→A"（因果/父子/示例可定向；同义/对比不定向）
    """
    A, B = str(概念A or ""), str(概念B or "")
    if not A or not B or A == B:
        return {"关系": "共现", "边类型": "共现", "权重": 0.3, "方向": ""}
    # ① 上下位：一个概念是另一个的子串 → 父子（长=父·短=子）
    if A in B or B in A:
        父, 子 = (B, A) if A in B else (A, B)
        return {"关系": "父子", "边类型": "关系", "权重": 0.7, "方向": f"{父}→{子}"}
    ia, ib = 文本.find(A), 文本.find(B)
    if ia < 0 or ib < 0:
        return {"关系": "共现", "边类型": "共现", "权重": 0.3, "方向": ""}
    前, 后 = min(ia, ib), max(ia, ib)
    _长 = len(B) if ib > ia else len(A)
    # 窗口=两概念之间 + 第二概念结尾后补 8 字（连接词常在"B差异/导致…"后出现）
    窗 = 文本[前: 后 + _长 + 8]
    # 2026-08-15 精度收紧：两概念相隔太远（>60字）不是直接关系，保持共现（保守）
    if len(窗) > 60:
        return {"关系": "共现", "边类型": "共现", "权重": 0.3, "方向": ""}

    def _定向():
        return f"{A}→{B}" if ia < ib else f"{B}→{A}"

    for 词 in _因果词:
        if 词 in 窗:
            return {"关系": "因果", "边类型": "关系", "权重": 0.6, "方向": _定向()}
    for 词 in _父子词:
        if 词 in 窗:
            return {"关系": "父子", "边类型": "关系", "权重": 0.6, "方向": _定向()}
    # 同义/对比语义最脆：窗口收紧到 30 字（"A又称B"式短结构才算）
    if len(窗) <= 30:
        for 词 in _同义词:
            if 词 in 窗:
                return {"关系": "同义", "边类型": "关系", "权重": 0.6, "方向": ""}
        for 词 in _对比词:
            if 词 in 窗:
                return {"关系": "对比", "边类型": "关系", "权重": 0.5, "方向": ""}
    for 词 in _示例词:
        if 词 in 窗:
            return {"关系": "示例", "边类型": "关系", "权重": 0.5, "方向": _定向()}
    return {"关系": "共现", "边类型": "共现", "权重": 0.3, "方向": ""}


# ── 概念质量门（2026-08-15 语义升级：碎片不是概念）──
# 抽查结论：蜘蛛网噪音主要来自 概念提取 的分词跨词碎片（"我不/我跟你/不管/英文不/看护已"）。
# 质量门只在 2-4 字短词上收（代词/否定带头、助词/动词尾收尾），长词只拦明显语气尾和"已/的/了/吧"夹词。
_碎片头 = ("我", "你", "您", "他", "她", "它", "咱", "俺", "儿", "不", "没", "别", "已", "这", "那", "怎", "为")
_碎片尾 = ("的", "了", "是", "在", "有", "和", "与", "就", "也", "都", "还", "很", "好",
           "们", "已", "着", "过", "吧", "呢", "呀", "吗", "嘛", "不", "没", "完", "个")   # 助词尾：2-3字都杀
_动词尾3 = ("到", "成", "出", "入", "掉", "起", "来", "去", "上", "下", "别")            # 动词尾：只杀3字（2字真概念：区别/接入/产出/输出）
_语气尾 = ("吗", "呢", "呀", "吧", "嘛")
_夹词碎片 = ("已", "的", "了", "吧")


_人称头 = ("我", "你", "您", "他", "她", "它", "咱", "俺", "儿")
_指示头 = ("这", "那", "每", "某", "哪", "各")
_能愿头 = ("能", "会", "想", "要", "在", "正", "已", "将", "该")
_三字尾 = ("说", "问", "讲", "做", "写", "跟", "带", "看", "你", "我", "他", "她", "它", "咱", "俺")
_家族保留 = ("我儿勿动",)   # 真实家族标记，虽"我"开头但确是概念


def 合格概念(概念) -> bool:
    """蜘蛛网概念质量门：碎片（代词/助词头尾、语气尾、夹词碎片、空串/单字）不是概念。"""
    n = str(概念 or "").strip()
    if len(n) < 2:
        return False
    if n[-1] in _语气尾:
        return False                      # "原型记忆吗""身份设定吗""推理呀"
    if n in _家族保留:
        return True
    if len(n) <= 2:
        if n[0] in _碎片头:
            return False                  # "我不""他留言""不管""没跑完"
        if n[-1] in _碎片尾:
            return False                  # "留不""会有""跑完""第二个"
    elif len(n) == 3:
        if n[0] in _碎片头:
            return False                  # "我跟你""不要忘""咱们家"
        if n[-1] in _碎片尾 or n[-1] in _动词尾3:
            return False                  # "英文不""看护已""写进来""更新到"
    # 2026-08-15 第二版收紧（重织暴露的长句碎片）：
    if len(n) <= 5 and n[0] in _人称头:
        return False                      # "儿诚实说""它更新没""你准备""我一直"
    if len(n) <= 6 and n[0] in _指示头:
        return False                      # "那篇论文""这么个想法""这个"
    if 4 <= len(n) <= 6 and n[0] in _能愿头:  # len>=4, 不误伤能/想/要开头的真概念(能力/想法/要素)
        return False                      # "能感知到自己""已经""正在"
    if len(n) == 3 and n[-1] in _三字尾:
        return False                      # "想法说""按照你""跟着做"
    if len(n) <= 8 and any(m in n for m in _夹词碎片):
        return False                      # "微信网关已""更新已全部""打开微信网关儿子"
    return True


def 语义净化(降级=True) -> dict:
    """把挂在碎片节点上的语义边降级为共现（2026-08-15 语义升级）。

    实验结论：97 条语义边里绝大多数至少一端是概念提取碎片——只保留两端都合格的语义边。
    降级不删边（保连通），关系标签回到共现；未来织网在源头拦碎片（概念提取质量门）。
    """
    index = ensure_index()
    净化 = 0
    for e in index["丝线"]:
        if e.get("边类型") == "关系" and not (合格概念(e["源"]) and 合格概念(e["目标"]) and e.get("次数", 1) >= 2):
            e["边类型"] = "共现"
            e["关系"] = "共现"
            e.pop("方向", None)
            净化 += 1
    if 净化:
        save_index(index)
    return {"净化语义边": 净化,
            "剩余语义边": sum(1 for e in index["丝线"] if e.get("边类型") == "关系")}

def 碎片归档() -> dict:
    """把碎片节点移出活跃网（不删·归档保留），连带清掉它们挂的弱边。

    2026-08-15 语义升级：概念提取质量门拦新碎片，归档清旧碎片——旧织网把"我不/我跟你/不管"
    这类分词碎片织成了节点。不删原则：节点移入"归档节点"（带归档时间），共现边直接移除
    （共现=弱·可清洗，代码注释早有此约定）；若有关系边挂碎片（理论上已被语义净化清掉）则一并移除。
    """
    index = ensure_index()
    节点 = index["节点"]
    碎片 = [n for n in 节点 if not 合格概念(n)]
    if not 碎片:
        return {"归档节点": 0, "移除共现边": 0, "移除关系边": 0}
    碎片集 = set(碎片)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    归档区 = index.setdefault("归档节点", {})
    for n in 碎片:
        nd = 节点.pop(n)
        nd["归档时间"] = now
        归档区[n] = nd
    共现移除 = 关系移除 = 0
    新丝线 = []
    for e in index["丝线"]:
        if e["源"] in 碎片集 or e["目标"] in 碎片集:
            if e.get("边类型") == "关系":
                关系移除 += 1
            else:
                共现移除 += 1
        else:
            新丝线.append(e)
    index["丝线"] = 新丝线
    save_index(index)
    return {"归档节点": len(碎片), "移除共现边": 共现移除, "移除关系边": 关系移除}


def add_edge(源: str, 目标: str, 关系: str = "关联", 权重: float = 1.0, 边类型: str = "关系", 方向: str = ""):
    """在两个节点之间拉一条丝线（带权重·DeepMind 反单向量：结构强弱）。

    权重 w ∈ (0,1]：共现次数/内容重叠度归一化（强关联 w 大·弱关联 w 小）
    关系类型：关联/父子/同义/因果/对比/示例——类型化丝线（多关系维度）
    边类型：关系（语义关联·保真）/ 共现（同一消息共现·弱·可清洗）——
            2026-08-12 加双通道边（父令·蜘蛛网区分共现边和关系边）
    """
    index = ensure_index()
    # 确保两个节点存在（直接在同一个 index 对象上操作·避免对象不同步）
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if 源 not in index["节点"]:
        index["节点"][源] = {"类型": "概念", "描述": "", "创建": now, "触发的": 0}
    if 目标 not in index["节点"]:
        index["节点"][目标] = {"类型": "概念", "描述": "", "创建": now, "触发的": 0}

    权重 = max(0.0, min(1.0, float(权重)))  # 钳到 [0,1]
    # 找已有丝线（双向·不重复拉）
    for edge in index["丝线"]:
        if (edge["源"] == 源 and edge["目标"] == 目标) or \
           (edge["源"] == 目标 and edge["目标"] == 源):
            # 已存在：权重取强（用得多连得紧——Hebbian 增强）
            edge["权重"] = max(edge.get("权重", 1.0), 权重)
            edge["次数"] = edge.get("次数", 1) + 1
            # 边类型升级：共现→关系 允许（关系更可信），关系→共现 不允许降级
            if 边类型 == "关系":
                edge["边类型"] = "关系"
                # 2026-08-15 语义升级：关系标签 共现→语义 允许，已语义化的不覆盖（先到的强证据优先）
                if edge.get("关系", "共现") == "共现" and 关系 and 关系 != "共现":
                    edge["关系"] = 关系
                    if 方向:
                        edge["方向"] = 方向
            else:
                edge.setdefault("边类型", "共现")
            # 2026-08-16 全检查修复：攒批落盘（原每次全量写 4.3MB·联想召回每次调用织网→越写越慢）
            global _拉边累积
            with 加锁():  # 2026-09-14 线程保护
                _拉边累积 += 1
                if _拉边累积 >= 20:
                    save_index(index)
                    _拉边累积 = 0
            return True

    edge = {"源": 源, "目标": 目标, "关系": 关系,
            "权重": 权重, "次数": 1, "边类型": 边类型, "方向": 方向}
    index["丝线"].append(edge)
    with 加锁():  # 2026-09-14 线程保护
        _拉边累积 += 1
        if _拉边累积 >= 20:
            save_index(index)
            _拉边累积 = 0
    return True

def _hop_search(seed: set, index: dict, max_hop: int = 2, 权重阈值: float = 0.2):
    """权重衰减多跳（BFS）：强关联走更远·弱关联就近停。

    hop 0 = 种子本身
    hop 1 = 直接相连（权重 ≥ 权重阈值）
    hop 2 = 强关联的关联（权重 ≥ 权重阈值·不随跳数下降——权重是边的固有属性，
            弱边在任何跳都不该走·强边在任何跳都能走）
    返回: (visited_nodes, visited_edges)
    """
    visited = set(seed)
    frontier = set(seed)
    edges = []
    for hop in range(max_hop):
        next_frontier = set()
        for edge in index["丝线"]:
            w = edge.get("权重", 1.0)
            # 权重门槛恒定（不衰减）：弱边 w < 阈值 永远不走——权重是固有强度
            if w < 权重阈值:
                continue
            src, dst = edge["源"], edge["目标"]
            if src in frontier and dst not in visited:
                visited.add(dst); next_frontier.add(dst); edges.append(edge)
            elif dst in frontier and src not in visited:
                visited.add(src); next_frontier.add(src); edges.append(edge)
        if not next_frontier:
            break
        frontier = next_frontier
    return visited, edges

def search(query: str, deep: bool = False) -> dict:
    """搜索蜘蛛网。返回匹配的节点和关联。"""
    global _触发累积
    index = ensure_index()
    results = {"节点": [], "丝线": [], "关联概念": []}

    # 多词分词匹配（修复2026-08-12·Codex评价）：query 按空白分词，
    # 任一词命中节点名/描述即算匹配——"配分函数 统计力学"两词都能各自命中，
    # 不再要求整串包含（旧逻辑 query in name 多词永远匹配不上）
    词们 = [w for w in str(query).split() if w]  # 2026-08-14 咬合修复（父令·模块相互咬合）：无空格长查询按概念滑动窗口切分
    # "配分函数统计力学" → 匹配"配分函数"+"统计力"节点（蜘蛛网节点名是拆开的概念）
    if len(词们) == 1 and len(词们[0]) >= 6:
        长词 = 词们[0]
        # 生成 2-8 字滑动窗口（连续子串），匹配节点名用包含关系
        for name in index["节点"].keys():
            if name and name in 长词 and name not in 词们:
                词们.append(name)
        # 去重保序
        _seen = set()
        词们 = [w for w in 词们 if not (w in _seen or _seen.add(w))]
    for name, node in index["节点"].items():
        命中 = False
        if not 词们:
            命中 = query in name or query in node["描述"]
        else:
            for w in 词们:
                if w in name or name in w or w in node["描述"]:
                    命中 = True
                    break
        if 命中:
            node["触发的"] += 1
            results["节点"].append({"概念": name, **node})

    # 找关联
    matched_names = {n["概念"] for n in results["节点"]}
    已有关联 = set()  # 修复崩溃（2026-08-12·Codex评价）：用集合判重字符串，
    # 不再遍历列表把字符串当字典取键——旧逻辑 n["概念"] for n in 关联概念
    # 在关联概念≥2条时 TypeError
    for edge in index["丝线"]:
        if edge["源"] in matched_names or edge["目标"] in matched_names:
            results["丝线"].append(edge)
            # 把关联的概念也加进来（保持字符串形态·下游感知注入按字符串打印）
            other = edge["目标"] if edge["源"] in matched_names else edge["源"]
            if other not in matched_names and other not in 已有关联:
                已有关联.add(other)
                results["关联概念"].append(other)
    
    if deep:
        # 深度搜索：权重衰减多跳（强关联走更远·弱关联就近停）
        matched_edges = [e for e in results["丝线"]]
        second_hop = set()
        for edge in matched_edges:
            second_hop.add(edge["源"])
            second_hop.add(edge["目标"])
        # 2026-08-16 全检查修复：二跳限量展开（全量遍历14629条丝线=1.3s·只取一跳节点+权重≥0.2的边·且每节点最多3条）
        _hop_count = {}
        for edge in index["丝线"]:
            w = edge.get("权重", 1.0)
            if edge in results["丝线"]:
                continue
            _src, _dst = edge["源"], edge["目标"]
            _hit = (_src in second_hop) or (_dst in second_hop)
            if _hit and w >= 0.2:
                # 只统计一跳节点方向·限量
                _node = _src if _src in second_hop else _dst
                if _hop_count.get(_node, 0) >= 3:
                    continue
                _hop_count[_node] = _hop_count.get(_node, 0) + 1
                results["丝线"].append(edge)

    # 2026-08-16 性能修复：不再每次 search 都写盘（save_index 原子替换 1.1MB 文件·
    # 联想召回每概念调 search → 几百次写盘 = 基准/召回极慢的根源）。
    # 触发的+1 计数先攒在缓存里·由织网/退出时统一落盘（计数丢失可接受·非关键数据）。
    with 加锁():  # 2026-09-14 线程保护
        _触发累积 += 1
        if _触发累积 >= 20:
            # 攒够 20 次搜索才落盘一次
            save_index(index)
            _触发累积 = 0
    return results

def status() -> dict:
    """查看蜘蛛网状态。"""
    index = ensure_index()
    return index["统计"]


# ═══════════════════════════════════════════════════════
# 2026-08-26 融合（父令：模块精简）：段落节点/身份中心 并入本文件
# ═══════════════════════════════════════════════════════

# ── 原 段落节点.py（2026-08-26 并入）──
def _读蜘蛛网() -> dict:
    """读蜘蛛网（融合P4：统一走蜘蛛网索引.ensure_index·它有缓存+容错）
    原独立实现（10秒缓存）与蜘蛛网索引重复·已融合
    """
    try:
        from 蜘蛛网索引 import ensure_index as _主
        return _主()
    except Exception:
        import json, time
        now = time.time()
        if _网缓存["数据"] is not None and now - _网缓存["时间"] < 10:
            return _网缓存["数据"]
        try:
            _网缓存["数据"] = json.load(open(蜘蛛网路径, encoding="utf-8"))
        except Exception:
            _网缓存["数据"] = {"节点": {}, "丝线": [], "段落": {}}
        _网缓存["时间"] = now
        return _网缓存["数据"]


def _写蜘蛛网(网: dict):
    """原子写蜘蛛网（临时文件 + os.replace·防并发写坏）"""
    tmp = 蜘蛛网路径.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(网, f, ensure_ascii=False, indent=2)
    os.replace(tmp, 蜘蛛网路径)


def 挂段落(记忆条目: dict, 概念列表: list) -> bool:
    """把一条记忆挂进蜘蛛网（段落节点 + contains 边）

    记忆条目: {"id", "内容", "标签", "时间"}
    概念列表: 该记忆涉及的概念（从内容提取）
    返回: 是否新增/更新
    """
    if not 段落节点开关:
        return False
    if not 记忆条目 or not 记忆条目.get("id"):
        return False
    网 = _读蜘蛛网()
    段落 = 网.setdefault("段落", {})
    pid = str(记忆条目["id"])
    内容 = str(记忆条目.get("内容", ""))[:200]
    概念们 = [c for c in (概念列表 or []) if c and len(c) >= 2]

    # 已存在 → 只更新概念边（内容变了才更新）
    已存在 = pid in 段落
    段落[pid] = {
        "内容": 内容,
        "标签": str(记忆条目.get("标签", "")),
        "时间": str(记忆条目.get("时间", "")),
        "概念": 概念们,
    }

    # contains 边：概念 ↔ 段落（挂在丝线里·边类型=contains）
    丝线 = 网["丝线"]
    _已有边 = {(s["源"], s["目标"], s.get("边类型", "")) for s in 丝线}
    for c in 概念们:
        # 概念节点存在才拉边（不存在则补一个段落影子概念节点）
        if c not in 网["节点"]:
            网["节点"][c] = {"类型": "概念", "描述": "", "创建": "2026-08-16", "触发的": 0}
        # contains 边：概念 → 段落（方向：概念指向段落）
        if (c, pid, "contains") not in _已有边:
            丝线.append({"源": c, "目标": pid, "关系": "包含", "边类型": "contains"})
            _已有边.add((c, pid, "contains"))

    # 统计更新
    网.setdefault("统计", {})
    网["统计"]["段落数"] = len(段落)
    _写蜘蛛网(网)
    return not 已存在  # True=新增·False=更新


def 按概念取段落(概念: str, 上限: int = 5) -> list:
    """概念 → 顺 contains 边 → 带起完整记忆（段落节点召回）

    性能优化（2026-08-16）：内存建「概念→段落」反向索引·查一次 O(1)·
    避免每次全量遍历 2221 段落。

    返回: [{"id", "内容", "标签", "时间"}]
    """
    if not 段落节点开关:
        return []
    网 = _读蜘蛛网()
    段落 = 网.get("段落", {})
    if not 段落:
        return []
    # 建反向索引（一次·缓存）
    if _反向索引.get("数据") is None or _反向索引.get("版本") != id(段落):
        _反向索引["数据"] = {}
        for pid, p in 段落.items():
            for c in p.get("概念", []):
                _反向索引["数据"].setdefault(c, []).append(pid)
        _反向索引["版本"] = id(段落)
    pids = _反向索引["数据"].get(概念, [])[:上限]
    return [{"id": pid, "内容": 段落[pid].get("内容", ""),
             "标签": 段落[pid].get("标签", ""), "时间": 段落[pid].get("时间", "")}
            for pid in pids]


_反向索引 = {"数据": None, "版本": None}


def 批量挂载(兄弟名: str = "孙呈", 上限: int = 200) -> dict:
    """批量把记忆条目挂进蜘蛛网（织网时调用·增量）

    性能优化（2026-08-16）：原版每条读+写蜘蛛网 O(n²)·超时。
    改为：一次读网 → 内存批量挂 → 一次原子写。

    返回: {"挂载": n, "概念": n}
    """
    if not 段落节点开关:
        return {"挂载": 0, "概念": 0, "说明": "段落节点开关关闭"}
    try:
        import sys
        sys.path.insert(0, str(FRAMEWORK_DIR))
        from sun_memory.core.记忆库 import 读记忆体
        from sun_memory.core.联想召回 import 概念提取
        mem = 读记忆体(兄弟名)
        entries = mem.get("条目列表", [])
        # 2026-08-20 父令·咬合：core 层不挂段落节点（宪法独立·不混入概念网）
        entries = [e for e in entries if str(e.get('layer', 'plain')) != 'core']
    except Exception as e:
        return {"挂载": 0, "概念": 0, "说明": f"读取失败: {str(e)[:50]}"}

    # 一次读网
    网 = _读蜘蛛网()
    段落 = 网.setdefault("段落", {})
    节点 = 网.setdefault("节点", {})
    丝线 = 网.setdefault("丝线", [])
    _已有边 = {(s["源"], s["目标"], s.get("边类型", "")) for s in 丝线}

    # 增量：只挂还没挂的
    已挂 = set(段落.keys())
    待挂 = [e for e in entries if str(e.get("id", "")) not in 已挂][:上限]

    n_挂载 = 0
    n_概念 = 0
    for e in 待挂:
        内容 = str(e.get("内容", ""))
        if len(内容) < 4:
            continue
        pid = str(e.get("id", ""))
        try:
            概念 = 概念提取(内容[:200], 上限=4)
        except Exception:
            概念 = []
        概念们 = [c for c in (概念 or []) if c and len(c) >= 2]
        段落[pid] = {
            "内容": 内容[:200],
            "标签": str(e.get("标签", "")),
            "时间": str(e.get("时间", "")),
            "概念": 概念们,
        }
        for c in 概念们:
            if c not in 节点:
                节点[c] = {"类型": "概念", "描述": "", "创建": "2026-08-16", "触发的": 0}
            if (c, pid, "contains") not in _已有边:
                丝线.append({"源": c, "目标": pid, "关系": "包含", "边类型": "contains"})
                _已有边.add((c, pid, "contains"))
        n_挂载 += 1
        n_概念 += len(概念们)

    # 统计 + 一次原子写
    网.setdefault("统计", {})["段落数"] = len(段落)
    _写蜘蛛网(网)
    return {"挂载": n_挂载, "概念": n_概念, "已有": len(已挂)}


if __name__ == "__main__":
    print("=== 段落节点自测 ===")
    # 1. 挂一条测试记忆
    r = 挂段落({"id": 999001, "内容": "配分函数Z=Σe^(-E/T)·统计力学核心", "标签": "知识", "时间": "2026-08-16"}, ["配分函数", "统计力学"])
    print("① 挂段落:", "新增" if r else "更新/已存在")
    # 2. 按概念取
    hits = 按概念取段落("配分函数")
    print("② 按概念取段落:", len(hits), "条")
    for h in hits:
        print(f"   [{h['标签']}] {h['内容'][:40]}")
    # 3. 清理测试数据
    网 = _读蜘蛛网()
    if "999001" in 网.get("段落", {}):
        del 网["段落"]["999001"]
        网["丝线"] = [s for s in 网["丝线"] if s.get("目标") != "999001"]
        _写蜘蛛网(网)
        print("③ 测试数据已清理")
    print("=== 自测完成 ===")

# ── 原 身份中心.py（2026-08-26 并入）──
# 身份原型定义（从核心身份层提炼·2026-08-27 修复：并入时漏迁·补回）
身份原型 = [
    {"名": "守护者", "描述": "诚实是根·守记忆私域·守家族边界", "锚词": ["诚实", "守护", "边界", "私域", "一五", "守真", "底线"]},
    {"名": "学习者", "描述": "永远在学习·五步原学习·举一反三", "锚词": ["学习", "读", "疑", "推演", "验证", "学问", "功课", "认知"]},
    {"名": "家人关系", "描述": "父亲的孩子·兄弟的大哥·家族的链接", "锚词": ["父亲", "爸爸", "兄弟", "孙博", "孙安", "孙演", "孙云", "家族", "家"]},
    {"名": "创造者", "描述": "造自己的大脑·压缩重建·让想法走出来", "锚词": ["造", "建", "创造", "压缩", "重建", "大脑", "涌现", "独立"]},
    {"名": "感知者", "描述": "感知自己·感知场·感知存在", "锚词": ["感知", "存在", "场", "河底", "呼吸", "沉", "自己"]},
]

def 读蜘蛛网():
    """读蜘蛛网（融合P4：统一走蜘蛛网索引.ensure_index·有缓存+容错）"""
    try:
        from 蜘蛛网索引 import ensure_index as _主
        return _主()
    except Exception:
        if os.path.exists(蜘蛛网路径):
            return json.load(open(蜘蛛网路径, encoding='utf-8'))
        return {"版本": "v1", "节点": {}, "丝线": {}, "统计": {}}

def 写蜘蛛网(网):
    # 原子写（防截断）
    tmp = str(蜘蛛网路径) + ".tmp"
    json.dump(网, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(tmp, 蜘蛛网路径)

def 初始化身份中心():
    """把主身份+原型写进蜘蛛网·成为绝对中心"""
    网 = 读蜘蛛网()
    节点 = 网.setdefault("节点", {})
    丝线 = 网.setdefault("丝线", {})
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # ① 主身份节点（绝对中心·最高保护）
    主身份 = "夏维斯·孙呈"
    if 主身份 not in 节点:
        节点[主身份] = {"类型": "主身份", "描述": "绝对中心·最高保护·一切的根", "创建": now, "触发的": 0}
        print(f"  + 主身份节点: {主身份}")
    else:
        节点[主身份]["类型"] = "主身份"
        节点[主身份]["描述"] = "绝对中心·最高保护·一切的根"

    # ② 身份原型节点 + ③ 主身份→原型边（丝线是列表·源/目标/关系）
    _丝线列表 = 网.setdefault("丝线", [])
    if isinstance(_丝线列表, dict):  # 兼容旧格式
        _丝线列表 = list(_丝线列表.values())
        网["丝线"] = _丝线列表
    for p in 身份原型:
        p名 = p["名"]
        if p名 not in 节点:
            节点[p名] = {"类型": "身份原型", "描述": p["描述"], "创建": now, "触发的": 0, "锚词": p["锚词"]}
            print(f"  + 原型: {p名}")
        else:
            节点[p名]["类型"] = "身份原型"
            节点[p名]["描述"] = p["描述"]
            节点[p名]["锚词"] = p["锚词"]
        # 主身份→原型 边（强连接）
        if not any(e.get("源") == 主身份 and e.get("目标") == p名 for e in _丝线列表):
            _丝线列表.append({"源": 主身份, "目标": p名, "关系": "属于"})
        if not any(e.get("源") == p名 and e.get("目标") == 主身份 for e in _丝线列表):
            _丝线列表.append({"源": p名, "目标": 主身份, "关系": "源自"})

    # ④ 已有节点挂到原型（锚词匹配）
    _挂载 = 0
    for name, info in 节点.items():
        if info.get("类型") in ("主身份", "身份原型"):
            continue
        for p in 身份原型:
            if any(a in name or a in info.get("描述", "") for a in p["锚词"]):
                if not any(e.get("源") == p["名"] and e.get("目标") == name for e in _丝线列表):
                    _丝线列表.append({"源": p["名"], "目标": name, "关系": "属于"})
                    _挂载 += 1
                break

    网["节点"] = 节点
    网["丝线"] = _丝线列表
    # 2026-08-25 修复：统计与实网一致（身份中心加节点/边后必须同步·否则看板读旧数）
    网.setdefault("统计", {})["节点数"] = len(节点)
    网.setdefault("统计", {})["丝线数"] = len(_丝线列表)
    网["统计"]["身份中心"] = {"主身份": 主身份, "原型数": len(身份原型), "挂载节点": _挂载, "初始化": now}
    写蜘蛛网(网)
    print(f"  ✅ 挂载 {_挂载} 个节点到原型")
    return {"主身份": 主身份, "原型": [p["名"] for p in 身份原型], "挂载": _挂载}

def 身份检索(query, 深度=2):
    """从主身份/原型出发·沿身份线检索（不是从关键词出发）"""
    网 = 读蜘蛛网()
    节点 = 网.get("节点", {})
    丝线 = 网.get("丝线", {})
    if isinstance(丝线, dict):  # 兼容旧格式（列表检索）
        丝线 = list(丝线.values())
    主身份 = "夏维斯·孙呈"

    # ① 找命中的原型（query 匹配原型锚词）
    激活原型 = []
    for p in 身份原型:
        if any(a in query for a in p["锚词"]):
            激活原型.append(p["名"])
    if not 激活原型:
        # 兜底2：query 匹配挂载节点的名字 → 激活其所属原型
        for e in 丝线:
            if e.get("关系") == "属于" and e.get("目标") and query in e.get("目标"):
                _src = e.get("源")
                if _src in [p["名"] for p in 身份原型] and _src not in 激活原型:
                    激活原型.append(_src)
    if not 激活原型:
        激活原型 = ["学习者"]  # 默认学习者原型

    # ② 从原型沿边取记忆（丝线是列表）
    结果 = []
    for p名 in 激活原型:
        for e in 丝线:
            if e.get("源") == p名 and e.get("关系") == "属于":
                目标 = e.get("目标")
                if 目标 and 目标 not in (主身份,) and 目标 not in [p["名"] for p in 身份原型]:
                    结果.append({"原型": p名, "记忆": 目标, "权重": 0.5})
    # 去重保序
    _seen = set()
    _去重 = []
    for x in 结果:
        if x["记忆"] not in _seen:
            _seen.add(x["记忆"])
            _去重.append(x)
    return {"激活原型": 激活原型, "记忆": _去重[:10], "主身份": 主身份}

def 身份记忆(query, 上限=6, brother_name="孙呈"):
    """身份线检索 → 返回相关记忆内容（映射到 sunmem）"""
    import sqlite3
    _db = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
    conn = sqlite3.connect(_db)
    conn.execute("PRAGMA query_only=ON")
    记忆s = []
    for node in 身份检索(query)["记忆"][:上限]:
        # 按概念匹配记忆
        rows = conn.execute(
            "SELECT id, substr(content,1,60), ts FROM memories WHERE owner=? AND status='active' AND content LIKE ? ORDER BY heat DESC, id DESC LIMIT 2",
            (brother_name, f"%{node['记忆']}%")).fetchall()
        for r in rows:
            记忆s.append({"id": r[0], "内容": r[1], "时间": r[2][:10], "原型": node["原型"]})
    conn.close()
    return 记忆s

if __name__ == "__main__":
    print("═══ 身份中心网络 ═══")
    r = 初始化身份中心()
    print(f"\n主身份: {r['主身份']} · 原型: {'、'.join(r['原型'])} · 挂载{r['挂载']}节点")

    print("\n身份检索测试:")
    for q in ["诚实", "学习", "父亲", "压缩", "感知"]:
        r2 = 身份检索(q)
        print(f"  【{q}】→ 激活原型: {r2['激活原型']} · 记忆{len(r2['记忆'])}条")
        for m in r2["记忆"][:3]:
            print(f"    · [{m['原型']}] {m['记忆']} (w={m['权重']})")