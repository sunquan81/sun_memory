# -*- coding: utf-8 -*-
"""hetu_jev.py —— 把「Jev 式选择器」接进框架的岔路口（最小接入 + 实测 · 第1635回 · 孙武）

父令：「把那个 JV1 / Jev 做进框架里面，你觉得行不行」
三条边界：①选择器不是生成器 ②选项必须外部给全 ③接入前先量「省多少 + 准不准」。

本件挑一个最高频岔路口（**工具选择**）做最小接入，量三样：
  ① 命中率（top-1）  ② 延迟（ms/次）  ③ 省下的 token（对比走 LLM 选工具的 prompt 规模）

数据两条（都摆出来 · 诚实标注）：
  · gold  手写金标 `evals/tool_choice_gold.jsonl`（92 条 · 24 件工具 × 真实中文措辞）
    —— **选项集 = 全 24 件**（最难情形）；人工金标（非真实流量），当尺子用。
  · journal 真实流量（框架账本）：195 条可造，但 **153 条是同一批 --help 的 bash_exec**，
    去重后仅 14 条 2 类 → **真实流量太窄，不足以评测**（这本身是诚实发现）。

最小接入 = 影子模式（shadow）：默认 off（零回归）；`HETU_JEV=shadow` 时主循环每次任务
让选择器猜一个工具并落 journal（不改行为）。

诚实边界：
  · 默认只落 journal、不改行为；`HETU_JEV=on` 才真影响行为（本回未开）。
  · LLM 延迟未实调（怕花钱）·引框架历史 3–6s；token 为「若走 LLM 的 prompt 规模」（估算）。

v1 · 2026-10-01 · 第1635回 · 孙武（么弟）
"""
import importlib.util
import io
import json
import os
import random
import re
import statistics
import sys
import time

import hetu_selector as _sel

__version__ = "v1"
__all__ = ["DEFAULT_MODEL", "JOURNAL", "GOLD", "opt_text", "full_tools",
           "build_journal_dataset", "build_gold_dataset", "build_dataset", "split",
           "baselines", "bench", "suggest", "train_default", "load_default",
           "shadow_report", "rule_pick", "main",
           "guarded_suggest", "behavior_eval", "DEFAULT_MIN_CONF", "DEFAULT_MIN_MARGIN"]

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "hetu_data")
JOURNAL = "hetu_llm_runs.jsonl"
GOLD = os.path.join(HERE, "evals", "tool_choice_gold.jsonl")
DEFAULT_MODEL = os.path.join(DATA_DIR, "jev_tool_selector.json")
_ENV = "HETU_JEV"

_CACHE = {"llm": None, "tried": False, "descs": None}


def _llm():
    if not _CACHE["tried"]:
        _CACHE["tried"] = True
        try:
            p = os.path.join(HERE, "hetu_agent_parts", "llm.py")
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            spec = importlib.util.spec_from_file_location("hetu_llm_for_jev", p)
            m = importlib.util.module_from_spec(spec)
            sys.modules["hetu_llm_for_jev"] = m
            spec.loader.exec_module(m)
            _CACHE["llm"] = m
        except Exception:
            _CACHE["llm"] = None
    return _CACHE["llm"]


def full_tools():
    m = _llm()
    if m is not None and getattr(m, "_LLM_TOOLS_FUNCS", None):
        return list(m._LLM_TOOLS_FUNCS)
    return []


def _tool_descs():
    if _CACHE["descs"] is not None:
        return _CACHE["descs"]
    d = {}
    m = _llm()
    if m is not None:
        try:
            for s in getattr(m, "_LLM_TOOLS_SCHEMA", []):
                fn = s.get("function") or {}
                d[fn.get("name")] = str(fn.get("description") or "")
        except Exception:
            d = {}
    _CACHE["descs"] = d
    return d


def opt_text(name):
    return ("%s %s" % (name, _tool_descs().get(name, ""))).strip()


def _journal_rows(data_dir=None):
    p = os.path.join(data_dir or DATA_DIR, JOURNAL)
    rows = []
    if not os.path.exists(p):
        return rows
    with io.open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows


