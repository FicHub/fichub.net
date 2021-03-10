#!/usr/bin/env bash
# create a gzip'd dump of the database (defaults to fichub_net)

dbname="${1-fichub_net}"

mkdir -p bak/

pg_dump "${dbname}" | gzip > bak/${dbname}_dump_$(date '+%s').sql.gz

