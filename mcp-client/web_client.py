# MCP\mcp-client\web_client.py
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from client import MCPClient
import uvicorn
import os
import asyncio
import json

app = FastAPI()

# 静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def web_interface():
    """返回网页界面"""
    return FileResponse("index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client = MCPClient()
    tool_calls_info = []
    
    try:
        # 连接服务
        server_path = os.path.abspath(os.path.join("..", "tools", "weather.py"))
        available_tools = await client.connect_to_server(server_path)
        
        # 发送初始信息
        tools_list = [tool['function']['name'] for tool in available_tools]
        await websocket.send_json({
            "type": "system",
            "data": f"系统：已连接天气服务，可用工具：{', '.join(tools_list)}"
        })
        
        async def send_tool_calls_update():
            """发送更新后的工具调用信息"""
            await websocket.send_json({
                "type": "tool_calls_update",
                "data": tool_calls_info
            })
        
        while True:
            query = await websocket.receive_text()
            async for event in client.process_query_stream(query):
                event_type = event["type"]
                event_data = event.get("data", None)
                
                # 处理不同类型的事件
                if event_type == "text_chunk":
                    await websocket.send_json({
                        "type": "text_chunk",
                        "data": event_data
                    })
                elif event_type == "tool_call_start":
                    # 记录工具调用开始
                    tool_calls_info.append({
                        "name": event_data["name"],
                        "arguments": event_data["args"],
                        "status": "processing",
                        "result": ""
                    })
                    await send_tool_calls_update()
                elif event_type == "tool_call_result":
                    # 更新工具调用结果
                    if tool_calls_info:
                        tool_call = tool_calls_info[-1]
                        tool_call["status"] = "completed"
                        tool_call["result"] = event_data
                        await send_tool_calls_update()
                    
                    # 发送工具调用的结果
                    await websocket.send_json({
                        "type": "tool_call_result",
                        "data": event_data
                    })
                elif event_type == "tool_call_error":
                    # 更新工具调用错误
                    if tool_calls_info:
                        tool_call = tool_calls_info[-1]
                        tool_call["status"] = "error"
                        tool_call["result"] = event_data
                        await send_tool_calls_update()
                elif event_type == "error":
                    await websocket.send_json({
                        "type": "error",
                        "data": event_data
                    })
                elif event_type == "end":
                    await websocket.send_json({"type": "end"})
                
    except Exception as e:
        error_msg = f"系统错误: {str(e)}"
        await websocket.send_json({
            "type": "error",
            "data": error_msg
        })
    finally:
        await client.cleanup()
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
