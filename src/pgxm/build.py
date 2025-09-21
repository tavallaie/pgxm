# pgxm/build.py
"""Core logic for building PostgreSQL extensions using Docker (OOP version)."""

import os

import logging
import tarfile
import tempfile
import json
import click
from pathlib import Path
from typing import List, Optional, Tuple, Set

# --- Import Docker Helpers ---
from .helpers import docker_helpers
import docker

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_PG_VERSION = "15"
DEFAULT_OUTPUT_DIR_NAME = ".pgxm"
MANIFEST_FILENAME = "manifest.json"


class PgxmBuilderError(Exception):
    """Base exception for PgxmBuilder errors."""

    pass


class PgxmBuilderConfigError(PgxmBuilderError):
    """Error related to builder configuration."""

    pass


class PgxmBuilderDockerError(PgxmBuilderError):
    """Error related to Docker operations."""

    pass


class PgxmBuilder:
    """
    Class responsible for building PostgreSQL extensions using Docker.
    """

    def __init__(self, **kwargs):
        """
        Initializes the PgxmBuilder with build options.

        Args:
            **kwargs: Build options matching the CLI arguments.
                path (str): Path to the extension source.
                output_path (str): Directory to place the built package.
                version (str): Override extension version.
                name (str): Override extension name.
                extension_name (str): Alias/override for extension name.
                extension_dependencies (str): Comma-separated dependencies.
                preload_libraries (str): Comma-separated preload libraries.
                platform (str): Target platform.
                dockerfile (str): Path to custom Dockerfile.
                install_command (str): Custom install command.
                test (bool): Whether to run tests.
                pg_version (str): Target PostgreSQL version.
        """
        self.options = kwargs
        self.extension_path: Optional[Path] = None
        self.output_dir: Optional[Path] = None
        self.control_file_path: Optional[Path] = None
        self.control_data: dict = {}
        self.final_name: str = ""
        self.final_version: str = ""
        self.dockerfile_path_obj: Optional[Path] = None
        self.final_install_command: str = ""
        self.docker_client: Optional[docker.DockerClient] = None
        self.image_id: Optional[str] = None
        self.container_id: Optional[str] = None
        self._validated = False

    def _resolve_paths(self):
        """Step 1: Resolve input and output paths."""
        path = self.options.get("path", ".")
        self.extension_path = Path(path).resolve()
        if not self.extension_path.exists():
            raise PgxmBuilderConfigError(
                f"Extension path does not exist: {self.extension_path}"
            )

        output_path = self.options.get("output_path")
        if output_path:
            self.output_dir = Path(output_path).resolve()
        else:
            self.output_dir = self.extension_path / DEFAULT_OUTPUT_DIR_NAME
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {self.output_dir}")

    def _read_control_file(self):
        """Step 2: Read the extension's .control file."""
        if not self.extension_path:
            raise PgxmBuilderError(
                "Paths must be resolved before reading control file."
            )

        try:
            self.control_file_path = self._find_control_file(self.extension_path)
            self.control_data = self._read_control_file_data(self.control_file_path)
        except FileNotFoundError as e:
            raise PgxmBuilderConfigError(str(e))

    def _find_control_file(self, extension_path: Path) -> Path:
        """Helper to find the .control file."""
        control_file = None
        potential_paths = [extension_path / "extension", extension_path]
        for p in potential_paths:
            if p.is_dir():
                for item in p.iterdir():
                    if item.is_file() and item.suffix == ".control":
                        if control_file:
                            logger.warning(
                                f"Multiple .control files found, using {item}"
                            )
                        control_file = item
        if not control_file:
            raise FileNotFoundError(
                f"No .control file found in {extension_path} or {extension_path / 'extension'}"
            )
        logger.debug(f"Found control file: {control_file}")
        return control_file

    def _read_control_file_data(self, control_path: Path) -> dict:
        """Helper to read .control file data."""
        control_data = {}
        try:
            with open(control_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        control_data[key.strip()] = value.strip().strip("'\"")
        except Exception as e:
            logger.error(f"Error reading control file {control_path}: {e}")
            raise
        logger.debug(f"Control file data: {control_data}")
        return control_data

    def _determine_name_and_version(self):
        """Step 3: Determine final name and version."""
        if not self.control_data:
            raise PgxmBuilderError(
                "Control file must be read before determining name/version."
            )

        override_name = self.options.get("extension_name") or self.options.get("name")
        self.final_name = (
            override_name
            or self.control_data.get("module_pathname", "").split("/")[-1]
            or self.control_data.get("comment", "unknown-extension").split()[0]
            or "unknown-extension"
        )

        override_version = self.options.get("version")
        self.final_version = (
            override_version
            or self.control_data.get("default_version")
            or "0.0.1"  # Default fallback
        )
        logger.info(f"Building with name: {self.final_name}")
        logger.info(f"Building with version: {self.final_version}")
        pg_version = self.options.get("pg_version", DEFAULT_PG_VERSION)
        logger.info(f"Building for PostgreSQL: {pg_version}")

    def _locate_dockerfile(self):
        """Step 4: Locate the Dockerfile."""
        if not self.extension_path:
            raise PgxmBuilderError("Paths must be resolved before locating Dockerfile.")

        dockerfile_opt = self.options.get("dockerfile")
        if dockerfile_opt and Path(dockerfile_opt).exists():
            self.dockerfile_path_obj = Path(dockerfile_opt)
        elif (self.extension_path / "Dockerfile").exists():
            self.dockerfile_path_obj = self.extension_path / "Dockerfile"
        else:
            raise PgxmBuilderConfigError(
                "No Dockerfile found. pgxm currently only supports Docker-based builds."
            )

        logger.info(f"Using Dockerfile at: {self.dockerfile_path_obj}")

    def _determine_install_command(self):
        """Step 5: Determine the install command."""
        install_cmd_opt = self.options.get("install_command")
        if install_cmd_opt:
            self.final_install_command = install_cmd_opt
        elif self.extension_path and (self.extension_path / "Makefile").exists():
            self.final_install_command = "make install"
        else:
            self.final_install_command = (
                "echo 'No standard install command found. Please specify with -i.'"
            )
        logger.info(f"Determined install command: {self.final_install_command}")

    def _validate(self):
        """Performs initial validation and setup of key attributes."""
        if not self._validated:
            self._resolve_paths()
            self._read_control_file()
            self._determine_name_and_version()
            self._locate_dockerfile()
            self._determine_install_command()
            self._validated = True

    def _connect_to_docker(self):
        """Connects to the Docker daemon."""
        try:
            self.docker_client = docker_helpers.get_docker_client()
        except Exception as e:
            raise PgxmBuilderDockerError(f"Failed to connect to Docker: {e}") from e

    def _build_docker_image(self):
        """Builds the Docker image for the extension."""
        if (
            not self.docker_client
            or not self.dockerfile_path_obj
            or not self.extension_path
        ):
            raise PgxmBuilderError(
                "Docker client, Dockerfile path, and extension path must be set."
            )

        pg_version = self.options.get("pg_version", DEFAULT_PG_VERSION)
        build_args = {
            "EXTENSION_NAME": self.final_name,
            "EXTENSION_VERSION": self.final_version,
            "PG_VERSION": pg_version,
        }
        image_tag = f"pgxm_build_{self.final_name}_{self.final_version}_{os.getpid()}"
        try:
            self.image_id = docker_helpers.build_image(
                client=self.docker_client,
                dockerfile_path=self.dockerfile_path_obj,
                path_context=self.extension_path,
                tag=image_tag,
                build_args=build_args,
                platform=self.options.get("platform"),
            )
            logger.info(
                f"Docker image built successfully with ID: {self.image_id[:12]}"
            )
        except Exception as e:
            raise PgxmBuilderDockerError(f"Failed to build Docker image: {e}") from e

    def _run_docker_container(self):
        """Runs a temporary Docker container."""
        if not self.docker_client or not self.image_id:
            raise PgxmBuilderError("Docker client and image ID must be set.")

        try:
            # Use 'sleep infinity' to keep container alive
            container_sleep_cmd = ["sleep", "infinity"]
            temp_container = docker_helpers.run_temporary_container(
                client=self.docker_client,
                image_id=self.image_id,
                command=container_sleep_cmd,
                platform=self.options.get("platform"),
            )
            self.container_id = temp_container.id
            logger.info(
                f"Temporary container started with ID: {self.container_id[:12]}"
            )
        except Exception as e:
            raise PgxmBuilderDockerError(f"Failed to run Docker container: {e}") from e

    def _run_tests(self):
        """Runs tests inside the Docker container if requested."""
        if not self.docker_client or not self.container_id:
            raise PgxmBuilderError("Docker client and container ID must be set.")
        if not self.options.get("test"):
            logger.debug("Testing not requested, skipping.")
            return

        logger.info("Running tests...")
        try:
            makefile_path = docker_helpers.locate_makefile(
                self.docker_client, self.container_id
            )
            if not makefile_path:
                logger.info("Makefile not found, skipping test execution.")
                click.echo("Makefile not found, skipping tests.")
                return

            # Check for 'installcheck' (requires install + Postgres)
            if docker_helpers.makefile_contains_target(
                self.docker_client, self.container_id, makefile_path, "installcheck"
            ):
                logger.info("Found 'installcheck' target in Makefile.")
                click.echo("Running 'make install' before 'installcheck'...")
                install_stdout, install_stderr, install_exit_code = (
                    docker_helpers.exec_in_container(
                        self.docker_client,
                        self.container_id,
                        ["make", "install"],
                        workdir=os.path.dirname(makefile_path),
                    )
                )
                if install_exit_code != 0:
                    logger.error(
                        f"'make install' failed. Exit code: {install_exit_code}"
                    )
                    raise PgxmBuilderDockerError(
                        "'make install' failed before 'installcheck'."
                    )

                click.echo("Attempting to start Postgres for 'installcheck'...")
                docker_helpers.start_postgres(
                    self.docker_client, self.container_id
                )  # Log result inside helper

                click.echo("Running 'make installcheck'...")
                test_stdout, test_stderr, test_exit_code = (
                    docker_helpers.exec_in_container(
                        self.docker_client,
                        self.container_id,
                        ["make", "installcheck"],
                        workdir=os.path.dirname(makefile_path),
                        environment=["PGUSER=postgres"],
                    )
                )
                if test_exit_code == 0:
                    logger.info("'make installcheck' passed.")
                    click.echo("Tests (installcheck) passed successfully!")
                else:
                    logger.error(
                        f"'make installcheck' failed. Exit code: {test_exit_code}"
                    )
                    raise PgxmBuilderDockerError("Tests (installcheck) failed.")

            # Check for 'check'
            elif docker_helpers.makefile_contains_target(
                self.docker_client, self.container_id, makefile_path, "check"
            ):
                logger.info("Found 'check' target in Makefile.")
                click.echo("Attempting to start Postgres for 'check'...")
                docker_helpers.start_postgres(self.docker_client, self.container_id)

                click.echo("Running 'make check'...")
                test_stdout, test_stderr, test_exit_code = (
                    docker_helpers.exec_in_container(
                        self.docker_client,
                        self.container_id,
                        ["make", "check"],
                        workdir=os.path.dirname(makefile_path),
                        environment=["PGUSER=postgres"],
                    )
                )
                if test_exit_code == 0:
                    logger.info("'make check' passed.")
                    click.echo("Tests (check) passed successfully!")
                else:
                    logger.error(f"'make check' failed. Exit code: {test_exit_code}")
                    raise PgxmBuilderDockerError("Tests (check) failed.")
            else:
                logger.info("No standard test target found.")
                click.echo(
                    "No standard test target ('check' or 'installcheck') found in Makefile."
                )

        except Exception as e:
            # Catch errors from helper functions and re-raise as Builder error
            raise PgxmBuilderDockerError(f"Error during test execution: {e}") from e

    def _execute_install_command(self):
        """Executes the main install command inside the container."""
        if (
            not self.docker_client
            or not self.container_id
            or not self.final_install_command
        ):
            raise PgxmBuilderError(
                "Docker client, container ID, and install command must be set."
            )

        logger.info(f"Executing installation command: {self.final_install_command}")
        try:
            install_cmd_parts = self.final_install_command.split()
            install_stdout, install_stderr, install_exit_code = (
                docker_helpers.exec_in_container(
                    self.docker_client, self.container_id, install_cmd_parts
                )
            )
            if install_exit_code != 0:
                logger.error(f"Install command failed. Exit code: {install_exit_code}")
                raise PgxmBuilderDockerError(
                    f"Install command failed: {self.final_install_command}"
                )
            logger.info("Install command executed successfully.")
        except Exception as e:
            raise PgxmBuilderDockerError(f"Error executing install command: {e}") from e

    def _discover_and_collect_files(
        self, temp_package_dir: Path
    ) -> List[Tuple[Path, str]]:
        """
        Discovers changed files using docker diff and collects them, including licenses.

        Args:
            temp_package_dir: The temporary directory on the host to collect files.

        Returns:
            A list of tuples (host_path, archive_path) for all collected files.
        """
        if not self.docker_client or not self.container_id:
            raise PgxmBuilderError("Docker client and container ID must be set.")

        all_collected_files_info = []

        # --- Discover Changed Files ---
        logger.info("Discovering changed files using 'docker diff'...")
        try:
            changed_file_paths: Set[str] = docker_helpers.get_changed_files(
                self.docker_client, self.container_id
            )
            if not changed_file_paths:
                logger.warning(
                    "No changed files detected by 'docker diff'. The package might be empty."
                )
                # Depending on policy, could raise an error here
        except Exception as e:
            raise PgxmBuilderDockerError(f"Error discovering changed files: {e}") from e

        # --- Copy Changed Files ---
        if changed_file_paths:
            logger.info("Copying changed files identified by 'docker diff'...")
            try:
                copied_main_files_info = docker_helpers.copy_files_from_container(
                    self.docker_client,
                    self.container_id,
                    changed_file_paths,
                    temp_package_dir,
                )
                all_collected_files_info.extend(copied_main_files_info)
            except Exception as e:
                raise PgxmBuilderDockerError(f"Error copying changed files: {e}") from e

        # --- Find and Copy License Files ---
        logger.info("Searching for license files...")
        try:
            license_paths: List[str] = docker_helpers.find_licenses(
                self.docker_client, self.container_id
            )
            if license_paths:
                logger.info("Copying license files...")
                # copy_licenses returns instructions: (container_path, archive_path)
                license_copy_instructions = docker_helpers.copy_licenses(
                    license_paths, self.container_id, self.docker_client
                )
                # Extract license files based on instructions
                license_container_paths = [
                    instr[0] for instr in license_copy_instructions
                ]
                copied_license_files_info = docker_helpers.copy_files_from_container(
                    self.docker_client,
                    self.container_id,
                    set(license_container_paths),
                    temp_package_dir,
                )
                # Adjust paths for archive placement (licenses/ subdirectory)
                # The helper `copy_licenses` gives us the intended archive path (e.g., 'licenses/LICENSE')
                # We need to map the copied host files to these intended archive paths.
                # A simple way: assume copied license files need to go under 'licenses/' in the archive.
                # Refine if needed based on exact structure from `copy_licenses`.
                for host_path, container_rel_path in copied_license_files_info:
                    # Derive archive path: 'licenses/<original_filename>'
                    # This assumes `copy_files_from_container` puts it relative to temp_package_dir
                    # and we want it in 'licenses/' inside the final tar.
                    archive_path = f"licenses/{host_path.name}"
                    all_collected_files_info.append((host_path, archive_path))

            else:
                logger.info("No license files found.")
        except Exception as e:
            logger.warning(f"Error handling license files: {e}. Continuing build.")
            # Not fatal, continue

        return all_collected_files_info

    def _create_manifest(self, temp_dir: Path) -> Path:
        """Creates the manifest.json file."""
        pg_version = self.options.get("pg_version", DEFAULT_PG_VERSION)
        deps_str = self.options.get("extension_dependencies", "")
        libs_str = self.options.get("preload_libraries", "")

        manifest_data = {
            "name": self.final_name,
            "version": self.final_version,
            "pg_version": pg_version,
            "description": self.control_data.get(
                "comment", f"Built by pgxm from {self.extension_path.name}"
            ),
            "dependencies": [d.strip() for d in deps_str.split(",") if d.strip()],
            "preload_libraries": [
                lib.strip() for lib in libs_str.split(",") if lib.strip()
            ],
        }
        manifest_path = temp_dir / MANIFEST_FILENAME
        try:
            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f, indent=2)
            logger.debug(f"Created manifest at {manifest_path}")
        except Exception as e:
            raise PgxmBuilderError(f"Failed to create manifest: {e}") from e
        return manifest_path

    def _package_files(
        self, collected_files_info: List[Tuple[Path, str]], manifest_path: Path
    ):
        """Creates the final .tar.gz package."""
        if not self.output_dir:
            raise PgxmBuilderError("Output directory must be set.")
        pg_version = self.options.get("pg_version", DEFAULT_PG_VERSION)
        package_filename = (
            f"{self.final_name}-{self.final_version}-pg{pg_version}.tar.gz"
        )
        package_path = self.output_dir / package_filename

        logger.info(f"Creating final package at: {package_path}")

        # Add manifest to the list of files to package
        # collected_files_info contains (host_path, archive_path)
        # manifest_path is on the host, its archive path should be just the filename
        collected_files_info.append((manifest_path, MANIFEST_FILENAME))

        try:
            with tarfile.open(package_path, "w:gz") as tar:
                added_paths = set()
                for host_path, archive_path in collected_files_info:
                    # Normalize archive path separators
                    archive_path = archive_path.replace("\\", "/")
                    if host_path.exists() and archive_path not in added_paths:
                        tar.add(host_path, arcname=archive_path)
                        added_paths.add(archive_path)
                        logger.debug(f"Added to package: {archive_path}")
                    elif not host_path.exists():
                        logger.warning(
                            f"File not found, skipping in package: {host_path}"
                        )
                    else:
                        logger.debug(
                            f"Skipping duplicate file in package: {archive_path}"
                        )

            logger.info(f"Packaged successfully to {package_path}")
            click.echo(f"Packaged to {package_path}")

        except Exception as e:
            raise PgxmBuilderError(f"Failed to create package archive: {e}") from e

    def build(self):
        """
        Executes the complete build process.
        """
        logger.info("Starting pgxm build process (OOP version)...")
        try:
            # --- Validation & Setup ---
            self._validate()
            self._connect_to_docker()

            # --- Docker Build & Run ---
            self._build_docker_image()
            self._run_docker_container()  # Sets self.container_id

            # --- Inside Container Execution ---
            self._run_tests()  # Run tests if requested
            self._execute_install_command()  # Run main install command

            # --- Post-Install File Handling ---
            # Create a temporary directory to collect all files for the package
            with tempfile.TemporaryDirectory() as temp_package_dir_str:
                temp_package_dir = Path(temp_package_dir_str)
                logger.debug(
                    f"Using temporary package collection directory: {temp_package_dir}"
                )

                # Discover, copy main files, and copy licenses
                collected_files_info = self._discover_and_collect_files(
                    temp_package_dir
                )

                # Create manifest in the same temp directory
                manifest_path = self._create_manifest(temp_package_dir)

                # Create the final .tar.gz package
                self._package_files(collected_files_info, manifest_path)

            logger.info("Build process completed successfully.")

        except PgxmBuilderError:
            # Re-raise our specific errors
            raise
        except docker.errors.APIError as e:
            # Catch specific Docker SDK errors
            raise PgxmBuilderDockerError(f"Docker API error: {e}") from e
        except Exception as e:
            # Catch any other unexpected errors
            logger.error(f"Unexpected error during build: {e}", exc_info=True)
            raise PgxmBuilderError(f"Build failed unexpectedly: {e}") from e
        finally:
            # --- Cleanup ---
            self._cleanup()

    def _cleanup(self):
        """Cleans up Docker resources (image and container)."""
        if self.docker_client:
            try:
                if self.container_id:
                    logger.debug(f"Cleaning up container {self.container_id[:12]}...")
                    container = self.docker_client.containers.get(self.container_id)
                    if container.status == "running":
                        container.stop()
                    container.remove()
                    logger.debug("Container cleaned up.")
            except Exception as e:
                logger.warning(f"Error cleaning up container: {e}")

            try:
                if self.image_id:
                    logger.debug(f"Cleaning up image {self.image_id[:12]}...")
                    self.docker_client.images.remove(self.image_id, force=True)
                    logger.debug("Image cleaned up.")
            except Exception as e:
                logger.warning(f"Error cleaning up image: {e}")


# --- Backwards compatibility function ---
# Keep the original function signature for cli.py to call
def build_extension(**kwargs):
    """
    Backwards compatible function to build an extension.
    Delegates to the PgxmBuilder class.
    """
    builder = PgxmBuilder(**kwargs)
    builder.build()
