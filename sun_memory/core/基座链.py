# -*- coding: utf-8 -*-
"""基座链（父令2026-08-25·门面模式）
语义辅助+基座：被链引用·保持独立
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from 记忆库 import *
from 时间衰减 import *
from 经验总结 import *
from 蜘蛛网索引 import *  # 2026-08-26 身份中心/段落节点已并入蜘蛛网索引
from 豆辞典 import *
from 感知注入 import *
# from 星空热度 import *  # 2026-08-26 已移出core（可视化专用·移入sun_memory/可视化专用/）
from 无模型向量 import *
from 英文词形归一 import *
# 2026-08-26 查知识库已并入召回链·函数内延迟import（防循环）
from 蜘蛛网索引 import *  # 2026-08-26 段落节点已并入蜘蛛网索引
# from 记忆生命流 import *  # 2026-08-26 已移出core（可视化专用·移入sun_memory/可视化专用/）

# 基座链·模块清单: 记忆库, 时间衰减, 经验总结, 身份中心, 豆辞典, 感知注入, 星空热度, 无模型向量, 英文词形归一, 知识库检索, 段落节点, 记忆生命流
