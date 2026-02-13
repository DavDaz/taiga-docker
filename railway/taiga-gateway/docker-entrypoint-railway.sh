#!/bin/sh
set -e
# Read the first nameserver from /etc/resolv.conf
NS=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf)
# nginx requires IPv6 addresses in brackets: [fd12::10]
case "$NS" in
    *:*) NGINX_RESOLVER="[$NS]" ;;
    *)   NGINX_RESOLVER="$NS" ;;
esac
export NGINX_RESOLVER
exec /docker-entrypoint.sh "$@"
