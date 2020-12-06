#!/usr/bin/env bash

find cache/epub/ -mindepth 1 -maxdepth 1 | sed 's:cache/epub/::' > tmp_regen_ids

cat tmp_regen_ids | while read -r id; do
	./export_epub.sh ${id}
done

