"""Application configuration for the Insider Threat Detection System.

Central location for tunable parameters so detection thresholds remain
configurable (AT2 FR5) rather than hard-coded across modules.
"""
import os

# Project root = parent of this app/ package directory.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")


class Config:
    """Base configuration shared by all run modes."""

    # --- Detection thresholds: Z-score severity bands (AT2 FR5 / FR6) ---
    # Bands are mutually exclusive:
    #   Low:    Z_LOW    <= Z < Z_MEDIUM
    #   Medium: Z_MEDIUM <= Z < Z_HIGH
    #   High:   Z >= Z_HIGH
    # A record with max deviation below Z_LOW is not flagged.
    Z_LOW = 2.5
    Z_MEDIUM = 3.0
    Z_HIGH = 4.0

    # Minimum historical activity records required before a per-user
    # statistical baseline is generated (AT2 FR3 / Objective 2).
    MIN_RECORDS = 20

    # --- Database ---
    DB_PATH = os.path.join(INSTANCE_DIR, "itd.sqlite")

    # --- Flask ---
    TESTING = False


class TestingConfig(Config):
    """Configuration used by the pytest suite.

    Points at a separate database file so tests never touch demo data.
    """

    TESTING = True
    DB_PATH = os.path.join(INSTANCE_DIR, "itd_test.sqlite")
