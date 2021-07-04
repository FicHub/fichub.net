#!/usr/bin/env bash
# check that the setup can probably run

if [[ ! -f authentications.py ]]; then
	echo "error: no authentications.py file"
	exit 1
fi

exit 0

