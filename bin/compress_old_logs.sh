#!/usr/bin/env bash

cd logs
du -hsc . | tail -1
find ./ -type f -regex '.*fichub_net.log.[0-9]*' -exec xz {} \;
du -hsc . | tail -1

