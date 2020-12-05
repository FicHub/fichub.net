begin transaction;
alter table requestLog rename to oldRequestLog;

create table if not exists requestSource (
	id bigserial primary key,
	created timestamp not null default(current_timestamp),
	isAutomated boolean default(false),
	route text,
	description text
);
insert into requestSource(isAutomated, route, description)
values
	(true, 'backend', 'backend'),
	(false, 'https://fic.pw', 'legacy');

create table if not exists requestLog (
	id bigserial primary key,
	created timestamp not null default(current_timestamp),
	sourceId bigint references requestSource(id),
	query text not null,

	infoRequestMs int4 not null,
	-- may be null if info request fails
	urlId text,
	ficInfo text, -- if failed, this will have error body

	-- export is only attepmted if info request succeeds
	exportMs int4,
	exportFileName text,
	exportFileHash text,
	url text
);

insert into requestLog(
	created, sourceId, query, infoRequestMs, urlId, ficInfo,
	exportMs, exportFileName, exportFileHash, url)
select created
	, (select id from requestSource where description = 'legacy')
	, query, infoRequestMs, urlId, ficInfo
	, epubCreationMs, epubFileName, hash, url
from oldRequestLog;

drop table oldRequestLog;

rollback;
--commit;
