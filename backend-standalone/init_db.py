import asyncio
import selectors

async def init():
    ...

if __name__ == "__main__":
    asyncio.run(
        init(),
        debug=True
    )