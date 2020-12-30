#!/usr/bin/env bash

if [[ ! -f authentications.py ]]; then
	echo "error: no authentications.py file"
	echo "       don't forget about ebooklib either"
	exit 1
fi

export OIL_DB_DBNAME=fic_pw

exec uwsgi --plugin python3 --http-socket 127.0.0.1:9291 --enable-threads \
	--daemonize2 ./fichub_net_uwsgi.log \
	--pidfile master.pid --master --processes 4 --threads 4 \
	--wsgi-file ./main.py --callable app
