create schema if not exists fichub;

create table if not exists fichub.limiter (
	id bigserial primary key,
	key text not null,
	capacity double precision,
	flow double precision,
	value double precision,
	lastDrain timestamp,
	dflt boolean not null default(true),
	unique(key)
);

insert into fichub.limiter(key, capacity, flow, value, lastDrain, dflt)
select 'global', 150, 30.0, 0, now(), false
where not exists (select 1 from fichub.limiter where key = 'global');

drop function if exists fichub.fill_limiter(text, double precision);
create or replace function fichub.fill_limiter (
	w_key text,
	w_value double precision
) returns double precision
as $$
declare
	shortfall double precision;
	retryAfter timestamp;
begin

	if (select 1 from fichub.limiter wl where wl.key = w_key) is null then
		return 60;
	end if;

	lock table fichub.limiter in exclusive mode;

	select (capacity - (w_value + greatest(0,
			value - (extract(epoch from (now() - lastDrain)) * flow)
		))) / flow
	into shortfall
	from fichub.limiter
	where key = w_key;

	if shortfall < 0 then
		return -1.0 * shortfall;
	end if;

	update fichub.limiter
	set lastDrain = now(),
		value = (w_value + greatest(0,
			value - (extract(epoch from (now() - lastDrain)) * flow)
		))
	where key = w_key;

	return -1.0;
end
$$ LANGUAGE plpgsql;

