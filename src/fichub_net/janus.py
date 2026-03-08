#!/usr/bin/env -S uv run --quiet
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar
import base64
import functools
from http import HTTPStatus
import inspect
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import os.path
from pathlib import Path
import resource
import subprocess
import sys
import time

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

import psutil

# for calls to janus service
import requests

EXPECTED_ARG_COUNT = 3
USE_LOCAL_CALIBRE = os.environ.get("JANUS_USE_LOCAL_CALIBRE", "false").lower() == "true"
EBOOK_CONVERT_PATH = os.environ.get(
    "JANUS_EBOOK_CONVERT_PATH", "/opt/calibre/ebook-convert"
)


class WaitTimeoutError(Exception):
    pass


def init_logging() -> None:
    if not Path("./log").is_dir():
        Path("./log").mkdir(parents=True)

    file_formatter = logging.Formatter(
        fmt="%(asctime)s\t%(levelname)s\t%(message)s", datefmt="%s"
    )
    file_handler = RotatingFileHandler("./log/janus.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    stream_formatter = logging.Formatter(fmt="%(asctime)s\t%(levelname)s\t%(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(stream_formatter)

    logging.captureWarnings(True)

    root_logger = logging.getLogger()

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    root_logger.setLevel(logging.DEBUG)


class LoggingTimer:
    def __init__(self, name: str, args: dict[str, str]) -> None:
        self.name = name
        self.args = args
        self.s = time.time()

    def __enter__(self) -> None:
        self.s = time.time()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        e = time.time()
        d = e - self.s
        msg = "timing: {}({}) took {}s".format(
            self.name, ", ".join([f"{k}={v}" for k, v in self.args.items()]), f"{d:.3f}"
        )
        plog(
            msg,
            func_name=self.name,
            func_args=self.args,
            duration_ms=round(d * 1000, 3),
        )


T = TypeVar("T")
P = ParamSpec("P")


def trace_timing(fspec: list[str]) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            with LoggingTimer(
                func.__name__,
                {
                    k: v
                    for k, v in inspect.getcallargs(func, *args, **kwargs).items()
                    if k in fspec
                },
            ):
                return func(*args, **kwargs)

        return wrapped

    return decorator


def plog(msg: str, **kwargs: Any) -> None:
    msg = json.dumps(
        {"service": "fichub/janus", "pid": os.getpid(), "msg": msg} | kwargs
    )

    janus_logger = logging.getLogger("janus")
    janus_logger.info(msg)


def get_wait_key(cmdline: list[str]) -> str:
    if len(cmdline) != (EXPECTED_ARG_COUNT + 1):  # includes python
        return "null"
    return cmdline[-1].split(".")[-1]


@trace_timing(["key"])
def wait_for_our_turn(key: str) -> None:
    max_other_waiting = 3
    delta = 2.5
    us_pid = os.getpid()
    us_created = None
    for _i in range(int(180 / delta)):
        cnt = 0
        min_pid: int | None = None
        min_created = 1.0 * 9e9
        for p in psutil.process_iter():
            if p.pid == us_pid:
                us_created = p.create_time()
            cmdl = p.cmdline()
            if (
                len(cmdl) != (EXPECTED_ARG_COUNT + 1)  # includes python
                or cmdl[0] != "python3"
                or cmdl[1] != "/home/fichub/fichub.net/janus.py"
            ):
                continue
            cnt += 1
            if get_wait_key(cmdl) != key:
                continue
            if min_pid is None or p.create_time() < min_created:
                min_pid = p.pid
                min_created = p.create_time()
        if (
            min_created is not None
            and us_created is not None
            and min_pid != us_pid
            and min_created < us_created
        ):
            if cnt > max_other_waiting:
                plog(f"there are at least {max_other_waiting} other waiting; aborting")
                sys.exit(103)
            plog(
                "previous export still running",
                min_pid=min_pid,
                min_created=min_created,
                us_created=us_created,
            )
            time.sleep(delta)
        else:
            return
    msg = "error: it was never our turn"
    raise WaitTimeoutError(msg)


def limit_virtual_memory() -> None:
    max_virtual_memory = int(1024 * 1024 * 1024 * 2.5)  # 2.5 GiB
    resource.setrlimit(resource.RLIMIT_AS, (max_virtual_memory, resource.RLIM_INFINITY))


def convert_local(epub_fname: str, tmp_fname: str) -> int:
    ret = 255
    try:
        res = subprocess.run(
            [EBOOK_CONVERT_PATH, epub_fname, tmp_fname],
            timeout=60 * 5,
            check=False,
        )  # preexec_fn=limit_virtual_memory)
        ret = res.returncode
    except Exception as e:
        plog("unhandled exception in convert_local", err=f"{e}")
    return ret


@trace_timing(["epub_fname", "tmp_fname"])
def convert_janus(epub_fname: str, tmp_fname: str) -> int:
    ret = 255

    input_filename = Path(epub_fname).name
    output_filename = Path(tmp_fname).name

    with Path(epub_fname).open("rb") as f:
        content = f.read()
    content_b64 = base64.b64encode(content).decode("utf-8")

    timeout_s = 285.1
    if "CONVERT_TIMEOUT" in os.environ:
        timeout_s = int(os.environ["CONVERT_TIMEOUT"]) - 10.1
        plog("janus request timeout", timeout_s=timeout_s)

    try:
        r = requests.post(
            "http://localhost:8001/convert",
            json={
                "input_filename": input_filename,
                "output_filename": output_filename,
                "content": content_b64,
                "timeout_s": timeout_s,
            },
            headers={
                "User-Agent": "fichub.net/janus/0.0.1",
            },
        )
        if r.status_code != HTTPStatus.OK:
            try:
                plog(
                    "janus request returned non-200",
                    status_code=r.status_code,
                    response=r.content.decode("utf-8"),
                )
            except Exception:
                plog(
                    "janus request returned non-200",
                    status_code=r.status_code,
                    response=f"{r.content!r}",
                )

        r.raise_for_status()

        j = r.json()

        content_b64 = j["content"]
        content = base64.b64decode(content_b64)
        j["content.len"] = len(content)
        del j["content"]

        plog("janus request returned 200", response=j)
        with Path(tmp_fname).open("wb") as f:
            f.write(content)

        ret = j["code"]
    except Exception as e:
        plog("unhandled exception in convert_janus", err=f"{e}")
    return ret


def main() -> int:
    if len(sys.argv) != EXPECTED_ARG_COUNT:
        return 1

    epub_fname = str(sys.argv[1])
    tmp_fname = str(sys.argv[2])

    us_pid = os.getpid()
    key = "null"
    for p in psutil.process_iter():
        if p.pid == us_pid:
            plog("cmdline", cmdline=p.cmdline())
            key = get_wait_key(p.cmdline())

    plog("waiting on key", key=key)
    wait_for_our_turn(key)

    ret = 255

    if USE_LOCAL_CALIBRE:
        ret = convert_local(epub_fname, tmp_fname)
    else:
        ret = convert_janus(epub_fname, tmp_fname)

    return ret


if __name__ == "__main__":
    init_logging()
    try:
        ret = main()
        plog("returning", ret=ret)
    except Exception as e:
        plog("unhandled exception in main", err=f"{e}")
        ret = 255
    sys.exit(ret)
