\timing on

-- stats on top requesters in the last 24hours
select rl.sourceId, rs.description, count(1)
from requestLog rl
join requestSource rs
	on rs.id = rl.sourceId
where rl.created >= now() - interval '1 day'
group by rl.sourceId, rs.description
order by count(1)
desc limit 10;
