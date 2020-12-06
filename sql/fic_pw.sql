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
	(false, 'https://fic.pw', 'legacy');

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
	status text not null
);

