#!/usr/bin/env bash
exec uwsgi --plugin python3 --http-socket 127.0.0.1:9091 --enable-threads \
	--logto ./uwsgi.log \
	--pidfile master.pid --master --processes 2 --threads 2 \
	--wsgi-file ./main.py --callable app

