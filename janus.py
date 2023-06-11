#!/usr/bin/env python3
from typing import List
import sys
import subprocess
import resource
import os
import psutil
import time
import logging

# for calls to janus service
import requests
import base64
import json
import os.path

USE_LOCAL_CALIBRE=False

def init_logging() -> None:
	logging.basicConfig(
		format="%(asctime)s\t%(levelname)s\t%(message)s",
		level=logging.DEBUG,
	)

def plog(msg: str) -> None:
	logging.info(f'janus|{msg}')
	if not msg.endswith('\n'):
		msg += '\n'
	with open('./janus.log', 'a+') as logf:
		logf.write(f'janus|{msg}')

def getWaitKey(cmdline: List[str]) -> str:
	if len(cmdline) != 4:
		return 'null'
	return cmdline[-1].split('.')[-1]

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
				plog(f'{usPid}|there are at least 3 other waiting; aborting')
				sys.exit(103)
			plog(f'{usPid}|previous export still running: {minPid} {minCreated} < {usCreated}')
			time.sleep(delta)
		else:
			return
	raise Exception(f'janus|{usPid}|error: it was never our turn')

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
		plog(f'{usPid}|exception: {e}')
	return ret

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
			plog(f'{usPid}|janus request returned non-200|{r.status_code}|{r.content!r}')
		r.raise_for_status()

		j = r.json()

		content_b64 = j['content']
		content = base64.b64decode(content_b64)
		j['content.len'] = len(content)
		del j['content']

		plog(f'{usPid}|janus returned 200|{json.dumps(j, sort_keys=True)}')
		with open(tmp_fname, 'wb') as f:
			f.write(content)

		ret = j['code']
	except Exception as e:
		plog(f'{usPid}|exception: {e}')
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
			plog(f'{usPid}|cmdline: {p.cmdline()}')
			key = getWaitKey(p.cmdline())

	plog(f'{usPid}|waiting on {key}')
	waitForOurTurn(key)
	plog(f'{usPid}|proceeding')

	ret = 255
	stime = time.time()

	if USE_LOCAL_CALIBRE:
		ret = convert_local(usPid, epub_fname, tmp_fname)
	else:
		ret = convert_janus(usPid, epub_fname, tmp_fname)

	etime = time.time()
	dtime = etime - stime
	plog(f'{usPid}|returning {ret} after {dtime}s')
	return ret

if __name__ == '__main__':
	init_logging()
	try:
		ret = main()
	except Exception as e:
		plog(f'main|exception: {e}')
		ret = 255
	sys.exit(ret)

