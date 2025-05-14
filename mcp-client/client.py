import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from typing import Optional, List, Dict, Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

load_dotenv()  # 加载环境变量

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.http_client = httpx.AsyncClient()
        self.conversation_history: List[Dict[str, Any]] = []

    async def connect_to_server(self, server_script_path: str):
        """连接MCP服务器"""
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        
        if not (is_python or is_js):
            raise ValueError("服务器脚本必须是.py或.js文件")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )
        
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        await self.session.initialize()
        
        # 获取可用工具列表
        response = await self.session.list_tools()
        self.available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in response.tools]
        
        print("\n连接的服务器工具:", [tool['function']['name'] for tool in self.available_tools])

    async def call_deepseek_api(self, messages: List[Dict]) -> Dict:
        """调用DeepSeek API"""
        try:
            response = await self.http_client.post(
                "https://api.siliconflow.cn/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('ANTHROPIC_API_KEY')}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-ai/DeepSeek-V3",
                    "messages": messages,
                    "temperature": 0.7,
                    "tools": self.available_tools,
                    "tool_choice": "auto"
                },
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"API错误: {e.response.status_code} - {e.response.text}")
            return {"error": str(e)}
        except Exception as e:
            print(f"请求失败: {str(e)}")
            return {"error": str(e)}

    async def process_tool_calls(self, tool_calls: List[Dict]) -> List[str]:
        """处理工具调用并返回结果"""
        results = []
        for call in tool_calls:
            try:
                func_name = call['function']['name']
                arguments = json.loads(call['function']['arguments'])
                
                # 执行工具调用
                result = await self.session.call_tool(func_name, arguments)
                results.append(f"{func_name} 结果: {result.content}")
                
                # 记录到会话历史
                self.conversation_history.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [call]
                })
                self.conversation_history.append({
                    "role": "tool",
                    "content": result.content,
                    "tool_call_id": call['id']
                })
            except Exception as e:
                results.append(f"工具调用失败: {str(e)}")
        return results

    async def process_query(self, query: str) -> str:
        """处理用户查询"""
        # 添加用户消息到历史
        self.conversation_history.append({"role": "user", "content": query})
        
        # 获取API响应
        api_response = await self.call_deepseek_api(self.conversation_history)
        if "error" in api_response:
            return f"错误: {api_response['error']}"
        
        message = api_response['choices'][0]['message']
        response_content = []
        
        # 处理文本响应
        if message.get('content'):
            response_content.append(message['content'])
        
        # 处理工具调用
        if 'tool_calls' in message:
            tool_results = await self.process_tool_calls(message['tool_calls'])
            response_content.extend(tool_results)
        
        # 更新会话历史
        self.conversation_history.append(message)
        
        return "\n".join(response_content)

    async def chat_loop(self):
        """交互式聊天循环"""
        print("\nMCP客户端已启动！")
        print("输入查询或'quit'退出")
        
        while True:
            try:
                query = input("\n查询: ").strip()
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(query)
                print(f"\n响应: {response}")
                
            except Exception as e:
                print(f"\n错误: {str(e)}")
    
    async def cleanup(self):
        """清理资源"""
        await self.exit_stack.aclose()
        await self.http_client.aclose()

async def main():
    if len(sys.argv) < 2:
        print("用法: python client.py <服务器脚本路径>")
        sys.exit(1)
        
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())