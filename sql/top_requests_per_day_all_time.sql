\timing on

-- stats on total successful non-automated requests per day, all time
select date(rl.created), count(1)
from requestLog rl
join requestSource rs on rs.id = rl.sourceId
where rl.urlId is not null
	and rl.exportFileHash is not null
	and rs.isAutomated = false
group by date(rl.created)
order by count(1) desc limit 10;
