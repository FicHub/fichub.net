#!/usr/bin/env python3
import os
import shutil
from db import FicInfo
import ebook

LEGACY_CACHE_DIR="/veil/fichub_net_cache"
TARGET_CACHE_DIR="/veil/new_fichub_net_cache"

def buildLegacyExportPath(etype: str, urlId: str, create: bool = False) -> str:
	fdir = os.path.join(LEGACY_CACHE_DIR, etype, urlId)
	if create and not os.path.isdir(fdir):
		os.makedirs(fdir)
	return fdir

def buildExportPath(etype: str, urlId: str, create: bool = False) -> str:
	urlId = urlId.lower()
	parts = [TARGET_CACHE_DIR, etype]
	for i in range(0, len(urlId), 3):
		parts.append(urlId[i:i + 3])
	parts.append(urlId)
	fdir = os.path.join(*parts)
	if create and not os.path.isdir(fdir):
		os.makedirs(fdir)
	return fdir

for fi in FicInfo.select():
	urlId = fi.id
	print(f'urlId: {urlId}')
	for etype in {'epub', 'html', 'mobi', 'pdf'}:
		odir = buildLegacyExportPath(etype, urlId)
		if not os.path.isdir(odir):
			continue
		tdir = buildExportPath(etype, urlId, create=True)
		for entry in os.scandir(odir):
			src = entry.path
			dst = os.path.join(tdir, entry.name)
			print(f'  {src} => {dst}')
			shutil.copy2(src, dst)

