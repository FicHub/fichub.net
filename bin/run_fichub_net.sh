#!/usr/bin/env bash

if ! ./bin/check_setup.sh; then
	exit $?
fi

if [[ -z "${1}" ]]; then
	echo "error: must specify instance name"
	exit 1
fi

instance="${1}"
export PYTHONPATH=/home/fichub/pylib
export OIL_DB_DBNAME=fichub
mkdir -p ./log/ ./run/

exec uwsgi --plugin python3 --venv venv/ --enable-threads \
	--reuse-port --uwsgi-socket 127.0.0.1:9293 \
	--plugin logfile \
	--logger file:logfile=./log/fichub_net.log,maxsize=20000000 \
	--pidfile ./run/master_${instance}.pid \
	--master --processes 6 --threads 6 \
	--daemonize2 /dev/null \
	--wsgi-file ./main.py --callable app

