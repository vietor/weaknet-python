#!/bin/bash

echo "........socks4........"
curl --socks4 127.0.0.1:51080 -I http://www.apple.com
echo "........socks4a........"
curl --socks4a 127.0.0.1:51080 -I http://www.apple.com
echo "........socks5........"
curl --socks5 127.0.0.1:51080 -I http://www.apple.com
echo "........socks5h........"
curl --socks5-hostname 127.0.0.1:51080 -I http://www.apple.com
echo "........proxy........"
curl --proxy 127.0.0.1:51080 -I http://www.apple.com
echo "........connect........"
curl --proxy 127.0.0.1:51080 --proxytunnel -I http://www.apple.com
