#!/usr/bin/env bash

id="$1"

echo curl "https://fic.pw/api/v0/epub?q=${id}&automated=true"
du -h cache/epub/${id}/*.epub
curl "https://fic.pw/api/v0/epub?q=${id}&automated=true"
echo $?
du -h cache/epub/${id}/*.epub

