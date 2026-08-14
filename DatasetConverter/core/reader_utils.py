"""Dependency-free helpers used by DatasetConverter's sample reader."""

import math
import os


def normalize_filename(filename):
    return str(filename).replace("\\", "/")


def filename_extension(filename, *, lower=False):
    extension = os.path.basename(filename).rpartition(".")[2]
    return extension.lower() if lower else extension


def sanitize_filename(title):
    result = title.replace("'", "’")
    for character in ('/', '\\', ':', '?', '"', '<', '>', '|', '\n', '\xa0', '\t', '*'):
        result = result.replace(character, "_")
    return result


def intersect_lists(left, right):
    return list(set(left) & set(right))


def wrap_text(text, width, piece_limit=math.inf):
    return [
        text[index : index + width]
        for index in range(0, min(len(text), piece_limit * width), width)
    ]
