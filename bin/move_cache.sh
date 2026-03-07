#!/usr/bin/bash
set -eu

old_dir='/mnt/atem_fichub/cache'
new_dir='/mnt/selene_fichub/cache'

cnt=0
for etype in pdf mobi html epub ; do
	if [[ ! -d "${old_dir}/${etype}" ]]; then
		continue
	fi
	echo "${old_dir}/${etype}"
	cd "${old_dir}/${etype}"
	#echo "removing empty dirs"
	#find ./ -mindepth 1 -empty -type d -print0 | xargs -0 -r -n1 rmdir
	echo "moving files"
	find ./ -type f | while read -r ef; do
		#echo "${ef}"
		dname="$(dirname "${ef}")"
		fname="$(basename "${ef}")"
		#echo $dname
		#echo $fname
		#echo "${new_dir}/${etype}/${dname}"
		mkdir -p "${new_dir}/${etype}/${dname}"
		if [[ -f "${new_dir}/${etype}/${dname}/${fname}" ]]; then
			#echo "file exists, check hash and delete old"
			nhash="$(md5sum "${new_dir}/${etype}/${dname}/${fname}" | cut -c1-32)"
			ohash="$(md5sum "${old_dir}/${etype}/${dname}/${fname}" | cut -c1-32)"
			if [[ "${ohash}" == "${nhash}" ]]; then
				echo "  hash match"
				rm -v "${old_dir}/${etype}/${dname}/${fname}"
				#while [[ -n "${dname}" ]] && [[ "${dname}" != "./" ]] && [[ "${dname}" != "." ]]; do
				#	#echo rmdir --ignore-fail-on-non-empty -v "${old_dir}/${etype}/${dname}"
				#	#rmdir --ignore-fail-on-non-empty -v "${old_dir}/${etype}/${dname}"
				#	if ! rmdir -v "${old_dir}/${etype}/${dname}" ; then
				#		break
				#	fi
				#	dname="$(dirname "${dname}")"
				#done
			else
				echo "error: ${etype}/${dname}/${fname}: hash mismatch: ${ohash} != ${nhash}"
				rm -v "${new_dir}/${etype}/${dname}/${fname}"
			fi
		else
			cp -v "${old_dir}/${etype}/${dname}/${fname}" "${new_dir}/${etype}/${dname}/${fname}"
		fi
		cnt=$((cnt + 1))
		if ((cnt > 50000)); then
			exit 0
		fi
	done
done

sleep 1

