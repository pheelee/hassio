# Rsync Backup

![Project Stage][project-stage-shield]
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE.md)

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]
![Supports i386 Architecture][i386-shield]
![Supports armv7 Architecture][armv7-shield]
![Supports armhf Architecture][armhf-shield]

![Project Maintenance][maintenance-shield]

Copy hass.io backups to remote rsync server

## About

This addon copies your hass.io backups to a remote rsync server and optionally deletes local backups

*Inspired by the addon rsync-backups from tykarol*

## Configuration
```yaml
server: 192.168.1.100
port: 22
directory: ~/backup-prod
rsync_args: '--rsync-path=/bin/rsync'
username: hassio
password: 'MySuperSecret123'
auto_purge: 0
```
*dont copy and paste this config, write your own!*

### Option: ```server```
The rsync server to connect to

### Option: ```port```
The port where the rsync server listens on

### Option: ```directory```
The remote directory where the backups are copied to. The directory tree (except the last node) already have to exist on the rsync server.

### Option: ```rsync_args```
Additional rsync arguments like `--rsync-path=/bin/rsync`

### Option: ```username```
The username used to connect to the rsync server

### Option: ```password```
The password used to connect to the rsync server

Can also be specified as `!secret rsync_password` (using the addon configuration yaml edit mode)

### Option: ```auto_purge```
Number of backups to preserve. If 0 is specified the cleanup is skipped

## Usage Scenario

This addon can be started from an automation to regularly transfer the backups to a remote location.

```yaml
alias: Backup Rsync
description: ''
trigger:
  - platform: time
    at: '01:00:00'
condition: []
action:
  - service: hassio.addon_start
    data:
      addon: local_rsync_backup # select the correct addon from the automations UI
mode: single
```

## License

MIT License

Copyright (c) 2021 Philipp Ritter

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[maintenance-shield]: https://img.shields.io/maintenance/yes/2021.svg
[project-stage-shield]: https://img.shields.io/badge/project%20stage-stable-green.svg
[repository]: https://github.com/pheelee/hassio