"""OpenCC integration adapter for DatasetConverter text conversion."""


def convert_text(text, conversion):
    """Convert text with the legacy OpenCC configuration on demand.

    The local import keeps readers that do not request script conversion from
    requiring the optional OpenCC runtime merely to import ``sampleHandler``.
    """

    from opencc import OpenCC

    return OpenCC(conversion).convert(text)
