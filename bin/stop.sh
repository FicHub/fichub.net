#!/usr/bin/env bash

if [[ -z "${1}" ]]; then
	echo "error: must specify instance name"
	exit 1
fi

instance="${1}"

kill -s SIGINT $(cat master_${instance}.pid)
rm master_${instance}.pid

