#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 工具聚合导航站 - 内容采集脚本
================================
从 GitHub(按 AI topic 搜索高星、近期活跃项目)和 Hacker News(Show HN 板块)
采集值得收录的 AI 工具 / 开源项目 / 开发者作品,整理成结构化 JSON 输出到
data/tools.json。

特点
----
- 纯 Python 标准库实现,零第三方依赖,可在 GitHub Actions 直接运行。
- 增量采集:已存在的 data/tools.json 会被读取并合并(按 url 去重),
  新条目覆盖旧条目以更新 score / summary。
- API token 一律从环境变量读取,不硬编码。

环境变量
--------
  GITHUB_TOKEN     可选。GitHub Personal Access Token,带上可提升 API 限流
                   (匿名 10 次/分钟,带 token 30 次/分钟)。
                   在 GitHub Actions 里直接用自动注入的 secrets.GITHUB_TOKEN 即可。
  MAX_PER_SOURCE   可选。每个源最多保留多少条,默认 200。
  OUTPUT_FILE      可选。输出路径,默认 data/tools.json。
  HTTP_TIMEOUT     可选。请求超时秒数,默认 20。
  FETCH_DAYS       可选。GitHub 活跃窗口天数,默认 365。
  GITHUB_SLEEP     可选。GitHub 请求间隔秒数,默认按有无 token 自动
                   (匿名 6.5s / 带 token 2.1s),避免触发限流。

用法
----
  python scripts/collect_tools.py
