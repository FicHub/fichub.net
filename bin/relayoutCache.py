#!/usr/bin/env python3
import os
import shutil

from fichub_net.db import FicInfo

LEGACY_CACHE_DIR = "/veil/fichub_net_cache"
TARGET_CACHE_DIR = "/veil/new_fichub_net_cache"


def build_legacy_export_path(etype: str, url_id: str, create: bool = False) -> str:
    fdir = os.path.join(LEGACY_CACHE_DIR, etype, url_id)
    if create and not os.path.isdir(fdir):
        os.makedirs(fdir)
    return fdir


def build_export_path(etype: str, url_id: str, create: bool = False) -> str:
    url_id = url_id.lower()
    parts = [TARGET_CACHE_DIR, etype]
    parts.extend(url_id[i : i + 3] for i in range(0, len(url_id), 3))
    fdir = os.path.join(*parts)
    if create and not os.path.isdir(fdir):
        os.makedirs(fdir)
    return fdir


for fi in FicInfo.select():
    url_id = fi.id
    print(f"url_id: {url_id}")
    for etype in ("epub", "html", "mobi", "pdf"):
        odir = build_legacy_export_path(etype, url_id)
        if not os.path.isdir(odir):
            continue
        tdir = build_export_path(etype, url_id, create=True)
        for entry in os.scandir(odir):
            src = entry.path
            dst = os.path.join(tdir, entry.name)
            print(f"  {src} => {dst}")
            shutil.copy2(src, dst)
