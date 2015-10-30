pysunday
========

Some python code for fucking world

# Usage

```sh
python weaknet.py --help
```

## Role: remote

A modifyed socket proxy server, compatible *shadowsocks* protocol.
> default bind port: 51080

## Role: local

A wrappered proxy server, multiple protocal support.
> default bind port 51080  
> Add -S for direct usage *shadowsocks* server.

### SOCKS4
Direct usage.

### SOCKS4A
Direct usage.

### SOCKS5
Direct usage. Unsupoort authentication.

### HTTP PROXY
Direct usage. Unsupoort authentication.

### AUTO PROXY
Usage "http://<bind ip>:<bind port>/proxy.pac". Unsupoort authentication.


