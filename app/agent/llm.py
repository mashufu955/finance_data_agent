import asyncio

import httpx
from langchain_openai import ChatOpenAI

from app.config.app_config import app_config

model_name = app_config.llm.model_name
api_key = app_config.llm.api_key
base_url = app_config.llm.base_url

# Windows Clash 代理会劫持 localhost 请求导致 502/连接失败，
# 与 Qdrant/embedding 客户端一样，需要 trust_env=False 绕过系统代理。
http_async_client = httpx.AsyncClient(trust_env=False)

llm = ChatOpenAI(
    model=model_name,
    api_key=api_key,
    base_url=base_url,
    temperature=0,
    http_async_client=http_async_client,
)

if __name__ == '__main__':
    async def test():
        print(await llm.ainvoke("中国的首都是哪里？"))


    print(asyncio.run(test()))
