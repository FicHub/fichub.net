#!/usr/bin/env python3
from typing import List
import sys
import subprocess
import resource
import os
import psutil
import time

def plog(msg: str) -> None:
	print(msg)
	if not msg.endswith('\n'):
		msg += '\n'
	with open('./janus.log', 'a+') as logf:
		logf.write(msg)

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
				plog(f'janus|{usPid}|there are at least 3 other waiting; aborting')
				sys.exit(103)
			plog(f'janus|{usPid}|previous export still running: {minPid} {minCreated} < {usCreated}')
			time.sleep(delta)
		else:
			return
	raise Exception(f'janus|{usPid}|error: it was never our turn')

def limitVirtualMemory() -> None:
	MAX_VIRTUAL_MEMORY = int(1024 * 1024 * 1024 * 2.5) # 2.5 GiB
	resource.setrlimit(resource.RLIMIT_AS,
			(MAX_VIRTUAL_MEMORY, resource.RLIM_INFINITY))

def main() -> int:
	if len(sys.argv) != 3:
		return 1

	epub_fname = str(sys.argv[1])
	tmp_fname = str(sys.argv[2])

	usPid = os.getpid()
	key = 'null'
	for p in psutil.process_iter():
		if p.pid == usPid:
			plog(f'janus|{usPid}|cmdline: {p.cmdline()}')
			key = getWaitKey(p.cmdline())

	plog(f'janus|{usPid}|waiting on {key}')
	waitForOurTurn(key)
	plog(f'janus|{usPid}|proceeding')

	ret = 255
	stime = time.time()
	try:
		res = subprocess.run(['/opt/calibre/ebook-convert', epub_fname, tmp_fname],
				timeout=60*5,
				)#preexec_fn=limitVirtualMemory)
		ret = res.returncode
	except Exception as e:
		plog(f'janus|{usPid}|exception: {e}')
	etime = time.time()
	dtime = etime - stime
	plog(f'janus|{usPid}|returning {ret} after {dtime}s')
	return ret

if __name__ == '__main__':
	try:
		ret = main()
	except Exception as e:
		plog(f'janus|main|exception: {e}')
		ret = 255
	sys.exit(ret)

