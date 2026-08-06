"""Arduino App Lab entrypoint for the LightWeave native receiver."""

from lightweave_uno import main

if __name__ == "__main__":
    raise SystemExit(main(["serve", "--host", "0.0.0.0", "--port", "7000"]))