"""

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ============================ 配置 ============================

OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "data/tools.json")
MAX_PER_SOURCE = int(os.environ.get("MAX_PER_SOURCE", "200"))
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "20"))
FETCH_DAYS = int(os.environ.get("FETCH_DAYS", "365"))
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# 分类表(9 类,固定,严禁自创)
CATEGORIES = {
    "对话与助手", "图像生成与处理", "视频与音频", "编程与开发",
    "写作与文本处理", "搜索与研究", "效率与办公", "模型与基础设施",
    "开发者作品",
}

# 关键词 -> 分类。加权命中:name +2 / description +1 / topics +3,
# 取最高分类;对话与助手命中负关键词则该类不计分;全 0 归 uncategorized;
# 同分按 PRIORITY 决定。
CATEGORY_RULES = {
    "对话与助手": ["chat", "chatbot", "assistant", "conversation", "gpt"],
    "图像生成与处理": ["image", "diffusion", "stable-diffusion", "midjourney",
                  "photo", "render", "vision", "inpaint", "upscaler"],
    "视频与音频": ["video", "audio", "music", "voice", "speech",
              "whisper", "tts", "suno", "dubbing", "asr"],
    "编程与开发": ["code", "coding", "developer", "programming", "ide",
              "copilot", "compiler", "debug", "reverse engineer",
              "refactor", "linter", "repl", "cli"],
    "写作与文本处理": ["writing", "text", "translate", "summar",
                  "document", "pdf", "editor", "markdown", "notion"],
    "搜索与研究": ["search", "research", "rag", "retrieval",
              "knowledge", "paper", "arxiv", "crawler", "scraper"],
    "效率与办公": ["productivity", "office", "meeting", "calendar",
              "email", "note", "automation", "workflow", "todo"],
    "模型与基础设施": ["model", "inference", "serving", "vector",
                  "database", "training", "finetune", "framework",
                  "llm", "embedding", "runtime", "engine",
                  "ollama", "vllm", "quantiz", "lora"],
    "开发者作品": ["show hn", "side project", "demo", "experiment",
              "game", "portfolio", "indie"],
}

# 对话与助手负关键词:命中则该类强制 0 分(防抢编程 / 模型类项目)
CHAT_NEGATIVE = ["code", "framework", "reverse", "decompil", "agent",
                 "sdk", "library", "cli", "api", "plugin"]

# 同分优先级:编程与开发 > 模型与基础设施 > 开发者作品 > 其余按规则顺序
PRIORITY = ["编程与开发", "模型与基础设施", "开发者作品"]

# 要搜索的 GitHub topic(每个独立查询后合并去重),按 9 类铺开覆盖
GITHUB_TOPICS = [
    # 对话与助手
    "chatbot", "conversational-ai", "llm-chat", "virtual-assistant",
    # 图像生成与处理
    "stable-diffusion", "image-generation", "text-to-image",
    "image-editing", "upscaling",
    # 视频与音频
    "text-to-video", "video-generation", "text-to-speech",
    "speech-recognition", "music-generation", "whisper",
    # 编程与开发
    "ai-coding", "code-generation", "copilot", "code-review",
    "developer-tools", "reverse-engineering",
    # 写作与文本处理
    "writing-assistant", "text-generation", "translation",
    "summarization", "document-processing", "markdown-editor", "pdf-tools",
    # 搜索与研究
    "rag", "retrieval-augmented-generation", "vector-search",
    "knowledge-base", "semantic-search", "research-tools",
    # 效率与办公
    "productivity", "automation", "workflow", "meeting-notes",
    "note-taking", "task-management", "email-assistant",
    # 模型与基础设施
    "llm", "large-language-model", "inference", "model-serving",
    "fine-tuning", "vector-database", "mlops",
    # 开发者作品
    "show-hn", "side-project", "experimental", "creative-coding",
    "webgl", "game",
]


# ============================ HTTP 工具 ============================

def http_get_json(url, headers=None):
    """GET 请求返回 JSON,失败返回 None。"""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        sys.stderr.write("[warn] GET %s 失败: %s\n" % (url[:90], e))
        return None


# ============================ 分类与打分 ============================

def classify(name, desc, topics, source=None):
    """加权分类:name +2 / desc +1 / topics +3,取最高分类;
    对话与助手命中负关键词则该类不计分;全 0 归 uncategorized;
    同分按 PRIORITY。source 保留兼容,不再用于兜底。"""
    name_l = (name or "").lower()
    desc_l = (desc or "").lower()
    topics_l = [t.lower() for t in (topics or [])]
    blob = name_l + " " + desc_l + " " + " ".join(topics_l)

    chat_blocked = any(neg in blob for neg in CHAT_NEGATIVE)

    scores = {}
    for cat, keywords in CATEGORY_RULES.items():
        if cat == "对话与助手" and chat_blocked:
            scores[cat] = 0
            continue
        s = 0
        for kw in keywords:
            if any(kw in t for t in topics_l):
                s += 3
            if kw in name_l:
                s += 2
            if kw in desc_l:
                s += 1
        scores[cat] = s

    max_score = max(scores.values()) if scores else 0
    if max_score <= 0:
        return "uncategorized"
    top_cats = [c for c, sc in scores.items() if sc == max_score]
    for p in PRIORITY:
        if p in top_cats:
            return p
    for c in CATEGORY_RULES:
        if c in top_cats:
            return c
    return "uncategorized"


def github_score(stars):
    """GitHub 按 star 数对数缩放到 0-100。"""
    if not stars or stars <= 0:
        return 0
    return min(100, round(17 * math.log10(stars + 10)))


def hn_score(points):
    """HN 按 points 对数缩放到 0-100(与 GitHub 量级可比)。"""
    if not points or points <= 0:
        return 0
    return min(100, round(22 * math.log10(points + 10)))


def make_id(name):
    """从 name 生成 id:小写、连字符、去特殊字符。"""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name or "").strip("-").lower()
    return s or "item"


def truncate(s, n=40):
    """截断到 n 字符,超出加省略号。"""
    s = re.sub(r"\s+", " ", (s or "").strip())
    if not s:
        return ""
    return s[:n] + ("…" if len(s) > n else "")


# ============================ 采集:GitHub ============================

def fetch_github():
    """按多个 AI topic 搜索 GitHub 高星、近期活跃仓库。"""
    pushed_after = (datetime.now(timezone.utc) -
                    timedelta(days=FETCH_DAYS)).strftime("%Y-%m-%d")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-nav-collector",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = "Bearer " + GITHUB_TOKEN

    # 动态限流间隔:匿名 10 次/分钟(6.5s),带 token 30 次/分钟(2.1s)
    sleep_sec = float(os.environ.get(
        "GITHUB_SLEEP", "2.1" if GITHUB_TOKEN else "6.5"))

    seen = {}
    for topic in GITHUB_TOPICS:
        params = urllib.parse.urlencode({
            "q": "topic:%s pushed:>%s" % (topic, pushed_after),
            "sort": "stars",
            "order": "desc",
            "per_page": 30,
        })
        url = "https://api.github.com/search/repositories?%s" % params
        data = http_get_json(url, headers)
        if not data or "items" not in data:
            time.sleep(sleep_sec)
            continue
        for repo in data["items"]:
            url_ = repo.get("html_url") or \
                "https://github.com/%s" % repo.get("full_name", "")
            key = url_.rstrip("/").lower()
            if key in seen:
                continue
            lang = repo.get("language")
            tags = ["开源"]
            if lang:
                tags.append(lang)
            seen[key] = {
                "id": make_id(repo.get("name")),
                "name": repo.get("name", ""),
                "url": url_,
                "category": classify(
                    repo.get("name"), repo.get("description"),
                    repo.get("topics"), "github"),
                "tags": tags,
                "summary": truncate(
                    repo.get("description") or repo.get("name")),
                "source": "github",
                "score": github_score(repo.get("stargazers_count")),
                "date_added": TODAY,
            }
        time.sleep(sleep_sec)  # 按限流间隔

    items = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
    return items[:MAX_PER_SOURCE]


# ============================ 采集:Hacker News ============================

def fetch_hackernews():
    """采集 HN Show HN 板块的开发者作品(Algolia API)。"""
    params = urllib.parse.urlencode({
        "query": "Show HN",
        "tags": "story",
        "hitsPerPage": 50,
        "numericFilters": "points>30",
    })
    url = "https://hn.algolia.com/api/v1/search?%s" % params
    data = http_get_json(url)
    if not data or "hits" not in data:
        return []

    seen = {}
    for hit in data["hits"]:
        title = hit.get("title") or ""
        if not title.lower().startswith("show hn"):
            continue
        clean = re.sub(r"^show hn\s*[:：\-\s]*", "", title,
                       flags=re.IGNORECASE).strip()
        name = clean or title
        story_url = hit.get("url") or \
            "https://news.ycombinator.com/item?id=%s" % hit.get("objectID", "")
        key = story_url.rstrip("/").lower()
        if key in seen:
            continue
        seen[key] = {
            "id": make_id(name),
            "name": name,
            "url": story_url,
            "category": classify(name, title, [], "hackernews"),
            "tags": ["网站", "作品集", "实验"],
            "summary": truncate(clean or title),
            "source": "hackernews",
            "score": hn_score(hit.get("points")),
            "date_added": TODAY,
        }

    items = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
    return items[:MAX_PER_SOURCE]


# ============================ 合并与写回 ============================

def load_existing(path):
    """读取已存在的 tools.json,返回 list。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def merge_and_dedup(existing, new_items):
    """合并:按 url 去重,新条目覆盖旧条目(更新);再按 name 去重保留高分。"""
    by_url = {}
    for item in existing:
        key = (item.get("url") or "").rstrip("/").lower()
        if key:
            by_url[key] = item
    for item in new_items:
        key = (item.get("url") or "").rstrip("/").lower()
        if key:
            by_url[key] = item          # 新数据覆盖旧数据(更新)

    by_name = {}
    for item in by_url.values():
        nm = (item.get("name") or "").strip().lower()
        if not nm:
            continue
        if nm in by_name:
            if item.get("score", 0) > by_name[nm].get("score", 0):
                by_name[nm] = item
        else:
            by_name[nm] = item

    return sorted(by_name.values(),
                  key=lambda x: x.get("score", 0), reverse=True)


# ============================ 主流程 ============================

def main():
    sys.stderr.write("[info] 开始采集,日期 %s\n" % TODAY)
    gh = fetch_github()
    sys.stderr.write("[info] GitHub 采集到 %d 条\n" % len(gh))
    hn = fetch_hackernews()
    sys.stderr.write("[info] Hacker News 采集到 %d 条\n" % len(hn))

    new_items = gh + hn
    # 必填四项(name/url/category/summary)缺一即丢弃
    valid_cats = CATEGORIES | {"uncategorized"}
    new_items = [it for it in new_items
                 if it.get("name") and it.get("url")
                 and it.get("category") in valid_cats and it.get("summary")]

    existing = load_existing(OUTPUT_FILE)
    merged = merge_and_dedup(existing, new_items)

    out_dir = os.path.dirname(OUTPUT_FILE)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    sys.stderr.write("[info] 已写入 %s,共 %d 条\n"
                     % (OUTPUT_FILE, len(merged)))
    # 标准输出留空(遵循"只输出 JSON 数组"约定由文件承载)


if __name__ == "__main__":
    main()
