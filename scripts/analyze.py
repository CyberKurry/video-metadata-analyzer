#!/usr/bin/env python3
"""
analyze.py — 从 observations (visual + audio) 合成 metadata.json

用法：
  python3 analyze.py --observations-visual obs_v.json --observations-audio obs_a.json --output metadata.json --method api|agent|manual

method:
  api   — 使用外部 API（vision/audio LLM）合成（需要 --api-key/--api-base/--model）
  agent — 在当前会话/agent 内用模型合成（本地或远程模型）
  manual— 只把 observations 转成可编辑的 Markdown 供人工审阅

注意：API 调用会把 observations 一并传给模型。
"""

import argparse
import json
import os
import re
import sys
import urllib.request

# 公共工具
from common import http_request_with_retry, parse_json_from_llm, extract_llm_content


def observations_to_markdown(obs_v, obs_a):
    parts = ["# Observations (Visual)", ""]
    for f in obs_v:
        parts.append(f"## {f.get('frame')}")
        parts.append(f"- desc: {f.get('desc')}")
        parts.append(f"- texts: {f.get('texts')}")
        parts.append(f"- objects: {', '.join(f.get('objects', []))}")
        parts.append(f"- actions: {', '.join(f.get('actions', []))}")
        parts.append(f"- style: {f.get('style')}")
        parts.append(f"- cover_candidate: {f.get('cover_candidate')}")
        parts.append("")
    parts.append("# Observations (Audio)")
    parts.append("")
    parts.append(f"transcript:\n{obs_a.get('transcript','')}")
    parts.append("")
    parts.append(f"speakers: {', '.join(obs_a.get('speakers',[]))}")
    parts.append("")
    parts.append(f"key_points:\n- " + "\n- ".join(obs_a.get('key_points',[])))
    parts.append("")
    parts.append(f"tone: {obs_a.get('tone','')}")
    return "\n".join(parts)


