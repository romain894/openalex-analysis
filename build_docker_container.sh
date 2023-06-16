#!/bin/bash
# build the docker container and push it on docker hub

# create the requierments.txt file for python packages
# pipreqs . --force
printf "Don't forget to run pipreqs . --force if you added python packages in the code"

# remove the last image
docker image rm romain894/src-dash-app
# create the new image
docker build --tag romain894/src-dash-app .
# push the image
docker push romain894/src-dash-app
