# Mobile PWA Dockerfile
FROM nginx:alpine

# Copy PWA files
COPY . /usr/share/nginx/html

# Copy nginx config for SPA routing and PWA headers
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]