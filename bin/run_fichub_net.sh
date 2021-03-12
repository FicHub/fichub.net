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

export PYTHONPATH=/home/fichub_net/pylib
export OIL_DB_DBNAME=fichub_net
mkdir -p ./logs/

exec uwsgi --plugin python3 --enable-threads \
	--reuse-port --uwsgi-socket 127.0.0.1:9293 \
	--plugin logfile \
	--logger file:logfile=./logs/fichub_net.log,maxsize=2000000 \
	--pidfile master_${instance}.pid \
	--master --processes 3 --threads 4 \
	--daemonize2 /dev/null \
	--wsgi-file ./main.py --callable app

