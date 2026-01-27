from __future__ import annotations

import json
import time
import uuid
from typing import Callable

from fastapi import Request


def new_request_id() -> str:
    return str(uuid.uuid4())


def json_log(message: str, **fields):
    # lightweight structured logging without external deps
    payload = {"msg": message, **fields}
    return json.dumps(payload, ensure_ascii=False)


async def timing_middleware(request: Request, call_next: Callable):
    request_id = request.headers.get("X-Request-Id") or new_request_id()
    trace_id = request.headers.get("X-Trace-Id") or new_request_id()

    request.state.request_id = request_id
    request.state.trace_id = trace_id

    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)

    response.headers["X-Request-Id"] = request_id
    response.headers["X-Trace-Id"] = trace_id
    response.headers["X-Response-Time-Ms"] = str(duration_ms)

    return response
