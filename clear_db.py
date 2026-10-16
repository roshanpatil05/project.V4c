from src.database.db_manager import DatabaseConnection
from src.config.settings import settings

def clear_database():
    conn = DatabaseConnection().get_connection()
    cursor = conn.cursor()
    
    db_name = settings.database
    print(f"Attempting to DROP and recreate database '{db_name}'...")
    
    try:
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name};")
        cursor.execute(f"CREATE DATABASE {db_name};")
        cursor.execute(f"USE {db_name};")
        conn.commit()
        print("\n✅ Database dropped and recreated successfully! You can now run run_schema.py")
    except Exception as e:
        print(f"\n❌ Failed. Your cloud user might not have permission to drop databases: {e}")
    finally:
        cursor.close()

if __name__ == "__main__":
    clear_database()
