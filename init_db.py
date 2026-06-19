import sqlite3
import hashlib
import os

def hash_password(password):
    """Gera um hash seguro com Salt aleatório (32 bytes)."""
    salt = os.urandom(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt + pwd_hash

def inicializar_sistema():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    print("Verificando perfis...")
    perfis = [(1, 'Admin'), (2, 'Operador'), (3, 'Auditor')]
    cursor.executemany('INSERT OR IGNORE INTO perfis (id, nome) VALUES (?, ?)', perfis)

    # Lista de usuários iniciais para teste (Usuario, Senha, Perfil_ID)
    usuarios_iniciais = [
        ('admin', 'admin123', 1),
        ('operador_rh', 'rh123', 2),
        ('auditor_fiscal', 'audit123', 3)
    ]

    print("Criando usuários iniciais com criptografia...")
    for username, senha_pura, perfil_id in usuarios_iniciais:
        senha_cripto = hash_password(senha_pura)
        try:
            cursor.execute('''INSERT INTO usuarios (username, senha, perfil_id) 
                              VALUES (?, ?, ?)''', (username, senha_cripto, perfil_id))
            print(f"Usuário '{username}' criado com sucesso.")
        except sqlite3.IntegrityError:
            print(f"Usuário '{username}' já existe. Pulando...")

    conn.commit()
    conn.close()
    print("\nSistema inicializado com sucesso! Use essas credenciais no seu app Flask.")



if __name__ == '__main__':
    inicializar_sistema()