"""Shared retry boundary for Bifu's read-only manual acceptance tools."""

import asyncio
import sys

from ccxt import RequestTimeout


async def retry_readonly_once(first_call, retry_call=None, *, retry_delay=1.0):
    try:
        return await first_call()
    except RequestTimeout:
        print(
            "Bifu 测试环境首次请求超时，正在进行第 2 次只读重试...",
            file=sys.stderr,
        )
        if retry_delay:
            await asyncio.sleep(retry_delay)
        return await (retry_call or first_call)()