def synthesize_agent(obs_v, obs_a):
    """Agent 模式：不调 API，用启发式规则生成基础 metadata。
    适合快速预览或作为 API 模式的 fallback。"""
    # --- 标题 ---
    # 优先从 key_points 取最有信息量的那句，截取到 80 字
    key_points = obs_a.get('key_points', [])
    transcript = obs_a.get('transcript', '')

    title = ''
    if key_points:
        # 取第一个 key_point 作为基础，但尽量让它像人写的
        title = key_points[0]
        if len(title) > 80:
            title = title[:77] + '...'
    elif transcript:
        # 从 transcript 第一句取前 60 字
        first_sentence = transcript.split('。')[0].split('，')[0]
        title = first_sentence[:60]
    else:
        title = obs_v[0].get('desc', '未命名视频')[:60]

    # --- 简介 ---
    # 把 key_points 和 transcript 前几句组合
    intro_parts = []
    if key_points:
        intro_parts.append('\n'.join(f'- {p}' for p in key_points[:5]))
    if transcript:
        # 取 transcript 前几句（最多 500 字）
        sentences = re.split(r'[。！？\n]', transcript)
        intro_text = '。'.join(s for s in sentences if s.strip())[:500]
        intro_parts.append(intro_text)
    intro = '\n\n'.join(intro_parts) if intro_parts else obs_v[0].get('desc', '')

    # --- 标签 ---
    # 从 style + objects + key_points 中提取
    tags = set()
    for f in obs_v:
        for t in (f.get('style') or '').split('/'):
            t = t.strip()
            if t and len(t) <= 20:
                tags.add(t)
        for obj in (f.get('objects') or []):
            if isinstance(obj, str) and len(obj) <= 10:
                tags.add(obj)
    for kp in key_points[:3]:
        # 从 key_points 提取关键词
        for word in re.findall(r'[A-Za-z]+|[\u4e00-\u9fff]{2,6}', kp):
            if len(word) >= 2:
                tags.add(word)
    tags = list(tags)[:10]
    if not tags:
        tags = ['视频']

    # --- 封面建议 ---
    cover_primary = None
    cover_reason = ''
    cover_secondary = None
    for f in obs_v:
        if f.get('cover_candidate'):
            frame_name = f.get('frame', '')
            if not cover_primary:
                cover_primary = frame_name
                desc = f.get('desc', '')
                texts = f.get('texts', '')
                reasons = []
                if texts:
                    reasons.append(f'含文字"{texts[:30]}"')
                if desc:
                    reasons.append(f'画面内容：{desc[:50]}')
                cover_reason = '；'.join(reasons) if reasons else '视觉信息密度高'
            elif not cover_secondary:
                cover_secondary = frame_name

    # --- 分区 ---
    all_text = ' '.join(f.get('texts', '') + ' ' + f.get('desc', '') for f in obs_v)
    all_text += ' ' + transcript
    category = '科技'
    sub_category = '计算机技术'
    if any(kw in all_text for kw in ['电路', '电气', '电压', '电流', '电机', '机械']):
        category = '科技'
        sub_category = '科普'
    elif any(kw in all_text for kw in ['游戏', '通关', '攻略', '速通', '电竞', '开箱']):
        category = '游戏'
        sub_category = '单机游戏'
    elif any(kw in all_text for kw in ['音乐', '翻唱', '编曲', '弹唱', '乐器', '演唱']):
        category = '音乐'
        sub_category = '原创音乐'
    elif any(kw in all_text for kw in ['知识', '科普', '教程', '教学', '原理', '解析', '讲解']):
        category = '知识'
        sub_category = '科普'
    elif any(kw in all_text for kw in ['美食', '烹饪', '食谱', '做饭', '料理', '烘焙']):
        category = '美食'
        sub_category = '美食制作'
    elif any(kw in all_text for kw in ['生活', '日常', 'Vlog', 'vlog', '记录', '体验']):
        category = '生活'
        sub_category = '日常'
    elif any(kw in all_text for kw in ['动画', '动漫', 'MAD']):
        category = '动画'
        sub_category = '综合'
    elif any(kw in all_text for kw in ['纪录片', '纪录', '纪实']):
        category = '纪录片'
        sub_category = '人文'
    elif any(kw in all_text for kw in ['舞蹈', '编舞', '宅舞']):
        category = '舞蹈'
        sub_category = '宅舞'
    elif any(kw in all_text for kw in ['鬼畜', '调教', '音 MAD']):
        category = '鬼畜'
        sub_category = '鬼畜调教'
    elif any(kw in all_text for kw in ['时尚', '穿搭', '美妆', '护肤']):
        category = '时尚'
        sub_category = '穿搭'
    elif any(kw in all_text for kw in ['娱乐', '综艺', '明星', '八卦']):
        category = '娱乐'
        sub_category = '综艺'
    elif any(kw in all_text for kw in ['影视', '电影', '电视剧', '解说']):
        category = '影视'
        sub_category = '影视杂谈'
    elif any(kw in all_text for kw in ['汽车', '改装', '赛车', '驾驶']):
        category = '汽车'
        sub_category = '汽车生活'
    elif any(kw in all_text for kw in ['运动', '健身', '篮球', '足球', '体育']):
        category = '运动'
        sub_category = '综合'
    elif any(kw in all_text for kw in ['宠物', '猫', '狗', '动物']):
        category = '动物圈'
        sub_category = '喵星人'
    elif any(kw in all_text for kw in ['国创', '国产动画', '国产']):
        category = '国创'
        sub_category = '国产动画'

    # --- 创作声明（对齐 B 站网页端单选列表） ---
    declaration = '内容无需标注'
    if any(kw in all_text for kw in ['AI生成', '人工智能运营', 'Sora', 'Runway', 'Midjourney', 'Stable Diffusion', 'Seedream']):
        declaration = '含AI生成内容'

    metadata = {
        'title': title,
        'intro': intro,
        'tags': tags,
        'category': category,
        'sub_category': sub_category,
        'cover_suggestion': {
            'primary': cover_primary or obs_v[0].get('frame', ''),
            'reason': cover_reason or '首帧',
            'secondary': cover_secondary or ''
        },
        'declaration': declaration,
        'copyright_claim': False  # 非必选，用户明确说明是自制时才勾选
    }
    return metadata


