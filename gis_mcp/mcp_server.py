from __future__ import annotations

import os

import django
from mcp.server.fastmcp import FastMCP

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from . import services  # noqa: E402

mcp = FastMCP("OpenSkagit GIS MCP")


@mcp.tool()
def gis_answer_rule() -> dict:
    return services.gis_answer_rule()


@mcp.tool()
def list_gis_layers() -> dict:
    return services.list_gis_layers()


@mcp.tool()
def get_gis_layer_metadata(layer: str) -> dict:
    return services.get_gis_layer_metadata(layer)


@mcp.tool()
def get_parcel_gis(parcel: str, include_geometry: bool = True) -> dict:
    return services.get_parcel_gis(parcel, include_geometry)


@mcp.tool()
def get_parcel_overlays(
    parcel: str,
    bundles: str | list[str] | None = None,
    layers: str | list[str] | None = None,
    include_parcel_geometry: bool = True,
) -> dict:
    return services.get_parcel_overlays(parcel, bundles, layers, include_parcel_geometry)


@mcp.tool()
def query_gis_layer(layer: str, where: str = "1=1", limit: int = 10, include_geometry: bool = False) -> dict:
    return services.query_gis_layer(layer, where, limit, include_geometry)


if __name__ == "__main__":
    mcp.run()
