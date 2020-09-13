create table if not exists requestLog (
	id bigserial primary key,
	created timestamp not null default(current_timestamp),
	infoRequestMs int4 not null,
	epubCreationMs int4 not null,
	urlId text not null,
	query text not null,
	ficInfo text not null,
	epubFileName text not null,
	hash text not null,
	url text not null
);

