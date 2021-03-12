#!/usr/bin/env bash
# re-export all previously exported epubs

find cache/epub/ -mindepth 1 -maxdepth 1 | sed 's:cache/epub/::' > tmp/regen_ids

cat tmp/regen_ids | while read -r id; do
	./bin/export_epub.sh ${id}
done

