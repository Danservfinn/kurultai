import sys
sys.path.insert(0, '.')
from post_to_x import post_thread

# Create test thread about Parse OpenRouter launch
thread = [
    "🚀 Just launched OpenRouter integration on Parse Platform!\n\nParse now uses OpenRouter API for all AI analyses, giving you access to multiple models including Qwen3.5-Plus, Claude, GPT-4, and Gemini.\n\nhttps://www.parsethe.media",
    "🧠 What this means:\n\n• Switch between AI models instantly\n• Better analysis quality\n• More flexibility\n• No code changes needed\n\nThe future of media analysis is multi-model! #AI #MediaAnalysis #Parse",
    "🔧 Technical details:\n\n• Default: Qwen3.5-Plus-02-15\n• Also supports Claude 3.5, GPT-4, Gemini\n• Environment-based model switching\n• Deployed on Railway\n\nTry it now: https://www.parsethe.media/api/v1/article/analyze",
    "💡 Want to analyze news articles with AI? Parse Platform provides:\n\n• Bias detection\n• Rhetorical analysis\n• Credibility scoring\n• Multi-model AI\n\nStart analyzing: https://www.parsethe.media #MediaLiteracy #AI"
]

success = post_thread(thread)
print(f"Thread posted: {success}")
