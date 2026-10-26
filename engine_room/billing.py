"""Connector-neutral billing identifiers; no provider names or currency conversion."""
import re


def valid_unit(value):
    return isinstance(value,str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}",value) is not None


def valid_scope(value):
    # A rental-specific reading and an account-total reading are different limits.
    return isinstance(value,str) and value in {"rental","account"}
