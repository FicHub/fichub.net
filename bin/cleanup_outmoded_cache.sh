#!/usr/bin/env bash
# remove export files which have been superseded by a successful new export
# for the same fic and export type
set -e

function disk_usage() {
	df -HT / | tail -1 | tr ' ' '\n' | sed -n 's/%//p'
}
echo "current usage: $(disk_usage)"

echo "removing old duplicate exports"
{
cat<<SQL
COPY (
	with dupIds as (
		select distinct(o.id)
		from requestLog o
		join requestLog n
			on n.urlId = o.urlId
			and n.etype = o.etype
			and n.exportFileHash != o.exportFileHash
			and n.created > o.created
		where o.urlId is not null
			and o.exportFileHash is not null
		order by o.id asc
	)
	select rl.etype, rl.urlId, rl.exportFileHash
	from requestLog rl
	join dupIds d on d.id = rl.id
	order by rl.created asc
) TO STDOUT
SQL
} | psql fichub \
	| sed -rn 's|^([^\t]*)\t([^\t]*)\t([^\t]*)$|/mnt/fichub/cache/\1/\2/\3.\1|p' \
	| sed 's/.html$/.zip/' \
	| xargs rm -f

echo "current usage: $(disk_usage)"

