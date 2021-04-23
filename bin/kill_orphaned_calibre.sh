#!/usr/bin/env bash

# TODO if everything is an orphan there's probably no space before the initial # 1
ps xjf -u fichub_net | grep -E '[0-9] /opt/calibre' | tr -s ' ' | grep '^ 1 '
echo kill -9 $(ps xjf -u fichub_net | grep -E '[0-9] /opt/calibre' | tr -s ' ' | grep '^ 1 ' | cut -d' ' -f3)

