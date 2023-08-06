#!/usr/bin/env bash

if [[ $PROVIDER ]]; then
  python -m "providers.${PROVIDER}"
else
  python run_scheduler.py
fi
