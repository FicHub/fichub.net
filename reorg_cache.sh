#!/usr/bin/env bash

find ./epub_cache/ -type f | while read -r f; do
	hash="$(md5sum "$f" | cut -c1-32)"
	urlId="$(basename "$f" | sed 's/.*-\(.*\).epub$/\1/')"
	echo "$f => cache/epub/${urlId}/${hash}.epub"
	mkdir -p ./cache/epub/${urlId}/
	mv "$f" "./cache/epub/${urlId}/${hash}.epub"
done

# update exportFileNames of cached epubs
find cache/epub/ -type f | sed "s:cache/epub/\(.*\)/\(.*\).epub:update requestLog set exportFileName = 'cache/epub/\1/\2.epub' where sourceId = 2 and urlId = '\1' and exportFileHash = '\2';:"  | psql fic_pw

