"""Step 4: logit-shift calibration so the national total matches the control total.

Inputs:  outputs/solar_share_pred.tif, population band, calibration target in config.yml
Outputs: outputs/solar_share_calibrated.tif
Owner:   C (model); see Part 10 of the team playbook.

    python -m solar_markets.calibrate --config config.yml
"""

from __future__ import annotations

from solar_markets.config import cli_args, get_paths, load_config


def run(cfg: dict) -> None:
    raise NotImplementedError("solar_markets.calibrate is not implemented yet")


def main() -> None:
    args = cli_args(__doc__.splitlines()[0])
    cfg = load_config(args.config)
    get_paths(cfg).ensure()
    run(cfg)


if __name__ == "__main__":
    main()
