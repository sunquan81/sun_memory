# -*- coding: utf-8 -*-
"""整理链（父令2026-08-25·门面模式）
统一出口：整理链 = 该域所有模块的转发
职责：整理相关操作全部从这一个文件进入
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from 自动整理引擎 import *
from 蜘蛛网索引 import *

# 整理链·模块清单: 记忆整理, 记忆自组织, 自动整理, 自动整理引擎, 蜘蛛网索引
