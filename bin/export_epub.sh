#!/usr/bin/env bash
# (re-)export an epub for a given query

id="$1"

echo curl "https://fichub.net/api/v0/epub?q=${id}&automated=true"
du -h cache/epub/${id}/*.epub
curl "https://fichub.net/api/v0/epub?q=${id}&automated=true"
echo $?
du -h cache/epub/${id}/*.epub

