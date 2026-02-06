#!/bin/sh
# Set eventsUrl to null in conf.json to disable WebSocket connections
sed -i 's|"eventsUrl":.*|"eventsUrl": null,|' /usr/share/nginx/html/conf.json
echo "Events disabled in conf.json"