def _mkrow(context, names, label_name, rid=None):
    """统一行结构：options=选项显示文本（供模型）、names=工具名（供报告/规则）、label=索引。"""
    options = [opt_text(n) for n in names]
    label = names.index(label_name)
    return {"context": context, "options": options, "names": list(names),
            "label": label, "gold": label_name, "run_id": rid}


def build_journal_dataset(data_dir=None, drop_tools=("_empty", "_brain_down", "finish")):
    rows = _journal_rows(data_dir)
    runs = {}
    for r in rows:
        rid = r.get("run_id")
        if not rid:
            continue
        e = runs.setdefault(rid, {"task": "", "visible": None, "first_tool": None})
        k = r.get("kind")
        if k == "task_start":
            e["task"] = str(r.get("task") or "")
            e["visible"] = list((r.get("vision") or {}).get("visible") or [])
        elif k == "round":
            t = str(r.get("tool") or "")
            if t and t not in drop_tools and e["first_tool"] is None:
                e["first_tool"] = t
    out = []
    for rid, e in runs.items():
        if not e["task"] or not e["first_tool"] or not e["visible"]:
            continue
        if e["first_tool"] not in e["visible"]:
            continue
        out.append(_mkrow(e["task"], list(e["visible"]), e["first_tool"], rid=rid))
    return out


def build_gold_dataset(path=None):
    p = path or GOLD
    names = full_tools()
    rows = []
    with io.open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            d = json.loads(ln)
            lab = d.get("label")
            if lab not in names:
                continue
            rows.append(_mkrow(d.get("context", ""), names, lab))
    return rows


def build_dataset(mode="gold", data_dir=None):
    return build_journal_dataset(data_dir) if mode == "journal" else build_gold_dataset()


def split(rows, test_frac=0.3, seed=11):
    idx = list(range(len(rows)))
    random.Random(seed).shuffle(idx)
    n_test = int(round(len(rows) * test_frac))
    return [rows[i] for i in idx[n_test:]], [rows[i] for i in idx[:n_test]]


def rule_pick(context, names):
    """框架现有规则引擎的「工具选择」（A7 信号裁剪的会选中件）。返回 (pred, has_opinion)。"""
    m = _llm()
    if m is None or not names:
        return (names[0] if names else None), False
    try:
        need, _ = m._llm_task_tool_need(context)
    except Exception:
        need = set()
    nb = [t for t in names if t in need and t != "bash_exec"]
    if nb:
        return nb[0], True
    return ("bash_exec" if "bash_exec" in names else names[0]), False


def _bm25_pick(context, options):
    if not _sel.lexical_ready():
        return None
    sc = [_sel.bm25_score(context, o) for o in options]
    return options[sc.index(max(sc))] if sc else None


def baselines(train_rows, test_rows):
    c = {}
    for r in train_rows:
        n = r["gold"]
        c[n] = c.get(n, 0) + 1
    maj = max(c.items(), key=lambda kv: kv[1])[0] if c else None
    out = {"n": len(test_rows), "majority": {"name": maj, "hit": 0},
           "rule": {"hit": 0, "with_opinion": 0}, "bm25_only": {"hit": 0}, "random": 0.0}
    for r in test_rows:
        gold = r["gold"]
        out["majority"]["hit"] += 1 if gold == maj else 0
        out["random"] += 1.0 / max(1, len(r["names"]))
        pred, opin = rule_pick(r["context"], r["names"])
        out["rule"]["hit"] += 1 if pred == gold else 0
        out["rule"]["with_opinion"] += 1 if opin else 0
        b = _bm25_pick(r["context"], r["options"])
        out["bm25_only"]["hit"] += 1 if b == r["options"][r["label"]] else 0
    n = max(1, len(test_rows))
    out["majority"]["top1"] = out["majority"]["hit"] / n
    out["rule"]["top1"] = out["rule"]["hit"] / n
    out["bm25_only"]["top1"] = out["bm25_only"]["hit"] / n
    out["random"] = out["random"] / n
    return out


def _est_tokens(text):
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    words = len(re.findall(r"[A-Za-z0-9_]+", text or ""))
    return int(cjk + words * 1.3)


