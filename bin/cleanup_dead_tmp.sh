#!/usr/bin/env bash
# remove tmp/ directories corresponding to dead processes

find tmp/ -mindepth 1 -maxdepth 1 \
		| grep -vf <(ps -eo pid) \
		| while read -r d; do
	rm -r $d
done

# if calibre isn't running, clean up any leftover temp dirs older than 5 minutes
if ! pgrep -f calibre >/dev/null ; then
	find /tmp -mindepth 1 -maxdepth 1 -type d -name 'calibre*' -cmin +5 -print0 \
		| xargs -r0 rm -r
fi

