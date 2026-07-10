from investor_egx.cli import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            [
                "run-all",
                "--intraday-interval",
                "1m",
                "--intraday-days-back",
                "7",
            ]
        )
    )
