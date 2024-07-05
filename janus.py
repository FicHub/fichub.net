#!./venv/bin/python3
from typing import List, TypeVar, ParamSpec, Any, Callable, Dict
import sys
import subprocess
import resource
import os
import psutil
import time
import logging
import functools
import inspect

# for calls to janus service
import requests
import base64
import json
import os.path

USE_LOCAL_CALIBRE=False

def init_logging() -> None:
	if not os.path.isdir('./log'):
		os.makedirs('./log')

	from logging.handlers import RotatingFileHandler
	file_formatter = logging.Formatter(fmt="%(asctime)s\t%(levelname)s\t%(message)s", datefmt='%s')
	file_handler = RotatingFileHandler('./log/janus.log')
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
	def __init__(self, name: str, args: Dict[str, str]) -> None:
		self.name = name
		self.args = args
		self.s = time.time()

	def __enter__(self) -> None:
		self.s = time.time()

	def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
		e = time.time()
		d = e - self.s
		msg = "timing: {}({}) took {}s".format(self.name, ', '.join([f"{k}={v}" for k, v in self.args.items()]), f"{d:.3f}")
		plog(msg, func_name=self.name, func_args=self.args, duration_ms=round(d*1000, 3))


T = TypeVar("T")
P = ParamSpec("P")


def trace_timing(fspec: List[str]) -> Callable[[Callable[P, T]], Callable[P, T]]:
	def decorator(func: Callable[P, T]) -> Callable[P, T]:
		@functools.wraps(func)
		def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
			with LoggingTimer(func.__name__,
					{k: v for k, v in inspect.getcallargs(func, *args, **kwargs).items() if k in fspec}
			):
				return func(*args, **kwargs)

		return wrapped

	return decorator


def plog(msg: str, **kwargs) -> None:
	msg = json.dumps({"service": "fichub/janus", "pid": os.getpid(), "msg": msg} | kwargs)
	logging.info(msg)

def getWaitKey(cmdline: List[str]) -> str:
	if len(cmdline) != 4:
		return 'null'
	return cmdline[-1].split('.')[-1]

@trace_timing(['key'])
def waitForOurTurn(key: str) -> None:
	delta = 2.5
	usPid = os.getpid()
	usCreated = None
	for i in range(int(180 / delta)):
		cnt = 0
		minPid = None
		minCreated = None
		for p in psutil.process_iter():
			if p.pid == usPid:
				usCreated = p.create_time()
			cmdl = p.cmdline()
			if len(cmdl) != 4 \
					or cmdl[0] != 'python3' \
					or cmdl[1] != '/home/fichub/fichub.net/janus.py':
				continue
			cnt += 1
			if getWaitKey(cmdl) != key:
				continue
			if minPid is None:
				minPid = p.pid
				minCreated = p.create_time()
			elif p.create_time() < minCreated:
				minPid = p.pid
				minCreated = p.create_time()
		if minCreated is not None and usCreated is not None \
				and minPid != usPid and minCreated < usCreated:
			if cnt >= 4:
				plog('there are at least 3 other waiting; aborting')
				sys.exit(103)
			plog('previous export still running', min_pid=minPid, min_created=minCreated, us_created=usCreated)
			time.sleep(delta)
		else:
			return
	raise Exception(f'error: it was never our turn')

def limitVirtualMemory() -> None:
	MAX_VIRTUAL_MEMORY = int(1024 * 1024 * 1024 * 2.5) # 2.5 GiB
	resource.setrlimit(resource.RLIMIT_AS,
			(MAX_VIRTUAL_MEMORY, resource.RLIM_INFINITY))

def convert_local(usPid: int, epub_fname: str, tmp_fname: str) -> int:
	ret = 255
	try:
		res = subprocess.run(['/opt/calibre/ebook-convert', epub_fname, tmp_fname],
				timeout=60*5,
				)#preexec_fn=limitVirtualMemory)
		ret = res.returncode
	except Exception as e:
		plog('unhandled exception in convert_local', err=f'{e}')
	return ret

@trace_timing(["usPid", "epub_fname", "tmp_fname"])
def convert_janus(usPid: int, epub_fname: str, tmp_fname: str) -> int:
	ret = 255

	input_filename = os.path.basename(epub_fname)
	output_filename = os.path.basename(tmp_fname)

	content = open(epub_fname, 'rb').read()
	content_b64 = base64.b64encode(content).decode('utf-8')

	try:
		r = requests.post('http://localhost:8001/convert',
			json={
				'input_filename': input_filename,
				'output_filename': output_filename,
				'content': content_b64,
			},
			headers={
				'User-Agent': 'fichub.net/janus/0.0.1',
			},
		)
		if r.status_code != 200:
			try:
				plog('janus request returned non-200', status_code=r.status_code, response=r.content.decode('utf-8'))
			except:
				plog('janus request returned non-200', status_code=r.status_code, response=f'{r.content!r}')

		r.raise_for_status()

		j = r.json()

		content_b64 = j['content']
		content = base64.b64decode(content_b64)
		j['content.len'] = len(content)
		del j['content']

		plog('janus request returned 200', response=j)
		with open(tmp_fname, 'wb') as f:
			f.write(content)

		ret = j['code']
	except Exception as e:
		plog('unhandled exception in convert_janus', err=f'{e}')
	return ret

def main() -> int:
	if len(sys.argv) != 3:
		return 1

	epub_fname = str(sys.argv[1])
	tmp_fname = str(sys.argv[2])

	usPid = os.getpid()
	key = 'null'
	for p in psutil.process_iter():
		if p.pid == usPid:
			plog('cmdline', cmdline=p.cmdline())
			key = getWaitKey(p.cmdline())

	plog(f'waiting on key', key=key)
	waitForOurTurn(key)

	ret = 255

	if USE_LOCAL_CALIBRE:
		ret = convert_local(usPid, epub_fname, tmp_fname)
	else:
		ret = convert_janus(usPid, epub_fname, tmp_fname)

	return ret

if __name__ == '__main__':
	init_logging()
	try:
		ret = main()
		plog('returning', ret=ret)
	except Exception as e:
		plog('unhandled exception in main', err=f'{e}')
		ret = 255
	sys.exit(ret)

