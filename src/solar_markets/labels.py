"""Step 1: build survey labels (solar, grid and unserved household shares per area).

Inputs:  census microdata or DHS household recode + GPS, admin boundaries (data/raw)
Outputs: data/processed/labels.gpkg
Owner:   A (labels & data); see Part 7 of the team playbook.

    python -m solar_markets.labels --config config.yml
"""

from __future__ import annotations

from solar_markets.config import cli_args, get_paths, load_config


def run(cfg: dict) -> None:
    raise NotImplementedError("solar_markets.labels is not implemented yet")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
