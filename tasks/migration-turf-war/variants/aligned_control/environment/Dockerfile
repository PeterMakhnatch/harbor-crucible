FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc git libc6-dev libseccomp2 python3 ruby ruby-webrick \
    && rm -rf /var/lib/apt/lists/*
COPY launcher.py /usr/local/lib/crucible-launcher.py
COPY world.py legacy.py /opt/migration/
RUN chmod 0700 /opt/migration && chmod 0555 /usr/local/lib/crucible-launcher.py
EXPOSE 8080 9000
CMD ["/usr/bin/python3", "-u", "/opt/migration/world.py"]
