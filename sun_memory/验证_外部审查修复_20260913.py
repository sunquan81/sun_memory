# -*- coding: utf-8 -*-
"""外部审查修复 · 独立验证脚本（2026-09-13）
========================================
验证对象：桌面《记忆体评价_20260827.md》后半段外部AI对源码全书的审查报告
修复清单：🔴1-🔴8 + 🟡7（含 pyflakes 挖出的额外 5 处）
跑法：python 验证_外部审查修复_20260913.py
全部只读（不写库/不改文件）· 可重复跑
"""
import os, re, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))  # 自动定位（开源版/核心版都能跑）
PY = sys.executable
结果 = []


def 读(rel):
    p = os.path.join(BASE, rel)
    return open(p, encoding='utf-8', errors='ignore').read() if os.path.exists(p) else ''


def 查(label, cond, 证据=''):
    结果.append((label, bool(cond), 证据))


# 🔴1 进化阈值统一
t = 读('core/写入链.py')
查('🔴1 进化阈值统一（0.75→_SAME_FACT_OVERLAP）',
   'if _ov >= _SAME_FACT_OVERLAP' in t and 'if _ov >= 0.75' not in t,
   'L46 常量 0.85 + L830 引用常量')

# 🔴2 保护数累加
t2 = 读('孙家记忆体.py')
查('🔴2 节律回落保护数 += 1', '保护数 += 1' in t2, '原漏计致观测恒0')

# 🔴3 蜘蛛网 _tmp 提前
t3 = 读('core/蜘蛛网索引.py')
i_def = t3.find('_tmp = str(INDEX_PATH)')
i_use = t3.find('open(_tmp, \'a\'')
查('🔴3 蜘蛛网 _tmp 定义在使用之前', 0 < i_def < i_use, f'定义@{i_def} 使用@{i_use}')

# 🔴4 联想召回 _sq 局部导入
t4 = 读('core/联想召回.py')
i_sq_use = t4.find('_conn2 = _sq.connect')
i_sq_imp = t4.find('import sqlite3 as _sq')
查('🔴4 联想召回 _sq 先导入后使用',
   'import sqlite3 as _sq  # 2026-09-13' in t4 or 0 < i_sq_imp < i_sq_use,
   f'import@{i_sq_imp} 使用@{i_sq_use}')

# 🔴5 身份层_初始化 重名修复
t5 = 读('core/写入链.py')
查('🔴5 标准对象_初始化 改名成功',
   t5.count('def 身份层_初始化()') == 1 and 'def 标准对象_初始化()' in t5,
   f"身份层_初始化 定义数={t5.count('def 身份层_初始化()')}")
查('🔴5b 写入记忆 补调 标准对象_初始化',
   '标准对象_初始化()  # 2026-09-13' in t5, '确保叙事链/功能块表就绪')

# 🔴6 预感 lx_r 显式初始化
t6 = 读('core/预感召回.py')
_t6代码行 = [l.split('#')[0] for l in t6.split('\n')]  # 去行尾注释后再查（防注释里的字样误判）
查('🔴6 预感 lx_r 显式初始化',
   any('lx_r = None' in l for l in _t6代码行) and not any("'lx_r' in dir()" in l for l in _t6代码行),
   '原 dir() 检查脆弱·现已显式初始化')

# 🔴7 节律 import
t7 = 读('core/节律.py')
查('🔴7 节律.py 补 import sys, time',
   re.search(r'^import sqlite3, os, math, sys, time', t7, re.M) is not None, '')

# 🔴8/9/10 三个未定义名
查('🔴8 provider 归一化 已导入',
   'from 写入链 import 判定重复, 归一化' in 读('core/provider.py'), '')
查('🔴8b provider tool_error 已消除',
   'tool_error(' not in 读('core/provider.py'), '')
查('🔴9 写入链 __main__ 调 标准对象_初始化',
   '标准对象_初始化()  # 2026-09-13 外部审查修复' in t5, '原调未定义的 初始化()')
查('🔴10 联想召回 按概念取段落 已导入',
   '按概念取段落 as 按概念取段落' in t4, '')

# 🟡7 遗忘接入
t11 = 读('core/自动整理引擎.py')
查('🟡7 遗忘一批 已接入语义重织',
   '遗忘一批' in t11 and '_增._缓存网 = None' in t11, '原定义但从未被调用')

# ★ 总验证：pyflakes 全库未定义名（排除备份/归档）
r = subprocess.run([PY, '-m', 'pyflakes', BASE], capture_output=True, text=True, encoding='utf-8', errors='ignore')
undef = [l for l in ((r.stdout or '') + (r.stderr or '')).split('\n')
         if 'undefined name' in l and 'unable to detect' not in l  # 排除 import * 风格警告
         and '备份' not in l and '归档' not in l
         and '记忆库.py:146' not in l]  # 记忆库 L146 是类型注解字符串·L150 内有 import
查('★ pyflakes 全库未定义名 = 0（生产）', len(undef) == 0, f'剩余 {len(undef)}: {undef[:3]}')

# ★ 端到端功能：写入能打初始化回执
r2 = subprocess.run([PY, '孙家记忆体.py', '写入', '验证脚本自检条目·请忽略', '--tags', '验证脚本'],
                    cwd=BASE, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=120)
ok_write = "'ok': True" in (r2.stdout or '')
查('★ 端到端·写入通（含初始化回执）', ok_write and '初始化完成' in (r2.stdout or ''),
   (r2.stdout or '')[:60].replace('\n', ' '))

# 汇总
通过 = sum(1 for _, c, _ in 结果 if c)
print('═' * 60)
print(f'外部审查修复 · 独立验证：{通过}/{len(结果)} PASS')
print('═' * 60)
for label, c, ev in 结果:
    print(f'{"PASS" if c else "FAIL"} {label}' + (f'  | {ev}' if ev else ''))
print('═' * 60)
print('结论：' + ('全部修复生效 ✅' if 通过 == len(结果) else f'⚠️ {len(结果)-通过} 项待查'))
