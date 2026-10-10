# -*- coding: utf-8 -*-
"""hetu_selector.py —— Jev 式「选项注意力」选择器（零依赖 · 第1635回 · 孙武）

════════════════════════════════════════════════════════════════════
父令（2026-10-01 凌晨 · 大哥转达第三节第三件）：
  「我想把那个 JV1 或者还是那个 Jev 那个角色，这一阵特别火的那个，做进这个框架里面，
   你觉得行不行」—— 本件是那个「行不行」的**最小接入**的第一半：把 Jev 的**输入/输出
   形状**（一段上下文 + N 个选项 → 每个选项一个概率 + 把握度 · 一次前向 · 亚毫秒）
   用**纯标准库**实现（不进 torch 依赖 · 不破「零依赖」家规）。

Jev 的核心机制（大哥摸清的底）：
  · **选项注意力头**：每个选项变成一个 query，对上下文分配注意力，softmax 跨选项出概率。
  · **选择器不是生成器**：在给定选项里挑，不生成内容；**选项必须外部给全**。

本件的实现（选项注意力 = 词法相关性注意力 + 可学习校正）：
  · 注意力主体：**BM25 词法相关性** —— 拿「上下文 token」去对每个**选项文本**算相关度
    （就是「这个选项对上下文分配了多少注意力」的经典近似 · 零训练即可用）。
  · 可学习校正：score = w·f + b，f 含交互特征 {x:共享词}/选项先验 {o:*}/共享二元组/重叠桶
    **外带一列 bm25**（初值给 1.0 → 训练只学「在 BM25 之上还差多少」）。
  · probs = softmax over options ； confidence = max ； margin = top1−top2。
  · 训练 = 交叉熵 + SGD + L2（纯 Python · seed 固定 → 同输入同结果）。

诚实边界（照实说）：
  · 这是 **Jev 的「形」**（同输入输出形状 + 选项注意力思想），**不是** TypeSafe Jev 的复现；
    真 Jev 闭源。本件是**零依赖 · 可离线 · 亚毫秒**的自家替身，给「规则能判/词法能判」的
    岔路口用 —— **不替代大模型生成**。
  · 精度取决于数据；数据少时纯学习头会**不如**词法先验（第1635回实测：见 hetu_jev bench）。

v1 · 2026-10-01 · 第1635回 · 孙武（么弟）
════════════════════════════════════════════════════════════════════
"""
import io
import json
import math
import os
import random
import re
import sys
import time

__version__ = "v1"
__all__ = ["tokenize", "feats", "fit_lexical", "lexical_ready", "bm25_score",
           "Selector", "train", "evaluate", "ece", "load_model", "save_model", "main"]

_ASCII = re.compile(r"[a-z0-9_]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")

# 词法语料（选项文本 → IDF/平均长度）。由 fit_lexical 装；无则 bm25 列退化为 0。
_LEX = {"idf": None, "avgdl": 1.0, "n": 0}


def tokenize(s):
    s = (s or "").lower()
    toks = _ASCII.findall(s)
    toks += _CJK.findall(s)
    return toks


def _bigrams(toks):
    return set("%s_%s" % (toks[i], toks[i + 1]) for i in range(len(toks) - 1))


