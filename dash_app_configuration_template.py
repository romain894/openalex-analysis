# Romain THOMAS 2023
# Stockholm Resilience Centre, Stockholm University
# 
# Template file for the app configuration
# Copy this file, rename it "dash_app_configuration.py" and set the configuration in it

import os

from redis import StrictRedis
from redis_cache import RedisCache

from openalex_analysis.plot import config

config_email = None # set the email to use the polite pool
config_api_key = None
config_openalex_url = "https://api.openalex.org"
config_allow_automatic_download = True
config_disable_tqdm_loading_bar = False
config_n_max_entities = 10000
config_project_datas_folder_path = "data"
config_parquet_compression = "brotli"
config_max_storage_percent = 95
config_redis_enabled = True
# Set the following lines to None if you don't use Redis cache
config_redis_client = StrictRedis(host=os.environ.get('DOCKER_REDIS_URL', "localhost"),
                                 decode_responses=True,
                                 port=6379,
                                 db=2,)
config_redis_cache = RedisCache(redis_client=config_redis_client)