#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采集结果统计报告。
读 data/tools.json(当前)与 data/tools_prev.json(上一版),
输出:总条目数、各分类条目数、仍为 0 的分类、与上一版的增量条目数。
纯标准库,零依赖。"""
import json
from collections import Counter

CATS = ["对话与助手", "图像生成与处理", "视频与音频", "编程与开发",
        "写作与文本处理", "搜索与研究", "效率与办公", "模型与基础设施",
        "开发者作品"]


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except Exception:
        return []


def key(x):
    return (x.get("url") or "").rstrip("/").lower()


cur = load("data/tools.json")
prev = load("data/tools_prev.json")
cur_keys = {key(x) for x in cur}
prev_keys = {key(x) for x in prev}

print("=" * 56)
print("采集统计")
print("=" * 56)
print("总条目数            : %d" % len(cur))
print("上一版条目数        : %d" % len(prev))
print("增量条目数(新增 url): %d" % len(cur_keys - prev_keys))
print("消失条目数          : %d" % len(prev_keys - cur_keys))
print()
print("各分类条目数:")
cnt = Counter(x.get("category") for x in cur)
for c in CATS:
    mark = "  <-- 0" if cnt.get(c, 0) == 0 else ""
    print("  %-16s %d%s" % (c, cnt.get(c, 0), mark))
print("  %-16s %d" % ("[uncategorized]", cnt.get("uncategorized", 0)))
print()
zero = [c for c in CATS if cnt.get(c, 0) == 0]
print("仍为 0 的分类 :", ("、".join(zero) if zero else "无"))
print("uncategorized :", cnt.get("uncategorized", 0))

# 按来源统计
print()
src = Counter(x.get("source") for x in cur)
for s, n in src.most_common():
    print("  来源 %-12s %d" % (s, n))
