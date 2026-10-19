#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补采:重试因 GitHub 限流(403)失败的 topic。
复用主脚本采集逻辑,不改主脚本的 GITHUB_TOPICS 配置。
用法:GITHUB_SLEEP=10 python scripts/retry_topics.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect_tools as ct

RETRY_TOPICS = ["writing-assistant", "text-generation", "fine-tuning",
                "vector-database", "creative-coding", "webgl"]

ct.GITHUB_TOPICS = RETRY_TOPICS          # 覆盖本次要跑的 topic
raw = ct.fetch_github()
raw = [it for it in raw if it.get("name") and it.get("url")
       and it.get("category") and it.get("summary")]

existing = ct.load_existing(ct.OUTPUT_FILE)
merged = ct.merge_and_dedup(existing, raw)
with open(ct.OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)
sys.stderr.write("[retry] 补采 %d 条,总计 %d 条\n" % (len(raw), len(merged)))
