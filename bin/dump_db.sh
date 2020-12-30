#!/usr/bin/env bash
# create a gzip'd dump of the database (defaults to fic_pw)

dbname="${1-fic_pw}"

mkdir -p bak/

pg_dump "${dbname}" | gzip > bak/${dbname}_dump_$(date '+%s').sql.gz

