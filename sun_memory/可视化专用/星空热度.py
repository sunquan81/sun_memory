# -*- coding: utf-8 -*-
"""星空热度数据（记忆体星空 v2：HEAT CODE / 归档暗星 / SYNC LOG）
被 main.js 调用·输出 JSON：热记忆标签→热节点·归档数·节律日志"""
import sqlite3, json, os, sys

DB = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sunmem.db'))
LOG = os.environ.get('节律日志路径', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', '节律观测日志.log'))


def main():
    out = {'hot': {}, '归档数': 0, '日志': []}

    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        # 热记忆（heat>0·取前50·内容关键词→热节点映射）
        rows = conn.execute(
            "SELECT id, content, tags, heat, layer FROM memories WHERE heat > 0 "
            "ORDER BY heat DESC LIMIT 50").fetchall()
        # 归档（过时记忆数）
        out['归档数'] = conn.execute("SELECT COUNT(*) FROM memories WHERE status='outdated'").fetchone()[0]
        # 热词映射：从热记忆内容里抽2-4字词·对应蜘蛛网节点（heat 高的浮出）
        import re
        热词 = []
        for r in rows:
            h = r['heat'] or 0.0
            # 标签优先
            tags = str(r['tags'] or '')
            for t in re.findall(r'[\u4e00-\u9fff]{2,6}', tags):
                if len(t) >= 2:
                    热词.append((t, h))
            # 内容里抽"父令/记忆/节律/星"等核心词
            c = str(r['content'] or '')[:60]
            for kw in ['父令', '记忆', '节律', '星空', '蜘蛛', '诚实', '宏愿', '咬合', '算子', '向量', '点亮', '召回', '进化', '压缩', '画像', '成绩']:
                if kw in c:
                    热词.append((kw, h))
        # 聚合（同词取最大热度）
        agg = {}
        for t, h in 热词:
            if t not in agg or h > agg[t]:
                agg[t] = h
        out['hot'] = agg
        conn.close()
    except Exception as e:
        out['hot'] = {'记忆': 0.3}

    # SYNC LOG（节律观测日志·最近5条）
    try:
        if os.path.exists(LOG):
            lines = open(LOG, encoding='utf-8').read().strip().splitlines()
            out['日志'] = lines[-5:]
    except Exception:
        pass

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
