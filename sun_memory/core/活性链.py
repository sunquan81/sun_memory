# -*- coding: utf-8 -*-
from pathlib import Path
# -*- coding: utf-8 -*-
"""活性链（父令2026-08-25·门面模式）
统一出口：活性链 = 该域所有模块的转发
职责：活性相关操作全部从这一个文件进入
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from 节律 import *
from 记忆成绩单 import *
# 2026-09-07 安弟1589体检🔴4修复：import*静默遮蔽——批量点亮 被记忆成绩单版覆盖节律版
# （成绩单版带 owner+账本记录·节律版旧实现被有意取代·显式声明消除 import 顺序依赖）
from 记忆成绩单 import 批量点亮

# 活性链·模块清单: 节律, 节律调度, 记忆成绩单, 记忆状态
