from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import asyncio

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


class Item(BaseModel):
    name: str
    price: float


@app.post("/item/", summary="Create an item")
async def create_item(item: Item):
    """
    创建商品

    - **name**: 商品名称
    - **price**: 商品价格
    """
    print(f"接收到的商品: {item.name}, 价格: {item.price}")

    # 返回响应体
    return {
        "item_name": item.name,
        "item_price": item.price,
        "message": "商品创建成功"
    }


# 6.8、流式响应
async def generate_stream():
    """模拟流式输出（逐字返回）"""
    words = ["你", "好", "这", "是", "流", "式", "响", "应"]

    for word in words:
        await asyncio.sleep(0.5)  # 每 0.5 秒输出一个字
        yield word.encode("utf-8")  # 流式输出需返回字节流


@app.get("/stream")
async def stream_response():
    """流式响应接口"""
    return StreamingResponse(generate_stream(), media_type="text/plain")




if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
