#!/bin/bash

celery -A main_app.celery_app worker --loglevel=INFO