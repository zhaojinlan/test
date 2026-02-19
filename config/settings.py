"""
全局配置 —— LLM / 搜索 / 系统参数
"""

# ==================== LLM 选择 ====================
# 设为 True 使用自建 Ollama（qwen2.5:14b），False 使用火山方舟 doubao
USE_OLLAMA = True

# ---- 火山方舟 doubao 配置 ----
DOUBAO_API_KEY = "e31694db-1a7e-4004-b2bc-ed51f6362714"
DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_MODEL = "doubao-seed-1-8-251228"

# ---- 自建 Ollama 配置 ----
OLLAMA_BASE_URL = "https://zjlchat.vip.cpolar.cn"
OLLAMA_MODEL = "qwen2.5:14b"

# ---- 根据开关自动选择 ----
if USE_OLLAMA:
    LLM_API_KEY = "ollama"                        # Ollama 不需要真实 key
    LLM_BASE_URL = OLLAMA_BASE_URL + "/v1"         # Ollama OpenAI 兼容端点
    LLM_MODEL = OLLAMA_MODEL
else:
    LLM_API_KEY = DOUBAO_API_KEY
    LLM_BASE_URL = DOUBAO_BASE_URL
    LLM_MODEL = DOUBAO_MODEL

LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = 32000

# ==================== 搜索配置（博查 —— 中文搜索）====================
SEARCH_API_KEY = "sk-3c89d90cb20c4072be599632958e7157"
SEARCH_BASE_URL = "https://api.bocha.cn/v1/web-search"
SEARCH_DEFAULT_COUNT = 10
SEARCH_FRESHNESS = "noLimit"

# ==================== 搜索配置（Serper —— 英文 Google 搜索）====================
SERPER_API_KEY = "704534631cedfd6842d9bb8da64bb8fd0eee1a59"
SERPER_BASE_URL = "https://google.serper.dev/search"
SERPER_DEFAULT_COUNT = 10

# ==================== 系统配置 ====================
MAX_SUPERVISOR_ITERATIONS = 10
MAX_AGENT_STEPS = 8
MAX_GROUP_CHAT_ROUNDS = 20


def get_autogen_llm_config() -> dict:
    """返回 AutoGen ConversableAgent 所需的 llm_config"""
    return {
        "config_list": [
            {
                "model": LLM_MODEL,
                "api_key": LLM_API_KEY,
                "base_url": LLM_BASE_URL,
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS,
            }
        ],
        "timeout": 120,
        "cache_seed": None,
    }
