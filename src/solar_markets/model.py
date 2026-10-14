"""Step 3: train LightGBM, report random vs blocked CV, explain with SHAP, predict every pixel.

Inputs:  data/processed/train_table.csv, data/processed/feature_stack.tif
Outputs: models/lgbm.txt, reports/cv_results.csv, outputs/solar_share_pred.tif
Owner:   C (model); see Part 9 of the team playbook.

    python -m solar_markets.model --config config.yml
"""

from __future__ import annotations

from solar_markets.config import cli_args, get_paths, load_config


def run(cfg: dict) -> None:
    raise NotImplementedError("solar_markets.model is not implemented yet")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
