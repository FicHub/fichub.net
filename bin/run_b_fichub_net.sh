#!/usr/bin/env bash

if ! ./bin/check_setup.sh; then
	exit $?
fi

instance="beta"
export PYTHONPATH=/home/fichub/pylib
export OIL_DB_DBNAME=b_fichub
mkdir -p ./log/ ./run/

exec uwsgi --plugin python3 --venv venv/ --enable-threads \
	--reuse-port --uwsgi-socket 127.0.0.1:9294 \
	--plugin logfile \
	--logger file:logfile=./log/b_fichub_net.log,maxsize=20000000 \
	--pidfile ./run/master_${instance}.pid \
	--master --processes 2 --threads 4 \
	--daemonize2 /dev/null \
	--wsgi-file ./main.py --callable app

