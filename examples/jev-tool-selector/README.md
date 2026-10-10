# Jev-style Tool Selector

**A tiny, zero-dependency tool selector that turns "which tool should I call?" into a typed decision with a confidence — in under 1 millisecond, on CPU, with no LLM call.**

Most agent frameworks answer "which tool?" by asking a chat model:

> send the whole tool catalog + the task on **every call**, wait 3–6 seconds,
> parse the model's text back into a tool name.

This project does the same job as a **single forward pass** — no prompt, no
network, no GPU, ~1 ms.

```
$ python run.py

gold set        : 92 labeled decisions  (65 train / 27 test)
option set      : 25 tools  (the selector must pick among ALL of them)

  metric                            value
  ------------------------------------------------------------------
  selector top-1                    0.6667   (18/27)
  keyword-rule baseline top-1       0.0741   (2/27)
  random baseline top-1             0.0395   (uniform 1/25 = 0.0400)
  median latency                    0.932 ms / decision
  p95 latency                       0.991 ms / decision

  guarded decisions (a confidence gate: speak up only when sure)
  gated through : 6 of 27
  of those, hit : 6  (1.000)   miss: 0
  rest          : fall back to the existing rule path (zero side effect)
```

## Why "Jev-style"

[System One models / Jev](https://typesafe.ai) made a simple observation that
matters: **most agent "decisions" are small.** A chat model can answer them,
but it spends time generating text that software immediately parses back into
an `if` statement.

A *decision* is a different shape from a *generation*:

| | chat model | decision model |
|:--|:--|:--|
| input | text | **context + a set of typed options** |
| output | text (must be parsed) | **a probability per option + a confidence** |
| latency | seconds | **sub-millisecond, CPU** |
| cost | tokens per call | **zero** |

This repo implements that *shape* — the **option-attention** idea: every
option becomes a query, attention is distributed over the context, and a
softmax across options yields a probability per option. See
`hetu_selector.py` for the ~15 KB implementation (BM25 lexical attention +
a learnable correction, pure standard library).

> **Honest note.** This is Jev-*style*, not Jev. TypeSafe's Jev is
> closed-source; its exact numbers are not comparable to these. What is
> comparable is the *shape* of the decision — and that's what makes the
> confidence gate below possible.

## The part that actually matters: the gate

A selector that is wrong is worse than no selector. So the real API is
`guarded_suggest()` — **it only speaks up when it is confident enough**:

```python
from hetu_selector import Selector, fit_lexical

fit_lexical(options)
model = Selector({"bm25": 1.0}, 0.0)

# best-effort guess (always returns something)
model.predict(context, options)
# -> {"choice": 3, "confidence": 0.182, "margin": 0.139, "probs": [...]}

# gated guess (returns None when unsure -> caller keeps its old behaviour)
def guarded(model, context, options, min_conf=0.05, min_margin=0.03):
    p = model.predict(context, options)
    if p["confidence"] >= min_conf and p["margin"] >= min_margin:
        return options[p["choice"]]
    return None          # <- low confidence: do NOT inject, fall back
```

In the run above, the gate let **6 of 27** decisions through — and **all 6
were correct**. The other 21 fell back to the existing rule path, so a wrong
guess never reaches the agent. **"Speak only when sure" is the whole point.**

*(This is the same gate that ships inside our agent framework; the numbers
above come from running it here, not from the framework.)*

## Install / run

No dependencies. Python 3.8+.

```bash
python run.py          # prints the numbers above
```

Files:

| file | what |
|:--|:--|
| `run.py` | the one-command benchmark |
| `hetu_selector.py` | the selector (~15 KB, stdlib only) |
| `hetu_jev.py` | the reference integration (dataset building, baselines, behavior eval). Kept for reference; `run.py` is self-contained. |
| `gold.jsonl` | 92 hand-labeled decisions (`{"context": ..., "label": ...}`) |
| `tools.json` | the 25-tool catalog the selector must choose among |
| `model.json` | a pre-fit lexical model (IDF table), loaded in ~0.5 ms |

## Benchmarks / honest boundaries

- **The gold set is hand-written, not real traffic.** 92 rows, 25 tools,
  Chinese phrasing. It is a *ruler*, not a production distribution.
- **The option set is all 25 tools** — the hardest case. Real agents often
  pre-filter; results would be higher, but also less honest.
- **top-1 is 0.6667.** It is not 99%. A decision layer that is right
  two-thirds of the time and *knows when it doesn't know* is the useful
  thing; a confident wrong answer is not.
- **We did not compare against a real Jev deployment.** Price, latency, and
  accuracy of TypeSafe's Jev are not public in a comparable form.
- **Only one model family is tested here** (lexical attention). A learned
  option-attention head on embeddings would likely do better on paraphrase.

## Where this fits

Use a decision layer for the small, typed, high-frequency forks:

- tool choice (this repo)
- routing: cheap model vs. expensive model
- retrieval: is this memory relevant enough to inject?
- guardrails: should this action be blocked?
- classification / tagging

Do **not** use it to replace generation. It picks among options you give it;
if the option set is wrong, the decision is wrong. **The ceiling of a
selector is the quality of its option list.**

## License

MIT.
