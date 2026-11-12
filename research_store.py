"""Canonical study records, with transactional writes and optimistic revisions.

SQLite is for local rehearsals. Formal hosting requires external PostgreSQL or Azure SQL.
No participant records are stored in Git or Hugging Face repository history.
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class StoreConflict(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


class ResearchStore:
    def __init__(self, path=None, url=None):
        self.url=url if url is not None else os.environ.get('STUDY_DATABASE_URL')
        self.lock=threading.RLock()
        self.sqlserver = bool(self.url and self.url.startswith('mssql:'))
        if self.sqlserver:
            from sqlserver_store import SqlServerConnection
            self.conn = SqlServerConnection(self.url)
            self.remote = True
        elif self.url:
            import psycopg
            # Verify both CA and hostname; never downgrade on a certificate failure.
            import certifi
            from urllib.parse import urlparse
            ca=os.environ.get('STUDY_DATABASE_CA')
            if not ca and (urlparse(self.url).hostname or '').endswith(('.supabase.com','.supabase.co')):
                root=Path(__file__).resolve().parent
                ca=str(root/'supabase-ca.crt' if (root/'supabase-ca.crt').exists() else root/'deploy'/'supabase-ca.crt')
            try:
                self.conn=psycopg.connect(self.url, sslmode='verify-full', sslrootcert=ca or certifi.where(),
                                         connect_timeout=15, autocommit=True)
            except psycopg.Error:
                raise RuntimeError('Study database connection failed. Check its private credentials, availability and TLS certificate.') from None
            self.remote=True
        else:
            path=Path(path or os.environ.get('STUDY_DB_PATH',str(Path(os.environ.get('DB_PATH','db/pedagogy_rl.db')).parent/'research.db')))
            path.parent.mkdir(parents=True,exist_ok=True)
            self.conn=sqlite3.connect(path,check_same_thread=False,isolation_level=None)
            path.chmod(0o600)
            self.conn.execute('PRAGMA journal_mode=WAL')
            self.conn.execute('PRAGMA synchronous=FULL')
            self.remote=False
        if self.sqlserver:
            self.conn.initialize()
            return
        self.execute('''CREATE TABLE IF NOT EXISTS research_records (
          kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL, study TEXT NOT NULL,
          payload TEXT NOT NULL, revision INTEGER NOT NULL, updated TEXT NOT NULL,
          PRIMARY KEY (kind,id))''')

    def execute(self, sql, args=()):
        return self.conn.execute(sql.replace('?', '%s') if self.remote else sql,args)

    @contextmanager
    def transaction(self):
        with self.lock:
            if self.remote:
                with self.conn.transaction():yield
            else:
                self.execute('BEGIN IMMEDIATE')
                try:yield
                except BaseException:
                    self.execute('ROLLBACK');raise
                else:self.execute('COMMIT')

    def get(self, kind, id, owner=None):
        with self.lock:
            row=self.execute('SELECT owner,study,payload,revision,updated FROM research_records WHERE kind=? AND id=?',(kind,id)).fetchone()
        if not row or (owner is not None and row[0]!=owner):return None
        return {'kind':kind,'id':id,'owner':row[0],'study':row[1],'data':json.loads(row[2]),'revision':row[3],'updated':row[4]}

    def put(self, kind, id, owner, study, data, expected=0):
        encoded=json.dumps(data,ensure_ascii=False,allow_nan=False)
        with self.transaction():
            current=self.get(kind,id)
            if current and current['owner']!=owner:raise StoreConflict('Record owner mismatch')
            if (current['revision'] if current else 0)!=expected:raise StoreConflict('Record changed; reload before retrying')
            if current:
                changed=self.execute('UPDATE research_records SET payload=?,revision=?,updated=? WHERE kind=? AND id=? AND revision=?',
                      (encoded,expected+1,now(),kind,id,expected)).rowcount
                if changed!=1:raise StoreConflict('Concurrent record update')
            else:
                self.execute('INSERT INTO research_records VALUES (?,?,?,?,?,?,?)',(kind,id,owner,study,encoded,1,now()))
        return expected+1

    def records(self, kind=None, study=None, owner=None):
        sql='SELECT kind,id,owner,study,payload,revision,updated FROM research_records WHERE 1=1';args=[]
        for column,value in [('kind',kind),('study',study),('owner',owner)]:
            if value is not None:sql+=' AND '+column+'=?';args.append(value)
        with self.lock:rows=self.execute(sql+' ORDER BY kind,id',args).fetchall()
        return [dict(kind=r[0],id=r[1],owner=r[2],study=r[3],data=json.loads(r[4]),revision=r[5],updated=r[6]) for r in rows]

    def withdraw(self, owner, study):
        """Delete active identifiable study records and keep only a blocking tombstone.

        Operator-managed backups require separate expiry/deletion per the protocol.
        """
        with self.transaction():
            self.execute('DELETE FROM research_records WHERE owner=? AND study=?',(owner,study))
            self.execute('INSERT INTO research_records VALUES (?,?,?,?,?,?,?)',
               ('withdrawal',study+':'+owner,owner,study,json.dumps({'withdrawn_at':now()}),1,now()))

    def close(self):self.conn.close()

    def export(self):return {'schema':1,'exported':now(),'records':self.records()}

    def restore_empty(self, archive):
        """Restore only into an empty store; refuse overwriting existing observations."""
        if archive.get('schema')!=1 or not isinstance(archive.get('records'),list):raise ValueError('Invalid backup')
        with self.transaction():
            if self.records():raise ValueError('Restore requires an empty database')
            for r in archive['records']:
                if type(r['revision']) is not int or r['revision']<1:raise ValueError('Invalid backup revision')
                self.execute('INSERT INTO research_records VALUES (?,?,?,?,?,?,?)',
                  (r['kind'],r['id'],r['owner'],r['study'],json.dumps(r['data'],allow_nan=False),r['revision'],r['updated']))
