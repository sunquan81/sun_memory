# -*- coding: utf-8 -*-
# 2026-08-26 数学化（父令：模块精简·做成方程式）：
# 活性方程.py 已建立——将 点亮(heat脉冲)/时间衰减(cover)/成绩单(账本) 统一成一条方程
# 本模块保留原实现（兼容）·活性方程.py 是新底座·后续逐步切换调用点

"""
节律回落引擎（父令 2026-08-20：让记忆活性像电波一样振荡——有脉冲·有回落·有节奏）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【论文依据】MIT MillerLab《Analog Cognition》：认知源于电波模拟计算——模拟值连续渐变
【问题】旧活性只增不减（点亮+1·从不回落）→ 不是振荡·是单向累积
【本引擎】heat 连续浮点·点亮脉冲拉升·时间推移指数衰减·保护底线
  点亮时：heat 上升（有上限·防无限涨）
  时间推移：按距上次点燃时长指数衰减（用得多回落慢·用得少回落快）
  保护：核心层/高自我相关/重要标记 → 慢衰减或最低热度地板（不凉死）
  沉冷：长期低 heat 且非保护 → 沉到冷层（仍保留·只是不热）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
import sqlite3, os, math, sys, time  # 2026-09-13 外部审查修复：__main__ 块用到 sys/time 但未导入
from datetime import datetime

DB_PATH = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))

# ── 节律参数（连续渐变·非开关）──
参数 = {
    '点亮增量': 0.3,          # 每次点亮 heat +0.3（上限封顶·防无限涨）
    '热上限': 5.0,            # heat 上限（防无限涨）
    '回落系数': 0.10,         # 指数衰减率 λ：每24小时衰减因子 e^(-λ)≈0.905（用得多回落慢）
    '冷阈值': 0.15,           # heat 低于此 → 沉冷层（不删·只是不热）
    '保护地板': 0.5,          # 保护记忆的最低热度（永不掉到地板下）
    '保护慢衰减': 0.02,       # 保护记忆的衰减率（比普通慢 5 倍）
}

# ═══ 2026-08-26 从原节律调度.py 迁入的常量 ═══
LOG = os.environ.get('节律日志路径', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', '节律观测日志.log'))

def 初始化():
    """memories 表加 heat/last_sparked_at 列（连续浮点·双时态活性）"""
    conn = sqlite3.connect(DB_PATH)
    cols = [r[1] for r in conn.execute('PRAGMA table_info(memories)').fetchall()]
    if 'heat' not in cols:
        conn.execute("ALTER TABLE memories ADD COLUMN heat REAL DEFAULT 0.0")
    if 'last_sparked_at' not in cols:
        conn.execute("ALTER TABLE memories ADD COLUMN last_sparked_at TEXT")
    conn.commit()
    conn.close()

def _连接():
    初始化()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _是保护记忆(row) -> bool:
    """保护判定（父令2026-08-20试点版）：必须匹配指定标签集合才启用热度地板
    去掉 hit_count≥10 机械判定——防噪音记忆靠访问次数被误保护"""
    layer = str(row['layer'] or 'plain')
    if layer == 'core':
        return True
    tags = str(row['tags'] or '')
    # 只认明确标签集合（#父令 #教训 #宪法 #core）
    for kw in ['父令', '教训', '宪法', 'core', '核心']:
        if kw in tags:
            return True
    return False

def 点亮(memory_id: int):
    """点亮：heat 脉冲上升（有上限·读取即写·流过就热）"""
    conn = _连接()
    row = conn.execute("SELECT heat, hit_count, layer, tags FROM memories WHERE id=?", (memory_id,)).fetchone()
    if not row:
        conn.close()
        return {'ok': False, 'msg': f'记忆 #{memory_id} 不存在'}
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    新heat = (row['heat'] or 0.0) + 参数['点亮增量']
    if 新heat > 参数['热上限']:
        新heat = 参数['热上限']
    conn.execute("UPDATE memories SET heat=?, last_sparked_at=?, hit_count=COALESCE(hit_count,0)+1 WHERE id=?",
                 (新heat, now, memory_id))
    conn.commit()
    conn.close()
    return {'ok': True, 'memory_id': memory_id, 'heat': round(新heat, 3)}

def 批量点亮(ids: list):
    """批量点亮：单连接批量写（2026-08-25 修复：原来逐条开连接·4042次=45秒）"""
    if not ids:
        return {'ok': True, '点亮数': 0}
    try:
        conn = _连接()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cnt = 0
        for i in ids:
            try:
                row = conn.execute("SELECT heat, layer, tags FROM memories WHERE id=?", (i,)).fetchone()
                if not row:
                    continue
                新heat = (row['heat'] or 0.0) + 参数['点亮增量']
                if 新heat > 参数['热上限']:
                    新heat = 参数['热上限']
                conn.execute("UPDATE memories SET heat=?, last_sparked_at=?, hit_count=COALESCE(hit_count,0)+1 WHERE id=?",
                             (新heat, now, i))
                cnt += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        return {'ok': True, '点亮数': cnt}
    except Exception as e:
        return {'ok': False, '错误': str(e)}

def 回落(now=None):
    """时间推移衰减：按距上次点燃时长指数衰减（连续渐变·非开关）
    普通：heat *= e^(-λ·天数)  保护：heat *= e^(-λ慢·天数) 且保底地板
    返回: {回落数, 保护数, 沉冷数}"""
    if now is None:
        now = datetime.now()
    conn = _连接()
    rows = conn.execute("SELECT id, heat, last_sparked_at, hit_count, layer, tags FROM memories WHERE heat > 0").fetchall()
    回落数 = 0
    保护数 = 0
    沉冷数 = 0
    for row in rows:
        heat = row['heat'] or 0.0
        if heat <= 0:
            continue
        # 距上次点燃的时长（天）
        try:
            last = datetime.strptime(row['last_sparked_at'][:19], '%Y-%m-%d %H:%M:%S')
            天数 = max(0.0, (now - last).total_seconds() / 86400.0)
        except Exception:
            天数 = 1.0  # 无记录·按1天算
        保护 = _是保护记忆(row)
        if 保护:
            λ = 参数['保护慢衰减']
            保护数 += 1
        else:
            λ = 参数['回落系数']
        # 指数衰减：连续渐变
        新heat = heat * math.exp(-λ * 天数)
        if 保护:
            # 保护地板：永不掉到地板下
            if 新heat < 参数['保护地板']:
                新heat = 参数['保护地板']
        # 更新
        if abs(新heat - heat) > 1e-6:
            conn.execute("UPDATE memories SET heat=? WHERE id=?", (新heat, row['id']))
            回落数 += 1
        # 沉冷检测：普通记忆长期低 heat → 标记冷（不删）
        if not 保护 and 新heat < 参数['冷阈值']:
            沉冷数 += 1
    conn.commit()
    conn.close()
    return {'回落数': 回落数, '保护数': 保护数, '沉冷数': 沉冷数}

def 热度排行(owner='孙呈', 上限=10):
    """热路径召回：heat 排序（热记忆浮出·像电波场强）"""
    conn = _连接()
    rows = conn.execute(
        "SELECT id, heat, hit_count, substr(content,1,30) c, layer FROM memories "
        "WHERE owner=? AND heat > 0 ORDER BY heat DESC LIMIT ?",
        (owner, 上限)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def 同步成绩单(memory_id=None):
    """成绩单同步：真实 heat 写入 memory_report_cards（对外展示一致）
    父令约束③：库里的 heat 和成绩单必须一致·否则振荡看不准"""
    conn = _连接()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if memory_id:
        rows = conn.execute("SELECT id, heat FROM memories WHERE id=?", (memory_id,)).fetchall()
    else:
        rows = conn.execute("SELECT id, heat FROM memories WHERE heat > 0").fetchall()
    n = 0
    for r in rows:
        # 成绩单 upsert 一行（memory_id + 最新 heat）
        conn.execute(
            "INSERT INTO memory_report_cards (memory_id, owner, action, score_delta, heat, note, ts) "
            "VALUES (?,?,?,?,?,?,?)",
            (r['id'], '孙呈', '节律同步', 0, round(r['heat'], 3), '节律回落引擎同步', now))
        n += 1
    conn.commit()
    conn.close()
    return {'同步数': n}

def 观测日志(owner='孙呈'):
    """试点观测日志（父令2026-08-20）：heat 分布·升温/降温/触地板/沉河底
    返回可打印的统计——观察振荡是否成立·多路径是否断层·有无副作用"""
    conn = _连接()
    rows = conn.execute(
        "SELECT id, layer, tags, heat, hit_count, status FROM memories WHERE owner=?",
        (owner,)).fetchall()
    conn.close()
    if not rows:
        return {'总条数': 0}
    总 = len(rows)
    有热度 = [r for r in rows if (r['heat'] or 0) > 0]
    零热 = [r for r in rows if not (r['heat'] or 0) > 0]
    保护 = [r for r in rows if _是保护记忆(r)]
    触地板 = [r for r in rows if (r['heat'] or 0) <= 参数['保护地板'] and _是保护记忆(r)]
    沉河底 = [r for r in rows if 0 < (r['heat'] or 0) < 参数['冷阈值'] and not _是保护记忆(r)]
    # heat 分布（分桶）
    buckets = {'热(>2.0)': 0, '温(1-2)': 0, '微温(0.5-1)': 0, '冷(<0.5)': 0}
    for r in 有热度:
        h = r['heat']
        if h > 2.0: buckets['热(>2.0)'] += 1
        elif h > 1.0: buckets['温(1-2)'] += 1
        elif h >= 0.5: buckets['微温(0.5-1)'] += 1
        else: buckets['冷(<0.5)'] += 1
    return {
        '总条数': 总,
        '有热度': len(有热度),
        '零热': len(零热),
        '保护记忆': len(保护),
        '触地板(保护最低)': len(触地板),
        '沉河底(冷且非保护)': len(沉河底),
        '分布': buckets,
        '热上限样本': [{'id': r['id'], 'heat': round(r['heat'], 2)} for r in sorted(有热度, key=lambda x: -x['heat'])[:3]],
    }

if __name__ == '__main__':
    初始化()
    print('═══ 节律回落引擎 · 参数 ═══')
    print('点亮增量 0.3 · 上限 5.0 · 回落系数 0.10/天 · 保护地板 0.5')
    print('用法: 点亮(记忆id) · 回落() · 热度排行() · 同步成绩单()')


# ═══════════════════════════════════════════════════════
# 2026-08-26 融合（父令：模块精简）：节律调度.跑一圈 并入本文件
# ═══════════════════════════════════════════════════════
def 跑一圈(轮次):
    # 2026-08-26 自引用修复：回落/观测日志在本文件直接可用
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    回落结果 = 回落()
    观测 = 观测日志('孙呈')
    # 落盘
    line = (f"[{now}] 轮#{轮次} 回落={回落结果} | "
            f"分布={观测.get('分布')} | 保护={观测.get('保护记忆')} "
            f"触地板={观测.get('触地板(保护最低)')} 沉河底={观测.get('沉河底(冷且非保护)')} "
            f"热上限={观测.get('热上限样本')}")
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    print(line)
    return 观测

if __name__ == '__main__':
    间隔 = int(sys.argv[1]) if len(sys.argv) > 1 else 1800  # 默认30分钟
    print(f'节律回落调度器启动·每{间隔}秒跑一圈·日志→{LOG}')
    # 先跑一圈（启动即观测基线）
    跑一圈('启动')
    # 初始化观测基线（记录初始 heat 分布）
    # 2026-08-26 自引用修复：观测日志在本文件直接可用
    基线 = 观测日志('孙呈')
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(f"[基线] 初始观测: {基线}\n")
    print(f"[基线] {基线}")
    轮次 = 1
    while True:
        time.sleep(间隔)
        轮次 += 1
        try:
            跑一圈(轮次)
        except Exception as e:
            with open(LOG, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now()}] 轮#{轮次} 异常: {e}\n")
            print(f'异常: {e}')