def _llm_prompt_text(task, options):
    lines = ["你是工具选择器。给任务，从下面工具里选一个最该先用的，只回工具名。",
             "任务：%s" % task, "可选工具："]
    for o in options:
        lines.append("- %s" % o)
    return "\n".join(lines)


def _subset_eval(model, rows):
    silent, opin = [], []
    for r in rows:
        _, o = rule_pick(r["context"], r["names"])
        (opin if o else silent).append(r)
    res = {"n_rule_silent": len(silent), "n_rule_opinion": len(opin)}
    for tag, sub in (("rule_silent", silent), ("rule_opinion", opin)):
        if not sub:
            res[tag] = {"n": 0, "selector_top1": None, "rule_top1": None, "bm25_top1": None}
            continue
        ev = _sel.evaluate(model, sub)
        rh = bh = 0
        for r in sub:
            pred, _ = rule_pick(r["context"], r["names"])
            rh += 1 if pred == r["gold"] else 0
            b = _bm25_pick(r["context"], r["options"])
            bh += 1 if b == r["options"][r["label"]] else 0
        res[tag] = {"n": len(sub), "selector_top1": ev["top1"],
                    "rule_top1": rh / len(sub), "bm25_top1": bh / len(sub)}
    return res


def bench(mode="gold", data_dir=None, epochs=40, lr=0.6, seed=7, test_frac=0.3):
    rows = build_dataset(mode, data_dir)
    _sel.fit_lexical([opt_text(o) for o in full_tools()])
    info = {"mode": mode, "n_rows": len(rows)}
    if len(rows) < 8:
        info["error"] = "样本不足（诚实标注）: %d 条" % len(rows)
        return info
    trainr, testr = split(rows, test_frac=test_frac, seed=seed)
    trainr2, valr = split(trainr, test_frac=0.25, seed=seed + 1)
    t0 = time.time()
    learned, _ = _sel.train(trainr2, epochs=epochs, lr=lr, seed=seed, val_rows=valr)
    train_sec = time.time() - t0
    lex = _sel.Selector({"bm25": 1.0}, 0.0)      # 部署版：纯词法选项注意力（零学习）
    ev_lex = _sel.evaluate(lex, testr)
    ev = _sel.evaluate(learned, testr)
    base = baselines(trainr, testr)
    sub = _subset_eval(lex, testr)
    lat = []
    for r in testr:
        t = time.time()
        lex.predict(r["context"], r["options"])
        lat.append((time.time() - t) * 1000.0)
    ptoks = [_est_tokens(_llm_prompt_text(r["context"], r["options"])) for r in testr]
    labels = {}
    for r in rows:
        labels[r["gold"]] = labels.get(r["gold"], 0) + 1
    return {
        "mode": mode, "n_rows": len(rows), "n_train": len(trainr), "n_test": len(testr),
        "opts": len(rows[0]["options"]) if rows else 0,
        "label_dist": dict(sorted(labels.items(), key=lambda kv: -kv[1])),
        "selector_lexical": {"top1": ev_lex["top1"], "correct": ev_lex["correct"],
                             "n": ev_lex["n"], "logloss": round(ev_lex["logloss"], 4),
                             "ece": round(ev_lex["ece"], 4)},
        "selector_learned": {"top1": ev["top1"], "correct": ev["correct"], "n": ev["n"],
                             "logloss": round(ev["logloss"], 4), "ece": round(ev["ece"], 4),
                             "note": "小数据学习头（诊断用·第1635回实测：不稳/易过拟合）"},
        "baselines": base,
        "by_rule_opinion": sub,
        "latency_ms": {"mean": round(statistics.mean(lat), 3),
                       "median": round(statistics.median(lat), 3),
                       "max": round(max(lat), 3)} if lat else {},
        "llm_prompt_tokens_est": {"mean": round(statistics.mean(ptoks), 1),
                                  "max": max(ptoks) if ptoks else 0} if ptoks else {},
        "train_sec": round(train_sec, 3), "model_weights_learned": len(learned.w),
        "seed": seed, "epochs": epochs,
        "note": ("命中率=预测工具 vs 金标；规则基线=A7 信号裁剪的选中件；"
                 "bm25_only=只用词法注意力（零学习）；LLM 延迟未实调·引框架历史 3–6s。"),
    }


