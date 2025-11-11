# openPDC

## Introduction
Alpine based docker image working as init container for [openPDC](../openpdc), specifically it creates a db user, granting access to a db schema, creates a db schema and populates it with the necessary initial data.
Optionally it can insert also a sample dataset.

### Caveats
Currently each init container creates a new user and db for each openpdc instance. It probably is not the proper way to use it though. A unique database should probably be used, with different users, one for each instance, so that admins can have an overview of configurations. A further development of this init container could be related to this logic: check if the database exists and create it if not, if it exists check if the user exists and if not create it.

## Configuration
The init container is configurable using environment variables descripted in the following table:

| env var | description |
|-|-|
| `DB_ROOTPASS` | MySQL root password, the whole init operation will be performed as root user in MySQL |
| `DB_USER` | Database user will be created and will be granted access to `DB_NAME` [default is `polito`] |
| `DB_PASS` | Database user's password [default is an empty string] |
| `DB_NAME` | Database name tied to the openPDC instance [default is `openPDC`] |
| `DB_PORT` | Port associated to the MySQL instance [default is `3306`]|
| `DB_URL` | URL of the MySQL instance [default is `localhost`] |
| `SAMPLE_DATASET` | If set to `true` a sample dataset is inserted [as default is not set] |

## Troubleshooting

The [init.sh](./init.sh) script is used to generate the sql files from the templates and run a mysql client to perform the creation and insertions. A dumb check on the existence of the MySQL instance and the database is initially performed to avoid runnning the init operation multiple times.
If any error occurs it should be present in the console output.