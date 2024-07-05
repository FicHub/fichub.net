#!/usr/bin/bash

time psql > /tmp/popular.tmp.data <<EOF
copy (
	select
		fi.id,
		fi.created,
		fi.updated,
		fi.title,
		fi.author,
		fi.chapters,
		fi.words,
		fi.description,
		fi.ficcreated,
		fi.ficupdated,
		fi.status,
		fi.source,
		fi.extrameta,
		fi.sourceid,
		fi.authorid,
		fi.authorurl,
		fi.authorlocalid,
		fi.rawextendedmeta,
		(select count(1) from requestLog rl where rl.urlId = fi.id),
		2147483647
	from ficInfo fi
	where sourceId is not null
		and not exists (
			select 1 from ficBlacklist fb
			where fb.urlId = fi.id and fb.reason is not null
		)
		and not exists (
			select 1 from authorBlacklist ab
			where ab.sourceId = fi.sourceId
				and ab.authorId = fi.authorId
				and ab.reason is not null
		)
) to stdout
EOF

chmod ogu+r /tmp/popular.tmp.data
mv /tmp/popular.tmp.data /tmp/popular.data

