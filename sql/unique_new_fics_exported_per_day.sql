-- stats on unique never before exported fics per day
\timing on
; with ncpr as (
	select rl.id, rl.created, rl.urlId,
		((rl.ficInfo::json)->>'chapters')::int as chapters
	from requestLog rl
	where not exists (
		select 1
		from requestLog prl
		where prl.urlId = rl.urlId
			and prl.id < rl.id
			and prl.ficInfo is not null
	)
		and rl.ficInfo is not null
)
select date(rl.created), count(1) as cnt, sum(rl.chapters) as chapters
from ncpr rl
group by date(rl.created)
order by date(rl.created) desc
limit 14;
