import sqlite3


def get_connection(db_path: str):
    """
    Returns a SQLite connection.
    """
    return sqlite3.connect(db_path)