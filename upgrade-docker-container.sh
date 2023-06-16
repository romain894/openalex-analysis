#!/bin/bash
# upgrade the running src-dash-app container
# run with sudo

docker compose pull
docker compose up -d
