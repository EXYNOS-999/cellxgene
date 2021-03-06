# Developer guidelines

### Requirements
- npm
- Python 3.6+
- Chrome

[See dev section of README](../README.md)

**All instructions are expected to be run from the top level cellxgene directory unless otherwise specified.**

### Environment

For all `make` commands, `common.mk` automatically checks whether required environment variables are set and, if they are not set, assigns them default values from `environment.default`.

You can set these environment variables manually with the `export` shell command, as in `export JEST_ENV=debug`.

## Running test suite
Client and server tests run on Travis CI for every push, PR, and commit to master on github. End to end tests run nightly on master only. 

### Unit tests
Steps to run the all unit tests:
1. Start in the project root directory
1. `make dev-env`
1. `make unit-test`

To run unit tests for the `client` code only:
1. Start in the project root directory
1. `cd client`
1. `make unit-test`

### End to end tests

To run E2E tests, run `cd client` and `make smoke-test`

The `JEST_ENV` environment variable enables the following E2E test options:
* `dev` - opens chromimum, runs tests with minimal slowdown, close on exit.
* `debug` - opens chromium, runs tests with 100ms slowdown, dev tools open, chrome stays open on exit.
* `prod` - run headless with no slowdown, chromium will not open.

Run end to end tests interactively during development
1. cellxgene should be installed as [specified in client dev](#install-1)
1. Follow [launch](#launch-1) instructions for client dev with dataset `example-dataset/pbmc3k`
1. Run `npm run e2e` or `make e2e` from the `client` directory
1. To debug a failing test `export JEST_ENV='debug'` and re-run.

To run end to end tests _exactly_ as they will be run on CI use the following command:
```
JEST_ENV=prod make pydist install-dist dev-env smoke-test
```

## Server dev
### Install
* Build the client and put static files in place: `make build-for-server-dev`
* Install from local files: `make install-dev`

### Launch
* `cellxgene launch [options] <datafile>`

### Reloading
If you install cellxgene using `make install-dev` the server will be restarted every time you make changes on the server code. If changes affects the client, the browser must be reloaded.

### Linter

We use [`flake8`](https://github.com/PyCQA/flake8) to lint python and [`black`](https://pypi.org/project/black/) for auto-formatting.

To auto-format code run `make fmt`. To run lint checks on the code run `make lint`.

### Test
If you would like to run the server tests individually, follow the steps below
1. Install development requirements `make dev-env`
1. Run `make unit-test` in the `server` directory or `make unit-test-server` in the root directory.

### Tips
* Install in a virtualenv
* May need to rebuild/reinstall when you make client changes

## Client dev
### Install
1. Install prereqs for client: `make dev-env`
2. Install cellxgene server: `make install-dev` Caveat: this will not build the production client package - you must use the [server install](#install) instructions above to serve web assets.

### Launch
To launch with hot reloading you need to launch the server and the client separately. Node's hot reloading starts the client on its own node server and auto-refreshes when changes are made.
1. Launch server (the client relies on the REST API being available): `cellxgene launch [options] <datafile>`
2. Launch client: in `client/` directory run `npm run start`
3. Client will be served on localhost:3000

### Build
To build only the client: `make build-client`

### Linter
We use `eslint` to lint the code and `prettier` as our code formatter.

### Test

If you would like to run the client tests individually, follow the steps below in the `client` directory
1. For unit tests run `npm run unit-test` or `make unit-test`
1. For the smoke test run `npm run smoke-test` or `make smoke-test`

### Tips
* You can also install/launch the server side code from npm scrips (requires python3.6 with virtualenv) in `client/` directory run `npm run backend-dev`


