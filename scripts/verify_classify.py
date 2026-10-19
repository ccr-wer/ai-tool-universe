#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分类逻辑改前 / 改后对比验证。
读 data/tools_before.json(改前,旧分类)与 data/tools.json(改后,新分类),
按 url 配对,输出:改后各分类条目数、uncategorized 数、分类变化条目列表。
纯标准库,零依赖。"""
import json
from collections import Counter


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except Exception:
        return []


def key(x):
    return (x.get("url") or "").rstrip("/").lower()


before = {key(x): x for x in load("data/tools_before.json")}
after = load("data/tools.json")
after_keys = {key(x) for x in after}

print("=" * 60)
print("改后各分类条目数")
print("=" * 60)
cnt = Counter(x.get("category", "?") for x in after)
for cat, n in sorted(cnt.items(), key=lambda kv: -kv[1]):
    print("  %-16s %d" % (cat, n))
print("  %-16s %d" % ("[uncategorized]", cnt.get("uncategorized", 0)))
print("  总计: %d" % len(after))

print("\n" + "=" * 60)
print("改前 -> 改后 分类发生变化的条目")
print("=" * 60)
changed = []
for x in after:
    k = key(x)
    if k in before:
        old = before[k].get("category", "?")
        new = x.get("category", "?")
        if old != new:
            changed.append((x.get("name", ""), x.get("source", ""), old, new))
print("变化条目数: %d" % len(changed))
for name, src, old, new in changed:
    print("  %s [%s]: %s -> %s" % (name, src, old, new))

print("\n" + "=" * 60)
print("条目集差异(非分类问题,仅 API 返回不同)")
print("=" * 60)
new_only = [x.get("name", "") for x in after if key(x) not in before]
gone = [v.get("name", "") for v in before.values()
        if v and key(v) not in after_keys]
print("仅改后新增: %d 条" % len(new_only))
print("仅改前消失: %d 条" % len(gone))
