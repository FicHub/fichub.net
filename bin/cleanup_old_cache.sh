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

./bin/cleanup_dead_tmp.sh

./bin/cleanup_outmoded_cache.sh

if (( $(disk_usage) < 70 )); then
	echo "usage is already below limit"
	exit 0
fi

# clean up not-recently-used epubs
grep -f \
  <(echo "COPY ($(cat sql/not_recently_used_exports.sql)) TO STDOUT" | psql) \
  <(ls -1 cache/epub/) \
  | xargs -n1 -I{} find ./cache/epub/{}/ -name '*.epub' -delete
#  | xargs -n1 -I{} find ./cache/epub/{}/ -name '*.epub' -print0 \
#  | xargs -0 du -xhsc | grep 'total'

echo "current usage: $(disk_usage)"

if (( $(disk_usage) < 80 )); then
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
	rm -rf ./cache/{epub,html}/${id}/
	if (( $(disk_usage) < 70 )); then
		break;
	fi
done

echo ''

