import yaml


def load_config(filename: str) -> None:
    with open(filename, "r") as f:
        config = yaml.safe_load(f)

    return config
