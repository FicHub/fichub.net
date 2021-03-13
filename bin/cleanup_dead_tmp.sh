#!/usr/bin/env bash
# remove tmp/ directories corresponding to dead processes

find tmp/ -mindepth 1 -maxdepth 1 \
	| grep -vf <(ps -eo pid) \
	| xargs rm -r

