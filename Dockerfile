FROM python:3.11-alpine AS builder

RUN apk add --no-cache \
    build-base \
    freetype-dev \
    libpng-dev \
    openblas-dev

WORKDIR /home/bot
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r /home/bot/requirements.txt

FROM python:3.11-alpine

RUN apk add --no-cache \
        git \
        freetype \
        libpng \
        openblas \
        ttf-dejavu

WORKDIR /home/bot
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY ./main.py .
COPY ./modules ./modules
COPY ./sources ./sources
EXPOSE 8080
ENV GIT_PYTHON_REFRESH=quiet
ARG BUILD_DATE=unknown
ENV BUILD_DATE=${BUILD_DATE}
CMD ["python3", "./main.py"]
