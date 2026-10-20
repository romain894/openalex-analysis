"""Shared library configuration and credential validation."""

import logging
import os
from os.path import expanduser, isfile, join
import tomllib
import warnings

from pyalex import config as pyalex_config

logging.captureWarnings(True)
# define a custom logging
log_oa = logging.getLogger('openalex_analysis.data.entities_data')
log_oa.addHandler(logging.StreamHandler())
# log_oa.addHandler(logging.FileHandler(__name__ + ".log"))


def _validate_filters(filters):
    """Keep credentials out of dataset filters, cache filenames and logs."""
    if isinstance(filters, dict):
        for key, value in filters.items():
            field = str(key).rsplit('.', 1)[-1].lower().replace('-', '').replace('_', '')
            if field in {'apikey', 'authorization', 'accesstoken'}:
                raise ValueError('Set API credentials using config.api_key, not entity filters.')
            _validate_filters(value)
    elif isinstance(filters, (list, tuple)):
        for value in filters:
            _validate_filters(value)


class AnalysisConfig(dict):
    """
    OpenAlex Analysis configuration class. This class contains the settings used by openalex-analysis (some settings
    are passed to pyalex).

    Tu use it, import the class and set the parameters as follows:
    
    .. code-block:: python

        from openalex_analysis.plot import config

        config.n_max_entities = 10000

    * **email** (*str*) - Optional contact email sent to OpenAlex. This does not replace an API key.
    * **api_key** (*str*) - Your activated OpenAlex API key. Defaults to OPENALEX_API_KEY from the environment,
      or None. Some operations, including subsequent cursor pages, require a key.
    * **openalex_url** (*str*) - Base URL passed to PyAlex. The default is "https://api.openalex.org".
      PyAlex 0.21 currently hardcodes the public host for regular queries.
    * **max_retries** (*int*) - maximum number of retries when querying the OpenAlex API in HTTP. The default value
      is 3.
    * **retry_backoff_factor** (*int*) - Exponential backoff factor passed to PyAlex. The default is 2.
    * **retry_http_codes** (*list[int]*) - The HTTP error codes for which to retry the request. The default is
      [429, 500, 502, 503, 504].
    * **disable_tqdm_loading_bar** (*bool*) - To disable the tqdm loading bar. The default is False.
    * **n_max_entities** (*int*) - Maximum number of entities to download (the default value is to download maximum
      10 000 entities). If set to None, no limitation will be applied.
    * **project_data_folder_path** (*str*) - Path to the folder containing the data downloaded from the OpenAlex API
      (these data are stored in compressed parquet files and used as a cache). The default path is
      "~/openalex-analysis/data".
    * **parquet_compression** (*str*) - Type of compression for the parquet files used as cache (see the Pandas
      documentation). The default value is "brotli".
    * **max_storage_percent** (*int*) - When the disk capacity reaches this percentage, cached parquet files will be
      deleted. The default value is 95.
    * **max_storage_files** (*int*) - When the cache folder reaches this number of files, cached parquet files will be
      deleted. The default value is 10000.
    * **max_storage_size** (*int*) - When the cache folder reached this size (in bytes), cached parquet files will be
      deleted. The default value is 5e9 (5 GB).
    * **min_storage_files** (*int*) - Before deleting files, we check if we exceed the minimum number of files and
      folder size. If one of those minimum if exceeded, we allow the program to delete cached parquet files. This is to
      avoid the setting max_storage_percent to delete every cached file when the disk is almost full. The default value
      is 1000.
    * **min_storage_size** (*int*) - Before deleting files, we check if we exceed the minimum number of files and folder
      size. If one of those minimum if exceeded, we allow the program to delete cached parquet files. This is to avoid
      the setting max_storage_percent to delete every cached file when the disk is almost full. The default value is 5e8
      (500 MB).
    * **cache_max_age** (*int*) - Maximum age of the cache in days. The default value is 365.
    * **query_cache_path** (*str*) - SQLite query cache, separate from entity Parquet files.
      Default: ~/openalex-analysis/query-cache.sqlite3.
    * **query_cache_enabled** (*bool*) - Enable QueryCache storage. Default: True.
    * **query_cache_mode** (*str*) - QueryCache mode: auto, refresh or offline. Default: auto.
    * **query_cache_ttl** (*float*) - Fixed cache duration in seconds for all queries. Default: 604800 (1 week).
      Freshness and cleanup use this setting with the stored retrieval date, including for existing entries.
    * **query_cache_stale_if_error** (*bool*) - Allow warned stale fallback on request or PyAlex query errors. Default: False.
    * **query_cache_max_entries** (*int*) - Maximum SQLite query rows. Default: 10000.
    * **query_cache_max_size_bytes** (*int*) - Maximum serialized query/result bytes. Default: 100 MB.
    * **query_cache_busy_timeout_ms** (*int*) - SQLite lock wait timeout. Default: 5000 milliseconds.
    * **log_level** (*str*) - The log detail level for openalex-analysis (library specific). The log_level must be
      'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'. The default value 'WARNING'.
    """
    def __getattr__(self, key):
        return super().__getitem__(key)


    def __setattr__(self, key, value):
        if key in pyalex_config.keys():
            pyalex_config.__setitem__(key, value)
        if key == "log_level":
            match value:
                case 'DEBUG':
                    log_oa.setLevel(logging.DEBUG)
                case 'INFO':
                    log_oa.setLevel(logging.INFO)
                case 'WARNING':
                    log_oa.setLevel(logging.WARNING)
                case 'ERROR':
                    log_oa.setLevel(logging.ERROR)
                case 'CRITICAL':
                    log_oa.setLevel(logging.CRITICAL)
                case _:
                    raise ValueError("The log_level must be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'")

        return super().__setitem__(key, value)


