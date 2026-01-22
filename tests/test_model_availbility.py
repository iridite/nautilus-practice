import requests
import json

API_KEY = "sk-b49925c33a2c87e458c245e76bf2f1514bd25b066446c4ef"
BASE_URL = "https://uapi.chat/v1/messages"

MODELS_TO_TEST = [
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "gemini-3-pro-preview"
]

def probe_v2(model_id):
    print(f"\n[探测模型]: {model_id}")
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    data = {
        "model": model_id,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": "你好，请简单自我介绍并说明你的知识截止日期。"}]
    }

    try:
        response = requests.post(BASE_URL, headers=headers, json=data, timeout=5)
        res = response.json()
        
        # 兼容多种返回格式
        content_list = res.get('content', [])
        found_content = False
        
        for item in content_list:
            # 捕获 2025-2026 模型特有的思维链
            if 'thinking' in item:
                print(f"🧠 思维内容: {item['thinking'][:500]}...")
                found_content = True
            # 捕获常规文本
            if 'text' in item and item['text']:
                print(f"💬 文本回复: {item['text']}")
                found_content = True
        
        if not found_content:
            print("⚠️ 警告：返回了结构但内容为空，可能触发了内容过滤或模型未真正激活。")
            
    except Exception as e:
        print(f"❌ 请求出错: {e}")

for m in MODELS_TO_TEST:
    probe_v2(m)