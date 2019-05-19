#!/usr/bin/env bash

# Makes sure we exit if flock fails.
set -e

PROVIDER=$1
(
  flock -n 200 || exit 1

  /home/windmobile/.local/share/virtualenvs/winds-mobi-providers-SLXTQqYQ/bin/python /home/windmobile/winds-mobi-providers/$PROVIDER.py 1>/dev/null 2>>/data/var/log/winds.mobi/$PROVIDER.err

) 200>/home/windmobile/winds-mobi-providers/$PROVIDER.lock
