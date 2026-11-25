FROM python:3.12-slim
WORKDIR /app
COPY breakcheck /app/breakcheck
COPY LICENSE /app/LICENSE
RUN mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8765
ENTRYPOINT ["python","-m","breakcheck","fleet-server","--host","0.0.0.0","--trusted-proxy","--db","/data/fleet.sqlite3"]
