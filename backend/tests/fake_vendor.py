"""A local HTTP server posing as an AI vendor's API, so that LiteLLM can be exercised for
real without contacting any vendor. Used through the `vendor` fixture (conftest)."""

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeVendor:
    """Answers each request with the next queued reply, recording what it receives."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        self.replies: list[tuple[int, dict[str, Any], float]] = []
        vendor = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 -- http.server API
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                vendor.requests.append((self.path, dict(self.headers), body))
                status, reply, delay = vendor.replies.pop(0)
                time.sleep(delay)
                data = json.dumps(reply).encode()
                try:
                    self.send_response(status)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError:
                    pass  # the client gave up waiting (timeout tests)

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def reply(self, body: dict[str, Any], status: int = 200, delay: float = 0) -> None:
        self.replies.append((status, body, delay))


@contextmanager
def running_vendor() -> Iterator[FakeVendor]:
    fake = FakeVendor()
    # A short poll interval: shutting the server down then takes milliseconds, not 0.5 s
    thread = threading.Thread(
        target=fake.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield fake
    finally:
        fake.server.shutdown()
        fake.server.server_close()


def anthropic_reply(text: str) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def openai_reply(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


def vendor_error(message: str, type_: str = "error") -> dict[str, Any]:
    """An error body in the shape OpenAI / Anthropic use."""
    return {"type": "error", "error": {"type": type_, "message": message}}
