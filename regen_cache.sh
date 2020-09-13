#!/usr/bin/env bash

ls -1 epub_cache/ | sed 's/.*-\(.*\).epub/\1/' > tmp_regen_ids
rm epub_cache/*.epub

for id in $(cat tmp_regen_ids); do
	./export_epub.sh ${id}
done

