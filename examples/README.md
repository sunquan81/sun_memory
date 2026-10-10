# Examples

## `jev-tool-selector/` — a "which tool?" decision in under 1 ms

Turns tool selection from a chat-model call into a typed decision with a
confidence. Zero dependencies, pure stdlib, CPU only.

```
cd examples/jev-tool-selector
python run.py
```

Real output (92 hand-labeled decisions, 25 candidate tools):

| metric | value |
|:--|:--|
| selector top-1 | **0.6667** (18/27) |
| keyword-rule baseline | 0.0741 (2/27) |
| random baseline | 0.0395 (1/25) |
| median latency | **0.932 ms** / decision |
| gated decisions (conf >= .05, margin >= .03) | 6 of 27 — **6/6 correct, 0 misses** |

The point is the **gate**: it speaks up only when confident; otherwise it
returns `None` and the caller keeps its old behaviour. A decision layer that
knows when it doesn't know is the useful part.

> Jev-*style*, not Jev. TypeSafe's Jev is closed-source; these numbers are
> not comparable to theirs.
