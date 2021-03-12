#!/usr/bin/env bash
# attempt to free up disk space by cleaning up outmoded exports first, and
# then fics which haven't been exported in a while as a fallback
set -e

function disk_usage() {
	df -HT / | tail -1 | tr ' ' '\n' | sed -n 's/%//p'
}
echo "current usage: $(disk_usage)"

if (( $(disk_usage) < 70 )); then
	echo "usage is already below limit"
	exit 0
fi

./cleanup_outmoded_cache.sh

if (( $(disk_usage) < 70 )); then
	echo "usage is already below limit"
	exit 0
fi

{
cat<<SQL
COPY (
	select rl.urlId
	from requestLog rl
	join requestSource s on s.id = rl.sourceId
	where rl.urlId is not null
		and rl.exportFileHash is not null
		and s.isAutomated = false
	group by rl.urlId
	order by max(date(rl.created)) asc,
		count(1) asc, urlId
) TO STDOUT
SQL
} | psql fichub_net | while read -r id; do
	echo "removing ${id}"
	rm -rf ./cache/{epub,html,mobi,pdf}/${id}/
	if (( $(disk_usage) < 70 )); then
		break;
	fi
done

