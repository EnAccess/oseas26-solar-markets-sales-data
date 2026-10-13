"""Step 2: build the 1 km feature stack and the training table.

Inputs:  Earth Engine datasets, Meta RWI CSV, Gridfinder lines, labels.gpkg
Outputs: data/processed/feature_stack.tif, data/processed/train_table.csv
Owner:   B (features); see Part 8 of the team playbook.

    python -m solar_markets.features --config config.yml
"""

from __future__ import annotations

from solar_markets.config import cli_args, get_paths, load_config


def run(cfg: dict) -> None:
    raise NotImplementedError("solar_markets.features is not implemented yet")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
