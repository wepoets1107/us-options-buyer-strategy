# 一键跑：构建快照 -> 保存 -> 起实时网页看板（端口 5060，后台线程定时刷新）
from web.app import serve

if __name__ == "__main__":
    print(f"看板 http://127.0.0.1:5060")
    serve()
