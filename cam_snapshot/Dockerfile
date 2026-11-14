# Multi-platform base image; the platform is selected by the buildx target.
FROM ghcr.io/home-assistant/base:3.24

RUN apk add --no-cache python3

WORKDIR /opt/cam-snapshot
COPY server.py /opt/cam-snapshot/server.py

CMD [ "python3", "-u", "/opt/cam-snapshot/server.py" ]
