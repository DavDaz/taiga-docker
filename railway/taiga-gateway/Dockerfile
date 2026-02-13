FROM nginx:1.19-alpine
COPY taiga.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint-railway.sh /docker-entrypoint-railway.sh
RUN chmod +x /docker-entrypoint-railway.sh
ENTRYPOINT ["/docker-entrypoint-railway.sh"]
CMD ["nginx", "-g", "daemon off;"]
