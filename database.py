"""
Database module for MCP Banking Server.
Handles SQLite database connections, schema creation, and CRUD operations.
"""

import sqlite3
import secrets
import string
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
import json
import os

# Database file path
DB_PATH = os.path.join(os.path.dirname(__file__), "bank.db")

# Default API key (generated at startup)
DEFAULT_API_KEY: Optional[str] = None


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def generate_account_number() -> str:
    """Generate a unique 10-digit account number."""
    return ''.join(secrets.choice(string.digits) for _ in range(10))


def generate_api_key() -> str:
    """Generate a secure API key."""
    return f"bank_{secrets.token_urlsafe(32)}"


def init_database():
    """Initialize the database with all required tables."""
    global DEFAULT_API_KEY
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create accounts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_number TEXT UNIQUE NOT NULL,
                holder_name TEXT NOT NULL,
                balance REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        # Create transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                balance_after REAL NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (id)
            )
        """)
        
        # Create idempotency_keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                response TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """)
        
        # Create api_keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_account_number ON accounts(account_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_idempotency_key ON idempotency_keys(key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_key ON api_keys(key)")
        
        conn.commit()
        
        # Check if default API key exists, if not create one
        cursor.execute("SELECT key FROM api_keys WHERE name = 'default'")
        result = cursor.fetchone()
        
        if result:
            DEFAULT_API_KEY = result['key']
        else:
            DEFAULT_API_KEY = generate_api_key()
            cursor.execute(
                "INSERT INTO api_keys (key, name) VALUES (?, ?)",
                (DEFAULT_API_KEY, 'default')
            )
            conn.commit()
        
        print("\n" + "=" * 60)
        print("MCP Banking Server - Database Initialized")
        print("=" * 60)
        print(f"Database: {DB_PATH}")
        print(f"Default API Key: {DEFAULT_API_KEY}")
        print("=" * 60 + "\n")



def create_account(holder_name: str) -> Dict[str, Any]:
    """Create a new bank account."""
    account_number = generate_account_number()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Ensure unique account number
        while True:
            cursor.execute("SELECT id FROM accounts WHERE account_number = ?", (account_number,))
            if not cursor.fetchone():
                break
            account_number = generate_account_number()
        
        cursor.execute(
            "INSERT INTO accounts (account_number, holder_name) VALUES (?, ?)",
            (account_number, holder_name)
        )
        conn.commit()
        
        return {
            "account_number": account_number,
            "holder_name": holder_name,
            "balance": 0.0,
            "created_at": datetime.now().isoformat()
        }


def get_account(account_number: str) -> Optional[Dict[str, Any]]:
    """Get account details by account number."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM accounts WHERE account_number = ? AND is_active = 1",
            (account_number,)
        )
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None


def get_account_by_id(account_id: int) -> Optional[Dict[str, Any]]:
    """Get account details by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM accounts WHERE id = ? AND is_active = 1",
            (account_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None


def update_balance(account_id: int, new_balance: float) -> bool:
    """Update account balance."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE accounts SET balance = ? WHERE id = ?",
            (new_balance, account_id)
        )
        conn.commit()
        return cursor.rowcount > 0



def record_transaction(
    account_id: int,
    transaction_type: str,
    amount: float,
    balance_after: float,
    description: str = ""
) -> Dict[str, Any]:
    """Record a new transaction."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO transactions 
               (account_id, type, amount, balance_after, description) 
               VALUES (?, ?, ?, ?, ?)""",
            (account_id, transaction_type, amount, balance_after, description)
        )
        conn.commit()
        
        return {
            "id": cursor.lastrowid,
            "account_id": account_id,
            "type": transaction_type,
            "amount": amount,
            "balance_after": balance_after,
            "description": description,
            "created_at": datetime.now().isoformat()
        }


def get_transactions(account_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get transaction history for an account."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM transactions 
               WHERE account_id = ? 
               ORDER BY created_at DESC 
               LIMIT ?""",
            (account_id, limit)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_all_transactions(account_id: int) -> List[Dict[str, Any]]:
    """Get all transactions for an account (for CSV export)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM transactions 
               WHERE account_id = ? 
               ORDER BY created_at DESC""",
            (account_id,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


#Idempotency Operations 

def check_idempotency_key(key: str) -> Optional[Dict[str, Any]]:
    """Check if an idempotency key exists and is not expired."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT response FROM idempotency_keys 
               WHERE key = ? AND expires_at > ?""",
            (key, datetime.now().isoformat())
        )
        row = cursor.fetchone()
        
        if row:
            return json.loads(row['response'])
        return None


def store_idempotency_key(key: str, response: Dict[str, Any]) -> None:
    """Store an idempotency key with its response."""
    expires_at = datetime.now() + timedelta(hours=24)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO idempotency_keys 
               (key, response, expires_at) VALUES (?, ?, ?)""",
            (key, json.dumps(response), expires_at.isoformat())
        )
        conn.commit()


def cleanup_expired_idempotency_keys() -> int:
    """Remove expired idempotency keys."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM idempotency_keys WHERE expires_at < ?",
            (datetime.now().isoformat(),)
        )
        conn.commit()
        return cursor.rowcount


# API Key Operations 

def validate_api_key(key: str) -> bool:
    """Validate an API key."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM api_keys WHERE key = ? AND is_active = 1",
            (key,)
        )
        return cursor.fetchone() is not None


def get_default_api_key() -> str:
    """Get the default API key."""
    global DEFAULT_API_KEY
    if DEFAULT_API_KEY is None:
        init_database()
    return DEFAULT_API_KEY
