"""Test setup: never write MLflow traces from unit tests."""

import os

os.environ["EDIP_TRACING"] = "off"
