# MCP\mcp-client\client.py
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from typing import Optional, List, Dict, Any, AsyncGenerator

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
        self.available_tools = []
        self.tool_calls_history: List[Dict[str, Any]] = []

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
        return self.available_tools

    async def call_deepseek_api_stream(self, messages: List[Dict]) -> AsyncGenerator[Dict, None]:
        """调用DeepSeek API流式接口"""
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
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
                        "tool_choice": "auto",
                        "stream": True  # 启用流式
                    },
                    timeout=30.0
                ) as response:
                    response.raise_for_status()
                    
                    # 事件流处理
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            event_data = line[6:].strip()
                            if event_data == '[DONE]':
                                break
                            
                            try:
                                chunk = json.loads(event_data)
                                yield chunk
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            yield {"error": str(e)}

    # async def process_query_stream(self, query: str) -> AsyncGenerator[Dict, None]:
    #     """流式处理用户查询"""
    #     self.conversation_history.append({"role": "user", "content": query})
    #     current_message = {"role": "assistant", "content": ""}
    #     tool_calls_collected = []
        
    #     # 处理流式响应
    #     async for chunk in self.call_deepseek_api_stream(self.conversation_history):
    #         if "error" in chunk:
    #             yield {"type": "error", "data": chunk["error"]}
    #             return
                
    #         for choice in chunk.get("choices", []):
    #             if "delta" not in choice:
    #                 continue
                    
    #             delta = choice["delta"]
                
    #             # 处理内容增量
    #             if "content" in delta and delta["content"] is not None:
    #                 content = delta["content"]
    #                 current_message["content"] += content
    #                 yield {"type": "text_chunk", "data": content}
                
    #             # 收集工具调用
    #             if "tool_calls" in delta:
    #                 tool_call = delta["tool_calls"][0]
    #                 if "index" in tool_call and tool_call["index"] >= len(tool_calls_collected):
    #                     tool_calls_collected.append({
    #                         "id": tool_call.get("id"),
    #                         "name": "",
    #                         "arguments": ""
    #                     })
                    
    #                 # 更新工具调用参数
    #                 if tool_call["index"] < len(tool_calls_collected):
    #                     current_tool = tool_calls_collected[tool_call["index"]]
    #                     function = tool_call.get("function", {})
    #                     if "name" in function:
    #                         current_tool["name"] = function.get("name")
    #                     if "arguments" in function:
    #                         current_tool["arguments"] += function["arguments"]
        
    #     # 保存完整消息
    #     self.conversation_history.append(current_message)
        
    #     # 处理工具调用
    #     if tool_calls_collected:
    #         for tool_call in tool_calls_collected:
    #             try:
    #                 # 发送工具调用开始事件
    #                 yield {
    #                     "type": "tool_call_start", 
    #                     "data": {
    #                         "name": tool_call["name"],
    #                         "args": tool_call["arguments"]
    #                     }
    #                 }
                    
    #                 # 执行工具调用
    #                 arguments = tool_call["arguments"]
    #                 if arguments:
    #                     try:
    #                         arguments = json.loads(arguments)
    #                     except json.JSONDecodeError:
    #                         pass
                        
    #                 tool_result = await self.session.call_tool(tool_call["name"], arguments)
                    
    #                 # 解析工具结果
    #                 if hasattr(tool_result.content, 'text'):
    #                     tool_content = tool_result.content.text
    #                 elif isinstance(tool_result.content, dict) and 'text' in tool_result.content:
    #                     tool_content = tool_result.content['text']
    #                 else:
    #                     tool_content = str(tool_result.content)
                    
    #                 tool_content = tool_content.replace("\\n", "\n").replace("\\'", "'")
                    
    #                 # 添加到工具调用历史
    #                 tool_data = {
    #                     "name": tool_call["name"],
    #                     "arguments": tool_call["arguments"],
    #                     "result": tool_content,
    #                     "success": True
    #                 }
    #                 self.tool_calls_history.append(tool_data)
                    
    #                 # 发送工具调用结果
    #                 yield {"type": "tool_call_result", "data": tool_content}
                    
    #                 # 添加到对话历史
    #                 self.conversation_history.append({
    #                     "role": "tool",
    #                     "content": tool_content,
    #                     "tool_call_id": tool_call["id"]
    #                 })
                    
    #             except Exception as e:
    #                 error_msg = f"工具调用失败: {str(e)}"
    #                 self.tool_calls_history.append({
    #                     "name": tool_call["name"],
    #                     "arguments": tool_call["arguments"],
    #                     "result": error_msg,
    #                     "success": False
    #                 })
    #                 yield {"type": "tool_call_error", "data": error_msg}
        
    #     if self.conversation_history[-1]["role"] == "tool":
    #         current_message = {"role": "assistant", "content": ""}
            
    #         # 第二次调用API（使用更新后的对话历史）
    #         async for chunk in self.call_deepseek_api_stream(self.conversation_history):
    #             # ... [处理第二次流式响应，与第一次相同] ...
                
    #         # 保存第二次的完整消息
    #             if current_message["content"]:
    #                 self.conversation_history.append(current_message)
    #     # 流式处理结束
    #     yield {"type": "end"}
    async def process_query_stream(self, query: str) -> AsyncGenerator[Dict, None]:
        """流式处理用户查询"""
        self.conversation_history.append({"role": "user", "content": query})
        current_message = {"role": "assistant", "content": ""}
        tool_calls_collected = []
        
        # 第一次API调用和处理
        async for chunk in self.call_deepseek_api_stream(self.conversation_history):
            if "error" in chunk:
                yield {"type": "error", "data": chunk["error"]}
                return
                
            for choice in chunk.get("choices", []):
                if "delta" not in choice:
                    continue
                    
                delta = choice["delta"]
                
                # 处理内容增量
                if "content" in delta and delta["content"] is not None:
                    content = delta["content"]
                    current_message["content"] += content
                    yield {"type": "text_chunk", "data": content}
                
                # 收集工具调用
                if "tool_calls" in delta:
                    tool_call = delta["tool_calls"][0]
                    if "index" in tool_call and tool_call["index"] >= len(tool_calls_collected):
                        tool_calls_collected.append({
                            "id": tool_call.get("id"),
                            "name": "",
                            "arguments": ""
                        })
                    
                    # 更新工具调用参数
                    if tool_call["index"] < len(tool_calls_collected):
                        current_tool = tool_calls_collected[tool_call["index"]]
                        function = tool_call.get("function", {})
                        if "name" in function:
                            current_tool["name"] = function.get("name")
                        if "arguments" in function:
                            current_tool["arguments"] += function["arguments"]
        
        # 保存第一次回复的完整消息
        self.conversation_history.append(current_message)
        
        # 处理工具调用
        if tool_calls_collected:
            for tool_call in tool_calls_collected:
                try:
                    # 发送工具调用开始事件
                    yield {
                        "type": "tool_call_start", 
                        "data": {
                            "name": tool_call["name"],
                            "args": tool_call["arguments"]
                        }
                    }
                    
                    # 执行工具调用
                    arguments = tool_call["arguments"]
                    if arguments:
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            pass
                        
                    tool_result = await self.session.call_tool(tool_call["name"], arguments)
                    
                    # 解析工具结果
                    if hasattr(tool_result.content, 'text'):
                        tool_content = tool_result.content.text
                    elif isinstance(tool_result.content, dict) and 'text' in tool_result.content:
                        tool_content = tool_result.content['text']
                    else:
                        tool_content = str(tool_result.content)
                    
                    tool_content = tool_content.replace("\\n", "\n").replace("\\'", "'")
                    
                    # 添加到工具调用历史
                    tool_data = {
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                        "result": tool_content,
                        "success": True
                    }
                    self.tool_calls_history.append(tool_data)
                    
                    # 发送工具调用结果
                    yield {"type": "tool_call_result", "data": tool_content}
                    
                    # 添加到对话历史
                    self.conversation_history.append({
                        "role": "tool",
                        "content": tool_content,
                        "tool_call_id": tool_call["id"]
                    })
                    
                except Exception as e:
                    error_msg = f"工具调用失败: {str(e)}"
                    self.tool_calls_history.append({
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                        "result": error_msg,
                        "success": False
                    })
                    yield {"type": "tool_call_error", "data": error_msg}
        yield {"type": "end"}
        # 如果有工具调用结果，进行第二次API调用（总结）
        if self.conversation_history[-1]["role"] == "tool":
            current_message = {"role": "assistant", "content": ""}
            
            # 第二次调用API（使用更新后的对话历史）
            async for chunk in self.call_deepseek_api_stream(self.conversation_history):
                if "error" in chunk:
                    yield {"type": "error", "data": chunk["error"]}
                    return
                    
                for choice in chunk.get("choices", []):
                    if "delta" not in choice:
                        continue
                        
                    delta = choice["delta"]
                    
                    # 只处理文本内容，忽略可能的工具调用（在第二次调用中我们不需要工具）
                    if "content" in delta and delta["content"] is not None:
                        content = delta["content"]
                        current_message["content"] += content
                        yield {"type": "text_chunk", "data": content}
            
            # 保存第二次的完整消息
            if current_message["content"]:
                self.conversation_history.append(current_message)
        
        # 流式处理结束
        yield {"type": "end"}


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
        while True:
            query = input("\n查询: ").strip()
            if query.lower() == 'quit':
                break
                
            async for event in client.process_query_stream(query):
                print(event)
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
