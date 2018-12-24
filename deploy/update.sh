#!/usr/bin/env bash

su - windmobile -c "cd /home/windmobile/winds-mobi-providers/; git fetch; git pull"
su - windmobile -c "/home/windmobile/.pyenv/versions/providers/bin/pip install -r /home/windmobile/winds-mobi-providers/requirements.txt"
