# mcp-client\client.py
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
                    "Authorization": f"Bearer {os.getenv('SILICONFLOW_API_KEY')}",
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

    async def process_query(self, query: str) -> str:
        """处理用户查询"""
        self.conversation_history.append({"role": "user", "content": query})
        
        api_response = await self.call_deepseek_api(self.conversation_history)
        if "error" in api_response:
            return f"错误: {api_response['error']}"
        
        # 校验API响应结构
        if not api_response.get('choices') or not isinstance(api_response['choices'], list):
            return "API返回结构无效"
        
        message = api_response['choices'][0].get('message', {})
        if not message:
            return "API返回消息无效"
        
        # 立即将API响应消息加入历史记录
        self.conversation_history.append(message)
        
        response_content = []
        
        if message.get('content'):
            response_content.append(message['content'])
        
        if 'tool_calls' in message:
            try:
                tool_results = await self.process_tool_calls(message['tool_calls'])
                response_content.extend(tool_results)
            except json.JSONDecodeError as e:
                response_content.append(f"工具参数解析失败: {str(e)}")
        
        return "\n".join(response_content)

    async def process_tool_calls(self, tool_calls: List[Dict]) -> List[str]:
        """处理工具调用并返回结果"""
        results = []
        for call in tool_calls:
            try:
                if not isinstance(call, dict) or 'function' not in call:
                    continue

                func_name = call['function'].get('name')
                arguments = call['function'].get('arguments')
                
                if not func_name or not arguments:
                    results.append("工具调用参数缺失")
                    continue

                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    pass  # 保持原始参数格式
                            
                result = await self.session.call_tool(func_name, arguments)
                
                # 深度解析框架返回的TextContent结构
                if hasattr(result.content, 'text'):
                    tool_content = result.content.text  # 直接访问对象属性
                elif isinstance(result.content, dict) and 'text' in result.content:
                    tool_content = result.content['text']  # 处理字典格式
                else:
                    tool_content = str(result.content)
                
                # 彻底处理转义字符
                tool_content = tool_content.replace("\\n", "\n").replace("\\'", "'")
                
                tool_response = f"【{func_name}】\n{tool_content}"
                results.append(tool_response)
                
                self.conversation_history.append({
                    "role": "tool",
                    "content": tool_content,
                    "tool_call_id": call.get('id', 'default_id')
                })
            except Exception as e:
                results.append(f"工具调用失败: {str(e)}")
        return results

    # async def chat_loop(self):
    #     """交互式聊天循环"""
    #     print("\nMCP客户端已启动！")
    #     print("输入查询或'quit'退出")
        
    #     while True:
    #         try:
    #             query = input("\n查询: ").strip()
    #             if query.lower() == 'quit':
    #                 break
                    
    #             response = await self.process_query(query)
    #             print(f"\n响应: {response}")
                
    #         except Exception as e:
    #             print(f"\n错误: {str(e)}")
    
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