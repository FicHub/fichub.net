#!/usr/bin/bash

URLID="$1"

if [[ -z "${URLID}" ]]; then
	echo "usage: $0 <url id>"
	exit 1
fi

for et in epub html mobi pdf ; do
	if [[ ! -d /mnt/atem_fichub/cache/${et}/${URLID:0:3}/${URLID:3:3}/${URLID:6:2}/${URLID}/ ]] ; then
		continue
	fi
	ls /mnt/atem_fichub/cache/${et}/${URLID:0:3}/${URLID:3:3}/${URLID:6:2}/${URLID}/
	rm -vr /mnt/atem_fichub/cache/${et}/${URLID:0:3}/${URLID:3:3}/${URLID:6:2}/${URLID}/
	rmdir -vp /mnt/atem_fichub/cache/${et}/${URLID:0:3}/${URLID:3:3}/${URLID:6:2}
done

