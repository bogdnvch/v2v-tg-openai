#!/bin/sh

alembic upgrade head

python bot/main.py