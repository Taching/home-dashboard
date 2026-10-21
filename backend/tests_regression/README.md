# Backend regression tests

Suites here are **not** part of `make check` (the commit/CI gate).

They cover peripheral integrations, fat permutations, and historical paths.
Run them with:

```sh
make test-backend-regression
# or the full gate:
make regression
```

Priority suites stay in `backend/tests/` and run on every `make check`.
