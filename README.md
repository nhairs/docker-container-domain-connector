# DCDC: Docker Container Domain Connector

[![PyPi](https://img.shields.io/pypi/v/docker-container-domain-connector.svg)](https://pypi.python.org/pypi/docker-container-domain-connector/)
[![PyPI - Status](https://img.shields.io/pypi/status/docker-container-domain-connector)](https://pypi.python.org/pypi/docker-container-domain-connector/)
[![Python Versions](https://img.shields.io/pypi/pyversions/docker-container-domain-connector.svg)](https://github.com/nhairs/docker-container-domain-connector)
[![License](https://img.shields.io/github/license/nhairs/docker-container-domain-connector.svg)](https://github.com/nhairs/docker-container-domain-connector)

DCDC provides a local DNS server for exposing docker containers on bridge networks.

This allows you to easily reference containers by name instead of exposing and binding IP addresses / ports on the localhost. Names are in the form of `container-name.compose-project-name.dcdc`

```console
% dig mysql.my-project.dcdc

; <<>> DiG 9.18.18-0ubuntu0.22.04.2-Ubuntu <<>> mysql.my-project.dcdc
;; global options: +cmd
;; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 59483
;; flags: qr rd ra; QUERY: 1, ANSWER: 1, AUTHORITY: 0, ADDITIONAL: 1

;; OPT PSEUDOSECTION:
; EDNS: version: 0, flags:; udp: 65494
;; QUESTION SECTION:
;mysql.my-project.dcdc.	IN	A

;; ANSWER SECTION:
mysql.my-project.dcdc. 51	IN	A	192.168.144.3

;; Query time: 0 msec
;; SERVER: 127.0.0.53#53(127.0.0.53) (UDP)
;; WHEN: Fri May 10 20:56:11 AEST 2024
;; MSG SIZE  rcvd: 71
```

## Setup

### Install DCDC

```shell
# TODO: upload to pypi
pip install docker-container-domain-conenctor
```

### Configure `systemd-resolved`

Edit `/etc/systemd/resolved.conf`

```conf
[Resolve]
DNS=127.0.0.1:9953#dcdc
```

### Run DCDC

```shell
dcdc
```

### Restart `systemd-resolved`

```shell
sudo systemctl restart systemd-resolved
```

### Test

```shell
dig some.container.dcdc
```

## Usage

The main application is provided by the `dcdc` command.

```
usage: dcdc [-h] [-v] [--log-dir PATH] [--version] [--host HOST] [--port PORT] [--tcp | --udp]
            [--root-domain ROOT_DOMAIN]

dcdc (Docker Container Domain Connector) is a dns server that allows mapping docker containers to their currently running bridge ip address.

options:
  -h, --help            show this help message and exit
  -v, --verbose         Increase logging verbosity
  --log-dir PATH        Set where log files should be stored. Defaults to /var/tmp
  --version             show program's version number and exit
  --host HOST           Host (IP) to bind to. Use --ips to see available. Defaults to localhost.
  --port PORT           Port to bind to. Defaults to 9953.
  --tcp                 Use TCPv4 socket for transport.
  --udp                 Use UDPv4 socket for transport. (default)
  --root-domain ROOT_DOMAIN
                        Root domain for queries (e.g. <query>.<root>). Does not have to be a TLD, can
                        be any level of domain. Defaults to ".dcdc".
```

This package also provies the `dcdc-ips` utility command which will print available IP addresses.

## Licence
This project is licenced under the MIT Licence - see [`LICENCE`](https://github.com/nhairs/docker-container-domain-connector/blob/main/LICENCE).


## Authors
A project by Nicholas Hairs - [www.nicholashairs.com](https://www.nicholashairs.com).
