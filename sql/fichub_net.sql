create table if not exists requestSource (
	id bigserial primary key,
	created timestamp not null default(current_timestamp),
	isAutomated boolean default(false),
	route text,
	description text,
	unique(isAutomated, route, description)
);
insert into requestSource(isAutomated, route, description)
values
	(true, 'backend', 'backend'),
	(false, 'https://fichub.net', 'legacy')
on conflict do nothing;

create table if not exists requestLog (
	id bigserial primary key,
	created timestamp not null default(current_timestamp),
	sourceId bigint references requestSource(id),
	etype text not null,
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

create index if not exists requestLog_urlId_etype_created
	on requestLog(urlId, etype, created);
create index if not exists requestLog_epub_date
	on requestLog(date(created))
	where exportFileName is not null and etype = 'epub';

create table if not exists ficInfo (
	id varchar(128) primary key,
	created timestamp not null default(current_timestamp),
	updated timestamp not null default(current_timestamp),
	title text not null,
	author text not null,
	chapters int4 not null,
	words int8 not null,
	description text not null,
	ficCreated timestamp not null,
	ficUpdated timestamp not null,
	status text not null,
	source text not null,
	extraMeta text,
	sourceId int8 null, -- TODO: make non-nullable when backfilled
	authorId int8 null, -- TODO: make non-nullable when backfilled
	contentHash varchar(256) null
);

create table if not exists exportLog (
	urlId varchar(128) references ficInfo(id),
	version int not null,
	etype text not null,
	inputHash text not null,
	exportHash text not null,
	created timestamp not null default(current_timestamp),

	unique(urlId, version, etype, inputHash)
);

create table if not exists ficBlacklist (
	urlId varchar(128) references ficInfo(id),
	created timestamp not null default(current_timestamp),
	updated timestamp not null default(current_timestamp),
	reason int not null default(1),

	unique(urlId, reason)
);

create table if not exists authorBlacklist (
	sourceId int8 not null,
	authorId int8 not null,
	created timestamp not null default(current_timestamp),
	updated timestamp not null default(current_timestamp),
	reason int not null default(1),

	unique(sourceId, authorId, reason)
);

