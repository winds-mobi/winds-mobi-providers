#!/usr/bin/env bash

su - windmobile -c "cd /home/windmobile/winds-mobi-providers/; git fetch; git pull"
su - windmobile -c "/home/windmobile/.virtualenvs/winds-mobi-providers/bin/pipenv install --deploy"