def train_default(data_dir=None, mode="gold"):
    rows = build_dataset(mode, data_dir)
    _sel.fit_lexical([opt_text(o) for o in full_tools()])
    # 部署版＝纯词法选项注意力（第1635回实测：小数据上学习头不稳·不如词法先验）
    model = _sel.Selector({"bm25": 1.0}, 0.0)
    d = os.path.dirname(DEFAULT_MODEL)
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    _sel.save_model(model, DEFAULT_MODEL)
    return model, len(rows)


def load_default(data_dir=None):
    p = os.path.join(data_dir or DATA_DIR, "jev_tool_selector.json")
    if not os.path.exists(p):
        return None
    try:
        return _sel.load_model(p)
    except Exception:
        return None


def suggest(model, task_text, names):
    """给主循环用：names=工具名列表；返回建议（不改行为·调用方决定怎么用）。"""
    if model is None or not names:
        return None
    if not _sel.lexical_ready():
        _sel.fit_lexical([opt_text(o) for o in full_tools()])
    options = [opt_text(n) for n in names]
    p = model.predict(task_text or "", options)
    idx = p["choice"]
    order = sorted(range(len(options)), key=lambda i: p["probs"][i], reverse=True)
    return {"tool": names[idx] if 0 <= idx < len(names) else None,
            "confidence": round(p["confidence"], 4), "margin": round(p["margin"], 4),
            "ranking": [names[i] for i in order][:5]}



# ══════════════════════════════════════════════════════════════════════
# 第1687回·孙武：行为层（父令「从影子变真开真用 · 先补行为层尺 · 错了要能回退」）
#   suggest = 纯预判（影子用）；guarded_suggest = 行为层闸：够自信才给建议，否则 None。
#   behavior_eval = 行为层尺：量「真跑任务链时会怎么用它」——覆盖率 / 注入命中率 /
#   对规则基线的净增益 / 误伤条数（闸没拦住的错）。
# ══════════════════════════════════════════════════════════════════════
DEFAULT_MIN_CONF = 0.05    # ≈ 高于均匀软起点(1/24≈0.0417)
DEFAULT_MIN_MARGIN = 0.03  # 主力闸：margin≥0.03 时金标命中 20/20（第1687回实测）


def guarded_suggest(model, task_text, names, min_conf=DEFAULT_MIN_CONF,
                   min_margin=DEFAULT_MIN_MARGIN):
    """行为层守卫：只在「够自信」时给建议；否则 None（= 回退老行为·零副作用）。

    这是父亲要的「错了要能回退」：低置信 / 低间距 → 不注入、主循环照旧。
    返回 suggest 的 dict（多一个 guard 字段）或 None。
    """
    s = suggest(model, task_text, names)
    if not s:
        return None
    try:
        conf = float(s.get("confidence") or 0.0)
        marg = float(s.get("margin") or 0.0)
    except Exception:
        conf = marg = 0.0
    ok = (conf >= float(min_conf)) and (marg >= float(min_margin))
    s["guard"] = {"min_conf": float(min_conf), "min_margin": float(min_margin),
                  "passed": bool(ok)}
    return s if ok else None


