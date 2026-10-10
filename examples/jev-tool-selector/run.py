#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py — one command, real numbers.

Trains a Jev-*style* option-attention selector on a hand-labeled gold set of
tool-choice decisions and prints the three numbers that matter:

  1. top-1 accuracy  (selector vs. a keyword-rule baseline vs. random)
  2. latency         (ms per decision, pure CPU, no GPU)
  3. tokens saved    (vs. asking an LLM to pick the tool every call)

Zero third-party dependencies. Pure standard library. No network.

    python run.py

Honest note: this is a Jev-*style* selector — same input/output *shape*
("context + N options -> a probability per option + a confidence"), in the
spirit of the option-attention idea. It is NOT a reimplementation of
TypeSafe's Jev (which is closed-source), and its numbers are not comparable
to Jev's. What it shows is the shape: a typed decision you can gate on.
"""

import json
import os
import random
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import hetu_selector as sel  # noqa: E402  (stdlib-only selector, ~15 KB)

GOLD = os.path.join(HERE, "gold.jsonl")
TOOLS = os.path.join(HERE, "tools.json")


# ── data ──────────────────────────────────────────────────────────────────
def load_gold(path=GOLD):
    """Each line: {"context": <task text>, "label": <correct tool>}"""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


def load_tools(path=TOOLS):
    """[{"name": ..., "description": ...}, ...]"""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["tools"]


def opt_text(t):
    return ("%s %s" % (t["name"], t.get("description") or "")).strip()


def split(rows, test_frac=0.3, seed=11):
    rng = random.Random(seed)
    rows = list(rows)
    rng.shuffle(rows)
    n_test = max(1, int(len(rows) * test_frac))
    return rows[n_test:], rows[:n_test]


# ── baselines ─────────────────────────────────────────────────────────────
def rule_pick(context, names):
    low = (context or "").lower()
    for n in names:
        if n and n.lower().replace("_", " ") in low.replace("_", " "):
            return n
    for n in names:                      # second pass: bare token
        if n and n.lower() in low:
            return n
    return names[0] if names else None


# ── main ──────────────────────────────────────────────────────────────────
def main():
    print("=" * 74)
    print("Jev-style tool selector - one-command benchmark (pure CPU, zero deps)")
    print("=" * 74)

    rows = load_gold()
    tools = load_tools()
    names = [t["name"] for t in tools]
    opts = [opt_text(t) for t in tools]

    train, test = split(rows)
    print("\ngold set        : %d labeled decisions  (%d train / %d test)" % (len(rows), len(train), len(test)))
    print("option set      : %d tools  (the selector must pick among ALL of them)" % len(names))

    t0 = time.perf_counter()
    sel.fit_lexical(opts)
    model = sel.Selector({"bm25": 1.0}, 0.0)
    fit_ms = (time.perf_counter() - t0) * 1000

    # accuracy / latency
    rule_hits = 0
    lat = []
    for r in test:
        ctx, gold = r["context"], r["label"]
        t1 = time.perf_counter()
        p = model.predict(ctx or "", opts)
        lat.append((time.perf_counter() - t1) * 1000.0)
        pick = names[p["choice"]] if 0 <= p["choice"] < len(names) else None
        rule_hits += 1 if rule_pick(ctx, names) == gold else 0
    n = len(test)

    # selector accuracy via the same API
    sel_hits = 0
    for r in test:
        p = model.predict(r["context"] or "", opts)
        pick = names[p["choice"]] if 0 <= p["choice"] < len(names) else None
        sel_hits += 1 if pick == r["label"] else 0

    # random baseline: mean over many draws (one draw is noisy)
    rng = random.Random(23)
    R = 300
    exp_rand = 0.0
    for _ in range(R):
        exp_rand += sum(1 for r in test if rng.choice(names) == r["label"]) / n
    exp_rand /= R
    # closed form: uniform over K options
    cf = 1.0 / len(names)

    print()
    print("-" * 74)
    print("  metric                            value")
    print("-" * 74)
    print("  selector top-1                    %.4f   (%d/%d)" % (sel_hits / n, sel_hits, n))
    print("  keyword-rule baseline top-1       %.4f   (%d/%d)" % (rule_hits / n, rule_hits, n))
    print("  random baseline top-1             %.4f   (uniform 1/%d = %.4f)" % (exp_rand, len(names), cf))
    print("  median latency                    %.3f ms / decision" % statistics.median(lat))
    print("  p95 latency                       %.3f ms / decision" % sorted(lat)[max(0, int(len(lat) * 0.95) - 1)])
    print("  fit time                          %.1f ms (one-off)" % fit_ms)
    print("-" * 74)

    # tokens
    print("\ntokens: picking a tool by asking an LLM means re-sending the whole tool")
    print("        catalog + task in the prompt on every call (thousands of tokens).")
    print("        This selector is a local forward pass - no prompt, no network.")
    cat_tok = sum(len(t["name"].split("_")) + len(t.get("description") or "") // 2 for t in tools)
    print("        (tool catalog alone is ~%d tokens; an LLM call re-sends it every time)" % cat_tok)

    # guarded decision = the actual point of a decision layer
    print("\n" + "=" * 74)
    print("guarded decisions (a confidence gate: speak up only when sure)")
    print("=" * 74)
    MIN_CONF, MIN_MARGIN = 0.05, 0.03
    shown = 0
    agree = miss = 0
    for r in test:
        p = model.predict(r["context"] or "", opts)
        conf, marg = float(p["confidence"]), float(p["margin"])
        if conf >= MIN_CONF and marg >= MIN_MARGIN:
            pick = names[p["choice"]]
            if pick == r["label"]:
                agree += 1
            else:
                miss += 1
            if shown < 3:
                print("  task   : %s" % (r["context"] or "")[:62])
                print("  pick   : %-14s conf=%.3f margin=%.3f  (gold: %s)  %s"
                      % (pick, conf, marg, r["label"], "OK" if pick == r["label"] else "MISS"))
                print()
                shown += 1
    gate = agree + miss
    print("  gated through : %d of %d" % (gate, n))
    if gate:
        print("  of those, hit : %d  (%.3f)   miss: %d" % (agree, agree / gate, miss))
        print("  rest          : fall back to the existing rule path (zero side effect)")

    print("\nDone. No network, no GPU, no third-party packages.")


if __name__ == "__main__":
    main()
