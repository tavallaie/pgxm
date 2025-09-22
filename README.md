# pgxm

**pgxm** (PostgreSQL eXtension Manager) is a powerful command-line tool designed to simplify the entire lifecycle of PostgreSQL extensions. Inspired by the innovative approach of [Trunk](https://pgt.dev), `pgxm` aims to provide a streamlined and efficient way to **build**, **publish**, and **install** PostgreSQL extensions.

**Please Note: This project is under active development. The features and usage instructions are subject to change.**

## Vision

Managing PostgreSQL extensions can be complex, involving various build systems, packaging formats, and distribution mechanisms. `pgxm` is being built to abstract away this complexity, offering a unified and user-friendly interface for extension developers and database administrators alike.

The goal is to make it incredibly easy to:
*   Package an extension developed in C, SQL, or using frameworks like PGRX (Rust).
*   Share your extension with the PostgreSQL community by publishing it to a central registry.
*   Discover and install extensions from the registry into your PostgreSQL instances with minimal effort.

## Key Features (Planned)

*   **`pgxm build`:** Compile and package PostgreSQL extensions from source.
    *   Supports various extension types (C/SQL, PGRX).
    *   Utilizes Docker containers for consistent and reproducible builds.
    *   Automatically discovers and packages essential files (`.so`, `.sql`, `.control`, licenses).
    *   Generates a standardized package artifact (`.tar.gz`) along with a `manifest.json`.
*   **`pgxm publish`:** Publish your packaged extension to a registry (e.g., compatible with `pgt.dev` or a self-hosted one).
    *   Simplifies sharing your extension with the world.
    *   Manages authentication and metadata upload.
*   **`pgxm install`:** Download and install extensions directly into your local PostgreSQL environment from the registry or a local package.
    *   Handles dependency resolution (planned).
    *   Automatically places files in the correct PostgreSQL directories.
    *   Provides clear post-installation instructions.

## Technology Stack

*   **Language:** Python
*   **Package Manager:** `uv` (for fast dependency management and project setup)
*   **CLI Framework:** `click`
*   **Containerization:** Docker (via `docker` Python SDK)

## Getting Started (Coming Soon)

Detailed installation and usage instructions will be provided here once the initial stable version is ready.

## Development Status

This project is currently in the **early development** phase. Core functionalities, especially `pgxm build`, are being actively implemented and tested.

## Contributing

As this is an early-stage project, contribution guidelines are still being formalized. Stay tuned for details on how you can get involved!


