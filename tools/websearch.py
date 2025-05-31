import re
import httpx
from typing import List, Dict
from urllib.parse import quote
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# 初始化 FastMCP server
mcp = FastMCP("websearch")

# 自定义User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"

class SearchParams(BaseModel):
    """搜索参数"""
    query: str = Field(..., description="要搜索的查询关键词")
    count: int = Field(default=5, description="返回的结果数量(1-10)", ge=1, le=10)

@mcp.tool()
async def search(query: str, count: int = 5) -> str:
    """使用Bing搜索网络内容（无需API密钥）"""
    # 构造Bing搜索URL
    base_url = "https://www.bing.com"
    search_url = f"{base_url}/search?q={quote(query)}"
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": base_url
    }
    
    try:
        # 发送HTTP请求
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()
            html = response.text
        
        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(html, "html.parser")
        
        # 查找搜索结果容器
        result_elements = soup.select("#b_results > .b_algo")
        if not result_elements:
            # 备选选择器
            result_elements = soup.select(".b_algo")
        
        # 提取搜索结果
        results = []
        for i, result in enumerate(result_elements[:count], 1):
            title_elem = result.select_one("h2")
            link_elem = result.select_one("a")
            desc_elem = result.select_one(".b_caption p") or result.select_one(".b_lineclamp2")
            
            title = title_elem.get_text(strip=True) if title_elem else "无标题"
            url = link_elem.get("href") if link_elem else "无网址"
            description = desc_elem.get_text(strip=True) if desc_elem else "无描述"
            
            # 清理描述中的特殊字符
            description = re.sub(r"[\u202f\u200b\xad]", "", description)
            
            results.append(f"""
结果 #{i}:
标题: {title}
网址: {url}
摘要: {description}
""")
        
        return "\n".join(results) if results else "未找到相关结果"
    
    except httpx.HTTPError as e:
        return f"搜索请求失败: HTTP错误 {e.response.status_code if hasattr(e, 'response') else ''}"
    except Exception as e:
        return f"搜索时发生错误: {str(e)}"

# 错误处理中间件
@mcp.exception_handler()
async def handle_exceptions(exc: Exception):
    return f"服务器内部错误: {str(exc)}"

if __name__ == "__main__":
    # 初始化并运行服务器
    mcp.run(transport='stdio')