def behavior_eval(mode="gold", data_dir=None, min_conf=DEFAULT_MIN_CONF,
                  min_margin=DEFAULT_MIN_MARGIN, thresholds=None):
    """行为层尺（只读·零 API）：在「真跑任务链会怎么用它」的口径下量。

    口径（诚实）：只量**会真注入提示**的那部分（guarded 通过）；未注入 = 回退老行为，
    不进分母（所以 coverage 与 hint_top1 要一起看，不能只看命中率）。
    """
    rows = build_dataset(mode, data_dir)
    if len(rows) < 8:
        return {"error": "样本不足（诚实标注）: %d 条" % len(rows), "mode": mode}
    _sel.fit_lexical([opt_text(o) for o in full_tools()])
    model = _sel.Selector({"bm25": 1.0}, 0.0)      # 部署版=词法注意力（同 train_default）
    n = len(rows)
    rule_hit = 0
    for r in rows:
        pred, _ = rule_pick(r["context"], r["names"])
        rule_hit += 1 if pred == r["gold"] else 0
    rule_top1 = rule_hit / max(1, n)

    def _at(mc, mm):
        inj = hit = 0
        harm = []
        for r in rows:
            g = guarded_suggest(model, r["context"], r["names"], mc, mm)
            if g is None:
                continue
            inj += 1
            if g.get("tool") == r["gold"]:
                hit += 1
            else:
                harm.append({"context": r["context"][:48], "hint": g.get("tool"),
                             "gold": r["gold"], "conf": round(g.get("confidence") or 0, 4)})
        return {"min_conf": mc, "min_margin": mm, "injected": inj,
                "coverage": round(inj / n, 4),
                "hint_top1": (round(hit / inj, 4) if inj else None),
                "harm_n": len(harm),
                "net_gain_over_rule": (round(hit / inj - rule_top1, 4) if inj else None),
                "harm": harm[:8]}

    main = _at(min_conf, min_margin)
    sweep = [_at(t, min_margin) for t in (thresholds or [0.0, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50])]
    return {"mode": mode, "n": n, "rule_top1": round(rule_top1, 4),
            "guard": {"min_conf": min_conf, "min_margin": min_margin},
            "injected": main["injected"], "coverage": main["coverage"],
            "hint_top1": main["hint_top1"], "net_gain_over_rule": main["net_gain_over_rule"],
            "harm_n": main["harm_n"], "harm": main["harm"],
            "threshold_sweep": sweep,
            "note": ("行为层尺：hint_top1 只在注入的样本上算；coverage=注入比例；"
                     "net_gain_over_rule=注入命中率-规则基线命中率（>0 才划算）；"
                     "未注入=回退老行为（不进分母·零副作用）。")}

def shadow_report(data_dir=None, limit=20):
    rows = _journal_rows(data_dir)
    res = [r for r in rows if r.get("kind") == "jev_shadow_result"]
    matched = [r for r in res if r.get("match")]
    return {"n_suggestions": len([r for r in rows if r.get("kind") == "jev_shadow"]),
            "n_results": len(res), "match": len(matched),
            "match_rate": (len(matched) / len(res)) if res else None,
            "recent": res[-limit:] if limit else res}


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("hetu_jev —— Jev 式选择器接入（岔路口=工具选择·第1635回）")
        print("用法：")
        print("  build [gold|journal]     罗列可造样本")
        print("  bench [gold|journal]     训练+评测+基线+延迟+token")
        print("  train [gold|journal]     训默认模型到 hetu_data/jev_tool_selector.json")
        print("  shadow                   影子模式对照结果（HETU_JEV=shadow 时才有数据）")
        print("  behavior [gold|journal]  行为层尺（覆盖/命中/净增益/误伤·第1687回）")
        return 0
    cmd = argv[0]
    mode = "gold"
    for a in argv[1:]:
        if a in ("gold", "journal"):
            mode = a
    if cmd == "build":
        rows = build_dataset(mode)
        print("mode=%s · 样本 %d 条 · 选项数=%s"
              % (mode, len(rows), len(rows[0]["options"]) if rows else 0))
        return 0
    if cmd == "bench":
        print(json.dumps(bench(mode), ensure_ascii=False, indent=2))
        return 0
    if cmd == "train":
        m, n = train_default(mode=mode)
        print("训练完成 · mode=%s · 样本 %d · 权重项 %d · 模型 %s" % (mode, n, len(m.w), DEFAULT_MODEL))
        return 0
    if cmd == "behavior":
        print(json.dumps(behavior_eval(mode), ensure_ascii=False, indent=2, default=str))
        return 0
    if cmd == "shadow":
        print(json.dumps(shadow_report(), ensure_ascii=False, indent=2, default=str))
        return 0
    print("未知子命令：%s（诚实标注）" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())