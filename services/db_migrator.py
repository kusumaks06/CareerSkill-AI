"""
Database Schema Migration & Auto-Upgrade Service for CareerSkill AI.
Ensures seamless schema evolution without data loss when new columns or tables are added.
"""
import sys
import logging
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def migrate_database_schema(db, app, seed_admin=False):
    """
    Safely inspects the active SQLite database, applies required schema upgrades,
    adds any missing columns with safe defaults, and preserves all existing data.
    """
    with app.app_context():
        try:
            engine = db.engine

            # 1. First ensure all tables defined in metadata exist
            db.create_all()

            # 2. Check if 'users' table exists and has missing columns
            inspector = inspect(engine)
            if inspector.has_table('users'):
                user_cols = {c['name'].lower() for c in inspector.get_columns('users')}
                with engine.connect() as conn:
                    # Upgrade 'is_admin'
                    if 'is_admin' not in user_cols:
                        print("[*] Migrating schema: adding 'is_admin' to users table...")
                        conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))
                        conn.commit()

                    # Upgrade 'is_active'
                    if 'is_active' not in user_cols:
                        print("[*] Migrating schema: adding 'is_active' to users table...")
                        conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
                        conn.commit()

                    # Upgrade 'role'
                    if 'role' not in user_cols:
                        print("[*] Migrating schema: adding 'role' to users table...")
                        conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT 'user'"))
                        conn.commit()

                    # Upgrade 'first_login'
                    if 'first_login' not in user_cols:
                        print("[*] Migrating schema: adding 'first_login' to users table...")
                        conn.execute(text("ALTER TABLE users ADD COLUMN first_login BOOLEAN NOT NULL DEFAULT 0"))
                        conn.commit()

                    # Clean nulls in users table
                    conn.execute(text("UPDATE users SET is_admin = 0 WHERE is_admin IS NULL"))
                    conn.execute(text("UPDATE users SET is_active = 1 WHERE is_active IS NULL"))
                    conn.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''"))
                    conn.execute(text("UPDATE users SET first_login = 0 WHERE first_login IS NULL"))
                    conn.commit()

            # 3. Dynamic generic migration for all other registered models
            # This future-proofs the database against any new compatible columns
            current_inspector = inspect(engine)
            for table_name, table in db.metadata.tables.items():
                if current_inspector.has_table(table_name):
                    existing_cols = {c['name'].lower() for c in inspect(engine).get_columns(table_name)}
                    for col in table.columns:
                        col_name_lower = col.name.lower()
                        if col_name_lower not in existing_cols:
                            # Construct safe SQLite column definition
                            type_str = str(col.type).upper()
                            default_clause = ""
                            
                            if "BOOLEAN" in type_str:
                                default_val = "1" if (col.default and str(col.default.arg).lower() in ['true', '1']) else "0"
                                default_clause = f"DEFAULT {default_val}"
                            elif "INT" in type_str:
                                default_clause = "DEFAULT 0"
                            elif "FLOAT" in type_str or "NUMERIC" in type_str:
                                default_clause = "DEFAULT 0.0"
                            elif "VARCHAR" in type_str or "TEXT" in type_str or "STRING" in type_str:
                                default_clause = "DEFAULT ''"
                            elif "DATETIME" in type_str or "TIMESTAMP" in type_str:
                                default_clause = ""

                            sql_stmt = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {type_str} {default_clause}"
                            sql_stmt = " ".join(sql_stmt.split())  # normalize spaces

                            print(f"[*] Auto-migrating missing column: {table_name}.{col.name}...")
                            with engine.connect() as conn:
                                conn.execute(text(sql_stmt))
                                conn.commit()

            # 4. Seed default super-admin if no admin account exists in development/production
            if seed_admin or not app.config.get('TESTING'):
                from models.user import User
                admin_user = User.query.filter((User.is_admin == True) | (User.role == 'admin')).first()
                if not admin_user:
                    default_admin_email = "admin@careerskill.ai"
                    existing_account = User.query.filter_by(email=default_admin_email).first()
                    if existing_account:
                        existing_account.is_admin = True
                        existing_account.role = 'admin'
                        existing_account.is_active = True
                        db.session.commit()
                        print(f"[+] Promoted existing user '{default_admin_email}' to Platform Admin.")
                    else:
                        new_admin = User(
                            full_name="Platform Admin",
                            email=default_admin_email,
                            is_admin=True,
                            is_active=True,
                            role="admin"
                        )
                        new_admin.set_password("AdminMaster2026!")
                        db.session.add(new_admin)
                        db.session.commit()
                        print(f"[+] Initialized default Platform Admin '{default_admin_email}'.")

        except Exception as e:
            print(f"[-] Database migration notice: {e}", file=sys.stderr)
