#!/usr/bin/env bash
# (re-)export an epub for a given url

id="$1"

echo curl "https://fichub.net/api/v0/epub?q=${id}&automated=true"
curl "https://fichub.net/api/v0/epub?q=${id}&automated=true"
echo $?

