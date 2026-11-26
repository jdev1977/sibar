Save this as `.github/workflows/ci.yml`:

```yaml
name: CI
on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ${{ matrix.os }}
    timeout-minutes: 10
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        go: ["1.25.x", "1.24.x"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: ${{ matrix.go }}
      - run: gofmt -l .
      - run: go vet ./...
      - run: go test -race -coverprofile=cover.out ./...
```
