-- stats on unique users making successful non-automated requests per day
\timing on
select date(rl.created), count(distinct(rs.id))
from requestLog rl
join requestSource rs on rs.id = rl.sourceId
where rl.urlId is not null
	and rl.exportFileHash is not null
	and rs.isAutomated = false
group by date(rl.created)
order by date(rl.created) desc limit 7;
