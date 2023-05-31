import json
import logging
from collections import defaultdict
from pathlib import Path

from datasets import Dataset

from ue_abssum.data.preprocessing import (
    _add_id_column_to_datasets,
    _use_train_subset,
    _filter_quantiles,
)

log = logging.getLogger()


def load_from_json_or_csv(config, cache_dir=None):
    text_name = config.text_name
    label_name = config.label_name

    path = Path(config.path) / config.dataset_name / "train.csv"
    # The dataset may be not processed yet
    if path.exists():
        dataset = Dataset.from_csv(str(path))
    else:
        path = Path(config.path) / config.dataset_name / "train.json"
        if path.exists():
            dataset = Dataset.from_json(str(path))
        else:
            convert_list_of_dicts_to_dict(
                Path(config.path) / config.dataset_name, "dataset.json", text_name
            )
            dataset = Dataset.from_json(str(path))

    dataset = dataset.remove_columns(
        [x for x in dataset.column_names if x not in [text_name, label_name, "id"]]
    )

    if isinstance(config.get("test_size_split"), int):
        train_size_split = (len(dataset) - config.get("test_size_split")) / len(dataset)
    elif isinstance(config.get("test_size_split"), float):
        train_size_split = 1 - config.get("test_size_split")
    else:
        train_size_split = config.get("train_size_split", 0.8)
    splitted_dataset = dataset.train_test_split(
        train_size=train_size_split,
        shuffle=True,
        seed=config.get("seed", 42),
    )
    train_dataset, test_dataset = splitted_dataset["train"], splitted_dataset["test"]

    log.info(f"Loaded train size: {len(train_dataset)}")
    log.info(f"Loaded test size: {len(test_dataset)}")
    log.info("Dev dataset coincides with test dataset")

    if getattr(config, "filter_quantiles", None) is not None:
        train_dataset = _filter_quantiles(
            train_dataset,
            config.filter_quantiles,
            cache_dir,
            text_name,
            config.tokenizer_name,
        )

    if getattr(config, "use_subset", None) is not None:
        train_dataset = _use_train_subset(
            train_dataset,
            config.use_subset,
            getattr(config, "seed", 42),
            label_name,
        )

    if ("id" not in train_dataset.column_names) and config.get("add_id_column", True):
        train_dataset, test_dataset = _add_id_column_to_datasets(
            [train_dataset, test_dataset]
        )

    if getattr(config, "dev_size_split") is None:
        log_dataset_lengths(train_dataset, test_dataset)
        return [train_dataset, test_dataset, test_dataset]

    dev_size_split = config.dev_size_split
    if isinstance(dev_size_split, int):
        dev_size_split = (len(train_dataset) - dev_size_split) / len(train_dataset)
    splitted_dataset = train_dataset.train_test_split(
        train_size=1 - dev_size_split,
        shuffle=True,
        seed=config.get("seed", 42),
    )
    train_dataset, dev_dataset = splitted_dataset["train"], splitted_dataset["test"]
    log_dataset_lengths(train_dataset, test_dataset, dev_dataset)
    return [train_dataset, dev_dataset, test_dataset]


def convert_list_of_dicts_to_dict(path, filename, text_name):
    with open(Path(path) / filename) as f:
        data = json.load(f)
    data_dict = defaultdict(list)
    for item in data:
        for key, value in item.items():
            if isinstance(value, dict):
                value = list(value.values())
            # Since keys may start with '_'
            if (key == text_name or key[1:] == text_name) and isinstance(value, list):
                value = "\n".join(value)
            if key.startswith("_"):
                key = key[1:]
            data_dict[key].append(value)
    dataset = Dataset.from_dict(data_dict)
    dataset.to_json(Path(path) / "train.json")


def log_dataset_lengths(train_dataset, test_dataset, dev_dataset=None):
    log.info(f"Loaded train size: {len(train_dataset)}")
    log.info(f"Loaded test size: {len(test_dataset)}")
    if dev_dataset is None:
        log.info("Dev dataset coincides with test dataset")
    else:
        log.info(f"Loaded dev size: {len(dev_dataset)}")