SYNTHESIZE_SYSTEM_PROMPT = """你是一位资深的 B 站内容运营，擅长根据视频内容撰写投稿元数据。你的目标受众是 B 站的普通观众，不是机器人。

核心原则：
- **标题是给人看的**：像真实 UP 主写的，不是 AI 概括。要有信息量、有辨识度，让人一眼知道视频讲什么并且想点进来。可以是陈述式、设问式、或带一点个性。严禁空泛套话（如"深入浅出""全面解析""带你了解"）。
- **简介是给人读的**：让人看完能判断"这个视频跟我有关吗"。用自然语言，可以分段，包含关键信息点。不是摘要，是预告。
- **标签从内容中自然长出来**：不要堆砌泛标签，要具体到内容领域。
- **分区要准**：根据视频实际内容选最匹配的 B 站分区。
- **封面建议要具体**：基于实际画面内容，说清楚为什么这帧好、适合做什么风格。

输出语言：中文为主，技术术语可保留英文。"""

SYNTHESIZE_USER_PROMPT = """## 视觉观测（从视频中抽取的关键帧分析）
{obs_visual}

## 音频观测（语音转写 + 结构化信息）
{obs_audio}

## 任务
根据以上视觉和音频观测，生成 B 站投稿元数据。

严格输出一个 JSON 对象，包含以下字段：

| 字段 | 类型 | 要求 |
|------|------|------|
| title | string | 80字以内。像 UP 主写的标题，有信息量有辨识度，不做标题党。参考示例。 |
| intro | string | 2000字以内。给观众看的视频介绍，用自然语言写，让人看完知道视频讲什么。可以分段，包含搜索关键词。 |
| tags | string[] | 10个以内，每个20字以内。从视频内容中自然提取的具体标签，不要泛标签。 |
| category | string | B 站一级分区（如：科技、知识、生活、游戏、动画、音乐、舞蹈、鬼畜、时尚、娱乐、影视、纪录片、汽车、运动、动物圈、国创、美食） |
| sub_category | string | B 站二级分区（如：计算机技术、科普、手工、日常等） |
| cover_suggestion | object | 封面建议：{{ "primary": "最推荐的帧编号+理由", "reason": "为什么这帧适合", "secondary": "备选帧编号+理由" }} |
| declaration | string | 创作声明（B 站网页端单选），必须为以下之一：“内容无需标注” | “含AI生成内容” | “含虚构演绎内容” | “内容含营销信息” | “个人观点，仅供参考” | “内容为转载” |
| copyright_claim | boolean | 非必选。是否勾选"内容为自制：未经作者允许，禁止转载"。默认 false |

## 标题参考示例（好的 vs 差的）
✅ 好的："用 AI Agent 自动审查代码缺陷，我把自家项目翻了个底朝天" / "ESP32 心率监测器：20 块钱的方案也能跑" / "别再手动投稿了，写个脚本自动发 B 站"
❌ 差的："AI Agent 技术分享" / "ESP32 项目介绍" / "自动投稿工具详解"

## 简介参考示例
"之前参加了一个代码审查活动，想到与其让人看，不如让 AI 也来审一遍。我用自己的 Obsidian 同步工具当靶子，让 AI Agent 逐行读了 2 万行 Rust + 8200 行 TypeScript，找到了几个挺有意思的问题。视频里走了一遍完整流程，包括怎么配置、怎么跑、以及 AI 看到的那些盲点。"

严格输出 JSON，不要包含 markdown 代码块标记或其他文字。"""


