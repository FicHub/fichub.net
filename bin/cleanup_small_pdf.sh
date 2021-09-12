#!/usr/bin/env bash
# remove cached pdfs that are smaller than <=3M. These should be relatively
# quick to regenerate.
set -e

find /mnt/fichub/cache/pdf/ -type f -size -4M -delete

