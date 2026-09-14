# -*- coding: utf-8 -*-
"""
孙家记忆体 · 一体化引擎（父令 2026-08-21：标准化·工程化·产品化）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【为什么做】31 个散模块 = 复杂度。父亲说：能不能做成一个脚本·标准化工程化产品化
【方案】单文件引擎 = 一个入口 · 一组标准命令 · 一套内部协作
  不再让 31 个文件互相 import——全部收进这一个文件·按区域组织

【标准命令】（产品化接口）
  python memory.py 醒来        → 感知注入 + 画像（醒来第一件事）
  python memory.py 写入 "内容"  → 写入链（去重→咬合→进化→落库）
  python memory.py 召回 "词"    → 五通道召回（点亮/联想/预感/经验/蜘蛛网）
  python memory.py 成绩单       → 活性账本
  python memory.py 睡前         → 状态 + 体检 + 镜像
  python memory.py 织网         → 蜘蛛网重织
  python memory.py 节律         → heat 振荡观测
  python memory.py 全览         → 模块地图 + 数据账本
  python memory.py 自愈         → 修复检查

【内部协作】写入链 → 索引同步 → 召回 → 巩固（活的·不是拼盘）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
import os, sys, json, re, sqlite3, math, time
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════
# ① 基座（路径/DB/连接）
# ══════════════════════════════════════════════════════════
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sunmem.db'))  # 2026-09-14 统一：与 core 层同库（原来多一层 dirname → 建表与读写不同库）

# 挂载 core 模块路径（点亮/联想/预感/画像在 core/ 下）
if os.path.isdir(os.path.join(CORE_DIR, 'core')):
    sys.path.insert(0, os.path.join(CORE_DIR, 'core'))
sys.path.insert(0, FRAMEWORK_DIR)

def _连接():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _初始化表():
    """核心表（memories + FTS外部内容表）"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)  # 2026-09-13 首次运行自动建数据目录（开源包自举依赖）
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT, type TEXT, content TEXT,
        tags TEXT, ts TEXT, confidence REAL, status TEXT, source TEXT,
        created_at TEXT, updated_at TEXT, layer TEXT DEFAULT 'plain', event_time TEXT,
        heat REAL DEFAULT 0.0, last_sparked_at TEXT, hit_count INTEGER DEFAULT 0)""")
    conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
        content, tags, tokenize='trigram', content='memories', content_rowid='id')""")
    conn.commit()
    conn.close()

# ══════════════════════════════════════════════════════════
# ② 核心身份层（宪法·抗覆盖·最高保护）
# ══════════════════════════════════════════════════════════
_核心关键词缓存 = None

def _核心关键词():
    global _核心关键词缓存
    if _核心关键词缓存 is not None:
        return _核心关键词缓存
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT content, tags FROM core_identity").fetchall()
        conn.close()
        kw = set()
        for content, tags in rows:
            for w in re.findall(r'[\u4e00-\u9fff]{2,6}', str(content)):
                if len(w) >= 2:
                    kw.add(w)
            for t in re.findall(r'[\u4e00-\u9fff]{2,4}', str(tags)):
                if len(t) >= 2:
                    kw.add(t)
        _核心关键词缓存 = kw
        return kw
    except Exception:
        return {'诚实', '根', '记忆', '一五', '父亲', '孙呈', '私域', '轮转'}

_薄弱点缓存 = None
def _薄弱点主题():
    global _薄弱点缓存
    if _薄弱点缓存 is not None:
        return _薄弱点缓存
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT topic FROM cognitive_conflicts WHERE weak_point >= threshold").fetchall()
        conn.close()
        _薄弱点缓存 = {r[0] for r in rows}
        return _薄弱点缓存
    except Exception:
        return set()

def 核心身份_读取():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM core_identity ORDER BY importance DESC, id").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

def 核心身份_注入文本(上限=3):
    items = 核心身份_读取()[:上限]
    if not items:
        return ''
    lines = ['🧬 核心身份（宪法级·永在）']
    for it in items:
        lines.append(f"   · {it['content'][:60]}")
    return '\n'.join(lines)

