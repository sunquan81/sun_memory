# -*- coding: utf-8 -*-
"""记忆生命流数据（记忆体星空 v9：动态显示自组织/自整理/点亮/回落行为）
被 main.js 调用·输出 JSON：自组织簇·小时叙事·节律日志·点亮事件"""
import sqlite3, json, os, sys, re
from datetime import datetime

DB = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sunmem.db'))
LOG = os.environ.get('节律日志路径', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', '节律观测日志.log'))
蜘蛛网 = os.environ.get("蜘蛛网_INDEX", os.path.join(os.path.dirname(os.path.abspath(__file__)), "蜘蛛网", "索引.json"))


def main():
    out = {'簇': [], '叙事': [], '节律日志': [], '点亮': [], '热度': {}, '归档数': 0, '总数': 0}

    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row

        # 总数/归档
        out['总数'] = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        out['归档数'] = conn.execute("SELECT COUNT(*) FROM memories WHERE status='outdated'").fetchone()[0]

        # 热度（热记忆标签→节点）
        rows = conn.execute("SELECT content, tags, heat, layer, ts FROM memories WHERE heat > 0.05 ORDER BY heat DESC LIMIT 40").fetchall()
        agg = {}
        for r in rows:
            h = r['heat'] or 0.0
            for kw in ['父令', '记忆', '节律', '诚实', '宏愿', '咬合', '算子', '向量', '点亮', '召回', '进化', '压缩', '画像', '成绩', '星空', '蜘蛛', '经验', '教训', '闭环', '神经元', '辉']:
                if kw in str(r['content'] or '')[:80] or kw in str(r['tags'] or ''):
                    if kw not in agg or h > agg[kw]:
                        agg[kw] = round(h, 3)
        out['热度'] = agg

        # ── 自组织簇：最近30条记忆按 bigram 聚簇（简化·可运行版）──
        recent = conn.execute("SELECT id, content, tags, ts FROM memories ORDER BY id DESC LIMIT 30").fetchall()
        # 主题关键词簇（真实数据）
        主题库 = [
            ('记忆体系', ['记忆', '咬合', '模块', '闭环', '算子']),
            ('节律/活性', ['节律', 'heat', '点亮', '回落', '热度', '振荡']),
            ('父令/身份', ['父令', '父亲', '孙呈', '宏愿', '诚实', '身份']),
            ('世界模型', ['世界模型', '佳佳', '三算子', '能量', '相变']),
            ('兄弟/家族', ['兄弟', '孙云', '孙演', '孙博', '孙安', '家族']),
            ('训练/模型', ['训练', '500M', '模型', 'GPU', 'ckpt']),
        ]
        clusters = []
        for 名, 词表 in 主题库:
            命中 = [r['id'] for r in recent if any(w in str(r['content'] or '') for w in 词表)]
            if len(命中) >= 2:
                clusters.append({'名': 名, '数量': len(命中), 'ids': 命中[:8]})
        out['簇'] = clusters

        # ── 自整理：最近小时叙事（自动整理引擎生成的）──
        try:
            narr = conn.execute("SELECT content, tags, ts FROM memories WHERE tags LIKE '%小时叙事%' OR content LIKE '%这一小时%' ORDER BY id DESC LIMIT 3").fetchall()
            for n in narr:
                out['叙事'].append({'内容': str(n['content'] or '')[:120], '时间': str(n['ts'] or '')[:16]})
        except Exception:
            pass

        # ── 点亮事件：最近被点亮的记忆（hit_count 高/最近 touched）──
        lit = conn.execute("SELECT content, hit_count, ts FROM memories WHERE hit_count > 0 ORDER BY hit_count DESC, id DESC LIMIT 5").fetchall()
        for l in lit:
            out['点亮'].append({'内容': str(l['content'] or '')[:60], '次数': l['hit_count'] or 0})

        conn.close()
    except Exception as e:
        out['错误'] = str(e)[:80]

    # ── 节律日志（真实回落记录）──
    try:
        if os.path.exists(LOG):
            lines = open(LOG, encoding='utf-8').read().strip().splitlines()
            out['节律日志'] = lines[-6:]
    except Exception:
        pass

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