config = AnalysisConfig()


def set_default_config():
    """
    Set the default configuration of the library. This function is called to set the default values before loading an
    optional configuration file.
    """
    log_oa.info(f"Setting the default configuration")
    config.email = None
    config.api_key = os.environ.get("OPENALEX_API_KEY") or None
    config.openalex_url = "https://api.openalex.org"
    config.max_retries = 3
    config.retry_backoff_factor = 2
    config.retry_http_codes = [429, 500, 502, 503, 504]
    config.disable_tqdm_loading_bar = False
    config.n_max_entities = 10000
    config.project_data_folder_path = join(expanduser("~"), "openalex-analysis", "data")
    config.parquet_compression = "brotli"
    config.max_storage_percent = 95
    config.max_storage_files = 10000
    config.max_storage_size = 5e9
    config.min_storage_files = 1000
    config.min_storage_size = 5e8
    config.cache_max_age = 365
    config.query_cache_path = join(expanduser("~"), "openalex-analysis", "query-cache.sqlite3")
    config.query_cache_enabled = True
    config.query_cache_mode = 'auto'
    config.query_cache_ttl = 7 * 86400
    config.query_cache_stale_if_error = False
    config.query_cache_max_entries = 10000
    config.query_cache_max_size_bytes = 100_000_000
    config.query_cache_busy_timeout_ms = 5000
    config.log_level = 'WARNING'


def load_config_from_file(config_path: str):
    """
    Load and set the configration of the library from a .toml file.
    If the file doesn't exist, a warning is raised.
    If a value isn't specified in the configuration file, the default value is used (see set_default_config()).
    When the library is imported, if a configuration file exists at "~/openalex-analysis/openalex-analysis-conf.toml",
    it is automatically loaded.

    :param config_path: The path of the configuration file.
    :type config_path: str
    """
    set_default_config()

    if isfile(config_path):
        log_oa.info(f"Loading the configuration from the file {config_path}")
        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)
        set_parameters = ""
        for attribute, value in config_data.items():
            # only load parameters that are defined in set_default_config()
            if attribute in config.keys():
                set_parameters += attribute + ", "
                setattr(config, attribute, value)
        if len(set_parameters) > 0:
            log_oa.info(f"Loaded the following configuration parameters: {set_parameters[:-2]}.")
        else:
            warnings.warn(f"No configuration parameters were found in the configuration file.")
    else:
        warnings.warn(f"The configuration file {config_path} was not found. Default configuration set.")


# if the config file exist, load the configuration from it otherwise load the default configuration
if isfile(join(expanduser("~"), "openalex-analysis","openalex-analysis-conf.toml")):
    load_config_from_file(join(expanduser("~"), "openalex-analysis", "openalex-analysis-conf.toml"))
else:
    set_default_config()
