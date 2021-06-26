select rl.urlId
from requestLog rl
join requestSource s on s.id = rl.sourceId
where rl.urlId is not null
	and rl.etype = 'epub'
	and rl.exportFileHash is not null
	and s.isAutomated = false
group by rl.urlId
having max(rl.created) < now() - (interval '30 days')
order by max(rl.created) asc, count(1) asc, urlId