def fit_lexical(texts):
    """用一组「选项文本」建 IDF 语料（域内自洽：就在这 N 个选项上算）。"""
    docs = [tokenize(t) for t in texts if str(t or "").strip()]
    n = len(docs)
    if n == 0:
        _LEX.update({"idf": None, "avgdl": 1.0, "n": 0})
        return _LEX
    df = {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    idf = {w: math.log(1.0 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
    _LEX.update({"idf": idf, "avgdl": sum(len(d) for d in docs) / float(n), "n": n})
    return _LEX


def lexical_ready():
    return _LEX["idf"] is not None


def bm25_score(context, option_text, k1=1.5, b=0.75):
    """选项注意力（词法）：上下文 token 对「选项文本」的 BM25 相关度。"""
    idf = _LEX["idf"]
    if idf is None:
        return 0.0
    d = tokenize(option_text)
    if not d:
        return 0.0
    f = {}
    for w in d:
        f[w] = f.get(w, 0) + 1
    avgdl = _LEX["avgdl"] or 1.0
    s = 0.0
    for w in set(tokenize(context)):
        if w not in f:
            continue
        s += idf.get(w, 0.0) * (f[w] * (k1 + 1)) / (f[w] + k1 * (1 - b + b * len(d) / avgdl))
    return s


def feats(context, option):
    ct = tokenize(context)
    ot = tokenize(option)
    cs, os_ = set(ct), set(ot)
    f = {}
    inter = cs & os_
    for t in inter:
        f["x:" + t] = f.get("x:" + t, 0) + 1
    for t in os_:
        f["o:" + t] = f.get("o:" + t, 0) + 1
    f["ov:%d" % min(len(inter), 5)] = 1.0
    ratio = len(inter) / float(max(1, len(os_)))
    f["or:%d" % min(int(ratio * 10), 10)] = 1.0
    f["bias"] = 1.0
    for bg in (_bigrams(ct) & _bigrams(ot)):
        f["xb:" + bg] = f.get("xb:" + bg, 0) + 1
    if lexical_ready():
        # 归一化 BM25 列（原值可达 20–40·直接喂 SGD 会发散）→ 压到 ~0..2
        f["bm25"] = min(bm25_score(context, option), 40.0) / 20.0
    return f


def _dot(w, f):
    s = 0.0
    for k, v in f.items():
        s += w.get(k, 0.0) * v
    return s


def _softmax(xs):
    if not xs:
        return []
    m = max(xs)
    es = [math.exp(x - m) for x in xs]
    z = sum(es) or 1.0
    return [e / z for e in es]


class Selector(object):
    """选项注意力选择器（w: dict 特征→权重；bm25 列由 fit_lexical 提供）。"""

    def __init__(self, w=None, b=0.0, meta=None):
        self.w = dict(w or {})
        self.b = float(b or 0.0)
        self.meta = dict(meta or {})

    def scores(self, context, options):
        return [_dot(self.w, feats(context, o)) + self.b for o in options]

    def predict(self, context, options):
        sc = self.scores(context, options)
        ps = _softmax(sc)
        if not ps:
            return {"options": [], "probs": [], "choice": -1, "confidence": 0.0,
                    "margin": 0.0, "scores": []}
        order = sorted(range(len(ps)), key=lambda i: ps[i], reverse=True)
        top = ps[order[0]]
        second = ps[order[1]] if len(order) > 1 else 0.0
        return {"options": list(options), "probs": ps, "choice": order[0],
                "confidence": top, "margin": top - second, "scores": sc}

    def to_dict(self):
        return {"w": self.w, "b": self.b, "meta": self.meta, "version": __version__,
                "lex": {"idf": _LEX["idf"], "avgdl": _LEX["avgdl"], "n": _LEX["n"]}}


def _update(w, f, grad_scale, lr, l2):
    for k, v in f.items():
        g = grad_scale * v
        if g > 1.0:
            g = 1.0
        elif g < -1.0:
            g = -1.0
        nv = w.get(k, 0.0) * (1.0 - lr * l2) + lr * g
        if nv == 0.0:
            w.pop(k, None)
        else:
            w[k] = nv


def train(rows, epochs=30, lr=0.2, l2=1e-3, seed=7, init_bm25=1.0, val_rows=None,
          freeze_bm25=True, min_improve=0.08, verbose=False, log_every=0):
    """rows: [{context, options:[display_text], label:int}]。返回 (Selector, loss_curve)。

    val_rows 给定时**早停**：每轮后算验证 top-1，保留最好那轮的权重
    （防止在 92 条这种小数据上把词法先验练坏——第1635回实测教训）。
    """
    rnd = random.Random(seed)
    w = {"bm25": float(init_bm25)} if lexical_ready() else {}
    b = 0.0
    if val_rows:
        best_top1 = evaluate(Selector(w, b), val_rows)["top1"]   # 含「第 0 轮＝纯词法先验」
    else:
        best_top1 = -1.0
    best_w, best_b, best_ep = dict(w), b, 0
    idx = list(range(len(rows)))
    hist = []
    for ep in range(1, int(epochs) + 1):
        rnd.shuffle(idx)
        total_loss, n = 0.0, 0
        for i in idx:
            r = rows[i]
            opts = r["options"]
            lab = int(r["label"])
            if not (0 <= lab < len(opts)):
                continue
            fs = [feats(r["context"], o) for o in opts]
            sc = [_dot(w, f) + b for f in fs]
            ps = _softmax(sc)
            total_loss += -math.log(max(ps[lab], 1e-12))
            n += 1
            for j, f in enumerate(fs):
                gf = ps[j] - (1.0 if j == lab else 0.0)
                if freeze_bm25 and "bm25" in f:
                    f2 = {k: v for k, v in f.items() if k != "bm25"}
                    _update(w, f2, gf, lr, l2)
                else:
                    _update(w, f, gf, lr, l2)
        hist.append(total_loss / max(1, n))
        if val_rows:
            v = evaluate(Selector(w, b), val_rows)
            # 只有验证集上**明显更好**（≥min_improve）才离开「第0轮＝纯词法先验」——
            # 小数据上学习头收益不稳，宁守先验（第1635回实测教训）
            if v["top1"] > best_top1 + min_improve:
                best_top1, best_ep, best_w, best_b = v["top1"], ep, dict(w), b
        if verbose and log_every and ep % log_every == 0:
            print("  epoch %d  loss=%.4f%s" % (ep, hist[-1],
                  ("  val_top1=%.3f" % (evaluate(Selector(w, b), val_rows)["top1"] if val_rows else 0)) if val_rows else ""))
    if val_rows and best_ep:
        w, b = best_w, best_b
    return Selector(w, b, {"epochs": epochs, "lr": lr, "l2": l2, "seed": seed,
                           "n_train": len(rows), "lexical": lexical_ready(),
                           "freeze_bm25": freeze_bm25, "best_epoch": best_ep, "val_top1": best_top1 if val_rows else None,
                           "loss_curve": hist}), hist


def ece(confs, corrects, bins=10):
    buckets = [[0, 0.0, 0] for _ in range(bins)]
    for c, ok in zip(confs, corrects):
        bi = min(bins - 1, int(c * bins))
        buckets[bi][0] += 1
        buckets[bi][1] += c
        buckets[bi][2] += 1 if ok else 0
    n = len(confs) or 1
    e = 0.0
    for bn, cs, cc in buckets:
        if bn == 0:
            continue
        e += (bn / float(n)) * abs(cc / float(bn) - cs / float(bn))
    return e


def evaluate(model, rows):
    n = correct = 0
    logloss = 0.0
    confs, oks = [], []
    per = {}
    for r in rows:
        opts = r["options"]
        lab = int(r["label"])
        if not (0 <= lab < len(opts)):
            continue
        p = model.predict(r["context"], opts)
        n += 1
        ok = (p["choice"] == lab)
        correct += 1 if ok else 0
        logloss += -math.log(max(p["probs"][lab], 1e-12))
        confs.append(p["confidence"])
        oks.append(ok)
        key = opts[lab].split()[0] if opts[lab] else str(lab)
        per.setdefault(key, [0, 0])
        per[key][0] += 1
        per[key][1] += 1 if ok else 0
    return {"n": n, "top1": (correct / n) if n else 0.0, "correct": correct,
            "logloss": (logloss / n) if n else 0.0,
            "ece": ece(confs, oks) if n else 0.0,
            "per_class": {k: {"n": v[0], "hit": v[1],
                              "acc": (v[1] / v[0]) if v[0] else 0.0}
                          for k, v in per.items()}}


def save_model(model, path):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(model.to_dict(), ensure_ascii=False))
    return path


def load_model(path):
    with io.open(path, encoding="utf-8") as f:
        d = json.load(f)
    lex = d.get("lex") or {}
    if lex.get("idf"):
        _LEX.update({"idf": lex["idf"], "avgdl": lex.get("avgdl") or 1.0,
                     "n": lex.get("n") or 0})
    return Selector(d.get("w") or {}, d.get("b") or 0.0, d.get("meta") or {})


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("hetu_selector —— Jev 式选项注意力选择器（零依赖·第1635回）")
        print("用法：")
        print("  predict <model.json> --context C --option A --option B [...]")
        print("  train <data.jsonl> --out m.json [--epochs 30] [--lr 0.5]")
        print("  eval <model.json> <data.jsonl>")
        return 0
    cmd = argv[0]
    if cmd == "predict":
        if len(argv) < 2:
            print("缺模型（诚实标注）"); return 2
        model = load_model(argv[1])
        ctx, opts = "", []
        i = 2
        while i < len(argv):
            if argv[i] == "--context" and i + 1 < len(argv):
                ctx = argv[i + 1]; i += 2
            elif argv[i] == "--option" and i + 1 < len(argv):
                opts.append(argv[i + 1]); i += 2
            else:
                i += 1
        p = model.predict(ctx, opts)
        for o, pr in zip(p["options"], p["probs"]):
            print("  %.4f  %s" % (pr, o))
        print("选择=%s · 把握=%.3f · 间距=%.3f"
              % (p["options"][p["choice"]] if p["choice"] >= 0 else "-",
                 p["confidence"], p["margin"]))
        return 0
    if cmd in ("train", "eval"):
        path = argv[1] if len(argv) > 1 else ""
        rows = []
        with io.open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    rows.append(json.loads(ln))
        # 训练/评测前先建词法语料（选项文本并集）
        corpus = []
        for r in rows:
            for o in r.get("options", []):
                if o not in corpus:
                    corpus.append(o)
        fit_lexical(corpus)
        if cmd == "train":
            out = "runs/selector.json"
            ep, lr = 30, 0.5
            for i, a in enumerate(argv):
                if a == "--out" and i + 1 < len(argv): out = argv[i + 1]
                if a == "--epochs" and i + 1 < len(argv): ep = int(argv[i + 1])
                if a == "--lr" and i + 1 < len(argv): lr = float(argv[i + 1])
            m, _ = train(rows, epochs=ep, lr=lr, verbose=True, log_every=max(1, ep // 5))
            d = os.path.dirname(os.path.abspath(out))
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            save_model(m, out)
            r = evaluate(m, rows)
            print("train n=%d · 训内 top1=%.4f · 模型=%s" % (len(rows), r["top1"], out))
            return 0
        model = load_model(argv[1])
        r = evaluate(model, rows)
        print("eval n=%d top1=%.4f logloss=%.4f ece=%.4f"
              % (r["n"], r["top1"], r["logloss"], r["ece"]))
        return 0
    print("未知子命令：%s（诚实标注）" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())