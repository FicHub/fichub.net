#!/usr/bin/env bash

if [[ ! -f authentications.py ]]; then
	echo "error: no authentications.py file"
	echo "       don't forget about ebooklib either"
	exit 1
fi

export OIL_DB_DBNAME=fic_pw

exec uwsgi --plugin python3 --http-socket 127.0.0.1:9091 --enable-threads \
	--daemonize2 ./b_fic_pw_uwsgi.log \
	--pidfile master.pid --master --processes 2 --threads 3 \
	--wsgi-file ./main.py --callable app

