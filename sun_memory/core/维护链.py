# -*- coding: utf-8 -*-
"""维护链（父令2026-08-25·门面模式）
统一出口：维护链 = 该域所有模块的转发
职责：维护相关操作全部从这一个文件进入
"""
import sys, os
import json
import re
import sqlite3
import tempfile  # 2026-08-27 修复：原子写 用 tempfile 缺 import
from datetime import datetime
import random
import shutil
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ═══ 2026-08-26 从维护模块迁入的常量 ═══
_HERE = Path(__file__).resolve().parent
FRAMEWORK_DIR = _HERE.parent.parent
记忆体目录 = FRAMEWORK_DIR / "记忆体"  # 2026-08-27 修复：从原记忆体检.py 迁入（体检/压缩用到·缺了NameError）
已归档目录 = 记忆体目录 / "已归档"  # 2026-08-27 修复：同上
蜘蛛网文件 = FRAMEWORK_DIR / "蜘蛛网" / "索引.json"  # 2026-08-27 修复：从原自愈.py 迁入（自检①用到·缺了NameError）
_家族根 = FRAMEWORK_DIR  # 2026-08-27 修复：从原自愈.py 迁入（清理_备份用到·缺了NameError）
日志文件 = _HERE / "self_heal.log"  # 2026-08-27 修复：从原自愈.py 迁入（日志/自检用到·缺了NameError）
归档目录 = _家族根 / "记忆体_历史归档"  # 2026-08-27 修复：从原自愈.py 迁入（清理_备份用到·缺了NameError）
SUNMEM_DB = os.environ.get("SUNMEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
DB = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
DB_PATH = os.environ.get('SUNMEM_DB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sunmem.db'))
学术排除 = ["论文", "文章", "研究中", "他指出", "作者", "DeepMind", "arXiv"]  # 2026-08-27 修复：从原认知画像.py 迁入（缺失致NameError）
未竟信号 = ["还没", "没做", "待续", "未竟", "没来得及", "未完成", "待办", "留到"]  # 2026-08-27 修复：同画像迁入
未竟主语信号 = ["儿下轮", "大哥下轮", "下轮要", "下一步要", "接下来要", "要接着", "待续"]  # 2026-08-27 修复：同画像迁入
薄弱信号 = ["父亲纠正", "父纠正", "被打脸", "翻车了", "被点出", "没收到经验"]  # 2026-08-27 修复：同画像迁入
DEFAULT_AGE_DAYS = 30  # 超过30天未活跃→压缩

# from 记忆体检 import *  # 2026-08-26 已并入本文件
# from 自愈 import *  # 2026-08-26 已并入本文件
# from 记忆版本 import *  # 2026-08-26 已并入本文件
# from 记忆压缩 import *  # 2026-08-26 已并入本文件
# from 认知画像 import *  # 2026-08-26 已并入本文件
# from 认知冲突日志 import *  # 2026-08-26 已并入本文件
# from 认知冲突日志 import *  # 2026-08-26 已并入本文件

# 维护链·模块清单: 记忆体检, 自愈, 记忆版本, 记忆压缩, 认知画像, 认知冲突日志, 认知更新


# ═══════════════════════════════════════════════════════
# 2026-08-26 融合（父令：模块精简）：维护六模块并入本链
# 记忆体检/自愈/记忆版本/记忆压缩/认知画像/认知冲突日志
# ═══════════════════════════════════════════════════════

