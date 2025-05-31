# tools\websearch.py
from typing import Any
import httpx
import os
import json
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
BAIDU_API_KEY = os.getenv("BAIDU_API_KEY")

# 初始化 FastMCP server
mcp = FastMCP("websearch")

# 百度Copilot引擎配置
COPILOT_API_URL = "https://appbuilder.baidu.com/rpc/2.0/cloud_hub/v1/ai_engine/copilot_engine/service/v1/baidu_search_rag/general"
HEADERS = {
    'Content-Type': 'application/json',
        'Authorization': f'Bearer {os.getenv('BAIDU_API_KEY')}'
    # 'Authorization': f'Bearer bce-v3/ALTAK-AhC6fmPq0j9Z4msHfEXPO/eebf22afbd4345d8dca35f04ef13a4e93e40adf9'
}

async def make_copilot_request(query: str) -> dict[str, Any] | None:
    """向百度Copilot引擎发送请求"""
    payload = {
        "model": "ERNIE-4.0-8K",
        "message": [
            {
                "role": "user",
                "content": query
            }
        ],
        "temperature": 1e-10,
        "top_p": 1e-10,
        "hide_corner_markers": False,
        "enable_timely_query_rewrite": False,
        "enable_historical_query_rewriting": False,
        "enable_instruction_enhance": False,
        "search_rearrange": True
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                COPILOT_API_URL,
                json=payload,
                headers=HEADERS
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"API错误: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            print(f"请求异常: {str(e)}")
            return None

def format_copilot_response(response: dict) -> str:
    """优化解析百度Copilot引擎返回结果"""
    try:
        # 深度检查结果结构
        answer_message = response.get("answer_message", {})
        content = answer_message.get("content", "")
        
        # 尝试提取主要内容
        if not content:
            # 检查其他可能的内容路径
            if "result" in response and "response" in response["result"]:
                responses = response["result"]["response"]
                if responses and "content" in responses[0]:
                    content = responses[0]["content"]
            
            # 最后尝试直接提取文本
            if not content:
                content = response.get("text", "") or json.dumps(response, ensure_ascii=False)
        
        # 精简内容 - 删除多余的引用标记和JSON结构
        content = content.replace('[ref_1]', '').replace('[ref_3]', '')
        return content.strip() or "未找到有效内容"
    
    except (KeyError, IndexError, TypeError) as e:
        return f"解析响应时出错: {str(e)}"

@mcp.tool()
async def web_search(query: str) -> str:
    """使用百度Copilot引擎获取网络资料
    
    Args:
        query: 搜索查询内容
    """
    # 调用Copilot API
    response = await make_copilot_request(query)
    
    if not response:
        return "无法获取搜索结果，请稍后重试"
    
    # 检查API错误
    if "error" in response:
        error_msg = response.get("error", "未知错误")
        return f"API错误: {error_msg}"
    
    # 格式化结果
    result = format_copilot_response(response)
    print("搜索结果:", result)  # 添加打印语句以检查结果
    return result

if __name__ == "__main__":
    # 初始化并运行 server
    mcp.run(transport='stdio')