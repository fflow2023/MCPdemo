from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from client import MCPClient
import uvicorn
import os

app = FastAPI()

# 静态文件目录（可选）
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def web_interface():
    """返回网页界面"""
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket 连接已建立")  # 添加连接日志
    client = MCPClient()
    
    try:
        # 连接天气服务（确认路径正确）
        server_path = os.path.join(os.path.dirname(__file__), "weather", "weather.py")
        server_path = os.path.abspath(os.path.join("..", "weather", "weather.py"))
        print(f"尝试连接服务端路径: {server_path}")  # 添加调试输出
        await client.connect_to_server(server_path)
        print("服务器连接成功")  # 添加服务器连接日志
        
        tools = [tool['function']['name'] for tool in client.available_tools]
        await websocket.send_text(f"系统：已连接天气服务，可用工具：{', '.join(tools)}")
        
        while True:
            try:
                query = await websocket.receive_text()
                print(f"收到查询: {query}")  # 添加接收日志
                response = await client.process_query(query)
                print(f"生成响应: {response}")  # 添加响应日志
                await websocket.send_text(response)
            except Exception as e:
                print(f"消息处理错误: {str(e)}")
                await websocket.send_text(f"错误: {str(e)}")
                
    except Exception as e:
        print(f"全局错误: {str(e)}")
        await websocket.send_text(f"系统故障: {str(e)}")
        await websocket.close()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)