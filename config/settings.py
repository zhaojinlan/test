# -*- coding: utf-8 -*-
"""全局配置"""
import os

# ==================== 关闭 LangSmith 追踪 ====================
os.environ["LANGSMITH_OTEL_ENABLED"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

# ==================== 火山方舟 LLM 配置 ====================
LLM_API_KEY = "e31694db-1a7e-4004-b2bc-ed51f6362714"
LLM_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
LLM_MODEL_NAME = "doubao-seed-1-8-251228"

# ==================== 博查搜索配置（中文数据为主） ====================
BOCHA_API_KEY = "sk-3c89d90cb20c4072be599632958e7157"
BOCHA_BASE_URL = "https://api.bocha.cn/v1/web-search"
BOCHA_DEFAULT_COUNT = 25

# ==================== Serper 搜索配置（国际数据为主） ====================
SERPER_API_KEY = "704534631cedfd6842d9bb8da64bb8fd0eee1a59"
SERPER_BASE_URL = "https://google.serper.dev/search"
SERPER_DEFAULT_NUM = 25

# ==================== 百度百科 API 配置（精确实体查询） ====================
BAIKE_API_KEY = "bce-v3/ALTAK-qyKOeBWeopfC6j5236hgq/93348634914b3067fb365bf73d20a39901aae0a0"
BAIKE_LIST_URL = "https://appbuilder.baidu.com/v2/baike/lemma/get_list_by_title"
BAIKE_CONTENT_URL = "https://appbuilder.baidu.com/v2/baike/lemma/get_content"

# ==================== 系统参数 ====================
MAX_SEARCH_RETRIES = 2          # 单次搜索最大重试
MAX_LOOPS = 4                   # 主循环最大次数（decompose→parallel_research→verify 算一轮）
RECURSION_LIMIT = 100           # LangGraph 递归上限
MAX_BAIKE_VERIFY = 1            # 每个研究分支最多触发的百科验证次数
