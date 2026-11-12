import os
import importlib.util
import unittest
from unittest.mock import MagicMock, patch

from research_store import ResearchStore
from sqlserver_store import SqlServerConnection, SCHEMA


@unittest.skipUnless(importlib.util.find_spec('pytds'), 'Install requirements-azure-sql.txt')
class SqlServerTests(unittest.TestCase):
    def test_tls_unicode_and_parameter_binding(self):
        with patch('pytds.connect') as connect:
            connection = connect.return_value
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.description = [('payload',)]
            cursor.fetchall.return_value = [('Éire 教学',)]
            store = ResearchStore(url='mssql://user:p%40ss@server.database.windows.net/study')
            args = connect.call_args.kwargs
            self.assertTrue(args['validate_host'])
            self.assertFalse(args['enc_login_only'])
            self.assertTrue(args['cafile'])
            self.assertEqual(args['password'], 'p@ss')
            result = store.execute('SELECT payload FROM research_records WHERE owner=?', ('CaseSensitive',))
            self.assertEqual(result.fetchone(), ('Éire 教学',))
            self.assertEqual(cursor.execute.call_args.args,
                ('SELECT payload FROM dbo.research_records WHERE owner=%s', ('CaseSensitive',)))
            self.assertIn('NVARCHAR(MAX)', SCHEMA)
            self.assertIn('Latin1_General_100_BIN2', SCHEMA)
            self.assertTrue(store.remote)

    def test_commit_and_rollback(self):
        with patch('pytds.connect') as connect:
            adapter = SqlServerConnection('mssql://u:p@host/db')
            with adapter.transaction(): pass
            connect.return_value.commit.assert_called_once()
            with self.assertRaises(ValueError):
                with adapter.transaction():raise ValueError('validation')
            connect.return_value.rollback.assert_called_once()
            self.assertTrue(connect.return_value.autocommit)

    def test_connection_errors_do_not_expose_credentials(self):
        import pytds
        with patch('pytds.connect', side_effect=pytds.OperationalError('PRIVATE_PASSWORD')):
            with self.assertRaises(RuntimeError) as e:
                SqlServerConnection('mssql://u:PRIVATE_PASSWORD@host/db')
        self.assertNotIn('PRIVATE_PASSWORD', str(e.exception))
        with self.assertRaises(RuntimeError):
            SqlServerConnection('mssql://u:p@host/db?TrustServerCertificate=yes')

    @unittest.skipUnless(os.environ.get('TEST_AZURE_SQL_URL'), 'Azure SQL integration URL not configured')
    def test_live_roundtrip_ownership_conflicts_and_cleanup(self):
        import uuid
        from research_store import StoreConflict
        store = ResearchStore(url=os.environ['TEST_AZURE_SQL_URL'])
        key = 'integration-' + uuid.uuid4().hex
        try:
            self.assertEqual(store.put('test', key, key, key, {'text':'Éire 教学'}), 1)
            self.assertIsNone(store.get('test', key, key.upper()))
            self.assertEqual(store.get('test', key, key)['data']['text'], 'Éire 教学')
            with self.assertRaises(StoreConflict):store.put('test', key, key, key, {}, expected=0)
            self.assertEqual(store.put('test', key, key, key, {'updated':True}, expected=1), 2)
            with self.assertRaises(ValueError):
                with store.transaction():
                    store.execute('DELETE FROM research_records WHERE kind=? AND id=?', ('test',key))
                    raise ValueError('rollback probe')
            self.assertIsNotNone(store.get('test',key))
        finally:
            store.execute('DELETE FROM research_records WHERE kind=? AND id=?', ('test',key))
            store.close()