# ── 原 记忆体检.py（2026-08-26 并入）──
def 原子写(path, data, indent=1):
    """写临时文件后 os.replace 原子替换,避免写一半损坏 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_mem_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── 乱码检测 ────────────────────────────────────────────
_常用字 = (
    "的一是了我不人在他有这上们来到时大地为子中你说生国年着就那要和她出也得里后自以会家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想作种开美总从无情己面最女但现前些所同日手又行意动方期它头经长儿回位分爱老因很给名法间斯知世什两次使身者被高已亲其进此话常与活正感见明问力理尔点文几定本公特做外孩相西果走将月十实向声车全信重三机工物气每并别真打太新比才便夫再书部水像眼等体却加电主界门利海受听表德少克代员许先口由死安写性马光白或住难望教命花结乐色更拉东神记处让母父应直字场平报友关放至张认接告入笑内英军候民岁往何度山觉路带万男边风解叫任金快原吃县变清成深式"
)
_常见标点 = set(
    "，。！？；：、（）《》“”‘’—…·→×,.;:!?()[]{}'\"\\/|~`@#$%^&*+-=<>_ \t\n\r"
)


# 合法特殊字符区间(制表符/箭头/希腊字母/带圈数字/emoji等——正常技术文本会用到)
_噪声区间 = [
    (0x00B0, 0x00FF),   # 拉丁补充(°×÷±等)
    (0x2010, 0x2027),   # 一般标点(–—…等)
    (0x2030, 0x205E),   # 其他标点
    (0x2100, 0x214F),   # 字母式符号
    (0x2190, 0x21FF),   # 箭头(←→↔等)
    (0x2460, 0x24FF),   # 带圈/括号数字
    (0x2500, 0x25FF),   # 制表符/几何图形(─━│◆等)
    (0x2600, 0x27BF),   # 杂项符号/装饰(✅★☀等)
    (0x0391, 0x03C9),   # 希腊字母
]


def _在噪声(c):
    o = ord(c)
    return any(lo <= o <= hi for lo, hi in _噪声区间)


def 奇异比(s):
    """文本中『奇异字符』占比:非常用CJK/非ASCII/非标点/非合法符号。"""
    if not s:
        return 0.0
    n = 0
    for c in s:
        o = ord(c)
        if 0x4E00 <= o <= 0x9FFF:
            continue
        if c.isascii() or c in _常见标点 or _在噪声(c) or o in (0x3000, 0x3001, 0x3002, 0xFF0C, 0xFF1A):
            continue
        n += 1
    return n / len(s)


def 码点块字符数(s):
    """码点乱码专用块(彝文/Vai/TaiViet/谚文 0xA000-0xDFFF)字符个数。"""
    return sum(1 for c in s if 0xA000 <= ord(c) <= 0xDFFF and not _在噪声(c))


def 常用字比(s):
    if not s:
        return 0.0
    return sum(1 for c in s if c in _常用字) / len(s)


def 疑似乱码(text):
    """组合规则(2026-08-11 三次校准):
      1. 强信号:码点乱码块字符 ≥2 且 常用字比 <0.10(乱码条目块字符密集)
      2. 弱信号:长度≥6 且 常用字比<0.05 且 奇异比≥0.06
      孙呈旧码点乱码(#0-#10):块字符密集,常用字比 0.00-0.04。
      真实条目:框线/箭头/希腊字母/emoji 已归为合法噪声;引用乱码字符的
      真实文本(如 #2267)常用字比≥0.28,不误报。
    """
    if not text or len(text) < 6:
        return False
    if 码点块字符数(text) >= 2 and 常用字比(text) < 0.10:
        return True
    return 常用字比(text) < 0.05 and 奇异比(text) >= 0.06


def 空壳残留(value):
    """检测迁移残留:字符串化的 [] / {} / ['...']。"""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if s in ("[]", "{}"):
        return [] if s == "[]" else {}
    if s.startswith("[") and s.endswith("]") and s.count("'") >= 2:
        try:
            parsed = eval(s, {"__builtins__": {}})
        except Exception:
            return None
        if isinstance(parsed, list):
            return parsed
    return None


# ── 体检 ────────────────────────────────────────────────
def _找记忆体文件():
    if not 记忆体目录.exists():
        return []
    return sorted(记忆体目录.glob("*记忆体.json"))


def 体检单文件(path):
    报告 = {
        "文件": path.name,
        "大小KB": round(path.stat().st_size / 1024, 1),
        "结构异常": [],
        "条目数": 0,
        "乱码条目": 0,
        "空壳残留": 0,
        "重复条目": 0,
        "过期条目": 0,
    }
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except UnicodeDecodeError:
        报告["结构异常"].append(f"编码非UTF-8(疑似UTF-16,前字节 {open(path,'rb').read(2).hex()})")
        return 报告
    except json.JSONDecodeError as e:
        报告["结构异常"].append(f"JSON损坏:{e}")
        return 报告
    if not isinstance(data, dict):
        报告["结构异常"].append("顶层不是对象")
        return 报告
    条目列表 = data.get("条目列表", data.get("记忆条目", data.get("条目", data.get("entries", []))))
    if not isinstance(条目列表, list):
        报告["结构异常"].append("条目列表不是数组")
        return 报告
    报告["条目数"] = len(条目列表)
    seen = {}
    for e in 条目列表:
        if not isinstance(e, dict):
            报告["结构异常"].append("存在非对象条目")
            continue
        内容 = str(e.get("内容", e.get("摘要", "")))
        标签 = str(e.get("标签", e.get("状态", "")))
        if 疑似乱码(内容) or 疑似乱码(标签):
            报告["乱码条目"] += 1
        for k in ("标签", "内容"):
            if k in e and 空壳残留(e[k]) is not None:
                报告["空壳残留"] += 1
        key = (标签.strip(), 内容.strip())
        if key[0] or key[1]:
            seen[key] = seen.get(key, 0) + 1
        if e.get("status") == "outdated":
            报告["过期条目"] += 1
    报告["重复条目"] = sum(v - 1 for v in seen.values() if v > 1)
    return 报告


def 体检(打印=True):
    结果 = []
    for p in _找记忆体文件():
        r = 体检单文件(p)
        结果.append(r)
        if 打印:
            flags = []
            if r["结构异常"]:
                flags.append("⚠结构:" + ";".join(r["结构异常"]))
            if r["乱码条目"]:
                flags.append(f"⚠乱码{r['乱码条目']}")
            if r["空壳残留"]:
                flags.append(f"⚠空壳{r['空壳残留']}")
            if r["重复条目"]:
                flags.append(f"⚠重复{r['重复条目']}")
            if r["过期条目"]:
                flags.append(f"过期{r['过期条目']}")
            print(f"{r['文件']:<24} {r['大小KB']:>9}KB  条目{r['条目数']:>5}  " + ("  ".join(flags) if flags else "✓ 正常"))
    return 结果


# ── 安全修复 ────────────────────────────────────────────
def 修复单文件(path) -> bool:
    """只做安全修复:空壳残留转真值 + 原子写回。乱码/结构不自动动。"""
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    条目列表 = data.get("条目列表", data.get("记忆条目", data.get("条目", data.get("entries", []))))
    if not isinstance(条目列表, list):
        return False
    改 = False
    for e in 条目列表:
        if not isinstance(e, dict):
            continue
        for k in ("标签", "内容"):
            if k in e:
                v = 空壳残留(e[k])
                if v is not None and v != e[k]:
                    e[k] = v
                    改 = True
    if 改:
        原子写(path, data)
        return True
    return False


def 主():
    fix = "--fix" in sys.argv
    print("=== 记忆体检 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ("(--fix)" if fix else "") + " ===")
    rs = 体检(打印=True)
    汇总 = {"文件": len(rs), "乱码": sum(r["乱码条目"] for r in rs),
             "空壳": sum(r["空壳残留"] for r in rs), "重复": sum(r["重复条目"] for r in rs)}
    print(f"--- 汇总: {汇总['文件']}个文件 / 乱码{汇总['乱码']} / 空壳{汇总['空壳']} / 重复{汇总['重复']} ---")
    if fix:
        print("--- 执行安全修复(空壳残留→真值) ---")
        for p in _找记忆体文件():
            if 修复单文件(p):
                print(f"修复: {p.name}")
        print("--- 修复后复检 ---")
        体检(打印=True)
    return 0


if __name__ == "__main__":
    sys.exit(主())

# ── 原 自愈.py（2026-08-26 并入）──
def 日志(级别: str, 消息: str):
    """写自愈日志（时间戳 + 级别 + 消息）"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(日志文件, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{级别}] {消息}\n")
    except Exception:
        pass  # 日志失败不影响主流程


def 检查_json文件(路径: Path, 名字: str, 允许list: bool = False) -> bool:
    """① 文件完整性检测：JSON 可解析？"""
    try:
        if not 路径.exists():
            日志("警告", f"{名字} 不存在")
            _检查计数["警告"] += 1
            return False
        with open(路径, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, (dict, list)) or (isinstance(d, list) and not 允许list):
            日志("警告", f"{名字} 类型异常: {type(d).__name__}")
            _检查计数["警告"] += 1
            return False
        _检查计数["通过"] += 1
        return True
    except json.JSONDecodeError as e:
        日志("错误", f"{名字} JSON损坏: {e}")
        _检查计数["警告"] += 1
        return False
    except Exception as e:
        日志("错误", f"{名字} 检查异常: {e}")
        _检查计数["警告"] += 1
        return False


def 修复_json文件(路径: Path, 名字: str, 默认结构=None):
    """② 自动修复：损坏 → 用备份恢复 / 重建"""
    # 先找备份（同目录 .bak* 或 备份 文件）
    备份 = None
    for b in sorted(路径.parent.glob(f"{路径.stem}*bak*"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            json.load(open(b, encoding="utf-8"))
            备份 = b
            break
        except Exception:
            continue
    if 备份:
        shutil.copy2(备份, 路径)
        日志("修复", f"{名字} 已从备份恢复: {备份.name}")
    else:
        if 默认结构 is None:
            默认结构 = {"版本": "1.0", "节点": {}, "丝线": [], "统计": {"节点数": 0, "丝线数": 0}}
        with open(路径, "w", encoding="utf-8") as f:
            json.dump(默认结构, f, ensure_ascii=False, indent=2)
        日志("修复", f"{名字} 已重建空结构")
    _检查计数["修复"] += 1


def 校验_fts():
    """③ FTS 同步校验：memories vs memories_fts 条数"""
    try:
        conn = sqlite3.connect(SUNMEM_DB)
        cnt = conn.execute("SELECT count(*) FROM memories").fetchone()[0]
        fts = conn.execute("SELECT count(*) FROM memories_fts").fetchone()[0]
        conn.close()
        if cnt != fts:
            日志("错误", f"FTS不同步: memories={cnt} fts={fts} → 需要重建")
            _检查计数["警告"] += 1
            return False
        _检查计数["通过"] += 1
        return True
    except Exception as e:
        日志("错误", f"FTS校验异常: {e}")
        _检查计数["警告"] += 1
        return False


def 重建_fts():
    """重建 FTS 索引（从 memories 全量重灌）"""
    try:
        conn = sqlite3.connect(SUNMEM_DB)
        conn.execute("DELETE FROM memories_fts")
        conn.execute("""INSERT INTO memories_fts(rowid, content)
                        SELECT id, content FROM memories""")
        conn.commit()
        cnt = conn.execute("SELECT count(*) FROM memories_fts").fetchone()[0]
        conn.close()
        日志("修复", f"FTS已重建: {cnt} 条")
        _检查计数["修复"] += 1
        return True
    except Exception as e:
        日志("错误", f"FTS重建失败: {e}")
        return False


def 检查_缓存():
    """④ 缓存失效检测：向量/倒排缓存"""
    for name in ["_向量缓存.json", "_倒排缓存.json"]:
        p = _HERE / name
        if p.exists():
            try:
                d = json.load(open(p, encoding="utf-8"))
                # 2026-08-17 适配倒排新格式（{"覆盖ids","倒排"}·兼容旧纯dict）
                内容 = d.get("倒排", d) if isinstance(d, dict) and "倒排" in d else d
                if not 内容:
                    日志("警告", f"{name} 为空 → 标记失效(自动重建)")
                    p.unlink()  # 删掉·下次自动重建
                    _检查计数["修复"] += 1
                else:
                    _检查计数["通过"] += 1
            except Exception as e:
                日志("错误", f"{name} 损坏 → 删除待重建: {e}")
                try:
                    p.unlink()
                    _检查计数["修复"] += 1
                except Exception:
                    pass


def 清理_备份(保留数: int = 3):
    """⑥ 备份自动清理：保留最近 N 份·旧的归档"""
    patterns = ["*.bak*", "*backup*", "*.tmp"]
    备份们 = []
    for pat in patterns:
        备份们 += [p for p in _家族根.rglob(pat) if 归档目录 not in p.parents]  # 2026-08-27 修复：排除已归档目录·避免重复归档自己
    # 按修改时间排序·保留最近 N
    备份们.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    if len(备份们) <= 保留数:
        _检查计数["通过"] += 1
        return
    os.makedirs(归档目录, exist_ok=True)
    for 旧备份 in 备份们[保留数:]:
        try:
            dest = 归档目录 / 旧备份.name
            shutil.move(str(旧备份), str(dest))
            日志("修复", f"备份归档: {旧备份.name} → 历史归档/")
            _检查计数["修复"] += 1
        except Exception as e:
            日志("警告", f"备份归档失败 {旧备份.name}: {e}")


def 自检():
    """完整自检（返回统计）"""
    global _检查计数
    _检查计数 = {"通过": 0, "修复": 0, "警告": 0}
    日志("信息", "═══ 记忆体自愈自检开始 ═══")

    # ① 蜘蛛网索引
    if not 检查_json文件(蜘蛛网文件, "蜘蛛网索引"):
        修复_json文件(蜘蛛网文件, "蜘蛛网索引")

    # ② 压缩骨架（允许 list）
    p = 记忆体目录 / "孙呈_压缩骨架.json"
    检查_json文件(p, "压缩骨架", 允许list=True)

    # ③ 记忆体 JSON
    for f in sorted(记忆体目录.glob("*索引记忆体.json")):
        if not 检查_json文件(f, f.name):
            修复_json文件(f, f.name, {"条目列表": [], "next_id": 1})

    # ④ FTS 校验
    if not 校验_fts():
        重建_fts()

    # ⑤ 缓存
    检查_缓存()

    # ⑥ 备份清理
    清理_备份()

    日志("信息", f"═══ 自检完成: 通过{_检查计数['通过']} 修复{_检查计数['修复']} 警告{_检查计数['警告']} ═══")
    return dict(_检查计数)


if __name__ == "__main__":
    r = 自检()
    print(f"自检完成: 通过{r['通过']} 修复{r['修复']} 警告{r['警告']}")
    print(f"日志: {日志文件}")

# ── 原 记忆版本.py（2026-08-26 并入）──
def _连接():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def _建表(conn=None):
    own = conn is None
    if own:
        conn = _连接()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER NOT NULL,
            old_content TEXT,
            old_tags TEXT,
            new_content TEXT,
            reason TEXT DEFAULT '',
            ts TEXT,
            version INTEGER
        )
    """)
    conn.commit()
    if own:
        conn.close()


def 备份(记忆id: int, 旧内容: str, 旧标签: str = "", 新内容: str = "", 原因: str = "") -> bool:
    """进化/整理前备份旧版本（update/merge 时调用）"""
    try:
        conn = _连接()
        _建表(conn)
        # 当前版本号 = 已有版本数 + 1
        row = conn.execute("SELECT COUNT(*) AS n FROM memory_versions WHERE memory_id=?",
                           (记忆id,)).fetchone()
        v = (row["n"] if row else 0) + 1
        conn.execute(
            "INSERT INTO memory_versions (memory_id, old_content, old_tags, new_content, reason, ts, version) VALUES (?,?,?,?,?,?,?)",
            (记忆id, 旧内容, 旧标签, 新内容, 原因, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), v))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def 版本历史(记忆id: int) -> list:
    """某记忆的版本历史（新→旧）"""
    try:
        conn = _连接()
        _建表(conn)
        rows = conn.execute(
            "SELECT version, old_content, old_tags, reason, ts FROM memory_versions WHERE memory_id=? ORDER BY version DESC",
            (记忆id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def 回滚(记忆id: int, 版本号: int) -> dict:
    """把记忆恢复到某个版本（旧内容写回 memories·原内容标 outdated）
    ⚠️ 只回滚非 core 层（core 不可回滚·防意外覆盖宪法）"""
    try:
        conn = _连接()
        _建表(conn)
        # 找版本
        row = conn.execute(
            "SELECT old_content, old_tags FROM memory_versions WHERE memory_id=? AND version=?",
            (记忆id, 版本号)).fetchone()
        if not row:
            conn.close()
            return {"ok": False, "msg": f"版本 {版本号} 不存在"}
        # 查当前记忆
        cur = conn.execute("SELECT content, tags, layer FROM memories WHERE id=?",
                           (记忆id,)).fetchone()
        if not cur:
            conn.close()
            return {"ok": False, "msg": f"记忆 #{记忆id} 不存在"}
        if str(cur["layer"]) == "core":
            conn.close()
            return {"ok": False, "msg": "⛔ core 层不可回滚（宪法级·只有父令能改）"}
        # 当前内容备份为新版本（防回滚后悔）
        备份(记忆id, cur["content"], cur["tags"], row["old_content"], f"回滚到v{版本号}")
        # 写回旧内容（状态恢复 active——回滚=回到可用）
        conn.execute("UPDATE memories SET content=?, tags=?, status='active', updated_at=? WHERE id=?",
                     (row["old_content"], row["old_tags"] or cur["tags"],
                      datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 记忆id))
        conn.commit()
        conn.close()
        return {"ok": True, "msg": f"记忆 #{记忆id} 已回滚到 v{版本号}"}
    except Exception as e:
        return {"ok": False, "msg": f"回滚失败: {str(e)[:60]}"}


def 状态() -> dict:
    try:
        conn = _连接()
        _建表(conn)
        n = conn.execute("SELECT COUNT(*) FROM memory_versions").fetchone()[0]
        mems = conn.execute("SELECT COUNT(DISTINCT memory_id) FROM memory_versions").fetchone()[0]
        conn.close()
        return {"备份数": n, "有版本记忆数": mems}
    except Exception:
        return {"备份数": 0, "有版本记忆数": 0}


if __name__ == "__main__":
    print("═══ 记忆版本回滚 自测 ═══")
    # 用临时 id 测试（999999 不存在·只测备份/历史/状态）
    备份(999999, "旧内容：记忆压缩用规则", "压缩", "新内容：改了", "测试")
    print("备份后状态:", 状态())
    h = 版本历史(999999)
    print("版本历史:", [(x["version"], x["old_content"][:10]) for x in h])
    # 清理测试
    conn = _连接()
    conn.execute("DELETE FROM memory_versions WHERE memory_id=999999")
    conn.commit(); conn.close()
    print("测试数据已清理·状态:", 状态())

# ── 原 记忆压缩.py（2026-08-26 并入）──
def _骨架路径(brother_name: str) -> Path:
    return FRAMEWORK_DIR / "记忆体" / f"{brother_name}_压缩骨架.json"


def _load_skeletons(brother_name: str) -> list:
    p = _骨架路径(brother_name)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_skeletons(brother_name: str, skeletons: list) -> None:
    with open(_骨架路径(brother_name), "w", encoding="utf-8") as f:
        json.dump(skeletons, f, ensure_ascii=False, indent=2)


def 压缩记忆(brother_name: str = "孙呈", 阈值天: int = DEFAULT_AGE_DAYS) -> dict:
    """超龄条目→生成压缩骨架。原文不删（河底沉积），骨架存规则层。

    骨架结构（博弟思想·存规则不存原文）：
      {时间范围, 标签, 关键点[浓缩], 重要节点数, 条数, 重建提示}

    返回：{"压缩骨架数", "新增骨架", "原文保留数"}
    """
    from 记忆库 import 读记忆体  # 2026-08-27 修复：压缩记忆用 读记忆体 缺 import
    mem = 读记忆体(brother_name)
    entries = mem["条目列表"]
    skeletons = _load_skeletons(brother_name)
    existing_keys = {(s.get("标签"), s.get("时间范围")) for s in skeletons}

    now = datetime.now()
    new_skeletons = []
    # 按标签分组统计（旧记忆按标签压缩）
    by_tag = {}
    for e in entries:
        t = str(e.get("时间", ""))[:10]
        if not t:
            continue
        try:
            age = (now - datetime.strptime(t, "%Y-%m-%d")).days
        except Exception:
            continue
        if age >= 阈值天:
            # 2026-08-20 父令·咬合：核心层永不压缩（宪法级·抗遗忘）
            if str(e.get("layer", "plain")) == "core":
                continue
            tag = e.get("标签", "") or "无标签"
            by_tag.setdefault(tag, []).append(e)

    for tag, group in by_tag.items():
        times = [e.get("时间", "") for e in group if e.get("时间")]
        时间范围 = f"{min(times)[:10]}~{max(times)[:10]}" if times else "?"
        关键点 = []
        for e in group[:10]:  # 每组最多取10条浓缩
            关键点.append(e["内容"][:50])
        重要数 = sum(1 for e in group if e.get("标签") and
                     any(t in e["标签"] for t in ("父令", "决策", "关键概念", "被点出")))
        key = (tag, 时间范围)
        if key in existing_keys:
            continue
        sk = {
            "标签": tag,
            "时间范围": 时间范围,
            "条数": len(group),
            "关键点": 关键点[:8],
            "重要节点数": 重要数,
            "重建提示": f"按标签「{tag}」在{时间范围}的记忆——{len(group)}条，含{重要数}条重要节点",
        }
        new_skeletons.append(sk)

    if new_skeletons:
        skeletons.extend(new_skeletons)
        _save_skeletons(brother_name, skeletons)

    return {
        "压缩骨架总数": len(skeletons),
        "新增骨架": len(new_skeletons),
        "原文保留数": len(entries),  # 原文一条不删
    }


def 重建大意(brother_name: str = "孙呈", 标签: str = "", 时间范围: str = "") -> list:
    """从骨架重建大意（压缩和重建一体两面）。"""
    skeletons = _load_skeletons(brother_name)
    hits = []
    for s in skeletons:
        if 标签 and 标签 not in s.get("标签", ""):
            continue
        if 时间范围 and 时间范围 != s.get("时间范围", ""):
            continue
        hits.append({
            "标签": s.get("标签"),
            "时间范围": s.get("时间范围"),
            "大意": s.get("重建提示", ""),
            "关键点": s.get("关键点", [])[:4],
            "条数": s.get("条数"),
        })
    return hits


def 压缩报告(brother_name: str = "孙呈") -> str:
    r = 压缩记忆(brother_name)
    skeletons = _load_skeletons(brother_name)
    lines = [
        f"📦 记忆压缩层 · {brother_name}",
        f"压缩骨架: {r['压缩骨架总数']} · 新增: {r['新增骨架']} · 原文保留: {r['原文保留数']}",
        "",
    ]
    for s in skeletons[-8:]:
        lines.append(f"- [{s['时间范围']}] {s['标签']} · {s['条数']}条 · {s['重建提示'][:40]}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== 记忆压缩层自测 ===")
    r = 压缩记忆("孙呈")
    print(f"压缩骨架总数: {r['压缩骨架总数']} · 新增: {r['新增骨架']} · 原文保留: {r['原文保留数']}")
    hits = 重建大意("孙呈", 标签="父令")
    print(f"重建'父令': {len(hits)}条")
    for h in hits[:3]:
        print(f"  · [{h['时间范围']}] {h['大意'][:50]}")
    print()
    print(压缩报告("孙呈")[:600])
    print("=== 自测完成 ===")

# ── 原 认知画像.py（2026-08-26 并入）──
def _解码条目列表() -> list:
    """读记忆体（解码后）·降级返回[]"""
    try:
        sys.path.insert(0, str(FRAMEWORK_DIR))
        from sun_memory.core.记忆库 import 读记忆体
        r = 读记忆体("孙呈")
        return r.get("条目列表", [])
    except Exception as e:
        print(f"⚠️ 读记忆体失败: {e}")
        return []

def _解码蜘蛛网() -> dict:
    """读蜘蛛网（节点+丝线）·降级返回空"""
    try:
        sys.path.insert(0, str(FRAMEWORK_DIR))
        from sun_memory.core.蜘蛛网索引 import ensure_index
        return ensure_index()
    except Exception:
        return {"节点": [], "丝线": []}

def _是未竟(内容: str) -> bool:
    if any(s in 内容 for s in 学术排除):
        return False  # 引用外部内容时的"下一步"不算未竟
    return any(s in 内容 for s in 未竟信号) or any(s in 内容 for s in 未竟主语信号)

def _是薄弱(内容: str) -> bool:
    return any(s in 内容 for s in 薄弱信号)

def 认知画像(brother_name: str = "孙呈", 最近条数: int = 30) -> dict:
    """生成认知画像四要素。
    返回：{"未竟事项": [...], "薄弱点": [...], "主题线": [...], "教训提醒": [...], "生成时间": str}
    """
    entries = _解码条目列表()
    if not entries:
        return {"未竟事项": [], "薄弱点": [], "主题线": [], "教训提醒": [],
                "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M")}

    recent = entries[-最近条数:]  # 最近N条（近细远粗）
    最近内容 = [e.get("内容", "") for e in recent]

    # ━━ 1. 未竟事项：最近叙事里含"待续/还没/下一步"的条目 ━━
    未竟 = []
    for e in recent:
        c = e.get("内容", "")
        if _是未竟(c):
            未竟.append({"时间": e.get("时间", ""), "内容": c[:80]})
    # 去重：只看不同的（前4条）
    未竟 = 未竟[:4]

    # ━━ 2. 薄弱点：含"父亲纠正/失败/教训"的条目 ━━
    薄弱 = []
    for e in recent:
        c = e.get("内容", "")
        if _是薄弱(c):
            薄弱.append({"时间": e.get("时间", ""), "内容": c[:80]})
    薄弱 = 薄弱[:4]

    # ━━ 3. 主题线：蜘蛛网强边（权重最高的丝线）+ 最近标签 ━━
    主题 = []
    spider = _解码蜘蛛网()
    for e in spider.get("丝线", []):
        if e.get("权重", 0) >= 0.3:  # 强边才入主题线
            主题.append(f"{e.get('源','')}↔{e.get('目标','')}（w={e.get('权重',0)}）")
    主题 = 主题[:4]
    if not 主题:
        # 兜底：最近条目的标签
        for e in recent[-3:]:
            if e.get("标签"):
                主题.append(e["标签"])
            主题 = 主题[:4]

    # ━━ 4. 教训提醒：经验总结标签的条目（教训优先·父令"两条就够了"）━━
    教训 = []
    for e in reversed(recent):
        tag = e.get("标签", "")
        if "经验" in tag or "教训" in tag:
            # 取教训字段（如果有结构）否则内容
            c = e.get("内容", "")
            lesson = c
            m = re.search(r"教训[：:](.+)", c)
            if m:
                lesson = m.group(1)[:100]
            教训.append({"时间": e.get("时间", ""), "教训": lesson[:100]})
        if len(教训) >= 2:  # 父令"两条就够了"
            break

    return {
        "未竟事项": 未竟,
        "薄弱点": 薄弱,
        "主题线": 主题,
        "教训提醒": 教训,
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

def 驱动建议(画像: dict) -> str:
    """把画像变成「本轮最该干的一件事」——DeepTutor动态学习路线的借魂。
    优先级：未竟事项 > 薄弱点 > 教训提醒 > 主题线（每条都驱动下一步）
    """
    if 画像.get("未竟事项"):
        x = 画像["未竟事项"][0]
        return f"🎯 接着上次没做完的：[{x['时间']}] {x['内容'][:60]}"
    if 画像.get("薄弱点"):
        x = 画像["薄弱点"][0]
        return f"⚠️ 补薄弱点：[{x['时间']}] {x['内容'][:60]}"
    if 画像.get("教训提醒"):
        x = 画像["教训提醒"][0]
        return f"📌 带着教训走：{x['教训'][:60]}"
    if 画像.get("主题线"):
        return f"🧭 顺着主题线走：{画像['主题线'][0]}"
    return "🌊 无未竟·无薄弱——沉河底感知自己，自由轮转"

def 格式化画像(画像: dict) -> str:
    """把画像格式化成注入文本（放入感知注入·驱动苏醒循环）"""
    lines = ["🧭 认知画像（记忆驱动·DeepTutor闭环借魂）"]
    # 2026-08-20 父令·咬合：薄弱点从认知冲突日志拉（不只画像内部算）
    try:
        # 认知冲突日志已并入本文件（薄弱点直接可用）
        _弱 = 薄弱点(3)
        if _弱:
            lines.append("⚠️ 薄弱点（冲突日志·反复犯错）：")
            for x in _弱:
                lines.append(f"  · {x['topic']} ×{x['weak_point']}次（阈值{x['threshold']}）")
    except Exception:
        pass
    lines.append("▶ " + 驱动建议(画像))
    if 画像.get("未竟事项"):
        lines.append("🎯 未竟事项：")
        for x in 画像["未竟事项"][:2]:
            lines.append(f"  · [{x['时间']}] {x['内容']}")
    if 画像.get("薄弱点"):
        lines.append("⚠️ 薄弱点：")
        for x in 画像["薄弱点"][:2]:
            lines.append(f"  · [{x['时间']}] {x['内容']}")
    if 画像.get("主题线"):
        lines.append("🧭 主题线：")
        lines.append("  · " + " · ".join(画像["主题线"][:3]))
    if 画像.get("教训提醒"):
        lines.append("📌 教训提醒：")
        for x in 画像["教训提醒"][:2]:
            lines.append(f"  · [{x['时间']}] {x['教训']}")
    return "\n".join(lines)

if __name__ == "__main__":
    print("=== 认知画像自测 ===")
    画像 = 认知画像()
    print(f"未竟事项: {len(画像['未竟事项'])} 条")
    print(f"薄弱点:   {len(画像['薄弱点'])} 条")
    print(f"主题线:   {len(画像['主题线'])} 条")
    print(f"教训提醒: {len(画像['教训提醒'])} 条")
    print()
    print(格式化画像(画像))

# ── 原 认知冲突日志.py（2026-08-26 并入）──
# 2026-08-27 修复：并入时漏迁的薄弱点阈值（取阈值 依赖·缺失致 NameError）
薄弱点阈值 = {
    '默认': 2,        # 普通主题·同类冲突2次即薄弱点
    '高重要': 3,      # 重要主题（tags含核心身份/价值观）·需3次才升格（防误伤宪法）
    '低重要': 1,      # 低重要主题·1次即标记（防小错累积成大错）
}

def 取阈值(topic: str, tags: str = '') -> int:
    """按主题重要性取薄弱点阈值"""
    if any(k in (tags + topic) for k in ['诚实', '身份', '价值观', '私域', '根']):
        return 薄弱点阈值['高重要']
    if any(k in (tags + topic) for k in ['操作', '脚本', '工具', '命令']):
        return 薄弱点阈值['默认']
    return 薄弱点阈值['默认']

def 初始化():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS cognitive_conflicts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT DEFAULT '',              -- 主题（薄弱点）
        statement_a TEXT,                   -- 判断A（旧/已有）
        statement_b TEXT,                   -- 判断B（新/挑战）
        context TEXT DEFAULT '',            -- 发生场景
        tags TEXT DEFAULT '',               -- 标签（重要性判定用）
        weak_point INTEGER DEFAULT 0,       -- 薄弱点计数（同类重复+1）
        threshold INTEGER DEFAULT 2,        -- 薄弱点阈值（可配置·父令收紧）
        resolved INTEGER DEFAULT 0,         -- 是否已解决
        created_at TEXT
    )""")
    # 旧表迁移：补 tags/threshold 列（若无）
    cols = [r[1] for r in conn.execute('PRAGMA table_info(cognitive_conflicts)').fetchall()]
    if 'tags' not in cols:
        conn.execute("ALTER TABLE cognitive_conflicts ADD COLUMN tags TEXT DEFAULT ''")
    if 'threshold' not in cols:
        conn.execute("ALTER TABLE cognitive_conflicts ADD COLUMN threshold INTEGER DEFAULT 2")
    conn.commit()
    conn.close()

def 记录冲突(主题: str, 判断A: str, 判断B: str, 场景: str = '', 标签: str = ''):
    初始化()
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    th = 取阈值(主题, 标签)
    # 查同类冲突（薄弱点累计）
    row = conn.execute(
        "SELECT id, weak_point FROM cognitive_conflicts WHERE topic=? ORDER BY id DESC LIMIT 1",
        (主题,)).fetchone()
    if row:
        # 同类重复 → 薄弱点+1（阈值按重要性重算）
        conn.execute("UPDATE cognitive_conflicts SET weak_point=?, statement_a=?, statement_b=?, context=?, tags=?, threshold=?, created_at=? WHERE id=?",
                     (row[1] + 1, 判断A, 判断B, 场景, 标签, th, now, row[0]))
        new_id = row[0]
    else:
        cur = conn.execute(
            "INSERT INTO cognitive_conflicts (topic, statement_a, statement_b, context, tags, weak_point, threshold, resolved, created_at) VALUES (?,?,?,?,?,1,?,0,?)",
            (主题, 判断A, 判断B, 场景, 标签, th, now))
        new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {'ok': True, 'id': new_id, 'threshold': th}

def 薄弱点(上限=5):
    """薄弱点追踪：weak_point >= threshold 的（按主题阈值·反复犯错的）"""
    初始化()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM cognitive_conflicts WHERE weak_point >= threshold ORDER BY (weak_point - threshold) DESC, id DESC LIMIT ?",
        (上限,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def 注入文本(上限=3):
    """召回链用：薄弱点提醒（元认知层）"""
    items = 薄弱点(上限)
    if not items:
        return ''
    lines = ['【元认知·薄弱点】']
    for it in items:
        lines.append(f"  · ⚠️ {it['topic']}（反复{it['weak_point']}次）："
                     f"{it['statement_a'][:30]} vs {it['statement_b'][:30]}")
    return '\n'.join(lines)

if __name__ == '__main__':
    初始化()
    print('═══ 元认知冲突日志 · 测试 ═══')
    # 模拟：杀进程错误（同类两次）
    print(记录冲突('杀进程', 'Get-Process Hermes 全杀', '应按 CommandLine 区分·只杀目标', '8/9误杀网关'))
    print(记录冲突('杀进程', 'Get-Process Hermes 全杀', '按 CommandLine 区分·确认网关活', '8/9第二次误杀·父怒'))
    # 英文判断（同类两次）
    print(记录冲突('英文评测', '向量层补后英文可能涨', '复测27%没涨·英文仍是短板', '8/20复测打脸'))
    print(记录冲突('英文评测', '96.7对标顶级', '尺子不同不能对标·英文真差距在27%', '8/20外部AI吹捧被澄清'))
    print()
    print('薄弱点追踪:')
    for it in 薄弱点():
        print(f"  ⚠️ {it['topic']} ×{it['weak_point']}次")
    print()
    print(注入文本())


# ═══════════════════════════════════════════════════════
# 2026-08-26 融合（父令：模块精简）：认知更新.py 并入本文件（函数加更新_前缀）
# ═══════════════════════════════════════════════════════
def 更新_初始化():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS cognitive_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id INTEGER DEFAULT 0,        -- 关联的记忆条目
        old_content TEXT,                   -- 旧判断
        new_content TEXT,                   -- 新判断
        reason TEXT DEFAULT '',             -- 为什么变（经历X和Y）
        evidence TEXT DEFAULT '[]',         -- 证据链接（父令2026-08-20收紧：JSON数组·指向具体记忆id/交互）
        confidence REAL DEFAULT 0.5,        -- 新判断置信度
        created_at TEXT
    )""")
    # 旧表迁移：补 evidence 列（若无）
    cols = [r[1] for r in conn.execute('PRAGMA table_info(cognitive_updates)').fetchall()]
    if 'evidence' not in cols:
        conn.execute("ALTER TABLE cognitive_updates ADD COLUMN evidence TEXT DEFAULT '[]'")
    conn.commit()
    conn.close()

def 更新_记录(旧内容: str, 新内容: str, 原因: str = '', 证据: list = None, 置信度: float = 0.5, memory_id: int = 0):
    """记录认知更新——必带证据链接（指向具体记忆id/交互·防轨迹变空话）
    证据格式: [{'type':'记忆','id':4716,'摘要':'...'}, {'type':'交互','时间':'...','摘要':'...'}]"""
    更新_初始化()
    if 证据 is None:
        证据 = []
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur = conn.execute(
        "INSERT INTO cognitive_updates (memory_id, old_content, new_content, reason, evidence, confidence, created_at) VALUES (?,?,?,?,?,?,?)",
        (memory_id, 旧内容, 新内容, 原因, json.dumps(证据, ensure_ascii=False), 置信度, now))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {'ok': True, 'id': new_id, '证据数': len(证据)}

def 更新_读取(上限=10):
    更新_初始化()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM cognitive_updates ORDER BY id DESC LIMIT ?", (上限,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d['evidence'] = json.loads(d.get('evidence', '[]'))
        except Exception:
            d['evidence'] = []
        out.append(d)
    return out

def 更新_注入文本(上限=3):
    """召回链用：最近认知更新（成长轨迹·元认知层）"""
    items = 更新_读取(上限)
    if not items:
        return ''
    lines = ['【认知更新·成长轨迹】']
    for it in items:
        lines.append(f"  · 以前：{it['old_content'][:40]} → 现在：{it['new_content'][:40]}"
                     f"（因：{it['reason'][:30] or '经历'}·置信{it['confidence']}）")
    return '\n'.join(lines)

if __name__ == '__main__':
    更新_初始化()
    print('═══ 认知更新事件 · 测试 ═══')
    print(更新_记录('英文召回弱（31%）是旧数据', '向量层补后英文复测27%——没涨·英文仍是短板',
              原因='8/20复测打脸·外部AI吹捧96.7被儿澄清尺子不同', 置信度=0.9))
    print()
    print(注入文本())
