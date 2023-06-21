# OpenAlex Analysis

Scientific literature analysis using the OpenAlex API.

This repo provides classes and methods to extract statistics, plots and graphs, as well as examples in Jupyter Notebooks. There is also a web app built with Dash and some docker config files to deploy it.

To clone this repo: `git clone --recurse-submodules git@github.com:romain894/openalex-analysis.git`

Documentation (python library only): [https://romain894.github.io/openalex-analysis](https://romain894.github.io/openalex-analysis)

Licence: GPL V3

## TODO

  - Recode the cache enabling part and add option to set the Redis URL, port and DB
  - Add more examples in Readme and Jupyter Notebooks

# Setting up

## OpenAlex Analysis python library

By default, the library will run out of the box. Nevertheless, some optional configurations can be done to improve the performance and to fit best the use case.

### Settings

These settings needs to be given for each instance. For a more convienient usage, you can define these values in a dictionary and provide this dictionnary at the instanciation as follow:

```python
parameters = {
    'n_max_entities': 600,
    'project_datas_folder_path': "data",
}

concept_sustainability_id = 'C66204764'

wcp = WorksConceptsPlot(concept_sustainability_id, **parameters)

```

#### n_max_entities

When downloading a list of entities from the API (eg a list of works), the maximum number of entities to download. Set to None to have no limitation. This number must be a multiple of 200 (the is the number of element per page used by the library)

Default: `n_max_entities = 10 000`

#### project_datas_folder_path

Path to store the data downloaded from the API. The data will be stored as parquet files, with each file corresponding to one request.

Default: `project_datas_folder_path = "data"`


#### parquet_compression

By default, the parquet files are compressed. The compression can be disabled by setting with parquet_compression = None. For other parquet compression algorithms, see the pandas documentation.

Compressing reduces by 2 to 10 the file size while needing a negligeable time to compress or decompress. Disabling the compression is usefull if you want to read the parquet files with an external software.

Default: `parquet_compression = "brotli"`


#### max_storage_percent

Maximum storage usage percentage on the disk before starting to delete data stored in project_datas_folder_path. The parquet file with the oldest last read data will be deleted first.

Default: `max_storage_percent = 95`


#### disable_tqdm_loading_bar

If set to True, it will disable the loading bar in the terminal output when downloading data from the OpenAlex API.

Default: `disable_tqdm_loading_bar = False`


#### email

To use the polite pool of the OpenAlex API, you need to provide an email. By default, it's set to None so it will use the default pool and will be slower to do requests.

Default: `email = None`


#### enable_redis_cache

To enable the Redis cache. To enable it, you need to have a running instance of Redit (for example in a Docker), on the localhost (can be overide by the system environnement variable $DOCKER_REDIS_URL), on the port 6379 and with nothing else running on the database 2.


### Examples

TODO

## Analysis web app




Romain Thomas 2023