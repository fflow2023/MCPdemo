# MCP-Demo
>参考资料:   
[MCP官方中文文档](https://mcp-docs.cn/quickstart/server)

(由于没有US的手机号，拼尽全力也无法获得Claude的可用api，所以现在接入的是siliconflow的DeepSeekV3模型。所以需要先注册siliconflow获得APIkey,并创建`mcp-client/.env`填入`SILICONFLOW_API_KEY=xxx`)

**使用方法**:   
参照官方文档quickstart里的教程配置uv环境，在`/mcp-client`目录下运行`uv run web.py`启动客户端，然后打开`http://localhost:8000/`，就可以和“ ~~(美国)~~ 天气助手”对话了。

> 更新日志：  
5.24 增加了网页端对话
5.31 优化了好多东西，尝试加入了websearch的tools
（需要在 tools\.env 里填入BAIDU_API_KEY=xxx ，在https://console.bce.baidu.com/iam/#/iam/apikey/list申请）