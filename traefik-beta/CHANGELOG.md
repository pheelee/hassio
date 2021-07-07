## v0.5.2

### 🛠️ Fixes

 - Edit configuration after filtering works now

### 🔨 Changes

 - Assets are embedded in binary
 - Added unittests
 - Backend healthcheck with visual feedback in config overview
 - Use an ID instead of name allows the configs name to be changed
 - Allow dash in the name of a config
 - Code refactor

## v0.5.1

### 🛠️ Fixes

- fix webinterface startup error if no authEndpoint is specified
- add hosts entries

## v0.5.0

### 🔨 Changes

- add SSO using traefiks forward auth and the homeassistant auth api
- UI overhaul
- manually add hosts entries
- toast notifications

## v0.4.1

### 🛠️ Fixes
- support multiple root ca's from config

## v0.4.0

### 🔨 Changes

- add HSTS to configs
- add IP restriction to configs
- use dns as cert resolver
- bump traefik to 2.3.4