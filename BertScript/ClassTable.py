"""Legacy ClassTable Python API backed by adjacent authoritative CSV.

Callers may continue to use "from ClassTable import ClassTable" when BertScript
is their script directory, or "from BertScript.ClassTable import ClassTable".
"""
from pathlib import Path

if __package__:
    from .class_table_metadata import load_class_table
else:
    from class_table_metadata import load_class_table

ClassTable = load_class_table(Path(__file__).with_name("ClassTable.csv"))
