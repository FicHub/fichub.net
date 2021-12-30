#!/usr/bin/env bash
# create a gzip'd dump of the database (defaults to fichub)

dbname="${1-fichub}"

mkdir -p bak/

pg_dump "${dbname}" | gzip -9 > bak/${dbname}_dump_$(date '+%s').sql.gz

