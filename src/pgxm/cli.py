# src/pgxm/cli.py
import click

# Import the build function from the build module
from .build import build_extension


# --- Main CLI Group ---
@click.group()
@click.version_option(version="0.1.0")  # Matches pyproject.toml
def cli():
    """pgxm: A CLI tool for PostgreSQL extensions, inspired by Trunk."""
    pass  # The group itself doesn't do much, subcommands do the work


# --- Build Command ---
# The @cli.command() decorator means the actual CLI command will be 'pgxm build'
@cli.command(
    name="build"
)  # Explicitly set the command name (optional if function name matches)
@click.option(
    "-p",
    "--path",
    default=".",
    help="The file path of the extension to build [default: .]",
)
@click.option("-o", "--output-path", help="Output directory for the built package.")
@click.option("-v", "--version", help="Override the extension version.")
@click.option("-n", "--name", help="Override the extension name.")
@click.option(
    "-e", "--extension-name", help="Override the extension name from control file."
)
@click.option(
    "-x",
    "--extension-dependencies",
    help="Comma-separated list of extension dependencies.",
)
@click.option(
    "-s", "--preload-libraries", help="Comma-separated list of preload libraries."
)
@click.option("-P", "--platform", help="Target platform (e.g., linux/amd64).")
@click.option("-d", "--dockerfile", help="Path to a custom Dockerfile.")
@click.option("-i", "--install-command", help="Custom install command.")
@click.option(
    "-t", "--test", is_flag=True, help="Run integration tests after building."
)
@click.option(
    "--pg-version",
    default="15",
    help="PostgreSQL version to build against [default: 15].",
)
def build(  # This function name is now 'build'
    path,
    output_path,
    version,
    name,
    extension_name,
    extension_dependencies,
    preload_libraries,
    platform,
    dockerfile,
    install_command,
    test,
    pg_version,
):
    """Build a PostgreSQL extension."""
    try:
        # Call the core build logic from pgxm.build
        build_extension(
            path=path,
            output_path=output_path,
            version=version,
            name=name,
            extension_name=extension_name,
            extension_dependencies=extension_dependencies,
            preload_libraries=preload_libraries,
            platform=platform,
            dockerfile=dockerfile,
            install_command=install_command,
            test=test,
            pg_version=pg_version,
        )
        click.echo("Build completed successfully.")
    except click.ClickException:
        # Re-raise ClickExceptions (they handle their own output)
        raise
    except Exception as e:
        # Catch any other unexpected errors and present them nicely
        click.echo(f"An unexpected error occurred during build: {e}", err=True)
        raise click.ClickException("Build failed.") from e


# --- Publish Command (Placeholder) ---
@cli.command()
@click.argument("name", required=False)  # Name can be provided as an argument
@click.option("-e", "--extension-name", help="Extension name (if different from NAME).")
@click.option(
    "-x",
    "--extension-dependencies",
    help="Comma-separated list of extension dependencies.",
)
@click.option(
    "-s", "--preload-libraries", help="Comma-separated list of preload libraries."
)
@click.option("-v", "--version", help="Version of the extension.")
@click.option("-f", "--file", help="Path to the built extension archive.")
@click.option("-d", "--description", help="Description of the extension.")
@click.option("-D", "--documentation", help="URL to the documentation.")
@click.option("-H", "--homepage", help="URL to the homepage.")
@click.option("-l", "--license", help="License of the extension.")
@click.option(
    "-r",
    "--registry",
    default="https://your-registry-url.com",
    help="Registry URL [default: ...].",
)
@click.option("-R", "--repository", help="URL to the source code repository.")
@click.option("-c", "--category", help="Category for the extension.")
def publish(
    name,
    extension_name,
    extension_dependencies,
    preload_libraries,
    version,
    file,
    description,
    documentation,
    homepage,
    license,
    registry,
    repository,
    category,
):
    """Publish a PostgreSQL extension to the registry."""
    click.echo("Publishing extension...")
    click.echo(f"  Name: {name}")
    click.echo(f"  Extension Name: {extension_name}")
    click.echo(f"  Version: {version}")
    click.echo(f"  File: {file}")
    click.echo(f"  Registry: {registry}")
    # --- TODO: Implement actual publish logic here ---
    # This is where you'd:
    # 1. Read package manifest if file not provided
    # 2. Authenticate with registry (using env var for token)
    # 3. Upload file and metadata via HTTP
    click.echo(
        "Publish logic placeholder. Implementation needed (Registry interaction)."
    )


# --- Install Command (Placeholder) ---
@cli.command()
@click.argument("name")  # Name is required for install
@click.option("-p", "--pg-config", help="Path to pg_config binary.")
@click.option("-f", "--file", help="Path to a local extension archive.")
@click.option(
    "-v", "--version", default="latest", help="Version to install [default: latest]."
)
@click.option(
    "-r",
    "--registry",
    default="https://your-registry-url.com",
    help="Registry URL [default: ...].",
)
@click.option(
    "--pg-version", help="PostgreSQL version for installation (experimental)."
)
@click.option(
    "-s", "--skip-dependencies", is_flag=True, help="Skip dependency resolution."
)
def install(name, pg_config, file, version, registry, pg_version, skip_dependencies):
    """Install a PostgreSQL extension from the registry."""
    click.echo("Installing extension...")
    click.echo(f"  Name: {name}")
    click.echo(f"  Version: {version}")
    click.echo(f"  File: {file}")
    click.echo(f"  Registry: {registry}")
    click.echo(f"  Skip Dependencies: {skip_dependencies}")
    # --- TODO: Implement actual install logic here ---
    # This is where you'd:
    # 1. Use pg_config to find install dirs
    # 2. Resolve dependencies (unless skipped)
    # 3. Download package from registry (or use local file)
    # 4. Extract archive
    # 5. Copy files to PG directories
    click.echo(
        "Install logic placeholder. Implementation needed (Registry interaction)."
    )


# --- Main Entry Point ---
def main():
    """Entry point for the pgxm CLI."""
    cli()  # Call the main CLI group


if __name__ == "__main__":
    main()  # Allows running the script directly (python -m pgxm.cli)
