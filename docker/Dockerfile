ARG BUILD
ARG BUILD_DATE
ARG GITHUB_SHA

FROM python:3.13-slim-bookworm AS base

FROM base AS builder
ARG BUILD_DATE

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
    curl \
    tar \
    build-essential; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*


COPY /app/ /build/app/

RUN chmod +x /build/app/run

RUN --mount=type=cache,target=/root/.cache/pip \
    set -eux; pip3 install --disable-pip-version-check --prefix=/build/usr/local -r /build/app/requirements.txt

RUN set -eux; \
    echo "BUILDING IMAGE FOR $(uname -m) (go2rtc WebRTC-to-RTSP Bridge)";\
    if [ "$(uname -m)" = "armv7l" ]; then \
    FFMPEG_ARCH=arm32v7; GO2RTC_ARCH=arm; \
    elif [ "$(uname -m)" = "aarch64" ]; then \
    FFMPEG_ARCH=aarch64; GO2RTC_ARCH=arm64; \
    else \
    FFMPEG_ARCH=x86_64; GO2RTC_ARCH=amd64; \
    fi; \
    cd /build; \
    . app/.env; \
    mkdir -p tokens; \
    curl -fsSL https://github.com/homebridge/ffmpeg-for-homebridge/releases/latest/download/ffmpeg-alpine-${FFMPEG_ARCH}.tar.gz -o ffmpeg.tar.gz; \
    tar tzf ffmpeg.tar.gz || (echo "Invalid ffmpeg tarball for ${FFMPEG_ARCH}" && exit 1); \
    tar xzf ffmpeg.tar.gz -C . ;\
    rm ffmpeg.tar.gz; \
    GO2RTC_VERSION="1.9.4"; \
    curl -fsSL https://github.com/AlexxIT/go2rtc/releases/download/v${GO2RTC_VERSION}/go2rtc_linux_${GO2RTC_ARCH} -o app/go2rtc; \
    chmod +x app/go2rtc; \
    rm -rf app/*.txt; \
    echo "BUILD_DATE=${BUILD_DATE:-$(date)}" > .build_date;


FROM base
ARG BUILD
ARG GITHUB_SHA
ARG BUILD_DATE
ARG BUILD_VERSION

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    ; \
    rm -rf /var/log/*.log ; \
    rm -rf /var/log/apt ; \
    rm -rf /var/lib/apt/lists/*


COPY --from=builder /build /

ENV PYTHONUNBUFFERED=1 FLASK_APP=frontend BUILD=$BUILD BUILD_VERSION=$BUILD_VERSION BUILD_DATE=$BUILD_DATE GITHUB_SHA=$GITHUB_SHA FLASK_ENV=production FLASK_DEBUG=0
WORKDIR /app
ENTRYPOINT [ "/app/run" ]

LABEL \
    io.hass.name="Docker Wyze Bridge for Home Assistant (WebRTC-to-RTSP)" \
    io.hass.description="Bridges Wyze Cameras to RTSP/HLS via KVS WebRTC for Home Assistant" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    maintainer="akeslo" \
    org.label-schema.name="Docker Wyze Bridge HA (WebRTC-to-RTSP)" \
    org.label-schema.description="Docker Wyze Bridge providing RTSP streams via KVS WebRTC and MediaMTX" \
    org.label-schema.build-date=${BUILD_DATE} \
    org.label-schema.schema-version="1.0" \
    org.label-schema.usage="https://github.com/akeslo/docker-wyze-bridge/blob/main/README.md" \
    org.label-schema.vcs-ref=${GITHUB_SHA} \
    org.label-schema.vcs-url="https://github.com/akeslo/docker-wyze-bridge/" \
    org.label-schema.vendor="akeslo"