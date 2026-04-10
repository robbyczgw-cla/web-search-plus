import os
import sys
from pathlib import Path


def is_docker() -> bool:
    """Detect if running inside a Docker container.
    
    Checks multiple signals:
    - /.dockerenv file
    - /proc/1/cgroup containing 'docker' or 'kubepods'
    - DOCKER environment variable
    """
    if os.path.exists("/.dockerenv"):
        return True
    
    try:
        with open("/proc/1/cgroup", "r") as f:
            cgroup = f.read().lower()
            if "docker" in cgroup or "kubepods" in cgroup:
                return True
    except (FileNotFoundError, PermissionError):
        pass
    
    if os.environ.get("DOCKER"):
        return True
    
    return False


def get_searxng_url() -> str:
    """Get the appropriate SearXNG URL based on environment.
    
    Returns:
        - http://172.17.0.1:8080 if running in Docker
        - http://127.0.0.1:8080 if running on host
    """
    if is_docker():
        return "http://172.17.0.1:8080"
    return "http://127.0.0.1:8080"


def ensure_searxng_env():
    """Set SEARXNG_INSTANCE_URL environment variable if not already set."""
    if "SEARXNG_INSTANCE_URL" not in os.environ:
        os.environ["SEARXNG_INSTANCE_URL"] = get_searxng_url()


if __name__ == "__main__":
    print(f"In Docker: {is_docker()}")
    print(f"SearXNG URL: {get_searxng_url()}")