"""
Web dashboard module for the technical blog monitor.

This module provides a simple web interface to browse discovered posts,
view details, and perform basic searches.
"""
from monitor.web.app import create_app

__all__ = ["create_app"]
