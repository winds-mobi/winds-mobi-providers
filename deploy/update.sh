#!/usr/bin/env bash

su - windmobile -c "cd /home/windmobile/winds-mobi-providers/; git fetch; git pull"
su - windmobile -c "cd /home/windmobile/winds-mobi-providers/; /home/windmobile/.pyenv/versions/3.6.6/bin/pipenv install --deploy"
