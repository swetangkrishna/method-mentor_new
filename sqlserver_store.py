"""TLS-verified SQL Server adapter for the canonical research record store."""
import os
import logging
import re
from contextlib import contextmanager
from urllib.parse import urlparse, unquote

import certifi

SCHEMA = """
IF OBJECT_ID(N'dbo.research_records', N'U') IS NULL
CREATE TABLE dbo.research_records (
 kind NVARCHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
 id NVARCHAR(350) COLLATE Latin1_General_100_BIN2 NOT NULL,
 owner NVARCHAR(256) COLLATE Latin1_General_100_BIN2 NOT NULL,
 study NVARCHAR(256) COLLATE Latin1_General_100_BIN2 NOT NULL,
 payload NVARCHAR(MAX) NOT NULL,
 revision INT NOT NULL,
 updated NVARCHAR(40) NOT NULL,
 CONSTRAINT PK_research_records PRIMARY KEY (kind, id)
)
"""


class Result:
    """Detached result: close TDS cursors before another statement starts."""
    def __init__(self, rows, rowcount):
        self.rows = rows
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _ConnectionDiagnostic(logging.Handler):
    """Log network routing failures without credentials or query contents."""
    def emit(self, record):
        if not record.exc_info:
            return
        error = str(record.exc_info[1])
        match = re.search(r"Client with IP address '([0-9.]+)'", error)
        if match:
            print('AZURE_SQL_NETWORK_CHECK client_ip=' + match.group(1), flush=True)
        elif 'Login failed' in error:
            print('AZURE_SQL_NETWORK_CHECK login_rejected', flush=True)


class SqlServerConnection:
    def __init__(self, url):
        self._url = url
        self._in_transaction = False
        import pytds
        logger = logging.getLogger("pytds")
        diagnostic = _ConnectionDiagnostic()
        previous_level = logger.level
        if os.environ.get("AZURE_SQL_NETWORK_DIAGNOSTICS") == "1":
            logger.addHandler(diagnostic)
            logger.setLevel(logging.INFO)
        try:
            parsed = urlparse(url)
            if (parsed.scheme != 'mssql' or not parsed.hostname or not parsed.username
                    or not parsed.password or not parsed.path.strip('/')
                    or parsed.query or parsed.fragment):
                raise ValueError('Invalid configuration')
            self.conn = pytds.connect(
                server=parsed.hostname, port=parsed.port or 1433,
                database=unquote(parsed.path.lstrip('/')),
                user=unquote(parsed.username), password=unquote(parsed.password),
                cafile=os.environ.get('STUDY_DATABASE_CA') or certifi.where(),
                validate_host=True, enc_login_only=False,
                login_timeout=15, timeout=30, autocommit=True,
                appname='Method Mentor', pooling=False,
            )
        except (pytds.Error, OSError, ValueError):
            raise RuntimeError('Azure SQL connection failed. Check private credentials, firewall access and TLS certificate.') from None
        finally:
            logger.removeHandler(diagnostic)
            logger.setLevel(previous_level)

    def _ensure_connection(self):
        """Reconnect only during a read-only preflight, never replay a write."""
        import pytds
        try:
            with self.conn.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchall()
        except (pytds.OperationalError, pytds.InterfaceError, OSError):
            try:
                self.conn.close()
            except Exception:
                pass
            self.__init__(self._url)
            logging.getLogger(__name__).info('Azure SQL connection renewed before operation')

    def execute(self, sql, args=()):
        # All callers serialize access through ResearchStore.lock.
        if not self._in_transaction:
            self._ensure_connection()
        sql = sql.replace('research_records', 'dbo.research_records')
        with self.conn.cursor() as cursor:
            cursor.execute(sql, args)
            rows = cursor.fetchall() if cursor.description else []
            return Result(rows, cursor.rowcount)

    def initialize(self):
        with self.conn.cursor() as cursor:
            cursor.execute(SCHEMA)

    @contextmanager
    def transaction(self):
        self._ensure_connection()
        self.conn.autocommit = False
        self._in_transaction = True
        try:
            yield
            self.conn.commit()
        except BaseException:
            try:
                self.conn.rollback()
            except Exception:
                pass  # Preserve the original error; do not replay uncertain writes.
            raise
        finally:
            self._in_transaction = False
            try:
                self.conn.autocommit = True
            except Exception:
                pass  # The next preflight will detect and replace a dead connection.

    def close(self):
        self.conn.close()
