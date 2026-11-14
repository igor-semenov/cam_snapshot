ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3

WORKDIR /opt/cam-snapshot
COPY server.py /opt/cam-snapshot/server.py

CMD [ "python3", "-u", "/opt/cam-snapshot/server.py" ]
