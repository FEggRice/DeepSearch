# Deep Search Agent 配置文件模板
# ============================================================
# 使用说明:
#   1. 将此文件复制为 config.py
#   2. 将下面的 "your_xxx_key_here" 替换为你的真实 API Key
#   3. 或者通过 Streamlit Web 界面直接输入 (推荐新手使用):
#      streamlit run examples/streamlit_app.py
#
# 注意: config.py 已被 .gitignore 忽略，真实密钥不会被提交到 Git
# ============================================================

# DeepSeek API Key - 从 https://platform.deepseek.com/ 获取
DEEPSEEK_API_KEY = "your_deepseek_api_key_here"

# OpenAI API Key (可选) - 从 https://platform.openai.com/ 获取
OPENAI_API_KEY = "your_openai_api_key_here"

# Tavily搜索API Key - 从 https://tavily.com/ 获取 (每月1000次免费)
TAVILY_API_KEY = "your_tavily_api_key_here"

# 配置参数
DEFAULT_LLM_PROVIDER = "deepseek"       # deepseek 或 openai
DEEPSEEK_MODEL = "deepseek-chat"
OPENAI_MODEL = "gpt-4o-mini"

MAX_REFLECTIONS = 2                      # 反思轮次
SEARCH_RESULTS_PER_QUERY = 3             # 每次搜索返回结果数
SEARCH_CONTENT_MAX_LENGTH = 20000
OUTPUT_DIR = "reports"                   # 报告输出目录
SAVE_INTERMEDIATE_STATES = True
