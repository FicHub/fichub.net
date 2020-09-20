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

