"""Step 6: interactive Folium map of the layers with sector popups.

Inputs:  outputs/*.tif, sector summary
Outputs: docs/map.html
Owner:   D (docs, map & pitch); see Part 12 of the team playbook.

    python -m solar_markets.webmap --config config.yml
"""

from __future__ import annotations

from solar_markets.config import cli_args, get_paths, load_config


def run(cfg: dict) -> None:
    raise NotImplementedError("solar_markets.webmap is not implemented yet")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