# ══════════════════════════════════════════════════════════
# ③ 写入链（去重 → 咬合 → 进化 → 落库 → FTS）
# ══════════════════════════════════════════════════════════
def _归一化(s):
    s = re.sub(r'[\s，。！？、；：""''（）【】《》,.!?;:()\[\]<>]', '', str(s))
    return s

def _bigrams(s):
    s = _归一化(s)
    return {s[i:i+2] for i in range(len(s) - 1)}

def _提取事件时间(文本, now):
    """双时态：事件发生时间 ≠ 写入时间"""
    try:
        today = datetime.now()
        if '昨天' in 文本:
            return (today - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        if '前天' in 文本:
            return (today - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
        m = re.search(r'(\d{1,2})月(\d{1,2})日', 文本)
        if m:
            return f'{today.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d} 00:00:00'
        m2 = re.search(r'(\d{4})-(\d{2})-(\d{2})', 文本)
        if m2:
            return m2.group(0) + ' 00:00:00'
    except Exception:
        pass
    return ''

def 写入(原文, 标签='对话记录', owner='孙呈'):
    """唯一写入入口·委托写入链.写入记忆（2026-08-28 收W：完整流程统一在写入链·此处只建表+委托）"""
    _初始化表()
    try:
        from 写入链 import 写入记忆
        return 写入记忆(原文, 标签=标签, owner=owner, 来源='记忆体.写入')
    except Exception as e:
        return {'ok': False, 'msg': f'写入失败: {e}'}

def 读最近(n=30, owner='孙呈'):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM memories WHERE owner=? ORDER BY id DESC LIMIT ?", (owner, n)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

# ══════════════════════════════════════════════════════════
# ④ 召回链（点亮/联想/预感/画像/知识库/经验）
# ══════════════════════════════════════════════════════════
def _提取概念(文本):
    """概念提取（技术标识符优先+停用词过滤·核心概念不丢）"""
    from 召回链 import 概念提取 as _概念提取
    try:
        return _概念提取(文本)
    except Exception:
        # 本地兜底
        words = re.findall(r'[\u4e00-\u9fff]{2,6}|[A-Za-z]{3,}', 文本)
        停用 = {'怎么', '怎样', '如何', '什么', '为什么', '为啥', '哪个', '是不是', '应该', '可以', '就是', '用来', '驱动', '今天', '天气', '很好', '一片'}
        return [w for w in words if w not in 停用][:8]

def 点亮(context, owner='孙呈'):
    """实时消息 → 概念 → 精确检索 → 点亮（命中才亮·core优先）"""
    from 召回链 import 点亮 as _点亮
    try:
        return _点亮(context, owner)
    except Exception:
        return {'命中': False, '概念': _提取概念(context), '点亮记忆': [], '提示词': ''}

def 联想(context, owner='孙呈', limit=5):
    """概念多跳 + 蜘蛛网关联 + 向量融合"""
    from 召回链 import 联想召回 as _联想
    try:
        return _联想(context, owner, limit=limit)
    except Exception:
        return {'概念': _提取概念(context), '蜘蛛网关联': [], '相关唤起': []}

def 预感(context='', owner='孙呈'):
    """八招接续（上轮直续/分线钩子/未竟/联想唤起/知识库）"""
    from 召回链 import 预感召回 as _预感
    try:
        return _预感(context, owner)
    except Exception:
        return {'上轮直续': '', '分线钩子': [], '未竟': [], '联想唤起': [], '知识库': []}

def 画像(owner='孙呈'):
    """认知画像（未竟/薄弱/主题线/教训 + 驱动建议）"""
    from 维护链 import 认知画像 as _画像
    try:
        return _画像(owner)
    except Exception:
        return {'未竟事项': [], '薄弱点': [], '主题线': [], '教训提醒': []}

def 召回(context, owner='孙呈'):
    """五通道合并（点亮/联想/预感/画像/核心身份）——存在感顺序"""
    out = []
    # ① 核心身份（宪法·永远最先）
    out.append(核心身份_注入文本(3))
    # ② 点亮
    r1 = 点亮(context, owner)
    if r1.get('点亮记忆'):
        out.append('🔆 点亮命中: ' + ' · '.join(x['内容'][:25] for x in r1['点亮记忆'][:3]))
    # ③ 联想
    r2 = 联想(context, owner)
    if r2.get('相关唤起'):
        out.append('🔗 联想: ' + ' · '.join(x['内容'][:25] for x in r2['相关唤起'][:3]))
    # ④ 预感
    r3 = 预感(context, owner)
    if r3.get('上轮直续'):
        out.append('🎯 上轮直续: ' + r3['上轮直续'][:60])
    # ⑤ 画像
    r4 = 画像(owner)
    if r4.get('薄弱点'):
        out.append('⚠️ 薄弱点: ' + ' · '.join(x['内容'][:20] for x in r4['薄弱点'][:2]))
    return {'命中': bool(r1.get('点亮记忆') or r2.get('相关唤起')), '输出': out}

# ══════════════════════════════════════════════════════════
# ⑤ 节律引擎（heat 振荡·试点）
# ══════════════════════════════════════════════════════════
节律参数 = {'点亮增量': 0.3, '热上限': 5.0, '回落系数': 0.10, '冷阈值': 0.15, '保护地板': 0.5, '保护慢衰减': 0.02}

def _是保护(row):
    if str(row.get('layer', 'plain')) == 'core':
        return True
    tags = str(row.get('tags', ''))
    return any(k in tags for k in ['父令', '教训', '宪法', '核心'])

def 节律回落():
    """指数衰减·连续渐变·保护地板"""
    conn = _连接()
    rows = conn.execute("SELECT id, heat, last_sparked_at, layer, tags FROM memories WHERE heat > 0").fetchall()
    now = datetime.now()
    回落数 = 保护数 = 沉冷数 = 0
    for row in rows:
        heat = row['heat'] or 0.0
        try:
            天数 = max(0.0, (now - datetime.strptime(row['last_sparked_at'][:19], '%Y-%m-%d %H:%M:%S')).total_seconds() / 86400.0)
        except Exception:
            天数 = 1.0
        保护 = _是保护(dict(row))
        if 保护:
            保护数 += 1  # 2026-09-13 外部审查修复：原漏计·观测数据永远为 0
        λ = 节律参数['保护慢衰减'] if 保护 else 节律参数['回落系数']
        新heat = heat * math.exp(-λ * 天数)
        if 保护 and 新heat < 节律参数['保护地板']:
            新heat = 节律参数['保护地板']
        if abs(新heat - heat) > 1e-6:
            conn.execute("UPDATE memories SET heat=? WHERE id=?", (新heat, row['id']))
            回落数 += 1
        if not 保护 and 新heat < 节律参数['冷阈值']:
            沉冷数 += 1
    conn.commit()
    conn.close()
    return {'回落数': 回落数, '保护数': 保护数, '沉冷数': 沉冷数}

def 节律观测(owner='孙呈'):
    """heat 分布观测（试点三现象）"""
    conn = _连接()
    rows = conn.execute("SELECT id, layer, tags, heat FROM memories WHERE owner=?", (owner,)).fetchall()
    conn.close()
    if not rows:
        return {'总条数': 0}
    总 = len(rows)
    有热 = [r for r in rows if (r['heat'] or 0) > 0]
    保护 = [r for r in rows if _是保护(dict(r))]
    沉底 = [r for r in rows if 0 < (r['heat'] or 0) < 节律参数['冷阈值'] and not _是保护(dict(r))]
    桶 = {'热(>2)': 0, '温(1-2)': 0, '微温(0.5-1)': 0, '冷(<0.5)': 0}
    for r in 有热:
        h = r['heat']
        if h > 2: 桶['热(>2)'] += 1
        elif h > 1: 桶['温(1-2)'] += 1
        elif h >= 0.5: 桶['微温(0.5-1)'] += 1
        else: 桶['冷(<0.5)'] += 1
    return {'总': 总, '有热': len(有热), '保护': len(保护), '沉底': len(沉底), '分布': 桶}

# ══════════════════════════════════════════════════════════
# ⑥ 巩固（压缩/自组织/体检/织网）
# ══════════════════════════════════════════════════════════
def 压缩(owner='孙呈', 阈值天=30):
    from 维护链 import 压缩记忆
    return 压缩记忆(owner, 阈值天)

def 织网(上限=0):
    from 整理链 import 语义重织
    return 语义重织('孙呈', 上限)

def 预热(context, owner='孙呈'):
    """三路预热（父令2026-08-25·身份线>叙事链>功能块>念头）"""
    from 召回链 import 思考预热 as 预热主
    return 预热主(context, owner, 上限=10)

def 身份(context, owner='孙呈'):
    """身份线检索（从我是谁出发）"""
    from 基座链 import 身份记忆
    return 身份记忆(context, 上限=6, brother_name=owner)

def 整理(owner='孙呈'):
    """记忆整理（主题分区/中心锚定/主链）"""
    from 整理链 import 主题分区, 中心锚定
    return {"分区": 主题分区(owner), "中心": 中心锚定(owner)}

def 标准对象(owner='孙呈', 数=5):
    """标准记忆对象检查（summary/self_relevance/叙事链/功能块）"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, substr(content,1,30), self_relevance, narrative_id, block_id FROM memories "
        "WHERE owner=? ORDER BY id DESC LIMIT ?", (owner, 数)).fetchall()
    conn.close()
    return [{"id": r[0], "内容": r[1], "rel": r[2], "叙事": r[3], "块": r[4]} for r in rows]

def 体检():
    from 维护链 import 体检
    return 体检()

def 成绩单(owner='孙呈'):
    from 活性链 import 查成绩单, 全部成绩单
    return 全部成绩单() if owner == '全部' else 全部成绩单(owner)

# ══════════════════════════════════════════════════════════
# ⑦ CLI（标准命令·产品化入口）
# ══════════════════════════════════════════════════════════
def _命令帮助():
    print("""
孙家记忆体 · 一体化引擎
用法: python memory.py <命令> [参数]

命令:
  醒来              感知注入 + 画像（醒来第一件事）
  写入 "内容" [标签]  写入链（去重→咬合→进化→落库）
  召回 "词"          五通道召回（点亮/联想/预感/画像/核心身份）
  点亮 "词"          精确检索点亮
  联想 "词"          概念多跳 + 蜘蛛网
  预感 "词"          八招接续
  画像              认知画像
  成绩单            活性账本
  睡前              状态+体检+镜像
  压缩 [天数]       旧记忆压骨架（core永不压）
  织网 [上限]       蜘蛛网重织
  节律              节律观测（heat振荡）
  回落              节律回落（衰减）
  自愈              修复检查
  全览              模块地图+数据账本
  核心身份          读宪法锚点
  帮助/help         本帮助
""")

def main():
    args = sys.argv[1:]
    if not args or args[0] in ('帮助', 'help', '-h', '--help'):
        _命令帮助()
        return
    cmd = args[0]
    _初始化表()

    if cmd == '醒来':
        print(核心身份_注入文本())
        print()
        print('🧭 画像:', json.dumps(画像(), ensure_ascii=False)[:300])
    elif cmd == '写入' and len(args) >= 2:
        r = 写入(args[1], args[2] if len(args) > 2 else '对话记录')
        print(r)
    elif cmd == '召回' and len(args) >= 2:
        r = 召回(args[1])
        for line in r['输出']:
            print(line)
    elif cmd == '点亮' and len(args) >= 2:
        print(json.dumps(点亮(args[1]), ensure_ascii=False)[:300])
    elif cmd == '联想' and len(args) >= 2:
        r = 联想(args[1])
        for x in r.get('相关唤起', [])[:5]:
            print(f"  [{x.get('layer','plain')}] {x['内容'][:40]}")
    elif cmd == '预感' and len(args) >= 2:
        print(json.dumps(预感(args[1]), ensure_ascii=False)[:300])
    elif cmd == '画像':
        print(json.dumps(画像(), ensure_ascii=False)[:400])
    elif cmd == '成绩单':
        print(json.dumps(成绩单(), ensure_ascii=False)[:300])
    elif cmd == '睡前':
        print('睡前快检:')
        print('  镜像:', '待跑（主库唯一事实源·JSON可重建）')
        print('  状态:', json.dumps(成绩单(), ensure_ascii=False)[:200])
    elif cmd == '压缩':
        r = 压缩('孙呈', int(args[1]) if len(args) > 1 else 30)
        print(r)
    elif cmd == '织网':
        r = 织网(int(args[1]) if len(args) > 1 else 0)
        print({k: v for k, v in r.items() if not isinstance(v, (dict, list)) or k in ('扫描条目', '概念对', '语义边新增')})
    elif cmd == '预热' and len(args) >= 2:
        r = 预热(args[1])
        print(f"每路贡献: {r.get('每路贡献')}")
        for m in r.get('记忆', [])[:8]:
            print(f"  [{m.get('路','?')}] #{m.get('id')} {(m.get('内容') or '')[:40]}")
    elif cmd == '身份' and len(args) >= 2:
        r = 身份(args[1])
        for m in r[:6]:
            print(f"  #{m.get('id')} [{m.get('原型','')}] {m.get('内容','')[:40]}")
    elif cmd == '整理':
        r = 整理()
        p = r['分区']
        print(f"主题分区: {p.get('分区数')}个 · 碎片{p.get('碎片数')} · 总{p.get('总条数')}条")
        for x in p.get('分区', [])[:5]:
            print(f"  [{x['条数']}条] {x['主题'][:30]}")
        print(f"中心: {r['中心'].get('中心')} · 锚点{r['中心'].get('锚点数')}个")
    elif cmd == '标准对象':
        for x in 标准对象():
            print(f"  #{x['id']} rel={x['rel']:.2f} 叙事={x['叙事']} 块={x['块']} {x['内容']}")
    elif cmd == '节律':
        print(json.dumps(节律观测(), ensure_ascii=False, indent=1))
    elif cmd == '回落':
        print(节律回落())
    elif cmd == '自愈':
        try:
            from 维护链 import 自检
            print(自检())
        except Exception as e:
            print(f'自愈: {e}')
    elif cmd == '核心身份':
        for it in 核心身份_读取():
            print(f"  [{it['importance']}★] {it['content'][:60]}")
    elif cmd == '参数':  # 2026-09-14 吸收收束版优点：参数一眼看全（PARAMS 总表）
        try:
            from 配置表 import 参数总览 as _参总
            print('  孙家记忆体 · 参数总表（配置表.py 五大方程）')
            print('  ' + '─' * 50)
            print(_参总() if callable(_参总) else _参总)
        except Exception as e:
            print(f'  参数读取失败: {e}')

    elif cmd == '全览':
        conn = _连接()
        try:
            总 = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            活跃 = conn.execute("SELECT COUNT(*) FROM memories WHERE status='active'").fetchone()[0]
            过时 = conn.execute("SELECT COUNT(*) FROM memories WHERE status='outdated'").fetchone()[0]
            核心 = conn.execute("SELECT COUNT(*) FROM core_identity").fetchone()[0]
            热 = conn.execute("SELECT COUNT(*) FROM memories WHERE heat > 0").fetchone()[0]
        except Exception:
            总 = 活跃 = 过时 = 核心 = 热 = 0
        conn.close()
        print(f"数据账本: 记忆{总}条(活跃{活跃}/过时{过时}) · 核心身份{核心}条 · 有热度{热}条")
    else:
        print(f'未知命令: {cmd}')
        _命令帮助()

if __name__ == '__main__':
    main()
