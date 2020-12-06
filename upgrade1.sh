#!/usr/bin/env bash
set -ex

date
pg_dump fic_pw | gzip > fic_pw_dump_$(date '+%s').sql.gz
date
git fetch
git merge --ff-only 3e73423065fcf9a62d7316bdada81a21c2243f0f
make prod
cat sql/upgrade1.sql | sed -e 's/^rollback/--rollback/' -e 's/^--commit/commit/' | psql fic_pw
./restart.sh
date
./reorg_cache.sh
date

