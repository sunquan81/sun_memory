# -*- coding: utf-8 -*-
"""记忆体配置表（父令2026-08-26·产品化：方程参数全部外置·不改源码可调优）

三大方程 + 5大集合的全部参数收敛于此：
  活性方程：λ衰减/点亮增量/热上限/账本权重
  相似度方程：α/β/γ权重/去重阈值
  召回方程：融合权重/重要加分/专名加分
  整理方程：骨架化阈值/小时叙事门槛
  写入准入：去重阈值/进化重叠阈值/关键内容标记词

外部可配置：config.yaml（零依赖解析·不改源码调参）
"""
import os
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_默认配置 = {
    # ── 活性方程（原节律/时间衰减/成绩单）──
    "活性": {
        "点亮增量": 0.3,       # 点亮一次 heat 上升量
        "热上限": 5.0,          # heat 上限
        "衰减λ": 0.10,          # 普通衰减/天
        "保护衰减λ": 0.02,      # 保护记忆衰减/天（慢5倍）
        "保护地板": 0.5,        # 保护记忆 heat 地板
        "确认权重": 2.0,        # 成绩单确认 +2
        "纠正权重": -2.0,       # 成绩单纠正 -2
        "点亮权重": 1.0,        # 成绩单点亮 +1
    },
    # ── 相似度方程（原内容去重/无模型向量/英文归一）──
    "相似度": {
        "α_bigram": 0.4,       # 无序 bigram Jaccard 权重
        "β_有序": 0.3,          # 有序 bigram 权重
        "γ_余弦": 0.3,          # 词干归一余弦权重
        "去重阈值": 0.6,        # 判重复阈值
    },
    # ── 召回方程（原联想召回排序）──
    "召回": {
        "向量权重": 20.0,       # 1余弦点≈20概念分
        "重要加分": 10.0,       # 父令/被点出加分
        "专名加分": 10.0,       # 专有名词命中加分
        "字面命中": 3.0,        # 字面命中保底
        "时间半衰": 30.0,       # 时间新鲜度半衰期（天）
    },
    # ── 整理方程（原自动整理/自组织/压缩）──
    "整理": {
        "小时叙事门槛": 3,      # 少于N条的小时不单独成叙事
        "整理间隔轮次": 30,     # 每N轮触发整理
        "整理间隔分钟": 60,     # 或每N分钟触发
        "骨架阈值天": 30,       # 30天以上可骨架化
        "进化重叠阈值": 0.85,   # 同事实重叠≥此值→标outdated
    },
    # ── 写入准入 ──
    "写入": {
        "关键标记词": ["父令", "父亲令", "记住", "教训", "重要", "必须", "决定", "命令", "禁止", "铁律"],
        "内容上限": 300,        # 实时抓取内容截断
        "缓冲容量": 200,        # 短时缓冲 detail 上限
    },
}

# 全局配置（启动时加载 config.yaml 覆盖默认）
_配置 = dict(_默认配置)
_config_path = _HERE / "config.yaml"


def _加载配置():
    """零依赖 YAML 解析（支持 键: 值 和 缩进分组）"""
    global _配置
    if not _config_path.exists():
        return
    try:
        当前组 = None
        for line in _config_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            # 分组（无冒号值·如 "活性:"）
            m = re.match(r'^([\w\u4e00-\u9fff]+):\s*$', s)
            if m:
                当前组 = m.group(1)
                if 当前组 in _配置:
                    continue
            # 键值对（如 "  点亮增量: 0.3"）
            m2 = re.match(r'^([\w\u4e00-\u9fff]+):\s*(.+)$', s)
            if m2 and 当前组 and 当前组 in _配置:
                键, 值 = m2.group(1), m2.group(2).strip()
                try:
                    _配置[当前组][键] = float(值) if "." in 值 else int(值)
                except ValueError:
                    if 值.startswith("[") and 值.endswith("]"):
                        _配置[当前组][键] = [x.strip().strip("\"'") for x in 值[1:-1].split(",")]
                    else:
                        _配置[当前组][键] = 值
    except Exception:
        pass


def get(组: str, 键: str):
    """读配置参数（产品化：外部 config.yaml 可覆盖·不改源码）"""
    return _配置.get(组, {}).get(键)


def 全部() -> dict:
    return dict(_配置)


def 写默认配置(路径=None):
    """生成默认 config.yaml（首次部署/导出用）"""
    p = Path(路径) if 路径 else _config_path
    lines = ["# 孙家记忆体 · 配置表（父令2026-08-26·参数外置）", "# 改这里不用改源码·重启网关生效", ""]
    for 组, kv in _默认配置.items():
        lines.append(f"{组}:")
        for 键, 值 in kv.items():
            if isinstance(值, list):
                lines.append(f"  {键}: {值}")
            elif isinstance(值, float):
                lines.append(f"  {键}: {值:g}")
            else:
                lines.append(f"  {键}: {值}")
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


_加载配置()


def 参数总览() -> str:
    """参数总表（2026-09-14 吸收收束版优点：一眼看全）"""
    import json as _j
    行 = []
    try:
        _fn = next((f for f in ('加载配置', '读配置', '配置', 'get_config') if f in dir()), None)
        参 = globals()[_fn]() if _fn else _默认配置
    except Exception:
        参 = _默认配置
    for 组, 项 in (参 or _默认配置).items():
        行.append(f'  【{组}】')
        if isinstance(项, dict):
            for k, v in 项.items():
                行.append(f'    {k} = {v}')
        else:
            行.append(f'    {项}')
    return '\n'.join(行)
