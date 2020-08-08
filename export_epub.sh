#!/usr/bin/bash

id="$1"

echo curl "https://fic.pw/api/v0/epub?q=${id}"
curl "https://fic.pw/api/v0/epub?q=${id}"
echo $?

