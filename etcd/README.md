# Etcd Addon

![](https://img.shields.io/badge/amd64-supported-brightgreen?style=flat-square)
![](https://img.shields.io/badge/arm64-experimental-orange?style=flat-square)
![](https://img.shields.io/badge/armv7-experimental-orange?style=flat-square)


This addon bundles the key-value store etcd with a web interface.

etcd is a distributed reliable key-value store for the most critical data of a distributed system, with a focus on being:

* *Simple*: well-defined, user-facing API (gRPC)
* *Secure*: automatic TLS with optional client cert authentication
* *Fast*: benchmarked 10,000 writes/sec
* *Reliable*: properly distributed using Raft

etcd is written in Go and uses the raft consensus algorithm to manage a highly-available replicated log.

![](https://github.com/evildecay/etcdkeeper/raw/master/screenshots/ui.gif)