\timing on

-- print last week's worth of daily epub export timing stats
select
	date(rl.created),
	count(1),
	round(avg(exportMS)) as avgExportMS,
	round(avg(infoRequestMs)) as avgInfoRequestMS,
	round(avg(exportMS + infoRequestMs)) as avgMS
from requestLog rl
where rl.urlId is not null
	and rl.exportFileHash is not null
	and rl.etype = 'epub'
group by date(rl.created)
order by date(rl.created)
desc limit 7;

-- print 12 hours worth of hourly epub export timing stats
select
	date_trunc('hour', rl.created),
	count(1),
	round(avg(exportMS)) as avgExportMS,
	round(avg(infoRequestMs)) as avgInfoRequestMS,
	round(avg(exportMS + infoRequestMS)) as avgMS
from requestLog rl
where rl.urlId is not null
	and rl.exportFileHash is not null
	and rl.etype = 'epub'
group by date_trunc('hour', rl.created)
order by date_trunc('hour', rl.created)
desc limit 12;
