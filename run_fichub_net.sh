#!/usr/bin/env bash

if [[ -z "${1}" ]]; then
	echo "error: must specify instance name"
	exit 1
fi

instance="${1}"

if [[ ! -f authentications.py ]]; then
	echo "error: no authentications.py file"
	echo "       don't forget about ebooklib either"
	exit 1
fi

export OIL_DB_DBNAME=fic_pw

exec uwsgi --plugin python3 --enable-threads \
	--reuse-port --http-socket 127.0.0.1:9291 \
	--daemonize2 ./fichub_net_uwsgi.log \
	--pidfile master_${instance}.pid \
	--master --processes 3 --threads 4 \
	--wsgi-file ./main.py --callable app

