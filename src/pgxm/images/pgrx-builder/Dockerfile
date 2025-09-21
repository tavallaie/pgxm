ARG PG_VERSION=15
FROM ghcr.io/tavallaie/pgxm/c-builder:pg${PG_VERSION}
ARG PG_VERSION=15

ENV CARGO_REGISTRIES_CRATES_IO_PROTOCOL=sparse

# Install Rust 
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/var/lib/postgresql/.cargo/bin:${PATH}"

# Install pgrx 
ARG PGRX_VERSION=0.8.2
RUN set -ex; \
    cargo --version && \
    cargo install cargo-pgrx --version "${PGRX_VERSION}" --locked; \
    cargo pgrx init --pg${PG_VERSION} /usr/bin/pg_config

USER postgres
WORKDIR /app