def synthesize_api(obs_v, obs_a, api_key, api_base, model):
    user_content = SYNTHESIZE_USER_PROMPT.format(
        obs_visual=json.dumps(obs_v, ensure_ascii=False, indent=2),
        obs_audio=json.dumps(obs_a, ensure_ascii=False, indent=2)
    )
    payload = {
        'model': model,
        'messages': [
            {'role':'system','content': SYNTHESIZE_SYSTEM_PROMPT},
            {'role':'user','content': user_content}
        ],
        'max_tokens': 4000
    }
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode('utf-8'),
        headers={"Content-Type":"application/json","Authorization":f"Bearer {api_key}"}
    )
    resp_data = http_request_with_retry(req, timeout=120, label=f"Synthesize LLM ({model})")
    content = extract_llm_content(resp_data, label=f"Synthesize LLM ({model})")

    # 多轮 JSON 解析重试
    for attempt in range(3):
        metadata = parse_json_from_llm(content, expect_array=False)
        if isinstance(metadata, dict) and 'title' in metadata and 'intro' in metadata and 'tags' in metadata:
            print(f"Synthesize JSON parsed OK on attempt {attempt+1}")
            return metadata
        if metadata is None:
            try:
                metadata = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                pass
        if not isinstance(metadata, dict) or 'title' not in metadata:
            print(f"WARNING: Synthesize parse attempt {attempt+1}/3 failed")
            if attempt < 2:
                retry_msg = f"你的上一次输出不是合法 JSON，解析失败。\n上一次输出（前500字）: {content[:500]}\n\n请重新输出，严格只输出一个 JSON 对象，不要包含 markdown 标记、解释或额外文字。"
                retry_payload = {
                    'model': model,
                    'messages': [
                        {'role':'system','content': SYNTHESIZE_SYSTEM_PROMPT},
                        {'role':'user','content': user_content},
                        {'role':'assistant','content': content},
                        {'role':'user','content': retry_msg}
                    ],
                    'max_tokens': 4000
                }
                retry_req = urllib.request.Request(
                    f"{api_base.rstrip('/')}/chat/completions",
                    data=json.dumps(retry_payload).encode('utf-8'),
                    headers={"Content-Type":"application/json","Authorization":f"Bearer {api_key}"}
                )
                try:
                    retry_resp = http_request_with_retry(retry_req, timeout=120, label=f"Synthesize retry {attempt+2}")
                    content = extract_llm_content(retry_resp, label=f"Synthesize retry {attempt+2}")
                except Exception as retry_err:
                    print(f"  Retry request failed: {retry_err}")
                    continue
            else:
                print(f"WARNING: All 3 synthesize parse attempts failed.")
                return synthesize_agent(obs_v, obs_a)
    # Safety net: should not reach here, but guarantee a return
    return synthesize_agent(obs_v, obs_a)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--observations-visual', required=True)
    parser.add_argument('--observations-audio', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--method', choices=['api','agent','manual'], default='manual')
    parser.add_argument('--api-key')
    parser.add_argument('--api-base')
    parser.add_argument('--model', default=None)
    args = parser.parse_args()

    with open(args.observations_visual, encoding='utf-8') as f:
        obs_v = json.load(f)
    with open(args.observations_audio, encoding='utf-8') as f:
        obs_a = json.load(f)

    if args.method == 'manual':
        md = observations_to_markdown(obs_v, obs_a)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(md)
        print('Wrote manual markdown to', args.output)
        return

    if args.method == 'agent':
        # 输出带引导 prompt 的 markdown，让 Agent 自行合成 metadata
        agent_md = SYNTHESIZE_SYSTEM_PROMPT + '\n\n'
        agent_md += SYNTHESIZE_USER_PROMPT.format(
            obs_visual=json.dumps(obs_v, ensure_ascii=False, indent=2),
            obs_audio=json.dumps(obs_a, ensure_ascii=False, indent=2)
        )
        agent_md += '\n\n--- END OF PROMPT ---\n\n请根据以上内容生成 metadata.json 并写入文件。\n'
        agent_md += f'输出文件路径: {args.output}\n'
        agent_md += '请严格输出 JSON 格式。\n'
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(agent_md)
        print(f'Wrote agent prompt to {args.output}. Agent should read it and generate metadata.')
        return

    if args.method == 'api':
        if not args.api_key or not args.api_base:
            print('api method requires --api-key and --api-base', file=sys.stderr); sys.exit(1)
        md = synthesize_api(obs_v, obs_a, args.api_key, args.api_base, args.model)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(md, f, ensure_ascii=False, indent=2)
        print('Wrote metadata (api) to', args.output)
        return

if __name__ == '__main__':
    main()
