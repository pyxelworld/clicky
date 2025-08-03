import sqlite3
import os

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'sixsec.db')

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns

def upgrade_database():
    if not os.path.exists(db_path):
        print(f"Banco de dados '{db_path}' não encontrado. Ele será criado na primeira execução do app.")
        return

    print(f"Conectando ao banco de dados em: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\nVerificando tabela 'notification'...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification'")
    if not cursor.fetchone():
        print(" -> Tabela 'notification' não encontrada. Criando...")
        cursor.execute("""
            CREATE TABLE notification (
                id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                actor_id INTEGER,
                action_type VARCHAR(50) NOT NULL,
                target_post_id INTEGER,
                target_comment_id INTEGER,
                is_read BOOLEAN NOT NULL,
                timestamp DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY(recipient_id) REFERENCES user (id),
                FOREIGN KEY(actor_id) REFERENCES user (id),
                FOREIGN KEY(target_post_id) REFERENCES post (id),
                FOREIGN KEY(target_comment_id) REFERENCES comment (id)
            )
        """)
        print(" -> Tabela 'notification' criada.")
    else:
        print(" -> Tabela 'notification' já existe.")

    print("\nVerificando tabela 'post_view'...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='post_view'")
    if not cursor.fetchone():
        print(" -> Tabela 'post_view' não encontrada. Criando...")
        cursor.execute("""
            CREATE TABLE post_view (
                id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                timestamp DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY(user_id) REFERENCES user (id),
                FOREIGN KEY(post_id) REFERENCES post (id)
            )
        """)
        print(" -> Tabela 'post_view' criada.")
    else:
        print(" -> Tabela 'post_view' já existe.")

    print("\nVerificando coluna 'last_notification_read_time' na tabela 'user'...")
    if not column_exists(cursor, 'user', 'last_notification_read_time'):
        print(" -> Coluna não encontrada. Adicionando 'last_notification_read_time'...")
        cursor.execute("ALTER TABLE user ADD COLUMN last_notification_read_time DATETIME")
        print(" -> Coluna adicionada.")
    else:
        print(" -> Coluna já existe.")

    conn.commit()
    conn.close()
    print("\nAtualização do banco de dados concluída.")

if __name__ == '__main__':
    upgrade_database()