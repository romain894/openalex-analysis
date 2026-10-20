# Tests directory

From the repository root:

```bash
make install-dev
make test
```

`make test` runs both the mocked tests and the existing live API tests in `tests.py`.

To run either suite separately:
```bash
make test-unit
make test-live
```

The live suite uses a temporary cache and caps downloads at 200 entities per query.
Set `OPENALEX_API_KEY` to an activated key for authenticated requests, including subsequent cursor pages.
