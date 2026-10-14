"""Step 5: export EAE-conformant 0-1 rasters (COG) with YAML metadata.

Inputs:  calibrated solar share, predicted grid share, population
Outputs: outputs/rwa_ogs_penetration_*.tif, outputs/rwa_ogs_underserved_*.tif + .yml
Owner:   C (model); see Part 11 of the team playbook.

    python -m solar_markets.export --config config.yml
"""

from __future__ import annotations

from solar_markets.config import cli_args, get_paths, load_config


def run(cfg: dict) -> None:
    raise NotImplementedError("solar_markets.export is not implemented yet")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
