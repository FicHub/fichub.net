#!/usr/bin/bash
exec uwsgi --plugin python --http :9091 --enable-threads \
	--logto ./uwsgi.log \
	--safe-pidfile master.pid --master --processes 2 --threads 2 \
	--wsgi-file ./main.py --callable app

